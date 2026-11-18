-- rollback 0003: убрать курьера из истории статусов

ALTER TABLE order_statuses
    DROP COLUMN courier_id;
