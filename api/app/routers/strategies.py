"""
W5: strategies CRUD + agentic generation.

Generation is a run, not a request/response: POST /strategies/generate starts
the graph and returns a run_id; the client tails /generate/{run_id}/events
(SSE over the persisted build log — reload-safe by design: state lives in
STRATEGY_GENERATION_EVENTS, the stream just tails it) and answers interrupts
via /resume. Credits are metered per RUN, up front.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps import get_current_user, verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])

TERMINAL_EVENTS = {'run_completed', 'run_failed', 'run_discarded'}


def _require_user(user: Optional[dict]) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to manage strategies")
    return user


def _serialize_strategy(row: dict, include_code: bool = True) -> dict:
    from db.database import db

    out = dict(row)
    out['parameters_json'] = db.deserialize_json_column(out.get('parameters_json')) or {}
    if not include_code:
        out.pop('code', None)
    for key in ('created_at', 'updated_at', 'last_validation_timestamp', 'cloned_at'):
        if out.get(key) is not None:
            out[key] = str(out[key])
    return out


def _owned_strategy(strategy_id: int, user: dict) -> dict:
    from db.database import db

    strategy = db.get_custom_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if strategy['user_id'] != user['id'] and not strategy.get('is_public'):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


# --- CRUD ------------------------------------------------------------------

@router.get("/strategies")
def list_strategies(user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db import strategy_generation as sg
    from db.database import db

    user = _require_user(user)
    rows = db.get_user_custom_strategies(user['id']) or []
    runs = sg.list_runs(user['id'])
    active_runs = [
        {**r, 'created_at': str(r['created_at']), 'updated_at': str(r['updated_at'])}
        for r in runs if r['status'] in ('running', 'needs_input')
    ]
    return {
        'strategies': [_serialize_strategy(r, include_code=False) for r in rows],
        'active_runs': active_runs,
    }


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: int, user: Optional[dict] = Depends(get_current_user)) -> dict:
    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    out = _serialize_strategy(strategy)
    out['is_owner'] = strategy['user_id'] == user['id']
    return out


@router.delete("/strategies/{strategy_id}")
def delete_strategy(strategy_id: int, user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    if not db.soft_delete_custom_strategy(strategy_id, user['id']):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {'deleted': True}


# --- Test run (user-initiated smoke test) ----------------------------------

class TestRun(BaseModel):
    strategy_params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/strategies/{strategy_id}/test")
def test_strategy(strategy_id: int, body: TestRun,
                  user: Optional[dict] = Depends(get_current_user)) -> dict:
    from app.agents.graph import TEST_PATHS, TEST_YEARS, _condense_paths, _sanitize
    from core.sandbox_tester import run_sandbox_test

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if not strategy.get('code'):
        raise HTTPException(status_code=422, detail="Strategy has no code to test")
    result = run_sandbox_test(
        strategy['code'], strategy['class_name'],
        {'num_years': TEST_YEARS, 'num_simulations': TEST_PATHS,
         'num_random_paths': TEST_PATHS, 'strategy_params': body.strategy_params})
    if not result.get('success'):
        return {'success': False, 'error': result.get('error')}
    return {'success': True,
            'summary_stats': _sanitize(result['summary_stats']),
            'paths': _sanitize(_condense_paths(result)),
            'num_paths': TEST_PATHS, 'num_years': TEST_YEARS}


# --- Evaluation (existing job type) ----------------------------------------

@router.post("/strategies/{strategy_id}/evaluate")
def evaluate_strategy(strategy_id: int,
                      user: Optional[dict] = Depends(get_current_user)) -> dict:
    from services.background_manager import BackgroundManager

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if not strategy.get('code'):
        raise HTTPException(status_code=422, detail="Strategy has no code to evaluate")
    job_id = BackgroundManager.start_strategy_evaluation(
        strategy_name=strategy['strategy_name'],
        is_custom=True,
        user_id=user['id'],
        custom_strategy_id=strategy_id,
        code=strategy['code'],
        class_name=strategy['class_name'],
        git_commit_sha=strategy.get('git_commit_sha'),
    )
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to queue evaluation job")
    return {'job_id': job_id}


@router.get("/strategies/{strategy_id}/evaluation")
def strategy_evaluation(strategy_id: int,
                        user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    evaluation = db.get_strategy_evaluation(
        strategy.get('git_commit_sha'),
        lookup_fallback_sha=strategy.get('clone_source_commit_sha'))
    if not evaluation:
        return {'evaluation': None}
    out = dict(evaluation)
    for key, value in list(out.items()):
        if hasattr(value, 'isoformat'):
            out[key] = str(value)
    if out.get('scenario_results_json'):
        out['scenario_results'] = db.deserialize_json_column(out.pop('scenario_results_json'))
    return {'evaluation': out}


# --- Agentic generation ----------------------------------------------------

class GenerateRequest(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    strategy_name: Optional[str] = Field(default=None, max_length=120)
    seed_strategy_id: Optional[int] = None


@router.post("/strategies/generate")
def generate_strategy(body: GenerateRequest,
                      user: Optional[dict] = Depends(get_current_user)) -> dict:
    from app.agents import runner
    from core.limits import LimitEnforcer
    from db.database import db

    user = _require_user(user)
    if not db.is_user_allowed(user['email']):
        raise HTTPException(status_code=403, detail="Beta access is full")

    # Per-RUN metering: one credit covers the whole run, internal retries
    # included (the old app accidentally never metered generation).
    limiter = LimitEnforcer(db)
    allowed, msg, usage = limiter.check_ai_credits(user['id'])
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)

    seed_strategy = None
    if body.seed_strategy_id is not None:
        seed = _owned_strategy(body.seed_strategy_id, user)
        if not seed.get('code'):
            raise HTTPException(status_code=422, detail="Seed strategy has no code")
        seed_strategy = {'id': seed['id'], 'strategy_name': seed['strategy_name'],
                         'description': seed.get('description'),
                         'ai_description': seed.get('ai_description'),
                         'code': seed['code']}

    limiter.increment_ai_credits(user['id'])
    run_id = runner.start_run(user['id'], body.request,
                              strategy_name=body.strategy_name,
                              seed_strategy=seed_strategy)
    return {'run_id': run_id, 'credits': usage}


def _owned_run(run_id: str, user: dict) -> dict:
    from db import strategy_generation as sg

    run = sg.get_run(run_id)
    if not run or run['user_id'] != user['id']:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/strategies/generate/{run_id}")
def generation_run(run_id: str, user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Full run state, rebuilt from the persisted build log (reload-safe)."""
    from db import strategy_generation as sg

    user = _require_user(user)
    run = _owned_run(run_id, user)
    events = sg.list_events(run_id)
    return {
        'run': {k: (str(v) if k in ('created_at', 'updated_at') else v)
                for k, v in run.items() if k != 'thread_id'},
        'events': [{'seq': e['seq'], 'type': e['type'], 'payload': e['payload'],
                    'created_at': str(e['created_at'])} for e in events],
    }


