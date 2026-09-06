"""
Services package for application-level services.

Contains business logic services like background process management,
separated from UI and data layers.
"""

from .background_manager import BackgroundManager

__all__ = ['BackgroundManager']
