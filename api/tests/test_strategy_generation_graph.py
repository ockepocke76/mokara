"""
End-to-end tests for the W5 strategy-generation graph, run synchronously
against the real local Postgres (checkpointer + event log) with the canned
LLM provider — no API key, deterministic.
"""
import os
import uuid

import pytest

os.environ['MOKARA_SYNC_RUNNER'] = '1'
os.environ['MOKARA_FAKE_LLM'] = '1'

from app.agents import runner
from app.agents.llm import fake_llm_call
from db import strategy_generation as sg
from db.database import db


def _new_user() -> int:
    return db.get_or_create_user_id(f"w5-graph-{uuid.uuid4().hex[:10]}@example.com", "W5 Graph")


def _types(run_id):
    return [e['type'] for e in sg.list_events(run_id)]


def _stages_completed(run_id):
    return [e['payload'].get('stage') for e in sg.list_events(run_id)
            if e['type'] == 'stage_completed']


def test_happy_path_to_review_then_save():
    user_id = _new_user()
    run_id = runner.start_run(user_id, "withdraw 4% of my portfolio each year, inflation adjusted",
                              strategy_name="Graph Test Strategy")

    run = sg.get_run(run_id)
    assert run['status'] == 'needs_input'  # paused at the review interrupt
    types = _types(run_id)
    assert types[0] == 'run_started'
    assert types[-1] == 'needs_input'
    assert _stages_completed(run_id) == ['understanding', 'examples', 'blueprint',
                                         'code', 'checks', 'test_flight', 'behavior']

    # Test-flight artifact carries paired baseline + paths for the chart
    test_event = [e for e in sg.list_events(run_id)
                  if e['type'] == 'stage_completed' and e['payload'].get('stage') == 'test_flight'][0]
    artifact = test_event['payload']['artifact']
    assert artifact['summary_stats']['success_rate'] is not None
    assert artifact['baseline'] and artifact['baseline']['name'] == 'TrinityStrategy'
    # 10 random paths + the flagged historical backtest, each carrying the
    # full yearly series for the charts (not just net worth)
    random_paths = [p for p in artifact['paths'] if not p.get('is_backtest')]
    backtests = [p for p in artifact['paths'] if p.get('is_backtest')]
    assert len(random_paths) == 10
    assert len(backtests) == 1
    for path in (artifact['paths'][0], backtests[0]):
        for series in ('net_worth', 'asset_value', 'debt', 'cash',
                       'contributed', 'withdrawn'):
            values = path[series]
            assert len(values) == len(path['years'])
            # An engine column rename would yield all-None series of the right
            # length — require real numbers, not just the right shape.
            if series in ('net_worth', 'asset_value'):
                assert any(v is not None for v in values)

    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    run = sg.get_run(run_id)
    assert run['status'] == 'completed'
    assert run['final_strategy_id']
    assert 'run_completed' in _types(run_id)

    saved = db.get_custom_strategy(run['final_strategy_id'])
    assert saved['validation_status'] == 'validated'
    assert saved['code'] and 'BaseStrategy' in saved['code']
    assert saved['ai_description']  # analyze explanation flowed through


def test_clarify_interrupt_and_proceed_with_assumptions():
    user_id = _new_user()
    # '???' triggers needs_clarification in the fake provider
    run_id = runner.start_run(user_id, "???", strategy_name="Clarify Test")
    run = sg.get_run(run_id)
    assert run['status'] == 'needs_input'
    needs = [e for e in sg.list_events(run_id) if e['type'] == 'needs_input'][-1]
    assert needs['payload']['kind'] == 'clarify'
    assert needs['payload']['questions']

    # Proceed with assumptions (no answers) -> runs through to review
    runner.resume_run(run_id, {'kind': 'clarify'})
    run = sg.get_run(run_id)
    assert run['status'] == 'needs_input'
    needs = [e for e in sg.list_events(run_id) if e['type'] == 'needs_input'][-1]
    assert needs['payload']['kind'] == 'review'


def test_review_refine_loops_then_saves():
    user_id = _new_user()
    run_id = runner.start_run(user_id, "simple 4% rule", strategy_name="Refine Test")
    runner.resume_run(run_id, {'kind': 'review', 'action': 'refine',
                               'feedback': 'make the withdrawal rate 5%'})
    run = sg.get_run(run_id)
    assert run['status'] == 'needs_input'  # regenerated, back at review
    # The code stage completed twice (initial + refine round)
    assert _stages_completed(run_id).count('code') == 2
    assert any(e['type'] == 'attempt_started' for e in sg.list_events(run_id))

    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    assert sg.get_run(run_id)['status'] == 'completed'


