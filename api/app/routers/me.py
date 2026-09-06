"""Viewer identity/authorization profile for the BFF."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_current_user, verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class UpdateSettings(BaseModel):
    currency: str


@router.put("/me/settings")
def update_settings(
    body: UpdateSettings,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    from core.user_profile import UserProfileService, get_currency_options
    from db.database import db

    if body.currency not in get_currency_options():
        raise HTTPException(status_code=422, detail=f"Unknown currency: {body.currency}")
    ok = UserProfileService.update_user_profile(db, user["id"], currency=body.currency)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    return {"currency": body.currency}


@router.get("/me")
def me(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """
    The acting viewer's profile: identity, beta-access status, tier, admin
    flag, and settings the UI needs everywhere (currency).

    Anonymous viewers get {authenticated: False} plus beta status so the
    UI can render the login prompt variants.
    """
    from db.database import db

    if user is None:
        beta = _safe_beta_status()
        return {"authenticated": False, "beta": beta}

    tier = None
    try:
        tier = db.get_user_tier(user["id"])
    except Exception:
        logging.exception("get_user_tier failed for %s", user["id"])

    allowed = False
    try:
        allowed = bool(db.is_user_allowed(user["email"]))
    except Exception:
        logging.exception("is_user_allowed failed for %s", user["email"])

    currency = "SEK"
    try:
        from core.user_profile import UserProfileService
        profile = UserProfileService.get_user_profile(db, user["id"]) or {}
        currency = profile.get("currency", "SEK")
    except Exception:
        logging.exception("get_user_profile failed for %s", user["id"])

    return {
        "authenticated": True,
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "allowed": allowed,
        "is_admin": tier == "ADMIN",
        "tier": tier,
        "currency": currency,
        "beta": _safe_beta_status(),
    }


def _safe_beta_status() -> dict:
    from db.database import db
    try:
        return db.get_beta_status()
    except Exception:
        logging.exception("get_beta_status failed")
        return {"current_users": 0, "max_users": 0, "is_full": True, "percent_full": 1.0}
