-- V41: One live strategy name per user, enforced by the database.
--
-- save_custom_strategy used to upsert by (user_id, strategy_name) with no
-- deleted_at filter: a same-named create silently overwrote (or resurrected
-- and overwrote) an existing strategy. The code is insert-intent now and
-- suffixes colliding live names; this index is the backstop that turns any
-- remaining race into a clean failed save instead of a corrupted row.
--
-- Existing live duplicates first. Built-in rows (user 0) must NOT be
-- renamed — builtin_sync, the builtin list, and the leaderboard lineage
-- join all key on their exact names — so a duplicated builtin (possible on
-- databases that predate the sync's advisory lock) keeps the most recently
-- synced row and soft-deletes the stale copies. User rows get their id
-- appended (length-capped); renaming can itself collide with a hand-typed
-- "name (id)" row, so it loops until no live duplicates remain (bounded —
-- if data is somehow still duplicated after 10 passes, the index build
-- below fails loudly rather than guessing).

UPDATE CUSTOM_STRATEGIES c
SET deleted_at = CURRENT_TIMESTAMP
FROM (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY strategy_name
        ORDER BY last_synced_at DESC NULLS LAST,
                 updated_at DESC NULLS LAST, id DESC) AS rn
    FROM CUSTOM_STRATEGIES
    WHERE deleted_at IS NULL AND user_id = 0
) d
WHERE c.id = d.id AND d.rn > 1;

DO $$
DECLARE
    renamed integer;
    pass integer := 0;
BEGIN
    LOOP
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY user_id, strategy_name
                ORDER BY updated_at DESC NULLS LAST, id DESC) AS rn
            FROM CUSTOM_STRATEGIES
            WHERE deleted_at IS NULL AND user_id <> 0
        )
        UPDATE CUSTOM_STRATEGIES c
        SET strategy_name =
            left(c.strategy_name, 255 - length(' (' || c.id || ')'))
            || ' (' || c.id || ')'
        FROM ranked r
        WHERE c.id = r.id AND r.rn > 1;
        GET DIAGNOSTICS renamed = ROW_COUNT;
        pass := pass + 1;
        EXIT WHEN renamed = 0 OR pass >= 10;
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_strategies_live_name
ON CUSTOM_STRATEGIES (user_id, strategy_name)
WHERE deleted_at IS NULL;
