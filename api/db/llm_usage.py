"""
LLM_USAGE: one row per Gemini call, written by core.llm.call_gemini_safe.

A user-facing operation (one strategy creation, one evolution, one Q&A
answer, one report analysis) spans several calls that share
(operation, ref_id); every read here aggregates to that grain first, so
"cost per strategy creation" is a real per-run number, not a per-call one.
Calls that arrived without an llm_scope (ref_id NULL) count as one operation
each — they show up as 'unknown' in admin rather than vanishing.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from db.database import db

# Operation labels used by callers of core.llm.llm_scope — kept here so the
# admin API and UI have one list to iterate.
OPERATIONS = ('strategy_create', 'strategy_evolve', 'strategy_qa', 'report_analysis')


def _rows(cursor) -> list[dict]:
    keys = [col[0] for col in cursor.description]
    out = []
    for row in cursor.fetchall():
        item = dict(zip(keys, row))
        for k, v in item.items():
            if isinstance(v, Decimal):
                item[k] = float(v)
            elif isinstance(v, (datetime, date)):
                item[k] = v.isoformat()
        out.append(item)
    return out


def record_call(*, operation: str, model: str, user_id: Optional[int] = None,
                ref_id: Optional[str] = None, step: Optional[str] = None,
                tier: Optional[str] = None, prompt_tokens: int = 0, cached_tokens: int = 0,
                completion_tokens: int = 0, thinking_tokens: int = 0,
                cost_usd: Optional[float] = None, latency_ms: Optional[int] = None,
                ok: bool = True, error: Optional[str] = None) -> None:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO LLM_USAGE
                (user_id, operation, ref_id, step, tier, model,
                 prompt_tokens, cached_tokens, completion_tokens, thinking_tokens,
                 cost_usd, latency_ms, ok, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, operation, ref_id, step, tier, model,
             int(prompt_tokens or 0), int(cached_tokens or 0),
             int(completion_tokens or 0), int(thinking_tokens or 0),
             cost_usd, latency_ms, bool(ok), error),
        )
        conn.commit()
    finally:
        db.release_connection(conn)


# One operation = the calls sharing (operation, ref_id). Scope-less calls
# (ref_id NULL) become one operation each via COALESCE on the row id.
_OPERATIONS_CTE = """
    ops AS (
        SELECT operation,
               COALESCE(ref_id, 'call-' || id::text) AS ref_id,
               MAX(user_id) AS user_id,
               COUNT(*) AS calls,
               COUNT(*) FILTER (WHERE NOT ok) AS failed_calls,
               COUNT(*) FILTER (WHERE cost_usd IS NULL AND ok) AS unpriced_calls,
               SUM(cost_usd) AS cost_usd,
               SUM(prompt_tokens) AS prompt_tokens,
               SUM(cached_tokens) AS cached_tokens,
               SUM(completion_tokens) AS completion_tokens,
               SUM(thinking_tokens) AS thinking_tokens,
               SUM(latency_ms) AS latency_ms,
               MIN(created_at) AS started_at,
               MAX(created_at) AS finished_at
        FROM LLM_USAGE
        {where}
        GROUP BY operation, COALESCE(ref_id, 'call-' || id::text)
    )
