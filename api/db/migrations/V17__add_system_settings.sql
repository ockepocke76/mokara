-- Create SYSTEM_SETTINGS table for global configuration
CREATE TABLE IF NOT EXISTS SYSTEM_SETTINGS (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default beta user limit (default to 50)
INSERT OR IGNORE INTO SYSTEM_SETTINGS (setting_key, setting_value)
VALUES ('max_beta_users', '50');