class ResumeRequest(BaseModel):
    kind: str  # clarify | review
    action: Optional[str] = None          # review: save | refine | discard
    feedback: Optional[str] = Field(default=None, max_length=4000)
    answers: Optional[Dict[str, Any]] = None  # clarify answers


@router.post("/strategies/generate/{run_id}/resume")
def resume_generation(run_id: str, body: ResumeRequest,
                      user: Optional[dict] = Depends(get_current_user)) -> dict:
    from app.agents import runner

    user = _require_user(user)
    _owned_run(run_id, user)
    payload: dict = {'kind': body.kind}
    if body.kind == 'clarify':
        if body.answers:
            payload['answers'] = body.answers
    elif body.kind == 'review':
        if body.action not in ('save', 'refine', 'discard'):
            raise HTTPException(status_code=422, detail="action must be save|refine|discard")
        payload['action'] = body.action
        if body.feedback:
            payload['feedback'] = body.feedback
    else:
        raise HTTPException(status_code=422, detail="kind must be clarify|review")
    try:
        runner.resume_run(run_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {'resumed': True}


@router.get("/strategies/generate/{run_id}/events")
async def generation_events(run_id: str, request: Request, after: int = 0,
                            user: Optional[dict] = Depends(get_current_user)):
    """SSE tail of the build log. `after` = last seen seq (reconnect cursor)."""
    from db import strategy_generation as sg

    user = _require_user(user)
    _owned_run(run_id, user)

    async def stream():
        cursor = after
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            try:
                events = await asyncio.to_thread(sg.list_events, run_id, cursor)
            except Exception:
                logging.exception("SSE event poll failed for run %s", run_id)
                events = []
            for event in events:
                cursor = event['seq']
                data = json.dumps({'seq': event['seq'], 'type': event['type'],
                                   'payload': event['payload']})
                yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"
                if event['type'] in TERMINAL_EVENTS:
                    return
            if events:
                idle = 0.0
            else:
                idle += 0.8
                if idle >= 15.0:
                    yield ": keepalive\n\n"
                    idle = 0.0
            await asyncio.sleep(0.8)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
