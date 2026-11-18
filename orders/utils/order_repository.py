import json

from utils.database import db
from utils.phone import normalize_phone
from models import (
    Customer,
    OrderDish,
    OrderMeta,
    OrderRequest,
    OrderResponse,
    StatusEvent,
    StatusResponse,
)


class OrderNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


class CourierNotFound(Exception):
    pass


ALLOWED_TRANSITIONS = {
    "new": {"started", "cancelled"},
    "started": {"ready", "cancelled"},
    "ready": {"assigned", "cancelled"},
    "assigned": {"picked_up", "cancelled", "failed"},
    "picked_up": {"delivered", "failed"},
    "delivered": set(),
    "failed": set(),
    "cancelled": set(),
}


def _meta_value(value) -> dict:
    """
    Приводит jsonb из asyncpg (строка) к словарю
    """
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


async def _get_or_create_client(
    connection,
    name: str,
    telephone: str,
) -> int:
    """
    Возвращает client_id по телефону, создавая клиента при необходимости
    """
    client_id = await connection.fetchval(
        "SELECT client_id FROM clients WHERE telephone = $1 ORDER BY client_id LIMIT 1",
        telephone,
    )
    if client_id is not None:
        return client_id

    return await connection.fetchval(
        "INSERT INTO clients (name, telephone) VALUES ($1, $2) RETURNING client_id",
        name,
        telephone,
    )


async def create_order(order: OrderRequest, request_id: str) -> int:
    """
    Сохраняет заказ, клиента и снимок блюд, начальный статус — new

    :return: id созданного заказа
    """
    positions = order.receipt.positions
    if not positions:
        raise ValueError("Заказ должен содержать хотя бы одно блюдо")

    dish_ids = [position.position for position in positions]
    if len(dish_ids) != len(set(dish_ids)):
        raise ValueError("Блюда в заказе не должны повторяться")

    customer = order.customer
    telephone = normalize_phone(customer.telephone)

    async with db.transaction() as connection:
        dish_rows = await connection.fetch(
            "SELECT dish_id, name, cost FROM dishes WHERE dish_id = ANY($1::bigint[])",
            dish_ids,
        )
        dishes_by_id = {row["dish_id"]: row for row in dish_rows}

        missing = [dish_id for dish_id in dish_ids if dish_id not in dishes_by_id]
        if missing:
            raise ValueError(f"Блюда не найдены: {missing}")

        client_id = await _get_or_create_client(connection, customer.name, telephone)

        row = await connection.fetchrow(
            "INSERT INTO orders (client_id) VALUES ($1) RETURNING order_id",
            client_id,
        )
        order_id = row["order_id"]

        await connection.executemany(
            "INSERT INTO order_dishes (order_id, dish_id, cost) VALUES ($1, $2, $3)",
            [
                (order_id, dish_id, dishes_by_id[dish_id]["cost"])
                for dish_id in dish_ids
            ],
        )

        event_meta = {
            "request_id": request_id,
            "customer": {
                "name": customer.name,
                "telephone": telephone,
                "address": customer.address,
                "comment": customer.comment,
            },
            "positions": [
                {
                    "position": position.position,
                    "comment": position.comment,
                }
                for position in positions
            ],
            "date": order.meta.date.isoformat() if order.meta and order.meta.date else None,
        }
        await connection.execute(
            "INSERT INTO order_statuses (order_id, status, meta) VALUES ($1, 'new', $2)",
            order_id,
            json.dumps(event_meta),
        )

    return order_id


