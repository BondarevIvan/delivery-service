import json

from utils.database import db
from utils.phone import normalize_phone
from models import (
    CourierAvailableResponse,
    CourierRef,
    Customer,
    DishReadyResponse,
    OrderDish,
    OrderMeta,
    OrderRequest,
    OrderResponse,
    OrderSummary,
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
    "new": {"started", "ready", "cancelled"},
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
        SELECT od.dish_id, d.name, od.cost, od.ready_at
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
                ready=dish["ready_at"] is not None,
            )
            for dish in dishes
        ],
        status=history[-1].status if history else "new",
        history=history,
    )


_LIST_ORDERS_SQL = """
SELECT o.order_id,
       o.created_at,
       COALESCE(ls.status, 'new') AS status,
       ac.courier_id,
       COALESCE(d.dish_ids, ARRAY[]::bigint[]) AS dish_ids,
       COALESCE(d.ready_dish_ids, ARRAY[]::bigint[]) AS ready_dish_ids
FROM orders o
LEFT JOIN LATERAL (
    SELECT status FROM order_statuses s
    WHERE s.order_id = o.order_id
    ORDER BY s.created_at DESC
    LIMIT 1
) ls ON TRUE
LEFT JOIN LATERAL (
    SELECT courier_id FROM order_statuses s
    WHERE s.order_id = o.order_id AND s.courier_id IS NOT NULL
    ORDER BY s.created_at DESC
    LIMIT 1
) ac ON TRUE
LEFT JOIN LATERAL (
    SELECT array_agg(od.dish_id ORDER BY od.dish_id) AS dish_ids,
           array_agg(od.dish_id ORDER BY od.dish_id)
               FILTER (WHERE od.ready_at IS NOT NULL) AS ready_dish_ids
    FROM order_dishes od WHERE od.order_id = o.order_id
) d ON TRUE
WHERE $1::text[] IS NULL OR COALESCE(ls.status, 'new') = ANY($1::text[])
ORDER BY o.created_at, o.order_id
"""


async def fetch_orders(statuses: list[str] | None = None) -> list[OrderSummary]:
    """
    Возвращает карточки заказов (для листинга и сборки контекста)
    """
    rows = await db.fetch(_LIST_ORDERS_SQL, statuses)
    return [
        OrderSummary(
            order_id=row["order_id"],
            created_at=row["created_at"],
            status=row["status"],
            courier_id=row["courier_id"],
            dish_ids=list(row["dish_ids"] or []),
            ready_dish_ids=list(row["ready_dish_ids"] or []),
        )
        for row in rows
    ]


async def fetch_couriers() -> list[CourierRef]:
    """
    Возвращает список курьеров с признаком явки на точку
    """
    rows = await db.fetch(
        "SELECT courier_id, name, available FROM couriers ORDER BY courier_id"
    )
    return [
        CourierRef(courier_id=row["courier_id"], name=row["name"], available=row["available"])
        for row in rows
    ]


async def set_courier_available(courier_id: int, available: bool) -> CourierAvailableResponse:
    """
    Отмечает курьера свободным (явился на точку) или недоступным
    """
    row = await db.fetchrow(
        """
        UPDATE couriers SET available = $2
        WHERE courier_id = $1
        RETURNING courier_id, available
        """,
        courier_id,
        available,
    )
    if row is None:
        raise CourierNotFound(courier_id)
    return CourierAvailableResponse(courier_id=row["courier_id"], available=row["available"])


DISH_READY_STATUSES = {"new", "started"}


async def mark_dish_ready(order_id: int, dish_id: int) -> DishReadyResponse:
    """
    Отмечает блюдо заказа готовым (идемпотентно). Доступно в статусах new/started.
    """
    async with db.transaction() as connection:
        current_status = await connection.fetchval(
            """
            SELECT s.status FROM order_statuses s
            WHERE s.order_id = $1
            ORDER BY s.created_at DESC
            LIMIT 1
            """,
            order_id,
        )
        if current_status is None:
            raise OrderNotFound(order_id)
        if current_status not in DISH_READY_STATUSES:
            raise InvalidTransition(
                f"Нельзя отметить блюдо готовым в статусе: {current_status}"
            )

        belongs = await connection.fetchval(
            "SELECT 1 FROM order_dishes WHERE order_id = $1 AND dish_id = $2",
            order_id,
            dish_id,
        )
        if belongs is None:
            raise ValueError(f"Блюдо {dish_id} не входит в заказ {order_id}")

        ready_at = await connection.fetchval(
            """
            UPDATE order_dishes SET ready_at = COALESCE(ready_at, now())
            WHERE order_id = $1 AND dish_id = $2
            RETURNING ready_at
            """,
            order_id,
            dish_id,
        )
        pending = await connection.fetchval(
            "SELECT count(*) FROM order_dishes WHERE order_id = $1 AND ready_at IS NULL",
            order_id,
        )

    return DishReadyResponse(
        order_id=order_id,
        dish_id=dish_id,
        ready_at=ready_at,
        all_ready=pending == 0,
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
    result = await _change_status(
        order_id,
        "assigned",
        request_id,
        courier_id=deliver_id,
    )
    # курьер забрал заказ и уехал с точки — снимаем доступность
    await db.execute(
        "UPDATE couriers SET available = FALSE WHERE courier_id = $1",
        deliver_id,
    )
    return result


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
