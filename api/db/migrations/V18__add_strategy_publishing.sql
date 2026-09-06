-- Add is_published_to_leaderboard column to CUSTOM_STRATEGIES (SQLite)
-- This allows users to explicitly opt-in to showing their strategy on the public leaderboard

-- Add column if it doesn't exist (SQLite doesn't have IF NOT EXISTS for ALTER COLUMN)
-- Run this migration manually or use application logic to check
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN is_published_to_leaderboard INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_custom_strategies_published 
ON CUSTOM_STRATEGIES(is_published_to_leaderboard) 
WHERE is_published_to_leaderboard = 1;
