"""
The W5 strategy-generation graph (LangGraph).

One graph serves create AND evolve (evolve = seed_* fields set). Shape:

  extract_spec -> (clarify?) -> retrieve -> plan -> generate -> validate
      -> static_review -> test_sim -> analyze -> review -> save
  with any failed rung routing through rework (bounded) back to generate.

Evolve runs the same shape through evolve-specific prompts: the spec is a
CHANGE spec (changes + change_scope), plan produces an edit list against the
seed code, generate edits the seed class in place (same class name), validate
adds a deterministic minimal-diff check, and the test flight's paired baseline
is the seed itself. A change the spec judges 'structural' falls back to the
create prompts (still saved into the seed row).

Hard rules from the design doc:
- The rework loop triggers on SPEC MISMATCH or broken code only. Faithful-but-
  underperforming results go to the user at review — never silent stat-chasing.
- Nodes call the LLM only through config['configurable']['llm_call'].
- All state must stay JSON-serializable (the Postgres checkpointer snapshots it).
"""
import json
import logging
import math
import threading
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import prompts, retrieval
from app.agents.llm import extract_description_and_code, parse_json_response
from core.simulation import STATE_KEY_PREFIX
from db import strategy_generation as sg

MAX_ATTEMPTS = 3        # automatic rework rounds (validate/static/analyze failures)
MAX_REVISIONS = 3       # user-requested "refine" rounds at review
MAX_LLM_CALLS = 30      # per-run backstop; must cover clarify (1) + full
                        # rework budget (3x3) + full revision budget (3x3,
                        # where an evolve refine re-runs spec+plan too: 3x5)
                        # on top of the base 5-call pass, with margin.

class GenerationNeedsDecision(Exception):
    """A resume request that cannot be honored; the run stays needs_input."""


TEST_YEARS = 30
TEST_PATHS = 10


class GenerationBudgetExceeded(RuntimeError):
    pass


class GenState(TypedDict, total=False):
    run_id: str
    user_id: int
    user_request: str
    strategy_name: str
    class_name: str
    seed_id: Optional[int]      # non-null = evolve; save updates this strategy
    seed_name: Optional[str]
    seed_description: Optional[str]
    seed_code: Optional[str]
    seed_class_name: Optional[str]
    seed: int  # RNG seed for the paired test sims

    spec: dict
    clarify_questions: list
    examples_meta: list         # name/source/score only — code is rebuilt per
                                # prompt so the checkpointer doesn't snapshot it
    plan: dict
    description: str
    code: str
    parameters: dict

    static_review: dict
    test_result: dict
    baseline_result: dict
    analyze: dict

    attempts: int
    revisions: int
    respec: bool            # a review refine on an evolve run re-enters at extract_spec
    llm_calls: int
    rework_reason: str      # human-readable, for attempt_started events
    rework_feedback: str    # detailed, goes into the generate prompt
    rework_stage: str       # which rung failed

    outcome: str            # saved | discarded | failed
    final_strategy_id: Optional[int]
    failure_summary: Optional[str]


def _emit(state: GenState, event_type: str, **payload) -> None:
    sg.append_event(state['run_id'], event_type, payload)


def _llm(state: GenState, config: dict, prompt: str, tier: str,
         json_mode: bool = True) -> tuple[Any, int]:
    """One LLM call; returns (parsed-or-raw response, calls-so-far).
    A malformed JSON response gets ONE retry (counted against the budget) —
    it is a transient generation glitch, not a reason to kill the run."""
    calls = state.get('llm_calls', 0)
    llm_call = config['configurable']['llm_call']
    last_error = None
    for _ in range(2):
        calls += 1
        if calls > MAX_LLM_CALLS:
            raise GenerationBudgetExceeded(
                f"LLM call budget ({MAX_LLM_CALLS}) exhausted for this run")
        text = llm_call(prompt, tier=tier, json_mode=json_mode)
        if not json_mode:
            return text, calls
        try:
            return parse_json_response(text), calls
        except ValueError as e:
            last_error = e
            logging.warning("Malformed JSON from LLM (attempt with retry): %s", e)
    raise last_error


def _sanitize(value):
    from db.utils import _sanitize_for_json
    return _sanitize_for_json(value)


# --- Nodes -----------------------------------------------------------------

