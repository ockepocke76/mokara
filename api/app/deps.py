"""
FastAPI dependencies: internal auth between the Next.js BFF and this API.

The browser never talks to this API directly. Next.js route handlers call it
with:
  - X-Internal-Secret: shared secret (INTERNAL_API_SECRET env var)
  - X-User-Email / X-User-Name: identity claims of the authenticated user
    (absent for anonymous visitors)

get_current_user returns a user dict shaped like the engine expects
({'email', 'name', 'id'}) or None for anonymous requests.
"""
import hmac
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException

from core.secrets import get_secret


def verify_internal_secret(x_internal_secret: str = Header(default="")) -> None:
    expected = get_secret("INTERNAL_API_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="INTERNAL_API_SECRET not configured")
    if not hmac.compare_digest(x_internal_secret.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid internal secret")


def get_current_user(
    x_user_email: Optional[str] = Header(default=None),
    x_user_name: Optional[str] = Header(default=None),
) -> Optional[dict]:
    """Resolve the acting user from BFF headers; None = anonymous."""
    if not x_user_email:
        return None
    from db.database import db
    try:
        user_id = db.get_or_create_user_id(x_user_email, x_user_name)
    except Exception:
        logging.exception("Failed to resolve user id for %s", x_user_email)
        raise HTTPException(status_code=500, detail="user resolution failed")
    return {'email': x_user_email, 'name': x_user_name, 'id': user_id}


def require_user(user: Optional[dict] = None) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def require_admin(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Admin = tier 'ADMIN' in the engine DB (same rule as the old app)."""
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    from db.database import db

    try:
        tier = db.get_user_tier(user["id"])
    except Exception:
        logging.exception("admin tier lookup failed for %s", user["id"])
        raise HTTPException(status_code=500, detail="tier lookup failed")
    if tier != "ADMIN":
        raise HTTPException(status_code=403, detail="admin access required")
    return user
