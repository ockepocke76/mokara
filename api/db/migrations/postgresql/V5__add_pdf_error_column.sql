-- V5__add_pdf_error_column.sql
-- Add missing PDF columns that might have been skipped in partial migrations

ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_error_message TEXT;
ALTER TABLE SIMULATION_RESULTS ADD COLUMN IF NOT EXISTS pdf_generation_time_ms INTEGER;
