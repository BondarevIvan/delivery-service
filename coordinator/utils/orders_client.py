"""HTTP-клиент координатора к сервису orders."""
import os
from uuid import uuid4

import httpx

from models.orders import CourierRef, OrderSummary

ACTIVE_STATUSES = ["new", "started", "ready", "assigned", "picked_up"]


class OrdersClient:
    def __init__(self, base_url: str, token: str, client=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.AsyncClient(timeout=10.0)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "RequestId": uuid4().hex,
        }

    async def list_orders(self, statuses: list[str] | None = None) -> list[OrderSummary]:
        params = [("status", s) for s in (ACTIVE_STATUSES if statuses is None else statuses)]
        resp = await self.client.get(
            f"{self.base_url}/orders", params=params, headers=self._headers()
        )
        resp.raise_for_status()
        return [OrderSummary.model_validate(row) for row in resp.json().get("orders", [])]

    async def list_couriers(self) -> list[CourierRef]:
        resp = await self.client.get(f"{self.base_url}/couriers", headers=self._headers())
        resp.raise_for_status()
        return [CourierRef.model_validate(row) for row in resp.json().get("couriers", [])]

    async def aclose(self) -> None:
        await self.client.aclose()


def from_env() -> OrdersClient:
    return OrdersClient(
        base_url=os.getenv("ORDERS_URL", "http://localhost:8000"),
        token=os.getenv("ORDERS_SERVICE_TOKEN", ""),
    )
