-- V20__add_is_public_to_simulations.sql
-- Move the is_public flag from USER_SIMULATION_HISTORY to CACHED_SIMULATIONS
-- This makes semantic sense: "public" is a property of the simulation itself, not the user's relationship to it
-- Rename from is_demo to is_public for consistency with CUSTOM_STRATEGIES

DO $$
BEGIN
    -- Add is_public column to CACHED_SIMULATIONS if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cached_simulations' 
        AND column_name = 'is_public'
    ) THEN
        ALTER TABLE CACHED_SIMULATIONS 
        ADD COLUMN is_public BOOLEAN DEFAULT FALSE;
        
        -- Create partial index for performance (only index TRUE values)
        CREATE INDEX idx_cached_simulations_is_public 
        ON CACHED_SIMULATIONS(is_public) 
        WHERE is_public = TRUE;
        
        COMMENT ON COLUMN CACHED_SIMULATIONS.is_public IS 
        'When TRUE, this simulation is visible to all users including anonymous guests. Replaces is_demo from USER_SIMULATION_HISTORY.';
    END IF;
END $$;
