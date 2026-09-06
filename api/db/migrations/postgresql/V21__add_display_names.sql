-- Add display name columns to USERS table
-- Replaces email with fun username for public display

ALTER TABLE USERS 
ADD COLUMN IF NOT EXISTS display_name VARCHAR(100) UNIQUE,
ADD COLUMN IF NOT EXISTS display_name_updated_at TIMESTAMP;

-- Create case-insensitive unique index for display names
CREATE UNIQUE INDEX IF NOT EXISTS users_display_name_lower_idx 
ON USERS (LOWER(display_name));

-- Add comment explaining the columns
COMMENT ON COLUMN USERS.display_name IS 'Public-facing username for leaderboards and published content';
COMMENT ON COLUMN USERS.display_name_updated_at IS 'Last time display name was changed';
