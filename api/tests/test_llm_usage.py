"""
LLM cost tracking: pricing, the recording hook in core.llm, scope
attribution through the designer runner, the LLM_USAGE aggregates, and the
admin endpoints. Runs against the local Postgres like the other API tests.
"""
import os
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

os.environ['MOKARA_SYNC_RUNNER'] = '1'
os.environ['MOKARA_FAKE_LLM'] = '1'
os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

from fastapi.testclient import TestClient

from app.main import app
from core import llm as core_llm
from core.llm import current_llm_scope, llm_scope
from core.llm_pricing import estimate_cost_usd, price_for
from db import llm_usage
from db.database import db

client = TestClient(app)
SECRET = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}

# Every row these tests write carries a ref_id with this prefix (or is the
# one deliberately unscoped failure below), so teardown can remove them:
# LLM_USAGE rows outlive their user on purpose (ON DELETE SET NULL), so the
# conftest user purge would leave them behind as anonymous spend.
REF_PREFIX = f"pytest-{uuid.uuid4().hex[:6]}-"
UNSCOPED_ERROR = f"429 quota exceeded ({REF_PREFIX})"


def _ref(label: str) -> str:
    return f"{REF_PREFIX}{label}"


@pytest.fixture(scope="module", autouse=True)
def _remove_rows_written_by_this_module():
    yield
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM LLM_USAGE WHERE ref_id LIKE %s OR error = %s "
            "OR ref_id IN (SELECT id::text FROM STRATEGY_GENERATION_RUNS "
            "              WHERE user_request = 'in-flight test')",
            (f"{REF_PREFIX}%", UNSCOPED_ERROR))
        conn.commit()
    finally:
        db.release_connection(conn)


def _new_user(tier=None) -> tuple[str, int]:
    email = f"llm-usage-{uuid.uuid4().hex[:10]}@example.com"
    user_id = db.get_or_create_user_id(email, "LLM Usage Test")
    if tier:
        db.update_user_tier(user_id, tier, changed_by="pytest", reason="test setup")
    return email, user_id


# --- pricing -----------------------------------------------------------------

def test_flash_promo_price_flips_on_new_year():
    promo = price_for('gemini-3.8-flash', date(2026, 12, 31))
    regular = price_for('gemini-3.8-flash', date(2027, 1, 1))
    assert (promo.input, promo.output) == (0.75, 3.75)
    assert (regular.input, regular.output) == (1.50, 7.50)


def test_cost_counts_thinking_as_output_and_cached_at_cache_rate():
    # 10k prompt of which 4k cached, 1k completion, 3k thinking on Flash-Lite
    cost = estimate_cost_usd('gemini-3.5-flash-lite', prompt_tokens=10_000, cached_tokens=4_000,
                             completion_tokens=1_000, thinking_tokens=3_000)
    expected = (6_000 * 0.30 + 4_000 * 0.03 + 4_000 * 2.50) / 1_000_000
    assert cost == pytest.approx(expected)
    # thinking is not free
    assert estimate_cost_usd('gemini-3.5-flash-lite', completion_tokens=1_000) < \
        estimate_cost_usd('gemini-3.5-flash-lite', completion_tokens=1_000, thinking_tokens=1_000)


def test_unknown_model_is_unpriced_not_free():
    assert estimate_cost_usd('gemini-9-ultra', prompt_tokens=1000) is None
    # prefixes/suffixes still match the known name
    assert price_for('models/gemini-3.8-flash-001') is not None


# --- scope ---------------------------------------------------------------------

def test_nested_scope_inherits_and_restores():
    assert current_llm_scope() == {}
    with llm_scope('strategy_create', user_id=7, ref_id='run-1'):
        with llm_scope(step='plan'):
            assert current_llm_scope() == {'operation': 'strategy_create', 'user_id': 7,
                                           'ref_id': 'run-1', 'step': 'plan'}
        assert current_llm_scope()['step'] is None
    assert current_llm_scope() == {}


# --- recording hook ------------------------------------------------------------

