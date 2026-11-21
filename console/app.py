"""Операторская консоль: заказы через /orders и решения координатора.

Сервис ничего не хранит: он проксирует запросы к orders (с админ-токеном) и к
coordinator, а также отдает одностраничную консоль на `/`.
"""
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dispatcher import run_forever
from upstream import Upstream, from_env

STATIC = Path(__file__).parent / "static"
_state: dict = {}


def get_upstream() -> Upstream:
    """Ленивый клиент к вышестоящим сервисам (в тестах подменяется)."""
    if "upstream" not in _state:
        _state["upstream"] = from_env()
    return _state["upstream"]


def _dispatch_interval() -> float:
    """Интервал автоназначения в секундах; 0 или AUTO_DISPATCH=0 — выключено."""
    if os.getenv("AUTO_DISPATCH", "1").lower() in ("0", "false", ""):
        return 0.0
    try:
        return float(os.getenv("AUTO_DISPATCH_INTERVAL", "3"))
    except ValueError:
        return 3.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    interval = _dispatch_interval()
    if interval > 0:
        task = asyncio.create_task(run_forever(get_upstream(), interval))
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    upstream = _state.pop("upstream", None)
    if upstream is not None:
        await upstream.aclose()


app = FastAPI(title="Operator console", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Одностраничная консоль оператора."""
    return FileResponse(STATIC / "console.html")


@app.get("/kitchen", include_in_schema=False)
async def kitchen_page() -> FileResponse:
    """Страница кухни."""
    return FileResponse(STATIC / "kitchen.html")


@app.get("/assembly", include_in_schema=False)
async def assembly_page() -> FileResponse:
    """Страница сборки."""
    return FileResponse(STATIC / "assembly.html")


@app.get("/courier", include_in_schema=False)
async def courier_page() -> FileResponse:
    """Страница курьеров."""
    return FileResponse(STATIC / "courier.html")


@app.get("/courier/{courier_id}", include_in_schema=False)
async def courier_detail_page(courier_id: int) -> FileResponse:
    """Страница конкретного курьера."""
    return FileResponse(STATIC / "courier_detail.html")


def _passthrough(resp: httpx.Response) -> JSONResponse:
    try:
        content = resp.json()
    except ValueError:
        content = {"detail": resp.text}
    return JSONResponse(status_code=resp.status_code, content=content)


async def _json_or_none(request: Request):
    try:
        return await request.json()
    except ValueError:
        return None


@app.get("/api/orders/{path:path}")
async def orders_get(
    path: str,
    request: Request,
    upstream: Upstream = Depends(get_upstream),
) -> JSONResponse:
    """Проксирует GET-запросы к orders (например, orders?status=new, order/1)."""
    params = request.query_params.multi_items()
    return _passthrough(await upstream.orders("GET", f"/{path}", params=params))


@app.post("/api/orders/{path:path}")
async def orders_post(
    path: str,
    request: Request,
    upstream: Upstream = Depends(get_upstream),
) -> JSONResponse:
    """Проксирует POST-запросы к orders (order/new, order/start, order/finish, ...)."""
    params = request.query_params.multi_items()
    return _passthrough(
        await upstream.orders("POST", f"/{path}", await _json_or_none(request), params=params)
    )


@app.post("/api/coordinator/{path:path}")
async def coordinator_post(
    path: str,
    request: Request,
    upstream: Upstream = Depends(get_upstream),
) -> JSONResponse:
    """Проксирует POST-запросы к coordinator (kitchen/next-order, coordinate, ...)."""
    return _passthrough(
        await upstream.coordinator("POST", f"/{path}", await _json_or_none(request))
    )


app.mount("/static", StaticFiles(directory=STATIC), name="static")
