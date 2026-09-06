-- V7__fix_asset_cache_schema.sql
-- Fix ASSET_DATA_CACHE schema mismatch and ensure missing columns

-- 1. Recreate ASSET_DATA_CACHE with canonical schema (BYTEA for data_blob)
DROP TABLE IF EXISTS ASSET_DATA_CACHE;

CREATE TABLE ASSET_DATA_CACHE (
    asset_key TEXT PRIMARY KEY,
    data_blob BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- 2. Ensure pdf_generated_at exists (missed in V5, present in V2 but V2 failed for some)
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_generated_at TIMESTAMP;
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS evaluation_data JSONB;