def _normalize_change_scope(spec: dict) -> None:
    """Pin the free-text scope label to the three values the router compares
    against — a mis-cased or reworded label must never reroute a run."""
    raw = str(spec.get('change_scope') or '').lower()
    if 'structural' in raw:
        spec['change_scope'] = 'structural'
    elif 'parameter' in raw:
        spec['change_scope'] = 'parameter_only'
    else:
        spec['change_scope'] = 'behavioral'


def _minimal_evolution(state: GenState) -> bool:
    """Evolve runs edit the seed code in place — except when the spec judged
    the request structural (a redesign), which falls back to the full create
    pipeline (still saved into the seed row). A spec with no change list
    (e.g. a run checkpointed before the change-spec existed) also falls back:
    the edit prompts would otherwise run with nothing to apply."""
    spec = state.get('spec') or {}
    return bool(state.get('seed_code')) and bool(spec.get('changes')) and \
        spec.get('change_scope') != 'structural'


def extract_spec(state: GenState, config) -> dict:
    _emit(state, 'stage_started', stage='understanding')
    if state.get('seed_code'):
        prompt = prompts.evolve_spec_prompt(
            state['user_request'], state.get('seed_name'),
            state.get('seed_description'), state['seed_code'])
    else:
        prompt = prompts.spec_prompt(state['user_request'])
    spec, calls = _llm(state, config, prompt, tier='fast')
    if state.get('seed_code'):
        _normalize_change_scope(spec)
    name = state.get('strategy_name') or spec.get('suggested_name') or 'Custom Strategy'
    update = {'spec': spec, 'llm_calls': calls, 'strategy_name': name,
              'respec': False,  # a refine re-entry is consumed here
              'clarify_questions': spec.get('questions') or []}
    sg.update_run(state['run_id'], spec=spec, strategy_name=name, llm_calls=calls)
    if not spec.get('needs_clarification'):
        _emit(state, 'stage_completed', stage='understanding',
              artifact={'spec': spec, 'strategy_name': name})
    return update


def clarify(state: GenState, config) -> dict:
    # interrupt() first: this node re-runs from the top on resume, and nothing
    # may be emitted before the pause (the runner emits needs_input instead).
    answers = interrupt({'kind': 'clarify',
                         'questions': state.get('clarify_questions', []),
                         'assumptions': state.get('spec', {}).get('assumptions', [])})
    update: dict = {}
    if isinstance(answers, dict) and answers.get('answers'):
        spec, calls = _llm(state, config, prompts.revise_spec_prompt(
            state['spec'], state.get('clarify_questions', []), answers['answers']),
            tier='fast')
        spec['needs_clarification'] = False
        if state.get('seed_code'):
            _normalize_change_scope(spec)
        update = {'spec': spec, 'llm_calls': calls}
        sg.update_run(state['run_id'], spec=spec, llm_calls=calls)
    else:
        # "Proceed with my assumptions" — first-class, not an error path.
        spec = dict(state['spec'])
        spec['needs_clarification'] = False
        update = {'spec': spec}
    _emit(state, 'stage_completed', stage='understanding',
          artifact={'spec': update['spec'], 'strategy_name': state['strategy_name']})
    return update


def _fetch_examples(state: GenState) -> list[dict]:
    category = state['spec'].get('category', 'HYBRID')
    return (retrieval.builtin_examples(category)
            + retrieval.public_examples(state['user_id']))


def retrieve(state: GenState, config) -> dict:
    _emit(state, 'stage_started', stage='examples')
    if _minimal_evolution(state):
        # An edit's only reference is the seed itself — other strategies' code
        # would pull the generator toward their style and away from a minimal
        # diff.
        meta = [{'name': state.get('seed_name') or 'Current version',
                 'source': 'seed', 'score': None}]
    else:
        meta = [{'name': e['name'], 'source': e['source'], 'score': e.get('score')}
                for e in _fetch_examples(state)]
    _emit(state, 'stage_completed', stage='examples', artifact={'examples': meta})
    return {'examples_meta': meta}


def plan(state: GenState, config) -> dict:
    _emit(state, 'stage_started', stage='blueprint')
    if _minimal_evolution(state):
        prompt = prompts.evolve_plan_prompt(state['spec'], state['seed_code'])
    else:
        examples_block = prompts.format_examples_block(_fetch_examples(state))
        prompt = prompts.plan_prompt(state['spec'], examples_block)
    plan_obj, calls = _llm(state, config, prompt, tier='strong')
    sg.update_run(state['run_id'], llm_calls=calls)
    _emit(state, 'stage_completed', stage='blueprint', artifact={'plan': plan_obj})
    return {'plan': plan_obj, 'llm_calls': calls}


