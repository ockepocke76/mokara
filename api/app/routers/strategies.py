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

from app.deps import get_current_user, require_user as _require_user, verify_internal_secret

router = APIRouter(dependencies=[Depends(verify_internal_secret)])

TERMINAL_EVENTS = {'run_completed', 'run_failed', 'run_discarded'}


def _stringify_dates(row: dict) -> dict:
    """datetime -> str for JSON, whatever the column is called."""
    return {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in row.items()}


def _serialize_strategy(row: dict, include_code: bool = True) -> dict:
    from db.database import db

    out = dict(row)
    out['parameters_json'] = db.deserialize_json_column(out.get('parameters_json')) or {}
    if not include_code:
        out.pop('code', None)
    return _stringify_dates(out)


def _owned_strategy(strategy_id: int, user: dict) -> dict:
    from db.database import db

    strategy = db.get_custom_strategy(strategy_id)
    if not strategy or strategy.get('deleted_at'):
        raise HTTPException(status_code=404, detail="Strategy not found")
    if strategy['user_id'] != user['id'] and not strategy.get('is_public'):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


def _builtin_key(strategy: dict) -> Optional[str]:
    """'trinity'|'bbd'|'grsr' for built-in rows (user_id=0), else None."""
    if strategy.get('user_id') != 0:
        return None
    from services.builtin_sync import BUILTIN_STRATEGIES

    return next((b['key'] for b in BUILTIN_STRATEGIES
                 if b['name'] == strategy['strategy_name']), None)


def _builtin_leaderboard_evaluations() -> Dict[str, dict]:
    """Built-in evaluations predate the SHA sync — they live on the
    leaderboard as is_custom=FALSE rows keyed by name (V34). The is_custom
    filter matters: without it a user-published strategy sharing a built-in's
    name would be served as the built-in's evaluation."""
    from db.database import db

    rows: Dict[str, dict] = {}
    for e in (db.get_leaderboard(limit=500) or []):
        if not e.get('is_custom') and e.get('strategy_name') not in rows:
            rows[e['strategy_name']] = dict(e)
    return rows


# --- CRUD ------------------------------------------------------------------

