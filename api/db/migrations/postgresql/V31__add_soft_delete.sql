-- V31__add_soft_delete.sql
-- Add soft delete support to CUSTOM_STRATEGIES

-- Add deleted_at column for soft deletes
ALTER TABLE CUSTOM_STRATEGIES 
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Create index for efficient active strategies query
-- This makes queries filtering by deleted_at IS NULL much faster
CREATE INDEX IF NOT EXISTS idx_custom_strategies_active 
ON CUSTOM_STRATEGIES(user_id, deleted_at) 
WHERE deleted_at IS NULL;

-- Optional: Create index for restore queries (admin use)
CREATE INDEX IF NOT EXISTS idx_custom_strategies_deleted 
ON CUSTOM_STRATEGIES(user_id, deleted_at) 
WHERE deleted_at IS NOT NULL;
