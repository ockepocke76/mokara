"""
Run Simulation flow: parameter schema, job submission, polling, results.

POST /simulations is the API port of the old ui/main_app_logic._start_simulation:
assemble params -> validate -> hash -> cache check -> history -> queue job.
The UI-only behavior (toasts, rerun loops, progress bars) maps to response
statuses the frontend acts on: 'cached' | 'running' | 'queued'.
"""
import logging
import os
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_current_user, verify_internal_secret
from core.cache import ttl_cache

router = APIRouter(dependencies=[Depends(verify_internal_secret)])

PERCENT_FORMAT = "%%"


def _param_spec(key: str, conf: Dict[str, Any], default_key: str = "value") -> Optional[Dict[str, Any]]:
    """Normalize an engine parameter config into a UI-agnostic spec."""
    if not isinstance(conf, dict):
        return None
    has_default = default_key in conf or "default" in conf
    default = conf.get(default_key, conf.get("default"))
    spec: Dict[str, Any] = {
        "key": key,
        "label": conf.get("display_name") or key.replace("_", " ").title(),
        "description": conf.get("description"),
        "default": default,
    }
    if "options" in conf:
        spec["type"] = "select"
        spec["options"] = conf["options"]
        if "captions" in conf:
            spec["captions"] = conf["captions"]
        return spec
    if isinstance(default, bool):
        spec["type"] = "boolean"
        return spec
    if "min" in conf or "max" in conf:
        spec["type"] = "number"
        spec["min"] = conf.get("min")
        spec["max"] = conf.get("max")
        spec["step"] = conf.get("step")
        spec["is_percent"] = PERCENT_FORMAT in str(conf.get("slider_format", ""))
        spec["is_currency"] = bool(conf.get("is_currency"))
        return spec
    if has_default:
        spec["type"] = "text"
        return spec
    return None


# Conditional visibility of Buy-Borrow-Die params (ported from the old sidebar)
BBD_VISIBILITY = {
    "fixed_drawdown": {"param": "drawdown_method", "equals": "fixed"},
    "initial_percentage_rate": {"param": "drawdown_method", "equals": "initial_percentage"},
    "percentage_rate": {"param": "drawdown_method", "equals": "percentage"},
    "max_drawdown": {"param": "drawdown_method", "equals": "percentage"},
    "ltv_warning_threshold": {"param": "enable_tiered_ltv", "truthy": True},
    "ltv_action_threshold": {"param": "enable_deleveraging", "truthy": True},
    "deleveraging_target": {"param": "enable_deleveraging", "truthy": True},
}

STRATEGY_LABELS = {
    "trinity": "Trinity (Asset Withdrawal)",
    "buy_borrow_die": "Buy, Borrow, Die",
    "get_rich_stay_rich": "Get Rich, Stay Rich",
}


