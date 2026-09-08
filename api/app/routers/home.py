"""
Home/landing content, simulation preview cards, asset explorer, and the
methodology flowchart — ports of the old app's pages/0_Dashboard.py,
ui/simulation_preview_card.py, pages/6_Assets.py and pages/7_Methodology.py.
"""
import json
import logging
import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, verify_internal_secret
from core.cache import ttl_cache

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


def _fig_json(fig) -> dict:
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# Simulation preview card (2 mini charts + category stats)
# ---------------------------------------------------------------------------

def _strategy_category(all_params: dict) -> str:
    try:
        from utils.strategy_utils import get_strategy_class

        strategy_identifier = all_params.get("strategy")
        if not strategy_identifier:
            return "UNKNOWN"
        strategy_class = get_strategy_class(strategy_identifier)
        if not strategy_class:
            return "UNKNOWN"
        return strategy_class(all_params).evaluation_category()
    except Exception:
        logging.warning("Failed to get strategy category", exc_info=True)
        return "UNKNOWN"


def _category_stats(final_stats: dict, all_params: dict, category: str, currency: str) -> List[dict]:
    """Port of ui/simulation_preview_card.calculate_category_specific_stats."""
    from core.currency_config import format_compact_currency

    stats: List[dict] = []
    median_final_nw = final_stats.get("median_final_net_worth", 0)
    stats.append({"label": "Median Final Net Worth", "value": format_compact_currency(median_final_nw, currency)})

    if category == "WITHDRAWAL_ONLY":
        ruin_prob = final_stats.get("chance_of_ruin", 0) * 100
        stats.append({"label": "Ruin Probability", "value": f"{ruin_prob:.1f}%"})
        years_left = final_stats.get("median_years_of_spending_left")
        if years_left is not None:
            years_fmt = f"{years_left:.0f}" if float(years_left).is_integer() else f"{years_left:.1f}"
            stats.append({"label": "Portfolio Longevity", "value": f"{years_fmt} years"})
        median_withdrawal = final_stats.get("median_total_withdrawn", 0) / max(all_params.get("num_years", 1), 1)
        stats.append({"label": "Median Annual Withdrawal", "value": format_compact_currency(median_withdrawal, currency)})
    elif category == "CONTRIBUTION_ONLY":
        total_contrib = final_stats.get("median_total_contributions", 0)
        stats.append({"label": "Total Contributions", "value": format_compact_currency(total_contrib, currency)})
        if total_contrib > 0:
            roi = ((median_final_nw / total_contrib) - 1) * 100
            stats.append({"label": "Return on Investment", "value": f"{roi:.1f}%"})
            years = all_params.get("num_years", 1)
            if years > 0:
                cagr = ((median_final_nw / total_contrib) ** (1 / years) - 1) * 100
                stats.append({"label": "CAGR", "value": f"{cagr:.1f}%"})
    elif category == "HYBRID":
        total_contrib = final_stats.get("median_total_contributions", 0)
        total_withdrawn = final_stats.get("median_total_withdrawn", 0)
        net_flow = total_contrib - total_withdrawn
        flow_label = "Net Contributions" if net_flow > 0 else "Net Withdrawals"
        stats.append({"label": flow_label, "value": format_compact_currency(abs(net_flow), currency)})
        success_rate = final_stats.get("success_rate")
        if success_rate is not None:
            stats.append({"label": "Success Rate", "value": f"{success_rate * 100:.1f}%"})
        p90_final = final_stats.get("p90_final_net_worth", median_final_nw)
        stats.append({"label": "Peak Portfolio (P90)", "value": format_compact_currency(p90_final, currency)})
    return stats


@ttl_cache(ttl=600, maxsize=32)
def _render_preview_json(simulation_hash: str, user_currency: Optional[str]) -> str:
    import pandas as pd

    from core.simulation_currency import get_simulation_currency
    from db.cache import get_simulation_final_stats_cached
    from reporting.interactive_plotting import (
        plot_portfolio_value_overview_interactive,
        plot_yearly_cash_flow_interactive,
    )

    final_stats, params, plot_data = get_simulation_final_stats_cached(simulation_hash)
    if not final_stats or not params:
        raise HTTPException(status_code=404, detail="Preview unavailable")

    currency = get_simulation_currency(params, user_currency=user_currency)
    category = _strategy_category(params)

    figures: Dict[str, Any] = {}
    try:
        fig1 = plot_portfolio_value_overview_interactive(
            df=pd.DataFrame(),
            params=params,
            final_stats=final_stats,
            precalculated_net_worth_paths=(plot_data or {}).get("net_worth_paths"),
            precalculated_asset_paths=(plot_data or {}).get("asset_paths"),
            currency=currency,
            theme="light",
            show_title=False,
        )
        fig1.update_layout(height=220, margin=dict(t=30, b=40, l=50, r=40))
        figures["portfolio"] = _fig_json(fig1)
    except Exception:
        logging.warning("preview portfolio plot failed", exc_info=True)
    try:
        fig2 = plot_yearly_cash_flow_interactive(
            final_stats=final_stats,
            params=params,
            currency=currency,
            theme="light",
            show_title=False,
        )
        fig2.update_layout(height=220, margin=dict(t=30, b=30, l=40, r=40))
        figures["cashflow"] = _fig_json(fig2)
    except Exception:
        logging.warning("preview cashflow plot failed", exc_info=True)

    return json.dumps(
        {
            "simulation_hash": simulation_hash,
            "figures": figures,
            "category": category,
            "stats": _category_stats(final_stats, params, category, currency),
        }
    )


