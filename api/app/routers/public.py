"""Read-only public data: leaderboard, community stats, beta status.

Leaderboard design (ported deliberately from ui/strategy_leaderboard.py):
the board is CATEGORY-SCOPED — evaluation metrics and investor profiles only
exist within a category, so there is no cross-category ranking. Profiles
cascade from the chosen category (get_profiles_for_category) and the ranking
score is the profile-weighted excellence score with base-score fallback.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user, verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])

# Audience-framed category options (old selector, incl. default order)
CATEGORY_OPTIONS = [
    {
        "key": "CONTRIBUTION_ONLY",
        "label": "💰 Accumulation Strategies",
        "description": "Strategies that maximize long-term wealth through regular contributions. For savers, investors, and wealth builders.",
    },
    {
        "key": "WITHDRAWAL_ONLY",
        "label": "🏖️ Withdrawal Strategies",
        "description": "Strategies that generate sustainable income from existing capital. For retirees and FIRE followers.",
    },
    {
        "key": "HYBRID",
        "label": "🔄 Lifecycle Strategies",
        "description": "Dynamic strategies that adapt across accumulation and withdrawal phases. For target-date and adaptive approaches.",
    },
]
DEFAULT_CATEGORY = "WITHDRAWAL_ONLY"

# Canonical metric display order (old ui/metric_display.get_metric_display_order)
METRIC_DISPLAY_ORDER = [
    ("pv_score", "Present Value"),
    ("purchasing_power_score", "Purchasing Power"),
    ("stability_score", "Stability"),
    ("risk_score", "Risk Score"),
    ("capital_efficiency_score", "Capital Efficiency"),
    ("legacy_score", "Legacy"),
    ("robustness_score", "Robustness"),
    ("coast_fire_score", "Coast FIRE"),
    ("accumulation_velocity_score", "Accumulation Velocity"),
    ("contribution_efficiency_score", "Contribution Efficiency"),
    ("consumption_ratio_score", "Consumption Ratio"),
]

EXCLUDED_METRICS = {"adequacy_score", "usability_score"}


def _profiles_for_category(category: str) -> List[dict]:
    from core.strategy_evaluation import METRIC_REGISTRY
    from core.weighting_profiles import WEIGHTING_PROFILES, get_profiles_for_category

    out = []
    for key in get_profiles_for_category(category):
        profile = WEIGHTING_PROFILES[key]
        weights = []
        for mkey, weight in sorted(
            profile.get("weights", {}).items(), key=lambda x: x[1], reverse=True
        ):
            metric = METRIC_REGISTRY.get(mkey)
            if not metric or mkey in EXCLUDED_METRICS:
                continue
            if not metric.is_applicable(category):
                continue
            weights.append(
                {
                    "key": mkey,
                    "name": metric.name,
                    "description": metric.description,
                    "weight": weight,
                }
            )
        out.append(
            {
                "key": key,
                "name": profile.get("name", key),
                "emoji": profile.get("emoji"),
                "description": profile.get("description"),
                "detailed_description": profile.get("detailed_description"),
                "is_balanced": "balanced" in key,
                "weights": weights,
            }
        )
    return out


@router.get("/leaderboard/meta")
def leaderboard_meta() -> dict:
    """Selector data: audience-framed categories, cascaded profiles, and
    per-category evaluation documentation."""
    from utils.evaluation_info import (
        get_evaluation_settings_markdown,
        get_market_scenarios_markdown,
        get_score_components_markdown,
        get_wisdom_of_crowd_markdown,
    )

    profiles_by_category = {}
    evaluation_info = {}
    for cat in CATEGORY_OPTIONS:
        key = cat["key"]
        profiles_by_category[key] = _profiles_for_category(key)
        evaluation_info[key] = {
            "settings_markdown": get_evaluation_settings_markdown(),
            "scenarios_markdown": get_market_scenarios_markdown(),
            "score_components_markdown": get_score_components_markdown(category=key),
            "wisdom_markdown": get_wisdom_of_crowd_markdown(),
        }

    return {
        "categories": CATEGORY_OPTIONS,
        "default_category": DEFAULT_CATEGORY,
        "profiles_by_category": profiles_by_category,
        "evaluation_info": evaluation_info,
    }


def _source_badge(row: dict, viewer_id: Optional[int]) -> str:
    """Old badge_helpers source badge (leaderboard context shows source only)."""
    if not row.get("is_custom"):
        return "🏛️"
    user_id = row.get("user_id")
    if user_id and viewer_id and user_id != viewer_id:
        return "🌐"
    return "✨"


def _resolve_description(row: dict) -> Optional[str]:
    if row.get("ai_description"):
        return row["ai_description"]
    if row.get("custom_description"):
        return row["custom_description"]
    if not row.get("is_custom"):
        try:
            from utils.strategy_utils import get_strategy_description

            return get_strategy_description(row.get("strategy_name", ""))
        except Exception:
            return None
    return None


def _metric_grid(row: dict, category: str, profile_weights: Dict[str, float]) -> List[dict]:
    """Old ui/metric_display.get_applicable_metrics: category-applicable,
    non-null metrics in canonical order, with profile weights."""
    from core.strategy_evaluation import METRIC_REGISTRY

    grid = []
    for key, display_name in METRIC_DISPLAY_ORDER:
        score = row.get(key)
        if score is None:
            continue
        metric = METRIC_REGISTRY.get(key)
        if not metric:
            continue
        if not metric.is_applicable(category):
            continue
        weight = profile_weights.get(key, getattr(metric, "weight", 0) or 0)
        grid.append(
            {
                "key": key,
                "name": display_name,
                "score": float(score),
                "weight": float(weight),
            }
        )
    return grid


def _builtin_strategy_id(strategy_name: str) -> Optional[int]:
    from db.database import db

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM CUSTOM_STRATEGIES WHERE user_id = 0 AND strategy_name = %s LIMIT 1",
            (strategy_name,),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        db.release_connection(conn)


@router.get("/leaderboard")
def leaderboard(
    category: str = Query(default=DEFAULT_CATEGORY),
    profile: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    from core.weighting_profiles import WEIGHTING_PROFILES, get_profiles_for_category
    from db.database import db

    valid_categories = {c["key"] for c in CATEGORY_OPTIONS}
    if category not in valid_categories:
        raise HTTPException(status_code=422, detail=f"Unknown category: {category}")

    available = get_profiles_for_category(category)
    if profile is None or profile not in available:
        # Default to the category's balanced variant (old selector behavior)
        profile = next((k for k in available if "balanced" in k), available[0])
    profile_info = WEIGHTING_PROFILES[profile]
    profile_weights = profile_info.get("weights", {})

    rows = db.get_leaderboard_with_profile(
        profile_key=profile, category=category, limit=limit
    ) or []

    viewer_id = user["id"] if user else None

    entries = []
    for row in rows:
        row = dict(row)
        profile_score = row.get("profile_excellence_score")
        base_score = row.get("excellence_score") or 0
        score = profile_score if profile_score is not None else base_score

        scenario_results = []
        try:
            for s in json.loads(row.get("scenario_results_json") or "[]"):
                scenario_results.append(
                    {
                        "name": s.get("name"),
                        "sortino_ratio": s.get("sortino_ratio"),
                        "success_rate": s.get("success_rate"),
                    }
                )
        except Exception:
            pass

        custom_strategy_id = row.get("custom_strategy_id")
        clone_target_id = None
        in_library = False
        if row.get("is_custom"):
            clone_target_id = custom_strategy_id
        else:
            try:
                clone_target_id = _builtin_strategy_id(row.get("strategy_name", ""))
            except Exception:
                logging.warning("builtin lookup failed", exc_info=True)
        if viewer_id and clone_target_id:
            try:
                from services.strategy_clone import has_user_cloned_strategy

                in_library = has_user_cloned_strategy(viewer_id, clone_target_id, db)
            except Exception:
                logging.warning("clone check failed", exc_info=True)

        entries.append(
            {
                "id": row.get("id"),
                "strategy_name": row.get("strategy_name"),
                "badge": _source_badge(row, viewer_id),
                "category": row.get("strategy_category"),
                "is_custom": bool(row.get("is_custom")),
                "author": row.get("user_name") if user else None,
                "score": float(score) if score is not None else None,
                "description": _resolve_description(row),
                "metric_grid": _metric_grid(row, category, profile_weights),
                "scenario_results": scenario_results,
                "usage_clone_count": row.get("usage_clone_count") or 0,
                "usage_fork_count": row.get("usage_fork_count") or 0,
                "clone_target_id": clone_target_id,
                "in_library": in_library,
                "created_at": row.get("created_at"),
            }
        )

    # Re-sort by effective score (profile fallback can reorder) and rank
    entries.sort(key=lambda e: e["score"] or 0, reverse=True)
    for rank, e in enumerate(entries, start=1):
        e["rank"] = rank

    return {
        "category": category,
        "profile": profile,
        "profile_name": profile_info.get("name"),
        "profile_is_balanced": "balanced" in profile,
        "total": len(entries),
        "entries": entries,
    }


@router.get("/leaderboard/{evaluation_id}/radar")
def leaderboard_radar(
    evaluation_id: int,
    category: str = Query(default=DEFAULT_CATEGORY),
    profile: str = Query(default="balanced_withdrawal"),
) -> dict:
    """Radar chart for one entry, weighted by the active profile."""
    from core.weighting_profiles import WEIGHTING_PROFILES
    from db.database import db
    from reporting.radar_chart_data import create_radar_chart

    rows = db.get_leaderboard_with_profile(
        profile_key=profile, category=category, limit=500
    ) or []
    row = next((dict(r) for r in rows if r.get("id") == evaluation_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    weights = (WEIGHTING_PROFILES.get(profile) or {}).get("weights")
    fig = create_radar_chart(
        row,
        profile_weights=weights,
        strategy_name=row.get("strategy_name"),
        height=320,
    )
    return {"figure": json.loads(fig.to_json())}


class _CloneBody:
    pass


@router.post("/leaderboard/{evaluation_id}/clone")
def clone_leaderboard_strategy(
    evaluation_id: int,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Clone a leaderboard strategy into the viewer's library (old Clone CTA)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to clone")
    from db.database import db
    from services.strategy_clone import clone_strategy, has_user_cloned_strategy

    rows = db.get_leaderboard_with_profile(profile_key="balanced", limit=500) or []
    row = next((dict(r) for r in rows if r.get("id") == evaluation_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    if row.get("is_custom"):
        target_id = row.get("custom_strategy_id")
    else:
        target_id = _builtin_strategy_id(row.get("strategy_name", ""))
    if not target_id:
        raise HTTPException(
            status_code=409, detail="Clone not available for this strategy"
        )

    if has_user_cloned_strategy(user["id"], target_id, db):
        return {"cloned": False, "in_library": True}

    result = clone_strategy(strategy_id=target_id, user_id=user["id"], db=db)
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Clone failed")
        )
    return {"cloned": True, "in_library": True, "strategy_id": result.get("strategy_id")}


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