def test_review_discard():
    user_id = _new_user()
    run_id = runner.start_run(user_id, "simple 4% rule", strategy_name="Discard Test")
    runner.resume_run(run_id, {'kind': 'review', 'action': 'discard'})
    run = sg.get_run(run_id)
    assert run['status'] == 'discarded'
    assert run['final_strategy_id'] is None
    assert 'run_discarded' in _types(run_id)


def test_broken_codegen_exhausts_attempts_and_saves_draft(monkeypatch):
    """A provider that always emits broken code must hit the retry cap,
    mark the run failed, and keep the last draft."""
    def broken_llm(prompt, tier='fast', json_mode=False):
        if prompt.startswith('TASK: generate'):
            return ("<description>broken</description>\n"
                    "```python\nclass BrokenStrategy(BaseStrategy):\n"
                    "    def initialize_portfolio(self, a, b):\n"
                    "        return {'action': 'BUY_ASSET', 'cash_amount': a['cash']}\n```")
        return fake_llm_call(prompt, tier=tier, json_mode=json_mode)

    monkeypatch.setattr('app.agents.runner.get_llm_call', lambda: broken_llm)

    user_id = _new_user()
    run_id = runner.start_run(user_id, "simple 4% rule", strategy_name="Broken Test")
    run = sg.get_run(run_id)
    assert run['status'] == 'failed'
    assert 'attempts' in (run['failure_summary'] or '')
    types = _types(run_id)
    assert 'run_failed' in types
    assert types.count('attempt_started') == 2  # attempts 2 and 3 announced
    # Draft kept with failed status, under a suffixed name so it can never
    # overwrite an existing strategy of the same name (evolve seeds reuse
    # the seed's name).
    failed_event = [e for e in sg.list_events(run_id) if e['type'] == 'run_failed'][0]
    draft_id = failed_event['payload'].get('draft_id')
    assert draft_id
    draft = db.get_custom_strategy(draft_id)
    assert draft['validation_status'] == 'failed'
    assert '(draft ' in draft['strategy_name']


def _seed_strategy(user_id: int, name: str = "Seed FIRE"):
    """A validated strategy row to evolve, built from the canned code template."""
    from app.agents.llm import _FAKE_CODE_TEMPLATE

    code = _FAKE_CODE_TEMPLATE.format(class_name="SeedFireStrategy").strip()
    sid = db.save_custom_strategy(
        user_id=user_id, strategy_name=name, class_name="SeedFireStrategy",
        description="A 4% rule strategy", ai_description="Withdraws 4% a year.",
        code=code, parameters_json={"withdrawal_rate": {"default": 0.04}},
        validation_status="validated")
    assert sid
    return sid, code


def _start_evolve(user_id: int, sid: int, request: str) -> str:
    seed = db.get_custom_strategy(sid)
    return runner.start_run(user_id, request, seed_strategy={
        'id': sid, 'strategy_name': seed['strategy_name'],
        'class_name': seed['class_name'], 'description': seed.get('description'),
        'ai_description': seed.get('ai_description'), 'code': seed['code']})


def test_evolve_parameter_change_is_minimal_edit():
    user_id = _new_user()
    sid, seed_code = _seed_strategy(user_id)
    request = "change the default withdrawal rate to 5%"
    run_id = _start_evolve(user_id, sid, request)

    assert sg.get_run(run_id)['status'] == 'needs_input'  # paused at review
    events = sg.list_events(run_id)

    # The spec is a change spec, not a fresh strategy spec
    spec_event = [e for e in events if e['type'] == 'stage_completed'
                  and e['payload'].get('stage') == 'understanding'][0]
    spec = spec_event['payload']['artifact']['spec']
    assert spec['change_scope'] == 'parameter_only'
    assert spec['changes']

    # No outside examples: the seed itself is the only reference
    examples_event = [e for e in events if e['type'] == 'stage_completed'
                      and e['payload'].get('stage') == 'examples'][0]
    assert examples_event['payload']['artifact']['examples'] == [
        {'name': 'Seed FIRE', 'source': 'seed', 'score': None}]

    # Code artifact: same class, marked as evolution, carries a diff
    code_event = [e for e in events if e['type'] == 'stage_completed'
                  and e['payload'].get('stage') == 'code'][0]
    artifact = code_event['payload']['artifact']
    assert artifact['is_evolution'] is True
    assert artifact['class_name'] == 'SeedFireStrategy'
    assert artifact['diff'] and '-' in artifact['diff']

    # The deterministic minimal-change check passed
    checks = [e for e in events if e['type'] == 'stage_progress'
              and e['payload'].get('check') == 'minimal_change']
    assert checks and checks[-1]['payload']['passed'] is True

    # The paired baseline is the strategy BEFORE the change
    test_event = [e for e in events if e['type'] == 'stage_completed'
                  and e['payload'].get('stage') == 'test_flight'][0]
    baseline = test_event['payload']['artifact']['baseline']
    assert baseline and baseline['name'] == 'Seed FIRE (before this change)'

    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    run = sg.get_run(run_id)
    assert run['status'] == 'completed'
    assert run['final_strategy_id'] == sid  # updated in place, not a new row

    saved = db.get_custom_strategy(sid)
    assert saved['class_name'] == 'SeedFireStrategy'
    # Exactly the requested default changed; every other line survived verbatim
    assert saved['code'] == seed_code.replace("'default': 0.04", "'default': 0.05")

    history = db.get_strategy_evolution_history(sid, include_code=True)
    assert history and history[-1]['request'] == request
    # The pre-change code is snapshotted, so a bad evolve is recoverable
    assert history[-1]['previous_code'] == seed_code