@router.get("/simulations/{simulation_hash}/preview")
def simulation_preview(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
):
    from fastapi.responses import Response

    currency = None
    if user:
        try:
            from core.user_profile import UserProfileService
            from db.database import db

            profile = UserProfileService.get_user_profile(db, user["id"]) or {}
            currency = profile.get("currency")
        except Exception:
            pass
    return Response(
        content=_render_preview_json(simulation_hash, currency),
        media_type="application/json",
    )


# ---------------------------------------------------------------------------
# Home page payload (old pages/0_Dashboard.py dashboard_cache + content)
# ---------------------------------------------------------------------------

FACTS = [
    "The '4% Rule' was designed for bonds/stocks, not volatile assets.",
    "Monte Carlo simulations run thousands of possible futures to find hidden risks.",
    "A 'Success Rate' of 95% means failure in 1 out of 20 lifetimes.",
    "Sequence of Returns Risk is one of the biggest dangers to portfolio sustainability.",
    "Rebalancing annually can significantly reduce portfolio volatility.",
    "Most strategies fail not because of low returns, but because of panic selling.",
]


@router.get("/home")
def home_payload(user: Optional[dict] = Depends(get_current_user)) -> dict:
    from core.strategy_evaluation import METRIC_REGISTRY, TEST_SCENARIOS
    from core.weighting_profiles import WEIGHTING_PROFILES
    from db.database import db
    from reporting.content import get_glossary_data
    from reporting.radar_chart_data import create_radar_chart
    from utils.dashboard_utils import get_random_comparison_assets
    from utils.evaluation_info import (
        get_evaluation_settings_markdown,
        get_market_scenarios_markdown,
        get_score_components_markdown,
    )
    from utils.strategy_utils import get_strategy_description

    # Featured strategies (top 2 by excellence) with mini radar figures
    featured = []
    try:
        for strat in db.get_leaderboard(limit=2) or []:
            strat = dict(strat)
            desc = (
                strat.get("custom_description")
                or strat.get("ai_description")
                or get_strategy_description(strat.get("strategy_name", ""))
                or "No description available."
            )
            entry = {
                "id": strat.get("id"),
                "name": strat.get("strategy_name"),
                "author": strat.get("user_name") or "Community",
                "category": strat.get("strategy_category"),
                "excellence_score": float(strat.get("excellence_score") or 0),
                "description": desc,
            }
            try:
                fig = create_radar_chart(
                    strat, metric_source="METRIC_WEIGHTS", height=260
                )
                fig.update_layout(
                    margin=dict(t=20, b=20, l=40, r=40),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                entry["radar"] = _fig_json(fig)
            except Exception:
                logging.warning("featured radar failed", exc_info=True)
            featured.append(entry)
    except Exception:
        logging.exception("featured strategies failed")

    # Spotlights (randomized per load, like the old per-session cache)
    valid_metrics = [
        m
        for k, m in METRIC_REGISTRY.items()
        if k not in ["adequacy_score", "usability_score", "consumption_ratio_score"]
    ]
    metric = random.choice(valid_metrics) if valid_metrics else None
    profile_key, profile = random.choice(list(WEIGHTING_PROFILES.items()))

    terms_of_day = []
    try:
        all_terms = [
            (term, definition)
            for _, terms in get_glossary_data().items()
            for term, definition in terms.items()
        ]
        terms_of_day = random.sample(all_terms, min(5, len(all_terms)))
    except Exception:
        logging.warning("terms of day failed", exc_info=True)

    comparison_assets = []
    try:
        comparison_assets = get_random_comparison_assets(n=2) or []
    except Exception:
        logging.warning("comparison assets failed", exc_info=True)

    # Recent (viewer) or demo (guest) simulations for preview cards
    sims: List[dict] = []
    try:
        from db.cache import get_user_simulations_cached

        rows = get_user_simulations_cached(user["email"] if user else None) or []
        for row in rows[:2]:
            sims.append(
                {
                    "simulation_hash": row.get("simulation_hash"),
                    "name": row.get("simulation_name") or "Untitled Simulation",
                }
            )
    except Exception:
        logging.warning("home sims failed", exc_info=True)

    try:
        community_stats = db.get_community_stats()
    except Exception:
        community_stats = None

    try:
        beta = db.get_beta_status()
    except Exception:
        beta = {"is_full": False, "current_users": 0, "max_users": 100}

    return {
        "beta": beta,
        "community_stats": community_stats,
        "featured_strategies": featured,
        "spotlights": {
            "stress_scenario": random.choice(TEST_SCENARIOS),
            "score_metric": (
                {"name": metric.name, "description": metric.description}
                if metric
                else None
            ),
            "investor_profile": {
                "key": profile_key,
                "name": profile.get("name"),
                "emoji": profile.get("emoji"),
                "description": profile.get("description"),
            },
            "did_you_know": random.choice(FACTS),
            "terms_of_day": [
                {"term": t, "definition": d} for t, d in terms_of_day
            ],
            "comparison_assets": comparison_assets,
        },
        "evaluation_info": {
            "settings_markdown": get_evaluation_settings_markdown(),
            "scenarios_markdown": get_market_scenarios_markdown(),
            "score_components_markdown": get_score_components_markdown(),
        },
        "recent_simulations": sims,
    }


# ---------------------------------------------------------------------------
# Asset explorer (old pages/6_Assets.py)
# ---------------------------------------------------------------------------

@router.get("/assets")
def list_assets() -> dict:
    from config import CONFIG

    assets = []
    for key, model in CONFIG.get("asset_models", {}).items():
        if key == "_defaults" or not isinstance(model, dict):
            continue
        if model.get("enabled") is not True:
            continue
        params = []
        for pkey, conf in (model.get("parameters") or {}).items():
            if not isinstance(conf, dict) or conf.get("value") is None:
                continue
            value = conf.get("value")
            fmt = str(conf.get("slider_format", ""))
            if isinstance(value, (int, float)):
                if "%%" in fmt:
                    display = fmt % (value * 100)
                elif "%d" in fmt:
                    display = f"{int(value):,}"
                elif isinstance(value, float):
                    display = f"{value:,.4f}"
                else:
                    display = str(value)
            else:
                display = str(value)
            params.append(
                {
                    "label": conf.get("display_name", pkey),
                    "value": display,
                    "description": conf.get("description"),
                }
            )
        assets.append(
            {
                "key": key,
                "name": model.get("display_name", key),
                "ticker": model.get("ticker_symbol"),
                "type": model.get("type"),
                "description": model.get("description"),
                "params": params,
            }
        )
    return {"assets": assets}


@ttl_cache(ttl=3600, maxsize=16)
def _asset_history_json(asset_key: str) -> str:
    from config import CONFIG
    from core.data import load_and_prepare_data
    from reporting.interactive_plotting import plot_price_history_interactive

    model = CONFIG.get("asset_models", {}).get(asset_key)
    if not isinstance(model, dict):
        raise HTTPException(status_code=404, detail="Unknown asset")

    flattened = {
        k: (v.get("value") if isinstance(v, dict) and "value" in v else v)
        for k, v in (model.get("parameters") or {}).items()
    }
    params = {"asset_model": asset_key, **flattened}
    data_dict = load_and_prepare_data(params)
    if not data_dict or data_dict.get("prices") is None or data_dict["prices"].empty:
        raise HTTPException(status_code=404, detail="No price data for this asset")

    fig = plot_price_history_interactive(
        data_dict["prices"], model.get("display_name", asset_key), params, theme="light"
    )
    return json.dumps({"figure": _fig_json(fig)})


@router.get("/assets/{asset_key}/figure")
def asset_figure(asset_key: str):
    from fastapi.responses import Response

    return Response(content=_asset_history_json(asset_key), media_type="application/json")


# ---------------------------------------------------------------------------
# Methodology flowchart (old pages/7_Methodology.py mermaid)
# ---------------------------------------------------------------------------

@router.get("/methodology/flowchart")
def methodology_flowchart() -> dict:
    from reporting.content import get_methodology_flowchart_description
    from reporting.flowchart import get_simulation_flowchart_detailed_mermaid

    return {
        "description": get_methodology_flowchart_description(),
        "mermaid": get_simulation_flowchart_detailed_mermaid(),
    }
