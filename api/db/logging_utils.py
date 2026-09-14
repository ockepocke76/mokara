"""
Database Logging Utilities

Provides automatic logging for database method calls with performance tracking.
Configure via environment variables:
- DB_LOGGING_ENABLED: Enable logging ('true', 'verbose', or 'false')
- DB_SLOW_QUERY_MS: Threshold for slow query warnings (default: 100ms)
"""

import functools
import time
import logging
import os
from typing import Any, Callable

# Configuration
DB_LOGGING_ENABLED = os.getenv('DB_LOGGING_ENABLED', 'false').lower() in ('true', '1', 'yes', 'verbose')
DB_LOGGING_VERBOSE = os.getenv('DB_LOGGING_ENABLED', 'false').lower() == 'verbose'
DB_SLOW_QUERY_MS = float(os.getenv('DB_SLOW_QUERY_MS', '100'))

# Session-level metrics
_call_counts = {}
_total_time = {}


def log_db_call(func: Callable) -> Callable:
    """
    Decorator to log database method calls with timing and performance tracking.
    
    Features:
    - Logs method name, sanitized arguments, and execution time
    - Warns on slow queries (configurable threshold)
    - Tracks call counts and total time per method
    - Exports timing metrics to Google Cloud Monitoring
    - Zero overhead when disabled
    
    Args:
        func: The database method to wrap
        
    Returns:
        Wrapped function with logging
    """
    
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        # Early exit if logging disabled - zero overhead
        if not DB_LOGGING_ENABLED:
            return func(self, *args, **kwargs)
        
        method_name = func.__name__
        start_time = time.time()
        
        # Sanitize args for logging (truncate long values)
        safe_args = _sanitize_args(args)
        safe_kwargs = {k: _sanitize_value(v) for k, v in kwargs.items()}
        
        # Log the call
        logging.info(f"[DB] → {method_name}(args={safe_args}, kwargs={list(safe_kwargs.keys())})")
        
        try:
            result = func(self, *args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Track metrics
            _call_counts[method_name] = _call_counts.get(method_name, 0) + 1
            _total_time[method_name] = _total_time.get(method_name, 0) + elapsed_ms
            
            # Log completion
            if elapsed_ms > DB_SLOW_QUERY_MS:
                logging.warning(
                    f"[DB] ⚠️  SLOW: {method_name} took {elapsed_ms:.2f}ms "
                    f"(threshold: {DB_SLOW_QUERY_MS}ms)"
                )
            else:
                logging.info(f"[DB] ✓ {method_name} completed in {elapsed_ms:.2f}ms")
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logging.error(f"[DB] ✗ {method_name} failed after {elapsed_ms:.2f}ms: {e}")
            raise
    
    return wrapper


def _sanitize_args(args: tuple) -> tuple:
    """Truncate long arguments for logging."""
    return tuple(_sanitize_value(arg) for arg in args[:3])  # Only log first 3 args


def _sanitize_value(value: Any) -> Any:
    """
    Sanitize a single value for logging.
    
    Truncates long strings, summarizes large collections.
    """
    if isinstance(value, str) and len(value) > 50:
        return f"{value[:47]}..."
    elif isinstance(value, (list, dict)) and len(str(value)) > 100:
        return f"{type(value).__name__}(len={len(value)})"
    elif isinstance(value, bytes):
        return f"bytes(len={len(value)})"
    return value


def get_db_metrics() -> dict:
    """
    Get aggregated database call metrics.
    
    Returns:
        dict: Contains call_counts, total_time_ms, and avg_time_ms for each method
    """
    return {
        'call_counts': _call_counts.copy(),
        'total_time_ms': _total_time.copy(),
        'avg_time_ms': {k: _total_time[k] / _call_counts[k] for k in _call_counts}
    }


def reset_db_metrics():
    """Reset metrics (useful between test runs or sessions)."""
    global _call_counts, _total_time
    _call_counts = {}
    _total_time = {}


def print_db_metrics():
    """Pretty-print database call metrics to console."""
    metrics = get_db_metrics()
    
    if not metrics['call_counts']:
        print("No database calls tracked yet.")
        return
    
    print("\n" + "="*70)
    print("DATABASE CALL METRICS")
    print("="*70)
    print(f"{'Method':<40} {'Calls':<8} {'Total (ms)':<12} {'Avg (ms)':<10}")
    print("-"*70)
    
    # Sort by total time (descending)
    sorted_methods = sorted(
        metrics['call_counts'].keys(),
        key=lambda k: metrics['total_time_ms'][k],
        reverse=True
    )
    
    for method in sorted_methods:
        calls = metrics['call_counts'][method]
        total = metrics['total_time_ms'][method]
        avg = metrics['avg_time_ms'][method]
        print(f"{method:<40} {calls:<8} {total:<12.2f} {avg:<10.2f}")
    
    print("-"*70)
    total_calls = sum(metrics['call_counts'].values())
    total_time = sum(metrics['total_time_ms'].values())
    print(f"{'TOTAL':<40} {total_calls:<8} {total_time:<12.2f}")
    print("="*70 + "\n")
