-- V3__update_tier_config.sql
-- Update TIER_CONFIG table to match current application logic (LimitEnforcer)
-- and populate it with default tiers.

-- Recreate table with correct columns matching LimitEnforcer expectations
DROP TABLE IF EXISTS TIER_CONFIG;

CREATE TABLE TIER_CONFIG (
    tier_name VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(100),
    description TEXT,
    max_simulations INTEGER,
    max_strategies INTEGER,
    max_pdf_downloads INTEGER,
    monthly_price_sek INTEGER,
    color VARCHAR(20),
    badge VARCHAR(20),
    features_json TEXT,
    max_mc_iterations_builtin INTEGER DEFAULT 1000,
    max_mc_iterations_custom INTEGER DEFAULT 500,
    ai_generation_credits_monthly INTEGER DEFAULT 5,
    simulation_retention_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert Default Tiers

-- FREE Tier
INSERT INTO TIER_CONFIG (
    tier_name, display_name, description, 
    max_simulations, max_strategies, max_pdf_downloads, 
    monthly_price_sek, color, badge, features_json,
    max_mc_iterations_builtin, max_mc_iterations_custom,
    ai_generation_credits_monthly, simulation_retention_days
) VALUES (
    'FREE', 
    'Free API Only', 
    'Basic access for individuals exploring the simulator.',
    5,              -- max_simulations
    3,              -- max_strategies (custom)
    3,              -- max_pdf_downloads
    0,              -- monthly_price_sek
    '#6B7280',      -- color (Gray)
    '🆓',           -- badge
    '{"can_use_custom_strategies": true, "can_access_leaderboard": true, "priority_support": false}',
    1000,           -- max_mc_iterations_builtin
    500,            -- max_mc_iterations_custom
    5,              -- ai_generation_credits_monthly
    7               -- simulation_retention_days (1 week)
);

-- PRO Tier
INSERT INTO TIER_CONFIG (
    tier_name, display_name, description, 
    max_simulations, max_strategies, max_pdf_downloads, 
    monthly_price_sek, color, badge, features_json,
    max_mc_iterations_builtin, max_mc_iterations_custom,
    ai_generation_credits_monthly, simulation_retention_days
) VALUES (
    'PRO', 
    'Pro Investor', 
    'Enhanced limits and features for serious analysis.',
    50,             -- max_simulations
    20,             -- max_strategies
    50,             -- max_pdf_downloads
    99,             -- monthly_price_sek
    '#3B82F6',      -- color (Blue)
    '🚀',           -- badge
    '{"can_use_custom_strategies": true, "can_access_leaderboard": true, "priority_support": true}',
    5000,           -- max_mc_iterations_builtin
    2000,           -- max_mc_iterations_custom
    50,             -- ai_generation_credits_monthly
    30              -- simulation_retention_days (1 month)
);

-- ADMIN Tier (Unlimited)
INSERT INTO TIER_CONFIG (
    tier_name, display_name, description, 
    max_simulations, max_strategies, max_pdf_downloads, 
    monthly_price_sek, color, badge, features_json,
    max_mc_iterations_builtin, max_mc_iterations_custom,
    ai_generation_credits_monthly, simulation_retention_days
) VALUES (
    'ADMIN', 
    'Administrator', 
    'Unlimited access for system administrators.',
    999999,         -- max_simulations
    999999,         -- max_strategies
    999999,         -- max_pdf_downloads
    0,              -- monthly_price_sek
    '#EF4444',      -- color (Red)
    '🛡️',           -- badge
    '{"can_use_custom_strategies": true, "can_access_leaderboard": true, "priority_support": true, "admin_dashboard": true}',
    10000,          -- max_mc_iterations_builtin
    10000,          -- max_mc_iterations_custom
    999999,         -- ai_generation_credits_monthly
    NULL            -- simulation_retention_days (Unlimited)
);
