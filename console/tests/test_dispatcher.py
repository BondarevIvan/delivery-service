"""Серверное автоназначение готовых заказов курьерам на точке."""
import asyncio

from dispatcher import dispatch_once


class Resp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class FakeUpstream:
    def __init__(self, mapping, coordinator_status=200):
        self.mapping = mapping
        self.coordinator_status = coordinator_status
        self.attached = []

    async def coordinator(self, method, path, payload=None):
        return Resp(self.coordinator_status, {"order_to_courier": self.mapping})

    async def orders(self, method, path, payload=None, params=None):
        self.attached.append((path, payload))
        return Resp(200, {})


def test_dispatch_once_attaches_ready_orders_to_couriers():
    upstream = FakeUpstream({"9": 1, "10": 2})
    assigned = asyncio.run(dispatch_once(upstream))
    assert assigned == 2
    assert upstream.attached == [
        ("/order/attach", {"order_id": 9, "deliver_id": 1}),
        ("/order/attach", {"order_id": 10, "deliver_id": 2}),
    ]


def test_dispatch_once_no_ready_orders():
    upstream = FakeUpstream({})
    assert asyncio.run(dispatch_once(upstream)) == 0
    assert upstream.attached == []


def test_dispatch_once_skips_on_coordinator_error():
    upstream = FakeUpstream({"9": 1}, coordinator_status=500)
    assert asyncio.run(dispatch_once(upstream)) == 0
    assert upstream.attached == []
