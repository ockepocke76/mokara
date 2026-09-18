-- V40: Retire the legacy evolution-history code snapshots (V37).
--
-- The V39 STRATEGY_VERSIONS DAG is the recovery substrate now: every
-- code-changing save appends a version node, so the previous_code blobs
-- the V37 timeline carried are redundant weight. The light entries
-- (timestamp/request/user/sha) stay as a frozen read-only timeline for
-- pre-W5 strategies with no generation runs; the app stops appending to
-- them (except on a pre-V39 schema, where the snapshot is still the only
-- recovery material).
--
-- A row is stripped ONLY when every one of its snapshots provably exists
-- in its version chain. A head alone is not proof: a save on a pre-V39
-- row self-heals with a SINGLE synthesized parent, and the startup
-- backfill (which runs in the API process, after the worker applied the
-- migrations) never revisits rows that already have a head — stripping
-- those would destroy the older snapshots forever. Uncovered rows keep
-- their blobs untouched; the column itself stays until every environment
-- has backfilled (a later migration).

UPDATE CUSTOM_STRATEGIES c
SET evolution_history = (
    SELECT jsonb_agg(CASE WHEN jsonb_typeof(t.entry) = 'object'
                          THEN t.entry - 'previous_code'
                          ELSE t.entry END
                     ORDER BY t.ord)
    FROM jsonb_array_elements(c.evolution_history) WITH ORDINALITY AS t(entry, ord)
)
WHERE c.head_version_id IS NOT NULL
  AND c.evolution_history IS NOT NULL
  AND jsonb_typeof(c.evolution_history) = 'array'
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(c.evolution_history) AS x(entry)
    WHERE jsonb_typeof(x.entry) = 'object' AND x.entry ? 'previous_code'
  )
  -- every snapshot is covered by a version node of this strategy
  AND NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(c.evolution_history) AS y(entry)
    WHERE jsonb_typeof(y.entry) = 'object'
      AND y.entry ? 'previous_code'
      AND NOT EXISTS (
        SELECT 1 FROM STRATEGY_VERSIONS v
        WHERE v.strategy_id = c.id
          AND btrim(v.code) = btrim(y.entry->>'previous_code')
      )
  );
