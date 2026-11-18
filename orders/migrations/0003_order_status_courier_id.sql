-- 0003: курьер в истории статусов заказа

ALTER TABLE order_statuses
    ADD COLUMN courier_id BIGINT DEFAULT NULL
        REFERENCES couriers(courier_id) ON DELETE SET NULL;
