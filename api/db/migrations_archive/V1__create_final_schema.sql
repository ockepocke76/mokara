-- V1__create_final_schema.sql
-- This is a consolidated migration file that creates the entire database schema from scratch.

-- Create the USERS table to store user information.
CREATE TABLE IF NOT EXISTS USERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create the SIMULATIONS table to store metadata for each run.
-- This version does NOT include the 'all_params' column, as it has been moved.
CREATE TABLE IF NOT EXISTS SIMULATIONS (
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

-- Create the STATISTICS table to store the results of each simulation.
CREATE TABLE IF NOT EXISTS STATISTICS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    median_final_net_worth REAL,
    p5_final_net_worth REAL,
    p10_final_net_worth REAL,
    p25_final_net_worth REAL,
    p75_final_net_worth REAL,
    p90_final_net_worth REAL,
    p95_final_net_worth REAL,
    chance_of_ruin REAL,
    chance_of_profit REAL,
    chance_of_real_profit REAL,
    success_rate REAL,
    median_year_of_ruin INTEGER,
    median_total_withdrawn REAL,
    median_real_final_net_worth REAL,
    median_years_of_spending_left REAL,
    chance_of_nominal_loss REAL,
    chance_drawdown_capped REAL,
    chance_drawdown_suspended REAL,
    median_accumulated_interest REAL,
    median_accumulated_tax REAL,
    median_accumulated_fees REAL,
    median_final_ltv REAL,
    p50_max_ltv REAL,
    p75_max_ltv REAL,
    p90_max_ltv REAL,
    strategy_sharpe_ratio REAL,
    strategy_sortino_ratio REAL,
    asset_sharpe_ratio REAL,
    asset_sortino_ratio REAL,
    var_95_loss REAL,
    cvar_95_loss REAL,
    risk_score REAL,
    risk_return_score REAL,
    all_stats TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS(id)
);

-- Create the SIMULATION_PARAMETERS table to store the large JSON blob of simulation parameters.
CREATE TABLE IF NOT EXISTS SIMULATION_PARAMETERS (
    simulation_id INTEGER NOT NULL,
    parameters TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS(id)
);