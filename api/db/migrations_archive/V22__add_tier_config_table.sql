-- V22__add_tier_config_table.sql
-- Dynamic tier configuration system
-- Allows admins to modify tier limits without code changes

CREATE TABLE IF NOT EXISTS TIER_CONFIG (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier_name VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    description TEXT,
    max_simulations INTEGER NOT NULL,
    max_strategies INTEGER NOT NULL,
    max_pdf_downloads INTEGER,  -- NULL = unlimited
    color VARCHAR,
    badge VARCHAR,
    monthly_price_sek DECIMAL(10, 2),
    features_json TEXT,  -- JSON object with feature flags
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR  -- Admin email
);

-- Insert default tier configurations
INSERT INTO TIER_CONFIG (tier_name, display_name, description, max_simulations, max_strategies, max_pdf_downloads, color, badge, monthly_price_sek, features_json) VALUES
('FREE', 'Free', 'Evaluation access for FIRE community members', 5, 3, 3, '#6B7280', '🆓', 0, '{"basic_simulations": true, "custom_strategies": true, "pdf_reports": true, "ai_analysis": true, "strategy_evaluations": true, "leaderboard_access": true, "priority_support": false, "api_access": false}'),
('PAID', 'Paid', 'Enhanced features for active users', 100, 50, NULL, '#3B82F6', '⭐', 50, '{"basic_simulations": true, "custom_strategies": true, "pdf_reports": true, "ai_analysis": true, "strategy_evaluations": true, "leaderboard_access": true, "priority_support": true, "api_access": false}'),
('UNLIMITED', 'Unlimited', 'No limits for power users', 999999, 999999, NULL, '#8B5CF6', '💎', 200, '{"basic_simulations": true, "custom_strategies": true, "pdf_reports": true, "ai_analysis": true, "strategy_evaluations": true, "leaderboard_access": true, "priority_support": true, "api_access": true}'),
('WHITELABEL', 'Whitelabel', 'Custom solutions for businesses', 999999, 999999, NULL, '#059669', '🏢', NULL, '{"basic_simulations": true, "custom_strategies": true, "pdf_reports": true, "ai_analysis": true, "strategy_evaluations": true, "leaderboard_access": true, "priority_support": true, "api_access": true}');

-- Index for fast tier lookups
CREATE INDEX IF NOT EXISTS idx_tier_config_name ON TIER_CONFIG(tier_name);
