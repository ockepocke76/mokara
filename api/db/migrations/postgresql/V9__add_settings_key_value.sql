-- Add generic key-value columns to USER_SETTINGS for flexible settings storage
ALTER TABLE USER_SETTINGS ADD COLUMN IF NOT EXISTS setting_key VARCHAR(100);
ALTER TABLE USER_SETTINGS ADD COLUMN IF NOT EXISTS setting_value TEXT;

-- Drop the old primary key and create a composite one
ALTER TABLE USER_SETTINGS DROP CONSTRAINT IF EXISTS user_settings_pkey;
ALTER TABLE USER_SETTINGS ADD CONSTRAINT user_settings_pkey PRIMARY KEY (user_id, setting_key);

-- Migrate existing default_currency to new format
INSERT INTO USER_SETTINGS (user_id, setting_key, setting_value, updated_at)
SELECT user_id, 'currency', default_currency, updated_at
FROM USER_SETTINGS
WHERE default_currency IS NOT NULL
ON CONFLICT (user_id, setting_key) DO NOTHING;

-- Drop old column (optional - keep for now for backwards compatibility)
-- ALTER TABLE USER_SETTINGS DROP COLUMN IF EXISTS default_currency;