async def get_order(order_id: int) -> OrderResponse | None:
    """
    Достает заказ по id с клиентом, блюдами и историей статусов
    """
    row = await db.fetchrow(
        """
        SELECT o.order_id, o.created_at, c.name, c.telephone
        FROM orders o
        JOIN clients c ON c.client_id = o.client_id
        WHERE o.order_id = $1
        """,
        order_id,
    )
    if row is None:
        return None

    dishes = await db.fetch(
        """
        SELECT od.dish_id, d.name, od.cost
        FROM order_dishes od
        JOIN dishes d ON d.dish_id = od.dish_id
        WHERE od.order_id = $1
        ORDER BY d.name
        """,
        order_id,
    )

    status_rows = await db.fetch(
        """
        SELECT status, created_at, meta, courier_id
        FROM order_statuses
        WHERE order_id = $1
        ORDER BY created_at
        """,
        order_id,
    )

    history = [
        StatusEvent(
            status=status_row["status"],
            created_at=status_row["created_at"],
            meta=_meta_value(status_row["meta"]),
            courier_id=status_row["courier_id"],
        )
        for status_row in status_rows
    ]

    new_meta = next(
        (
            _meta_value(status_row["meta"])
            for status_row in status_rows
            if status_row["status"] == "new"
        ),
        {},
    )
    customer_meta = new_meta.get("customer") or {}
    comments = {
        position.get("position"): position.get("comment")
        for position in new_meta.get("positions", [])
        if isinstance(position, dict)
    }

    return OrderResponse(
        order_id=row["order_id"],
        created_at=row["created_at"],
        customer=Customer(
            name=row["name"],
            telephone=row["telephone"],
            address=customer_meta.get("address"),
            comment=customer_meta.get("comment"),
        ),
        positions=[
            OrderDish(
                position=dish["dish_id"],
                name=dish["name"],
                cost=dish["cost"],
                comment=comments.get(dish["dish_id"]),
            )
            for dish in dishes
        ],
        status=history[-1].status if history else "new",
        history=history,
    )


async def _change_status(
    order_id: int,
    new_status: str,
    request_id: str,
    extra_meta: dict | None = None,
    courier_id: int | None = None,
) -> StatusResponse:
    """
    Переводит заказ в новый статус с проверкой допустимого перехода
    """
    async with db.transaction() as connection:
        exists = await connection.fetchval(
            "SELECT order_id FROM orders WHERE order_id = $1 FOR UPDATE",
            order_id,
        )
        if exists is None:
            raise OrderNotFound(order_id)

        if courier_id is not None:
            courier_exists = await connection.fetchval(
                "SELECT 1 FROM couriers WHERE courier_id = $1",
                courier_id,
            )
            if courier_exists is None:
                raise CourierNotFound(courier_id)

        current_status = await connection.fetchval(
            """
            SELECT status
            FROM order_statuses
            WHERE order_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            order_id,
        )
        if current_status is None:
            current_status = "new"

        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"Недопустимый переход: {current_status} -> {new_status}"
            )

        event_meta = {"request_id": request_id}
        if extra_meta:
            event_meta.update(extra_meta)

        changed_at = await connection.fetchval(
            """
            INSERT INTO order_statuses (order_id, status, meta, courier_id)
            VALUES ($1, $2, $3, $4)
            RETURNING created_at
            """,
            order_id,
            new_status,
            json.dumps(event_meta),
            courier_id,
        )

    return StatusResponse(
        order_id=order_id,
        status=new_status,
        changed_at=changed_at,
    )


async def start_order(order_id: int, request_id: str) -> StatusResponse:
    return await _change_status(order_id, "started", request_id)


async def ready_order(order_id: int, request_id: str) -> StatusResponse:
    return await _change_status(order_id, "ready", request_id)


async def cancel_order(order_id: int, request_id: str) -> StatusResponse:
    return await _change_status(order_id, "cancelled", request_id)


async def attach_courier(
    order_id: int,
    deliver_id: int,
    request_id: str,
) -> StatusResponse:
    return await _change_status(
        order_id,
        "assigned",
        request_id,
        courier_id=deliver_id,
    )


async def pickup_order(order_id: int, request_id: str) -> StatusResponse:
    return await _change_status(order_id, "picked_up", request_id)


async def fail_order(order_id: int, request_id: str) -> StatusResponse:
    return await _change_status(order_id, "failed", request_id)


async def finish_order(
    order_id: int,
    meta: OrderMeta | None,
    request_id: str,
) -> StatusResponse:
    extra_meta = {}
    if meta and meta.date:
        extra_meta["date"] = meta.date.isoformat()
    return await _change_status(order_id, "delivered", request_id, extra_meta)
