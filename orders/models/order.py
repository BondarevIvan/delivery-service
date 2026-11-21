from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ReceiptPosition(BaseModel):
    """
    Позиция чека: position — id блюда
    """
    position: int
    comment: str | None = None


class Receipt(BaseModel):
    positions: list[ReceiptPosition]


class Customer(BaseModel):
    name: str
    telephone: str
    address: str | None = None
    comment: str | None = None


class OrderMeta(BaseModel):
    date: datetime | None = None


class OrderRequest(BaseModel):
    receipt: Receipt
    customer: Customer
    meta: OrderMeta | None = None


class OrderDish(BaseModel):
    position: int
    name: str
    cost: Decimal
    comment: str | None = None
    ready: bool = False


class StatusEvent(BaseModel):
    status: str
    created_at: datetime
    meta: dict[str, Any]
    courier_id: int | None = None


class OrderResponse(BaseModel):
    order_id: int
    created_at: datetime
    customer: Customer
    positions: list[OrderDish]
    status: str
    history: list[StatusEvent]


class NewOrderResponse(BaseModel):
    id: int


class OrderIdRequest(BaseModel):
    id: int


class OrderRefRequest(BaseModel):
    order_id: int


class AttachRequest(BaseModel):
    order_id: int
    deliver_id: int


class FinishRequest(BaseModel):
    order_id: int
    meta: OrderMeta | None = None


class StatusResponse(BaseModel):
    order_id: int
    status: str
    changed_at: datetime


class DishReadyRequest(BaseModel):
    """
    Отметка конкретного блюда заказа приготовленным
    """
    order_id: int
    dish_id: int


class DishReadyResponse(BaseModel):
    order_id: int
    dish_id: int
    ready_at: datetime
    all_ready: bool


class OrderSummary(BaseModel):
    """
    Компактная карточка заказа для листинга и сборки контекста координатором
    """
    order_id: int
    created_at: datetime
    status: str = "new"
    courier_id: int | None = None
    dish_ids: list[int] = Field(default_factory=list)
    ready_dish_ids: list[int] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    orders: list[OrderSummary]


class CourierRef(BaseModel):
    courier_id: int
    name: str | None = None
    available: bool = False


class CourierListResponse(BaseModel):
    couriers: list[CourierRef]


class CourierAvailableRequest(BaseModel):
    """
    Явка курьера на точку: available=true — свободен и готов брать заказы
    """
    courier_id: int
    available: bool


class CourierAvailableResponse(BaseModel):
    courier_id: int
    available: bool
