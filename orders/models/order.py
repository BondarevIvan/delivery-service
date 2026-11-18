from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


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
