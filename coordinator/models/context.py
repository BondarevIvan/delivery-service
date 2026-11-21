from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


def _to_utc(value: datetime) -> datetime:
    """
    Приводит время к UTC, чтобы корректно сравнивать заказы между собой
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class OrderRef(BaseModel):
    """
    Минимальная информация о заказе, нужная для приоритизации
    """
    order_id: int
    created_at: datetime
    priority: int = 0

    @field_validator("created_at")
    @classmethod
    def _normalize_created_at(cls, value: datetime) -> datetime:
        return _to_utc(value)


class WaitingOrder(OrderRef):
    """
    Заказ из листа ожидания: кухня еще должна приготовить его блюда
    """
    dish_ids: list[int] = Field(
        min_length=1,
        description="блюда заказа в порядке приготовления",
    )


class ReadyOrder(OrderRef):
    """
    Собранный заказ, который ждет курьера
    """
    courier_id: int | None = Field(
        default=None,
        description="курьер, если заказ уже кому-то назначен",
    )


class DishRef(BaseModel):
    """
    Блюдо и заказ, к которому оно относится
    """
    dish_id: int
    order_id: int


class CoordinatorContext(BaseModel):
    """
    Текущее состояние ресторана на момент запроса.

    Содержит ровно те списки, по которым принимаются решения:
    свободные курьеры, лист ожидания, готовые и готовящиеся блюда,
    а также уже собранные заказы.
    """
    free_couriers: list[int] = Field(
        default_factory=list,
        description="id курьеров, свободных прямо сейчас",
    )
    waiting_orders: list[WaitingOrder] = Field(
        default_factory=list,
        description="лист ожидания кухни",
    )
    cooking_dishes: list[DishRef] = Field(
        default_factory=list,
        description="блюда, которые готовятся прямо сейчас",
    )
    ready_dishes: list[DishRef] = Field(
        default_factory=list,
        description="готовые блюда",
    )
    ready_orders: list[ReadyOrder] = Field(
        default_factory=list,
        description="собранные заказы, ожидающие курьера",
    )

    @model_validator(mode="after")
    def _check_state(self) -> "CoordinatorContext":
        ready_dish_ids = [dish.dish_id for dish in self.ready_dishes]
        cooking_dish_ids = [dish.dish_id for dish in self.cooking_dishes]

        if len(ready_dish_ids) != len(set(ready_dish_ids)):
            raise ValueError("Готовые блюда не должны повторяться")
        if len(cooking_dish_ids) != len(set(cooking_dish_ids)):
            raise ValueError("Готовящиеся блюда не должны повторяться")

        intersection = set(ready_dish_ids) & set(cooking_dish_ids)
        if intersection:
            raise ValueError(
                f"Блюда не могут быть одновременно готовыми и готовящимися: {sorted(intersection)}"
            )

        waiting_order_ids = [order.order_id for order in self.waiting_orders]
        if len(waiting_order_ids) != len(set(waiting_order_ids)):
            raise ValueError("Заказы в листе ожидания не должны повторяться")

        ready_order_ids = [order.order_id for order in self.ready_orders]
        if len(ready_order_ids) != len(set(ready_order_ids)):
            raise ValueError("Собранные заказы не должны повторяться")

        return self
