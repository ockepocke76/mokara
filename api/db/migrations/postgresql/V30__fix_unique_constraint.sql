-- V30__fix_unique_constraint.sql
-- Fix the index on STRATEGY_EVALUATIONS to be UNIQUE, required for ON CONFLICT clause

-- 1. Drop the old non-unique index if it exists (from V27)
DROP INDEX IF EXISTS idx_eval_commit_sha;

-- 2. Create the UNIQUE index required for UPSERT
CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_commit_sha_unique ON STRATEGY_EVALUATIONS(git_commit_sha);
