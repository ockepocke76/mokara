-- V1__complete_schema.sql
-- Complete database schema for the BTC Simulator application
-- This single migration creates all tables needed for the system

-- ============================================================================
-- USER MANAGEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS USERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    plan_tier VARCHAR(50),
    tier_override_reason TEXT,
    tier_set_at TIMESTAMP,
    tier_set_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS USER_SETTINGS (
    user_id INTEGER PRIMARY KEY,
    default_currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

-- ============================================================================
-- SIMULATION CACHING
-- ============================================================================

CREATE TABLE IF NOT EXISTS CACHED_SIMULATIONS (
    simulation_hash TEXT PRIMARY KEY,
    parameters TEXT NOT NULL,
    ui_parameters TEXT,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    results_id INTEGER,
    component_hashes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (results_id) REFERENCES SIMULATION_RESULTS(id)
);

CREATE TABLE IF NOT EXISTS SIMULATION_RESULTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stats TEXT,
    gemini_content TEXT,
    evaluation_data TEXT,
    results_dataframe BLOB,
    average_results_df BLOB,
    median_yearly_results_df BLOB,
    pdf_storage_path TEXT,
    pdf_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SIMULATION_RESULTS_DATA (
    results_id INTEGER NOT NULL,
    data_key TEXT NOT NULL,
    data_blob BLOB NOT NULL,
    PRIMARY KEY (results_id, data_key),
    FOREIGN KEY (results_id) REFERENCES SIMULATION_RESULTS(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS USER_SIMULATION_HISTORY (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    simulation_hash TEXT NOT NULL,
    simulation_name TEXT,
    status VARCHAR(20) DEFAULT 'completed',
    is_removed BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id),
    FOREIGN KEY (simulation_hash) REFERENCES CACHED_SIMULATIONS(simulation_hash)
);

CREATE INDEX IF NOT EXISTS idx_user_history_status ON USER_SIMULATION_HISTORY(status);
CREATE INDEX IF NOT EXISTS idx_user_history_is_demo ON USER_SIMULATION_HISTORY(is_demo);
CREATE INDEX IF NOT EXISTS idx_custom_strategies_is_public ON CUSTOM_STRATEGIES(is_public);

-- ============================================================================
-- STRATEGY MANAGEMENT  
-- ============================================================================

CREATE TABLE IF NOT EXISTS CUSTOM_STRATEGIES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    strategy_name VARCHAR(255) NOT NULL,
    strategy_description TEXT,
    strategy_code TEXT NOT NULL,
    parameters TEXT,
    ai_description TEXT,
    validation_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

CREATE TABLE IF NOT EXISTS STRATEGY_EVALUATIONS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name VARCHAR(255) NOT NULL UNIQUE,
    user_id INTEGER,
    excellence_score REAL,
    risk_management_score REAL,
    withdrawal_adequacy_score REAL,
    capital_efficiency_score REAL,
    wealth_building_score REAL,
    drawdown_resilience_score REAL,
    consumption_ratio_score REAL,
    usability_score REAL,
    ulcer_management_score REAL,
    psychological_resilience_score REAL,
    scenario_results_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

-- ============================================================================
-- TIER & SUBSCRIPTION SYSTEM
-- ============================================================================

CREATE TABLE IF NOT EXISTS TIER_CONFIG (
    tier_name VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(100),
    simulation_limit INTEGER,
    advanced_simulation_limit INTEGER,
    gemini_credits_per_month INTEGER,
    can_use_pdf_reports BOOLEAN DEFAULT TRUE,
    can_use_custom_strategies BOOLEAN DEFAULT FALSE,
    can_access_leaderboard BOOLEAN DEFAULT FALSE,
    monthly_price_usd REAL DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SUBSCRIPTION_HISTORY (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_tier VARCHAR(50) NOT NULL,
    changed_from VARCHAR(50),
    changed_to VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255),
    reason TEXT,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

CREATE INDEX IF NOT EXISTS idx_subscription_history_user_id ON SUBSCRIPTION_HISTORY(user_id);
CREATE INDEX IF NOT EXISTS idx_users_plan_tier ON USERS(plan_tier);

CREATE TABLE IF NOT EXISTS AI_CREDIT_USAGE (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    credits_used INTEGER NOT NULL,
    operation_type VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

-- ============================================================================
-- CACHE & LOGGING
-- ============================================================================

CREATE TABLE IF NOT EXISTS ASSET_DATA_CACHE (
    cache_key TEXT PRIMARY KEY,
    cached_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS LOGS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    simulation_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

-- ============================================================================
-- LEGACY TABLES (for backward compatibility during transition)
-- ============================================================================

CREATE TABLE IF NOT EXISTS SIMULATIONS_OLD (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    strategy VARCHAR(50),
    asset_model VARCHAR(50),
    num_years INTEGER,
    num_simulations INTEGER,
    initial_investment REAL,
    simulation_name VARCHAR(255),
    pdf_report_path VARCHAR,
    is_removed BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

CREATE TABLE IF NOT EXISTS SIMULATION_PARAMETERS_OLD (
    simulation_id INTEGER NOT NULL,
    parameters TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS_OLD(id)
);

CREATE TABLE IF NOT EXISTS STATISTICS_OLD (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    median_final_net_worth REAL,
    all_stats TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS_OLD(id)
);

CREATE TABLE IF NOT EXISTS AI_ANALYSIS_OLD (
    simulation_id INTEGER PRIMARY KEY,
    analysis TEXT,
    main_outcome TEXT,
    bottom_line TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS_OLD(id)
);

CREATE TABLE IF NOT EXISTS SIMULATION_RESULTS_DATA_OLD (
    simulation_id INTEGER NOT NULL,
    data_key TEXT NOT NULL,
    data_blob BLOB NOT NULL,
    PRIMARY KEY (simulation_id, data_key),
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS_OLD(id) ON DELETE CASCADE
);
