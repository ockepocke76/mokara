"""Admin: LLM cost insight — what strategy creation / evolution / Q&A /
report analysis actually cost us, per operation type and per user.

Reads LLM_USAGE (db.llm_usage), which core.llm fills on every Gemini call.
Own module (same gate as routers/admin.py) so it can grow without crowding
the users/jobs/system surface.
"""
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
    """Per-operation cost stats over the latest `window` operations of each
    type, plus spend totals over the last `days`."""
    import os

    from core.llm_pricing import price_for
    from db import llm_usage

    # Price list for the models that matter: the two configured tiers plus
    # anything that has actually been called (an override, a retired default).
    models = {
        os.environ.get('GEMINI_MODEL_STRONG', 'gemini-3.8-flash'),
        os.environ.get('GEMINI_MODEL_FAST', 'gemini-3.5-flash-lite'),
        *llm_usage.models_used(),
    }
    return {
        "window": window,
        "operations": llm_usage.operation_stats(window=window),
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


@router.get("/steps")
def usage_steps(
    operation: str,
    window: int = Query(100, ge=1, le=1000),
) -> dict:
    """Cost per graph step inside one operation type (where the money goes)."""
    from db import llm_usage

    return {"operation": operation, "window": window,
            "steps": llm_usage.step_stats(operation, window=window)}


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
