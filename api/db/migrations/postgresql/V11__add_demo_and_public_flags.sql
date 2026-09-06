-- V11__add_demo_and_public_flags.sql
-- Add flags to mark content as viewable by anonymous users

-- Add is_demo flag to USER_SIMULATION_HISTORY (correct table name)
ALTER TABLE USER_SIMULATION_HISTORY ADD COLUMN is_demo BOOLEAN DEFAULT FALSE;

-- Add is_public flag to CUSTOM_STRATEGIES (correct table name with uppercase)
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN is_public BOOLEAN DEFAULT FALSE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_simulation_history_is_demo ON USER_SIMULATION_HISTORY(is_demo);
CREATE INDEX IF NOT EXISTS idx_custom_strategies_is_public ON CUSTOM_STRATEGIES(is_public);

-- Add comment explaining the purpose
COMMENT ON COLUMN USER_SIMULATION_HISTORY.is_demo IS 'When TRUE, this simulation is visible to all users including anonymous guests';
COMMENT ON COLUMN CUSTOM_STRATEGIES.is_public IS 'When TRUE, this strategy is visible to all users including anonymous guests';
