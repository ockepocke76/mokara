-- Background Jobs Queue Table
-- Production-ready job queue for PDF generation, strategy evaluation, and other async tasks

CREATE TABLE IF NOT EXISTS BACKGROUND_JOBS (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Job identification
    job_type VARCHAR(100) NOT NULL,  -- 'pdf_generation', 'strategy_evaluation', etc.
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    priority INTEGER NOT NULL DEFAULT 5,  -- 1-10, higher = more urgent
    
    -- Job data (JSONB for flexibility)
    payload JSONB NOT NULL,  -- Input parameters
    result JSONB,  -- Output result (when completed)
    error_message TEXT,  -- Error details (when failed)
    
    -- Ownership & auditing
    user_id INTEGER REFERENCES USERS(id) ON DELETE SET NULL,
    idempotency_key VARCHAR(255) UNIQUE,  -- Prevent duplicate jobs
    
    -- Retry logic
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Timing & timeouts
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- For delayed jobs
    started_at TIMESTAMP,  -- When worker claimed job
    completed_at TIMESTAMP,  -- When job finished (success or failure)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timeout_seconds INTEGER DEFAULT 900,  -- 15 minutes default
    processing_time_ms INTEGER,  -- Performance tracking
    
    -- Worker tracking (for debugging)
    worker_id VARCHAR(255),
    
    -- Constraints
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED'))
);

-- Indexes for performance
-- Most important: Workers fetch jobs by status + priority
CREATE INDEX idx_jobs_status_priority ON BACKGROUND_JOBS(status, priority DESC, created_at ASC)
    WHERE status = 'PENDING';  -- Partial index for faster worker queries

-- User job lookup
CREATE INDEX idx_jobs_user ON BACKGROUND_JOBS(user_id, created_at DESC);

-- Job type filtering (for admin dashboard)
CREATE INDEX idx_jobs_type ON BACKGROUND_JOBS(job_type, created_at DESC);

-- Scheduled jobs (for future: delayed execution)
CREATE INDEX idx_jobs_scheduled ON BACKGROUND_JOBS(scheduled_at)
    WHERE status = 'PENDING';

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_background_jobs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_background_jobs_timestamp
BEFORE UPDATE ON BACKGROUND_JOBS
FOR EACH ROW
EXECUTE FUNCTION update_background_jobs_timestamp();

-- Comment for documentation
COMMENT ON TABLE BACKGROUND_JOBS IS 'Production job queue for async tasks (PDF generation, strategy evaluation, etc.)';
COMMENT ON COLUMN BACKGROUND_JOBS.idempotency_key IS 'Unique key to prevent duplicate job creation (e.g., pdf_gen_{history_id})';
COMMENT ON COLUMN BACKGROUND_JOBS.priority IS 'Higher number = higher priority. User-facing tasks (PDF download) should be 7-10, batch tasks 1-3';
COMMENT ON COLUMN BACKGROUND_JOBS.worker_id IS 'Identifier of worker that claimed this job (for debugging stuck jobs)';