@router.get("/strategies")
def list_strategies(user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db import strategy_generation as sg
    from db.database import db

    user = _require_user(user)
    rows = db.get_user_custom_strategies(user['id']) or []
    runs = sg.list_runs(user['id'])
    active_runs = [_stringify_dates(r) for r in runs
                   if r['status'] in ('running', 'needs_input')]
    return {
        'strategies': [_serialize_strategy(r, include_code=False) for r in rows],
        'builtins': [_stringify_dates(r) for r in _builtin_list_rows()],
        'active_runs': active_runs,
    }


def _builtin_list_rows() -> list:
    """Built-in strategies (user_id=0, synced at startup) with their latest
    evaluation — get_user_custom_strategies deliberately excludes them."""
    from db.database import db
    from psycopg2 import extras

    conn = db.get_connection()
    try:
        cursor = db._get_cursor(conn, cursor_factory=extras.RealDictCursor)
        cursor.execute("""
            SELECT c.id, c.user_id, c.strategy_name, c.description,
                   c.ai_description, c.validation_status, c.updated_at,
                   e.excellence_score, (e.id IS NOT NULL) AS has_evaluation
            FROM CUSTOM_STRATEGIES c
            LEFT JOIN LATERAL (
                SELECT id, excellence_score FROM STRATEGY_EVALUATIONS e
                WHERE e.git_commit_sha = c.git_commit_sha
                ORDER BY e.created_at DESC LIMIT 1
            ) e ON TRUE
            WHERE c.user_id = 0 AND c.deleted_at IS NULL
            ORDER BY c.strategy_name
        """)
        rows = [dict(r) for r in cursor.fetchall()]
    except Exception:
        logging.exception("builtin list query failed")
        return []
    finally:
        db.release_connection(conn)

    # Fill in scores the SHA join couldn't find (see helper docstring).
    missing = [r for r in rows if not r.get('has_evaluation')]
    if missing:
        try:
            evaluations = _builtin_leaderboard_evaluations()
            for row in missing:
                evaluation = evaluations.get(row['strategy_name'])
                if evaluation and evaluation.get('excellence_score') is not None:
                    row['excellence_score'] = evaluation['excellence_score']
                    row['has_evaluation'] = True
        except Exception:
            logging.exception("builtin leaderboard score fallback failed")
    return rows


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: int, user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    out = _serialize_strategy(strategy)
    out['is_owner'] = strategy['user_id'] == user['id']
    out['is_builtin'] = strategy['user_id'] == 0
    conn = db.get_connection()
    try:
        # Same clone/fork definition as the leaderboard query, so the two
        # pages never disagree about one strategy's usage numbers.
        cursor = db._get_cursor(conn)
        cursor.execute("""
            SELECT COUNT(*) FILTER (WHERE is_clone_unedited = TRUE),
                   COUNT(*) FILTER (WHERE is_clone_unedited = FALSE)
            FROM CUSTOM_STRATEGIES WHERE parent_strategy_id = %s
        """, (strategy_id,))
        clones, forks = cursor.fetchone()
        out['usage_clone_count'] = clones or 0
        out['usage_fork_count'] = forks or 0
    except Exception:
        logging.exception("usage count query failed")
        out['usage_clone_count'] = 0
        out['usage_fork_count'] = 0
    finally:
        db.release_connection(conn)
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
    if strategy['user_id'] != user['id']:
        # Test flights execute the strategy's code synchronously in this
        # process — owner-only, like evaluate. Clone a public strategy first.
        raise HTTPException(status_code=403, detail="Only the owner can run a test flight")
    if not strategy.get('code'):
        raise HTTPException(status_code=422, detail="Strategy has no code to test")
    # Never let strategy params override the smoke test's cost bounds.
    safe_params = {k: v for k, v in (body.strategy_params or {}).items()
                   if k not in ('num_years', 'num_simulations', 'num_random_paths',
                                'num_sims')}
    result = run_sandbox_test(
        strategy['code'], strategy['class_name'],
        {'num_years': TEST_YEARS, 'num_simulations': TEST_PATHS,
         'num_random_paths': TEST_PATHS, 'strategy_params': safe_params})
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
    if strategy['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail="Only the owner can run an evaluation")
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


def _evaluation_in_progress(strategy_id: int) -> bool:
    """A pending/processing evaluation job for this strategy (old Info tab).
    Targeted SQL, not a job listing: this runs on every Evaluation-tab poll,
    and a newest-N listing both hauls full-source payloads and misses the
    user's own job once the queue is deeper than the window."""
    from db.database import db

    conn = db.get_connection()
    try:
        cursor = db._get_cursor(conn)
        cursor.execute("""
            SELECT 1 FROM BACKGROUND_JOBS
            WHERE job_type = 'strategy_evaluation'
              AND status IN ('PENDING', 'PROCESSING')
              AND payload->>'custom_strategy_id' = %s
            LIMIT 1
        """, (str(strategy_id),))
        return cursor.fetchone() is not None
    except Exception:
        logging.exception("evaluation job poll failed")
        return False
    finally:
        db.release_connection(conn)


@router.get("/strategies/{strategy_id}/evaluation")
def strategy_evaluation(strategy_id: int,
                        user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    evaluation = db.get_strategy_evaluation(
        strategy.get('git_commit_sha'),
        lookup_fallback_sha=strategy.get('clone_source_commit_sha'))
    if not evaluation and _builtin_key(strategy):
        evaluation = _builtin_leaderboard_evaluations().get(strategy['strategy_name'])
    in_progress = _evaluation_in_progress(strategy_id)
    if not evaluation:
        return {'evaluation': None, 'in_progress': in_progress}
    out = _stringify_dates(dict(evaluation))
    if out.get('scenario_results_json'):
        out['scenario_results'] = db.deserialize_json_column(out.pop('scenario_results_json'))

    radar = None
    try:
        from reporting.radar_chart_data import create_radar_chart

        fig = create_radar_chart(
            dict(evaluation), metric_source='METRIC_WEIGHTS',
            strategy_name=strategy['strategy_name'],
            excellence_score=evaluation.get('excellence_score'), height=340)
        if fig is not None:
            radar = json.loads(fig.to_json())
    except Exception:
        logging.exception("evaluation radar failed")

    metric_grid = []
    try:
        from app.routers.public import _metric_grid

        metric_grid = _metric_grid(dict(evaluation),
                                   evaluation.get('strategy_category'), {})
    except Exception:
        logging.exception("evaluation metric grid failed")

    return {'evaluation': out, 'in_progress': in_progress,
            'radar': radar, 'metric_grid': metric_grid}


# --- Evolution history, publish, clone, flowchart (old Info/History tabs) --

@router.get("/strategies/{strategy_id}/history")
def strategy_history(strategy_id: int,
                     user: Optional[dict] = Depends(get_current_user)) -> dict:
    """The strategy's human-input timeline.

    `runs` (owner only — clarify answers and refine feedback are raw user
    input) carries every generation run that produced or evolved this
    strategy, each with the verbatim request and the inputs typed during it.
    `genesis` is the ORIGINAL user request from the create run — not the
    AI-written description. `history` keeps the legacy evolution entries as
    a fallback for strategies with no recorded runs.
    """
    from db import strategy_generation as sg
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)

    runs = []
    genesis = None
    if strategy['user_id'] == user['id']:
        for run in sg.list_runs_for_strategy(strategy_id):
            inputs = []
            try:
                for event in sg.list_events(run['id']):
                    if event['type'] != 'input_received':
                        continue
                    payload = event['payload'] or {}
                    entry = {k: payload[k]
                             for k in ('kind', 'action', 'feedback', 'answers')
                             if payload.get(k)}
                    if entry:
                        entry['timestamp'] = str(event['created_at'])
                        inputs.append(entry)
            except Exception:
                logging.exception("history: event read failed for run %s", run['id'])
            runs.append({
                'run_id': run['id'],
                'kind': 'evolve' if run['seed_strategy_id'] else 'create',
                'status': run['status'],
                'request': run['user_request'],
                'created_at': str(run['created_at']),
                'inputs': inputs,
            })
        genesis = next((r['request'] for r in runs if r['kind'] == 'create'), None)

    # previous_code snapshots stay server-side (revert material, not UI) —
    # the DB strips them unless include_code=True is asked for.
    history = db.get_strategy_evolution_history(strategy_id) or []
    return {
        'history': [_stringify_dates(dict(h)) for h in history],
        'runs': runs,
        'genesis': genesis or strategy.get('description'),
        'created_at': str(strategy.get('created_at') or '') or None,
    }


@router.get("/strategies/{strategy_id}/versions")
def strategy_versions(strategy_id: int,
                      user: Optional[dict] = Depends(get_current_user)) -> dict:
    """The strategy's version ancestry (V39 DAG) — owner only: the chain
    carries evolve requests, and revert is owner-only anyway."""
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if strategy['user_id'] != user['id']:
        raise HTTPException(status_code=404, detail="Strategy not found")
    versions = db.get_strategy_versions(strategy_id, user['id']) or []
    return {'versions': [
        {'id': v['id'],
         # content hashes carry a legacy 'draft_' prefix — not display material
         'short_hash': (v.get('content_hash') or '').removeprefix('draft_')[:8],
         'source': v.get('source'),
         'request': v.get('request'),  # already redacted for foreign nodes
         'created_at': str(v.get('created_at') or '') or None,
         'is_head': bool(v.get('is_head')),
         # a clone-boundary node: committed under a strategy the user does
         # not own (the state that was cloned)
         'inherited': not v.get('owned'),
         'from_strategy_id': (v.get('strategy_id')
                              if v.get('strategy_id') not in (None, strategy_id)
                              else None)}
        for v in versions]}


class RevertRequest(BaseModel):
    version_id: int


@router.post("/strategies/{strategy_id}/revert")
def revert_strategy(strategy_id: int, body: RevertRequest,
                    user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Restore an earlier version (append-only: the restore becomes the new
    head). Ownership and ancestry are enforced in the DB layer too."""
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if strategy['user_id'] != user['id']:
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = db.revert_strategy_to_version(strategy_id, user['id'], body.version_id)
    if not result.get('success'):
        raise HTTPException(status_code=422,
                            detail=result.get('error') or 'Revert failed')
    return {'reverted': True, 'version_id': result.get('version_id')}


@router.post("/strategies/{strategy_id}/publish")
def publish_strategy(strategy_id: int,
                     user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if strategy['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail="Only the owner can publish")
    # Old rule: no unevaluated strategies on the leaderboard.
    evaluation = db.get_strategy_evaluation(
        strategy.get('git_commit_sha'),
        lookup_fallback_sha=strategy.get('clone_source_commit_sha'))
    if not evaluation or evaluation.get('excellence_score') is None:
        raise HTTPException(
            status_code=409,
            detail="Strategy must be evaluated before publishing to the leaderboard")
    if not db.set_strategy_published_status(strategy_id, user['id'], True):
        raise HTTPException(status_code=500, detail="Failed to publish strategy")
    return {'published': True}


@router.post("/strategies/{strategy_id}/unpublish")
def unpublish_strategy(strategy_id: int,
                       user: Optional[dict] = Depends(get_current_user)) -> dict:
    from db.database import db

    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    if strategy['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail="Only the owner can unpublish")
    if not db.set_strategy_published_status(strategy_id, user['id'], False):
        raise HTTPException(status_code=500, detail="Failed to unpublish strategy")
    return {'published': False}


@router.post("/strategies/{strategy_id}/clone")
def clone_strategy_endpoint(strategy_id: int,
                            user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Clone a visible strategy (built-in or public) into the viewer's library."""
    from db.database import db
    from services.strategy_clone import clone_strategy, has_user_cloned_strategy

    user = _require_user(user)
    _owned_strategy(strategy_id, user)
    if has_user_cloned_strategy(user['id'], strategy_id, db):
        return {'cloned': False, 'in_library': True}
    result = clone_strategy(strategy_id=strategy_id, user_id=user['id'], db=db)
    if not result.get('success'):
        raise HTTPException(status_code=409,
                            detail=result.get('error') or "Clone failed")
    return {'cloned': True, 'in_library': True,
            'strategy_id': result.get('strategy_id')}


@router.get("/strategies/{strategy_id}/flowchart")
def strategy_flowchart(strategy_id: int, theme: str = 'light',
                       user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Decision flowchart (mermaid) — built-in strategies only."""
    user = _require_user(user)
    strategy = _owned_strategy(strategy_id, user)
    key = _builtin_key(strategy)
    if not key:
        return {'mermaid': None}
    from reporting.strategy_flowcharts import get_strategy_flowchart

    theme = theme if theme in ('light', 'dark') else 'light'
    return {'mermaid': get_strategy_flowchart(key, theme=theme)}


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
        if seed['user_id'] != user['id']:
            # Evolve saves back INTO the seed row — never someone else's.
            raise HTTPException(status_code=403,
                                detail="You can only evolve your own strategies — clone it from the leaderboard first")
        if not seed.get('code'):
            raise HTTPException(status_code=422, detail="Seed strategy has no code")
        seed_strategy = {'id': seed['id'], 'strategy_name': seed['strategy_name'],
                         'class_name': seed.get('class_name'),
                         'description': seed.get('description'),
                         'ai_description': seed.get('ai_description'),
                         'code': seed['code']}

    run_id = runner.start_run(user['id'], body.request,
                              strategy_name=body.strategy_name,
                              seed_strategy=seed_strategy)
    # Charge only after the run exists — a start_run failure must not bill.
    limiter.increment_ai_credits(user['id'])
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
        'run': _stringify_dates({k: v for k, v in run.items() if k != 'thread_id'}),
        'events': [_stringify_dates(e) for e in events],
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
        empty_polls = 0
        delay = 0.8
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
                empty_polls = 0
                delay = 0.8
            else:
                empty_polls += 1
                # A reconnect can arrive with `after` already past the terminal
                # event — end the stream instead of polling a finished run
                # forever. Interrupted runs (needs_input) wait on the user for
                # a long time, so back the poll cadence off while idle.
                if empty_polls % 5 == 0:
                    run = await asyncio.to_thread(sg.get_run, run_id)
                    if not run or run['status'] in ('completed', 'failed', 'discarded'):
                        # Status flips just before the terminal event lands —
                        # drain once so a live client still gets it.
                        final = await asyncio.to_thread(sg.list_events, run_id, cursor)
                        for event in final:
                            cursor = event['seq']
                            data = json.dumps({'seq': event['seq'], 'type': event['type'],
                                               'payload': event['payload']})
                            yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"
                        return
                    if run['status'] == 'needs_input':
                        delay = min(5.0, delay * 1.5)
                idle += delay
                if idle >= 15.0:
                    yield ": keepalive\n\n"
                    idle = 0.0
            await asyncio.sleep(delay)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
