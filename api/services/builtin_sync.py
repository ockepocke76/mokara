"""
Built-in Strategy Synchronization Module

Syncs built-in strategies (Trinity, BBD, GRSR) from Python code to:
1. CUSTOM_STRATEGIES table (user_id=0)
2. Git repository (strategies/builtin/* branches)

This enables unified architecture where all strategies use the same
Git-based lineage tracking and evolution history.
"""

import logging
import inspect
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone

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


def create_metadata_json(strategy_info: dict, commit_sha: str) -> str:
    """Create metadata.json content for a built-in strategy."""
    metadata = {
        'strategy_name': strategy_info['name'],
        'strategy_key': strategy_info['key'],
        'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'is_builtin': True,
        'parent_strategy_id': None,
        'evolution_history': [],
        'git_commit_sha': commit_sha,
        'description': strategy_info['description']
    }
    return json.dumps(metadata, indent=2)


def sync_builtin_strategy(
    strategy_info: dict,
    git_service,
    db,
    force_update: bool = False
) -> Tuple[str, str, str]:
    """
    Sync a single built-in strategy to Git and database.

    Args:
        strategy_info: Dict with 'key', 'name', 'class', 'description'
        git_service: GitHubService instance, or None to sync DB-only with a
            local content-hash SHA (mokara runs without the GitHub repo)
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
        
        # 2. Check if strategy exists in database
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, code, git_commit_sha FROM CUSTOM_STRATEGIES WHERE user_id = 0 AND strategy_name = %s",
                (strategy_name,)
            )
            existing = cursor.fetchone()
        finally:
            db.release_connection(conn)
        
        # 3. Skip if code unchanged (unless force_update)
        if existing and not force_update:
            existing_id, existing_code, existing_sha = existing
            if existing_code == code:
                return ('skipped', strategy_name, f'Code unchanged (SHA: {existing_sha[:7] if existing_sha else "N/A"})')
        
        # 4-7. Git branch + commits — or a local content-hash SHA when no
        # git service is configured (mokara: DB is the source of truth).
        if git_service is None:
            from utils.strategy_utils import calculate_strategy_hash
            branch_name = None
            commit_sha = calculate_strategy_hash(code, {})
        else:
            branch_name = f"strategies/builtin/{strategy_key}"

            try:
                # Branch from main instead of empty-template
                branch_info = git_service.create_branch(branch_name, from_branch='main')
                if branch_info.get('already_exists'):
                    logging.info(f"Branch exists: {branch_name}")
                else:
                    logging.info(f"Created branch: {branch_name}")
            except Exception as e:
                logging.warning(f"Branch creation warning: {e}")
                # Branch might already exist, continue

            # 5. Commit strategy.py to Git
            commit_sha = git_service.commit_file(
                branch_name=branch_name,
                file_path='strategy.py',
                content=code,
                message=f"Sync built-in strategy: {strategy_name}"
            )
            logging.info(f"Committed strategy.py: {commit_sha[:7]}")

            # 6. Create metadata.json
            metadata_content = create_metadata_json(strategy_info, commit_sha)

            # 7. Commit metadata.json
            git_service.commit_file(
                branch_name=branch_name,
                file_path='metadata.json',
                content=metadata_content,
                message=f"Update metadata for {strategy_name}"
            )

        # 8. Save to database
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            
            if existing:
                # Update existing
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES 
                    SET code = %s,
                        git_branch_name = %s,
                        git_commit_sha = %s,
                        description = %s,
                        ai_description = %s,
                        validation_status = 'validated',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (code, branch_name, commit_sha, strategy_info['description'], strategy_info['description'], existing[0]))
                status = 'updated'
                message = f'Updated (SHA: {commit_sha[:7]})'
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO CUSTOM_STRATEGIES 
                    (user_id, strategy_name, class_name, description, ai_description, code, git_branch_name, git_commit_sha, 
                     is_public, validation_status, created_at, updated_at)
                    VALUES (0, %s, %s, %s, %s, %s, %s, %s, TRUE, 'validated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (strategy_name, strategy_class.__name__, strategy_info['description'], strategy_info['description'], code, branch_name, commit_sha))
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


def sync_all_builtins(git_service, db, force_update: bool = False) -> List[Tuple[str, str, str]]:
    """
    Sync all built-in strategies.
    
    Args:
        git_service: GitHubService instance
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
        result = sync_builtin_strategy(strategy_info, git_service, db, force_update)
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
