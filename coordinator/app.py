from contextlib import asynccontextmanager

import dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from models import (
    AlgoRequest,
    CoordinatorContext,
    CourierAssignmentResponse,
    DistributionOrders,
    KitchenDish,
    KitchenQueueResponse,
    NextDishResponse,
    NextOrderResponse,
)
from utils import (
    OrdersClient,
    UnknownAlgorithmError,
    distribute_orders,
    from_env,
    kitchen_dish_queue,
    load_state,
    next_dish_for_kitchen,
    next_order_for_assembly,
    next_order_for_courier,
    next_order_for_kitchen,
    resolve_dish,
)


dotenv.load_dotenv()

_client: OrdersClient | None = None


def get_client() -> OrdersClient:
    """Ленивый клиент к orders (в тестах подменяется)."""
    global _client
    if _client is None:
        _client = from_env()
    return _client


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


app = FastAPI(
    title="Coordinator",
    description="Сервис, который выбирает следующие задачи для кухни, сборки и курьеров",
    lifespan=lifespan,
)


@app.exception_handler(UnknownAlgorithmError)
async def unknown_algorithm_handler(
    _: Request,
    exc: UnknownAlgorithmError,
) -> JSONResponse:
    """
    Возвращает 400, если в запросе указан неизвестный алгоритм
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _free_couriers(request: AlgoRequest) -> list[int]:
    """
    Список свободных курьеров: значение из алгоритма важнее контекста
    """
    override = request.distribution_algo.free_couriers
    if override is not None:
        return override
    return request.context.free_couriers


@app.post("/kitchen/next-order", response_model=NextOrderResponse)
async def kitchen_next_order(request: AlgoRequest) -> NextOrderResponse:
    """
    Находит следующий заказ для исполнения кухней
    """
    order = next_order_for_kitchen(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    return NextOrderResponse(order_id=order.order_id if order else None)


@app.post("/kitchen/next-dish", response_model=NextDishResponse)
async def kitchen_next_dish(request: AlgoRequest) -> NextDishResponse:
    """
    Находит следующее блюдо для кухни с учетом готовых и готовящихся блюд
    """
    selection = next_dish_for_kitchen(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    if selection is None:
        return NextDishResponse()
    order, dish_id = selection
    return NextDishResponse(dish_id=dish_id, order_id=order.order_id)


@app.post("/assembly/next-order", response_model=NextOrderResponse)
async def assembly_next_order(request: AlgoRequest) -> NextOrderResponse:
    """
    Находит следующий заказ для сборки: все блюда готовы, заказ еще не собран
    """
    order = next_order_for_assembly(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    return NextOrderResponse(order_id=order.order_id if order else None)


@app.post("/courier/next-order", response_model=CourierAssignmentResponse)
async def courier_next_order(request: AlgoRequest) -> CourierAssignmentResponse:
    """
    Находит следующий заказ для свободного курьера
    """
    assignment = next_order_for_courier(
        request.context,
        request.distribution_algo.name,
        _free_couriers(request),
        request.distribution_algo.options,
    )
    if assignment is None:
        return CourierAssignmentResponse()
    order, courier_id = assignment
    return CourierAssignmentResponse(
        order_id=order.order_id,
        courier_id=courier_id,
    )


@app.post("/coordinate", response_model=DistributionOrders)
async def coordinate(request: AlgoRequest) -> DistributionOrders:
    """
    Рассчитывает текущий план: ближайшие задачи и распределение курьеров
    """
    kitchen_order = next_order_for_kitchen(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    dish_selection = next_dish_for_kitchen(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    assembly_order = next_order_for_assembly(
        request.context,
        request.priority_algo.name,
        request.priority_algo.options,
    )
    order_to_courier = distribute_orders(
        request.context,
        request.distribution_algo.name,
        _free_couriers(request),
        request.distribution_algo.options,
    )

    return DistributionOrders(
        order_to_courier=order_to_courier,
        next_dish_id=dish_selection[1] if dish_selection else None,
        next_order_assembly=assembly_order.order_id if assembly_order else None,
        next_order_cooking=kitchen_order.order_id if kitchen_order else None,
        next_order_courier=next(iter(order_to_courier), None),
    )


# --- высокоуровневые ручки: сами ходят в orders и собирают контекст ----------


@app.get("/state", response_model=CoordinatorContext)
async def state(client: OrdersClient = Depends(get_client)) -> CoordinatorContext:
    """
    Собирает текущий контекст ресторана из сервиса orders
    """
    return (await load_state(client)).context


@app.post("/auto/kitchen/next-order", response_model=NextOrderResponse)
async def auto_kitchen_next_order(
    priority: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> NextOrderResponse:
    """
    Следующий заказ для кухни по данным из orders
    """
    loaded = await load_state(client)
    order = next_order_for_kitchen(loaded.context, priority)
    return NextOrderResponse(order_id=order.order_id if order else None)


@app.post("/auto/kitchen/next-dish", response_model=NextDishResponse)
async def auto_kitchen_next_dish(
    priority: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> NextDishResponse:
    """
    Следующее блюдо для кухни по данным из orders
    """
    loaded = await load_state(client)
    selection = next_dish_for_kitchen(loaded.context, priority)
    if selection is None:
        return NextDishResponse()
    order, dish_instance = selection
    return NextDishResponse(
        dish_id=resolve_dish(loaded, order.order_id, dish_instance),
        order_id=order.order_id,
    )


@app.post("/auto/kitchen/dishes", response_model=KitchenQueueResponse)
async def auto_kitchen_dishes(
    priority: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> KitchenQueueResponse:
    """
    Упорядоченный список блюд к приготовлению по данным из orders
    """
    loaded = await load_state(client)
    queue = kitchen_dish_queue(loaded.context, priority)
    return KitchenQueueResponse(
        dishes=[
            KitchenDish(order_id=order.order_id,
                        dish_id=resolve_dish(loaded, order.order_id, instance))
            for order, instance in queue
        ]
    )


@app.post("/auto/assembly/next-order", response_model=NextOrderResponse)
async def auto_assembly_next_order(
    priority: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> NextOrderResponse:
    """
    Следующий заказ для сборки по данным из orders
    """
    loaded = await load_state(client)
    order = next_order_for_assembly(loaded.context, priority)
    return NextOrderResponse(order_id=order.order_id if order else None)


@app.post("/auto/courier/next-order", response_model=CourierAssignmentResponse)
async def auto_courier_next_order(
    distribution: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> CourierAssignmentResponse:
    """
    Следующий заказ для свободного курьера по данным из orders
    """
    loaded = await load_state(client)
    assignment = next_order_for_courier(loaded.context, distribution)
    if assignment is None:
        return CourierAssignmentResponse()
    order, courier_id = assignment
    return CourierAssignmentResponse(order_id=order.order_id, courier_id=courier_id)


@app.post("/auto/courier/{courier_id}/next-order", response_model=CourierAssignmentResponse)
async def auto_courier_assign(
    courier_id: int,
    distribution: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> CourierAssignmentResponse:
    """
    Автоназначение следующего готового заказа конкретному свободному курьеру
    """
    loaded = await load_state(client)
    if courier_id not in loaded.context.free_couriers:
        return CourierAssignmentResponse()
    assignment = next_order_for_courier(
        loaded.context, distribution, free_couriers=[courier_id]
    )
    if assignment is None:
        return CourierAssignmentResponse()
    order, assigned = assignment
    return CourierAssignmentResponse(order_id=order.order_id, courier_id=assigned)


@app.post("/auto/coordinate", response_model=DistributionOrders)
async def auto_coordinate(
    priority: str = "fifo",
    distribution: str = "fifo",
    client: OrdersClient = Depends(get_client),
) -> DistributionOrders:
    """
    Общий план по данным из orders: ближайшие задачи и распределение курьеров
    """
    loaded = await load_state(client)
    context = loaded.context
    kitchen_order = next_order_for_kitchen(context, priority)
    dish_selection = next_dish_for_kitchen(context, priority)
    assembly_order = next_order_for_assembly(context, priority)
    order_to_courier = distribute_orders(context, distribution)

    return DistributionOrders(
        order_to_courier=order_to_courier,
        next_dish_id=(
            resolve_dish(loaded, dish_selection[0].order_id, dish_selection[1])
            if dish_selection
            else None
        ),
        next_order_assembly=assembly_order.order_id if assembly_order else None,
        next_order_cooking=kitchen_order.order_id if kitchen_order else None,
        next_order_courier=next(iter(order_to_courier), None),
    )
