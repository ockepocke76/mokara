-- V41: One live strategy name per user, enforced by the database.
--
-- save_custom_strategy used to upsert by (user_id, strategy_name) with no
-- deleted_at filter: a same-named create silently overwrote (or resurrected
-- and overwrote) an existing strategy. The code is insert-intent now and
-- suffixes colliding live names; this index is the backstop that turns any
-- remaining race into a clean failed save instead of a corrupted row.
--
-- Existing live duplicates are renamed first — every row except the most
-- recently updated one gets its id appended, which is unique by
-- construction. Soft-deleted rows are outside the index (their names are
-- free to reuse; nothing resurrects them anymore).

WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY user_id, strategy_name
        ORDER BY updated_at DESC NULLS LAST, id DESC) AS rn
    FROM CUSTOM_STRATEGIES
    WHERE deleted_at IS NULL
)
UPDATE CUSTOM_STRATEGIES c
SET strategy_name = c.strategy_name || ' (' || c.id || ')'
FROM ranked r
WHERE c.id = r.id AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_strategies_live_name
ON CUSTOM_STRATEGIES (user_id, strategy_name)
WHERE deleted_at IS NULL;
