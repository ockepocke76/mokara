-- V40: Retire the legacy evolution-history code snapshots (V37).
--
-- The V39 STRATEGY_VERSIONS DAG is the recovery substrate now: every
-- code-changing save appends a version node, so the previous_code blobs
-- the V37 timeline carried are redundant weight on every row that has a
-- version head. The light entries (timestamp/request/user/sha) stay as a
-- frozen read-only timeline for pre-W5 strategies with no generation runs;
-- the app stops appending to them (except on a pre-V39 schema, where the
-- snapshot is still the only recovery material).
--
-- Rows WITHOUT a head keep their snapshots untouched: they are the input
-- of the startup version backfill, which runs after migrations and
-- reconstructs their chains from exactly these blobs. The column itself
-- stays until every environment has backfilled (a later migration).

UPDATE CUSTOM_STRATEGIES
SET evolution_history = (
    SELECT jsonb_agg(t.entry - 'previous_code' ORDER BY t.ord)
    FROM jsonb_array_elements(evolution_history) WITH ORDINALITY AS t(entry, ord)
)
WHERE head_version_id IS NOT NULL
  AND evolution_history IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(evolution_history) AS x(entry)
    WHERE x.entry ? 'previous_code'
  );