"""


def operation_stats(window: int = 100) -> list[dict]:
    """Per operation type: n / mean / median / p90 / max cost and mean token
    mix over the latest `window` operations of that type."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "WITH " + _OPERATIONS_CTE.format(where="") + """,
            ranked AS (
                SELECT ops.*, ROW_NUMBER() OVER (PARTITION BY operation ORDER BY finished_at DESC) AS rn
                FROM ops
            )
            SELECT operation,
                   COUNT(*) AS n,
                   AVG(cost_usd) AS mean_cost_usd,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cost_usd) AS median_cost_usd,
                   PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY cost_usd) AS p90_cost_usd,
                   MAX(cost_usd) AS max_cost_usd,
                   SUM(cost_usd) AS total_cost_usd,
                   AVG(calls) AS mean_calls,
                   AVG(prompt_tokens) AS mean_prompt_tokens,
                   AVG(cached_tokens) AS mean_cached_tokens,
                   AVG(completion_tokens) AS mean_completion_tokens,
                   AVG(thinking_tokens) AS mean_thinking_tokens,
                   AVG(latency_ms) AS mean_latency_ms,
                   SUM(unpriced_calls) AS unpriced_calls,
                   SUM(failed_calls) AS failed_calls,
                   MIN(started_at) AS window_from,
                   MAX(finished_at) AS window_to
            FROM ranked
            WHERE rn <= %s
            GROUP BY operation
            ORDER BY operation
            """,
            (window,),
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)


def step_stats(operation: str, window: int = 100) -> list[dict]:
    """Where the money goes inside one operation type: mean cost and tokens
    per step (graph node) over the latest `window` operations."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "WITH " + _OPERATIONS_CTE.format(where="WHERE operation = %s") + """,
            recent AS (
                SELECT ref_id FROM ops ORDER BY finished_at DESC LIMIT %s
            )
            SELECT COALESCE(u.step, '(no step)') AS step,
                   COALESCE(u.tier, '') AS tier,
                   COUNT(*) AS calls,
                   COUNT(*)::float / (SELECT COUNT(*) FROM recent) AS calls_per_operation,
                   SUM(u.cost_usd) / (SELECT COUNT(*) FROM recent) AS cost_per_operation_usd,
                   AVG(u.cost_usd) AS mean_cost_usd,
                   AVG(u.prompt_tokens) AS mean_prompt_tokens,
                   AVG(u.completion_tokens) AS mean_completion_tokens,
                   AVG(u.thinking_tokens) AS mean_thinking_tokens,
                   AVG(u.latency_ms) AS mean_latency_ms
            FROM LLM_USAGE u
            JOIN recent ON recent.ref_id = COALESCE(u.ref_id, 'call-' || u.id::text)
            WHERE u.operation = %s
            GROUP BY u.step, u.tier
            ORDER BY cost_per_operation_usd DESC NULLS LAST
            """,
            (operation, window, operation),
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)


def totals(days: int = 30) -> dict:
    """Spend over the last `days`: grand total, per operation, and per day."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT operation,
                   COUNT(DISTINCT COALESCE(ref_id, 'call-' || id::text)) AS operations,
                   COUNT(*) AS calls,
                   SUM(cost_usd) AS cost_usd,
                   COUNT(*) FILTER (WHERE cost_usd IS NULL AND ok) AS unpriced_calls
            FROM LLM_USAGE
            WHERE created_at >= NOW() - (%s || ' days')::interval
            GROUP BY operation
            ORDER BY cost_usd DESC NULLS LAST
            """,
            (str(int(days)),),
        )
        by_operation = _rows(cursor)
        cursor.execute(
            """
            SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
                   COUNT(DISTINCT COALESCE(ref_id, 'call-' || id::text)) AS operations,
                   SUM(cost_usd) AS cost_usd
            FROM LLM_USAGE
            WHERE created_at >= NOW() - (%s || ' days')::interval
            GROUP BY 1
            ORDER BY 1
            """,
            (str(int(days)),),
        )
        by_day = _rows(cursor)
        cursor.execute(
            "SELECT SUM(cost_usd) AS cost_usd, COUNT(*) AS calls FROM LLM_USAGE"
        )
        all_time = _rows(cursor)[0]
        return {
            'days': days,
            'cost_usd': sum((r['cost_usd'] or 0) for r in by_operation),
            'by_operation': by_operation,
            'by_day': by_day,
            'all_time_cost_usd': all_time['cost_usd'] or 0,
            'all_time_calls': all_time['calls'] or 0,
        }
    finally:
        db.release_connection(conn)


def user_totals(days: int = 30, limit: int = 200) -> list[dict]:
    """Per user over the last `days`: spend, operation counts by type."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "WITH " + _OPERATIONS_CTE.format(
                where="WHERE created_at >= NOW() - (%s || ' days')::interval") + """
            SELECT ops.user_id,
                   usr.email, usr.name, usr.plan_tier AS tier,
                   COUNT(*) AS operations,
                   SUM(cost_usd) AS cost_usd,
                   COUNT(*) FILTER (WHERE operation = 'strategy_create') AS strategy_create,
                   COUNT(*) FILTER (WHERE operation = 'strategy_evolve') AS strategy_evolve,
                   COUNT(*) FILTER (WHERE operation = 'strategy_qa') AS strategy_qa,
                   COUNT(*) FILTER (WHERE operation = 'report_analysis') AS report_analysis,
                   COUNT(*) FILTER (WHERE operation NOT IN ('strategy_create', 'strategy_evolve',
                                                            'strategy_qa', 'report_analysis')) AS other,
                   MAX(finished_at) AS last_activity
            FROM ops
            LEFT JOIN USERS usr ON usr.id = ops.user_id
            GROUP BY ops.user_id, usr.email, usr.name, usr.plan_tier
            ORDER BY cost_usd DESC NULLS LAST
            LIMIT %s
            """,
            (str(int(days)), limit),
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)


