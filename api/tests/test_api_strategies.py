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
    # num_paths random markets, plus the flagged historical backtest when
    # market data provides one
    random_paths = [p for p in body["paths"] if not p.get("is_backtest")]
    assert len(random_paths) == body["num_paths"]
    assert len(body["paths"]) - len(random_paths) <= 1
    # Every path carries the full yearly series with real values, not just
    # net worth (and not all-None arrays from a renamed engine column).
    for series in ("net_worth", "asset_value", "debt", "cash",
                   "contributed", "withdrawn", "borrowed", "sold"):
        assert len(body["paths"][0][series]) == len(body["paths"][0]["years"])
    for series in ("net_worth", "borrowed", "sold"):
        assert any(v is not None for v in body["paths"][0][series])

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

    # Saving an evolve run updates the SEED strategy in place (old-app
    # semantic) — no sibling copy, no name collision.
    from db.database import db
    before = db.get_custom_strategy(strategy_id)
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "save"})
    assert r.status_code == 200
    r = client.get(f"/strategies/generate/{run_id}", headers=headers)
    assert r.json()["run"]["final_strategy_id"] == strategy_id
    after = db.get_custom_strategy(strategy_id)
    assert after["strategy_name"] == before["strategy_name"]
    assert after["validation_status"] == "validated"


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


# --- Detail-page extension endpoints (history/publish/clone/flowchart) -----

def test_list_includes_builtins():
    headers = _auth()
    r = client.get("/strategies", headers=headers)
    assert r.status_code == 200
    builtins = r.json()["builtins"]
    names = {b["strategy_name"] for b in builtins}
    assert {"Trinity", "Buy Borrow Die", "Get Rich Stay Rich"} <= names
    assert all(b["user_id"] == 0 for b in builtins)


def _builtin_id(name="Trinity") -> int:
    headers = _auth()
    r = client.get("/strategies", headers=headers)
    return next(b["id"] for b in r.json()["builtins"]
                if b["strategy_name"] == name)


