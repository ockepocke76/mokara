-- V32__update_validation_status_constraint.sql
-- Add 'not_started' to validation_status values to support description-only drafts

-- Drop existing constraint
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'chk_validation_status'
    ) THEN
        ALTER TABLE CUSTOM_STRATEGIES DROP CONSTRAINT chk_validation_status;
    END IF;
END $$;

-- Add updated constraint with 'not_started' value
ALTER TABLE CUSTOM_STRATEGIES 
ADD CONSTRAINT chk_validation_status 
CHECK (validation_status IN ('validated', 'draft', 'failed', 'not_started'));

-- Note: Default remains 'validated' as set in V23
-- New description-only strategies will explicitly set 'not_started'
