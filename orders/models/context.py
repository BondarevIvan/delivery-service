from pydantic import BaseModel


class Context(BaseModel):
    free_couriers: list[int]
    ongoing_orders: list[int]
    dishes_being_prepared: list[int]