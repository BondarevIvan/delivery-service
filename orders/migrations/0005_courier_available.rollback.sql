-- 0005 rollback: убрать доступность курьера

ALTER TABLE couriers
    DROP COLUMN available;
