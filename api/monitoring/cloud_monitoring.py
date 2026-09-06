"""
Google Cloud Monitoring integration for performance metrics.

Exports custom metrics to Cloud Monitoring with batching and graceful fallback.
"""

import os
import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict
import queue

logger = logging.getLogger(__name__)

# Lazy imports to avoid crashes if GCP libraries not available
_monitoring_client = None
_client_lock = threading.Lock()
_metric_buffer = queue.Queue(maxsize=1000)
_flush_thread = None
_flush_interval = 60  # seconds
_is_enabled = None


def _is_monitoring_enabled() -> bool:
    """Check if Cloud Monitoring is enabled via config."""
    global _is_enabled
    if _is_enabled is None:
        try:
            from core.config_manager import CONFIG
            _is_enabled = CONFIG.get('monitoring.cloud_monitoring_enabled', True)
            
            # Also check if we're in production (Cloud Run)
            if not os.getenv('K_SERVICE'):
                # Local development - respect config or disable by default
                _is_enabled = CONFIG.get('monitoring.cloud_monitoring_enabled', False)
        except Exception:
            _is_enabled = False
    return _is_enabled


def get_project_id() -> Optional[str]:
    """Get Google Cloud project ID from environment or config."""
    # Try environment variable first
    project_id = os.getenv('GCP_MONITORING_PROJECT_ID') or os.getenv('GCP_PROJECT')
    
    if not project_id:
        try:
            from core.config_manager import CONFIG
            project_id = CONFIG.get('monitoring.cloud_monitoring_project_id')
        except Exception:
            pass
    
    return project_id


def get_monitoring_client():
    """
    Get or create the Cloud Monitoring client (singleton).
    
    Returns None if monitoring is disabled or unavailable.
    """
    global _monitoring_client
    
    if not _is_monitoring_enabled():
        return None
    
    with _client_lock:
        if _monitoring_client is None:
            try:
                from google.cloud import monitoring_v3
                
                project_id = get_project_id()
                if not project_id:
                    logger.warning("Cloud Monitoring enabled but no project ID configured")
                    return None
                
                _monitoring_client = monitoring_v3.MetricServiceClient()
                logger.info(f"Cloud Monitoring client initialized for project: {project_id}")
                
                # Start background flush thread
                _start_flush_thread()
                
            except ImportError:
                logger.warning("google-cloud-monitoring not installed, metrics export disabled")
                return None
            except Exception as e:
                logger.warning(f"Failed to initialize Cloud Monitoring: {e}")
                return None
        
        return _monitoring_client


def _create_metric_descriptor(client, project_id: str, metric_type: str, 
                              description: str, unit: str = "ms",
                              value_type: str = "DOUBLE",
                              metric_kind: str = "GAUGE") -> bool:
    """Create a custom metric descriptor if it doesn't exist."""
    try:
        from google.cloud import monitoring_v3
        from google.api_core import exceptions
        
        project_name = f"projects/{project_id}"
        descriptor = monitoring_v3.MetricDescriptor()
        descriptor.type = f"custom.googleapis.com/streamlit/{metric_type}"
        descriptor.metric_kind = getattr(monitoring_v3.MetricDescriptor.MetricKind, metric_kind)
        descriptor.value_type = getattr(monitoring_v3.MetricDescriptor.ValueType, value_type)
        descriptor.description = description
        descriptor.unit = unit
        
        try:
            client.create_metric_descriptor(name=project_name, metric_descriptor=descriptor)
            logger.info(f"Created metric descriptor: {metric_type}")
            return True
        except exceptions.AlreadyExists:
            # Already exists, that's fine
            return True
        except Exception as e:
            logger.error(f"Failed to create metric descriptor {metric_type}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating metric descriptor: {e}")
        return False


