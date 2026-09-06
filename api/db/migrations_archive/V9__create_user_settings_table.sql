-- V9__create_user_settings_table.sql
-- Migration to add user settings table for storing user-specific preferences

CREATE TABLE IF NOT EXISTS USER_SETTINGS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS(id) ON DELETE CASCADE,
    UNIQUE(user_id, setting_key)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON USER_SETTINGS(user_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_key ON USER_SETTINGS(user_id, setting_key);

-- Insert default settings for existing users (if any)
-- Default currency is SEK to maintain backward compatibility
INSERT OR IGNORE INTO USER_SETTINGS (user_id, setting_key, setting_value)
SELECT id, 'currency', 'SEK' FROM USERS;

INSERT OR IGNORE INTO USER_SETTINGS (user_id, setting_key, setting_value)
SELECT id, 'currency_symbol', 'SEK' FROM USERS;

INSERT OR IGNORE INTO USER_SETTINGS (user_id, setting_key, setting_value)
SELECT id, 'locale', 'sv_SE' FROM USERS;
