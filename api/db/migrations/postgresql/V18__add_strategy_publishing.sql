-- Add is_published_to_leaderboard column to CUSTOM_STRATEGIES
-- This allows users to explicitly opt-in to showing their strategy on the public leaderboard

DO $$
BEGIN
    -- Add is_published_to_leaderboard column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'custom_strategies' 
        AND column_name = 'is_published_to_leaderboard'
    ) THEN
        ALTER TABLE CUSTOM_STRATEGIES 
        ADD COLUMN is_published_to_leaderboard BOOLEAN DEFAULT FALSE;
        
        CREATE INDEX idx_custom_strategies_published 
        ON CUSTOM_STRATEGIES(is_published_to_leaderboard) 
        WHERE is_published_to_leaderboard = TRUE;
        
        COMMENT ON COLUMN CUSTOM_STRATEGIES.is_published_to_leaderboard IS 
        'When TRUE, user has explicitly consented to show this strategy on the public leaderboard with their username';
    END IF;
END $$;
