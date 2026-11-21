"""Сборка CoordinatorContext из карточек заказов orders."""
from datetime import datetime, timezone

from models.context import DishRef
from models.orders import CourierRef, OrderSummary
from utils.context_builder import INSTANCE_BASE, build_state, resolve_dish


def t(hour, minute=0):
    return datetime(2026, 11, 19, hour, minute, tzinfo=timezone.utc)


def make_state():
    orders = [
        OrderSummary(order_id=1, created_at=t(10, 0), status="new", dish_ids=[1, 2]),
        OrderSummary(order_id=2, created_at=t(10, 5), status="started", dish_ids=[1, 3],
                     ready_dish_ids=[1]),
        OrderSummary(order_id=3, created_at=t(9, 30), status="ready", dish_ids=[4]),
        OrderSummary(order_id=4, created_at=t(9, 0), status="assigned", dish_ids=[5],
                     courier_id=7),
        OrderSummary(order_id=5, created_at=t(8, 0), status="delivered", dish_ids=[6]),
    ]
    couriers = [
        CourierRef(courier_id=1, available=True),
        CourierRef(courier_id=2, available=True),
        CourierRef(courier_id=7, available=True),
    ]
    return build_state(orders, couriers)


def test_free_couriers_exclude_busy():
    assert make_state().context.free_couriers == [1, 2]


def test_free_couriers_require_availability():
    orders = [OrderSummary(order_id=1, created_at=t(10, 0), status="new", dish_ids=[1])]
    couriers = [CourierRef(courier_id=1, available=False), CourierRef(courier_id=2, available=True)]
    assert build_state(orders, couriers).context.free_couriers == [2]


def test_waiting_orders():
    context = make_state().context
    assert [o.order_id for o in context.waiting_orders] == [1, 2]


def test_started_order_dishes_split_into_cooking_and_ready():
    context = make_state().context
    assert context.cooking_dishes == [DishRef(dish_id=2 * INSTANCE_BASE + 1, order_id=2)]
    assert context.ready_dishes == [DishRef(dish_id=2 * INSTANCE_BASE, order_id=2)]


def test_ready_orders():
    context = make_state().context
    assert [o.order_id for o in context.ready_orders] == [3, 4]
    assert {o.order_id: o.courier_id for o in context.ready_orders} == {3: None, 4: 7}


def test_new_order_ready_dish_goes_to_ready_dishes():
    orders = [
        OrderSummary(order_id=20, created_at=t(10, 0), status="new", dish_ids=[1, 2],
                     ready_dish_ids=[1]),
    ]
    context = build_state(orders, []).context
    assert context.ready_dishes == [DishRef(dish_id=20 * INSTANCE_BASE, order_id=20)]
    assert context.cooking_dishes == []
    assert [o.order_id for o in context.waiting_orders] == [20]


def test_delivered_order_is_excluded():
    context = make_state().context
    assert 5 not in [o.order_id for o in context.waiting_orders]
    assert 5 not in [o.order_id for o in context.ready_orders]


def test_resolve_dish_maps_instance_to_position():
    state = make_state()
    assert resolve_dish(state, 1, 1 * INSTANCE_BASE) == 1
    assert resolve_dish(state, 1, 1 * INSTANCE_BASE + 1) == 2
    assert resolve_dish(state, 3, 3 * INSTANCE_BASE) == 4
    assert resolve_dish(state, 3, 3 * INSTANCE_BASE + 5) is None
    assert resolve_dish(state, 999, 0) is None
