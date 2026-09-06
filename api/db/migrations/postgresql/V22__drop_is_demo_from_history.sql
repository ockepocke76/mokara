-- V22__drop_is_demo_from_history.sql
-- Remove the old is_demo column from USER_SIMULATION_HISTORY
-- This column has been replaced by is_public on CACHED_SIMULATIONS (V20)
-- Only run this after confirming V20 and V21 have been successfully applied

DO $$
BEGIN
    -- Drop the is_demo column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_simulation_history' 
        AND column_name = 'is_demo'
    ) THEN
        -- Drop the index first
        DROP INDEX IF EXISTS idx_user_simulation_history_is_demo;
        
        -- Drop the column
        ALTER TABLE USER_SIMULATION_HISTORY 
        DROP COLUMN is_demo;
    END IF;
END $$;
