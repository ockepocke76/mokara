-- Create Global Stats Table
CREATE TABLE IF NOT EXISTS GLOBAL_STATS (
    metric_key VARCHAR(255) PRIMARY KEY,
    metric_value BIGINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed initial values if table is empty or specific keys missing
-- 1. Total Simulations Run
INSERT INTO GLOBAL_STATS (metric_key, metric_value)
VALUES (
    'total_simulations_run', 
    (SELECT COUNT(*) FROM USER_SIMULATION_HISTORY)
)
ON CONFLICT (metric_key) DO NOTHING;

-- 2. Total Strategies Created
INSERT INTO GLOBAL_STATS (metric_key, metric_value)
VALUES (
    'total_strategies_created', 
    (SELECT COUNT(*) FROM CUSTOM_STRATEGIES)
)
ON CONFLICT (metric_key) DO NOTHING;

-- 3. Total Years Simulated
-- Calculate sum of num_years for all historical user simulations
INSERT INTO GLOBAL_STATS (metric_key, metric_value)
VALUES (
    'total_years_simulated',
    (
        SELECT COALESCE(SUM(CAST(parameters::jsonb->>'num_years' AS INT)), 0)
        FROM CACHED_SIMULATIONS
        WHERE simulation_hash IN (SELECT simulation_hash FROM USER_SIMULATION_HISTORY)
    )
)
ON CONFLICT (metric_key) DO NOTHING;
