"""Tests for history/PDF endpoints."""
import os
import uuid

import pytest
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


def test_pdf_status_unknown_hash_is_404():
    # Access rules: unknown/private hashes 404 for everyone (hashes are
    # deterministic functions of params, not unguessable capabilities).
    r = client.get("/simulations/deadbeef/pdf/status", headers=SECRET)
    assert r.status_code == 404


_SEEDED_HASHES: list = []


@pytest.fixture(autouse=True, scope="module")
def _cleanup_seeded_sims():
    yield
    from db.database import db

    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        for h in _SEEDED_HASHES:
            cur.execute("DELETE FROM USER_SIMULATION_HISTORY WHERE simulation_hash = %s", (h,))
            # A DB trigger refuses deleting public sims — unmark first.
            cur.execute("UPDATE CACHED_SIMULATIONS SET is_public = FALSE WHERE simulation_hash = %s", (h,))
            cur.execute("DELETE FROM CACHED_SIMULATIONS WHERE simulation_hash = %s", (h,))
        conn.commit()
    finally:
        db.release_connection(conn)


def _seed_sim(is_public: bool, owner_email: str) -> str:
    """Create a cached sim + a history entry for owner_email; returns hash."""
    from db.database import db

    sim_hash = uuid.uuid4().hex + uuid.uuid4().hex  # 64 chars, hash-shaped
    _SEEDED_HASHES.append(sim_hash)
    db.create_cached_simulation_entry(sim_hash, {"num_years": 1})
    owner_id = db.get_or_create_user_id(owner_email, "")
    db.add_to_user_history(owner_id, sim_hash, "access-test")
    if is_public:
        conn = db.get_connection()
        try:
            cur = db._get_cursor(conn)
            cur.execute(
                "UPDATE CACHED_SIMULATIONS SET is_public = TRUE WHERE simulation_hash = %s",
                (sim_hash,))
            conn.commit()
        finally:
            db.release_connection(conn)
    return sim_hash


def test_private_sim_is_invisible_to_other_users():
    owner = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    other = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    sim_hash = _seed_sim(is_public=False, owner_email=owner)
    other_h = {**SECRET, "X-User-Email": other}

    # Reads: 404 for another user and for anonymous
    for headers in (other_h, SECRET):
        assert client.get(f"/simulations/{sim_hash}/pdf/status", headers=headers).status_code == 404
        r = client.get(f"/simulations/{sim_hash}/results", headers=headers)
        assert r.status_code == 404
        assert r.json()["detail"] == "Simulation not found"  # gated before lookup
    # Mutations: 404 for another user
    assert client.delete(f"/simulations/{sim_hash}", headers=other_h).status_code == 404
    assert client.post(f"/simulations/{sim_hash}/pdf", headers=other_h).status_code == 404


def test_owner_passes_access_gate():
    owner = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    sim_hash = _seed_sim(is_public=False, owner_email=owner)
    owner_h = {**SECRET, "X-User-Email": owner}

    # Passes the gate; 404s further in only because no results exist yet
    r = client.get(f"/simulations/{sim_hash}/results", headers=owner_h)
    assert r.status_code == 404
    assert r.json()["detail"] == "Simulation results not found"
    assert client.get(f"/simulations/{sim_hash}/pdf/status", headers=owner_h).status_code == 200
    # Owner can delete their private sim
    assert client.delete(f"/simulations/{sim_hash}", headers=owner_h).status_code == 200


def test_others_public_sims_stay_out_of_my_history_list():
    owner = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    other = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    _seed_sim(is_public=True, owner_email=owner)
    r = client.get("/simulations", headers={**SECRET, "X-User-Email": other})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_public_sim_readable_by_all_but_not_deletable():
    owner = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    other = f"w4-test-{uuid.uuid4().hex[:10]}@example.com"
    sim_hash = _seed_sim(is_public=True, owner_email=owner)
    other_h = {**SECRET, "X-User-Email": other}

    # Readable by another user and anonymously (gate passes; results absent)
    for headers in (other_h, SECRET):
        r = client.get(f"/simulations/{sim_hash}/results", headers=headers)
        assert r.status_code == 404
        assert r.json()["detail"] == "Simulation results not found"
        assert client.get(f"/simulations/{sim_hash}/pdf/status", headers=headers).status_code == 200
    # Not deletable: other user has no history entry (404); the owner's
    # delete is refused because the sim is public (409)
    assert client.delete(f"/simulations/{sim_hash}", headers=other_h).status_code == 404
    owner_h = {**SECRET, "X-User-Email": owner}
    assert client.delete(f"/simulations/{sim_hash}", headers=owner_h).status_code == 409
