-- V6__set_default_plan_tier.sql
-- Fixes "Tier 'None' not found" warnings by enforcing default 'FREE' tier

-- 1. Backfill existing NULLs to 'FREE'
UPDATE USERS SET plan_tier = 'FREE' WHERE plan_tier IS NULL;

-- 2. Set default constraint for future inserts
ALTER TABLE USERS ALTER COLUMN plan_tier SET DEFAULT 'FREE';
