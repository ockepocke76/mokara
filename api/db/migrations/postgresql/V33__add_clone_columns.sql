-- Add columns for Git-like Reference Cloning

ALTER TABLE CUSTOM_STRATEGIES 
ADD COLUMN IF NOT EXISTS parent_strategy_id INTEGER REFERENCES CUSTOM_STRATEGIES(id),
ADD COLUMN IF NOT EXISTS clone_source_commit_sha TEXT,
ADD COLUMN IF NOT EXISTS cloned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS fork_count INTEGER DEFAULT 0;

-- Index for faster lineage queries
CREATE INDEX IF NOT EXISTS idx_custom_strategies_parent_id ON CUSTOM_STRATEGIES(parent_strategy_id);
