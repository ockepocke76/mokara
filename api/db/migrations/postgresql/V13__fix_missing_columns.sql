-- V13__fix_missing_columns.sql
-- Ensure is_public and is_demo columns exist (fixing failed partial V11 application)

-- Add is_public to CUSTOM_STRATEGIES if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custom_strategies' AND column_name = 'is_public') THEN
        ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN is_public BOOLEAN DEFAULT FALSE;
        CREATE INDEX idx_custom_strategies_is_public ON CUSTOM_STRATEGIES(is_public);
        COMMENT ON COLUMN CUSTOM_STRATEGIES.is_public IS 'When TRUE, this strategy is visible to all users including anonymous guests';
    END IF;
END $$;

-- Add is_demo to USER_SIMULATION_HISTORY if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_simulation_history' AND column_name = 'is_demo') THEN
        ALTER TABLE USER_SIMULATION_HISTORY ADD COLUMN is_demo BOOLEAN DEFAULT FALSE;
        CREATE INDEX idx_user_simulation_history_is_demo ON USER_SIMULATION_HISTORY(is_demo);
        COMMENT ON COLUMN USER_SIMULATION_HISTORY.is_demo IS 'When TRUE, this simulation is visible to all users including anonymous guests';
    END IF;
END $$;
