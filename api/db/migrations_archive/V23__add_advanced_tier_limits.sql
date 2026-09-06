-- V23__add_advanced_tier_limits.sql
-- Add advanced tier configuration options

ALTER TABLE TIER_CONFIG ADD COLUMN max_mc_iterations_builtin INTEGER DEFAULT 1000;
ALTER TABLE TIER_CONFIG ADD COLUMN max_mc_iterations_custom INTEGER DEFAULT 500;
ALTER TABLE TIER_CONFIG ADD COLUMN ai_generation_credits_monthly INTEGER DEFAULT 5;
ALTER TABLE TIER_CONFIG ADD COLUMN simulation_retention_days INTEGER DEFAULT 30;

-- Update default values for existing tiers
UPDATE TIER_CONFIG SET 
    max_mc_iterations_builtin = 1000,
    max_mc_iterations_custom = 500,
    ai_generation_credits_monthly = 5,
    simulation_retention_days = 30
WHERE tier_name = 'FREE';

UPDATE TIER_CONFIG SET 
    max_mc_iterations_builtin = 5000,
    max_mc_iterations_custom = 2500,
    ai_generation_credits_monthly = 50,
    simulation_retention_days = 365
WHERE tier_name = 'PAID';

UPDATE TIER_CONFIG SET 
    max_mc_iterations_builtin = 10000,
    max_mc_iterations_custom = 10000,
    ai_generation_credits_monthly = 999999,
    simulation_retention_days = NULL  -- NULL = forever
WHERE tier_name = 'UNLIMITED';

UPDATE TIER_CONFIG SET 
    max_mc_iterations_builtin = 10000,
    max_mc_iterations_custom = 10000,
    ai_generation_credits_monthly = 999999,
    simulation_retention_days = NULL  -- NULL = forever
WHERE tier_name = 'WHITELABEL';

-- Track AI credit usage
CREATE TABLE IF NOT EXISTS AI_CREDIT_USAGE (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    month VARCHAR NOT NULL,  -- Format: YYYY-MM
    credits_used INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id),
    UNIQUE(user_id, month)
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_user_month ON AI_CREDIT_USAGE(user_id, month);
