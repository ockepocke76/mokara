"""
Background Job Worker Service

Processes jobs from the BACKGROUND_JOBS table with:
- Retry logic with exponential backoff
- Graceful shutdown handling (SIGTERM)
- Stale job recovery
- Production-ready error handling

Works in both local development and production (Cloud Run).
"""

import logging
import time
import os
import signal
import sys
import threading
from typing import Optional, Dict, Any

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle SIGTERM from Cloud Run gracefully."""
    global shutdown_requested
    logging.info(f"⚠️  Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True

# Signal handlers are registered in run_worker(), not at import time:
# multiprocessing's spawn children re-import this module (via worker.py as
# __main__), and an import-time SIGTERM handler would make the sandbox
# validation subprocess ignore terminate().


class JobWorker:
    """
    Processes background jobs from database queue.
    
    Features:
    - Fetch jobs using FOR UPDATE SKIP LOCKED (concurrent worker safety)
    - Retry failed jobs with exponential backoff
    - Graceful shutdown (finishes current job before exiting)
    - Timeout detection and recovery
    """
    
    def __init__(self, worker_id: str = None):
        self.worker_id = worker_id or f"worker_{os.getpid()}"
        self.current_job_id = None
        logging.info(f"🔧 Worker initialized: {self.worker_id}")
    
    def run(self):
        """Main worker loop."""
        from db.database import db
        
        logging.info(f"🚀 Worker {self.worker_id} started")
        
        while not shutdown_requested:
            try:
                # 1. Fetch and lock next job
                job = db.fetch_and_lock_job(self.worker_id)
                
                if not job:
                    # No work available - sleep and retry
                    time.sleep(2)
                    continue
                
                self.current_job_id = str(job['id'])
                logging.info(f"📦 Processing job {job['id']}: {job['job_type']}")
                
                # 2. Process job
                start_time = time.time()
                try:
                    result = self._process_job(job)
                    elapsed = time.time() - start_time
                    db.complete_job(job['id'], result)
                    logging.info(f"✅ Job {job['id']} completed in {elapsed:.2f}s")
                
                except Exception as e:
                    elapsed = time.time() - start_time
                    logging.error(f"❌ Job {job['id']} failed after {elapsed:.2f}s: {e}", exc_info=True)
                    self._handle_failure(job, str(e))
                
                finally:
                    self.current_job_id = None
            
            except Exception as e:
                logging.error(f"Worker loop error: {e}", exc_info=True)
                time.sleep(5)  # Back off on unexpected errors
        
        logging.info(f"👋 Worker {self.worker_id} shutting down gracefully")
    
    def _process_job(self, job: Dict) -> Any:
        """Route job to appropriate handler based on job_type."""
        job_type = job['job_type']
        payload = job['payload']
        
        handlers = {
            'pdf_generation': self._process_pdf_generation,
            'strategy_evaluation': self._process_strategy_evaluation,
            'simulation_run': self._process_simulation_run,
        }
        
        handler = handlers.get(job_type)
        if not handler:
            raise ValueError(f"Unknown job type: {job_type}")
        
        return handler(job['id'], payload)
    
    def _process_pdf_generation(self, job_id: str, payload: Dict) -> Dict:
        """Generate PDF from simulation results."""
        from db.database import db
        from db.pdf_storage import get_pdf_storage
        from background_tasks import _generate_pdf_for_simulation
        import time

        start_time = time.time()
        history_id = payload['history_id']
        logging.info(f"📄 Generating PDF for history_id={history_id}")
        
        # 1. Resolve history_id -> simulation_hash
        try:
            conn = db.get_connection()
            cursor = db._get_cursor(conn)
            cursor.execute("SELECT simulation_hash FROM USER_SIMULATION_HISTORY WHERE id = %s", (history_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"History ID {history_id} not found")
            simulation_hash = row[0]
        finally:
            if 'conn' in locals():
                db.release_connection(conn)
                
        logging.info(f"Resolved history_id {history_id} -> hash {simulation_hash[:10]}")

        try:
            # 2. Generate PDF (returns BytesIO buffer)
            pdf_buffer = _generate_pdf_for_simulation(simulation_hash)
            if not pdf_buffer:
                raise RuntimeError("PDF generation returned None")

            # 3. Save PDF via the storage backend (local pdf_cache/ in dev, GCS in prod)
            pdf_path = get_pdf_storage().save_pdf(simulation_hash, pdf_buffer)
        except Exception as e:
            # The job row gets its own failure handling upstream, but the
            # simulation row is what the UI polls — without this it stays
            # 'pending' forever.
            db.update_simulation_pdf_storage(
                simulation_hash=simulation_hash,
                storage_path=None,
                status='failed',
                gen_time_ms=int((time.time() - start_time) * 1000),
                error_msg=str(e)[:500],
            )
            raise

        logging.info(f"💾 Saved PDF to {pdf_path}")
        
        # 4. Calculate generation time
        gen_time_ms = int((time.time() - start_time) * 1000)
        
        # 5. Update database with PDF path and status
        db.update_simulation_pdf_storage(
            simulation_hash=simulation_hash,
            storage_path=pdf_path,
            status='ready',
            gen_time_ms=gen_time_ms,
            error_msg=None
        )
        
        logging.info(f"✅ PDF generated in {gen_time_ms}ms for {simulation_hash[:10]}")
        
        return {
            'simulation_hash': simulation_hash,
            'history_id': history_id,
            'success': True,
            'generation_time_ms': gen_time_ms,
            'pdf_path': pdf_path
        }
    
    def _process_strategy_evaluation(self, job_id: str, payload: Dict) -> Dict:
        """Run strategy evaluation across market scenarios."""
        from core.strategy_evaluation import evaluate_strategy
        from db.database import db
        
        strategy_type = payload.get('type', 'builtin')  # Default to builtin for backward compat
        strategy_name = payload.get('strategy_name', 'Unknown')
        
        logging.info(f"📊 Evaluating {strategy_type} strategy: {strategy_name}")
        
        # Get strategy class based on type
        if strategy_type == 'custom':
            # Load custom strategy from code
            logging.info(f"  Loading custom strategy code...")
            
            code = payload.get('code')
            class_name = payload.get('class_name')
            user_id = payload.get('user_id')
            
            if not all([code, class_name]):
                raise ValueError("Custom strategy requires 'code' and 'class_name'")
            
            # Execute strategy code in sandbox
            from core.sandbox import execute_strategy_code
            strategy_class = execute_strategy_code(code, class_name)
            logging.info(f"  ✓ Loaded custom class: {class_name}")
            
            # Prepare eval_params with custom strategy metadata
            eval_params = payload.get('params', {})
            
        else:
            # Built-in strategy
            strategy_class_name = payload.get('strategy_class')
            if not strategy_class_name:
                raise ValueError("Built-in strategy requires 'strategy_class'")
            
            logging.info(f"  Loading built-in strategy: {strategy_class_name}")
            
            # Dynamically import strategy class
            from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
            from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy
            
            strategy_map = {
                'TrinityStrategy': TrinityStrategy,
                'BuyBorrowDieStrategy': BuyBorrowDieStrategy,
                'GetRichStayRichStrategy': GetRichStayRichStrategy,
            }
            
            strategy_class = strategy_map.get(strategy_class_name)
            if not strategy_class:
                raise ValueError(f"Unknown strategy class: {strategy_class_name}")
            
            eval_params = payload.get('params', {})
        
        # Run evaluation
        logging.info(f"  Running evaluation across 8 scenarios...")
        result = evaluate_strategy(strategy_class, strategy_name, eval_params)
        
        # Add custom strategy metadata if applicable
        if strategy_type == 'custom':
            result['user_id'] = payload.get('user_id')
            result['is_custom'] = True
            result['custom_strategy_id'] = payload.get('custom_strategy_id')
            result['git_commit_sha'] = payload.get('git_commit_sha')
        
        # Save to database
        success = db.save_strategy_evaluation(result)
        
        if success:
            logging.info(f"✅ Strategy evaluation complete: {strategy_name}")
            logging.info(f"   Excellence Score: {result.get('excellence_score'):.2f}")
            logging.info(f"   Category: {result.get('strategy_category')}")
        else:
            logging.error(f"❌ Failed to save evaluation to database")
        
        return {
            'success': success,
            'excellence_score': result.get('excellence_score'),
            'strategy_category': result.get('strategy_category'),
            'strategy_name': strategy_name
        }
    
    def _process_simulation_run(self, job_id: str, payload: Dict) -> Dict:
        """
        Execute simulation with progress tracking.
        
        This is the critical handler that enables real-time progress bars in the UI.
        """
        from db.database import db
        from background_tasks import run_and_save_simulation
        
        # Extract parameters from payload
        full_sim_params = payload['params']  # Full simulation parameters
        simulation_hash = payload['simulation_hash']
        ui_params = payload.get('ui_params', {})  # UI parameters (may be empty)
        
        logging.info(f"🎲 Running simulation: {simulation_hash[:10]}")
        
        # Progress callback for UI updates
        def update_progress(progress: float, message: str = None):
            """Called by simulation code to report progress (0.0-1.0)."""
            try:
                db.update_job_progress(job_id, progress, message)
            except Exception as e:
                logging.warning(f"Failed to update progress: {e}")
        
        # Run simulation with correct parameter names
        try:
            # Note: run_and_save_simulation expects: ui_params, full_sim_params, simulation_hash
            # The function handles its own database saving. It swallows its
            # own exceptions and reports failure through the return value —
            # ignoring it would mark a failed simulation's job as successful.
            success, _ = run_and_save_simulation(
                ui_params=ui_params,
                full_sim_params=full_sim_params,
                simulation_hash=simulation_hash,
                progress_queue=None  # We use callback instead
            )
            if not success:
                raise RuntimeError(
                    f"Simulation failed for {simulation_hash[:10]} "
                    "(see simulation logs for the cause)")

            logging.info(f"✅ Simulation complete: {simulation_hash[:10]}")
            
            return {
                'success': True,
                'simulation_hash': simulation_hash,
                'completed': True
            }
        
        except Exception as e:
            logging.error(f"Simulation execution failed: {e}", exc_info=True)
            raise
    
    def _handle_failure(self, job: Dict, error_message: str):
        """Handle job failure with retry logic."""
        from db.database import db
        
        job_id = str(job['id'])
        retry_count = job['retry_count']
        max_retries = job['max_retries']
        
        if retry_count < max_retries:
            # Calculate exponential backoff
            # Retry 1: 10s, Retry 2: 40s, Retry 3: 90s
            backoff_seconds = min(2 ** (retry_count + 1) * 10, 300)
            scheduled_at = time.time() + backoff_seconds
            
            db.retry_job(job_id, error_message, scheduled_at)
            logging.warning(
                f"🔄 Job {job_id} will retry in {backoff_seconds}s "
                f"(attempt {retry_count + 1}/{max_retries})"
            )
        else:
            # Max retries exceeded - permanently failed
            db.fail_job(job_id, error_message)
            logging.error(
                f"💀 Job {job_id} failed permanently after {max_retries} retries"
            )


def cleanup_stale_jobs():
    """
    Recovery function to reset jobs stuck in PROCESSING for too long.
    
    This handles:
    - Crashed workers (process died mid-job)
    - Timeouts (job taking too long)
    - Cloud Run instance evictions
    
    Should be run periodically in a background thread.
    """
    from db.database import db
    
    timeout_threshold = 900  # 15 minutes default
    recovered = db.reset_stale_jobs(timeout_threshold)
    
    if recovered > 0:
        logging.warning(
            f"🔧 Recovered {recovered} stale jobs "
            f"(timeout: {timeout_threshold}s)"
        )


def run_worker():
    """Main entry point for worker service."""
    from logger import configure_logging
    configure_logging()

    # Schema readiness, once per worker start (advisory-locked; replaces the
    # old per-simulation-job run_migrations call). A failed migration must
    # stop the worker, not let it process jobs against a broken schema.
    from db.database import db
    db.run_migrations()

    # Graceful-shutdown signals, only for the real worker process.
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logging.info("=" * 60)
    logging.info("Background Worker Service Starting")
    logging.info("=" * 60)
    
    # Create worker
    worker = JobWorker()
    
    # Start cleanup thread
    def cleanup_loop():
        while not shutdown_requested:
            try:
                cleanup_stale_jobs()
            except Exception as e:
                logging.error(f"Cleanup error: {e}", exc_info=True)
            
            # Sleep for 5 minutes
            for _ in range(300):
                if shutdown_requested:
                    break
                time.sleep(1)
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    logging.info("🧹 Stale job cleanup thread started")
    
    # Run worker (blocks until shutdown)
    try:
        worker.run()
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    
    logging.info("Worker service stopped")


if __name__ == "__main__":
    run_worker()
