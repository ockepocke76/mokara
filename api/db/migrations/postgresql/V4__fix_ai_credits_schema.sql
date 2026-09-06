-- V4__fix_ai_credits_schema.sql
-- Add missing columns to AI_CREDIT_USAGE for LimitEnforcer compatibility

-- Add month column (YYYY-MM)
ALTER TABLE AI_CREDIT_USAGE ADD COLUMN IF NOT EXISTS month VARCHAR(7);

-- Add last_updated column
ALTER TABLE AI_CREDIT_USAGE ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add unique constraint for UPSERT support
-- If there is existing data without month, we might need to handle it. 
-- Assuming existing data is invalid or we can just default to current month if null?
-- For now, let's just add the constraint. If it fails due to duplicates, we'll need a cleanup.
-- But since code was failing to write, table is likely empty or has rows without month.
-- If 'month' is null, unique constraint allows multiple nulls.
-- But LimitEnforcer inserts with month.

ALTER TABLE AI_CREDIT_USAGE ADD CONSTRAINT unique_user_month UNIQUE (user_id, month);