def user_operations(user_id: int, limit: int = 50) -> list[dict]:
    """One user's latest operations, newest first, with their cost."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "WITH " + _OPERATIONS_CTE.format(where="WHERE user_id = %s") + """
            SELECT operation, ref_id, calls, failed_calls, unpriced_calls, cost_usd,
                   prompt_tokens, cached_tokens, completion_tokens, thinking_tokens,
                   latency_ms, started_at, finished_at
            FROM ops
            ORDER BY finished_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)


def user_summary(user_id: int) -> dict:
    """All-time and 30-day spend for one user, for the admin user detail."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SUM(cost_usd) AS all_time_cost_usd,
                   SUM(cost_usd) FILTER (WHERE created_at >= NOW() - interval '30 days') AS cost_30d_usd,
                   SUM(cost_usd) FILTER (WHERE date_trunc('month', created_at) = date_trunc('month', NOW())) AS cost_month_usd,
                   COUNT(DISTINCT COALESCE(ref_id, 'call-' || id::text)) AS operations,
                   COUNT(DISTINCT COALESCE(ref_id, 'call-' || id::text))
                       FILTER (WHERE date_trunc('month', created_at) = date_trunc('month', NOW())) AS operations_month
            FROM LLM_USAGE WHERE user_id = %s
            """,
            (user_id,),
        )
        row = _rows(cursor)[0]
        return {k: (v or 0) for k, v in row.items()}
    finally:
        db.release_connection(conn)


def operation_calls(operation: str, ref_id: str) -> list[dict]:
    """The individual calls of one operation, in order (drill-down)."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, created_at, user_id, step, tier, model,
                   prompt_tokens, cached_tokens, completion_tokens, thinking_tokens,
                   cost_usd, latency_ms, ok, error
            FROM LLM_USAGE
            WHERE operation = %s AND ref_id = %s
            ORDER BY created_at, id
            """,
            (operation, ref_id),
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)


def recent_operations(operation: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Latest operations across users (admin overview table)."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        where = "WHERE operation = %s" if operation else ""
        params: tuple = (operation, limit) if operation else (limit,)
        cursor.execute(
            "WITH " + _OPERATIONS_CTE.format(where=where) + """
            SELECT ops.operation, ops.ref_id, ops.user_id, usr.email,
                   ops.calls, ops.failed_calls, ops.unpriced_calls, ops.cost_usd,
                   ops.prompt_tokens, ops.cached_tokens, ops.completion_tokens, ops.thinking_tokens,
                   ops.latency_ms, ops.started_at, ops.finished_at
            FROM ops
            LEFT JOIN USERS usr ON usr.id = ops.user_id
            ORDER BY ops.finished_at DESC
            LIMIT %s
            """,
            params,
        )
        return _rows(cursor)
    finally:
        db.release_connection(conn)
