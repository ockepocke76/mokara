-- Add validation status tracking to custom_strategies table
-- This allows us to filter out invalid strategies from the sidebar
-- while still allowing users to save and fix them in the designer

ALTER TABLE custom_strategies ADD COLUMN validation_status TEXT DEFAULT 'not_checked';
ALTER TABLE custom_strategies ADD COLUMN validation_error TEXT;
ALTER TABLE custom_strategies ADD COLUMN last_validation_timestamp DATETIME;
