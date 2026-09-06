-- V34__fix_strategy_evaluation_constraints.sql
-- Split uniqueness constraints to handle Versioned (SHA) vs Built-in (Name) strategies

-- 1. Drop the old strict constraint on strategy_name
ALTER TABLE STRATEGY_EVALUATIONS DROP CONSTRAINT IF EXISTS strategy_evaluations_strategy_name_key;

-- 2. Create partial unique index for Versioned Strategies (Custom)
-- Enforce uniqueness on git_commit_sha where it exists
CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_sha_unique 
ON STRATEGY_EVALUATIONS(git_commit_sha) 
WHERE git_commit_sha IS NOT NULL;

-- 3. Create partial unique index for Built-in Strategies
-- Enforce uniqueness on strategy_name only where SHA is NULL (built-ins)
CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_name_builtin_unique 
ON STRATEGY_EVALUATIONS(strategy_name) 
WHERE git_commit_sha IS NULL;
