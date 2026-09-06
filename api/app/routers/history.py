"""My Simulations: history list, delete, PDF generation + download."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.deps import get_current_user, verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


def _require_user(user: Optional[dict]) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def _own_history_row(user: dict, simulation_hash: str) -> dict:
    from db.database import db

    rows = db.get_user_simulations_with_params(user["email"]) or []
    for row in rows:
        if row.get("simulation_hash") == simulation_hash:
            return dict(row)
    raise HTTPException(status_code=404, detail="Simulation not in your history")


@router.get("/simulations")
def list_simulations(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """The viewer's simulation history with preview stats."""
    user = _require_user(user)
    from db.cache import get_simulation_final_stats_cached
    from db.database import db
    from utils.helpers import generate_simulation_description

    rows = db.get_user_simulations_with_params(user["email"]) or []
    items = []
    for row in rows:
        params = row.get("all_params") or {}
        entry = {
            "history_id": row.get("id"),
            "simulation_hash": row.get("simulation_hash"),
            "name": row.get("simulation_name"),
            "created_at": row.get("timestamp"),
            "status": row.get("status"),
            "strategy": params.get("custom_strategy_name") or params.get("strategy"),
            "asset": params.get("asset_name") or params.get("asset_model"),
            "num_years": params.get("num_years"),
            "num_simulations": params.get("num_simulations"),
            "initial_investment": params.get("initial_investment"),
            "currency": params.get("currency"),
        }
        try:
            entry["description"] = generate_simulation_description(params)
        except Exception:
            entry["description"] = None
        try:
            stats, _, _ = get_simulation_final_stats_cached(row.get("simulation_hash"))
            if stats:
                entry["success_rate"] = stats.get("success_rate")
                entry["median_final_net_worth"] = stats.get("median_final_net_worth")
        except Exception:
            logging.exception("preview stats failed for %s", row.get("simulation_hash"))
        items.append(entry)
    return {"items": items}


@router.delete("/simulations/{simulation_hash}")
def delete_simulation(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    user = _require_user(user)
    from core.cache import clear_all
    from db.database import db

    row = _own_history_row(user, simulation_hash)
    db.permanently_delete_simulation(row["id"])
    clear_all()
    return {"deleted": True, "history_id": row["id"]}


@router.post("/simulations/{simulation_hash}/pdf")
def request_pdf(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    user = _require_user(user)
    from services.background_manager import BackgroundManager

    row = _own_history_row(user, simulation_hash)
    job_id = BackgroundManager.start_pdf_generation(
        history_id=row["id"], user=user
    )
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to queue PDF job")
    return {"job_id": job_id, "history_id": row["id"]}


@router.get("/simulations/{simulation_hash}/pdf/status")
def pdf_status(simulation_hash: str) -> dict:
    from db.database import db

    info = db.get_pdf_info_by_hash(simulation_hash)
    if not info:
        return {"pdf_status": None}
    return {
        "pdf_status": info.get("pdf_status"),
        "generated_at": info.get("pdf_generated_at"),
        "error": info.get("pdf_error_message"),
    }


@router.get("/simulations/{simulation_hash}/pdf")
def download_pdf(
    simulation_hash: str,
    user: Optional[dict] = Depends(get_current_user),
):
    user = _require_user(user)
    from db.database import db
    from db.pdf_storage import get_pdf_storage

    _own_history_row(user, simulation_hash)
    info = db.get_pdf_info_by_hash(simulation_hash)
    # Engine status vocabulary: pending -> ready | failed
    if not info or info.get("pdf_status") != "ready" or not info.get("pdf_storage_path"):
        raise HTTPException(status_code=404, detail="PDF not ready")

    pdf_bytes = get_pdf_storage().get_pdf(info["pdf_storage_path"])
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF file missing from storage")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="mokara-{simulation_hash[:10]}.pdf"'
        },
    )
