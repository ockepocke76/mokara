"""Tests for settings + admin endpoints."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def _new_user(tier=None):
    from db.database import db

    email = f"w6-test-{uuid.uuid4().hex[:10]}@example.com"
    user_id = db.get_or_create_user_id(email, "W6 Test")
    if tier:
        db.update_user_tier(user_id, tier, changed_by="pytest", reason="test setup")
    return email, user_id


def test_settings_update_and_validation():
    email, _ = _new_user()
    headers = {**SECRET, "X-User-Email": email}
    r = client.put("/me/settings", headers=headers, json={"currency": "EUR"})
    assert r.status_code == 200
    assert client.get("/me", headers=headers).json()["currency"] == "EUR"
    r = client.put("/me/settings", headers=headers, json={"currency": "XXX"})
    assert r.status_code == 422


def test_admin_gate():
    assert client.get("/admin/users", headers=SECRET).status_code == 401
    email, _ = _new_user()  # FREE tier
    r = client.get("/admin/users", headers={**SECRET, "X-User-Email": email})
    assert r.status_code == 403


def test_admin_users_and_tier_change():
    admin_email, _ = _new_user(tier="ADMIN")
    target_email, target_id = _new_user()
    headers = {**SECRET, "X-User-Email": admin_email}

    r = client.get("/admin/users", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "ADMIN" in body["tiers"] and "FREE" in body["tiers"]
    assert any(u["email"] == target_email for u in body["users"])

    r = client.post(
        f"/admin/users/{target_id}/tier",
        headers=headers,
        json={"tier": "PAID", "reason": "pytest"},
    )
    assert r.status_code == 200
    r = client.get("/admin/users", headers=headers)
    target = next(u for u in r.json()["users"] if u["id"] == target_id)
    assert target["tier"] == "PAID"

    r = client.post(
        f"/admin/users/{target_id}/tier", headers=headers, json={"tier": "NOPE"}
    )
    assert r.status_code == 422


def test_admin_allowlist_and_jobs():
    admin_email, _ = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}
    guest = f"w6-allow-{uuid.uuid4().hex[:8]}@example.com"

    r = client.post("/admin/allowed-users", headers=headers, json={"email": guest})
    assert r.status_code == 200
    r = client.get("/admin/users", headers=headers)
    row = next(u for u in r.json()["users"] if u["email"] == guest)
    assert row["allowed"] is True and row.get("pending_signup") is True

    assert (
        client.delete(f"/admin/allowed-users/{guest}", headers=headers).status_code
        == 200
    )

    r = client.get("/admin/jobs?limit=5", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json()["jobs"], list)


def test_system_reset_requires_correct_password():
    admin_email, _ = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}
    r = client.post(
        "/admin/system-reset",
        headers=headers,
        json={"admin_password": "wrong", "confirmation_text": "DELETE-EVERYTHING"},
    )
    assert r.status_code == 403
    r = client.post(
        "/admin/system-reset",
        headers=headers,
        json={"admin_password": "wrong", "confirmation_text": "nope"},
    )
    assert r.status_code == 403
