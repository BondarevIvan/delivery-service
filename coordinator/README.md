# Сервис координатор
Сервис раздает заказы курьерам и задает порядок выполнения заказов.

## Требования
- возможность задавать алгоритм параметром (и еще возможно опциями)
- рассчет нового распределения заказов и курьеров по запросу

## API

Все запросы принимают `POST` с телом `AlgoRequest`: текущий контекст
ресторана и параметры алгоритмов.

```json
{
  "context": {
    "free_couriers": [1, 2],
    "waiting_orders": [
      {"order_id": 10, "created_at": "2026-11-19T10:00:00Z", "dish_ids": [100, 101], "priority": 0}
    ],
    "cooking_dishes": [{"dish_id": 100, "order_id": 10}],
    "ready_dishes": [{"dish_id": 101, "order_id": 10}],
    "ready_orders": [
      {"order_id": 9, "created_at": "2026-11-19T09:30:00Z", "courier_id": null}
    ]
  },
  "priority_algo": {"name": "fifo"},
  "distribution_algo": {"name": "fifo"}
}
```

- `POST /kitchen/next-order` — следующий заказ для кухни.
- `POST /kitchen/next-dish` — следующее блюдо для кухни.
- `POST /assembly/next-order` — следующий заказ для сборки.
- `POST /courier/next-order` — следующий заказ для свободного курьера.
- `POST /coordinate` — общий план: ближайшие задачи и распределение курьеров.

Алгоритмы приоритизации: `fifo`, `lifo`, `fewest_dishes`, `most_dishes`,
`priority`. Алгоритмы распределения: `fifo`, `lifo`, `priority`.
Список свободных курьеров можно переопределить в `distribution_algo.free_couriers`.

## Высокоуровневые ручки

Ручки `/state` и `/auto/*` сами ходят в `orders` (`GET /orders`, `GET /couriers`)
и собирают контекст, поэтому тело с `context` не нужно — алгоритм задаётся
query-параметрами.

- `GET /state` — собранный `CoordinatorContext`.
- `POST /auto/kitchen/next-order?priority=fifo`
- `POST /auto/kitchen/next-dish?priority=fifo`
- `POST /auto/kitchen/dishes?priority=fifo` — упорядоченный список блюд к приготовлению
- `POST /auto/assembly/next-order?priority=fifo`
- `POST /auto/courier/next-order?distribution=fifo` — следующий заказ для первого свободного курьера.
- `POST /auto/courier/{courier_id}/next-order?distribution=fifo` — автоназначение
  следующего готового заказа конкретному свободному курьеру (если он занят — пусто).
- `POST /auto/coordinate?priority=fifo&distribution=fifo`

Нужны переменные окружения `ORDERS_URL` и `ORDERS_SERVICE_TOKEN`.

Соответствие статусов orders: `new` — лист ожидания кухни, `started` — блюда
готовятся (отмеченные готовыми `ready_dish_ids` попадают в `ready_dishes`),
`ready`/`assigned`/`picked_up` — заказ собран и ждёт/получил курьера. Когда все
блюда заказа отмечены готовыми, он становится кандидатом на сборку
(`/auto/assembly/next-order`). Свободные курьеры — все минус занятые на
`assigned`/`picked_up`. Свободные курьеры — те, кто явился на точку (`available`),
минус занятые. Блюдам присваиваются синтетические id
`order_id * 1000 + позиция`; `/auto/kitchen/next-dish` возвращает настоящий id
позиции заказа.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_planner.py` покрывает ручки кухни/сборки/курьеров и алгоритмы,
`tests/test_app.py` — HTTP-эндпоинты.

## Постановка задачи

минимизировать $E(f(\xi))$, где $\xi$ - время ожидания клиентом заказа. 

TODO: Стоит сказать, что про то какое вероятностное пространство я использую. (благо тут оно может быть описано достаточно хорошо)

TODO: подумать о том, чтобы минимизировать 95%-квантиль для f(\xi)

сразу отмечу, что f(x) вполне возможно просто равно x. Идея f в постановке задаче - приблизить негатив клиента, зависимо от времени ожидания.

Также стоит отметить, что мат ожидание не факт, что является лучшим выбором. Вполне интересно пытаться минимизировать и некоторые квантили. (достаточно высокого порядка)
