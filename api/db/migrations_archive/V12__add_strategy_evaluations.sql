-- Strategy Leaderboard: Evaluation Results Table
-- Migration V4: Add strategy evaluations table for leaderboard system
-- Only stores LATEST evaluation per strategy (UNIQUE constraint)

CREATE TABLE IF NOT EXISTS STRATEGY_EVALUATIONS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL UNIQUE,  -- UNIQUE: only one evaluation per strategy
    strategy_class_name TEXT NOT NULL,
    strategy_category TEXT NOT NULL,  -- WITHDRAWAL_ONLY, CONTRIBUTION_ONLY, HYBRID
    evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite scores (0-100)
    excellence_score REAL NOT NULL,
    return_score REAL NOT NULL,
    risk_score REAL NOT NULL,
    robustness_score REAL NOT NULL,
    
    -- Metadata
    test_suite_version TEXT DEFAULT 'v1.0',
    scenario_results_json TEXT NOT NULL,  -- JSON blob with per-scenario detailed metrics
    evaluation_params_json TEXT NOT NULL  -- Standardized params used for this evaluation
);

-- Index for fast category-filtered leaderboard queries
CREATE INDEX IF NOT EXISTS idx_category_score 
ON STRATEGY_EVALUATIONS(strategy_category, excellence_score DESC);

-- Index for sorting by score globally
CREATE INDEX IF NOT EXISTS idx_excellence_score 
ON STRATEGY_EVALUATIONS(excellence_score DESC);
