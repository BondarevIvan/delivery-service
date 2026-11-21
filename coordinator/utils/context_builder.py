"""Сборка CoordinatorContext из заказов и курьеров сервиса orders.

Заказы в orders хранят статус на уровне заказа, а не на уровне блюда. Чтобы
переиспользовать ручки координатора (они работают с идентификаторами блюд),
каждому блюду заказа присваивается синтетический уникальный id
`order_id * INSTANCE_BASE + позиция`. Обратная замена — `resolve_dish`.

Соответствие статусов:
    new                     -> заказ в листе ожидания кухни
    started                 -> блюда готовятся, а отмеченные готовыми (ready_dish_ids)
                               попадают в ready_dishes
    ready/assigned/picked_up-> заказ собран и ждет/получил курьера
Свободные курьеры — те, кто явился на точку (available), минус занятые на
assigned/picked_up.
"""
from dataclasses import dataclass

from models.context import CoordinatorContext, DishRef, ReadyOrder, WaitingOrder
from models.orders import CourierRef, OrderSummary

INSTANCE_BASE = 1000

ACTIVE = {"new", "started", "ready", "assigned", "picked_up"}
WAITING = {"new", "started"}
COOKING = {"started"}
ASSEMBLED = {"ready", "assigned", "picked_up"}
BUSY_COURIER = {"assigned", "picked_up"}


@dataclass
class LoadedState:
    context: CoordinatorContext
    orders: dict[int, OrderSummary]


def _instances(order: OrderSummary) -> list[int]:
    return [order.order_id * INSTANCE_BASE + index for index in range(len(order.dish_ids))]


def build_state(orders: list[OrderSummary], couriers: list[CourierRef]) -> LoadedState:
    waiting: list[WaitingOrder] = []
    cooking: list[DishRef] = []
    ready_dishes: list[DishRef] = []
    ready_orders: list[ReadyOrder] = []
    busy: set[int] = set()
    by_id: dict[int, OrderSummary] = {}

    for order in orders:
        by_id[order.order_id] = order
        if order.status not in ACTIVE:
            continue
        if order.status in WAITING and order.dish_ids:
            waiting.append(
                WaitingOrder(order_id=order.order_id, created_at=order.created_at,
                             dish_ids=_instances(order))
            )
        if order.status in WAITING:
            ready_set = set(order.ready_dish_ids)
            for index, dish_id in enumerate(order.dish_ids):
                ref = DishRef(dish_id=order.order_id * INSTANCE_BASE + index,
                              order_id=order.order_id)
                if dish_id in ready_set:
                    ready_dishes.append(ref)
                elif order.status in COOKING:
                    cooking.append(ref)
        if order.status in ASSEMBLED:
            ready_orders.append(
                ReadyOrder(order_id=order.order_id, created_at=order.created_at,
                           courier_id=order.courier_id)
            )
        if order.status in BUSY_COURIER and order.courier_id is not None:
            busy.add(order.courier_id)

    free = [
        courier.courier_id
        for courier in couriers
        if courier.available and courier.courier_id not in busy
    ]
    context = CoordinatorContext(
        free_couriers=free,
        waiting_orders=waiting,
        cooking_dishes=cooking,
        ready_dishes=ready_dishes,
        ready_orders=ready_orders,
    )
    return LoadedState(context=context, orders=by_id)


async def load_state(client) -> LoadedState:
    """Забирает состояние из orders и собирает контекст."""
    orders = await client.list_orders()
    couriers = await client.list_couriers()
    return build_state(orders, couriers)


def resolve_dish(state: LoadedState, order_id: int, instance_id: int) -> int | None:
    """Синтетический id блюда -> настоящий id блюда (позиция) в заказе."""
    order = state.orders.get(order_id)
    if order is None:
        return None
    index = instance_id - order_id * INSTANCE_BASE
    if 0 <= index < len(order.dish_ids):
        return order.dish_ids[index]
    return None
