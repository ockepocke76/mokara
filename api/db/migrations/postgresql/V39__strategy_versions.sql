-- V39: Version DAG for strategy code — git semantics, DB-native.
-- Every code-changing save appends a version node whose parent is the
-- strategy's previous head; the strategy row's head_version_id is the branch
-- ref. A pure-reference clone's head points at the SAME version node as its
-- parent (pointer to a commit), so a later evolve of the clone forks the DAG.
-- Revert is append-only: a new node whose content is the old version's.
CREATE TABLE IF NOT EXISTS STRATEGY_VERSIONS (
    id SERIAL PRIMARY KEY,
    -- The strategy under which this version was committed ("branch"). SET
    -- NULL on delete: shared DAG nodes must outlive any one strategy row.
    strategy_id INTEGER REFERENCES CUSTOM_STRATEGIES(id) ON DELETE SET NULL,
    content_hash VARCHAR(64) NOT NULL,
    code TEXT NOT NULL,
    -- NULL = parameters unknown (reconstructed nodes); restore must never
    -- overwrite the row's params with an unknown.
    parameters_json TEXT,
    class_name VARCHAR(255),
    parent_version_id INTEGER REFERENCES STRATEGY_VERSIONS(id) ON DELETE SET NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'edit'
        CHECK (source IN ('create', 'evolve', 'edit', 'revert', 'backfill')),
    -- The human request that produced this version (evolve message = commit
    -- message); NULL for creates/backfills where none is known.
    request TEXT,
    created_by_user_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy
    ON STRATEGY_VERSIONS(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_versions_parent
    ON STRATEGY_VERSIONS(parent_version_id);
CREATE INDEX IF NOT EXISTS idx_strategy_versions_hash
    ON STRATEGY_VERSIONS(content_hash);

ALTER TABLE CUSTOM_STRATEGIES
    ADD COLUMN IF NOT EXISTS head_version_id INTEGER
        REFERENCES STRATEGY_VERSIONS(id) ON DELETE SET NULL;

-- The startup backfill probes for headless rows on every boot; keep that an
-- index-only near-noop once everything is migrated.
CREATE INDEX IF NOT EXISTS idx_custom_strategies_headless
    ON CUSTOM_STRATEGIES(id) WHERE head_version_id IS NULL;
