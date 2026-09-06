"""
Background Job Manager

Queues and polls database-backed background jobs (simulation runs, PDF
generation, strategy evaluation). Jobs are stored in the BACKGROUND_JOBS
table and executed by services/background_worker.py; the UI (or any other
client) polls job status by ID.

This module is framework-free: the caller supplies the acting user where
attribution is wanted.

Note: the old in-process thread/process registry that lived here (session-
state backed, with poll_all_processes/start_ui_regeneration) was dead code
from the pre-database-queue era and has been removed. The UI-regeneration
thread bookkeeping lives inline in ui/my_simulations.py until the phase-2
rewrite.
"""

import logging
from typing import Any, Dict, Optional


class BackgroundManager:
    """Queue background jobs in the database and poll their status."""

    @staticmethod
    def _resolve_user_id(user: Optional[Dict[str, Any]]) -> Optional[int]:
        """Resolve a user dict ({'email': ..., 'name': ...}) to a DB user id."""
        if not user:
            return None
        user_email = user.get('email')
        if not user_email:
            return None
        from db.database import db
        return db.get_or_create_user_id(user_email, user.get('name'))

    @staticmethod
    def start_simulation(params: dict, user: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Queue a simulation job in the database.

        Args:
            params: Simulation parameters dictionary
            user: Acting user dict with 'email'/'name' for job attribution
                  (None for anonymous)

        Returns:
            Job ID if queued, None if already queued
        """
        from core.shared_logic import generate_simulation_hash
        from db.database import db

        simulation_hash = generate_simulation_hash(params)
        idempotency_key = f"sim_{simulation_hash}"

        # Check if job already exists and is pending/processing
        existing_job = db.get_job_by_idempotency_key(idempotency_key)
        if existing_job and existing_job['status'] in ['PENDING', 'PROCESSING']:
            logging.info(f"Simulation job already queued: {existing_job['id']}")
            return str(existing_job['id'])

        user_id = BackgroundManager._resolve_user_id(user)

        # Queue job in database
        job_id = db.create_background_job(
            job_type='simulation_run',
            payload={
                'simulation_hash': simulation_hash,
                'params': params  # Full params for worker
            },
            user_id=user_id,
            priority=6,  # Medium-high priority (user waiting)
            idempotency_key=idempotency_key,
            max_retries=2,  # Simulations less likely to benefit from retries
            timeout_seconds=1800  # 30 minutes for complex simulations
        )

        if job_id:
            logging.info(f"✅ Queued simulation job {job_id} for hash {simulation_hash[:10]}")

        return job_id

    @staticmethod
    def start_pdf_generation(history_id: int, user: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Queue a PDF generation job in the database.

        Args:
            history_id: Database history ID
            user: Acting user dict with 'email'/'name' for job attribution
                  (None for anonymous)

        Returns:
            Job ID if queued, None if already queued
        """
        logging.info(f"[BG_MGR] start_pdf_generation ENTRY: history_id={history_id}")
        from db.database import db

        idempotency_key = f"pdf_gen_{history_id}"
        logging.info(f"[BG_MGR] Checking for existing job with key={idempotency_key}")

        # Check if PDF job already exists and is pending/processing
        existing_job = db.get_job_by_idempotency_key(idempotency_key)
        logging.info(f"[BG_MGR] Existing job: {existing_job}")

        if existing_job:
            status = existing_job['status']
            logging.info(f"[BG_MGR] Found existing job {existing_job['id']} with status={status}")

            if status in ['PENDING', 'PROCESSING']:
                logging.info(f"[BG_MGR] Job already active, returning existing ID")
                return str(existing_job['id'])
            elif status == 'FAILED':
                # Reset failed job for retry
                logging.info(f"[BG_MGR] Resetting FAILED job {existing_job['id']} to PENDING")
                db.update_job_status(existing_job['id'], 'PENDING', error_message=None)
                logging.info(f"[BG_MGR] Reset complete, returning job ID")
                return str(existing_job['id'])

        user_id = BackgroundManager._resolve_user_id(user)
        logging.info(f"[BG_MGR] Resolved user_id={user_id}")

        # Queue job in database
        logging.info(f"[BG_MGR] Creating new job: history_id={history_id}, user_id={user_id}, priority=8")
        # Worker will fetch data from database using history_id
        try:
            job_id = db.create_background_job(
                job_type='pdf_generation',
                payload={
                    'history_id': history_id
                    # Worker fetches results and package from DB - no need to pass large data
                },
                user_id=user_id,
                priority=8,  # High priority - user is waiting for download
                idempotency_key=idempotency_key,
                max_retries=3,  # PDF generation can benefit from retries
                timeout_seconds=600  # 10 minutes for PDF generation
            )

            logging.info(f"✅ [BG_MGR] Queued PDF generation job {job_id} for history {history_id}")

            return job_id
        except Exception as e:
            logging.error(f"[BG_MGR] EXCEPTION creating job: {e}", exc_info=True)
            return None

    # ===== Job Status Polling (Database-Backed) =====

    @staticmethod
    def poll_job_status(job_id: str) -> dict:
        """
        Poll database for job status.

        Args:
            job_id: Job UUID from start_simulation() or start_pdf_generation()

        Returns:
            dict with status info:
                - status: PENDING | PROCESSING | COMPLETED | FAILED
                - progress: 0.0-1.0 (optional)
                - result: Result data (if COMPLETED)
                - error: Error message (if FAILED)
        """
        from db.database import db

        if not job_id:
            return {'status': 'NOT_FOUND', 'error': 'No job ID provided'}

        job = db.get_job_by_id(job_id)
        if not job:
            return {'status': 'NOT_FOUND', 'error': f'Job {job_id} not found'}

        response = {
            'status': job['status'],
            'job_type': job.get('job_type'),
        }

        # Add progress if available in payload
        payload = job.get('payload', {}) or {}
        if 'progress' in payload:
            response['progress'] = payload['progress']

        if job['status'] == 'COMPLETED':
            response['result'] = job.get('result') or {}
            response['processing_time_ms'] = job.get('processing_time_ms')
        elif job['status'] == 'FAILED':
            response['error'] = job.get('error_message')
            response['retry_count'] = job.get('retry_count')
        elif job['status'] == 'PROCESSING':
            response['started_at'] = job.get('started_at')
            response['worker_id'] = job.get('worker_id')

        return response

    @staticmethod
    def start_strategy_evaluation(
        strategy_class: str = None,
        strategy_name: str = None,
        params: dict = None,
        is_custom: bool = False,
        user_id: int = None,
        custom_strategy_id: int = None,
        code: str = None,
        class_name: str = None,
        git_commit_sha: str = None
    ) -> Optional[str]:
        """
        Start a strategy evaluation job in the worker queue.

        Supports both built-in and custom strategies using a discriminated union payload.

        Args:
            strategy_class: Class name for built-in strategies (e.g., 'TrinityStrategy')
            strategy_name: Display name for the strategy
            params: Optional strategy parameters
            is_custom: True for custom strategies
            user_id: User ID for custom strategies
            custom_strategy_id: Custom strategy database ID
            code: Strategy code for custom strategies
            class_name: Class name to extract from code

        Returns:
            Job ID if created, None if failed
        """
        from db.database import db

        logging.info(f"[BG_MGR] start_strategy_evaluation ENTRY")
        logging.info(f"  strategy_name={strategy_name}, is_custom={is_custom}")

        # Build payload based on type
        if is_custom:
            if not all([code, class_name, user_id is not None]):
                logging.error("Custom strategy requires: code, class_name, user_id")
                return None

            payload = {
                'type': 'custom',
                'strategy_name': strategy_name,
                'user_id': user_id,
                'custom_strategy_id': custom_strategy_id,
                'code': code,
                'class_name': class_name,
                'git_commit_sha': git_commit_sha,
                'params': params or {}
            }
        else:
            if not strategy_class:
                logging.error("Built-in strategy requires: strategy_class")
                return None

            payload = {
                'type': 'builtin',
                'strategy_class': strategy_class,
                'strategy_name': strategy_name or strategy_class,
                'params': params or {}
            }

        # Create job in database
        job_id = db.create_background_job(
            job_type='strategy_evaluation',
            payload=payload,
            priority=5  # Normal priority
        )

        if job_id:
            logging.info(f"[BG_MGR] Created strategy evaluation job: {job_id}")
            return job_id
        else:
            logging.error(f"[BG_MGR] Failed to create job")
            return None

    @staticmethod
    def list_jobs(job_type: str = None, status: str = None, limit: int = 50) -> list:
        """
        List background jobs from the database.

        Args:
            job_type: Filter by job type (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)

        Returns:
            List of job dicts
        """
        from db.database import db
        return db.get_jobs(job_type=job_type, status=status, limit=limit)
