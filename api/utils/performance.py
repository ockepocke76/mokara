"""
Performance timing utilities for diagnosing slowness in cloud deployments.

Enhanced with Google Cloud Monitoring integration and specialized trackers.

Usage:
    from utils.performance import log_timing, TimingContext, PageLoadTracker
    
    # Decorator usage
    @log_timing("my_function")
    def my_function():
        ...
    
    # Context manager usage
    with TimingContext("operation_name"):
        ...
    
    # Page-level tracking with auto-export
    with PageLoadTracker("Dashboard"):
        render_dashboard()
"""

import time
import logging
import os
from functools import wraps
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Lazy load config to avoid circular imports
_perf_enabled_cache = None
_memory_tracking_enabled = None

# Optional callable returning {'user_type': ..., 'user_id': ...} for metric
# labels. The UI registers one that reads its session; background processes
# and CLI runs leave it unset and report 'unknown'.
_user_context_provider = None


def set_user_context_provider(provider) -> None:
    """Register a zero-arg callable supplying user labels for metrics."""
    global _user_context_provider
    _user_context_provider = provider


def _is_perf_enabled():
    """Check if performance logging is enabled via config."""
    global _perf_enabled_cache
    if _perf_enabled_cache is None:
        try:
            from core.config_manager import CONFIG
            _perf_enabled_cache = CONFIG.get('admin.enable_performance_logging', False)
        except Exception:
            # Default to disabled if config can't be loaded
            _perf_enabled_cache = False
    return _perf_enabled_cache


def _is_memory_tracking_enabled():
    """Check if memory tracking is enabled."""
    global _memory_tracking_enabled
    if _memory_tracking_enabled is None:
        try:
            from core.config_manager import CONFIG
            _memory_tracking_enabled = CONFIG.get('monitoring.enable_memory_tracking', False)
        except Exception:
            _memory_tracking_enabled = False
    return _memory_tracking_enabled


def _get_memory_usage() -> Optional[float]:
    """Get current process memory usage in MB."""
    if not _is_memory_tracking_enabled():
        return None
    
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Failed to get memory usage: {e}")
        return None


def _export_to_cloud_monitoring(metric_type: str, value: float, labels: Optional[Dict[str, str]] = None):
    """Export metric to Cloud Monitoring if enabled."""
    try:
        from monitoring.cloud_monitoring import export_metric
        export_metric(metric_type, value, labels)
    except Exception as e:
        logger.debug(f"Failed to export metric to Cloud Monitoring: {e}")


def _get_user_context() -> Dict[str, str]:
    """Get current user context for metric labels via the registered provider."""
    if _user_context_provider is not None:
        try:
            return _user_context_provider()
        except Exception:
            pass
    return {'user_type': 'unknown', 'user_id': 'unknown'}


