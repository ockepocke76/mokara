"""
Admin Logic Module

Contains orchestrator functions for administrative tasks like:
- System Reset (Wiping DB)
"""

import logging

from db.database import db

def perform_system_reset(admin_password: str, confirmation_text: str) -> bool:
    """
    Performs a full system reset:
    1. Validates admin password.
    2. Validates confirmation text ("DELETE-EVERYTHING").
    3. Wipes the database schema.
    4. (Optional) Could trigger other cleanups.
    
    Returns True if successful, raises Exception on failure.
    """
    # 1. Validate Confirmation Text
    if confirmation_text != "DELETE-EVERYTHING":
        raise ValueError("Invalid confirmation text. Type 'DELETE-EVERYTHING' exactly.")

    # 2. Validate Password (Double check)
    from core.secrets import get_secret

    correct_password = get_secret("ADMIN_PASSWORD")
    if not correct_password:
        raise ValueError("ADMIN_PASSWORD is not configured; system reset refused.")

    if admin_password != correct_password:
        raise ValueError("Invalid admin password.")

    # 3. Wipe Database
    logging.warning("⚠️ INITIATING SYSTEM RESET: DROPPING ALL TABLES")
    try:
        db.drop_all_tables()
        logging.info("✅ Database schema wiped successfully.")
        
        # Clear local caches
        from core.cache import clear_all
        clear_all()

        return True
    except Exception as e:
        logging.critical(f"❌ System reset failed: {e}")
        raise e
