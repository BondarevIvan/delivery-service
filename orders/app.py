from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models import (
    AttachRequest,
    FinishRequest,
    NewOrderResponse,
    OrderIdRequest,
    OrderRefRequest,
    OrderRequest,
    OrderResponse,
    StatusResponse,
)
from utils import (
    CourierNotFound,
    InvalidTransition,
    OrderNotFound,
    attach_courier,
    cancel_order,
    create_order,
    fail_order,
    finish_order,
    get_order,
    pickup_order,
    ready_order,
    start_order,
    read_payload,
    db,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(lifespan=lifespan)


async def check_admin(
    creds: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=True)),
):
    """
    Проверяет токен и роль admin
    """
    payload = read_payload(creds.credentials)
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return payload


async def get_request_id(request_id: str = Header(..., alias="RequestId")) -> str:
    """
    Обязательный заголовок RequestId
    """
    return request_id


@app.exception_handler(OrderNotFound)
async def order_not_found_handler(_: Request, __: OrderNotFound):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Заказ не найден"},
    )


@app.exception_handler(InvalidTransition)
async def invalid_transition_handler(_: Request, exc: InvalidTransition):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.exception_handler(CourierNotFound)
async def courier_not_found_handler(_: Request, __: CourierNotFound):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Доставщик не найден"},
    )


@app.get("/order/{order_id}", response_model=OrderResponse)
async def read_order(
    order_id: int,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> OrderResponse:
    """
    Возвращает заказ по id вместе с клиентом, позициями и историей статусов
    """
    order = await get_order(order_id)
    if order is None:
        raise OrderNotFound(order_id)
    return order


@app.post("/order/new", response_model=NewOrderResponse)
async def new_order(
    payload: OrderRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> NewOrderResponse:
    """
    Создает новый заказ и возвращает его id
    """
    try:
        order_id = await create_order(payload, request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return NewOrderResponse(id=order_id)


@app.post("/order/cancel", response_model=StatusResponse)
async def cancel(
    payload: OrderIdRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Отменяет заказ
    """
    return await cancel_order(payload.id, request_id)


@app.post("/order/start", response_model=StatusResponse)
async def start(
    payload: OrderIdRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Берет заказ в работу (статус started)
    """
    return await start_order(payload.id, request_id)


@app.post("/order/ready", response_model=StatusResponse)
async def ready(
    payload: OrderIdRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Отмечает заказ готовым (статус ready)
    """
    return await ready_order(payload.id, request_id)


@app.post("/order/attach", response_model=StatusResponse)
async def attach(
    payload: AttachRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Привязывает доставщика к заказу (статус assigned)
    """
    return await attach_courier(payload.order_id, payload.deliver_id, request_id)


@app.post("/order/pickup", response_model=StatusResponse)
async def pickup(
    payload: OrderRefRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Отмечает передачу заказа доставщику (статус picked_up)
    """
    return await pickup_order(payload.order_id, request_id)


@app.post("/order/fail", response_model=StatusResponse)
async def fail(
    payload: OrderRefRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Отмечает неудачную доставку (статус failed)
    """
    return await fail_order(payload.order_id, request_id)


@app.post("/order/finish", response_model=StatusResponse)
async def finish(
    payload: FinishRequest,
    request_id: str = Depends(get_request_id),
    _=Depends(check_admin),
) -> StatusResponse:
    """
    Завершает заказ (статус delivered)
    """
    return await finish_order(payload.order_id, payload.meta, request_id)
