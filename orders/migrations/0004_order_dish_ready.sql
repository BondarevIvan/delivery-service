-- 0004: отметка готовности блюда в заказе

ALTER TABLE order_dishes
    ADD COLUMN ready_at TIMESTAMPTZ DEFAULT NULL;
