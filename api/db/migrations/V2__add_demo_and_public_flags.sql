-- V2__add_demo_and_public_flags.sql
-- Add flags to mark content as viewable by anonymous users (SQLite version)

-- Add is_demo flag to USER_SIMULATION_HISTORY
ALTER TABLE USER_SIMULATION_HISTORY ADD COLUMN is_demo BOOLEAN DEFAULT FALSE;

-- Add is_public flag to CUSTOM_STRATEGIES  
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN is_public BOOLEAN DEFAULT FALSE;

-- Note: Indexes for these columns are already created in V1__complete_schema.sql