def _custom_param_spec(key: str, conf: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort ParamSpec from a custom strategy's simpler {default, description}
    shape — no min/max/type metadata exists for user-authored strategies."""
    if not isinstance(conf, dict) or "default" not in conf:
        return None
    default = conf["default"]
    if isinstance(default, bool):
        ptype = "boolean"
    elif isinstance(default, (int, float)):
        ptype = "number"
    else:
        ptype = "text"
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "description": conf.get("description"),
        "default": default,
        "type": ptype,
    }


def _custom_strategy_spec(row: Dict[str, Any], user_id: int) -> Optional[Dict[str, Any]]:
    from db.database import db

    if not row.get("code"):
        return None
    params_json = db.deserialize_json_column(row.get("parameters_json")) or {}
    params = [spec for pkey, conf in params_json.items() if (spec := _custom_param_spec(pkey, conf))]
    validated = row.get("validation_status") == "validated"
    is_owner = row.get("user_id") == user_id
    return {
        "key": f"custom:{row['id']}",
        "name": row.get("strategy_name") or f"Strategy {row['id']}",
        "description": row.get("description"),
        "params": params,
        "group": "mine" if is_owner else "community",
        "is_custom": True,
        "disabled": not validated,
        "disabled_reason": None if validated else "Not validated yet — finish validation in the strategy designer before running it here.",
    }


@router.get("/config/params")
def config_params(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """The config-driven parameter schema that drives the simulate form."""
    from config import CONFIG
    from core.strategy import BuyBorrowDieStrategy, TrinityStrategy
    from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy

    strategy_classes = {
        "trinity": TrinityStrategy,
        "buy_borrow_die": BuyBorrowDieStrategy,
        "get_rich_stay_rich": GetRichStayRichStrategy,
    }

    strategies = []
    for key, cls in strategy_classes.items():
        try:
            defs = cls({}).parameters or {}
        except Exception:
            logging.exception("parameter defs failed for %s", key)
            defs = {}
        params = []
        for pkey, conf in defs.items():
            spec = _param_spec(pkey, conf, default_key="default")
            if spec is None:
                continue
            if key == "buy_borrow_die" and pkey in BBD_VISIBILITY:
                spec["visible_if"] = BBD_VISIBILITY[pkey]
            params.append(spec)
        strategies.append(
            {
                "key": key,
                "name": STRATEGY_LABELS.get(key, key),
                "description": CONFIG.get("strategies", {}).get(key, {}).get("description"),
                "params": params,
                "group": "builtin",
            }
        )

    if user:
        from db.database import db

        custom_rows = db.get_user_custom_strategies(user["id"]) or []
        for row in custom_rows:
            spec = _custom_strategy_spec(row, user["id"])
            if spec is not None:
                strategies.append(spec)

    assets = []
    for key, model in CONFIG.get("asset_models", {}).items():
        if key == "_defaults" or not isinstance(model, dict):
            continue
        if not model.get("enabled", True):
            continue
        params = []
        for pkey, conf in (model.get("parameters") or {}).items():
            spec = _param_spec(pkey, conf)
            if spec is not None:
                params.append(spec)
        assets.append(
            {
                "key": key,
                "name": model.get("display_name", key),
                "type": model.get("type"),
                "description": model.get("description"),
                "params": params,
            }
        )

    # (ui param key, config section, config key) — ui key is what the engine
    # reads from assembled params (the old sidebar's layout keys).
    sections = []
    for title, keys in [
        ("Simulation Settings", [
            ("num_simulations", "simulation", "num_simulations"),
            ("initial_investment", "simulation", "initial_investment"),
        ]),
        ("Economic Assumptions", [
            ("inflation_rate", "simulation", "inflation_rate"),
            ("cash_interest_rate", "simulation", "cash_interest_rate"),
        ]),
        ("Tax Settings", [
            ("tax_method", "tax", "method"),
            ("isk_tax_rate", "tax", "isk_tax_rate"),
            ("capital_gains_tax_rate", "tax", "capital_gains_tax_rate"),
        ]),
    ]:
        params = []
        for ui_key, section_key, config_key in keys:
            conf = CONFIG.get(section_key, {}).get(config_key)
            spec = _param_spec(ui_key, conf) if conf else None
            if spec is not None:
                params.append(spec)
        sections.append({"title": title, "params": params})

    return {
        "strategies": strategies,
        "assets": assets,
        "sections": sections,
        "defaults": {
            "strategy": CONFIG["simulation"]["strategy"]["value"],
            "asset_model": CONFIG["simulation"]["asset_model"]["value"],
        },
    }


class CreateSimulation(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)
    simulation_name: Optional[str] = None
    # Sim-limit flow (old confirm-delete-oldest dialog): when the user is at
    # their tier's cap, the first submit returns 409 with the sims that would
    # be deleted; a resubmit with replace_oldest=True deletes them and runs.
    replace_oldest: bool = False


@router.post("/simulations")
def create_simulation(
    body: CreateSimulation,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    from core.shared_logic import assemble_params, generate_simulation_hash
    from core.secrets import get_secret
    from db.database import db
    from services.background_manager import BackgroundManager
    from validation import validate_params
    from version import get_component_hashes

    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to run simulations")
    if not db.is_user_allowed(user["email"]):
        raise HTTPException(status_code=403, detail="Beta access is full")

    # AI-credit gate (same as the old flow)
    from core.limits import LimitEnforcer

    limiter = LimitEnforcer(db)
    allowed, msg, _ = limiter.check_ai_credits(user["id"])
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)

    # Saved-simulation cap (old _handle_run_button_click confirm flow)
    sim_ok, sim_msg, usage = limiter.check_simulation_limit(user["id"])
    if not sim_ok:
        from app.access import own_history_rows

        limit = usage.get("limit")
        rows = own_history_rows(user)
        rows = sorted(rows, key=lambda r: r.get("timestamp") or "")
        overflow = max(1, len(rows) - int(limit) + 1) if isinstance(limit, int) else 1
        oldest = rows[:overflow]
        if not body.replace_oldest:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": sim_msg,
                    "limit": limit,
                    "to_delete": [
                        {
                            "history_id": r.get("id"),
                            "name": r.get("simulation_name"),
                            "created_at": str(r.get("timestamp")),
                        }
                        for r in oldest
                    ],
                },
            )
        from core.cache import clear_all

        for r in oldest:
            db.permanently_delete_simulation(r["id"])
        clear_all()

    ui_params = dict(body.params)
    if body.simulation_name:
        ui_params["simulation_name"] = body.simulation_name

    # custom_strategy_* fields must only ever be populated by the trusted DB
    # lookup below — never trust them if the client supplied them directly
    # (that would let a "strategy": "custom" request run arbitrary code with
    # no ownership or validation_status check at all).
    for key in (
        "custom_strategy_code", "custom_strategy_class_name", "custom_strategy_name",
        "custom_strategy_description", "custom_strategy_ai_description",
        "custom_strategy_id", "custom_strategy_param_defs", "custom_strategy_params",
    ):
        ui_params.pop(key, None)

    strategy_value = str(ui_params.get("strategy", ""))
    if strategy_value == "custom":
        # Bare 'custom' is the internal execution sentinel this branch sets
        # below (as "custom:<id>") — never a valid selector on its own.
        raise HTTPException(status_code=400, detail="Unknown strategy")
    if strategy_value.startswith("custom:"):
        from app.routers.strategies import _owned_strategy

        try:
            strategy_id = int(strategy_value.split(":", 1)[1])
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid strategy id")
        custom_strategy = _owned_strategy(strategy_id, user)
        if custom_strategy.get("validation_status") != "validated":
            raise HTTPException(status_code=422, detail="This strategy has not been validated yet")
        if not custom_strategy.get("code"):
            raise HTTPException(status_code=422, detail="Strategy has no runnable code")
        if not custom_strategy.get("class_name"):
            raise HTTPException(status_code=422, detail="Strategy has no class name")
        ui_params["strategy"] = "custom"
        ui_params["custom_strategy_code"] = custom_strategy["code"]
        ui_params["custom_strategy_class_name"] = custom_strategy["class_name"]
        ui_params["custom_strategy_name"] = custom_strategy.get("strategy_name")
        ui_params["custom_strategy_description"] = custom_strategy.get("description")
        ui_params["custom_strategy_ai_description"] = custom_strategy.get("ai_description")
        ui_params["custom_strategy_id"] = custom_strategy["id"]
        ui_params["custom_strategy_param_defs"] = (
            db.deserialize_json_column(custom_strategy.get("parameters_json")) or {}
        )

    full = assemble_params(ui_params)

    if full.get("strategy") == "custom":
        # Resolved parameter values (post-assemble: user overrides, falling
        # back to the strategy's own recorded default when the client didn't
        # send that key — e.g. a slider left untouched) for the PDF settings
        # table and Gemini analysis prompt.
        full["custom_strategy_params"] = {
            k: full[k] if k in full else conf.get("default")
            for k, conf in full.get("custom_strategy_param_defs", {}).items()
        }
        limit = limiter.get_mc_iterations_limit(user["id"], is_custom_strategy=True)
        if limit <= 0:
            raise HTTPException(
                status_code=403,
                detail="Your plan does not include running custom strategies.",
            )
        try:
            requested = int(full.get("num_simulations", 1000))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail={"num_simulations": "must be a number"})
        full["num_simulations"] = min(requested, limit)

    # Currency from the user's profile unless explicitly set
    if "currency" not in full:
        try:
            from core.user_profile import UserProfileService

            profile = UserProfileService.get_user_profile(db, user["id"]) or {}
            full["currency"] = profile.get("currency", "SEK")
        except Exception:
            full["currency"] = "SEK"

    full["user_email"] = user["email"]
    full["user_name"] = user.get("name")

    gemini_api_key = get_secret("GEMINI_API_KEY")
    if gemini_api_key:
        full["gemini_api_key"] = gemini_api_key

    errors = validate_params(full)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    simulation_hash = generate_simulation_hash(full)
    cache_status, results_id, stored_hashes = db.check_simulation_cache(simulation_hash)

    simulation_name = full.get("simulation_name", "Untitled Simulation")

    def ensure_history() -> None:
        from app.access import own_history_rows

        history = own_history_rows(user)
        if not any(s.get("simulation_hash") == simulation_hash for s in history):
            db.add_to_user_history(user["id"], simulation_hash, simulation_name)
            from db.cache import get_user_simulations_cached

            get_user_simulations_cached.clear()

    if cache_status in ("PENDING", "RUNNING"):
        ensure_history()
        existing = db.get_job_by_idempotency_key(f"sim_{simulation_hash}")
        return {
            "status": "running",
            "simulation_hash": simulation_hash,
            "job_id": str(existing["id"]) if existing else None,
        }

    full["component_hashes"] = get_component_hashes()

    if cache_status is None:
        db.create_cached_simulation_entry(simulation_hash, full)

    ensure_history()

    if cache_status == "COMPLETED":
        current_hashes = get_component_hashes()
        is_stale = stored_hashes is not None and stored_hashes != current_hashes
        if not is_stale:
            return {"status": "cached", "simulation_hash": simulation_hash}
        # Stale cache: re-run with replacement flag (old UI behavior)
        full["is_replacement_run"] = True

    job_id = BackgroundManager.start_simulation(full, user=user)
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to queue simulation job")
    return {"status": "queued", "simulation_hash": simulation_hash, "job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    from db.database import db
    from services.background_manager import BackgroundManager

    status = BackgroundManager.poll_job_status(job_id)
    # Progress lives in the job payload (worker updates it there)
    try:
        job = db.get_job_by_id(job_id)
        payload = (job or {}).get("payload") or {}
        status["progress_value"] = payload.get("progress_value")
        status["progress_message"] = payload.get("progress_message")
    except Exception:
        pass
    return status


@router.get("/simulations/{simulation_hash}/results")
def simulation_results(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Chart series + stats for a completed simulation (own or public)."""
    import pandas as pd

    from app.access import require_simulation_view
    from db.regeneration_db import get_regeneration_data
    from db.utils import _sanitize_for_json

    require_simulation_view(simulation_hash, user)

    package = get_regeneration_data(simulation_hash)
    if not package:
        raise HTTPException(status_code=404, detail="Simulation results not found")

    params = package.get("params") or {}
    stats = dict(package.get("stats") or {})
    stats.pop("drawdown_data", None)  # pandas Series; charted from paths instead
    pre = package.get("precalculated_data") or {}

    def df_series(key: str) -> Optional[dict]:
        df = pre.get(key)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None
        return {
            "index": _sanitize_for_json(list(df.index)),
            "series": {str(c): _sanitize_for_json(df[c].tolist()) for c in df.columns},
        }

    def sampled_net_worth() -> Optional[dict]:
        """sampled_paths rows are (year, metric) — extract the Net Worth slice."""
        df = pre.get("sampled_paths")
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None
        try:
            if isinstance(df.index, pd.MultiIndex):
                nw = df.xs("Net Worth", level=1)
            else:
                mask = [
                    isinstance(i, tuple) and len(i) == 2 and i[1] == "Net Worth"
                    for i in df.index
                ]
                if not any(mask):
                    return None
                nw = df[mask]
                nw.index = [i[0] for i in nw.index]
            nw = nw.sort_index()
            return {
                "index": _sanitize_for_json(list(nw.index)),
                "series": {str(c): _sanitize_for_json(nw[c].tolist()) for c in nw.columns},
            }
        except Exception:
            logging.exception("sampled_paths net-worth extraction failed")
            return None

    display_params = {
        k: params.get(k)
        for k in (
            "strategy",
            "custom_strategy_name",
            "asset_model",
            "asset_name",
            "num_years",
            "num_simulations",
            "initial_investment",
            "currency",
            "simulation_name",
            "inflation_rate",
        )
    }

    return {
        "simulation_hash": simulation_hash,
        "params": display_params,
        "stats": _sanitize_for_json(stats),
        "gemini_content": package.get("gemini_content"),
        "charts": {
            "net_worth_percentile_paths": df_series("net_worth_percentile_paths"),
            "asset_percentile_paths": df_series("asset_percentile_paths"),
            "sampled_paths": sampled_net_worth(),
            "final_net_worths_hist": _sanitize_for_json(pre.get("final_net_worths_hist")),
            "median_yearly_results": df_series("median_yearly_results_df"),
        },
    }


# ---------------------------------------------------------------------------
# Full report — the old Streamlit results view, served as an item stream.
# Runs the same engine renderer (background_tasks.regenerate_ui_results) and
# returns its ordered typed items; Plotly figures are serialized to JSON so
# the web app renders the identical charts (light theme per config.yml).
# ---------------------------------------------------------------------------

# Single-flight guard for report rendering: a cache miss runs the ~full
# report regeneration inline (seconds of CPU + pooled DB connections), so N
# concurrent requests for the same hash must not render N copies — later
# arrivals wait on the stripe lock and then hit the TTL cache. Fixed stripe
# pool keeps memory bounded; unrelated hashes colliding on a stripe merely
# serialize (rare, harmless).
_REPORT_RENDER_STRIPES = [threading.Lock() for _ in range(32)]


def _render_report_json_singleflight(simulation_hash: str, viewer_is_admin: bool) -> str:
    stripe = _REPORT_RENDER_STRIPES[hash((simulation_hash, viewer_is_admin)) % 32]
    with stripe:
        return _render_report_json(simulation_hash, viewer_is_admin)


@ttl_cache(ttl=600, maxsize=16)
def _render_report_json(simulation_hash: str, viewer_is_admin: bool) -> str:
    import base64
    import json as _json
    import queue as _queue

    import plotly.io as pio

    from background_tasks import regenerate_ui_results
    from db.utils import _sanitize_for_json

    q: _queue.Queue = _queue.Queue()
    regenerate_ui_results(
        simulation_hash, q, viewer_is_admin=viewer_is_admin
    )

    items = []
    while not q.empty():
        item = q.get()
        kind = item.get("type")
        if kind == "regeneration_package":
            # Session-state payload for the old UI's follow-up interactions —
            # multi-MB and unused by the web report.
            continue
        try:
            if kind == "plotly":
                fig = item["data"]
                if isinstance(fig, str):
                    item["data"] = _json.loads(fig)
                else:
                    item["data"] = _json.loads(pio.to_json(fig, validate=False))
            elif kind == "plot":
                # A PNG file path (strategy flowchart) → data URI
                path = item.get("data")
                if path and os.path.exists(str(path)):
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    item["data"] = f"data:image/png;base64,{b64}"
                    item["type"] = "image"
                else:
                    continue
            else:
                item["data"] = _sanitize_for_json(item.get("data"))
        except Exception:
            logging.exception("report item serialization failed (type=%s)", kind)
            continue
        items.append(item)

    if not items:
        raise HTTPException(status_code=404, detail="Report could not be generated")
    return _json.dumps({"simulation_hash": simulation_hash, "items": items})


@router.get("/simulations/{simulation_hash}/report")
def get_report(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
):
    from fastapi.responses import Response as _Response

    from app.access import require_simulation_view

    require_simulation_view(simulation_hash, user)

    viewer_is_admin = False
    if user:
        from db.database import db

        viewer_is_admin = db.get_user_tier(user["id"]) == "ADMIN"

    payload = _render_report_json_singleflight(simulation_hash, viewer_is_admin)
    return _Response(content=payload, media_type="application/json")
