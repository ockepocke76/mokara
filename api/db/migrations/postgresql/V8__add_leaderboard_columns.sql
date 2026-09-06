-- Add supporting columns for Leaderboard and Strategy Evaluations
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN IF NOT EXISTS is_custom BOOLEAN DEFAULT FALSE;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN IF NOT EXISTS custom_strategy_id INTEGER;
ALTER TABLE STRATEGY_EVALUATIONS ADD COLUMN IF NOT EXISTS strategy_category VARCHAR(50);

-- Optional: Add index for performance if leaderboard grows
CREATE INDEX IF NOT EXISTS idx_strategy_evaluations_category ON STRATEGY_EVALUATIONS(strategy_category);
