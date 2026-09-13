"""
Persistence for agentic strategy-generation runs (W5).

STRATEGY_GENERATION_RUNS is the run registry; STRATEGY_GENERATION_EVENTS is
the append-only build log. The UI rehydrates from events after a reload, and
the full trace feeds prompt tuning — so every artifact the graph produces is
written here, not only streamed.
"""
import json
import logging

from db.database import db

_RUN_FIELDS = {'status', 'strategy_name', 'spec', 'final_strategy_id',
               'failure_summary', 'llm_calls'}
_JSON_FIELDS = {'spec'}


def create_run(run_id: str, user_id: int, thread_id: str, user_request: str,
               strategy_name: str | None = None,
               seed_strategy_id: int | None = None) -> None:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO STRATEGY_GENERATION_RUNS
                (id, user_id, thread_id, status, user_request, strategy_name, seed_strategy_id)
            VALUES (%s, %s, %s, 'running', %s, %s, %s)
            """,
            (run_id, user_id, thread_id, user_request, strategy_name, seed_strategy_id),
        )
        conn.commit()
    finally:
        db.release_connection(conn)


def update_run(run_id: str, **fields) -> None:
    updates = {k: v for k, v in fields.items() if k in _RUN_FIELDS}
    if not updates:
        return
    sets = []
    values = []
    for key, value in updates.items():
        sets.append(f"{key} = %s")
        if key in _JSON_FIELDS and isinstance(value, (dict, list)):
            value = json.dumps(value)
        values.append(value)
    values.append(run_id)
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE STRATEGY_GENERATION_RUNS SET {', '.join(sets)}, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            tuple(values),
        )
        conn.commit()
    finally:
        db.release_connection(conn)


def claim_run(run_id: str, expected_status: str, new_status: str) -> bool:
    """Atomic status transition — the row is claimed only if it is still in
    expected_status. Returns False when another caller won the race."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE STRATEGY_GENERATION_RUNS SET status = %s, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = %s AND status = %s",
            (new_status, run_id, expected_status),
        )
        claimed = cursor.rowcount == 1
        conn.commit()
        return claimed
    finally:
        db.release_connection(conn)


def fail_orphaned_runs() -> int:
    """Startup reconcile: rows left 'running' by a dead process. Safe to call
    before any run has started in this process — every 'running' row is then
    an orphan (its daemon thread died with the old process)."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE STRATEGY_GENERATION_RUNS SET status = 'failed', "
            "failure_summary = 'The server restarted while this run was in "
            "progress. Start a new run — any draft was kept.', "
            "updated_at = CURRENT_TIMESTAMP WHERE status = 'running' "
            "RETURNING id",
        )
        rows = cursor.fetchall()
        conn.commit()
        for (orphan_id,) in rows:
            try:
                append_event(orphan_id, 'run_failed',
                             {'summary': 'The server restarted while this run was in progress.'})
            except Exception:
                pass
        return len(rows)
    finally:
        db.release_connection(conn)


def get_run(run_id: str) -> dict | None:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, thread_id, status, user_request, strategy_name,
                   seed_strategy_id, spec, final_strategy_id, failure_summary,
                   llm_calls, created_at, updated_at
            FROM STRATEGY_GENERATION_RUNS WHERE id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        keys = ['id', 'user_id', 'thread_id', 'status', 'user_request',
                'strategy_name', 'seed_strategy_id', 'spec',
                'final_strategy_id', 'failure_summary', 'llm_calls',
                'created_at', 'updated_at']
        run = dict(zip(keys, row))
        run['id'] = str(run['id'])
        run['spec'] = db.deserialize_json_column(run['spec']) if run['spec'] else None
        return run
    finally:
        db.release_connection(conn)


def list_runs(user_id: int, limit: int = 20) -> list[dict]:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, status, user_request, strategy_name, seed_strategy_id,
                   final_strategy_id, created_at, updated_at
            FROM STRATEGY_GENERATION_RUNS
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        keys = ['id', 'status', 'user_request', 'strategy_name',
                'seed_strategy_id', 'final_strategy_id', 'created_at', 'updated_at']
        runs = [dict(zip(keys, row)) for row in cursor.fetchall()]
        for run in runs:
            run['id'] = str(run['id'])
        return runs
    finally:
        db.release_connection(conn)


def append_event(run_id: str, event_type: str, payload: dict | None = None) -> int:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        # Single writer per run (the graph runner), so MAX+1 is race-free.
        cursor.execute(
            """
            INSERT INTO STRATEGY_GENERATION_EVENTS (run_id, seq, event_type, payload)
            SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s
            FROM STRATEGY_GENERATION_EVENTS WHERE run_id = %s
            RETURNING seq
            """,
            (run_id, event_type, json.dumps(payload or {}), run_id),
        )
        seq = cursor.fetchone()[0]
        conn.commit()
        return seq
    except Exception:
        logging.exception("append_event failed for run %s (%s)", run_id, event_type)
        raise
    finally:
        db.release_connection(conn)


def list_events(run_id: str, after_seq: int = 0) -> list[dict]:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT seq, event_type, payload, created_at
            FROM STRATEGY_GENERATION_EVENTS
            WHERE run_id = %s AND seq > %s
            ORDER BY seq
            """,
            (run_id, after_seq),
        )
        return [
            {'seq': row[0], 'type': row[1],
             'payload': db.deserialize_json_column(row[2]) or {},
             'created_at': row[3]}
            for row in cursor.fetchall()
        ]
    finally:
        db.release_connection(conn)


def list_runs_for_strategy(strategy_id: int) -> list[dict]:
    """All runs that produced or evolved this strategy (the create run,
    evolve runs, and a failed run whose saved draft this is), oldest first.
    Powers the strategy History tab's human-input timeline."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, status, user_request, seed_strategy_id, created_at
            FROM STRATEGY_GENERATION_RUNS
            WHERE final_strategy_id = %s
            ORDER BY created_at
            """,
            (strategy_id,),
        )
        keys = ['id', 'status', 'user_request', 'seed_strategy_id', 'created_at']
        runs = [dict(zip(keys, row)) for row in cursor.fetchall()]
        for run in runs:
            run['id'] = str(run['id'])
        return runs
    finally:
        db.release_connection(conn)
