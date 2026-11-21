# Консоль оператора

Единый сервис, через который можно делать заказы и выполнять все операции
`/orders`, а также дёргать ручки координатора.

Ничего не хранит: проксирует запросы к `orders` (подставляя админ-токен на
сервере, чтобы не держать его в браузере) и к `coordinator`.

## UI

- `GET /` — одностраничная консоль: вкладка «Заказы» (создать, start/ready/
  attach/pickup/finish/fail/cancel, просмотр и история) и вкладка «Координатор»
  (ручки: кухня заказ/блюдо, сборка, курьер, `/coordinate`, «Авто-план из orders»).

### Ролевые страницы

- `GET /kitchen` — кухня: не карточки заказов, а **плоский список блюд** в
  порядке приготовления (`POST /auto/kitchen/dishes`), с кнопкой «готово»
  (`order/dish/ready`). Список сам обновляется.
- `GET /assembly` — сборка: заказы, у которых все блюда готовы, собрать (`ready`).
- `GET /courier` — список курьеров (свободен/занят) и заказов, ожидающих курьера.
- `GET /courier/{id}` — страница конкретного курьера: кнопка **«Я на точке»**
  (`POST /courier/available`), затем забрать (`pickup`), доставить (`finish`) или
  провал (`fail`), «Уйти» снимает доступность. После доставки кнопка «Я на точке»
  появляется снова (назначение заказа снимает доступность автоматически).

Автоназначение выполняет **серверная фоновая задача консоли** (`dispatcher.py`):
раз в `AUTO_DISPATCH_INTERVAL` секунд (по умолчанию 3) она берёт у координатора
`/auto/coordinate` и назначает готовые заказы курьерам **на точке**. Если на
точке никого нет — заказ ждёт, а как только курьер отметится «на точке»,
следующий проход его назначит. Выключается через `AUTO_DISPATCH=0`.

Страницы ходят через тот же серверный прокси (`/api/orders/*`,
`/api/coordinator/*`), токен в браузер не попадает. Общие стили и хелперы —
`/static/role.css`, `/static/role.js`.

## API (прокси)

- `GET|POST /api/orders/{path}` → `orders` (например, `order/new`, `order/1`,
  `order/start`, `order/finish`). Токен и `RequestId` добавляются на сервере.
- `POST /api/coordinator/{path}` → `coordinator` (например,
  `kitchen/next-order`, `kitchen/next-dish`, `assembly/next-order`,
  `courier/next-order`, `coordinate`).

## Переменные окружения

| переменная | назначение |
|---|---|
| `ORDERS_URL` | базовый адрес сервиса orders (например, `http://api:8000`) |
| `COORDINATOR_URL` | базовый адрес координатора (`http://coordinator:7777`) |
| `ORDERS_SERVICE_TOKEN` | токен с ролью `admin` для orders |

## Запуск

```bash
docker compose up -d console
# http://localhost:8888
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_proxy.py` проверяет проброс к orders/coordinator на моке HTTP,
`tests/test_app.py` — отдачу страницы.
