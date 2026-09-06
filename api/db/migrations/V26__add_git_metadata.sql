-- V26__add_git_metadata.sql
-- Add Git version control columns to CUSTOM_STRATEGIES table

-- Git Integration Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN git_branch_name TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN git_commit_sha TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN git_repo_url TEXT 
    DEFAULT 'https://github.com/YOUR_ORG/btc-simulator-strategies';

-- Clone Tracking Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN parent_strategy_id INTEGER
    REFERENCES CUSTOM_STRATEGIES(id) ON DELETE SET NULL;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN clone_source_commit_sha TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN is_clone_unedited BOOLEAN DEFAULT 0;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN fork_count INTEGER DEFAULT 0;

-- Versioning Columns
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN version_tag TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN last_synced_at TIMESTAMP;

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_git_branch ON CUSTOM_STRATEGIES(git_branch_name);
CREATE INDEX IF NOT EXISTS idx_parent_strategy ON CUSTOM_STRATEGIES(parent_strategy_id);
CREATE INDEX IF NOT EXISTS idx_clone_source ON CUSTOM_STRATEGIES(clone_source_commit_sha);
CREATE INDEX IF NOT EXISTS idx_is_clone_unedited ON CUSTOM_STRATEGIES(is_clone_unedited);
