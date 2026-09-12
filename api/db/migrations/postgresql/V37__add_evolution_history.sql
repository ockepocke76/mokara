-- Evolution history natively in Postgres.
-- The old app kept the refine/evolve timeline in the strategies GitHub
-- repo's metadata.json (branch per strategy). Mokara runs without that
-- GitHub dependency, so evolve requests are appended to this column at
-- save time; the git metadata remains a read fallback for rows migrated
-- from the old app.
ALTER TABLE CUSTOM_STRATEGIES
    ADD COLUMN IF NOT EXISTS evolution_history JSONB NOT NULL DEFAULT '[]'::jsonb;
