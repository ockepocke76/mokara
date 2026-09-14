import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def configure_logging():
    """
    Centralized root-logger setup for the api and the worker; call once at
    process start. Console always; the rotating simulation.log file only
    when the filesystem is meant for it (disable with LOG_TO_FILES=0 — on
    Cloud Run the writable FS is in-memory and stdout is what reaches
    Cloud Logging).
    """
    # --- Import config inside the function to avoid circular dependencies ---
    from config import CONFIG

    root_logger = logging.getLogger()

    # Clear any existing handlers to prevent duplicate logging on
    # re-initialization (worker restarts, test harnesses).
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Read the desired terminal log level from config.yml. Default to INFO.
    terminal_level_str = CONFIG.get('logging', {}).get('terminal_level', {}).get('value', 'INFO').upper()
    terminal_level = getattr(logging, terminal_level_str, logging.INFO)

    # Root at DEBUG; each handler filters down to its own level.
    root_logger.setLevel(logging.DEBUG)

    # Silence verbose chart-export internals (kaleido spawns chatty
    # subprocess logging during flowchart PNG generation).
    for logger_name in ('choreo', 'kaleido'):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    if os.getenv('LOG_TO_FILES', '1') != '0':
        file_handler = RotatingFileHandler(
            'simulation.log', maxBytes=5 * 1024 * 1024, backupCount=2, mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(terminal_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.info("Logging configured.")
