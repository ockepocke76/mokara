-- V27__sha_keyed_evaluations.sql
-- Add Git Commit SHA to STRATEGY_EVALUATIONS to support version-safe results

-- 1. Add the column
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN IF NOT EXISTS git_commit_sha TEXT;

-- 2. Create index for fast lookups by version
CREATE INDEX IF NOT EXISTS idx_eval_commit_sha ON STRATEGY_EVALUATIONS(git_commit_sha);

-- 3. Update existing evaluations to have a SHA if we can determine it
-- For built-in strategies, we can't easily backfill here, but they will be 
-- populated on next run. For custom strategies, we could try to join but 
-- it's safer to let them re-sync.


