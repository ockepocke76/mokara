"""Background job queue: create, claim, heartbeat, and recover jobs.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import json
import logging

import psycopg2
from psycopg2 import extras

from ..utils import _sanitize_for_json
from ..logging_utils import log_db_call


class JobsMixin:
    """Background job queue: create, claim, heartbeat, and recover jobs. Mixed into PostgreSQLDatabase."""

    # Terminal job transitions are fenced: they only apply while the job is
    # still PROCESSING and (when a worker_id is given) still owned by that
    # worker. A worker whose claim was revoked by stale-job recovery — and
    # whose job may already be re-running elsewhere — must not overwrite the
    # reclaimer's state (CODE_REVIEW R2.1).
    _JOB_OWNER_FENCE = "AND status = 'PROCESSING' AND (%(worker_id)s::text IS NULL OR worker_id = %(worker_id)s)"

    @log_db_call
    def create_background_job(self, job_type, payload, user_id=None, priority=5, 
                             idempotency_key=None, max_retries=3, timeout_seconds=900):
        """
        Create a new background job.
        
        Args:
            job_type: Type of job ('pdf_generation', 'strategy_evaluation', etc.)
            payload: Dict of job parameters (will be serialized to JSONB)
            user_id: ID of user who requested the job
            priority: 1-10, higher = more urgent (default: 5)
            idempotency_key: Unique key to prevent duplicate jobs
            max_retries: Maximum retry attempts on failure
            timeout_seconds: Timeout for processing (default: 15 minutes)
            
        Returns:
            str: Job ID (UUID as string)
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
            # Sanitize payload for JSON (handles date/datetime/numpy objects)
            sanitized_payload = _sanitize_for_json(payload)
            
            cursor.execute("""
                INSERT INTO BACKGROUND_JOBS (
                    job_type, payload, user_id, priority, scheduled_at,
                    idempotency_key, max_retries, timeout_seconds
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING id
            """, (job_type, json.dumps(sanitized_payload), user_id, priority, 
                  idempotency_key, max_retries, timeout_seconds))
            
            job_id = cursor.fetchone()[0]
            conn.commit()
            logging.info(f"Created background job {job_id}: {job_type}")
            return str(job_id)
        except psycopg2.IntegrityError as e:
            # Idempotency key violation - job already exists
            conn.rollback()
            if idempotency_key:
                logging.info(f"Job with idempotency_key {idempotency_key} already exists")
                # Fetch existing job ID
                cursor.execute("SELECT id FROM BACKGROUND_JOBS WHERE idempotency_key = %s", (idempotency_key,))
                row = cursor.fetchone()
                return str(row[0]) if row else None
            raise
        except Exception as e:
            logging.error(f"Failed to create background job: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_job_by_id(self, job_id):
        """Get job details by ID."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("SELECT * FROM BACKGROUND_JOBS WHERE id = %s", (job_id,))
                job = cursor.fetchone()

            if job:
                # Deserialize JSON columns
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                job['result'] = self.deserialize_json_column(job.get('result'))

            return job
        except Exception as e:
            logging.error(f"Failed to get job {job_id}: {e}", exc_info=True)
            return None

    @log_db_call
    def get_job_by_idempotency_key(self, idempotency_key):
        """Get job by idempotency key (for duplicate prevention)."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("SELECT * FROM BACKGROUND_JOBS WHERE idempotency_key = %s", (idempotency_key,))
                job = cursor.fetchone()

            if job:
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                job['result'] = self.deserialize_json_column(job.get('result'))

            return job
        except Exception as e:
            logging.error(f"Failed to get job by idempotency_key: {e}", exc_info=True)
            return None

    @log_db_call
    def fetch_and_lock_job(self, worker_id):
        """
        Fetch and lock the next available job for processing.
        
        Uses FOR UPDATE SKIP LOCKED to allow multiple workers to safely
        fetch different jobs concurrently without conflicts.
        
        Args:
            worker_id: Identifier of worker claiming the job
            
        Returns:
            dict: Job data, or None if no jobs available
        """
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor) as cursor:
                # CRITICAL: FOR UPDATE SKIP LOCKED is the magic that allows concurrent workers
                cursor.execute("""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'PROCESSING',
                        started_at = CURRENT_TIMESTAMP,
                        heartbeat_at = CURRENT_TIMESTAMP,
                        worker_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id FROM BACKGROUND_JOBS
                        WHERE status = 'PENDING'
                          AND scheduled_at <= CURRENT_TIMESTAMP
                        ORDER BY priority DESC, created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING *
                """, (worker_id,))

                job = cursor.fetchone()

            # Post-commit, as before: the claim is durable even if
            # deserialization/logging below were to fail.
            if job:
                # Deserialize JSON columns
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                logging.info(f"Worker {worker_id} claimed job {job['id']}: {job['job_type']}")

            return job
        except Exception as e:
            logging.error(f"Failed to fetch job for worker {worker_id}: {e}", exc_info=True)
            return None

    @log_db_call
    def complete_job(self, job_id, result, worker_id=None):
        """
        Mark job as completed with result.

        Args:
            job_id: Job UUID
            result: Result data (will be serialized to JSONB)
            worker_id: When given, the update only applies if this worker
                still owns the job (fence against revoked claims).

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(f"""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'COMPLETED',
                        result = %(result)s,
                        completed_at = CURRENT_TIMESTAMP,
                        processing_time_ms = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at)) * 1000
                    WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                """, {'result': json.dumps(_sanitize_for_json(result)),
                      'job_id': job_id, 'worker_id': worker_id})
                updated = cursor.rowcount > 0
            if updated:
                logging.info(f"Job {job_id} completed successfully")
            else:
                logging.warning(
                    f"Job {job_id}: completion by worker {worker_id} ignored — "
                    "claim no longer held (job was recovered or already terminal)")
            return updated
        except Exception as e:
            logging.error(f"Failed to mark job {job_id} as completed: {e}", exc_info=True)
            return False

    @log_db_call
    def fail_job(self, job_id, error_message, worker_id=None):
        """
        Mark job as permanently failed (after max retries exceeded).

        Args:
            job_id: Job UUID
            error_message: Error description
            worker_id: When given, only applies if this worker still owns the job.

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(f"""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'FAILED',
                        error_message = %(error)s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                """, {'error': error_message, 'job_id': job_id, 'worker_id': worker_id})
                updated = cursor.rowcount > 0
            if updated:
                logging.error(f"Job {job_id} failed permanently: {error_message}")
            else:
                logging.warning(
                    f"Job {job_id}: failure report by worker {worker_id} ignored — "
                    "claim no longer held")
            return updated
        except Exception as e:
            logging.error(f"Failed to mark job {job_id} as failed: {e}", exc_info=True)
            return False

    @log_db_call
    def retry_job(self, job_id, error_message, scheduled_at, worker_id=None):
        """
        Reset job to PENDING for retry with exponential backoff.

        Args:
            job_id: Job UUID
            error_message: Error that caused retry
            scheduled_at: Unix timestamp when job should be retried
            worker_id: When given, only applies if this worker still owns the job.

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(f"""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'PENDING',
                        retry_count = retry_count + 1,
                        error_message = %(error)s,
                        scheduled_at = to_timestamp(%(scheduled_at)s),
                        started_at = NULL,
                        heartbeat_at = NULL,
                        worker_id = NULL
                    WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                """, {'error': error_message, 'scheduled_at': scheduled_at,
                      'job_id': job_id, 'worker_id': worker_id})
                updated = cursor.rowcount > 0
            if updated:
                logging.warning(f"Job {job_id} scheduled for retry: {error_message}")
            else:
                logging.warning(
                    f"Job {job_id}: retry request by worker {worker_id} ignored — "
                    "claim no longer held")
            return updated
        except Exception as e:
            logging.error(f"Failed to retry job {job_id}: {e}", exc_info=True)
            return False

    @log_db_call
    def heartbeat_job(self, job_id, worker_id):
        """
        Record that the given worker is still actively processing the job.

        Returns:
            bool: True if the beat landed (this worker still owns the job);
            False when the claim was revoked — the worker's eventual
            complete/fail will be fenced out, so the job is effectively
            running for nothing.
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE BACKGROUND_JOBS
                    SET heartbeat_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND worker_id = %s AND status = 'PROCESSING'
                """, (job_id, worker_id))
                beat = cursor.rowcount > 0
            return beat
        except Exception as e:
            logging.error(f"Heartbeat failed for job {job_id}: {e}", exc_info=True)
            return False

    @log_db_call
    def update_job_status(self, job_id, status, error_message=None):
        """
        Update job status and optionally clear error message.
        
        Args:
            job_id: Job UUID
            status: New status ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
            error_message: Optional error message (None to clear)
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = %s,
                        error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, error_message, job_id))
            logging.info(f"Job {job_id} status updated to {status}")
        except Exception as e:
            logging.error(f"Failed to update job {job_id} status: {e}", exc_info=True)

    @log_db_call
    def reset_stale_jobs(self, heartbeat_timeout_seconds=300):
        """
        Re-queue PROCESSING jobs whose worker stopped heartbeating.

        Recovery keys on worker liveness, not wall-clock job age: a long
        simulation on a live worker keeps beating and is never reset mid-run
        (the old global age cutoff re-queued legitimately long jobs and
        caused concurrent double-runs — CODE_REVIEW R2.1).

        Jobs with NULL heartbeat_at were claimed by a worker that never
        beats (pre-heartbeat binary during a rolling deploy, or in-flight
        rows from before migration V38). Presuming those dead after the
        heartbeat window would re-introduce the double-run for legitimately
        long jobs — they instead get their own full timeout_seconds budget
        (default 900s) before reclaim.

        Args:
            heartbeat_timeout_seconds: silence threshold before a worker is
                presumed dead (default 5 min; beats land every ~30s).

        Returns:
            int: Number of jobs recovered
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'PENDING',
                        started_at = NULL,
                        heartbeat_at = NULL,
                        worker_id = NULL,
                        error_message = 'Recovered: worker stopped heartbeating'
                    WHERE status = 'PROCESSING'
                      AND (
                        (heartbeat_at IS NOT NULL
                         AND heartbeat_at < CURRENT_TIMESTAMP - make_interval(secs => %s))
                        OR
                        (heartbeat_at IS NULL
                         AND started_at < CURRENT_TIMESTAMP
                             - make_interval(secs => COALESCE(timeout_seconds, 900)))
                      )
                    RETURNING id
                """, (heartbeat_timeout_seconds,))

                recovered_ids = [row[0] for row in cursor.fetchall()]

            if recovered_ids:
                logging.warning(f"Recovered {len(recovered_ids)} stale jobs: {recovered_ids}")

            return len(recovered_ids)
        except Exception as e:
            logging.error(f"Failed to reset stale jobs: {e}", exc_info=True)
            return 0

    @log_db_call
    def fail_timed_out_jobs(self, heartbeat_timeout_seconds=300, default_timeout_seconds=900):
        """
        Fail PROCESSING jobs that exceeded their own timeout_seconds while
        their worker is still alive (heartbeating) — a runaway job, not a
        crash. The row goes terminal so the user gets resolution and no
        retry storm starts; the zombie worker's eventual complete/fail is
        fenced out by the PROCESSING-status guard.

        Returns:
            int: Number of jobs failed
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE BACKGROUND_JOBS
                    SET
                        status = 'FAILED',
                        completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Job exceeded its timeout ('
                            || COALESCE(timeout_seconds, %s)::text || 's) while still running'
                    WHERE status = 'PROCESSING'
                      AND started_at < CURRENT_TIMESTAMP
                          - make_interval(secs => COALESCE(timeout_seconds, %s))
                      AND COALESCE(heartbeat_at, started_at)
                          >= CURRENT_TIMESTAMP - make_interval(secs => %s)
                    RETURNING id
                """, (default_timeout_seconds, default_timeout_seconds,
                      heartbeat_timeout_seconds))

                failed_ids = [row[0] for row in cursor.fetchall()]

            if failed_ids:
                logging.warning(f"Failed {len(failed_ids)} timed-out jobs: {failed_ids}")

            return len(failed_ids)
        except Exception as e:
            logging.error(f"Failed to fail timed-out jobs: {e}", exc_info=True)
            return 0

    @log_db_call
    def get_user_jobs(self, user_id, limit=50):
        """Get recent jobs for a user (for admin/debugging)."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT id, job_type, status, priority, created_at, completed_at, error_message
                    FROM BACKGROUND_JOBS
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get user jobs: {e}", exc_info=True)
            return []

    @log_db_call
    def get_jobs(self, job_type=None, status=None, limit=50):
        """
        List background jobs with optional filtering.
        
        Args:
            job_type: Filter by 'job_type' column
            status: Filter by 'status' column
            limit: Max rows to return
            
        Returns:
            List of job dictionaries
        """
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                query = "SELECT * FROM BACKGROUND_JOBS WHERE 1=1"
                params = []

                if job_type:
                    query += " AND job_type = %s"
                    params.append(job_type)

                if status:
                    query += " AND status = %s"
                    params.append(status)

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, tuple(params))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to list jobs: {e}", exc_info=True)
            return []

    @log_db_call
    def get_queue_stats(self):
        """Get job queue statistics (for monitoring)."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT
                        status,
                        COUNT(*) as count,
                        AVG(CASE WHEN processing_time_ms IS NOT NULL THEN processing_time_ms ELSE NULL END) as avg_processing_ms
                    FROM BACKGROUND_JOBS
                    WHERE created_at > CURRENT_TIMESTAMP -  INTERVAL '24 hours'
                    GROUP BY status
                """)
                rows = cursor.fetchall()

            stats = {row['status']: {'count': row['count'], 'avg_ms': row['avg_processing_ms']} for row in rows}
            return stats
        except Exception as e:
            logging.error(f"Failed to get queue stats: {e}", exc_info=True)
            return {}

    @log_db_call
    def update_job_progress(self, job_id, progress_value, progress_message=None, worker_id=None):
        """
        Update job progress for real-time UI feedback.

        Progress writes double as heartbeats, and are fenced like the
        terminal transitions: an evicted worker must not mutate the payload
        of a job that has been reclaimed.

        Args:
            job_id: Job UUID
            progress_value: Float 0.0-1.0
            progress_message: Optional status message
            worker_id: When given, only applies if this worker still owns the job.
        """
        try:
            with self._connection_cursor() as cursor:
                # Update progress in payload JSONB field
                if progress_message:
                    cursor.execute(f"""
                        UPDATE BACKGROUND_JOBS
                        SET payload = jsonb_set(
                            jsonb_set(payload, '{{progress_value}}', %(value)s::jsonb),
                            '{{progress_message}}', %(message)s::jsonb
                        ),
                        heartbeat_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                        WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                    """, {'value': json.dumps(progress_value),
                          'message': json.dumps(progress_message),
                          'job_id': job_id, 'worker_id': worker_id})
                else:
                    cursor.execute(f"""
                        UPDATE BACKGROUND_JOBS
                        SET payload = jsonb_set(payload, '{{progress_value}}', %(value)s::jsonb),
                            heartbeat_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                    """, {'value': json.dumps(progress_value),
                          'job_id': job_id, 'worker_id': worker_id})
        except Exception as e:
            logging.error(f"Failed to update job progress: {e}", exc_info=True)
