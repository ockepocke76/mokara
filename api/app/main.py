"""
Mokara API — FastAPI application.

Run locally (from api/):  .venv/bin/uvicorn app.main:app --reload --port 8000
"""
import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI

from logger import configure_logging
from app.deps import verify_internal_secret

configure_logging()

app = FastAPI(title="Mokara API", version="0.1.0")

from app.routers import admin as admin_router
from app.routers import history as history_router
from app.routers import me as me_router
from app.routers import public as public_router
from app.routers import simulations as simulations_router

app.include_router(me_router.router)
app.include_router(public_router.router)
app.include_router(simulations_router.router)
app.include_router(history_router.router)
app.include_router(admin_router.router)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness + DB reachability. No auth — used by infra health checks."""
    db_ok = False
    try:
        from db.database import db
        conn = db.get_connection()
        try:
            cursor = db._get_cursor(conn)
            cursor.execute("SELECT 1")
            db_ok = cursor.fetchone()[0] == 1
        finally:
            db.release_connection(conn)
    except Exception:
        logging.exception("healthz: database check failed")
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.get("/internal/ping", dependencies=[Depends(verify_internal_secret)])
def internal_ping() -> dict:
    """Verifies BFF → API internal auth wiring."""
    return {"pong": True}
