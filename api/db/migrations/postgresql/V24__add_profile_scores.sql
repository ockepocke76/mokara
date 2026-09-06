-- Add STRATEGY_PROFILE_SCORES table for pre-calculated excellence scores per profile
-- This eliminates the need for on-the-fly recalculation in the UI

CREATE TABLE IF NOT EXISTS STRATEGY_PROFILE_SCORES (
    evaluation_id INTEGER NOT NULL,
    profile_key VARCHAR(50) NOT NULL,
    excellence_score REAL NOT NULL,
    rank_overall INTEGER,
    rank_in_category INTEGER,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (evaluation_id, profile_key),
    FOREIGN KEY (evaluation_id) REFERENCES STRATEGY_EVALUATIONS(id) ON DELETE CASCADE
);

-- Index for fast lookups by profile and score (for leaderboard queries)
CREATE INDEX IF NOT EXISTS idx_profile_scores_ranking 
    ON STRATEGY_PROFILE_SCORES(profile_key, excellence_score DESC);

-- Index for category-specific rankings
CREATE INDEX IF NOT EXISTS idx_profile_scores_category 
    ON STRATEGY_PROFILE_SCORES(profile_key, rank_in_category);

-- Index for reverse lookups (all profiles for a given evaluation)
CREATE INDEX IF NOT EXISTS idx_profile_scores_eval 
    ON STRATEGY_PROFILE_SCORES(evaluation_id);