def test_builtin_detail_flowchart_and_clone():
    headers = _auth()
    builtin_id = _builtin_id()

    r = client.get(f"/strategies/{builtin_id}", headers=headers)
    assert r.status_code == 200
    detail = r.json()
    assert detail["is_builtin"] is True and detail["is_owner"] is False
    assert len(detail["description"] or "") > 100  # rich write-up, not the sync one-liner

    r = client.get(f"/strategies/{builtin_id}/flowchart", headers=headers)
    assert r.status_code == 200
    assert "flowchart" in (r.json()["mermaid"] or "")

    # Clone lands in the caller's library; a second clone is a no-op
    r = client.post(f"/strategies/{builtin_id}/clone", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cloned"] is True and body["strategy_id"]
    r = client.post(f"/strategies/{builtin_id}/clone", headers=headers)
    assert r.json() == {"cloned": False, "in_library": True}

    # Custom strategies have no flowchart
    r = client.get(f"/strategies/{body['strategy_id']}/flowchart", headers=headers)
    assert r.status_code == 200 and r.json()["mermaid"] is None


def test_publish_requires_evaluation():
    headers = _auth()
    _, strategy_id = _generate_and_save(headers)

    r = client.post(f"/strategies/{strategy_id}/publish", headers=headers)
    assert r.status_code == 409
    assert "evaluated" in r.json()["detail"]

    # Another user can neither publish nor unpublish it
    other = _auth()
    assert client.post(f"/strategies/{strategy_id}/publish",
                       headers=other).status_code == 404
    r = client.post(f"/strategies/{strategy_id}/unpublish", headers=headers)
    assert r.status_code == 200 and r.json() == {"published": False}


def test_evaluation_endpoint_shape():
    headers = _auth()
    _, strategy_id = _generate_and_save(headers)
    r = client.get(f"/strategies/{strategy_id}/evaluation", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"] is None
    assert body["in_progress"] is False

    # Queue an evaluation -> the endpoint reports it in progress
    r = client.post(f"/strategies/{strategy_id}/evaluate", headers=headers)
    assert r.status_code == 200
    r = client.get(f"/strategies/{strategy_id}/evaluation", headers=headers)
    assert r.json()["in_progress"] is True


def test_history_records_evolution():
    headers = _auth()
    _, strategy_id = _generate_and_save(headers)

    r = client.get(f"/strategies/{strategy_id}/history", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["history"] == []
    # Genesis is the VERBATIM original request, not the AI description
    assert body["genesis"] == "withdraw 4% yearly, inflation adjusted"
    runs = body["runs"]
    assert len(runs) == 1 and runs[0]["kind"] == "create"
    assert runs[0]["request"] == "withdraw 4% yearly, inflation adjusted"

    # Evolve with a refine round -> request AND feedback land in the timeline
    r = client.post("/strategies/generate", headers=headers,
                    json={"request": "make the withdrawal rate 5%",
                          "seed_strategy_id": strategy_id})
    run_id = r.json()["run_id"]
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "refine",
                          "feedback": "round the withdrawal to whole dollars"})
    assert r.status_code == 200
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "save"})
    assert r.status_code == 200

    r = client.get(f"/strategies/{strategy_id}/history", headers=headers)
    body = r.json()
    assert len(body["history"]) == 1
    # An evolve refine folds the follow-up into the recorded request, so the
    # timeline carries the full ask, not just the opening message.
    assert body["history"][0]["request"].startswith("make the withdrawal rate 5%")
    assert "round the withdrawal to whole dollars" in body["history"][0]["request"]
    assert body["history"][0]["timestamp"]
    runs = body["runs"]
    assert [x["kind"] for x in runs] == ["create", "evolve"]
    evolve = runs[1]
    assert evolve["request"] == "make the withdrawal rate 5%"
    feedbacks = [i.get("feedback") for i in evolve["inputs"] if i.get("feedback")]
    assert feedbacks == ["round the withdrawal to whole dollars"]

    # Another user viewing a public strategy gets no raw run inputs
    from db.database import db
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE CUSTOM_STRATEGIES SET is_public = TRUE WHERE id = %s",
                       (strategy_id,))
        conn.commit()
    finally:
        db.release_connection(conn)
    other = _auth()
    r = client.get(f"/strategies/{strategy_id}/history", headers=other)
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_versions_endpoint_and_revert_flow():
    headers = _auth()
    _, strategy_id = _generate_and_save(headers)

    # Evolve once so there is something to revert to
    r = client.post("/strategies/generate", headers=headers,
                    json={"request": "make the withdrawal rate 5%",
                          "seed_strategy_id": strategy_id})
    run_id = r.json()["run_id"]
    r = client.post(f"/strategies/generate/{run_id}/resume", headers=headers,
                    json={"kind": "review", "action": "save"})
    assert r.status_code == 200

    r = client.get(f"/strategies/{strategy_id}/versions", headers=headers)
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert [v["source"] for v in versions] == ["evolve", "create"]
    assert versions[0]["is_head"] and versions[0]["short_hash"]
    # Version metadata never carries code
    assert "code" not in versions[0]

    # Another user gets a 404, not someone else's lineage
    other = _auth()
    assert client.get(f"/strategies/{strategy_id}/versions",
                      headers=other).status_code == 404
    assert client.post(f"/strategies/{strategy_id}/revert", headers=other,
                       json={"version_id": versions[1]["id"]}).status_code == 404

    # Restore the original: append-only — three versions, head content = v1
    r = client.post(f"/strategies/{strategy_id}/revert", headers=headers,
                    json={"version_id": versions[1]["id"]})
    assert r.status_code == 200, r.text
    r = client.get(f"/strategies/{strategy_id}/versions", headers=headers)
    versions = r.json()["versions"]
    assert [v["source"] for v in versions] == ["revert", "evolve", "create"]
    assert versions[0]["short_hash"] == versions[2]["short_hash"]

    # Reverting to the current head is refused
    r = client.post(f"/strategies/{strategy_id}/revert", headers=headers,
                    json={"version_id": versions[0]["id"]})
    assert r.status_code == 422
