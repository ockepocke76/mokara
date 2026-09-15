"""Global system settings and counters.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import logging

from ..logging_utils import log_db_call


class SystemMixin:
    """Global system settings and counters. Mixed into PostgreSQLDatabase."""

    def get_system_setting(self, key, default=None):
        """Get a global system setting."""
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute("SELECT setting_value FROM SYSTEM_SETTINGS WHERE setting_key = %s", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            logging.error(f"Failed to get system setting '{key}': {e}")
            return default

    def set_system_setting(self, key, value):
        """Set a global system setting."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO SYSTEM_SETTINGS (setting_key, setting_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = CURRENT_TIMESTAMP
                """, (key, str(value)))
            return True
        except Exception as e:
            logging.error(f"Failed to set system setting '{key}': {e}")
            return False

    @log_db_call
    def increment_global_counter(self, metric_key, value=1):
        """
        Increment a global persistent counter.
        Creates the row if it doesn't exist (e.g., for new metrics).
        """
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO GLOBAL_STATS (metric_key, metric_value)
                    VALUES (%s, %s)
                    ON CONFLICT (metric_key)
                    DO UPDATE SET metric_value = GLOBAL_STATS.metric_value + EXCLUDED.metric_value
                """, (metric_key, value))
        except Exception as e:
            logging.error(f"Failed to increment global counter {metric_key}: {e}", exc_info=True)
