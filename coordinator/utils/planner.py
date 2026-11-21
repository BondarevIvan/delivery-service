from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
from typing import Any, TypeVar

from models.context import CoordinatorContext, OrderRef, ReadyOrder, WaitingOrder

Options = dict[str, Any]
OrderT = TypeVar("OrderT", bound=OrderRef)

_MAX_TIME = datetime.max.replace(tzinfo=timezone.utc)


class UnknownAlgorithmError(ValueError):
    """
    Запрошен неизвестный алгоритм приоритизации или распределения
    """


def _dish_count(order: OrderRef) -> int:
    return len(getattr(order, "dish_ids", ()))


def _fifo_key(order: OrderRef, _: Options) -> tuple[Any, ...]:
    return (order.created_at, order.order_id)


def _lifo_key(order: OrderRef, _: Options) -> tuple[Any, ...]:
    return (_MAX_TIME - order.created_at, order.order_id)


def _fewest_dishes_key(order: OrderRef, _: Options) -> tuple[Any, ...]:
    return (_dish_count(order), order.created_at, order.order_id)


def _most_dishes_key(order: OrderRef, _: Options) -> tuple[Any, ...]:
    return (-_dish_count(order), order.created_at, order.order_id)


def _priority_key(order: OrderRef, _: Options) -> tuple[Any, ...]:
    return (-order.priority, order.created_at, order.order_id)


PRIORITY_ALGORITHMS: dict[str, Callable[[OrderRef, Options], tuple[Any, ...]]] = {
    "fifo": _fifo_key,
    "lifo": _lifo_key,
    "fewest_dishes": _fewest_dishes_key,
    "most_dishes": _most_dishes_key,
    "priority": _priority_key,
}


def _get_priority_key(
    name: str,
    options: Options | None,
) -> Callable[[OrderRef, Options], tuple[Any, ...]]:
    if name not in PRIORITY_ALGORITHMS:
        available = ", ".join(sorted(PRIORITY_ALGORITHMS))
        raise UnknownAlgorithmError(
            f"Неизвестный алгоритм приоритизации: {name}. Доступны: {available}"
        )
    return lambda order, _: PRIORITY_ALGORITHMS[name](order, options or {})


def sort_orders(
    orders: Iterable[OrderT],
    algo_name: str = "fifo",
    options: Options | None = None,
) -> list[OrderT]:
    """
    Сортирует заказы в порядке, в котором их нужно брать в работу
    """
    key = _get_priority_key(algo_name, options)
    return sorted(orders, key=lambda order: key(order, options or {}))


def _ready_dish_ids(context: CoordinatorContext) -> set[int]:
    return {dish.dish_id for dish in context.ready_dishes}


def _cooking_dish_ids(context: CoordinatorContext) -> set[int]:
    return {dish.dish_id for dish in context.cooking_dishes}


def _remaining_dishes(
    order: WaitingOrder,
    ready: set[int],
    cooking: set[int],
) -> list[int]:
    return [dish_id for dish_id in order.dish_ids if dish_id not in ready and dish_id not in cooking]


def next_order_for_kitchen(
    context: CoordinatorContext,
    algo_name: str = "fifo",
    options: Options | None = None,
) -> WaitingOrder | None:
    """
    Находит заказ из листа ожидания, для которого у кухни еще есть работа
    """
    ready = _ready_dish_ids(context)
    cooking = _cooking_dish_ids(context)
    candidates = [
        order
        for order in context.waiting_orders
        if _remaining_dishes(order, ready, cooking)
    ]
    if not candidates:
        return None
    return sort_orders(candidates, algo_name, options)[0]


def next_dish_for_kitchen(
    context: CoordinatorContext,
    algo_name: str = "fifo",
    options: Options | None = None,
) -> tuple[WaitingOrder, int] | None:
    """
    Находит следующее блюдо, которое кухня еще не готовит и которое не готово.

    Блюдо выбирается из самого приоритетного заказа, внутри заказа — в порядке
    позиций чека.
    """
    ready = _ready_dish_ids(context)
    cooking = _cooking_dish_ids(context)

    for order in sort_orders(context.waiting_orders, algo_name, options):
        for dish_id in order.dish_ids:
            if dish_id not in ready and dish_id not in cooking:
                return order, dish_id
    return None


