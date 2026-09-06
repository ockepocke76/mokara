-- V15: Add user tracking columns to STRATEGY_EVALUATIONS for custom strategies
-- Allows tracking which user created a custom strategy on the leaderboard

ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN user_id INTEGER DEFAULT NULL;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN is_custom BOOLEAN DEFAULT FALSE;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN custom_strategy_id INTEGER DEFAULT NULL;

-- Index for filtering by user
CREATE INDEX IF NOT EXISTS idx_evaluations_user_id ON STRATEGY_EVALUATIONS(user_id);
