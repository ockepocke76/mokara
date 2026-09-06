-- Add missing columns to SIMULATION_RESULTS
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_generated_at TIMESTAMP;
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_generation_time_ms REAL;
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_error_message TEXT;
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS evaluation_data JSONB;

-- Add missing columns to CUSTOM_STRATEGIES
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS code TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS class_name TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS validation_error TEXT;
ALTER TABLE CUSTOM_STRATEGIES ADD COLUMN IF NOT EXISTS last_validation_timestamp TIMESTAMP;

-- Rename columns in CUSTOM_STRATEGIES if they exist (legacy schema)
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='parameters') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='parameters_json') THEN
        ALTER TABLE CUSTOM_STRATEGIES RENAME COLUMN parameters TO parameters_json;
    END IF;
    IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='strategy_code') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='code') THEN
        ALTER TABLE CUSTOM_STRATEGIES RENAME COLUMN strategy_code TO code;
    END IF;
     IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='strategy_description') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='custom_strategies' AND column_name='description') THEN
        ALTER TABLE CUSTOM_STRATEGIES RENAME COLUMN strategy_description TO description;
    END IF;
END $$;

-- ASSET_DATA_CACHE renames
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='asset_data_cache' AND column_name='cache_key') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='asset_data_cache' AND column_name='asset_key') THEN
        ALTER TABLE ASSET_DATA_CACHE RENAME COLUMN cache_key TO asset_key;
    END IF;
    IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='asset_data_cache' AND column_name='cached_data') AND NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='asset_data_cache' AND column_name='data_blob') THEN
        ALTER TABLE ASSET_DATA_CACHE RENAME COLUMN cached_data TO data_blob;
    END IF;
END $$;

-- Type conversions (if needed after Rename)
-- Ensure parameters_json is JSONB
DO $$
BEGIN
    BEGIN
        ALTER TABLE CUSTOM_STRATEGIES ALTER COLUMN parameters_json TYPE JSONB USING parameters_json::jsonb;
    EXCEPTION WHEN OTHERS THEN
        -- If casting fails, we might have invalid JSON. Log or ignore (keep as text).
        RAISE NOTICE 'Could not convert parameters_json to JSONB: %', SQLERRM;
    END;
END $$;
