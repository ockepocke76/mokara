-- Add tables for login request tracking and database-backed user access management

-- Table to track unauthorized login attempts
CREATE TABLE IF NOT EXISTS login_requests (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    first_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attempt_count INTEGER DEFAULT 1,
    notes TEXT
);

-- Table to store allowed users (replaces allowed_users.txt)
CREATE TABLE IF NOT EXISTS allowed_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR(255),
    notes TEXT
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_login_requests_email ON login_requests(email);
CREATE INDEX IF NOT EXISTS idx_login_requests_last_attempt ON login_requests(last_attempt_at DESC);
CREATE INDEX IF NOT EXISTS idx_allowed_users_email ON allowed_users(email);
