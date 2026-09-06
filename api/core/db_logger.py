import logging
import threading
from db.database import db

class DatabaseHandler(logging.Handler):
    """
    A custom logging handler that writes log records to a database table.
    It captures the current user's email from the Streamlit session state.
    Works with both SQLite and Snowflake backends via the db abstraction layer.
    
    IMPORTANT: Set to WARNING level to avoid performance issues from excessive writes.
    """
    def __init__(self, user_email=None):
        super().__init__()
        self.db = db
        self.user_email = user_email
        self._thread_local = threading.local()
        # Only log WARNING and above to avoid database lock contention
        self.setLevel(logging.WARNING)

    def emit(self, record):
        """
        Writes a log record to the database.
        """
        # --- Recursion Guard ---
        # Prevent infinite loops if logging occurs during the DB write (e.g. pool exhaustion)
        if getattr(self._thread_local, 'in_db_log', False):
            return

        # Prepare the log message and exception info
        log_message = self.format(record)
        exc_info = None
        if record.exc_info:
            exc_info = logging.Formatter().formatException(record.exc_info)

        conn = None # Ensure variable exists for finally block
        try:
            self._thread_local.in_db_log = True
            
            # Use the db abstraction layer which handles both SQLite and Snowflake
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO LOGS (level, logger_name, message, user_email, exception_details)
                   VALUES (?, ?, ?, ?, ?)""",
                (record.levelname, record.name, log_message, self.user_email, exc_info)
            )
            conn.commit()
        except Exception as e:
            # If logging to the DB fails, we print to stderr to avoid an infinite loop.
            # This is a critical fallback.
            import sys
            sys.stderr.write(f"---!!!--- FAILED TO WRITE LOG TO DATABASE ---!!!---\n")
            sys.stderr.write(f"Log Record: {record}\n")
            sys.stderr.write(f"Database Error: {e}\n")
            sys.stderr.write("---!!!--- END OF DB LOGGING ERROR ---!!!---\n")
        finally:
             if conn:
                 self.db.release_connection(conn)
             self._thread_local.in_db_log = False