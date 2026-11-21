"""Высокоуровневые ручки /auto/*: координатор сам собирает контекст из orders."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import app, get_client
from models.orders import CourierRef, OrderSummary


def t(hour, minute=0):
    return datetime(2026, 11, 19, hour, minute, tzinfo=timezone.utc)


ORDERS = [
    OrderSummary(order_id=1, created_at=t(10, 0), status="new", dish_ids=[1, 2]),
    OrderSummary(order_id=2, created_at=t(10, 5), status="started", dish_ids=[1, 3]),
    OrderSummary(order_id=3, created_at=t(9, 30), status="ready", dish_ids=[4]),
    OrderSummary(order_id=4, created_at=t(9, 0), status="assigned", dish_ids=[5],
                 courier_id=7),
]
COURIERS = [
    CourierRef(courier_id=1, available=True),
    CourierRef(courier_id=2, available=True),
    CourierRef(courier_id=7, available=True),
]


class FakeOrdersClient:
    def __init__(self, orders, couriers):
        self._orders, self._couriers = orders, couriers

    async def list_orders(self, statuses=None):
        return self._orders

    async def list_couriers(self):
        return self._couriers


@pytest.fixture
def client():
    fake = FakeOrdersClient(ORDERS, COURIERS)
    app.dependency_overrides[get_client] = lambda: fake
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_state_is_assembled(client):
    data = client.get("/state").json()
    assert data["free_couriers"] == [1, 2]
    assert [o["order_id"] for o in data["waiting_orders"]] == [1, 2]
    assert [o["order_id"] for o in data["ready_orders"]] == [3, 4]
    assert len(data["cooking_dishes"]) == 2


def test_auto_kitchen_next_order(client):
    resp = client.post("/auto/kitchen/next-order")
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 1}


def test_auto_kitchen_next_dish_returns_real_dish(client):
    resp = client.post("/auto/kitchen/next-dish")
    assert resp.status_code == 200
    assert resp.json() == {"dish_id": 1, "order_id": 1}


def test_auto_kitchen_dishes_queue(client):
    resp = client.post("/auto/kitchen/dishes")
    assert resp.status_code == 200
    assert resp.json() == {
        "dishes": [
            {"order_id": 1, "dish_id": 1},
            {"order_id": 1, "dish_id": 2},
        ]
    }


def test_auto_assembly_is_empty_without_ready_dishes(client):
    resp = client.post("/auto/assembly/next-order")
    assert resp.status_code == 200
    assert resp.json() == {"order_id": None}


def test_auto_courier_assignment(client):
    resp = client.post("/auto/courier/next-order")
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 3, "courier_id": 1}


def test_auto_coordinate_full_plan(client):
    resp = client.post("/auto/coordinate")
    assert resp.status_code == 200
    assert resp.json() == {
        "order_to_courier": {"3": 1},
        "next_dish_id": 1,
        "next_order_assembly": None,
        "next_order_cooking": 1,
        "next_order_courier": 3,
    }


def test_auto_courier_assign_for_specific_free_courier(client):
    resp = client.post("/auto/courier/1/next-order")
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 3, "courier_id": 1}


def test_auto_courier_assign_busy_courier_returns_empty(client):
    resp = client.post("/auto/courier/7/next-order")
    assert resp.json() == {"order_id": None, "courier_id": None}


def test_auto_courier_assign_unknown_courier_returns_empty(client):
    resp = client.post("/auto/courier/99/next-order")
    assert resp.json() == {"order_id": None, "courier_id": None}


def test_auto_unknown_algorithm_returns_400(client):
    resp = client.post("/auto/kitchen/next-order", params={"priority": "no-such-algo"})
    assert resp.status_code == 400


def test_auto_assembly_picks_fully_ready_order():
    orders = [
        OrderSummary(order_id=10, created_at=t(10, 0), status="started", dish_ids=[1, 2],
                     ready_dish_ids=[1, 2]),
        OrderSummary(order_id=11, created_at=t(10, 5), status="started", dish_ids=[3],
                     ready_dish_ids=[]),
    ]
    app.dependency_overrides[get_client] = lambda: FakeOrdersClient(orders, [])
    try:
        with TestClient(app) as test_client:
            assert test_client.post("/auto/assembly/next-order").json() == {"order_id": 10}
            ready = test_client.get("/state").json()["ready_dishes"]
            assert ready == [
                {"dish_id": 10 * 1000, "order_id": 10},
                {"dish_id": 10 * 1000 + 1, "order_id": 10},
            ]
    finally:
        app.dependency_overrides.clear()
