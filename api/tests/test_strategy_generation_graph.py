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
    assert len(artifact['paths']) == 10

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
