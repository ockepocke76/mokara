"""Admin: LLM cost insight — what strategy creation / evolution / Q&A /
report analysis actually cost us, per operation type and per user.

Reads LLM_USAGE (db.llm_usage), which core.llm fills on every Gemini call.
Own module (same gate as routers/admin.py) so it can grow without crowding
the users/jobs/system surface.
"""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_admin, verify_internal_secret

router = APIRouter(
    prefix="/admin/llm-usage",
    dependencies=[Depends(verify_internal_secret), Depends(require_admin)],
)


@router.get("/summary")
def usage_summary(
    window: int = Query(100, ge=1, le=1000),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Per-operation cost stats (and the per-step breakdown behind them)
    over the latest `window` operations of each type, plus spend totals over
    the last `days` and the list prices in force."""
    from core.llm import model_for_tier
    from core.llm_pricing import price_for
    from db import llm_usage

    steps: dict[str, list] = defaultdict(list)
    for row in llm_usage.step_stats(window=window):
        steps[row.pop('operation')].append(row)

    # Price list for the models that matter: the two configured tiers plus
    # anything that has actually been called (an override, a retired default).
    models = {model_for_tier('strong'), model_for_tier('fast'), *llm_usage.models_used()}
    return {
        "window": window,
        "operations": llm_usage.operation_stats(window=window),
        "steps": steps,
        "totals": llm_usage.totals(days=days),
        "prices": {
            model: (
                {"input": p.input, "output": p.output, "cached": p.cached,
                 "effective_from": p.effective_from.isoformat()}
                if (p := price_for(model)) is not None else None
            )
            for model in sorted(models)
        },
    }


@router.get("/operations")
def recent_operations(
    operation: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    from db import llm_usage

    return {"operations": llm_usage.recent_operations(operation=operation, limit=limit)}


@router.get("/operations/{operation}/{ref_id}")
def operation_detail(operation: str, ref_id: str) -> dict:
    """The individual calls of one operation (step, tier, tokens, cost)."""
    from db import llm_usage

    calls = llm_usage.operation_calls(operation, ref_id)
    if not calls:
        raise HTTPException(status_code=404, detail="no usage recorded for that operation")
    return {"operation": operation, "ref_id": ref_id, "calls": calls,
            "cost_usd": sum((c["cost_usd"] or 0) for c in calls)}


@router.get("/users")
def usage_by_user(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    from db import llm_usage

    return {"days": days, "users": llm_usage.user_totals(days=days, limit=limit)}


@router.get("/users/{user_id}")
def usage_for_user(user_id: int, limit: int = Query(50, ge=1, le=500)) -> dict:
    from db import llm_usage
    from db.database import db

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, name, plan_tier FROM USERS WHERE id = %s", (user_id,))
        row = cursor.fetchone()
    finally:
        db.release_connection(conn)
    if not row:
        raise HTTPException(status_code=404, detail="unknown user")
    return {
        "user": {"id": row[0], "email": row[1], "name": row[2], "tier": row[3]},
        "summary": llm_usage.user_summary(user_id),
        "operations": llm_usage.user_operations(user_id, limit=limit),
    }
