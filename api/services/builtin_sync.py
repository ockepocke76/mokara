"""
Built-in Strategy Synchronization Module

Syncs built-in strategies (Trinity, BBD, GRSR) from Python code to the
CUSTOM_STRATEGIES table (user_id=0), identified by a content-hash SHA
(stored in the legacy git_commit_sha column).

This enables unified architecture where all strategies use the same
lineage tracking and evolution history.
"""

import logging
import inspect
from typing import Dict, List, Tuple, Optional

from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy


# Built-in strategy definitions
BUILTIN_STRATEGIES = [
    {
        'key': 'trinity',
        'name': 'Trinity',
        'class': TrinityStrategy,
        'description': 'Trinity Study 4% withdrawal strategy'
    },
    {
        'key': 'bbd',
        'name': 'Buy Borrow Die',
        'class': BuyBorrowDieStrategy,
        'description': 'Tax-efficient leverage strategy'
    },
    {
        'key': 'grsr',
        'name': 'Get Rich Stay Rich',
        'class': GetRichStayRichStrategy,
        'description': 'Hybrid accumulation and withdrawal strategy'
    }
]


def get_builtin_name_by_key(key: str) -> Optional[str]:
    """
    Get built-in strategy display name from its key.
    
    Args:
        key: Strategy key (e.g., 'trinity', 'bbd', 'grsr')
    
    Returns:
        Display name (e.g., 'Trinity') or None if not found
    """
    for strategy in BUILTIN_STRATEGIES:
        if strategy['key'] == key:
            return strategy['name']
    return None


def extract_strategy_code(strategy_class) -> str:
    """Extract source code from strategy class."""
    return inspect.getsource(strategy_class)


def sync_builtin_strategy(
    strategy_info: dict,
    db,
    force_update: bool = False
) -> Tuple[str, str, str]:
    """
    Sync a single built-in strategy to the database, identified by a
    content-hash SHA (the DB is the authoritative store).

    Args:
        strategy_info: Dict with 'key', 'name', 'class', 'description'
        db: Database instance
        force_update: Force update even if code matches

    Returns:
        Tuple of (status, strategy_name, message)
        status: 'success' | 'updated' | 'skipped' | 'error'
    """
    strategy_key = strategy_info['key']
    strategy_name = strategy_info['name']
    strategy_class = strategy_info['class']
    
    try:
        # 1. Extract code
        code = extract_strategy_code(strategy_class)
        logging.info(f"Extracted {len(code)} chars from {strategy_name}")

        # Store the full user-facing write-up, not the sync's one-liner —
        # every consumer (library cards, detail page) reads these columns.
        from utils.strategy_utils import get_strategy_description
        description = get_strategy_description(strategy_key) or strategy_info['description']

        # 2. Check if strategy exists in database
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, code, git_commit_sha, description FROM CUSTOM_STRATEGIES WHERE user_id = 0 AND strategy_name = %s",
                (strategy_name,)
            )
            existing = cursor.fetchone()
        finally:
            db.release_connection(conn)

        # 3. Skip if nothing changed (unless force_update)
        if existing and not force_update:
            existing_id, existing_code, existing_sha, existing_description = existing
            if existing_code == code and existing_description == description:
                return ('skipped', strategy_name, f'Code unchanged (SHA: {existing_sha[:7] if existing_sha else "N/A"})')
        
        # 4. Local content-hash SHA (the DB is the source of truth)
        from utils.strategy_utils import calculate_strategy_hash
        commit_sha = calculate_strategy_hash(code, {})

        # 5. Save to database
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            
            if existing:
                # Update existing
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET code = %s,
                        git_commit_sha = %s,
                        description = %s,
                        ai_description = %s,
                        validation_status = 'validated',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (code, commit_sha, description, description, existing[0]))
                status = 'updated'
                message = f'Updated (SHA: {commit_sha[:7]})'
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO CUSTOM_STRATEGIES
                    (user_id, strategy_name, class_name, description, ai_description, code, git_commit_sha,
                     is_public, validation_status, created_at, updated_at)
                    VALUES (0, %s, %s, %s, %s, %s, %s, TRUE, 'validated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (strategy_name, strategy_class.__name__, description, description, code, commit_sha))
                status = 'success'
                message = f'Created (SHA: {commit_sha[:7]})'
            
            conn.commit()
            logging.info(f"✓ Synced {strategy_name}: {status}")
            
        finally:
            db.release_connection(conn)
        
        return (status, strategy_name, message)
        
    except Exception as e:
        logging.error(f"Failed to sync {strategy_name}: {e}", exc_info=True)
        return ('error', strategy_name, str(e))


def sync_all_builtins(db, force_update: bool = False) -> List[Tuple[str, str, str]]:
    """
    Sync all built-in strategies.

    Args:
        db: Database instance
        force_update: Force update even if code matches

    Returns:
        List of (status, strategy_name, message) tuples
    """
    # Ensure system user exists (user_id=0)
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM USERS WHERE id = 0")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO USERS (id, email, name, created_at)
                VALUES (0, 'system@btc-simulator.internal', 'SYSTEM', CURRENT_TIMESTAMP)
            """)
            conn.commit()
            logging.info("Created system user (id=0)")
        else:
            logging.info("System user (id=0) already exists")
    except Exception as e:
        logging.error(f"Failed to ensure system user: {e}")
        return [('error', 'SYSTEM_USER', str(e))]
    finally:
        db.release_connection(conn)
    
    # Sync each built-in strategy
    results = []
    for strategy_info in BUILTIN_STRATEGIES:
        result = sync_builtin_strategy(strategy_info, db, force_update)
        results.append(result)
    
    return results


def get_builtin_sync_status(db) -> List[Dict]:
    """
    Get current sync status of built-in strategies.
    
    Returns:
        List of dicts with strategy info and sync status
    """
    status_list = []
    
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        
        for strategy_info in BUILTIN_STRATEGIES:
            try:
                cursor.execute("""
                    SELECT id, git_commit_sha, updated_at 
                    FROM CUSTOM_STRATEGIES 
                    WHERE user_id = 0 AND strategy_name = %s
                """, (strategy_info['name'],))
                row = cursor.fetchone()
                
                if row:
                    status_list.append({
                        'name': strategy_info['name'],
                        'key': strategy_info['key'],
                        'synced': True,
                        'db_id': row[0],
                        'git_sha': row[1],
                        'last_synced': row[2]
                    })
                else:
                    status_list.append({
                        'name': strategy_info['name'],
                        'key': strategy_info['key'],
                        'synced': False,
                        'db_id': None,
                        'git_sha': None,
                        'last_synced': None
                    })
            except Exception as e:
                logging.error(f"Error getting status for {strategy_info['name']}: {e}")
                status_list.append({
                    'name': strategy_info['name'],
                    'key': strategy_info['key'],
                    'synced': False,
                    'error': str(e)
                })
    finally:
        db.release_connection(conn)
    
    return status_list
