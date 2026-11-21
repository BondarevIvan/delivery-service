"""Прокси-ручки консоли: заказы (orders) и решения (coordinator)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import app, get_upstream
from upstream import Upstream

SEEN = {}


def handler(request: httpx.Request) -> httpx.Response:
    SEEN["auth"] = request.headers.get("authorization")
    SEEN["request_id"] = request.headers.get("requestid")
    path = request.url.path
    if path == "/order/new":
        return httpx.Response(200, json={"id": 42})
    if path == "/order/7":
        return httpx.Response(200, json={"order_id": 7, "history": []})
    if path == "/order/999":
        return httpx.Response(404, json={"detail": "Заказ не найден"})
    if path == "/orders":
        SEEN["statuses"] = request.url.params.get_list("status")
        return httpx.Response(200, json={"orders": []})
    if path == "/couriers":
        return httpx.Response(200, json={"couriers": [{"courier_id": 1}]})
    if path == "/courier/available":
        return httpx.Response(200, json={"courier_id": 1, "available": True})
    if path == "/kitchen/next-order":
        return httpx.Response(200, json={"order_id": 10})
    if path == "/auto/kitchen/dishes":
        return httpx.Response(200, json={"dishes": [{"order_id": 1, "dish_id": 2}]})
    if path == "/coordinator-no-json":
        return httpx.Response(500, text="boom")
    return httpx.Response(404, json={"detail": f"no route {path}"})


@pytest.fixture
def client():
    transport = httpx.MockTransport(handler)
    fake = Upstream("http://orders", "http://coordinator", "secret-token",
                    client=httpx.AsyncClient(transport=transport))
    app.dependency_overrides[get_upstream] = lambda: fake
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_order_is_proxied_with_auth_and_request_id(client):
    resp = client.post("/api/orders/order/new", json={"receipt": {"positions": []}})
    assert resp.status_code == 200
    assert resp.json() == {"id": 42}
    assert SEEN["auth"] == "Bearer secret-token"
    assert SEEN["request_id"]


def test_get_order_is_proxied(client):
    resp = client.get("/api/orders/order/7")
    assert resp.status_code == 200
    assert resp.json()["order_id"] == 7


def test_orders_query_params_are_forwarded(client):
    resp = client.get("/api/orders/orders?status=new&status=started")
    assert resp.status_code == 200
    assert SEEN["statuses"] == ["new", "started"]


def test_couriers_list_is_proxied(client):
    resp = client.get("/api/orders/couriers")
    assert resp.status_code == 200
    assert resp.json() == {"couriers": [{"courier_id": 1}]}


def test_kitchen_dishes_queue_is_proxied(client):
    resp = client.post("/api/coordinator/auto/kitchen/dishes")
    assert resp.status_code == 200
    assert resp.json() == {"dishes": [{"order_id": 1, "dish_id": 2}]}


def test_courier_available_is_proxied(client):
    resp = client.post("/api/orders/courier/available", json={"courier_id": 1, "available": True})
    assert resp.status_code == 200
    assert resp.json() == {"courier_id": 1, "available": True}


def test_upstream_error_status_is_propagated(client):
    resp = client.get("/api/orders/order/999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Заказ не найден"}


def test_coordinator_handle_is_proxied(client):
    payload = {"context": {"free_couriers": [1]}, "priority_algo": {"name": "fifo"}}
    resp = client.post("/api/coordinator/kitchen/next-order", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"order_id": 10}


def test_non_json_upstream_body_is_wrapped(client):
    resp = client.post("/api/coordinator/coordinator-no-json", json={})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "boom"}


def test_invalid_json_body_does_not_crash(client):
    resp = client.post("/api/orders/order/new", content=b"not-json",
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json() == {"id": 42}
