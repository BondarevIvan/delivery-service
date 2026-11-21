"""HTTP-клиент к сервисам orders и coordinator.

Токен админа orders держим на сервере, чтобы операторская консоль не хранила
его в браузере. Каждому запросу к orders добавляем обязательный заголовок
RequestId.
"""
import os
from uuid import uuid4

import httpx


class Upstream:
    def __init__(self, orders_url: str, coordinator_url: str, token: str, client=None):
        self.orders_url = orders_url.rstrip("/")
        self.coordinator_url = coordinator_url.rstrip("/")
        self.token = token
        self.client = client or httpx.AsyncClient(timeout=15.0)

    async def orders(self, method: str, path: str, payload=None, params=None) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "RequestId": uuid4().hex,
        }
        return await self.client.request(
            method, self.orders_url + path, json=payload, headers=headers, params=params
        )

    async def coordinator(self, method: str, path: str, payload=None) -> httpx.Response:
        return await self.client.request(
            method, self.coordinator_url + path, json=payload
        )

    async def aclose(self) -> None:
        await self.client.aclose()


def from_env() -> Upstream:
    return Upstream(
        orders_url=os.getenv("ORDERS_URL", "http://localhost:8000"),
        coordinator_url=os.getenv("COORDINATOR_URL", "http://localhost:7777"),
        token=os.getenv("ORDERS_SERVICE_TOKEN", ""),
    )
