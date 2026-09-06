"""Smoke tests for the FastAPI skeleton."""
import os

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)


def test_healthz_reports_db():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["db"], bool)


def test_internal_ping_requires_secret():
    assert client.get("/internal/ping").status_code == 401
    r = client.get("/internal/ping", headers={"X-Internal-Secret": "wrong"})
    assert r.status_code == 401
    r = client.get(
        "/internal/ping",
        headers={"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]},
    )
    assert r.status_code == 200
    assert r.json() == {"pong": True}
