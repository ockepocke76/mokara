-- V10__add_anonymous_tier.sql
-- Add ANONYMOUS tier configuration for guest users

INSERT INTO TIER_CONFIG (
    tier_name, display_name, description, 
    max_simulations, max_strategies, max_pdf_downloads, 
    monthly_price_sek, color, badge, features_json,
    max_mc_iterations_builtin, max_mc_iterations_custom,
    ai_generation_credits_monthly, simulation_retention_days
) VALUES (
    'ANONYMOUS', 
    'Guest', 
    'Full access to demo content and public features',
    0,              -- Cannot create simulations
    0,              -- Cannot create strategies
    NULL,           -- Unlimited demo PDF downloads
    0,              -- monthly_price_sek
    '#9CA3AF',      -- color (Light Gray)
    '👁️',           -- badge
    '{"can_use_custom_strategies": false, "can_access_leaderboard": true, "priority_support": false, "view_demos": true, "view_public_content": true, "download_demo_pdfs": true}',
    0,              -- max_mc_iterations_builtin (cannot run sims)
    0,              -- max_mc_iterations_custom (cannot run sims)
    0,              -- ai_generation_credits_monthly (cannot generate)
    0               -- simulation_retention_days (has no sims)
);
