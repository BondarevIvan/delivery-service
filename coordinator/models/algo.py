from typing import Any

from pydantic import BaseModel, Field

from models.context import CoordinatorContext


class AlgoPriorityOrder(BaseModel):
    """
    Параметры алгоритма приоритизации заказов
    """
    name: str = Field(
        default="fifo",
        description="fifo, lifo, fewest_dishes, most_dishes, priority",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="дополнительные опции конкретного алгоритма",
    )


class AlgoDistribution(BaseModel):
    """
    Параметры алгоритма распределения заказов между курьерами
    """
    name: str = Field(
        default="fifo",
        description="fifo, lifo, priority",
    )
    free_couriers: list[int] | None = Field(
        default=None,
        description=(
            "необязательное переопределение списка свободных курьеров. "
            "Если не задано, берется context.free_couriers"
        ),
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="дополнительные опции конкретного алгоритма",
    )


class AlgoRequest(BaseModel):
    """
    Запрос к сервису: текущее состояние ресторана и параметры алгоритмов
    """
    context: CoordinatorContext
    priority_algo: AlgoPriorityOrder = Field(default_factory=AlgoPriorityOrder)
    distribution_algo: AlgoDistribution = Field(default_factory=AlgoDistribution)


class DistributionOrders(BaseModel):
    """
    Результат распределения заказов по курьерам и ближайшие задачи
    """
    order_to_courier: dict[int, int] = Field(
        default_factory=dict,
        description="маппинг заказа в курьера",
    )
    next_dish_id: int | None = Field(
        default=None,
        description="следующее блюдо для кухни",
    )
    next_order_assembly: int | None = Field(
        default=None,
        description="следующий заказ для сборки",
    )
    next_order_cooking: int | None = Field(
        default=None,
        description="следующий заказ для кухни",
    )
    next_order_courier: int | None = Field(
        default=None,
        description="следующий заказ для курьера",
    )


class NextOrderResponse(BaseModel):
    """
    Следующий заказ, найденный координатором
    """
    order_id: int | None = None


class NextDishResponse(BaseModel):
    """
    Следующее блюдо и заказ, в рамках которого его нужно приготовить
    """
    dish_id: int | None = None
    order_id: int | None = None


class CourierAssignmentResponse(BaseModel):
    """
    Следующий заказ для свободного курьера
    """
    order_id: int | None = None
    courier_id: int | None = None


class KitchenDish(BaseModel):
    """
    Блюдо в очереди кухни с указанием заказа
    """
    order_id: int
    dish_id: int


class KitchenQueueResponse(BaseModel):
    """
    Упорядоченный список блюд к приготовлению
    """
    dishes: list[KitchenDish] = Field(default_factory=list)
