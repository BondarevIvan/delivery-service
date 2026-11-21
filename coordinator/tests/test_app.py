"""Тесты ручек HTTP-координатора (kitchen / assembly / courier / coordinate)."""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

CONTEXT = {
    "free_couriers": [1, 2],
    "waiting_orders": [
        {"order_id": 10, "created_at": "2026-11-19T10:00:00Z", "dish_ids": [100, 101, 103]},
        {"order_id": 11, "created_at": "2026-11-19T10:05:00Z", "dish_ids": [102]},
        {"order_id": 12, "created_at": "2026-11-19T10:02:00Z", "dish_ids": [105]},
        {"order_id": 13, "created_at": "2026-11-19T10:03:00Z", "dish_ids": [106]},
    ],
    "cooking_dishes": [{"dish_id": 100, "order_id": 10}],
    "ready_dishes": [
        {"dish_id": 101, "order_id": 10},
        {"dish_id": 105, "order_id": 12},
        {"dish_id": 106, "order_id": 13},
    ],
    "ready_orders": [
        {"order_id": 9, "created_at": "2026-11-19T09:30:00Z", "courier_id": None}
    ],
}


def body(priority="fifo", distribution="fifo", free_couriers=None, context=CONTEXT):
    payload = {
        "context": context,
        "priority_algo": {"name": priority},
        "distribution_algo": {"name": distribution},
    }
    if free_couriers is not None:
        payload["distribution_algo"]["free_couriers"] = free_couriers
    return payload


def test_kitchen_next_order():
    resp = client.post("/kitchen/next-order", json=body())
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 10}


def test_kitchen_next_dish():
    resp = client.post("/kitchen/next-dish", json=body())
    assert resp.status_code == 200
    assert resp.json() == {"dish_id": 103, "order_id": 10}


def test_assembly_next_order():
    resp = client.post("/assembly/next-order", json=body())
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 12}


def test_courier_next_order():
    resp = client.post("/courier/next-order", json=body())
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 9, "courier_id": 1}


def test_courier_respects_free_couriers_override():
    resp = client.post("/courier/next-order", json=body(free_couriers=[7]))
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 9, "courier_id": 7}


def test_coordinate_full_plan():
    resp = client.post("/coordinate", json=body())
    assert resp.status_code == 200
    assert resp.json() == {
        "order_to_courier": {"9": 1},
        "next_dish_id": 103,
        "next_order_assembly": 12,
        "next_order_cooking": 10,
        "next_order_courier": 9,
    }


def test_unknown_priority_algorithm_returns_400():
    resp = client.post("/kitchen/next-order", json=body(priority="no-such-algo"))
    assert resp.status_code == 400
    assert "no-such-algo" in resp.json()["detail"]


def test_unknown_distribution_algorithm_returns_400():
    resp = client.post("/courier/next-order", json=body(distribution="no-such-algo"))
    assert resp.status_code == 400


def test_empty_context_returns_nulls():
    empty = {"free_couriers": [], "waiting_orders": [], "cooking_dishes": [],
             "ready_dishes": [], "ready_orders": []}
    assert client.post("/kitchen/next-order", json=body(context=empty)).json() == {"order_id": None}
    assert client.post("/assembly/next-order", json=body(context=empty)).json() == {"order_id": None}
    assert client.post("/courier/next-order", json=body(context=empty)).json() == {
        "order_id": None, "courier_id": None}
