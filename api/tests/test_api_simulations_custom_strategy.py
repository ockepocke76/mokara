"""Tests for running custom (W5-designer-authored) strategies via /simulate."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from app.main import app
from core.shared_logic import generate_simulation_hash
from db.database import db

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}

MINIMAL_STRATEGY_CODE = """
from core.strategy import BaseStrategy

class MinimalCustomStrategy(BaseStrategy):
    parameters = {
        "withdrawal_rate": {"label": "Withdrawal Rate", "default": 0.04, "description": "Annual withdrawal rate"},
    }

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {"action": "BUY_ASSET", "cash_amount": initial_portfolio_state.get("cash", 0.0)}

    @property
    def shortfall_funding_policy(self):
        return ["SELL_ASSETS", "USE_CASH"]

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        rate = self.params.get("withdrawal_rate", 0.04)
        return portfolio_state.get("asset_value", 0.0) * rate

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        return {
            "amount_contributed": 0.0,
            "amount_sold": desired_drawdown + mandatory_costs,
            "amount_bought": 0.0,
            "debt_increase": 0.0,
            "debt_repayment": 0.0,
        }
"""


def _auth(email=None):
    email = email or f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    return {**SECRET, "X-User-Email": email, "X-User-Name": "Custom Strategy Test"}


def _make_strategy(email, validation_status="validated", is_public=False, name=None):
    user_id = db.get_or_create_user_id(email, "Custom Strategy Test")
    strategy_id = db.save_custom_strategy(
        user_id=user_id,
        strategy_name=name or f"Test Strategy {uuid.uuid4().hex[:6]}",
        class_name="MinimalCustomStrategy",
        description="A minimal test strategy.",
        ai_description="A minimal test strategy.",
        # Unique marker keeps each test's simulation_hash distinct so a
        # /simulations call in one test can't hit another test's cached
        # result (generate_simulation_hash hashes custom_strategy_code).
        code=f"# test marker: {uuid.uuid4().hex}\n{MINIMAL_STRATEGY_CODE}",
        parameters_json={"withdrawal_rate": {"default": 0.04, "description": "Annual withdrawal rate"}},
        validation_status=validation_status,
    )
    assert strategy_id, "failed to save test strategy"
    if is_public:
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE CUSTOM_STRATEGIES SET is_public = TRUE WHERE id = %s", (strategy_id,))
            conn.commit()
        finally:
            db.release_connection(conn)
    return user_id, strategy_id


def test_config_params_includes_own_validated_custom_strategy():
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(email, validation_status="validated")

    r = client.get("/config/params", headers=_auth(email))
    assert r.status_code == 200
    strategies = r.json()["strategies"]
    entry = next(s for s in strategies if s["key"] == f"custom:{strategy_id}")
    assert entry["group"] == "mine"
    assert entry["disabled"] is False
    assert entry["is_custom"] is True


def test_config_params_shows_draft_custom_strategy_disabled():
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(email, validation_status="draft")

    r = client.get("/config/params", headers=_auth(email))
    assert r.status_code == 200
    entry = next(s for s in r.json()["strategies"] if s["key"] == f"custom:{strategy_id}")
    assert entry["disabled"] is True
    assert entry["disabled_reason"]


def test_config_params_excludes_other_users_private_strategy():
    owner_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(owner_email, validation_status="validated", is_public=False)

    other_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    r = client.get("/config/params", headers=_auth(other_email))
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()["strategies"]}
    assert f"custom:{strategy_id}" not in keys


def test_config_params_includes_other_users_public_strategy():
    owner_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(owner_email, validation_status="validated", is_public=True)

    other_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    r = client.get("/config/params", headers=_auth(other_email))
    assert r.status_code == 200
    entry = next(s for s in r.json()["strategies"] if s["key"] == f"custom:{strategy_id}")
    assert entry["group"] == "community"


def test_create_simulation_rejects_other_users_private_strategy():
    owner_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(owner_email, validation_status="validated", is_public=False)

    other_email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/simulations",
        headers=_auth(other_email),
        json={"params": {"strategy": f"custom:{strategy_id}", "asset_model": "parametric"}},
    )
    assert r.status_code == 404


def test_create_simulation_rejects_unvalidated_custom_strategy():
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    _, strategy_id = _make_strategy(email, validation_status="draft")

    r = client.post(
        "/simulations",
        headers=_auth(email),
        json={"params": {"strategy": f"custom:{strategy_id}", "asset_model": "parametric"}},
    )
    assert r.status_code == 422


def test_create_simulation_rejects_missing_custom_strategy():
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/simulations",
        headers=_auth(email),
        json={"params": {"strategy": "custom:99999999", "asset_model": "parametric"}},
    )
    assert r.status_code == 404

    r = client.post(
        "/simulations",
        headers=_auth(email),
        json={"params": {"strategy": "custom:not-a-number", "asset_model": "parametric"}},
    )
    assert r.status_code == 400


def test_create_simulation_clamps_custom_strategy_num_simulations():
    """num_simulations is clamped to the caller's tier limit for custom
    strategies (core.limits.LimitEnforcer.get_mc_iterations_limit), not a
    flat constant — a fresh test user defaults to the FREE tier (1000)."""
    from core.limits import LimitEnforcer

    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    headers = _auth(email)
    user_id, strategy_id = _make_strategy(email, validation_status="validated")
    expected_limit = LimitEnforcer(db).get_mc_iterations_limit(user_id, is_custom_strategy=True)
    assert expected_limit > 0

    r = client.post(
        "/simulations",
        headers=headers,
        json={
            "params": {
                "strategy": f"custom:{strategy_id}",
                "asset_model": "parametric",
                "num_simulations": 10000,
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in {"queued", "running", "cached"}

    job = db.get_job_by_id(body["job_id"]) if body.get("job_id") else None
    if job:
        params = job["payload"]["params"] if isinstance(job.get("payload"), dict) else {}
        if params:
            assert params.get("num_simulations") == expected_limit


def test_create_simulation_rejects_non_numeric_num_simulations():
    """A malformed num_simulations must 422 cleanly, not 500."""
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    headers = _auth(email)
    _, strategy_id = _make_strategy(email, validation_status="validated")

    r = client.post(
        "/simulations",
        headers=headers,
        json={
            "params": {
                "strategy": f"custom:{strategy_id}",
                "asset_model": "parametric",
                "num_simulations": "not-a-number",
            }
        },
    )
    assert r.status_code == 422


def test_create_simulation_rejects_client_supplied_custom_code():
    """Security regression test: a client must not be able to bypass the
    ownership/validation gate by sending strategy='custom' directly with its
    own custom_strategy_code — only the "custom:<id>" path (which fetches
    the code fresh from the DB) may set the strategy engine's 'custom'
    execution sentinel."""
    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    headers = _auth(email)

    r = client.post(
        "/simulations",
        headers=headers,
        json={
            "params": {
                "strategy": "custom",
                "asset_model": "parametric",
                "custom_strategy_code": MINIMAL_STRATEGY_CODE,
                "custom_strategy_class_name": "MinimalCustomStrategy",
            }
        },
    )
    assert r.status_code == 400

    # Even if the request is otherwise well-formed (a real built-in strategy
    # selected), smuggled custom_strategy_* fields must be stripped, never
    # forwarded to the job payload.
    r = client.post(
        "/simulations",
        headers=headers,
        json={
            "params": {
                "strategy": "trinity",
                "asset_model": "parametric",
                "custom_strategy_code": MINIMAL_STRATEGY_CODE,
                "custom_strategy_class_name": "MinimalCustomStrategy",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    job = db.get_job_by_id(body["job_id"]) if body.get("job_id") else None
    if job:
        params = job["payload"]["params"] if isinstance(job.get("payload"), dict) else {}
        assert "custom_strategy_code" not in params


def test_custom_strategy_simulation_runs_end_to_end():
    """Confirms the previously-dead 'custom' branch in background_tasks.py
    actually produces a valid simulation result now that it's reachable."""
    from services.background_worker import JobWorker

    email = f"custom-strat-{uuid.uuid4().hex[:10]}@example.com"
    headers = _auth(email)
    _, strategy_id = _make_strategy(email, validation_status="validated")

    r = client.post(
        "/simulations",
        headers=headers,
        json={
            "params": {
                "strategy": f"custom:{strategy_id}",
                "asset_model": "parametric",
                "num_simulations": 1000,
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued", body
    job_id = body["job_id"]

    job = db.get_job_by_id(job_id)
    assert job is not None
    params = job["payload"]["params"]
    assert params["strategy"] == "custom"
    assert params["custom_strategy_class_name"] == "MinimalCustomStrategy"
    assert params["custom_strategy_param_defs"]["withdrawal_rate"]["default"] == 0.04
    assert params["custom_strategy_params"]["withdrawal_rate"] == 0.04

    # Claim this specific job (scoped by id, unlike fetch_and_lock_job's
    # "next available" pick) so the test can't race a real dev worker.
    worker_id = "test-worker"
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE BACKGROUND_JOBS SET status = 'PROCESSING', worker_id = %s "
            "WHERE id = %s AND status = 'PENDING'",
            (worker_id, job_id),
        )
        conn.commit()
        assert cursor.rowcount == 1, "could not claim the queued job for the test"
    finally:
        db.release_connection(conn)

    worker = JobWorker(worker_id)
    try:
        result = worker._process_job(job)
    except Exception as e:
        db.fail_job(job_id, str(e), worker_id=worker_id)
        raise
    assert db.complete_job(job_id, result, worker_id=worker_id) is True

    job_after = db.get_job_by_id(job_id)
    assert job_after["status"] == "COMPLETED", job_after.get("result")

    cache_status, results_id, _ = db.check_simulation_cache(body["simulation_hash"])
    assert cache_status == "COMPLETED"


def test_hash_ignores_custom_strategy_metadata_but_not_code():
    base = {"strategy": "custom", "custom_strategy_code": "print(1)", "custom_strategy_class_name": "X"}
    a = {**base, "custom_strategy_name": "Foo", "custom_strategy_description": "d1"}
    b = {**base, "custom_strategy_name": "Bar", "custom_strategy_description": "d2"}
    assert generate_simulation_hash(a) == generate_simulation_hash(b)

    c = {**base, "custom_strategy_code": "print(2)"}
    assert generate_simulation_hash(a) != generate_simulation_hash(c)


def test_hash_distinguishes_custom_strategy_id_even_with_identical_code():
    """Security regression: two different strategies (e.g. two users' clones
    of the same public template, byte-identical code) must never collide
    onto the same simulation_hash — that would leak one user's cached
    report (with the other strategy's name/description) to the other."""
    base = {"strategy": "custom", "custom_strategy_code": "print(1)", "custom_strategy_class_name": "X"}
    a = {**base, "custom_strategy_id": 1, "custom_strategy_name": "A's clone"}
    b = {**base, "custom_strategy_id": 2, "custom_strategy_name": "B's clone"}
    assert generate_simulation_hash(a) != generate_simulation_hash(b)
