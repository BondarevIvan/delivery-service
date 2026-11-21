"""Тесты ручек планировщика: кухня, сборка, курьеры — с FIFO по умолчанию."""
from datetime import datetime, timezone

import pytest

from models.context import CoordinatorContext, DishRef, ReadyOrder, WaitingOrder
from utils.planner import (UnknownAlgorithmError, distribute_orders, kitchen_dish_queue,
                           next_dish_for_kitchen, next_order_for_assembly, next_order_for_courier,
                           next_order_for_kitchen, sort_orders, sort_ready_orders,
                           unassigned_ready_orders)


def t(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 19, hour, minute, tzinfo=timezone.utc)


def sample_context() -> CoordinatorContext:
    """Заказы 10-13 в работе, заказ 9 собран и ждёт курьера."""
    return CoordinatorContext(
        free_couriers=[1, 2],
        waiting_orders=[
            WaitingOrder(order_id=10, created_at=t(10, 0), dish_ids=[100, 101, 103]),
            WaitingOrder(order_id=11, created_at=t(10, 5), dish_ids=[102]),
            WaitingOrder(order_id=12, created_at=t(10, 2), dish_ids=[105]),
            WaitingOrder(order_id=13, created_at=t(10, 3), dish_ids=[106]),
        ],
        cooking_dishes=[DishRef(dish_id=100, order_id=10)],
        ready_dishes=[DishRef(dish_id=101, order_id=10),
                      DishRef(dish_id=105, order_id=12),
                      DishRef(dish_id=106, order_id=13)],
        ready_orders=[ReadyOrder(order_id=9, created_at=t(9, 30), courier_id=None)],
    )


class TestKitchen:
    def test_next_order_fifo(self):
        assert next_order_for_kitchen(sample_context()).order_id == 10

    def test_next_dish_skips_ready_and_cooking(self):
        selection = next_dish_for_kitchen(sample_context())
        assert selection is not None
        order, dish_id = selection
        assert (order.order_id, dish_id) == (10, 103)

    def test_fully_cooked_order_is_not_a_kitchen_task(self):
        context = CoordinatorContext(
            waiting_orders=[WaitingOrder(order_id=12, created_at=t(10, 2), dish_ids=[105])],
            ready_dishes=[DishRef(dish_id=105, order_id=12)],
        )
        assert next_order_for_kitchen(context) is None
        assert next_dish_for_kitchen(context) is None


class TestKitchenQueue:
    def test_queue_is_ordered_by_priority_and_skips_ready_cooking(self):
        queue = kitchen_dish_queue(sample_context())
        assert [(order.order_id, dish) for order, dish in queue] == [(10, 103), (11, 102)]

    def test_empty_queue_when_nothing_left(self):
        context = CoordinatorContext(
            waiting_orders=[WaitingOrder(order_id=12, created_at=t(10, 2), dish_ids=[105])],
            ready_dishes=[DishRef(dish_id=105, order_id=12)],
        )
        assert kitchen_dish_queue(context) == []


class TestAssembly:
    def test_next_order_fifo_among_ready_to_assemble(self):
        assert next_order_for_assembly(sample_context()).order_id == 12

    def test_none_when_nothing_ready(self):
        context = CoordinatorContext(
            waiting_orders=[WaitingOrder(order_id=20, created_at=t(10, 0), dish_ids=[200, 201])],
            cooking_dishes=[DishRef(dish_id=200, order_id=20)],
        )
        assert next_order_for_assembly(context) is None


class TestCourier:
    def test_next_order_fifo_and_first_free_courier(self):
        assignment = next_order_for_courier(sample_context())
        assert assignment is not None
        order, courier_id = assignment
        assert (order.order_id, courier_id) == (9, 1)

    def test_none_without_free_couriers(self):
        context = sample_context().model_copy(update={"free_couriers": []})
        assert next_order_for_courier(context) is None

    def test_skips_already_assigned_orders(self):
        context = sample_context().model_copy(update={
            "ready_orders": [ReadyOrder(order_id=9, created_at=t(9, 30), courier_id=5)]
        })
        assert next_order_for_courier(context) is None
        assert unassigned_ready_orders(context) == []

    def test_distribute_maps_orders_to_couriers(self):
        assert distribute_orders(sample_context()) == {9: 1}

    def test_distribute_respects_free_couriers_override(self):
        assert distribute_orders(sample_context(), free_couriers=[7, 8]) == {9: 7}


class TestAlgorithms:
    def test_fifo_tie_break_by_order_id(self):
        first = WaitingOrder(order_id=1, created_at=t(10, 0), dish_ids=[1])
        second = WaitingOrder(order_id=2, created_at=t(10, 0), dish_ids=[2])
        assert [o.order_id for o in sort_orders([second, first])] == [1, 2]

    def test_lifo(self):
        orders = [WaitingOrder(order_id=1, created_at=t(10, 0), dish_ids=[1]),
                  WaitingOrder(order_id=2, created_at=t(10, 5), dish_ids=[2])]
        assert [o.order_id for o in sort_orders(orders, "lifo")] == [2, 1]

    def test_fewest_and_most_dishes(self):
        orders = [WaitingOrder(order_id=1, created_at=t(10, 0), dish_ids=[1, 2]),
                  WaitingOrder(order_id=2, created_at=t(10, 5), dish_ids=[3])]
        assert [o.order_id for o in sort_orders(orders, "fewest_dishes")] == [2, 1]
        assert [o.order_id for o in sort_orders(orders, "most_dishes")] == [1, 2]

    def test_priority(self):
        orders = [WaitingOrder(order_id=1, created_at=t(10, 0), dish_ids=[1], priority=0),
                  WaitingOrder(order_id=2, created_at=t(10, 5), dish_ids=[2], priority=9)]
        assert [o.order_id for o in sort_orders(orders, "priority")] == [2, 1]

    def test_ready_orders_distribution_sorting(self):
        a = ReadyOrder(order_id=1, created_at=t(10, 0), priority=1)
        b = ReadyOrder(order_id=2, created_at=t(10, 5), priority=5)
        assert [o.order_id for o in sort_ready_orders([a, b], "fifo")] == [1, 2]
        assert [o.order_id for o in sort_ready_orders([a, b], "priority")] == [2, 1]

    def test_unknown_algorithms_raise(self):
        with pytest.raises(UnknownAlgorithmError):
            sort_orders([], "no-such-algo")
        with pytest.raises(UnknownAlgorithmError):
            sort_ready_orders([], "no-such-algo")
