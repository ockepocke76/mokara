"""
Startup backfill for the V39 strategy version DAG.

Strategies that predate the DAG have code but no head_version_id. This
reconstructs their chain from the legacy evolution_history previous_code
snapshots (written between V37 and V39), then points pure-reference clones
at their parent's head. Idempotent: rows with a head are never touched, so
after one pass per database this is a cheap no-op.

Runs at API startup under an advisory lock (same pattern as the builtin
sync — concurrent containers must not double-insert version rows).
"""
import json
import logging

from utils.strategy_utils import calculate_strategy_hash


def backfill_strategy_versions(db) -> int:
    """Returns the number of strategies that received a version chain."""
    conn = db.get_connection()
    try:
        cursor = db._get_cursor(conn)
        cursor.execute(
            "SELECT pg_advisory_lock(hashtext('mokara_version_backfill'))")
        try:
            return _backfill(cursor, conn)
        finally:
            cursor.execute(
                "SELECT pg_advisory_unlock(hashtext('mokara_version_backfill'))")
    finally:
        db.release_connection(conn)


def _backfill(cursor, conn) -> int:
    cursor.execute("""
        SELECT id, user_id, code, parameters_json, class_name, git_commit_sha,
               evolution_history
        FROM CUSTOM_STRATEGIES
        WHERE code IS NOT NULL AND head_version_id IS NULL
        ORDER BY id
    """)
    rows = cursor.fetchall()
    touched = 0
    for sid, uid, code, parameters_json, class_name, sha, history in rows:
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except ValueError:
                history = []
        history = history or []
        if isinstance(parameters_json, (dict, list)):
            parameters_json = json.dumps(parameters_json)

        # Chain of (code, request-that-produced-it). Entry i's previous_code
        # is the code BEFORE request i, so request i belongs to the NEXT
        # snapshot in the chain (or to the current code for the last entry).
        snapshots = [(e.get('previous_code'), e.get('request'))
                     for e in history if e.get('previous_code')]
        chain = []
        produced_by = None
        for snap_code, request in snapshots:
            if not chain or chain[-1][0].strip() != snap_code.strip():
                chain.append((snap_code, produced_by))
            produced_by = request
        if not chain or chain[-1][0].strip() != code.strip():
            chain.append((code, produced_by))

        parent_id = None
        for i, (node_code, request) in enumerate(chain):
            is_live = i == len(chain) - 1  # the final node is the live code
            params = (parameters_json or '{}') if is_live else '{}'
            content_hash = (sha if is_live and sha else
                            calculate_strategy_hash(node_code, json.loads(params)))
            cursor.execute("""
                INSERT INTO STRATEGY_VERSIONS
                    (strategy_id, content_hash, code, parameters_json,
                     class_name, parent_version_id, source, request,
                     created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'backfill', %s, %s)
                RETURNING id
            """, (sid, content_hash, node_code, params, class_name,
                  parent_id, request, uid))
            parent_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET head_version_id = %s WHERE id = %s",
            (parent_id, sid))
        touched += 1

    # Pure-reference clones: the head is a pointer at the parent's head.
    cursor.execute("""
        UPDATE CUSTOM_STRATEGIES c
        SET head_version_id = p.head_version_id
        FROM CUSTOM_STRATEGIES p
        WHERE c.parent_strategy_id = p.id
          AND c.code IS NULL AND c.head_version_id IS NULL
          AND p.head_version_id IS NOT NULL
    """)
    touched += cursor.rowcount
    conn.commit()
    return touched
