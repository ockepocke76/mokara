-- V3: Create table for storing pre-calculated simulation results data
-- This table holds various data artifacts derived from the main simulation run,
-- allowing for report regeneration without storing the full, raw results_dataframe.

CREATE TABLE IF NOT EXISTS SIMULATION_RESULTS_DATA (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INT NOT NULL,
    data_key VARCHAR(255) NOT NULL, -- e.g., 'percentile_paths', 'final_values', 'sampled_paths'
    data_blob BLOB NOT NULL, -- The compressed parquet data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS(id),
    UNIQUE (simulation_id, data_key) -- Ensure only one of each key per simulation
);