def kitchen_dish_queue(
    context: CoordinatorContext,
    algo_name: str = "fifo",
    options: Options | None = None,
) -> list[tuple[WaitingOrder, int]]:
    """
    Полный список блюд к приготовлению в порядке приоритета.

    Идёт по заказам в порядке алгоритма, у каждого берёт ещё не готовые и не
    готовящиеся блюда в порядке чека. Возвращает пары (заказ, id блюда).
    """
    ready = _ready_dish_ids(context)
    cooking = _cooking_dish_ids(context)
    queue: list[tuple[WaitingOrder, int]] = []
    for order in sort_orders(context.waiting_orders, algo_name, options):
        for dish_id in order.dish_ids:
            if dish_id not in ready and dish_id not in cooking:
                queue.append((order, dish_id))
    return queue


def next_order_for_assembly(
    context: CoordinatorContext,
    algo_name: str = "fifo",
    options: Options | None = None,
) -> WaitingOrder | None:
    """
    Находит заказ, все блюда которого готовы, но который еще не собран
    """
    ready = _ready_dish_ids(context)
    assembled = {order.order_id for order in context.ready_orders}
    candidates = [
        order
        for order in context.waiting_orders
        if order.order_id not in assembled
        and all(dish_id in ready for dish_id in order.dish_ids)
    ]
    if not candidates:
        return None
    return sort_orders(candidates, algo_name, options)[0]


DISTRIBUTION_ALGORITHMS: dict[str, Callable[[Iterable[ReadyOrder], Options], list[ReadyOrder]]] = {
    "fifo": lambda orders, options: sort_orders(orders, "fifo", options),
    "lifo": lambda orders, options: sort_orders(orders, "lifo", options),
    "priority": lambda orders, options: sort_orders(orders, "priority", options),
}


def sort_ready_orders(
    orders: Iterable[ReadyOrder],
    algo_name: str = "fifo",
    options: Options | None = None,
) -> list[ReadyOrder]:
    """
    Сортирует собранные заказы алгоритмом распределения
    """
    if algo_name not in DISTRIBUTION_ALGORITHMS:
        available = ", ".join(sorted(DISTRIBUTION_ALGORITHMS))
        raise UnknownAlgorithmError(
            f"Неизвестный алгоритм распределения: {algo_name}. Доступны: {available}"
        )
    return DISTRIBUTION_ALGORITHMS[algo_name](orders, options or {})


def _unique_couriers(free_couriers: Sequence[int] | None) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for courier_id in free_couriers or ():
        if courier_id not in seen:
            seen.add(courier_id)
            result.append(courier_id)
    return result


def unassigned_ready_orders(context: CoordinatorContext) -> list[ReadyOrder]:
    """
    Собранные заказы, которым еще не назначен курьер
    """
    return [order for order in context.ready_orders if order.courier_id is None]


def next_order_for_courier(
    context: CoordinatorContext,
    distribution_algo: str = "fifo",
    free_couriers: Sequence[int] | None = None,
    options: Options | None = None,
) -> tuple[ReadyOrder, int] | None:
    """
    Находит следующий заказ для свободного курьера.

    Если свободных курьеров нет или нет готовых к выдаче заказов, возвращает None.
    """
    couriers = _unique_couriers(
        context.free_couriers if free_couriers is None else free_couriers
    )
    if not couriers:
        return None

    orders = sort_ready_orders(
        unassigned_ready_orders(context),
        distribution_algo,
        options,
    )
    if not orders:
        return None
    return orders[0], couriers[0]


def distribute_orders(
    context: CoordinatorContext,
    distribution_algo: str = "fifo",
    free_couriers: Sequence[int] | None = None,
    options: Options | None = None,
) -> dict[int, int]:
    """
    Распределяет собранные заказы по свободным курьерам
    """
    couriers = _unique_couriers(
        context.free_couriers if free_couriers is None else free_couriers
    )
    if not couriers:
        return {}

    orders = sort_ready_orders(
        unassigned_ready_orders(context),
        distribution_algo,
        options,
    )
    return {
        order.order_id: courier_id
        for order, courier_id in zip(orders, couriers)
    }
