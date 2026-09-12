"""Per-resource access checks shared by routers.

Simulation hashes are deterministic functions of the input parameters, not
unguessable capabilities, and the cached-simulation store is content-
addressed and shared between users. The rules therefore are:

- READ (results, report, PDF status/download): the sim must be public, or
  the viewer must have a live history entry for it.
- MUTATE (delete, queue PDF): the acting user must have their own live
  history entry for it — someone else's public sim is never "owned".

Both checks answer with 404 (never 403) so the existence of private
simulations is not confirmed to other users.
"""
from typing import Optional

from fastapi import HTTPException


def _access_or_404(simulation_hash: str, user: Optional[dict]) -> dict:
    from db.database import db

    access = db.get_simulation_access(
        simulation_hash, user["id"] if user else None
    )
    if access is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return access


def require_simulation_view(simulation_hash: str, user: Optional[dict]) -> dict:
    """Own-or-public gate for read endpoints; anonymous viewers get public only."""
    access = _access_or_404(simulation_hash, user)
    if not access["is_public"] and access["history_id"] is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return access


def require_simulation_owner(simulation_hash: str, user: dict) -> dict:
    """Own-history gate for mutating endpoints (delete, PDF queue)."""
    access = _access_or_404(simulation_hash, user)
    if access["history_id"] is None:
        raise HTTPException(
            status_code=404, detail="Simulation not in your history"
        )
    return access


def own_history_rows(user: dict) -> list:
    """The user's own live history rows.

    get_user_simulations_with_params also returns other users' public sims
    (its query serves the shared/public listing too) — every app-layer use
    of "my history" must filter to rows the user actually owns.
    """
    from db.database import db

    rows = db.get_user_simulations_with_params(user["email"]) or []
    return [dict(r) for r in rows if r.get("user_id") == user["id"]]
