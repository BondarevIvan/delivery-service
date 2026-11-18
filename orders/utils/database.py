import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


class Database:
    """
    Пул подключений к PostgreSQL и базовые операции над ним
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """
        Создает пул подключений, если он еще не создан
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=_database_url(),
                min_size=1,
                max_size=10,
            )

    async def disconnect(self) -> None:
        """
        Закрывает пул подключений
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database is not connected")
        return self._pool

    async def execute(self, query: str, *args: Any) -> str:
        """
        Выполняет запрос без возврата строк (INSERT/UPDATE/DELETE)
        """
        return await self.pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """
        Выполняет запрос и возвращает все строки
        """
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """
        Выполняет запрос и возвращает первую строку
        """
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """
        Выполняет запрос и возвращает первое значение первой строки
        """
        return await self.pool.fetchval(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Открывает транзакцию: все запросы внутри выполняются атомарно
        """
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                yield connection


db = Database()