def _evolution_diff(seed_code: str, code: str) -> str:
    import difflib

    return '\n'.join(difflib.unified_diff(
        seed_code.splitlines(), code.splitlines(),
        fromfile='before', tofile='after', lineterm=''))


def generate(state: GenState, config) -> dict:
    from core.sandbox import _slugify_to_classname

    attempt = state.get('attempts', 0) + state.get('revisions', 0)
    if attempt == 0:
        _emit(state, 'stage_started', stage='code')
    evolving = _minimal_evolution(state)
    # An edit keeps the seed's class name — re-slugifying would alone force a
    # "new" class out of an unchanged strategy.
    class_name = (state.get('seed_class_name') or '') if evolving else ''
    if not class_name or not class_name.isidentifier():
        class_name = _slugify_to_classname(state['strategy_name']) or 'CustomStrategy'
        if not class_name.isidentifier():
            class_name = 'S' + class_name  # slugs can start with a digit ("4% Rule" -> "4Rule")
    if evolving:
        prompt = prompts.evolve_generate_prompt(
            state['spec'], state['plan'], state['seed_code'], class_name,
            feedback=state.get('rework_feedback'), prior_code=state.get('code'))
    else:
        examples_block = prompts.format_examples_block(_fetch_examples(state))
        prompt = prompts.generate_prompt(
            state['spec'], state['plan'], examples_block, class_name,
            feedback=state.get('rework_feedback'), prior_code=state.get('code'))
    text, calls = _llm(state, config, prompt, tier='strong', json_mode=False)
    description, code = extract_description_and_code(text)
    sg.update_run(state['run_id'], llm_calls=calls)
    artifact = {'code': code, 'description': description, 'class_name': class_name,
                'is_evolution': bool(state.get('seed_code'))}
    # A structural rebuild's "diff" would just be both files interleaved —
    # only a minimal edit gets the before/after view.
    if evolving:
        artifact['diff'] = _evolution_diff(state['seed_code'], code)
    _emit(state, 'stage_completed', stage='code', artifact=artifact)
    return {'code': code, 'description': description, 'class_name': class_name,
            'llm_calls': calls, 'rework_feedback': None,
            'static_review': {}, 'test_result': {},
            'baseline_result': {}, 'analyze': {}}


