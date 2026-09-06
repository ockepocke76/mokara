-- V25: Add accumulation-specific metrics to STRATEGY_EVALUATIONS
-- These metrics are designed for contribution/accumulation strategies

-- Add new metric columns
ALTER TABLE STRATEGY_EVALUATIONS 
    ADD COLUMN IF NOT EXISTS coast_fire_score REAL,
    ADD COLUMN IF NOT EXISTS accumulation_velocity_score REAL,
    ADD COLUMN IF NOT EXISTS contribution_efficiency_score REAL;

-- Add indexes for new metrics (for potential future leaderboard queries)
CREATE INDEX IF NOT EXISTS idx_coast_fire_score 
    ON STRATEGY_EVALUATIONS(coast_fire_score DESC);

CREATE INDEX IF NOT EXISTS idx_accumulation_velocity 
    ON STRATEGY_EVALUATIONS(accumulation_velocity_score DESC);

CREATE INDEX IF NOT EXISTS idx_contribution_efficiency 
    ON STRATEGY_EVALUATIONS(contribution_efficiency_score DESC);
