"""Round-trip tests for the strategy-generation run/event store (W5)."""
import uuid

from db import strategy_generation as sg
from db.database import db


def _new_user() -> int:
    return db.get_or_create_user_id(f"w5-db-{uuid.uuid4().hex[:10]}@example.com", "W5 DB Test")


def test_run_and_event_roundtrip():
    user_id = _new_user()
    run_id = str(uuid.uuid4())
    sg.create_run(run_id, user_id, thread_id=f"thread-{run_id}",
                  user_request="a 4% withdrawal strategy", strategy_name="Test Run")

    run = sg.get_run(run_id)
    assert run is not None
    assert run['status'] == 'running'
    assert run['user_id'] == user_id
    assert run['user_request'] == "a 4% withdrawal strategy"

    seq1 = sg.append_event(run_id, 'run_started', {'strategy_name': 'Test Run'})
    seq2 = sg.append_event(run_id, 'stage_started', {'stage': 'extract_spec'})
    assert (seq1, seq2) == (1, 2)

    events = sg.list_events(run_id)
    assert [e['type'] for e in events] == ['run_started', 'stage_started']
    assert events[1]['payload']['stage'] == 'extract_spec'
    assert sg.list_events(run_id, after_seq=1)[0]['seq'] == 2

    sg.update_run(run_id, status='completed', spec={'category': 'WITHDRAWAL_ONLY'},
                  llm_calls=4)
    run = sg.get_run(run_id)
    assert run['status'] == 'completed'
    assert run['spec'] == {'category': 'WITHDRAWAL_ONLY'}
    assert run['llm_calls'] == 4

    runs = sg.list_runs(user_id)
    assert runs and runs[0]['id'] == run_id


def test_update_run_ignores_unknown_fields():
    user_id = _new_user()
    run_id = str(uuid.uuid4())
    sg.create_run(run_id, user_id, thread_id="t", user_request="req")
    sg.update_run(run_id, nonsense_field="x")  # silently ignored
    assert sg.get_run(run_id)['status'] == 'running'
