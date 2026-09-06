-- V8__add_pdf_tracking.sql
-- Add PDF tracking columns to SIMULATION_RESULTS table for automatic PDF generation

-- Add PDF status column
ALTER TABLE SIMULATION_RESULTS ADD COLUMN pdf_status TEXT DEFAULT 'pending';
  -- Values: 'pending', 'processing', 'ready', 'failed'

-- Add PDF storage path column (works for both local files and Snowflake STAGE)
ALTER TABLE SIMULATION_RESULTS ADD COLUMN pdf_storage_path TEXT;
  -- Local example: './pdf_cache/ab/c1/abc123def456.pdf'
  -- Snowflake example: '@PDF_REPORTS/abc123def456.pdf'

-- Add timestamp for when PDF was generated
ALTER TABLE SIMULATION_RESULTS ADD COLUMN pdf_generated_at TIMESTAMP;

-- Add generation time in milliseconds for performance tracking
ALTER TABLE SIMULATION_RESULTS ADD COLUMN pdf_generation_time_ms INTEGER;

-- Add error message for failed PDF generations
ALTER TABLE SIMULATION_RESULTS ADD COLUMN pdf_error_message TEXT;

-- Create index for efficient querying of pending PDFs
CREATE INDEX IF NOT EXISTS idx_pdf_status ON SIMULATION_RESULTS(pdf_status);
