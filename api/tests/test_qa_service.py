"""
Strategy Q&A: context built from a real (canned-LLM) designer build and from
simulation frames, triage refusals, on-topic answers, credits, ownership.
"""
import os
import uuid

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

os.environ['MOKARA_SYNC_RUNNER'] = '1'
os.environ['MOKARA_FAKE_LLM'] = '1'

from app.agents import runner
from app.agents.llm import fake_llm_call
from app.qa import context as qa_context
from app.qa import prompts, service
from db import strategy_generation as sg
from db.database import db


def _user() -> dict:
    email = f"qa-svc-{uuid.uuid4().hex[:10]}@example.com"
    return {'email': email, 'name': 'QA Svc', 'id': db.get_or_create_user_id(email, 'QA Svc')}


def _credits_used(user_id: int) -> int:
    from core.limits import LimitEnforcer
    return LimitEnforcer(db).check_ai_credits(user_id)[2]['current']


@pytest.fixture(scope='module')
def build():
    user = _user()
    run_id = runner.start_run(user['id'], "withdraw 4% of my portfolio each year, inflation adjusted",
                              strategy_name="QA Build")
    assert sg.get_run(run_id)['status'] == 'needs_input'
    return user, run_id


def test_generation_run_context_carries_code_traces_and_state(build):
    user, run_id = build
    ctx = qa_context.from_generation_run(sg.get_run(run_id), sg.list_events(run_id))
    assert ctx.subject_type == 'generation_run'
    assert ctx.strategy_name == 'QA Build'
    assert 'BaseStrategy' in ctx.strategy_source
    assert ctx.blueprint_rules and ctx.parameters == {'withdrawal_rate': 0.04}
    assert ctx.state_metrics[0]['name'] == 'state_withdrawal_target'
    labels = [t['label'] for t in ctx.traces]
    assert labels[0].startswith('worst path') and labels[1].startswith('median path')
    assert labels[-1].startswith('historical backtest')
    worst = ctx.traces[0]['years']
    assert worst[0]['year'] == 0 and worst[1]['state_withdrawal_target'] > 0
    assert ctx.has_state_metrics
    assert ctx.prior_analysis['conforms_to_spec'] is True
    assert ctx.run_conditions['num_paths'] == 10


def test_context_is_none_before_test_flight():
    run = {'id': 'x', 'user_id': 1, 'strategy_name': 'Early', 'spec': None}
    events = [{'type': 'stage_completed',
               'payload': {'stage': 'code', 'artifact': {'code': 'class X: pass'}}}]
    assert qa_context.from_generation_run(run, events) is None


def test_off_topic_question_is_refused_without_charging(build):
    user, run_id = build
    before = _credits_used(user['id'])
    result = service.ask(user, 'generation_run', run_id, "What is the capital of France?")
    assert result['assistant']['content'] == prompts.REFUSAL
    assert result['assistant']['on_topic'] is False
    assert result['assistant']['llm_calls'] == 1
    assert result['can_refine'] is True  # paused at review
    assert _credits_used(user['id']) == before


def test_on_topic_question_answers_with_suggested_change_and_charges(build):
    user, run_id = build
    before = _credits_used(user['id'])
    seen = []

    def spy(prompt, tier='fast', json_mode=False):
        seen.append((prompt.split('\n', 1)[0], tier))
        return fake_llm_call(prompt, tier=tier, json_mode=json_mode)

    result = service.ask(user, 'generation_run', run_id,
                         "Why did the strategy never change what it sold each year, "
                         "and what would need to change?", llm_call=spy)
    assert seen == [('TASK: qa_triage', 'fast'), ('TASK: qa_answer', 'strong')]
    assistant = result['assistant']
    assert assistant['on_topic'] is True
    assert 'state_withdrawal_target' in assistant['content']
    assert assistant['suggested_change']['refine_feedback'].startswith('Change the withdrawal_rate')
    assert _credits_used(user['id']) == before + 1

    thread = service.get_thread(user, 'generation_run', run_id)
    roles = [m['role'] for m in thread['messages']]
    assert roles == ['user', 'assistant', 'user', 'assistant']
    assert thread['thread_id'] == result['thread_id']


def test_answer_prompt_includes_history_code_and_traces(build):
    user, run_id = build
    ctx = qa_context.from_generation_run(sg.get_run(run_id), sg.list_events(run_id))
    prompt = prompts.answer_prompt(ctx, [{'role': 'user', 'content': 'earlier q'},
                                         {'role': 'assistant', 'content': 'earlier a'}],
                                   "follow-up?")
    assert prompt.startswith('TASK: qa_answer')
    assert 'USER: earlier q' in prompt and 'ASSISTANT: earlier a' in prompt
    assert 'class ' in prompt and 'state_withdrawal_target' in prompt
    assert 'cite them by name and year' in prompt  # state metrics present


