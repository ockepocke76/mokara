"""
Strategy Cloning Service

Centralized service for cloning strategies (both built-in and custom).
Ensures consistent clone behavior across all UI components.
"""

import logging
from typing import Optional, Any


def clone_strategy(
    strategy_id: int,
    user_id: int,
    db: Any,
    clone_name: Optional[str] = None
) -> dict:
    """
    Clone a strategy (built-in or custom) for a user.
    
    This is the single source of truth for ALL cloning operations in the application.
    Use this instead of calling db.save_custom_strategy() directly for clones.
    
    Args:
        strategy_id: ID of strategy to clone (from CUSTOM_STRATEGIES table)
        user_id: User ID creating the clone
        db: Database instance
        clone_name: Optional custom name for clone (defaults to original name)
    
    Returns:
        {
            'success': bool,
            'strategy_id': int | None,      # ID of newly created clone
            'strategy_name': str | None,    # Name of clone
            'git_commit_sha': str | None,   # SHA of clone (inherited from parent)
            'parent_strategy_id': int,      # ID of parent strategy
            'error': str | None             # Error message if failed
        }
    
    Example:
        >>> result = clone_strategy(
        ...     strategy_id=24,  # Trinity built-in
        ...     user_id=1,
        ...     db=db
        ... )
        >>> if result['success']:
        ...     print(f"Cloned as ID {result['strategy_id']}")
    """
    
    try:
        # Fetch parent strategy from unified CUSTOM_STRATEGIES table
        parent_strategy = db.get_custom_strategy(strategy_id)
        
        if not parent_strategy:
            logging.error(f"Strategy ID {strategy_id} not found in CUSTOM_STRATEGIES")
            return {
                'success': False,
                'strategy_id': None,
                'strategy_name': None,
                'git_commit_sha': None,
                'parent_strategy_id': strategy_id,
                'error': f'Strategy ID {strategy_id} not found'
            }
            
        # Recursive Reference Prevention: Disallow cloning unmaterialized clones
        if parent_strategy.get('is_pure_clone'):
            logging.warning(f"Attempted to clone unmaterialized clone ID {strategy_id}")
            return {
                'success': False,
                'strategy_id': None,
                'strategy_name': None,
                'git_commit_sha': None,
                'parent_strategy_id': strategy_id,
                'error': 'Recursion prevention: Clones must be edited/materialized before they can be cloned themselves.'
            }
        
        # Determine clone name (use original name if not specified). If the
        # user already HAS a strategy with that name — soft-deleted ones
        # included, because save_custom_strategy's (user_id, strategy_name)
        # upsert matches and resurrects those too — suffix it: a colliding
        # clone would UPDATE that row, and with is_clone_unedited=True that
        # nulls its code (cloning your own strategy used to destroy it this
        # way).
        final_clone_name = clone_name or parent_strategy['strategy_name']
        existing = db.get_user_strategy_names(user_id)
        if final_clone_name in existing:
            base = final_clone_name
            n = 2
            final_clone_name = f"{base} (clone)"
            while final_clone_name in existing:
                final_clone_name = f"{base} (clone {n})"
                n += 1
        
        # Extract parent metadata
        parent_sha = parent_strategy.get('git_commit_sha')
        
        logging.info(
            f"Cloning strategy '{parent_strategy['strategy_name']}' "
            f"(ID: {strategy_id}, SHA: {parent_sha[:7] if parent_sha else 'N/A'}) "
            f"for user {user_id}"
        )
        
        # Save clone with complete metadata
        # Returns strategy_id (int) on success, or True/False/None
        logging.info(f"[DEBUG] Calling db.save_custom_strategy for clone '{final_clone_name}'...")
        save_result = db.save_custom_strategy(
            user_id=user_id,
            strategy_name=final_clone_name,
            class_name=parent_strategy['class_name'],
            description=parent_strategy.get('description', ''),
            ai_description=parent_strategy.get('ai_description', ''),
            code=None,                                # Pure Clone (Inherit from parent)
            parameters_json=parent_strategy.get('parameters_json', '{}'),
            validation_status=parent_strategy.get('validation_status', 'not_started'),
            validation_error=parent_strategy.get('validation_error'),
            parent_strategy_id=strategy_id,           # Link to parent
            clone_source_commit_sha=parent_sha,       # Preserve parent SHA
            is_clone_unedited=True,                   # Explicitly marked as unedited
        )
        
        logging.info(f"[DEBUG] db.save_custom_strategy returned: {save_result} (Type: {type(save_result)})")
        
        if not save_result:
            logging.error(f"Failed to save clone for strategy ID {strategy_id}")
            return {
                'success': False,
                'strategy_id': None,
                'strategy_name': final_clone_name,
                'git_commit_sha': None,
                'parent_strategy_id': strategy_id,
                'error': 'Database save failed'
            }

        # Determine ID from result
        saved_id = None
        if isinstance(save_result, int) and not isinstance(save_result, bool):
            saved_id = save_result
            
        # Fallback verification (legacy or if DB didn't return ID directly)
        cloned_strategy = None
        if saved_id:
             # We have the ID directly from the DB save
             cloned_strategy = {'id': saved_id, 'strategy_name': final_clone_name}
        else:
            # Fallback: Fetch list (prone to caching issues, used only if DB returns bool)
            user_strategies = db.get_user_custom_strategies(user_id)
            cloned_strategy = next(
                (s for s in user_strategies 
                 if s.get('parent_strategy_id') == strategy_id 
                 and s['strategy_name'] == final_clone_name),
                None
            )
        
        if not cloned_strategy:
            # Clone was saved (result was True) but we couldn't find it
            logging.error(f"CRITICAL: Clone saved but ID not returned and not found in list verification!")
            return {
                'success': False,
                'strategy_id': None,
                'strategy_name': final_clone_name,
                'git_commit_sha': None,
                'parent_strategy_id': strategy_id,
                'error': 'Strategy saved but could not be verified'
            }

        logging.info(
            f"✓ Clone created successfully: '{final_clone_name}' "
            f"(ID: {cloned_strategy['id']}, SHA: {parent_sha[:7] if parent_sha else 'N/A'})"
        )
        
        return {
            'success': True,
            'strategy_id': cloned_strategy['id'],
            'strategy_name': cloned_strategy['strategy_name'],
            'git_commit_sha': parent_sha, # Use parent SHA as it is unedited
            'parent_strategy_id': strategy_id,
            'error': None
        }
        
    except Exception as e:
        logging.error(f"Exception during clone operation: {e}", exc_info=True)
        return {
            'success': False,
            'strategy_id': None,
            'strategy_name': clone_name,
            'git_commit_sha': None,
            'parent_strategy_id': strategy_id,
            'error': str(e)
        }


def has_user_cloned_strategy(user_id: int, parent_strategy_id: int, db: Any) -> bool:
    """
    Check if user has already cloned a specific strategy.
    
    Uses parent_strategy_id linkage (not name comparison) for accurate detection.
    
    Args:
        user_id: User ID to check
        parent_strategy_id: ID of parent strategy
        db: Database instance
    
    Returns:
        True if user has a clone of this strategy, False otherwise
    
    Example:
        >>> if has_user_cloned_strategy(user_id=1, parent_strategy_id=24, db=db):
        ...     print("User already has a clone of Trinity")
    """
    try:
        user_strategies = db.get_user_custom_strategies(user_id)
        
        # Check for parent linkage (SHA-based identity, not name-based!)
        return any(
            s.get('parent_strategy_id') == parent_strategy_id 
            for s in user_strategies
        )
        
    except Exception as e:
        logging.error(f"Error checking clone status: {e}", exc_info=True)
        return False  # Fail open - allow clone attempt if check fails
