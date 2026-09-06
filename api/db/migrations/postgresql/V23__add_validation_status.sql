-- Add validation_status column to CUSTOM_STRATEGIES
-- This tracks whether strategy code has been validated to prevent execution of invalid code

-- Add column if it doesn't exist (might already exist from failed migration)
ALTER TABLE CUSTOM_STRATEGIES 
ADD COLUMN IF NOT EXISTS validation_status VARCHAR(20);

-- First, update ALL existing rows to 'validated' 
-- (they must have passed validation to be saved under old system)
-- This handles 'pending', NULL, empty strings, and any other invalid values
UPDATE CUSTOM_STRATEGIES 
SET validation_status = 'validated' 
WHERE validation_status IS NULL 
   OR validation_status = ''
   OR validation_status = 'pending'
   OR validation_status NOT IN ('validated', 'draft', 'failed');

-- Now change the default to 'validated' (removing any 'pending' default)
ALTER TABLE CUSTOM_STRATEGIES 
ALTER COLUMN validation_status SET DEFAULT 'validated';

-- Add constraint to ensure only valid values (with existence check)
DO $$ 
BEGIN
    -- Drop existing constraint if it exists (in case of retry)
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'chk_validation_status'
    ) THEN
        ALTER TABLE CUSTOM_STRATEGIES DROP CONSTRAINT chk_validation_status;
    END IF;
    
    -- Add the constraint
    ALTER TABLE CUSTOM_STRATEGIES 
    ADD CONSTRAINT chk_validation_status 
    CHECK (validation_status IN ('validated', 'draft', 'failed'));
END $$;
