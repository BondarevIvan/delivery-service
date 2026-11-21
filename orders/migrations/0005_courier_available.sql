-- 0005: явка курьера на точку (доступность)

ALTER TABLE couriers
    ADD COLUMN available BOOLEAN NOT NULL DEFAULT FALSE;
