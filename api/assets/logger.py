import logging
import sys
from logging.handlers import RotatingFileHandler

class UIInteractionFilter(logging.Filter):
    """A filter to isolate logs related to UI callbacks and background polling."""
    def filter(self, record):
        """
        Allows a log record to pass if its message starts with specific prefixes.
        """
        msg = record.getMessage()
        return msg.startswith("CALLBACK:") or msg.startswith("POLL:")

class StreamlitNoiseFilter(logging.Filter):
    """
    A comprehensive filter to suppress various known, benign warnings from Streamlit
    that occur when running in background threads or in "bare" mode.
    """
    def filter(self, record):
        msg = record.getMessage()
        # List of noisy messages to suppress.
        suppress_list = [
            "ScriptRunContext", # Catches "missing ScriptRunContext", "No script run context", etc.
            "No script run context available",
            "No runtime found, using MemoryCacheStorageManager",
            "special scriptrun state", # Another internal Streamlit message
            # The warning about how to run a streamlit app, seen in background processes.
            "streamlit run"
        ]
        # The filter will PASS (return True) if the message is NOT in the suppress list.
        return not any(suppressed_msg in msg for suppressed_msg in suppress_list)

def configure_logging():
    """
    A single, centralized function to configure the root logger for the entire application.
    This should be called once at the very beginning of the application's lifecycle.
    It sets up handlers and applies filters to suppress noisy output globally.
    """
    # --- Prevent Re-configuration in Streamlit ---
    # In Streamlit, the script re-runs on every interaction. We use a simple
    # flag to ensure this complex setup happens only ONCE per session.
    # For background processes, this check won't apply, and they will
    # correctly configure themselves once.
    try:
        import streamlit as st
        if getattr(st, '_is_logging_configured', False):
            return
        st._is_logging_configured = True
    except (ImportError, AttributeError):
        # We are not in a Streamlit session (e.g., a background process), so proceed.
        pass

    print("Configuring logging...")
    # --- Import config inside the function to avoid circular dependencies ---
    # This is a safe way to access config without causing startup issues.
    from config import CONFIG

    root_logger = logging.getLogger()

    # --- Make Log Level Configurable ---
    # Read the desired terminal log level from config.yml. Default to INFO if not found.
    terminal_level_str = CONFIG.get('logging', {}).get('terminal_level', {}).get('value', 'INFO').upper()
    terminal_level = getattr(logging, terminal_level_str, logging.INFO)

    # --- Set Root Logger Level ---
    # This is crucial. Set the root logger to the most permissive level (DEBUG).
    # Each handler will then filter messages based on its own configured level.
    root_logger.setLevel(logging.DEBUG)
    root_logger.addFilter(StreamlitNoiseFilter())

    # --- Robustly Silence Noisy Streamlit Loggers ---
    # This is the most reliable way to suppress benign warnings like "missing ScriptRunContext".
    # For each known noisy logger, we:
    # 1. Get the logger instance.
    # 2. Clear any handlers Streamlit may have added to it.
    # 3. Add our custom noise filter.
    # 4. Ensure it propagates messages to the root logger, which has its own handlers.
    noisy_loggers = [
        'snowflake.connector',
        'streamlit.runtime.scriptrunner.script_run_context',
        'streamlit.runtime.scriptrunner_utils.script_run_context',
        'streamlit.user_info',
        'streamlit.runtime.caching.cache_data_api'
    ]
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.addFilter(StreamlitNoiseFilter())
        logger.propagate = True

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    # --- Handler 1: General Log File (simulation.log) ---
    file_handler = RotatingFileHandler('simulation.log', maxBytes=5*1024*1024, backupCount=2, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # --- Handler 2: Special UI Interaction Log File (ui_interaction.log) ---
    ui_log_handler = RotatingFileHandler('ui_interaction.log', maxBytes=1*1024*1024, backupCount=1, mode='w')
    ui_log_handler.setLevel(logging.DEBUG)
    ui_log_handler.setFormatter(formatter)
    ui_log_handler.addFilter(UIInteractionFilter())
    root_logger.addHandler(ui_log_handler)

    # --- Handler 3: Console Output ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(terminal_level) # Use the level from the config file
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)