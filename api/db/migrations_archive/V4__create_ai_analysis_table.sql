-- V4: Create table for storing AI-generated analysis content
-- This separates large text fields from the main SIMULATIONS table.

CREATE TABLE IF NOT EXISTS AI_ANALYSIS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INT NOT NULL,
    analysis_content TEXT,
    main_outcome_content TEXT,
    bottom_line_content TEXT,
    FOREIGN KEY (simulation_id) REFERENCES SIMULATIONS(id)
);