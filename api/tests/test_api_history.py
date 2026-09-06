"""Tests for history/PDF endpoints."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def test_list_requires_auth():
    assert client.get("/simulations", headers=SECRET).status_code == 401


def test_list_empty_for_new_user():
    email = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    r = client.get("/simulations", headers={**SECRET, "X-User-Email": email})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_pdf_endpoints_guard_ownership():
    email = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    headers = {**SECRET, "X-User-Email": email}
    # A hash not in this user's history: 404 on queue and download
    assert client.post("/simulations/deadbeef/pdf", headers=headers).status_code == 404
    assert client.get("/simulations/deadbeef/pdf", headers=headers).status_code == 404
    assert (
        client.delete("/simulations/deadbeef", headers=headers).status_code == 404
    )


def test_pdf_status_is_public_shape():
    r = client.get("/simulations/deadbeef/pdf/status", headers=SECRET)
    assert r.status_code == 200
    assert r.json()["pdf_status"] is None