def _fake_client(text="ok", prompt=1200, cached=200, completion=300, thoughts=500, error=None):
    def generate_content(model, contents, config=None):
        if error:
            raise RuntimeError(error)
        return SimpleNamespace(
            text=text,
            usage_metadata=SimpleNamespace(
                prompt_token_count=prompt, cached_content_token_count=cached,
                candidates_token_count=completion, thoughts_token_count=thoughts,
                total_token_count=prompt + completion + thoughts))
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def test_call_gemini_safe_records_scoped_usage(monkeypatch):
    _, user_id = _new_user()
    ref = _ref(uuid.uuid4().hex[:8])
    monkeypatch.setattr(core_llm, '_get_client', lambda api_key=None: _fake_client())

    with llm_scope('strategy_create', user_id=user_id, ref_id=ref, step='generate'):
        text, err, usage = core_llm.call_gemini_safe('gemini-3.8-flash', "prompt", tier='strong')

    assert (text, err) == ("ok", None)
    assert usage['thinking_tokens'] == 500 and usage['cached_tokens'] == 200
    calls = llm_usage.operation_calls('strategy_create', ref)
    assert len(calls) == 1
    row = calls[0]
    assert (row['user_id'], row['step'], row['tier'], row['model']) == \
        (user_id, 'generate', 'strong', 'gemini-3.8-flash')
    assert (row['prompt_tokens'], row['cached_tokens'], row['completion_tokens'],
            row['thinking_tokens']) == (1200, 200, 300, 500)
    assert row['cost_usd'] == pytest.approx(
        estimate_cost_usd('gemini-3.8-flash', 1200, 200, 300, 500))
    assert row['ok'] is True and row['latency_ms'] is not None


def test_call_gemini_safe_records_failures_and_unscoped_calls(monkeypatch):
    monkeypatch.setattr(core_llm, '_get_client',
                        lambda api_key=None: _fake_client(error=UNSCOPED_ERROR))
    text, err, usage = core_llm.call_gemini_safe('gemini-3.5-flash-lite', "prompt")
    assert text is None and "high load" in err
    # Scope-less: lands as its own 'unknown' operation under a synthetic
    # 'call-<id>' key (found by our error text — the DB is shared with other
    # sessions' tests, so no global counts here) …
    mine = [o for o in llm_usage.recent_operations(operation='unknown', limit=50)
            if llm_usage.operation_calls('unknown', o['ref_id'])[0]['error'] == UNSCOPED_ERROR]
    assert len(mine) == 1
    op = mine[0]
    assert op['failed_calls'] == 1 and op['calls'] == 1 and op['ref_id'].startswith('call-')
    # … and that synthetic key resolves in the drill-down, like a real ref.
    calls = llm_usage.operation_calls('unknown', op['ref_id'])
    assert len(calls) == 1 and calls[0]['ok'] is False and calls[0]['cost_usd'] == 0


