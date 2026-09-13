-- Worker liveness tracking for stale-job recovery (CODE_REVIEW R2.1).
-- Recovery keys on "worker stopped heartbeating" instead of wall-clock age,
-- so long-running jobs on a live worker are never reset mid-run.
ALTER TABLE BACKGROUND_JOBS ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP;
