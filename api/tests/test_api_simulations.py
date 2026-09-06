"""Tests for the Run Simulation endpoints (schema, submission gates, jobs)."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def test_config_params_schema():
    r = client.get("/config/params", headers=SECRET)
    assert r.status_code == 200
    body = r.json()
    keys = {s["key"] for s in body["strategies"]}
    assert {"trinity", "buy_borrow_die", "get_rich_stay_rich"} <= keys
    assert any(a["key"] == "bootstrap_gspc" for a in body["assets"])
    # tax method exposed under the engine's ui key
    tax = next(s for s in body["sections"] if s["title"] == "Tax Settings")
    assert any(p["key"] == "tax_method" for p in tax["params"])
    # percent detection
    trinity = next(s for s in body["strategies"] if s["key"] == "trinity")
    wr = next(p for p in trinity["params"] if p["key"] == "withdrawal_rate")
    assert wr["is_percent"] is True
    # BBD conditional visibility survives
    bbd = next(s for s in body["strategies"] if s["key"] == "buy_borrow_die")
    fixed = next(p for p in bbd["params"] if p["key"] == "fixed_drawdown")
    assert fixed["visible_if"] == {"param": "drawdown_method", "equals": "fixed"}


def test_create_simulation_requires_auth():
    r = client.post("/simulations", headers=SECRET, json={"params": {}})
    assert r.status_code == 401


def test_create_simulation_validates_params():
    email = f"w3-test-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/simulations",
        headers={**SECRET, "X-User-Email": email},
        json={
            "params": {
                "strategy": "trinity",
                "asset_model": "parametric",
                "num_simulations": 5,  # below engine minimum
            }
        },
    )
    assert r.status_code == 422
    assert any("num_simulations" in d for d in r.json()["detail"])


def test_job_status_not_found():
    r = client.get("/jobs/does-not-exist", headers=SECRET)
    assert r.status_code == 200
    assert r.json()["status"] == "NOT_FOUND"


def test_results_not_found():
    r = client.get("/simulations/deadbeef/results", headers=SECRET)
    assert r.status_code == 404
