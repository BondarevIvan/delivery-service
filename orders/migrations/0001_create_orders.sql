-- create orders

CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_dishes (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    name TEXT NOT NULL
);

CREATE TABLE order_client_info (
    order_id BIGINT PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    comment TEXT NOT NULL,
    telephone TEXT NOT NULL
);