def log_timing(operation_name: str, log_level: int = logging.INFO):
    """
    Decorator to log execution time of a function.
    
    Args:
        operation_name: Name to identify this operation in logs
        log_level: Logging level (default: INFO)
    
    Example:
        @log_timing("database_query")
        def get_user_data():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            start_mem = _get_memory_usage()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                # Log to console
                log_msg = f"PERF_TIMING: {operation_name}: {elapsed:.3f}s"
                if start_mem is not None:
                    end_mem = _get_memory_usage()
                    mem_delta = end_mem - start_mem if end_mem else 0
                    log_msg += f" (mem: {mem_delta:+.1f}MB)"
                
                logger.log(log_level, log_msg)
                
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.log(log_level, f"PERF_TIMING: {operation_name}: {elapsed:.3f}s (FAILED: {e})")
                raise
        return wrapper
    return decorator


@contextmanager
def TimingContext(operation_name: str, log_level: int = logging.INFO, log_start: bool = False,
                 export_to_cloud: bool = False, metric_type: Optional[str] = None,
                 labels: Optional[Dict[str, str]] = None):
    """
    Context manager to log execution time of a code block.
    
    Args:
        operation_name: Name to identify this operation in logs
        log_level: Logging level (default: INFO)
        log_start: If True, log when operation starts
        export_to_cloud: If True, export timing to Cloud Monitoring
        metric_type: Cloud Monitoring metric type (e.g., "component_render_time")
        labels: Additional labels for Cloud Monitoring
    
    Example:
        with TimingContext("render_tab"):
            render_expensive_content()
    """
    if log_start:
        logger.log(log_level, f"PERF_TIMING: START: {operation_name}")
    
    start_time = time.time()
    start_mem = _get_memory_usage()
    
    try:
        yield
        elapsed = time.time() - start_time
        elapsed_ms = elapsed * 1000
        
        # Log to console
        log_msg = f"PERF_TIMING: {operation_name}: {elapsed:.3f}s"
        if start_mem is not None:
            end_mem = _get_memory_usage()
            mem_delta = end_mem - start_mem if end_mem else 0
            log_msg += f" (mem: {mem_delta:+.1f}MB)"
        
        logger.log(log_level, log_msg)
        
        # Export to Cloud Monitoring if requested
        if export_to_cloud and metric_type:
            export_labels = labels or {}
            export_labels['operation'] = operation_name
            _export_to_cloud_monitoring(metric_type, elapsed_ms, export_labels)
            
    except Exception as e:
        elapsed = time.time() - start_time
        logger.log(log_level, f"PERF_TIMING: {operation_name}: {elapsed:.3f}s (FAILED: {e})")
        raise


@contextmanager
def PageLoadTracker(page_name: str, log_level: int = logging.INFO):
    """
    Specialized tracker for full page load timing.
    Automatically exports to Cloud Monitoring.
    
    Args:
        page_name: Name of the page being loaded
        log_level: Logging level
    
    Example:
        with PageLoadTracker("Dashboard"):
            render_dashboard_content()
    """
    start_time = time.time()
    logger.log(log_level, f"PERF_TIMING: PAGE_LOAD START: {page_name}")

    try:
        yield
        
        elapsed = time.time() - start_time
        elapsed_ms = elapsed * 1000
        
        logger.log(log_level, f"PERF_TIMING: PAGE_LOAD: {page_name}: {elapsed:.3f}s")
        
        # Always export page load metrics to Cloud Monitoring
        labels = _get_user_context()
        labels['page'] = page_name
        _export_to_cloud_monitoring('page_load_time', elapsed_ms, labels)
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.log(log_level, f"PERF_TIMING: PAGE_LOAD: {page_name}: {elapsed:.3f}s (FAILED: {e})")
        raise


@contextmanager
def DatabaseQueryTracker(operation_name: str, query_type: Optional[str] = None):
    """
    Specialized tracker for database queries.
    
    Args:
        operation_name: Name of the database operation
        query_type: Type of query (SELECT, INSERT, UPDATE, DELETE)
    
    Example:
        with DatabaseQueryTracker("get_user_simulations", "SELECT"):
            results = cursor.execute(query)
    """
    start_time = time.time()
    
    try:
        yield
        elapsed = time.time() - start_time
        elapsed_ms = elapsed * 1000
        
        logger.info(f"PERF_TIMING: DB_QUERY: {operation_name}: {elapsed:.3f}s")
        
        # Export to Cloud Monitoring
        labels = {'operation': operation_name}
        if query_type:
            labels['query_type'] = query_type
        _export_to_cloud_monitoring('db_query_time', elapsed_ms, labels)
        
        # Log slow queries
        try:
            from core.config_manager import CONFIG
            slow_threshold = CONFIG.get('monitoring.slow_query_threshold', 1.0)
            if elapsed > slow_threshold:
                logger.warning(f"SLOW_QUERY: {operation_name} took {elapsed:.3f}s (threshold: {slow_threshold}s)")
        except Exception:
            pass
            
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"PERF_TIMING: DB_QUERY: {operation_name}: {elapsed:.3f}s (FAILED: {e})")
        raise


@contextmanager
def ComponentRenderTracker(component_name: str):
    """
    Specialized tracker for Streamlit component rendering.
    
    Args:
        component_name: Name of the component being rendered
    
    Example:
        with ComponentRenderTracker("simulation_card"):
            st.plotly_chart(fig)
    """
    start_time = time.time()
    
    try:
        yield
        elapsed = time.time() - start_time
        elapsed_ms = elapsed * 1000
        
        if _is_perf_enabled():
            logger.debug(f"PERF_TIMING: COMPONENT: {component_name}: {elapsed:.3f}s")
        
        # Export to Cloud Monitoring
        labels = {'component': component_name}
        labels.update(_get_user_context())
        _export_to_cloud_monitoring('component_render_time', elapsed_ms, labels)
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.debug(f"PERF_TIMING: COMPONENT: {component_name}: {elapsed:.3f}s (FAILED: {e})")
        raise


class PerformanceTracker:
    """
    Track multiple timing checkpoints for complex operations.
    
    Example:
        tracker = PerformanceTracker("page_load")
        tracker.checkpoint("imports")
        # ... do work ...
        tracker.checkpoint("database")
        # ... do work ...
        tracker.log_summary()
    """
    
    def __init__(self, operation_name: str, export_checkpoints: bool = False):
        self.operation_name = operation_name
        self.start_time = time.time()
        self.checkpoints = []
        self.last_checkpoint = self.start_time
        self.export_checkpoints = export_checkpoints
    
    def checkpoint(self, name: str):
        """Record a checkpoint with elapsed time since last checkpoint."""
        now = time.time()
        elapsed_from_last = now - self.last_checkpoint
        total_elapsed = now - self.start_time
        
        self.checkpoints.append({
            'name': name,
            'elapsed_from_last': elapsed_from_last,
            'total_elapsed': total_elapsed
        })
        self.last_checkpoint = now
        
        logger.info(f"PERF_TIMING: {self.operation_name}.{name}: +{elapsed_from_last:.3f}s (total: {total_elapsed:.3f}s)")
        
        # Optionally export each checkpoint
        if self.export_checkpoints:
            labels = {'operation': self.operation_name, 'checkpoint': name}
            _export_to_cloud_monitoring('component_render_time', elapsed_from_last * 1000, labels)
    
    def log_summary(self):
        """Log a summary of all checkpoints."""
        total = time.time() - self.start_time
        logger.info(f"PERF_TIMING: {self.operation_name} SUMMARY: {total:.3f}s total")
        
        if self.checkpoints:
            for cp in self.checkpoints:
                pct = (cp['elapsed_from_last'] / total * 100) if total > 0 else 0
                logger.info(f"PERF_TIMING:   └─ {cp['name']}: {cp['elapsed_from_last']:.3f}s ({pct:.1f}%)")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.log_summary()
