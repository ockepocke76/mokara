"""
Admin Logic Module

Contains orchestrator functions for administrative tasks like:
- System Reset (Wiping DB)
- Strategy Repo Reseeding (Syncing built-ins to GitHub)
"""

import logging
import inspect
from typing import List, Dict, Any

from db.database import db
from services.git_service import get_git_service
from utils.strategy_utils import STRATEGY_CLASS_MAP

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


def reseed_strategy_repo() -> List[str]:
    """
    Syncs built-in strategies to the configured GitHub repository.
    
    Checks if the strategy file exists on the 'main' branch.
    If missing or content differs, pushes the current built-in code.
    
    Returns:
        List of strings describing actions taken (e.g., "Updated Trinity", "Skipped BBD").
    """
    git_service = get_git_service()
    results = []
    
    logging.info("🔄 Starting Strategy Repo Reseed...")
    
    for display_name, strategy_cls in STRATEGY_CLASS_MAP.items():
        # Deduplicate: strategy names might map to same class (e.g. "Trinity", "Trinity Study")
        # We only want to save uniquely by class name.
        # But we need a naming convention for the file. 
        # Let's use the class name as the filename: strategies/builtin/{ClassName}.py
        
        class_name = strategy_cls.__name__
        file_path = f"strategies/builtin/{class_name}.py"
        
        try:
            # 1. Get Local Content
            source_code = inspect.getsource(strategy_cls)
            doc_string = inspect.getdoc(strategy_cls) or ""
            
            # Add a header to indicate this is a system file
            file_content = f'"""\n{doc_string}\n\nExisting Built-in Strategy used for Reference.\n"""\n\n{source_code}'
            
            # 2. Check Remote Content (Idempotency)
            should_update = False
            message = "Skipped (Up to date)"
            
            try:
                # Get current SHA/Content from main branch
                # This might fail if file doesn't exist -> 404
                remote_content = git_service.get_file_content("main", file_path)
                
                # Compare contents
                # Simple string comparison (ignoring line endings could be safer but strict is ok for now)
                if remote_content.strip() != file_content.strip():
                    should_update = True
                    message = "Updated (Content changed)"
                    
            except Exception as e:
                # Assuming 404/Not Found means we need to create it
                should_update = True
                message = "Created (New file)"
            
            # 3. Push if needed
            if should_update:
                git_service.commit_file(
                    branch_name="main",
                    file_path=file_path,
                    content=file_content,
                    message=f"System: Reseed built-in strategy {class_name}"
                )
                logging.info(f"✅ Pushed {file_path}")
            else:
                logging.info(f"⏭️  {file_path} is up to date.")
                
            results.append(f"{class_name}: {message}")
            
        except Exception as e:
            error_msg = f"Failed to process {class_name}: {str(e)}"
            logging.error(error_msg)
            results.append(f"❌ {class_name}: Error ({str(e)})")
            
    # Filter duplicates in results (since map has aliases)
    unique_results = sorted(list(set(results)))
    return unique_results
