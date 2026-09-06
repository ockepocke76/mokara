-- Phase 1: Archive old tables by renaming them. This is a non-destructive operation.
ALTER TABLE SIMULATIONS RENAME TO SIMULATIONS_OLD;
ALTER TABLE SIMULATION_PARAMETERS RENAME TO SIMULATION_PARAMETERS_OLD;
ALTER TABLE STATISTICS RENAME TO STATISTICS_OLD;
ALTER TABLE AI_ANALYSIS RENAME TO AI_ANALYSIS_OLD;
ALTER TABLE SIMULATION_RESULTS_DATA RENAME TO SIMULATION_RESULTS_DATA_OLD;

-- Phase 2: Create the new tables for the global caching architecture.

-- Table to store the canonical results of a unique simulation.
-- The hash of the parameters is the primary key.
CREATE TABLE CACHED_SIMULATIONS (
    simulation_hash TEXT PRIMARY KEY,
    parameters TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    results_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (results_id) REFERENCES SIMULATION_RESULTS(id)
);

-- Table to hold the actual result data blobs (stats, AI content).
-- This is separated to keep the CACHED_SIMULATIONS table lean.
CREATE TABLE SIMULATION_RESULTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stats TEXT,
    gemini_content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Re-create the table for large data blobs (plots), now linked to SIMULATION_RESULTS.
CREATE TABLE SIMULATION_RESULTS_DATA (
    results_id INTEGER NOT NULL,
    data_key TEXT NOT NULL,
    data_blob BLOB NOT NULL,
    PRIMARY KEY (results_id, data_key),
    FOREIGN KEY (results_id) REFERENCES SIMULATION_RESULTS(id) ON DELETE CASCADE
);

-- Table to link users to their simulation history.
-- This replaces the old user-centric SIMULATIONS table.
CREATE TABLE USER_SIMULATION_HISTORY (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    simulation_hash TEXT NOT NULL,
    simulation_name TEXT,
    is_removed BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id),
    FOREIGN KEY (simulation_hash) REFERENCES CACHED_SIMULATIONS(simulation_hash)
);