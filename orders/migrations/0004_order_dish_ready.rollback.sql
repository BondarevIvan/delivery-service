-- 0004 rollback: убрать отметку готовности блюда

ALTER TABLE order_dishes
    DROP COLUMN ready_at;
