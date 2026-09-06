"""
Run lifecycle for the strategy-generation graph.

- The compiled graph + Postgres checkpointer are module-level singletons; the
  checkpointer's tables live in the same Postgres as everything else, so an
  interrupted run survives process restarts and resumes by thread_id.
- start_run/resume_run execute the graph in a daemon thread (the engine and
  LLM calls are sync); the SSE endpoint tails STRATEGY_GENERATION_EVENTS, so
  no cross-thread plumbing is needed. MOKARA_SYNC_RUNNER=1 runs inline
  (tests, debugging).
- The runner — not the nodes — emits needs_input: interrupt() re-executes its
  node from the top on resume, so nodes must not emit before pausing.
"""
import logging
import os
import threading
import uuid

from langgraph.types import Command

from app.agents.graph import build_graph
from app.agents.llm import get_llm_call
from db import strategy_generation as sg

_lock = threading.Lock()
_graph = None
_pool = None


def _dsn() -> str:
    """Same database the engine uses — mirror the live db object's config,
    not the env directly (the factory has local-dev fallbacks)."""
    from db.database import db

    cfg = getattr(db, 'config', {}) or {}
    host = cfg.get('host', 'localhost')
    port = cfg.get('port', 5432)
    name = cfg.get('database', 'btc_simulator_local')
    user = cfg.get('user', '')
    password = cfg.get('password', '')
    sslmode = cfg.get('sslmode', 'prefer')
    auth = f"{user}:{password}@" if password else (f"{user}@" if user else "")
    return f"postgresql://{auth}{host}:{port}/{name}?sslmode={sslmode}"


def get_graph():
    global _graph, _pool
    with _lock:
        if _graph is None:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            _pool = ConnectionPool(_dsn(), min_size=1, max_size=4,
                                   kwargs={'autocommit': True}, open=True)
            checkpointer = PostgresSaver(_pool)
            checkpointer.setup()
            _graph = build_graph(checkpointer)
        return _graph


def _config(thread_id: str) -> dict:
    return {'configurable': {'thread_id': thread_id, 'llm_call': get_llm_call()}}


def _execute(run_id: str, thread_id: str, graph_input) -> None:
    graph = get_graph()
    config = _config(thread_id)
    try:
        result = graph.invoke(graph_input, config)
    except Exception as e:
        logging.exception("strategy generation run %s crashed", run_id)
        _fail_run(run_id, thread_id, e)
        return

    interrupts = result.get('__interrupt__') if isinstance(result, dict) else None
    if interrupts:
        payload = interrupts[0].value if hasattr(interrupts[0], 'value') else {}
        sg.update_run(run_id, status='needs_input')
        sg.append_event(run_id, 'needs_input', payload if isinstance(payload, dict) else {})
    # Terminal outcomes (save/fail/discard nodes) already wrote status + events.


def _fail_run(run_id: str, thread_id: str, error: Exception) -> None:
    """Unexpected crash (LLM outage, budget, bug): keep any draft, be honest."""
    from db.database import db

    summary = f"Generation stopped unexpectedly: {error}"
    draft_id = None
    try:
        snapshot = get_graph().get_state(_config(thread_id))
        state = snapshot.values if snapshot else {}
        if state.get('code'):
            draft_id = db.save_custom_strategy(
                user_id=state['user_id'],
                strategy_name=state.get('strategy_name', 'Unnamed draft'),
                class_name=state.get('class_name', 'CustomStrategy'),
                description=state.get('description', ''),
                ai_description='',
                code=state['code'],
                parameters_json=state.get('parameters') or {},
                validation_status='failed',
                validation_error=str(error),
            ) or None
    except Exception:
        logging.exception("draft salvage failed for run %s", run_id)
    try:
        sg.update_run(run_id, status='failed', failure_summary=summary,
                      final_strategy_id=draft_id)
        sg.append_event(run_id, 'run_failed',
                        {'summary': summary, 'draft_id': draft_id})
    except Exception:
        logging.exception("failure bookkeeping failed for run %s", run_id)


def _launch(run_id: str, thread_id: str, graph_input) -> None:
    if os.environ.get('MOKARA_SYNC_RUNNER') == '1':
        _execute(run_id, thread_id, graph_input)
        return
    threading.Thread(target=_execute, args=(run_id, thread_id, graph_input),
                     daemon=True, name=f"strategy-gen-{run_id[:8]}").start()


def start_run(user_id: int, user_request: str, strategy_name: str | None = None,
              seed_strategy: dict | None = None) -> str:
    run_id = str(uuid.uuid4())
    thread_id = f"stratgen-{run_id}"
    sg.create_run(run_id, user_id, thread_id, user_request,
                  strategy_name=strategy_name,
                  seed_strategy_id=(seed_strategy or {}).get('id'))
    sg.append_event(run_id, 'run_started', {
        'user_request': user_request, 'strategy_name': strategy_name,
        'seed_strategy': ({'id': seed_strategy['id'],
                           'name': seed_strategy.get('strategy_name')}
                          if seed_strategy else None)})
    initial_state = {
        'run_id': run_id,
        'user_id': user_id,
        'user_request': user_request,
        'strategy_name': strategy_name or '',
        'seed': int(run_id.replace('-', '')[:8], 16) & 0x7FFFFFFF,
        'attempts': 0, 'revisions': 0, 'llm_calls': 0,
    }
    if seed_strategy:
        initial_state.update({
            'seed_name': seed_strategy.get('strategy_name'),
            'seed_description': (seed_strategy.get('ai_description')
                                 or seed_strategy.get('description')),
            'seed_code': seed_strategy.get('code'),
        })
    _launch(run_id, thread_id, initial_state)
    return run_id


def resume_run(run_id: str, payload: dict) -> None:
    run = sg.get_run(run_id)
    if not run:
        raise KeyError(f"unknown run {run_id}")
    if run['status'] != 'needs_input':
        raise ValueError(f"run {run_id} is not waiting for input (status={run['status']})")
    sg.update_run(run_id, status='running')
    sg.append_event(run_id, 'input_received', {'kind': payload.get('kind')})
    _launch(run_id, run['thread_id'], Command(resume=payload))
