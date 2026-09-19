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


def test_delete_user_guards_and_bulk_allow():
    from db.database import db

    admin_email, admin_id = _new_user(tier="ADMIN")
    target_email, target_id = _new_user()
    headers = {**SECRET, "X-User-Email": admin_email}

    assert client.delete("/admin/users/0", headers=headers).status_code == 403
    assert client.delete(f"/admin/users/{admin_id}", headers=headers).status_code == 403
    assert client.delete("/admin/users/999999999", headers=headers).status_code == 404
    assert client.delete(f"/admin/users/{target_id}", headers=headers).status_code == 200
    assert client.delete(f"/admin/users/{target_id}", headers=headers).status_code == 404

    guest = f"bulk-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/admin/allowed-users/bulk",
        headers=headers,
        json={"emails": [guest.upper(), "# comment", "", guest]},
    )
    assert r.status_code == 200
    assert r.json() == {"added": [guest, guest], "failed": []}
    db.remove_allowed_user(guest)


def test_approve_login_request_keeps_request_on_failure(monkeypatch):
    from db.database import db

    admin_email, _ = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}
    guest = f"req-{uuid.uuid4().hex[:8]}@example.com"
    db.log_login_request(guest, "Guest")
    try:
        monkeypatch.setattr(type(db), "add_allowed_user", lambda self, *a, **k: False)
        r = client.post(f"/admin/login-requests/{guest}/approve", headers=headers)
        assert r.status_code == 500
        assert any(q["email"] == guest for q in db.get_login_requests())
        monkeypatch.undo()
        r = client.post(f"/admin/login-requests/{guest}/approve", headers=headers)
        assert r.status_code == 200
        assert not any(q["email"] == guest for q in db.get_login_requests())
    finally:
        db.delete_login_request(guest)
        db.remove_allowed_user(guest)


def test_tier_change_unknown_user_is_404_and_audited_from():
    admin_email, _ = _new_user(tier="ADMIN")
    target_email, target_id = _new_user()
    headers = {**SECRET, "X-User-Email": admin_email}

    r = client.post("/admin/users/999999999/tier", headers=headers, json={"tier": "PAID"})
    assert r.status_code == 404

    r = client.post(f"/admin/users/{target_id}/tier", headers=headers, json={"tier": "PAID"})
    assert r.status_code == 200
    entry = next(e for e in client.get("/admin/audit", headers=headers).json()["entries"]
                 if e["user_id"] == target_id)
    assert (entry["changed_from"], entry["changed_to"]) == ("FREE", "PAID")

    r = client.get("/admin/stats", headers=headers)
    assert r.status_code == 200
    assert all(u["email"] != "system@btc-simulator.internal" for u in r.json()["top_by_strategies"])


def test_public_toggle_is_scoped_to_admin_owned_strategies():
    from db.database import db

    admin_email, admin_id = _new_user(tier="ADMIN")
    user_email, user_id = _new_user()
    headers = {**SECRET, "X-User-Email": admin_email}

    def make(owner_id, name):
        assert db.save_custom_strategy(
            owner_id, name, "S", "d", None, "class S:\n    pass", "{}")
        return next(s["id"] for s in db.get_user_custom_strategies(owner_id) if s["strategy_name"] == name)

    theirs = make(user_id, f"private-{uuid.uuid4().hex[:6]}")
    mine = make(admin_id, f"demo-{uuid.uuid4().hex[:6]}")
    try:
        r = client.post(f"/admin/strategies/{theirs}/public", headers=headers, json={"is_public": True})
        assert r.status_code == 404
        assert not db.get_custom_strategy(theirs)["is_public"]

        r = client.post(f"/admin/strategies/{mine}/public", headers=headers, json={"is_public": True})
        assert r.status_code == 200
        assert db.get_custom_strategy(mine)["is_public"]
        assert any(s["id"] == mine and s["is_public"]
                   for s in client.get("/admin/demo-content", headers=headers).json()["strategies"])
        assert client.post("/admin/strategies/999999999/public", headers=headers,
                           json={"is_public": True}).status_code == 404
        assert client.post("/admin/simulations/no-such-hash/public", headers=headers,
                           json={"is_public": True}).status_code == 404
    finally:
        client.post(f"/admin/strategies/{mine}/public", headers=headers, json={"is_public": False})
        db.delete_users_by_id([user_id, admin_id])


def test_selective_evaluation_and_status():
    from db.database import db

    admin_email, _ = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}

    r = client.get("/admin/evaluations/strategies", headers=headers)
    assert r.status_code == 200
    assert "Trinity" in r.json()["builtins"]

    r = client.post(
        "/admin/evaluations/run",
        headers=headers,
        json={"builtin_names": ["Trinity"], "custom_strategy_ids": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["queued"] == 1
    job_id = body["job_ids"][0]
    try:
        r = client.get(f"/admin/evaluations/status?job_ids={job_id}", headers=headers)
        assert r.status_code == 200
        status = r.json()
        # A live worker may already have picked the job up (or finished it).
        assert status["total"] == 1
        assert sum(status[k] for k in ("pending", "processing", "completed", "failed")) == 1
        assert status["running"] == (status["completed"] + status["failed"] < 1)

        r = client.post(
            "/admin/evaluations/run",
            headers=headers,
            json={"builtin_names": ["Nope"]},
        )
        assert r.status_code == 422
        r = client.post(
            "/admin/evaluations/run",
            headers=headers,
            json={"builtin_names": [], "custom_strategy_ids": [999999999]},
        )
        assert r.status_code == 422
        assert "999999999" in r.json()["detail"]
    finally:
        with db._connection_cursor() as cur:
            cur.execute("DELETE FROM background_jobs WHERE id = %s", (job_id,))


def test_analytics_summary_and_login_event():
    from db.database import db

    admin_email, admin_id = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}

    r = client.post("/me/login-event", headers=headers, json={"method": "pytest"})
    assert r.status_code == 200
    try:
        r = client.get("/admin/analytics?days=7", headers=headers)
        assert r.status_code == 200
        s = r.json()
        assert s["total_events"] >= 1
        assert any(row["method"] == "pytest" for row in s["logins_by_method"])
        assert client.get("/admin/analytics?days=0", headers=headers).status_code == 422
    finally:
        with db._connection_cursor() as cur:
            cur.execute("DELETE FROM analytics_events WHERE user_id = %s", (admin_id,))
