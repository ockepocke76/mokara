-- V20__add_tier_system.sql
-- Comprehensive tier system implementation
-- Supports flexible multi-tier structure (FREE, PAID, UNLIMITED, WHITELABEL)

-- Add tier management fields to USERS table
-- Note: SQLite doesn't support CURRENT_TIMESTAMP in ALTER TABLE, so we add without default first
ALTER TABLE USERS ADD COLUMN plan_tier VARCHAR(50);
ALTER TABLE USERS ADD COLUMN tier_override_reason TEXT;
ALTER TABLE USERS ADD COLUMN tier_set_at TIMESTAMP;
ALTER TABLE USERS ADD COLUMN tier_set_by VARCHAR(255);

-- Set defaults for existing users
UPDATE USERS SET plan_tier = 'FREE' WHERE plan_tier IS NULL;
UPDATE USERS SET tier_set_at = CURRENT_TIMESTAMP WHERE tier_set_at IS NULL;
UPDATE USERS SET tier_set_by = 'system' WHERE tier_set_by IS NULL;

-- Create subscription history table for audit trail
CREATE TABLE SUBSCRIPTION_HISTORY (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_tier VARCHAR(50) NOT NULL,
    changed_from VARCHAR(50),
    changed_to VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255),  -- email of admin who made change
    reason TEXT,
    FOREIGN KEY (user_id) REFERENCES USERS(id)
);

-- Add indexes for performance
CREATE INDEX idx_subscription_history_user_id ON SUBSCRIPTION_HISTORY(user_id);
CREATE INDEX idx_users_plan_tier ON USERS(plan_tier);
