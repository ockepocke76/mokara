"""
Performance monitoring and observability package.

Provides integration with Google Cloud Monitoring for production metrics.
"""

from .cloud_monitoring import get_monitoring_client, export_metric

__all__ = ['get_monitoring_client', 'export_metric']
