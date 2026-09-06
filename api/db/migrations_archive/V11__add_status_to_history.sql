-- Add status column to USER_SIMULATION_HISTORY table
-- This allows tracking of failed simulations

ALTER TABLE USER_SIMULATION_HISTORY 
ADD COLUMN status VARCHAR(20) DEFAULT 'completed';

-- Create index for status lookups
CREATE INDEX IF NOT EXISTS idx_user_history_status 
ON USER_SIMULATION_HISTORY(status);