def ensure_metric_descriptors():
    """Ensure all required metric descriptors are created."""
    client = get_monitoring_client()
    if not client:
        return
    
    project_id = get_project_id()
    if not project_id:
        return
    
    # Define all custom metrics
    metrics = [
        ("page_load_time", "Time to fully render a Streamlit page", "ms", "DOUBLE", "GAUGE"),
        ("db_query_time", "Database query execution time", "ms", "DOUBLE", "GAUGE"),
        ("component_render_time", "Individual Streamlit component render time", "ms", "DOUBLE", "GAUGE"),
        ("cache_hit_rate", "Streamlit cache hit rate", "%", "DOUBLE", "GAUGE"),
        ("db_pool_utilization", "PostgreSQL connection pool utilization", "%", "DOUBLE", "GAUGE"),
    ]
    
    for metric_type, description, unit, value_type, metric_kind in metrics:
        _create_metric_descriptor(client, project_id, metric_type, description, unit, value_type, metric_kind)


def export_metric(metric_type: str, value: float, labels: Optional[Dict[str, str]] = None):
    """
    Export a metric to Cloud Monitoring (buffered).
    
    Args:
        metric_type: Type of metric (e.g., "page_load_time")
        value: Metric value
        labels: Optional labels/dimensions (e.g., {"page": "Dashboard", "user": "guest"})
    """
    if not _is_monitoring_enabled():
        return
    
    try:
        # Add to buffer for batched export
        _metric_buffer.put_nowait({
            'metric_type': metric_type,
            'value': value,
            'labels': labels or {},
            'timestamp': time.time()
        })
    except queue.Full:
        logger.warning("Metric buffer full, dropping metric")


def _flush_metrics():
    """Flush buffered metrics to Cloud Monitoring (batched)."""
    client = get_monitoring_client()
    if not client:
        return
    
    project_id = get_project_id()
    if not project_id:
        return
    
    try:
        from google.cloud import monitoring_v3
        
        # Collect all pending metrics
        metrics_to_send = []
        try:
            while True:
                metric = _metric_buffer.get_nowait()
                metrics_to_send.append(metric)
        except queue.Empty:
            pass
        
        if not metrics_to_send:
            return
        
        # Group by metric type for efficient sending
        grouped = defaultdict(list)
        for metric in metrics_to_send:
            grouped[metric['metric_type']].append(metric)
        
        # Send each group
        project_name = f"projects/{project_id}"
        
        for metric_type, metrics in grouped.items():
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"custom.googleapis.com/streamlit/{metric_type}"
            
            # Use first metric's labels (assume consistent within type)
            for key, value in metrics[0]['labels'].items():
                series.metric.labels[key] = str(value)
            
            # Add resource labels
            series.resource.type = "generic_task"
            series.resource.labels["project_id"] = project_id
            series.resource.labels["location"] = os.getenv("GCP_REGION", "us-central1")
            series.resource.labels["namespace"] = "streamlit"
            series.resource.labels["job"] = "btc_simulator"
            series.resource.labels["task_id"] = os.getenv("K_REVISION", "local")
            
            # Add data points (limit to 200 per request)
            for metric in metrics[:200]:
                point = monitoring_v3.Point()
                point.value.double_value = metric['value']
                point.interval.end_time.seconds = int(metric['timestamp'])
                series.points.append(point)
            
            # Send to Cloud Monitoring
            try:
                client.create_time_series(name=project_name, time_series=[series])
                logger.debug(f"Exported {len(metrics)} {metric_type} metrics to Cloud Monitoring")
            except Exception as e:
                logger.error(f"Failed to export {metric_type} metrics: {e}")
        
    except Exception as e:
        logger.error(f"Error flushing metrics: {e}", exc_info=True)


def _flush_worker():
    """Background worker that periodically flushes metrics."""
    global _flush_interval
    
    try:
        from core.config_manager import CONFIG
        _flush_interval = CONFIG.get('monitoring.metric_export_interval', 60)
    except Exception:
        pass
    
    while True:
        time.sleep(_flush_interval)
        try:
            _flush_metrics()
        except Exception as e:
            logger.error(f"Error in flush worker: {e}", exc_info=True)


def _start_flush_thread():
    """Start the background flush thread."""
    global _flush_thread
    
    if _flush_thread is None or not _flush_thread.is_alive():
        _flush_thread = threading.Thread(target=_flush_worker, daemon=True)
        _flush_thread.start()
        logger.info("Started Cloud Monitoring flush thread")


def force_flush():
    """Force an immediate flush of all buffered metrics."""
    _flush_metrics()


# Initialize on import if enabled
if _is_monitoring_enabled():
    get_monitoring_client()
    ensure_metric_descriptors()
