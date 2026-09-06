"""Read-only public data: leaderboard, community stats, beta status."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])

CATEGORIES = ["ACCUMULATION_ONLY", "WITHDRAWAL_ONLY", "HYBRID"]

SCORE_FIELDS = [
    "excellence_score",
    "risk_score",
    "pv_score",
    "capital_efficiency_score",
    "purchasing_power_score",
    "robustness_score",
    "consumption_ratio_score",
    "stability_score",
    "legacy_score",
    "coast_fire_score",
    "accumulation_velocity_score",
    "contribution_efficiency_score",
    "sharpe_ratio_score",
    "calmar_ratio_score",
    "downside_stability_score",
    "ulcer_index_score",
]


@router.get("/leaderboard/meta")
def leaderboard_meta() -> dict:
    """Selector data: categories and weighting profiles."""
    from core.weighting_profiles import WEIGHTING_PROFILES

    return {
        "categories": CATEGORIES,
        "profiles": [
            {"key": key, "name": profile.get("name", key)}
            for key, profile in WEIGHTING_PROFILES.items()
        ],
    }


@router.get("/leaderboard")
def leaderboard(
    category: Optional[str] = Query(default=None),
    profile: str = Query(default="balanced"),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    from db.database import db

    rows = db.get_leaderboard_with_profile(
        profile_key=profile, category=category, limit=limit
    ) or []

    entries = []
    for rank, row in enumerate(rows, start=1):
        row = dict(row)
        # Same fallback the old UI applied: pre-calculated profile score if
        # backfilled, else the base excellence score.
        profile_score = row.get("profile_excellence_score")
        base_score = row.get("excellence_score") or 0
        score = profile_score if profile_score is not None else base_score
        entries.append(
            {
                "rank": rank,
                "id": row.get("id"),
                "strategy_name": row.get("strategy_name"),
                "category": row.get("strategy_category"),
                "is_custom": bool(row.get("is_custom")),
                "author": row.get("user_name"),
                "score": float(score) if score is not None else None,
                "scores": {
                    f: (float(row[f]) if row.get(f) is not None else None)
                    for f in SCORE_FIELDS
                },
                "created_at": row.get("created_at"),
            }
        )
    # Re-sort by the effective score (profile fallback can reorder)
    entries.sort(key=lambda e: e["score"] or 0, reverse=True)
    for rank, e in enumerate(entries, start=1):
        e["rank"] = rank
    return {"profile": profile, "category": category, "entries": entries}


@router.get("/community-stats")
def community_stats() -> dict:
    from db.database import db

    try:
        return db.get_community_stats()
    except Exception:
        logging.exception("get_community_stats failed")
        return {
            "total_simulations": 0,
            "total_strategies": 0,
            "total_years_simulated": 0,
            "top_strategies": [],
        }


@router.get("/beta-status")
def beta_status() -> dict:
    from db.database import db

    return db.get_beta_status()
