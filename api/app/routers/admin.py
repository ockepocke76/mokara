"""Admin endpoints — tier-gated (engine tier 'ADMIN').

Ports the operational surface of the old separate admin_app.py:
users + tiers + beta allowlist, background jobs table, leaderboard
re-evaluation, migrations, and the system-reset danger zone.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin, verify_internal_secret

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(verify_internal_secret), Depends(require_admin)],
)

BUILTIN_EVALUATION_STRATEGIES = {
    "Trinity": "TrinityStrategy",
    "Buy Borrow Die": "BuyBorrowDieStrategy",
    "Get Rich Stay Rich": "GetRichStayRichStrategy",
}


@router.get("/users")
def list_users() -> dict:
    """Unified user view: registered users + pre-authorized allowlist entries."""
    from db.database import db

    users = []
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, name, plan_tier, tier_set_by, created_at FROM USERS ORDER BY id"
        )
        for u_id, email, name, tier, tier_set_by, created_at in cursor.fetchall():
            cursor.execute(
                "SELECT COUNT(*) FROM USER_SIMULATION_HISTORY WHERE user_id = %s AND is_removed = FALSE",
                (u_id,),
            )
            sim_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM CUSTOM_STRATEGIES WHERE user_id = %s", (u_id,)
            )
            strat_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT added_at FROM ALLOWED_USERS WHERE email = %s", (email.lower(),)
            )
            allowed_row = cursor.fetchone()
            users.append(
                {
                    "id": u_id,
                    "email": email,
                    "name": name,
                    "tier": tier,
                    "tier_set_by": tier_set_by,
                    "allowed": allowed_row is not None,
                    "simulations": sim_count,
                    "strategies": strat_count,
                    "joined": created_at,
                }
            )

        cursor.execute(
            """SELECT email, added_at FROM ALLOWED_USERS
               WHERE email NOT IN (SELECT email FROM USERS)"""
        )
        pending = [
            {
                "id": None,
                "email": email,
                "name": None,
                "tier": "FREE",
                "allowed": True,
                "pending_signup": True,
                "simulations": 0,
                "strategies": 0,
                "joined": added_at,
            }
            for email, added_at in cursor.fetchall()
        ]
    finally:
        db.release_connection(conn)

    from tier_config.limits import TIER_LIMITS

    return {
        "users": users + pending,
        "tiers": list(TIER_LIMITS.keys()) + ["ADMIN"],
    }


class SetTier(BaseModel):
    tier: str
    reason: Optional[str] = None


@router.post("/users/{user_id}/tier")
def set_tier(user_id: int, body: SetTier, admin: dict = Depends(require_admin)) -> dict:
    from db.database import db
    from tier_config.limits import TIER_LIMITS

    valid = set(TIER_LIMITS.keys()) | {"ADMIN"}
    if body.tier not in valid:
        raise HTTPException(status_code=422, detail=f"Unknown tier: {body.tier}")
    db.update_user_tier(
        user_id, body.tier, changed_by=admin["email"], reason=body.reason or "admin panel"
    )
    return {"user_id": user_id, "tier": body.tier}


class AllowUser(BaseModel):
    email: str
    notes: Optional[str] = None


@router.post("/allowed-users")
def allow_user(body: AllowUser, admin: dict = Depends(require_admin)) -> dict:
    from db.database import db

    db.add_allowed_user(body.email.lower(), added_by=admin["email"], notes=body.notes)
    return {"email": body.email.lower(), "allowed": True}


@router.delete("/allowed-users/{email}")
def revoke_user(email: str) -> dict:
    from db.database import db

    db.remove_allowed_user(email.lower())
    return {"email": email.lower(), "allowed": False}


class BulkAllowUsers(BaseModel):
    emails: list[str]


@router.post("/allowed-users/bulk")
def bulk_allow_users(body: BulkAllowUsers, admin: dict = Depends(require_admin)) -> dict:
    from db.database import db

    added: list[str] = []
    failed: list[str] = []
    for raw in body.emails:
        email = raw.strip().lower()
        if not email or email.startswith("#"):
            continue
        if db.add_allowed_user(email, added_by=admin["email"], notes="Bulk import"):
            added.append(email)
        else:
            failed.append(email)
    return {"added": added, "failed": failed}


SYSTEM_USER_ID = 0


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: dict = Depends(require_admin)) -> dict:
    from db.database import db

    if user_id == SYSTEM_USER_ID:
        raise HTTPException(status_code=403, detail="The system account cannot be deleted")
    if user_id == admin["id"]:
        raise HTTPException(status_code=403, detail="You cannot delete your own account")
    try:
        deleted = db.delete_users_by_id([user_id])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "deleted": True}


@router.get("/login-requests")
def list_login_requests(limit: int = 100) -> dict:
    from db.database import db

    return {"requests": db.get_login_requests(limit=limit) or []}


@router.post("/login-requests/{email}/approve")
def approve_login_request(email: str, admin: dict = Depends(require_admin)) -> dict:
    from db.database import db

    if not db.add_allowed_user(email.lower(), added_by=admin["email"], notes="Approved login request"):
        raise HTTPException(status_code=500, detail="Could not add user to the allowlist")
    db.delete_login_request(email.lower())
    return {"email": email.lower(), "approved": True}


@router.delete("/login-requests/{email}")
def dismiss_login_request(email: str) -> dict:
    from db.database import db

    db.delete_login_request(email.lower())
    return {"email": email.lower(), "dismissed": True}


@router.get("/system-settings/max-beta-users")
def get_beta_capacity() -> dict:
    from db.database import db

    try:
        max_beta_users = int(db.get_system_setting("max_beta_users", 50))
    except (TypeError, ValueError):
        logging.warning("max_beta_users setting is not an integer; showing default")
        max_beta_users = 50
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM allowed_users")
        current_allowed = cursor.fetchone()[0]
    finally:
        db.release_connection(conn)
    return {"max_beta_users": max_beta_users, "current_allowed": current_allowed}


class SetBetaCapacity(BaseModel):
    max_beta_users: int


@router.post("/system-settings/max-beta-users")
def set_beta_capacity(body: SetBetaCapacity) -> dict:
    from db.database import db

    if body.max_beta_users < 0:
        raise HTTPException(status_code=422, detail="max_beta_users must be >= 0")
    db.set_system_setting("max_beta_users", body.max_beta_users)
    return {"max_beta_users": body.max_beta_users}


@router.get("/jobs")
def list_jobs(
    job_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> dict:
    from services.background_manager import BackgroundManager

    jobs = BackgroundManager.list_jobs(job_type=job_type, status=status, limit=limit)
    return {
        "jobs": [
            {
                "id": j.get("id"),
                "job_type": j.get("job_type"),
                "status": j.get("status"),
                "created_at": j.get("created_at"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "retry_count": j.get("retry_count"),
                "error_message": j.get("error_message"),
                "user_id": j.get("user_id"),
            }
            for j in (jobs or [])
        ]
    }


@router.post("/evaluations/run")
def run_evaluations() -> dict:
    """Queue leaderboard re-evaluation jobs for all built-in + custom strategies."""
    from db.database import db
    from services.background_manager import BackgroundManager

    job_ids = []
    for name, cls in BUILTIN_EVALUATION_STRATEGIES.items():
        job_id = BackgroundManager.start_strategy_evaluation(
            strategy_class=cls, strategy_name=name, is_custom=False
        )
        if job_id:
            job_ids.append(job_id)

    customs = db.get_all_custom_strategies_for_admin() or []
    for cs in customs:
        job_id = BackgroundManager.start_strategy_evaluation(
            strategy_name=cs.get("strategy_name"),
            is_custom=True,
            user_id=cs.get("user_id"),
            custom_strategy_id=cs.get("id"),
            code=cs.get("code"),
            class_name=cs.get("class_name"),
            git_commit_sha=cs.get("git_commit_sha"),
        )
        if job_id:
            job_ids.append(job_id)

    return {"queued": len(job_ids), "job_ids": job_ids}


@router.post("/migrations/run")
def run_migrations() -> dict:
    from db.database import db

    try:
        db.run_migrations()
        return {"ok": True}
    except Exception as e:
        logging.exception("migrations failed")
        raise HTTPException(status_code=500, detail=str(e))


class SystemReset(BaseModel):
    admin_password: str
    confirmation_text: str


@router.post("/system-reset")
def system_reset(body: SystemReset) -> dict:
    """DANGER: wipes the database. Same double confirm as the old admin app."""
    from core.admin_logic import perform_system_reset

    try:
        ok = perform_system_reset(body.admin_password, body.confirmation_text)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=500, detail="System reset failed")
    return {"reset": True}
