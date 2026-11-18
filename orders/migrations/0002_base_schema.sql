-- 0002: базовая схема (6 таблиц)
-- Заменяет прототип из 0001 (orders, order_dishes, order_client_info).
-- ВНИМАНИЕ: миграция destructive — старые таблицы удаляются.

DROP TABLE IF EXISTS order_client_info;
DROP TABLE IF EXISTS order_dishes;
DROP TABLE IF EXISTS orders;

CREATE TABLE dishes (
    dish_id     BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    cost        NUMERIC(12,2) NOT NULL
);

CREATE TABLE couriers (
    courier_id BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    telephone  TEXT NOT NULL
);

CREATE TABLE clients (
    client_id BIGSERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    telephone TEXT NOT NULL
);

CREATE TABLE orders (
    order_id   BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_id  BIGINT NOT NULL REFERENCES clients(client_id) ON DELETE RESTRICT
);

CREATE TABLE order_dishes (
    order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    dish_id  BIGINT NOT NULL REFERENCES dishes(dish_id) ON DELETE RESTRICT,
    cost     NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, dish_id)
);

CREATE TABLE order_statuses (
    order_id   BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta       JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (order_id, created_at)
);

CREATE INDEX orders_client_id_idx ON orders (client_id);
CREATE INDEX order_dishes_dish_id_idx ON order_dishes (dish_id);