def test_evolve_structural_request_falls_back_to_rebuild():
    user_id = _new_user()
    sid, seed_code = _seed_strategy(user_id, name="Rebuild Me")
    # 'completely' makes the canned evolve_spec judge the change structural
    run_id = _start_evolve(user_id, sid,
                           "completely change the approach: borrow instead of selling")

    assert sg.get_run(run_id)['status'] == 'needs_input'
    events = sg.list_events(run_id)
    code_event = [e for e in events if e['type'] == 'stage_completed'
                  and e['payload'].get('stage') == 'code'][0]
    # Structural = full create pipeline: a rebuild gets no before/after diff
    assert 'diff' not in code_event['payload']['artifact']
    # No minimal-change guard on a deliberate rebuild
    assert not [e for e in events if e['type'] == 'stage_progress'
                and e['payload'].get('check') == 'minimal_change']

    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    run = sg.get_run(run_id)
    assert run['status'] == 'completed'
    assert run['final_strategy_id'] == sid  # still saved into the seed row


_REWRITE_CODE = '''
class SeedFireStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {'spend_rate': {'description': 'Annual spend rate',
                               'default': 0.03, 'min': 0.01, 'max': 0.08, 'step': 0.005}}

    @property
    def shortfall_funding_policy(self):
        return ['USE_CASH', 'SELL_ASSETS']

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        rate = self.params.get('spend_rate', 0.03)
        return portfolio_state.get('net_worth', 0) * rate

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        need = desired_drawdown + mandatory_costs
        return {'amount_sold': need, 'amount_bought': 0.0,
                'debt_increase': 0.0, 'debt_repayment': 0.0, 'amount_contributed': 0.0}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''


def test_evolve_rewrite_is_caught_by_minimal_change_guard(monkeypatch):
    """A generator that rewrites the strategy instead of editing it must trip
    the deterministic fidelity check, exhaust rework, and leave the seed
    strategy untouched."""
    def rewriting_llm(prompt, tier='fast', json_mode=False):
        if prompt.startswith('TASK: evolve_generate'):
            return ("<description>rewritten</description>\n"
                    f"```python\n{_REWRITE_CODE.strip()}\n```")
        return fake_llm_call(prompt, tier=tier, json_mode=json_mode)

    monkeypatch.setattr('app.agents.runner.get_llm_call', lambda: rewriting_llm)

    user_id = _new_user()
    sid, seed_code = _seed_strategy(user_id, name="Guarded FIRE")
    run_id = _start_evolve(user_id, sid, "set the default withdrawal rate to 5%")

    run = sg.get_run(run_id)
    assert run['status'] == 'failed'
    checks = [e for e in sg.list_events(run_id) if e['type'] == 'stage_progress'
              and e['payload'].get('check') == 'minimal_change']
    assert checks and all(c['payload']['passed'] is False for c in checks)

    # The seed strategy survives untouched; the broken draft went elsewhere
    saved = db.get_custom_strategy(sid)
    assert saved['code'] == seed_code
    assert saved['validation_status'] == 'validated'
    draft_id = [e for e in sg.list_events(run_id)
                if e['type'] == 'run_failed'][0]['payload'].get('draft_id')
    assert draft_id and draft_id != sid
    assert '(draft ' in db.get_custom_strategy(draft_id)['strategy_name']


def test_evolve_refine_respecs_against_seed():
    """A review refine on an evolve run must re-derive the change spec (the
    frozen original scope would otherwise reject feedback that widens it)."""
    user_id = _new_user()
    sid, _seed_code = _seed_strategy(user_id, name="Refine FIRE")
    run_id = _start_evolve(user_id, sid, "change the default withdrawal rate to 5%")

    runner.resume_run(run_id, {'kind': 'review', 'action': 'refine',
                               'feedback': 'and round the rate to whole percents'})
    run = sg.get_run(run_id)
    assert run['status'] == 'needs_input'  # back at review after the refine round
    # understanding ran twice: the refine re-specs instead of blindly
    # regenerating against the stale plan
    assert _stages_completed(run_id).count('understanding') == 2
    assert _stages_completed(run_id).count('code') == 2

    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    run = sg.get_run(run_id)
    assert run['status'] == 'completed'
    assert run['final_strategy_id'] == sid


def test_evolve_verbatim_seed_output_is_rejected(monkeypatch):
    """A generator that returns the seed unchanged must fail the fidelity
    check ('change never applied'), not save a no-op evolve."""
    def parrot_llm(prompt, tier='fast', json_mode=False):
        if prompt.startswith('TASK: evolve_generate'):
            seed = prompt.split("```python", 1)[1].split("```", 1)[0].strip()
            return f"<description>unchanged</description>\n```python\n{seed}\n```"
        return fake_llm_call(prompt, tier=tier, json_mode=json_mode)

    monkeypatch.setattr('app.agents.runner.get_llm_call', lambda: parrot_llm)

    user_id = _new_user()
    sid, seed_code = _seed_strategy(user_id, name="Parrot FIRE")
    run_id = _start_evolve(user_id, sid, "set the default withdrawal rate to 5%")

    run = sg.get_run(run_id)
    assert run['status'] == 'failed'
    checks = [e for e in sg.list_events(run_id) if e['type'] == 'stage_progress'
              and e['payload'].get('check') == 'minimal_change']
    assert checks and all(c['payload']['passed'] is False for c in checks)
    assert 'never applied' in checks[-1]['payload']['message']
    assert db.get_custom_strategy(sid)['code'] == seed_code  # seed untouched


def test_evolve_clone_snapshots_parent_code():
    """The previous_code snapshot must COALESCE from the parent for a
    pure-reference clone (whose own code column is NULL)."""
    user_id = _new_user()
    parent_id, parent_code = _seed_strategy(user_id, name="Clone Parent")
    clone_id = db.save_custom_strategy(
        user_id=user_id, strategy_name="My Clone", class_name="SeedFireStrategy",
        description='', ai_description='', code=None, parameters_json={},
        validation_status='validated', parent_strategy_id=parent_id)
    assert clone_id and clone_id != parent_id

    run_id = _start_evolve(user_id, clone_id, "change the default withdrawal rate to 5%")
    runner.resume_run(run_id, {'kind': 'review', 'action': 'save'})
    assert sg.get_run(run_id)['status'] == 'completed'

    history = db.get_strategy_evolution_history(clone_id, include_code=True)
    assert history and history[-1]['previous_code'] == parent_code
    # the default listing strips the snapshots in SQL
    stripped = db.get_strategy_evolution_history(clone_id)
    assert stripped and 'previous_code' not in stripped[-1]
    # the parent's own row is untouched
    assert db.get_custom_strategy(parent_id)['code'] == parent_code


def test_change_scope_normalization_and_legacy_guard():
    from app.agents.graph import _minimal_evolution, _normalize_change_scope

    spec = {'change_scope': 'Structural Redesign'}
    _normalize_change_scope(spec)
    assert spec['change_scope'] == 'structural'
    spec = {'change_scope': 'Parameter_Only'}
    _normalize_change_scope(spec)
    assert spec['change_scope'] == 'parameter_only'
    spec = {}
    _normalize_change_scope(spec)
    assert spec['change_scope'] == 'behavioral'
    # a checkpointed pre-change-spec run (no 'changes') falls back to the
    # create pipeline instead of editing with an empty change list
    assert not _minimal_evolution({'seed_code': 'x',
                                   'spec': {'change_scope': 'behavioral'}})
    assert _minimal_evolution({'seed_code': 'x',
                               'spec': {'change_scope': 'behavioral',
                                        'changes': ['a']}})
    assert not _minimal_evolution({'seed_code': 'x',
                                   'spec': {'change_scope': 'structural',
                                            'changes': ['a']}})


def test_blueprint_test_capital_clamped():
    from app.agents.graph import _test_capital

    assert _test_capital({'test_initial_investment': 10_000}, 500_000) == 10_000
    assert _test_capital({'test_initial_investment': '25000'}, 500_000) == 25_000
    assert _test_capital({}, 500_000) == 500_000
    assert _test_capital({'test_initial_investment': None}, 500_000) == 500_000
    assert _test_capital({'test_initial_investment': 'lots'}, 500_000) == 500_000
    assert _test_capital({'test_initial_investment': -5}, 500_000) == 0.0
    assert _test_capital({'test_initial_investment': 9e12}, 500_000) == 10_000_000.0
    assert _test_capital({'test_initial_investment': float('nan')}, 500_000) == 500_000