def test_logging_failure_never_breaks_the_call(monkeypatch):
    monkeypatch.setattr(core_llm, '_get_client', lambda api_key=None: _fake_client(text="fine"))

    def boom(**kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(llm_usage, 'record_call', boom)
    text, err, _ = core_llm.call_gemini_safe('gemini-3.8-flash', "prompt")
    assert (text, err) == ("fine", None)


# --- runner attribution --------------------------------------------------------

def test_designer_run_scopes_every_call_to_the_run(monkeypatch):
    from app.agents import runner
    from app.agents.llm import fake_llm_call

    seen = []

    def spying_llm(prompt, tier='fast', json_mode=False):
        seen.append(dict(current_llm_scope(), tier=tier))
        return fake_llm_call(prompt, tier=tier, json_mode=json_mode)
    monkeypatch.setattr('app.agents.runner.get_llm_call', lambda: spying_llm)

    _, user_id = _new_user()
    run_id = runner.start_run(user_id, "withdraw 4% of my portfolio each year, inflation adjusted",
                              strategy_name="Scope Test")

    assert seen, "the fake run made no LLM calls"
    assert {s['operation'] for s in seen} == {'strategy_create'}
    assert {s['user_id'] for s in seen} == {user_id}
    assert {s['ref_id'] for s in seen} == {run_id}
    steps = [s['step'] for s in seen]
    assert 'extract_spec' in steps and 'generate' in steps
    # strong tier on the code-generation step
    assert any(s['step'] == 'generate' and s['tier'] == 'strong' for s in seen)
    # the scope does not leak out of the run
    assert current_llm_scope() == {}


# --- aggregates ----------------------------------------------------------------

def _record(op, ref, user_id, cost_parts, step='generate'):
    for prompt, completion, thinking in cost_parts:
        llm_usage.record_call(
            operation=op, model='gemini-3.8-flash', user_id=user_id, ref_id=ref, step=step,
            tier='strong', prompt_tokens=prompt, completion_tokens=completion,
            thinking_tokens=thinking,
            cost_usd=estimate_cost_usd('gemini-3.8-flash', prompt, 0, completion, thinking),
            latency_ms=100)


def test_operation_stats_aggregate_per_run_not_per_call():
    _, user_id = _new_user()
    op = f"test_op_{uuid.uuid4().hex[:6]}"   # private operation label: isolated stats
    # three runs: 1 call / 2 calls / 3 calls of equal size
    unit = (10_000, 2_000, 4_000)
    _record(op, _ref('r1'), user_id, [unit])
    _record(op, _ref('r2'), user_id, [unit, unit])
    _record(op, _ref('r3'), user_id, [unit, unit, unit])
    unit_cost = estimate_cost_usd('gemini-3.8-flash', *unit[:1], 0, *unit[1:])

    stats = {s['operation']: s for s in llm_usage.operation_stats(window=100)}[op]
    assert stats['n'] == 3
    assert stats['mean_cost_usd'] == pytest.approx(2 * unit_cost)
    assert stats['median_cost_usd'] == pytest.approx(2 * unit_cost)
    assert stats['max_cost_usd'] == pytest.approx(3 * unit_cost)
    assert stats['mean_calls'] == pytest.approx(2)
    assert stats['mean_thinking_tokens'] == pytest.approx(8_000)

    # window trims to the newest runs
    assert {s['operation']: s for s in llm_usage.operation_stats(window=1)}[op]['n'] == 1

    steps = [s for s in llm_usage.step_stats(window=100) if s['operation'] == op]
    assert len(steps) == 1 and steps[0]['step'] == 'generate'
    assert steps[0]['cost_per_operation_usd'] == pytest.approx(2 * unit_cost)
    assert steps[0]['calls_per_operation'] == pytest.approx(2)

    ops = llm_usage.user_operations(user_id)
    assert [o['ref_id'] for o in ops] == [_ref('r3'), _ref('r2'), _ref('r1')]
    assert ops[0]['calls'] == 3

    summary = llm_usage.user_summary(user_id)
    assert summary['operations'] == 3
    assert summary['all_time_cost_usd'] == pytest.approx(6 * unit_cost)

    me = next(u for u in llm_usage.user_totals(days=1, limit=1000) if u['user_id'] == user_id)
    assert me['operations'] == 3 and me['other'] == 3


def test_running_strategy_runs_are_left_out_of_window_stats():
    from db import strategy_generation as sg

    _, user_id = _new_user()
    run_id = str(uuid.uuid4())
    sg.create_run(run_id, user_id, f"stratgen-{run_id}", "in-flight test")   # status running
    _record('strategy_create', run_id, user_id, [(100_000, 20_000, 40_000)])  # deliberately huge
    huge = estimate_cost_usd('gemini-3.8-flash', 100_000, 0, 20_000, 40_000)
    cost_of_newest = lambda: {  # noqa: E731
        s['operation']: s for s in llm_usage.operation_stats(window=1)}['strategy_create']

    # Still generating: not the newest settled creation, so it doesn't rank.
    assert cost_of_newest()['max_cost_usd'] != pytest.approx(huge)

    sg.update_run(run_id, status='completed')
    assert cost_of_newest()['max_cost_usd'] == pytest.approx(huge)


# --- admin API -----------------------------------------------------------------

def test_admin_llm_usage_endpoints():
    admin_email, _ = _new_user(tier="ADMIN")
    headers = {**SECRET, "X-User-Email": admin_email}
    _, target_id = _new_user()
    _record('strategy_evolve', _ref(f"api-{uuid.uuid4().hex[:6]}"), target_id, [(5_000, 500, 1_000)],
            step='plan')

    r = client.get("/admin/llm-usage/summary?window=50&days=7", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body['window'] == 50
    assert 'gemini-3.8-flash' in body['prices']
    assert any(o['operation'] == 'strategy_evolve' for o in body['operations'])
    assert body['totals']['days'] == 7

    assert any(s['step'] == 'plan' for s in body['steps']['strategy_evolve'])

    r = client.get(f"/admin/llm-usage/users/{target_id}", headers=headers)
    assert r.status_code == 200
    detail = r.json()
    assert detail['user']['id'] == target_id
    assert detail['summary']['operations'] == 1
    assert detail['operations'][0]['operation'] == 'strategy_evolve'
    ref = detail['operations'][0]['ref_id']

    r = client.get(f"/admin/llm-usage/operations/strategy_evolve/{ref}", headers=headers)
    assert r.status_code == 200 and r.json()['calls'][0]['step'] == 'plan'

    r = client.get("/admin/llm-usage/users?days=7", headers=headers)
    assert r.status_code == 200
    assert any(u['user_id'] == target_id for u in r.json()['users'])

    assert client.get("/admin/llm-usage/users/999999999", headers=headers).status_code == 404


def test_admin_llm_usage_is_admin_only():
    email, _ = _new_user()  # FREE
    r = client.get("/admin/llm-usage/summary", headers={**SECRET, "X-User-Email": email})
    assert r.status_code == 403
