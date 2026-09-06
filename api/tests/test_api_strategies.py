"""W5 API tests: strategies CRUD + agentic generation endpoints."""
import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")
os.environ['MOKARA_SYNC_RUNNER'] = '1'
os.environ['MOKARA_FAKE_LLM'] = '1'

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def _auth(email=None):
    email = email or f"w5-api-{uuid.uuid4().hex[:10]}@example.com"
    return {**SECRET, "X-User-Email": email, "X-User-Name": "W5 API Test"}


def test_strategies_require_auth():
    assert client.get("/strategies", headers=SECRET).status_code == 401
    assert client.post("/strategies/generate", headers=SECRET,
                       json={"request": "x"}).status_code == 401


def _generate_and_save(headers) -> tuple[str, int]:
    r = client.post("/strategies/generate", headers=headers,
                    json={"request": "withdraw 4% yearly, inflation adjusted",
                          "strategy_name": f"API Test {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    r = client.get(f"/strategies/generate/{run_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["status"] == "needs_input"
    assert "thread_id" not in body["run"]
    types = [e["type"] for e in body["events"]]
    assert types[0] == "run_started" and types[-1] == "needs_input"

    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "save"})
    assert r.status_code == 200

    r = client.get(f"/strategies/generate/{run_id}", headers=headers)
    run = r.json()["run"]
    assert run["status"] == "completed"
    return run_id, run["final_strategy_id"]


def test_full_generation_flow_and_crud():
    headers = _auth()
    run_id, strategy_id = _generate_and_save(headers)

    # List includes the new strategy; the completed run is no longer active
    r = client.get("/strategies", headers=headers)
    assert r.status_code == 200
    body = r.json()
    ids = [s["id"] for s in body["strategies"]]
    assert strategy_id in ids
    assert all(run["id"] != run_id for run in body["active_runs"])

    # Detail carries code + ownership
    r = client.get(f"/strategies/{strategy_id}", headers=headers)
    assert r.status_code == 200
    detail = r.json()
    assert detail["is_owner"] is True
    assert "BaseStrategy" in detail["code"]
    assert detail["validation_status"] == "validated"

    # Another user cannot see a private strategy or the run
    other = _auth()
    assert client.get(f"/strategies/{strategy_id}", headers=other).status_code == 404
    assert client.get(f"/strategies/generate/{run_id}", headers=other).status_code == 404

    # Test-run endpoint executes the saved strategy
    r = client.post(f"/strategies/{strategy_id}/test", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["summary_stats"]["success_rate"] is not None
    assert len(body["paths"]) == body["num_paths"]

    # Evaluate queues a job
    r = client.post(f"/strategies/{strategy_id}/evaluate", headers=headers)
    assert r.status_code == 200 and r.json()["job_id"]

    # Delete (soft) hides it from the list
    r = client.delete(f"/strategies/{strategy_id}", headers=headers)
    assert r.status_code == 200
    r = client.get("/strategies", headers=headers)
    assert strategy_id not in [s["id"] for s in r.json()["strategies"]]


def test_evolve_uses_seed_strategy():
    headers = _auth()
    _, strategy_id = _generate_and_save(headers)

    r = client.post("/strategies/generate", headers=headers,
                    json={"request": "make the withdrawal rate 5%",
                          "seed_strategy_id": strategy_id})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    r = client.get(f"/strategies/generate/{run_id}", headers=headers)
    body = r.json()
    assert body["run"]["seed_strategy_id"] == strategy_id
    started = [e for e in body["events"] if e["type"] == "run_started"][0]
    assert started["payload"]["seed_strategy"]["id"] == strategy_id
    assert body["run"]["status"] == "needs_input"  # reached review


def test_resume_validation_and_conflicts():
    headers = _auth()
    run_id, _ = _generate_and_save(headers)
    # Completed run refuses resume
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "save"})
    assert r.status_code == 409
    # Bad kind rejected
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "nonsense"})
    assert r.status_code == 422


def test_sse_replays_persisted_events():
    headers = _auth()
    run_id, _ = _generate_and_save(headers)
    with client.stream("GET", f"/strategies/generate/{run_id}/events",
                       headers=headers) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        seen = []
        for line in response.iter_lines():
            if line.startswith("event: "):
                seen.append(line.removeprefix("event: "))
            if "run_completed" in line:
                break
    assert seen[0] == "run_started"
    assert "run_completed" in seen
