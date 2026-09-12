"""
Mokara API — FastAPI application.

Run locally (from api/):  .venv/bin/uvicorn app.main:app --reload --port 8000
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI

from logger import configure_logging
from app.deps import verify_internal_secret

configure_logging()

# The API is internal (BFF pattern); in prod it is HTTPS-reachable, so the
# interactive docs and the OpenAPI schema must not be served publicly.
_docs_disabled = os.getenv("DISABLE_API_DOCS") == "1"
app = FastAPI(
    title="Mokara API",
    version="0.1.0",
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
)


@app.on_event("startup")
def _sync_builtin_strategies() -> None:
    # Idempotent: skips strategies whose code is unchanged. The old app ran
    # this from an admin button; without it the built-ins never exist as
    # CUSTOM_STRATEGIES rows, so they can't be listed, viewed, or cloned.
    # Always DB-only (git_service=None): startup must never block on GitHub
    # or push commits just because a GITHUB_TOKEN happens to be in the env.
    # The advisory lock serializes concurrent workers/containers — the sync
    # is SELECT-then-INSERT and CUSTOM_STRATEGIES has no unique constraint,
    # so an unserialized race would create duplicate built-in rows.
    try:
        from db.database import db
        from services.builtin_sync import sync_all_builtins

        conn = db.get_connection()
        try:
            cursor = db._get_cursor(conn)
            cursor.execute("SELECT pg_advisory_lock(hashtext('mokara_builtin_sync'))")
            try:
                results = sync_all_builtins(None, db)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(hashtext('mokara_builtin_sync'))")
        finally:
            db.release_connection(conn)
        changed = [r for r in results if r[0] not in ('skipped',)]
        if changed:
            logging.info("Builtin strategy sync: %s", changed)
    except Exception:
        logging.exception("Builtin strategy sync failed; continuing")


@app.on_event("startup")
def _reconcile_orphaned_generation_runs() -> None:
    # Runs still marked 'running' at startup belong to a dead process (the
    # runner is a daemon thread) — fail them so their SSE streams terminate
    # and users can retry, instead of spinning forever.
    try:
        from db import strategy_generation as sg

        count = sg.fail_orphaned_runs()
        if count:
            logging.warning(
                "Startup: marked %d orphaned strategy-generation run(s) as failed",
                count,
            )
    except Exception:
        logging.exception("Startup orphaned-run reconcile failed; continuing")


from app.routers import admin as admin_router
from app.routers import history as history_router
from app.routers import home as home_router
from app.routers import me as me_router
from app.routers import public as public_router
from app.routers import simulations as simulations_router
from app.routers import strategies as strategies_router

app.include_router(me_router.router)
app.include_router(public_router.router)
app.include_router(simulations_router.router)
app.include_router(history_router.router)
app.include_router(admin_router.router)
app.include_router(home_router.router)
app.include_router(strategies_router.router)


@app.get("/")
def root() -> dict:
    """Friendly root: this is the API, not the app."""
    info = {
        "service": "mokara-api",
        "hint": "This is the backend API. The app runs on the web frontend (locally: http://localhost:3100).",
        "health": "/healthz",
    }
    if not _docs_disabled:
        info["openapi_docs"] = "/docs"
    return info


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
