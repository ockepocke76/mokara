import os
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")
os.environ['MOKARA_SYNC_RUNNER'] = '1'
os.environ['MOKARA_FAKE_LLM'] = '1'

from app.main import app

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


def _auth():
    email = f"qa-api-{uuid.uuid4().hex[:10]}@example.com"
    return {**SECRET, "X-User-Email": email, "X-User-Name": "QA API Test"}


def _build(headers) -> str:
    r = client.post("/strategies/generate", headers=headers,
                    json={"request": "withdraw 4% a year, inflation adjusted",
                          "strategy_name": "QA API Build"})
    assert r.status_code == 200, r.text
    return r.json()['run_id']


def test_qa_requires_auth_and_secret():
    assert client.get("/qa/thread?subject_type=simulation&subject_id=x").status_code in (401, 403)
    assert client.get("/qa/thread?subject_type=simulation&subject_id=x", headers=SECRET).status_code == 401
    assert client.post("/qa/messages", headers=SECRET,
                       json={"subject_type": "simulation", "subject_id": "x", "question": "why?"}).status_code == 401


def test_qa_validates_subject_type():
    r = client.get("/qa/thread?subject_type=report&subject_id=x", headers=_auth())
    assert r.status_code == 422


def test_qa_round_trip_on_a_build():
    headers = _auth()
    run_id = _build(headers)

    r = client.get(f"/qa/thread?subject_type=generation_run&subject_id={run_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {'thread_id': None, 'messages': [], 'can_refine': True}

    r = client.post("/qa/messages", headers=headers,
                    json={"subject_type": "generation_run", "subject_id": run_id,
                          "question": "Why does it sell the same amount each year, and what would change that?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['assistant']['on_topic'] is True
    assert body['assistant']['suggested_change']['refine_feedback']
    assert isinstance(body['assistant']['created_at'], str)

    r = client.post("/qa/messages", headers=headers,
                    json={"subject_type": "generation_run", "subject_id": run_id,
                          "question": "Tell me a joke about cats"})
    assert r.status_code == 200
    assert r.json()['assistant']['on_topic'] is False

    r = client.get(f"/qa/thread?subject_type=generation_run&subject_id={run_id}", headers=headers)
    assert r.json()['thread_id'] == body['thread_id']
    assert [m['role'] for m in r.json()['messages']] == ['user', 'assistant', 'user', 'assistant']

    # Someone else's build: not found, both ways.
    other = _auth()
    assert client.get(f"/qa/thread?subject_type=generation_run&subject_id={run_id}",
                      headers=other).status_code == 404
    assert client.post("/qa/messages", headers=other,
                       json={"subject_type": "generation_run", "subject_id": run_id,
                             "question": "why?"}).status_code == 404