def _strategy_method_dumps(code: str) -> Optional[dict]:
    """{method name: normalized AST dump} for the strategy class in `code` —
    the BaseStrategy subclass, else the last class defined. AST dumps are
    formatting-immune, so a requote or re-indent never reads as a change."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    cls = next((c for c in classes
                if any(getattr(b, 'id', None) == 'BaseStrategy' for b in c.bases)),
               classes[-1] if classes else None)
    if cls is None:
        return None
    return {n.name: ast.dump(n) for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _evolution_fidelity(state: GenState, parameters: dict) -> Optional[str]:
    """Deterministic minimal-edit backstop for evolve runs: the prompts insist
    on editing the seed, this catches the model straying anyway. Compares the
    two versions method-by-method at the AST level (a size heuristic cannot
    tell an edit from a rewrite on this corpus — BaseStrategy subclasses share
    most of their text). Returns the problem, or None when the edit is
    faithful."""
    from core.ast_parser import safe_parse_strategy_parameters

    scope = state['spec'].get('change_scope')
    seed_code, code = state['seed_code'], state['code']
    if seed_code.strip() == code.strip():
        return ("the code is identical to the original — the requested change "
                "was never applied")
    seed_methods = _strategy_method_dumps(seed_code)
    new_methods = _strategy_method_dumps(code)
    if seed_methods is None or new_methods is None:
        return None  # unparseable (the sandbox gate already ran); LLM review still guards
    changed = sorted(name for name in set(seed_methods) | set(new_methods)
                     if seed_methods.get(name) != new_methods.get(name))
    problems = []
    if scope == 'parameter_only':
        extra = [name for name in changed if name != 'parameters']
        if extra:
            problems.append(
                f"a parameter_only change may only touch the `parameters` "
                f"property, but these methods changed: {extra}")
        try:
            seed_params = safe_parse_strategy_parameters(
                seed_code, state.get('seed_class_name') or state['class_name']) or {}
        except Exception:
            seed_params = {}
        if seed_params and set(parameters) != set(seed_params):
            problems.append(
                f"the parameter set changed (before: {sorted(seed_params)}, "
                f"after: {sorted(parameters)}) — a parameter_only change keeps "
                f"every existing parameter name")
    else:  # behavioral: edits must stay within the methods the plan declared
        targets = {str(e.get('target')).strip()
                   for e in (state.get('plan') or {}).get('edits', [])
                   if isinstance(e, dict) and e.get('target')}
        if targets:
            extra = [name for name in changed
                     if name not in targets and name != 'parameters']
            if extra:
                problems.append(
                    f"methods changed that no planned edit targets: {extra} "
                    f"(planned targets: {sorted(targets)})")
    return "; ".join(problems) or None


def validate(state: GenState, config) -> dict:
    from core.ast_parser import safe_parse_strategy_parameters
    from core.sandbox import execute_strategy_code

    _emit(state, 'stage_started', stage='checks')
    try:
        execute_strategy_code(state['code'], state['class_name'], strict_category=True)
    except Exception as e:
        _emit(state, 'stage_progress', stage='checks', check='sandbox',
              passed=False, message=str(e)[:500])
        return {'rework_stage': 'validate',
                'rework_reason': 'the code failed the sandbox safety checks',
                'rework_feedback': f"Sandbox compilation/dry-run failed:\n{e}"}
    _emit(state, 'stage_progress', stage='checks', check='sandbox', passed=True)
    parameters = {}
    try:
        parameters = safe_parse_strategy_parameters(state['code'], state['class_name']) or {}
    except Exception:
        logging.exception("parameter AST parse failed (non-fatal)")
    if _minimal_evolution(state):
        problem = _evolution_fidelity(state, parameters)
        _emit(state, 'stage_progress', stage='checks', check='minimal_change',
              passed=problem is None, message=(problem or '')[:500] or None)
        if problem:
            return {'parameters': parameters,
                    'rework_stage': 'validate',
                    'rework_reason': 'the edit changed more than the request asked for',
                    'rework_feedback':
                        f"The modified class strayed from the original: {problem}.\n"
                        f"Start again from the ORIGINAL code and apply only the "
                        f"planned edits, preserving everything else verbatim."}
    return {'parameters': parameters}


def static_review(state: GenState, config) -> dict:
    review, calls = _llm(state, config, prompts.static_review_prompt(
        state['code'], state['plan'], state['spec'],
        seed_code=(state.get('seed_code') if _minimal_evolution(state) else None)),
        tier='fast')
    sg.update_run(state['run_id'], llm_calls=calls)
    passed = bool(review.get('implements_blueprint'))
    _emit(state, 'stage_progress', stage='checks', check='blueprint_conformance',
          passed=passed, rule_verdicts=review.get('rule_verdicts', []),
          issues=review.get('issues', []))
    update = {'static_review': review, 'llm_calls': calls}
    if not passed:
        issues = "; ".join(review.get('issues', [])) or "blueprint rules not implemented"
        update.update({'rework_stage': 'static_review',
                       'rework_reason': 'the code does not implement the blueprint',
                       'rework_feedback': f"A code review against the blueprint found:\n{issues}\n"
                                          f"Rule verdicts: {json.dumps(review.get('rule_verdicts', []))}"})
    else:
        _emit(state, 'stage_completed', stage='checks',
              artifact={'rule_verdicts': review.get('rule_verdicts', [])})
    return update


def _round_finite(v):
    # LLM strategies can produce NaN/inf (e.g. 0.0/0.0 on numpy floats);
    # round() raises on those, and a crash here would bypass the rework
    # loop entirely. Map non-finite to None instead.
    try:
        return round(v) if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        # OverflowError: math.isfinite raises on ints too large for a float.
        return None


# Yearly-snapshot columns shipped to the test-flight UI, keyed by the
# engine's Title Case names from Portfolio.record_yearly_snapshot.
_PATH_SERIES = {'net_worth': 'Net Worth', 'asset_value': 'Asset Value',
                'debt': 'Debt', 'cash': 'Cash',
                'contributed': 'Amount Contributed',
                'withdrawn': 'Consumption Delivered',
                # Debt-funded strategies (e.g. Buy Borrow Die) record zero
                # 'Consumption Delivered' — the real cash flow is here.
                # _worst_path_trace below derives from this same mapping.
                'borrowed': 'Debt Change', 'sold': 'Amount Sold'}


def _condense_paths(result: dict) -> list[dict]:
    """Per-path yearly series for the test-flight charts, rounded to whole
    currency units. The backtest path (when present) comes last, flagged so
    the UI can draw it as the highlighted trace."""
    entries = [(p, False) for p in result.get('random_paths', [])]
    if result.get('backtest_path'):
        entries.append((result['backtest_path'], True))
    paths = []
    for p, is_backtest in entries:
        yearly = p.get('yearly_results', [])
        path = {'label': p.get('path_label', ''),
                'years': [y['Year'] for y in yearly]}
        for key, column in _PATH_SERIES.items():
            path[key] = [_round_finite(y.get(column)) for y in yearly]
        state_keys = _state_keys(yearly)
        if state_keys:
            path['state'] = {k: [_finite_or_none(y.get(k)) for y in yearly]
                             for k in state_keys}
        if is_backtest:
            path['is_backtest'] = True
        paths.append(path)
    return paths


def _state_keys(yearly: list[dict]) -> list[str]:
    """The strategy's own `state_*` metrics present in a path's yearly rows
    (year 0 carries none — the engine records them from year 1)."""
    keys: set[str] = set()
    for y in yearly:
        keys.update(k for k in y if k.startswith(STATE_KEY_PREFIX))
    return sorted(keys)


def _finite_or_none(v):
    try:
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _missing_state_metrics(plan: dict, result: dict) -> list[str]:
    required = [m.get('name') for m in (plan or {}).get('state_metrics', [])
                if isinstance(m, dict) and isinstance(m.get('name'), str)]
    if not required:
        return []
    seen: set[str] = set()
    for p in result.get('random_paths', []):
        seen.update(_state_keys(p.get('yearly_results', [])))
    return [name for name in required if name not in seen]


# The engine seeds the process-global numpy RNG; the shared reentrant lock
# (owned by core.sandbox_tester so EVERY caller of run_sandbox_test takes it,
# including the /test endpoint) is held here across the candidate+baseline
# PAIR so nothing interleaves between the two same-seed sims.
from core.sandbox_tester import SIM_RNG_LOCK as _test_sim_lock


def _test_capital(plan: dict, fallback: float) -> float:
    """The blueprint's smoke-test starting capital, clamped to sane bounds;
    anything missing or malformed falls back to the category standard."""
    value = (plan or {}).get('test_initial_investment')
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(value):
        return fallback
    return min(max(value, 0.0), 10_000_000.0)


def test_sim(state: GenState, config) -> dict:
    from core.sandbox_tester import run_sandbox_test

    _emit(state, 'stage_started', stage='test_flight',
          message=f"Running {TEST_PATHS} simulated markets x {TEST_YEARS} years")
    from core.sandbox_tester import capital_params_for_category

    seed = state.get('seed', 12345)
    category = state['spec'].get('category', 'HYBRID')
    # num_simulations/num_years must be explicit: assemble_params merges the
    # config defaults (1000 sims) over anything run_sandbox_test setdefaults.
    # Capital shape is pinned to the SPEC's category for BOTH runs — the
    # baseline builtin may belong to another category, and a paired
    # comparison is only fair when the two see identical conditions. The
    # blueprint can override the starting capital (it knows the scenario's
    # scale — a lifecycle-from-salary spec needs a near-zero start or its
    # retirement trigger legitimately fires on day one and the career phase
    # is never observed); the full evaluation stays standardized.
    capital = capital_params_for_category(category)
    capital['initial_investment'] = _test_capital(
        state['plan'], capital.get('initial_investment', 1_000_000))
    test_params = {'num_years': TEST_YEARS, 'num_simulations': TEST_PATHS,
                   'num_random_paths': TEST_PATHS, **capital,
                   'strategy_params': {p: (v.get('default') if isinstance(v, dict) else v)
                                       for p, v in (state.get('parameters') or {}).items()}}
    if _minimal_evolution(state):
        # An evolve run's fairest comparison is the strategy BEFORE the change
        # on identical markets — the delta shows the edit itself.
        baseline_class = state.get('seed_class_name') or state['class_name']
        baseline_source = state['seed_code']
        baseline_display = f"{state.get('seed_name') or 'This strategy'} (before this change)"
    else:
        _key, baseline_class, baseline_source = retrieval.baseline_for_category(category)
        baseline_display = baseline_class
    baseline = {}
    with _test_sim_lock:
        result = run_sandbox_test(state['code'], state['class_name'],
                                  dict(test_params), seed=seed)
        if result.get('success'):
            # Paired baseline: same seed => identical market paths.
            try:
                baseline_run = run_sandbox_test(baseline_source, baseline_class,
                                                {'num_years': TEST_YEARS,
                                                 'num_simulations': TEST_PATHS,
                                                 'num_random_paths': TEST_PATHS,
                                                 **capital}, seed=seed)
                if baseline_run.get('success'):
                    baseline = {'name': baseline_display,
                                'summary_stats': _sanitize(baseline_run['summary_stats'])}
            except Exception:
                logging.exception("baseline test sim failed (non-fatal)")
    if not result.get('success'):
        _emit(state, 'stage_progress', stage='test_flight', passed=False,
              message=str(result.get('error'))[:500])
        return {'rework_stage': 'test_sim',
                'rework_reason': 'the strategy crashed during the test simulation',
                'rework_feedback': f"The test simulation failed at runtime:\n{result.get('error')}"}
    missing = _missing_state_metrics(state.get('plan'), result)
    if missing:
        _emit(state, 'stage_progress', stage='test_flight', check='state_metrics',
              passed=False, message=f"missing state metrics: {', '.join(missing)}")
        return {'rework_stage': 'test_sim',
                'rework_reason': 'the strategy did not record its required state metrics',
                'rework_feedback': (
                    f"The yearly history never contained these required state "
                    f"metrics: {missing}. Return each of them (numeric/boolean) "
                    f"from execute_strategy_for_year on every code path, exact names.")}

    # The condensed per-path series go only into the emitted artifact (the
    # UI's copy) — keeping them out of graph state avoids re-checkpointing
    # ~20 KB nothing downstream reads on every later superstep.
    test_result = {'summary_stats': _sanitize(result['summary_stats']),
                   'num_paths': TEST_PATHS, 'num_years': TEST_YEARS,
                   'test_capital': capital['initial_investment'],
                   'worst_path_trace': _worst_path_trace(result)}
    paths = _sanitize(_condense_paths(result))
    _emit(state, 'stage_completed', stage='test_flight',
          artifact={'summary_stats': test_result['summary_stats'],
                    'paths': paths,
                    'state_metrics': (state.get('plan') or {}).get('state_metrics', []),
                    'baseline': baseline or None,
                    'num_paths': TEST_PATHS, 'num_years': TEST_YEARS})
    return {'test_result': test_result, 'baseline_result': baseline}


# The worst-path narrative's field names, mapped to their _PATH_SERIES key
# (only 'withdrawal' differs) — keeps the engine column names declared once.
_TRACE_FIELDS = {'net_worth': 'net_worth', 'withdrawal': 'withdrawn',
                 'sold': 'sold', 'borrowed': 'borrowed', 'contributed': 'contributed'}


def _worst_path_trace(result: dict) -> list[dict]:
    worst = None
    worst_final = None
    for p in result.get('random_paths', []):
        yearly = p.get('yearly_results', [])
        if not yearly:
            continue
        final = yearly[-1]['Net Worth']
        if worst_final is None or final < worst_final:
            worst_final, worst = final, yearly
    if not worst:
        return []
    state_keys = _state_keys(worst)
    return _sanitize([
        {'year': y['Year'],
         **{field: _round_finite(y.get(_PATH_SERIES[series_key]))
            for field, series_key in _TRACE_FIELDS.items()},
         **{k: _finite_or_none(y.get(k)) for k in state_keys if k in y}}
        for y in worst])


def analyze(state: GenState, config) -> dict:
    _emit(state, 'stage_started', stage='behavior')
    baseline = state.get('baseline_result') or {}
    evolution = None
    if _minimal_evolution(state):
        evolution = {'seed_name': state.get('seed_name'),
                     'changes': state['spec'].get('changes', []),
                     'baseline_ran': bool(baseline)}
    verdict, calls = _llm(state, config, prompts.analyze_prompt(
        state['spec'], state['plan'],
        state['test_result']['summary_stats'],
        baseline.get('summary_stats'), baseline.get('name'),
        state['test_result']['worst_path_trace'],
        test_capital=state['test_result'].get('test_capital'),
        evolution=evolution), tier='strong')
    sg.update_run(state['run_id'], llm_calls=calls)
    conforms = bool(verdict.get('conforms_to_spec'))
    _emit(state, 'stage_completed', stage='behavior',
          artifact={'analyze': verdict, 'conforms': conforms})
    update = {'analyze': verdict, 'llm_calls': calls}
    if not conforms:
        mismatches = "; ".join(verdict.get('mismatches', [])) or "behavior did not match the spec"
        update.update({'rework_stage': 'analyze',
                       'rework_reason': 'observed behavior did not match the spec',
                       'rework_feedback': f"The test simulation showed behavior contradicting the spec:\n{mismatches}"})
    return update


def rework(state: GenState, config) -> dict:
    attempts = state.get('attempts', 0) + 1
    if attempts >= MAX_ATTEMPTS:
        return {'attempts': attempts,
                'failure_summary': f"Could not produce a working strategy after {MAX_ATTEMPTS} attempts. "
                                   f"Last problem: {state.get('rework_reason')}"}
    _emit(state, 'attempt_started', stage=state.get('rework_stage', 'code'),
          attempt=attempts + 1, max=MAX_ATTEMPTS, reason=state.get('rework_reason', ''))
    return {'attempts': attempts}


def review(state: GenState, config) -> dict:
    revisions = state.get('revisions', 0)
    revisions_left = max(0, MAX_REVISIONS - revisions)
    decision = interrupt({'kind': 'review', 'revisions_left': revisions_left})
    action = (decision or {}).get('action', 'save')
    if action == 'discard':
        return {'outcome': 'discarded'}
    if action == 'refine' and (decision or {}).get('feedback'):
        if revisions_left <= 0:
            # Budget spent: never silently save against the user's request.
            # Surface it and treat the run as still needing a real decision —
            # the client re-resumes with save or discard.
            _emit(state, 'stage_progress', stage='decision',
                  message='Revision budget exhausted — save the strategy as-is or discard it.')
            raise GenerationNeedsDecision(
                'Revision budget exhausted; resume with action save or discard.')
        revisions += 1
        _emit(state, 'attempt_started', stage='code', attempt=revisions,
              max=MAX_REVISIONS, reason='you asked for changes')
        update = {'revisions': revisions,
                  'attempts': 0,  # a fresh user-requested round gets the full automatic-rework budget
                  'rework_stage': 'review',
                  'rework_reason': 'user requested changes'}
        if _minimal_evolution(state):
            # A refine on an evolve is a NEW evolution request: re-derive the
            # change spec and edit plan against the seed with the feedback
            # folded in. Feeding feedback straight into evolve_generate would
            # pit it against the frozen change_scope/edits — the fidelity
            # guard would then reject exactly what the user asked for.
            update.update({
                'respec': True,
                'rework_feedback': None,
                'user_request': (f"{state['user_request']}\n\n"
                                 f"Follow-up change requested at review:\n"
                                 f"{decision['feedback']}"),
            })
        else:
            update['rework_feedback'] = (
                f"The user reviewed the working strategy and asked for changes:\n"
                f"{decision['feedback']}\n"
                f"Keep everything else as is.")
        return update
    return {'outcome': 'save'}


def save(state: GenState, config) -> dict:
    from db.database import db

    _emit(state, 'stage_started', stage='decision')
    ai_description = (state.get('analyze') or {}).get('explanation') or state.get('description', '')
    # Evolve updates the seed strategy in place (the old app's semantic —
    # evolution_request lands in its git history); create inserts a new one.
    strategy_id = db.save_custom_strategy(
        user_id=state['user_id'],
        strategy_name=state['strategy_name'],
        class_name=state['class_name'],
        description=state.get('description', ''),
        ai_description=ai_description,
        code=state['code'],
        parameters_json=state.get('parameters') or {},
        validation_status='validated',
        strategy_id=state.get('seed_id'),
        evolution_request=(state['user_request'] if state.get('seed_id') else None),
        parent_strategy_id=None,
    )
    if not strategy_id:
        raise RuntimeError("save_custom_strategy failed")
    # The save layer suffixes colliding names — report the name the row
    # actually got, not the one we asked for.
    saved_row = db.get_custom_strategy(strategy_id) or {}
    saved_name = saved_row.get('strategy_name') or state['strategy_name']
    sg.update_run(state['run_id'], status='completed',
                  final_strategy_id=strategy_id, strategy_name=saved_name)
    _emit(state, 'run_completed', strategy_id=strategy_id,
          strategy_name=saved_name)
    return {'outcome': 'saved', 'final_strategy_id': strategy_id}


def discard(state: GenState, config) -> dict:
    sg.update_run(state['run_id'], status='discarded')
    _emit(state, 'run_discarded')
    return {'outcome': 'discarded'}


def fail_run(run_id: str, state: dict, summary: str,
             validation_error: str | None) -> Optional[int]:
    """Shared failure path (retry cap AND unexpected crash — see runner):
    keep the last draft, be honest about what happened.

    The draft gets a suffixed name so it is recognizable as the failed
    run's leftovers, distinct from the user's working strategy (the save
    layer is insert-intent and would suffix a colliding name anyway).
    """
    from db.database import db

    draft_id = None
    if state.get('code'):
        draft_name = f"{state.get('strategy_name') or 'Unnamed'} (draft {run_id[:6]})"
        try:
            draft_id = db.save_custom_strategy(
                user_id=state['user_id'],
                strategy_name=draft_name,
                class_name=state.get('class_name', 'CustomStrategy'),
                description=state.get('description', ''),
                ai_description='',
                code=state['code'],
                parameters_json=state.get('parameters') or {},
                validation_status='failed',
                validation_error=validation_error,
            ) or None
        except Exception:
            logging.exception("draft save failed for run %s", run_id)
    try:
        sg.update_run(run_id, status='failed', failure_summary=summary,
                      final_strategy_id=draft_id)
        sg.append_event(run_id, 'run_failed', {
            'summary': summary, 'draft_id': draft_id,
            'last_problem': state.get('rework_reason')})
    except Exception:
        logging.exception("failure bookkeeping failed for run %s", run_id)
    return draft_id


def fail(state: GenState, config) -> dict:
    summary = state.get('failure_summary') or 'Generation failed.'
    draft_id = fail_run(state['run_id'], state, summary,
                        validation_error=state.get('rework_feedback'))
    return {'outcome': 'failed', 'final_strategy_id': draft_id}


# --- Routing ---------------------------------------------------------------

def _route_after_spec(state: GenState) -> str:
    return 'clarify' if state['spec'].get('needs_clarification') else 'retrieve'


def _rework_or(next_node: str):
    """A checking rung failed iff it set rework_feedback (generate clears it
    on every fresh code round) — one router serves every rung."""
    def route(state: GenState) -> str:
        return 'rework' if state.get('rework_feedback') else next_node
    route.__name__ = f"_route_or_{next_node}"
    return route


def _route_after_rework(state: GenState) -> str:
    return 'fail' if state.get('failure_summary') else 'generate'


def _route_after_review(state: GenState) -> str:
    outcome = state.get('outcome')
    if outcome == 'discarded':
        return 'discard'
    if state.get('rework_stage') == 'review':
        if state.get('respec'):
            return 'extract_spec'
        if state.get('rework_feedback'):
            return 'generate'
    return 'save'


def build_graph(checkpointer=None):
    g = StateGraph(GenState)
    for name, fn in [('extract_spec', extract_spec), ('clarify', clarify),
                     ('retrieve', retrieve), ('plan', plan), ('generate', generate),
                     ('validate', validate), ('static_review', static_review),
                     ('test_sim', test_sim), ('analyze', analyze),
                     ('rework', rework), ('review', review), ('save', save),
                     ('discard', discard), ('fail', fail)]:
        g.add_node(name, fn)

    g.add_edge(START, 'extract_spec')
    g.add_conditional_edges('extract_spec', _route_after_spec, ['clarify', 'retrieve'])
    g.add_edge('clarify', 'retrieve')
    g.add_edge('retrieve', 'plan')
    g.add_edge('plan', 'generate')
    g.add_edge('generate', 'validate')
    g.add_conditional_edges('validate', _rework_or('static_review'), ['rework', 'static_review'])
    g.add_conditional_edges('static_review', _rework_or('test_sim'), ['rework', 'test_sim'])
    g.add_conditional_edges('test_sim', _rework_or('analyze'), ['rework', 'analyze'])
    g.add_conditional_edges('analyze', _rework_or('review'), ['rework', 'review'])
    g.add_conditional_edges('rework', _route_after_rework, ['fail', 'generate'])
    g.add_conditional_edges('review', _route_after_review,
                            ['discard', 'generate', 'save', 'extract_spec'])
    g.add_edge('save', END)
    g.add_edge('discard', END)
    g.add_edge('fail', END)
    return g.compile(checkpointer=checkpointer)
