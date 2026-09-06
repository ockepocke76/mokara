-- V26__add_git_metadata.sql
-- Add Git version control columns to CUSTOM_STRATEGIES table

-- Git Integration Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS git_branch_name TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS git_commit_sha TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS git_repo_url TEXT 
    DEFAULT 'https://github.com/YOUR_ORG/btc-simulator-strategies';

-- Clone Tracking Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS parent_strategy_id INTEGER
    REFERENCES CUSTOM_STRATEGIES(id) ON DELETE SET NULL;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS clone_source_commit_sha TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS is_clone_unedited BOOLEAN DEFAULT FALSE;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS fork_count INTEGER DEFAULT 0;

-- Versioning Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS version_tag TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_git_branch ON CUSTOM_STRATEGIES(git_branch_name);
CREATE INDEX IF NOT EXISTS idx_parent_strategy ON CUSTOM_STRATEGIES(parent_strategy_id);
CREATE INDEX IF NOT EXISTS idx_clone_source ON CUSTOM_STRATEGIES(clone_source_commit_sha);
CREATE INDEX IF NOT EXISTS idx_is_clone_unedited ON CUSTOM_STRATEGIES(is_clone_unedited);

-- Helper function to build branch name
COMMENT ON COLUMN CUSTOM_STRATEGIES.git_branch_name IS 'Git branch name format: strategies/builtin/{name} or strategies/user-{user_id}/strat-{id}';
COMMENT ON COLUMN CUSTOM_STRATEGIES.clone_source_commit_sha IS 'Git commit SHA this strategy was cloned from (if applicable)';
COMMENT ON COLUMN CUSTOM_STRATEGIES.is_clone_unedited IS 'True if clone has not been edited yet (no Git branch created)';
COMMENT ON COLUMN CUSTOM_STRATEGIES.fork_count IS 'Number of times this strategy has been cloned';
