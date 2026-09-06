"""Tests for GET /me — viewer profile via BFF headers."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def test_me_requires_internal_secret():
    assert client.get("/me").status_code == 401


def test_me_anonymous():
    r = client.get("/me", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is False
    assert "beta" in body and "is_full" in body["beta"]


def test_me_authenticated_creates_and_profiles_user():
    email = f"w1-test-{uuid.uuid4().hex[:10]}@example.com"
    r = client.get(
        "/me",
        headers={**SECRET, "X-User-Email": email, "X-User-Name": "W1 Test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["email"] == email
    assert isinstance(body["id"], int)
    assert isinstance(body["allowed"], bool)
    assert body["is_admin"] is False
    assert body["currency"]

    # Same email resolves to the same engine user id (stable identity link)
    r2 = client.get("/me", headers={**SECRET, "X-User-Email": email})
    assert r2.json()["id"] == body["id"]
