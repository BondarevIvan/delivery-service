from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from models.context import _to_utc


class OrderSummary(BaseModel):
    """
    Карточка заказа, как ее отдает сервис orders
    """
    order_id: int
    created_at: datetime
    status: str = "new"
    courier_id: int | None = None
    dish_ids: list[int] = Field(default_factory=list)
    ready_dish_ids: list[int] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def _normalize_created_at(cls, value: datetime) -> datetime:
        return _to_utc(value)


class CourierRef(BaseModel):
    courier_id: int
    name: str | None = None
    available: bool = False