def test_provider_failure_persists_nothing_and_maps_to_502(build):
    user, run_id = build
    before = len(service.get_thread(user, 'generation_run', run_id)['messages'])

    def down(prompt, tier='fast', json_mode=False):
        from app.agents.llm import LLMError
        raise LLMError("quota exceeded")

    with pytest.raises(service.QAError) as e:
        service.ask(user, 'generation_run', run_id, "why did it sell?", llm_call=down)
    assert e.value.status_code == 502 and 'quota' in e.value.detail
    assert len(service.get_thread(user, 'generation_run', run_id)['messages']) == before


def test_other_users_build_is_not_found(build):
    _owner, run_id = build
    stranger = _user()
    with pytest.raises(service.QAError) as e:
        service.get_thread(stranger, 'generation_run', run_id)
    assert e.value.status_code == 404
    with pytest.raises(service.QAError) as e:
        service.ask(stranger, 'generation_run', run_id, "why?")
    assert e.value.status_code == 404


def test_unknown_subject_and_empty_question_rejected(build):
    user, run_id = build
    with pytest.raises(service.QAError) as e:
        service.ask(user, 'report', run_id, "why?")
    assert e.value.status_code == 422
    with pytest.raises(service.QAError) as e:
        service.ask(user, 'generation_run', run_id, "   ")
    assert e.value.status_code == 422


def test_missing_simulation_is_not_found():
    with pytest.raises(HTTPException) as e:
        service.get_thread(_user(), 'simulation', 'no-such-hash')
    assert e.value.status_code == 404


def _sampled_frame() -> pd.DataFrame:
    years = [0, 1, 2]
    metrics = ['Net Worth', 'Asset Value', 'Debt', 'Cash', 'Consumption Delivered',
               'Amount Sold', 'Amount Bought', 'Debt Change', 'Amount Contributed',
               'state_transitioned']
    index = pd.MultiIndex.from_product([years, metrics], names=['Year', 'Metric'])
    data = {}
    for sim, final in (('Sim_3', 500_000.0), ('Sim_7', 1_200_000.0), ('Sim_9', 900_000.0)):
        values = []
        for y in years:
            row = {m: float(100 * y) for m in metrics}
            row['Net Worth'] = final if y == 2 else 1_000_000.0
            row['state_transitioned'] = np.nan if y == 0 else float(y == 2)
            values.extend(row[m] for m in metrics)
        data[sim] = values
    return pd.DataFrame(data, index=index)


def test_simulation_context_from_frames_custom_strategy():
    params = {'strategy': 'custom', 'custom_strategy_name': 'Lifecycle',
              'custom_strategy_ai_description': 'Transitions at a ratio.',
              'custom_strategy_code': 'class Lifecycle(BaseStrategy): ...',
              'custom_strategy_params': {'transition_ratio': 6.0},
              'num_years': 2, 'num_simulations': 1000, 'currency': 'SEK',
              'initial_investment': 1_000_000}
    stats = {'median_final_net_worth': 900_000.0, 'chance_of_ruin': 0.01,
             'median_drawdown_values': {'1': 1.0}, 'analysis': 'Prior narrative.',
             'main_outcome': '', 'acf_data': {'acf_values': [1, 2]}}
    ctx = qa_context.from_simulation('abc', params, stats, _sampled_frame())
    assert ctx.subject_type == 'simulation'
    assert ctx.strategy_name == 'Lifecycle' and ctx.parameters == {'transition_ratio': 6.0}
    assert ctx.summary_stats == {'median_final_net_worth': 900_000.0, 'chance_of_ruin': 0.01}
    assert ctx.prior_analysis == {'analysis': 'Prior narrative.'}
    assert ctx.run_conditions['simulation_hash'] == 'abc' and ctx.run_conditions['currency'] == 'SEK'
    assert [t['label'] for t in ctx.traces] == ['worst sampled path (Sim_3)',
                                                'median sampled path (Sim_9)']
    worst = ctx.traces[0]['years']
    assert worst[2]['net_worth'] == 500_000
    assert worst[0]['state_transitioned'] is None and worst[2]['state_transitioned'] == 1.0
    assert ctx.has_state_metrics


def test_simulation_context_builtin_strategy_has_source_and_description():
    ctx = qa_context.from_simulation('h', {'strategy': 'trinity', 'num_years': 30},
                                     {'chance_of_ruin': 0.05}, None)
    assert ctx.strategy_name == 'Trinity'
    assert 'class TrinityStrategy' in ctx.strategy_source
    assert ctx.strategy_description
    assert ctx.traces == [] and not ctx.has_state_metrics
    assert 'infer its decisions from the code' in prompts.answer_prompt(ctx, [], 'why?')
