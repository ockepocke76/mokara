"""
Everything the Q&A model gets to see about a subject, in one shape.

Two subjects feed the same QAContext: a designer build (its generation run's
persisted build-log artifacts) and a completed simulation (its saved
parameters, stats, and sampled paths). Prompts and the UI never branch on
which one it was.
"""
import inspect
import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from core.simulation import STATE_KEY_PREFIX

# Yearly snapshot columns worth a trace row, keyed by the engine's Title
# Case names (Portfolio.record_yearly_snapshot).
_TRACE_COLUMNS = {'net_worth': 'Net Worth', 'asset_value': 'Asset Value',
                  'debt': 'Debt', 'cash': 'Cash',
                  'withdrawn': 'Consumption Delivered', 'sold': 'Amount Sold',
                  'bought': 'Amount Bought', 'borrowed': 'Debt Change',
                  'contributed': 'Amount Contributed'}

# The designer's condensed-path series names (graph._PATH_SERIES) -> trace names.
_DESIGNER_SERIES = {'net_worth': 'net_worth', 'asset_value': 'asset_value',
                    'debt': 'debt', 'cash': 'cash', 'withdrawn': 'withdrawn',
                    'sold': 'sold', 'borrowed': 'borrowed', 'contributed': 'contributed'}

_BUILTIN_STRATEGIES = {'trinity': ('core.strategy', 'TrinityStrategy'),
                       'buy_borrow_die': ('core.strategy', 'BuyBorrowDieStrategy'),
                       'get_rich_stay_rich': ('core.strategy_get_rich_stay_rich',
                                              'GetRichStayRichStrategy')}

_RUN_PARAM_KEYS = ('num_years', 'num_simulations', 'initial_investment',
                   'initial_assets', 'initial_debt', 'currency', 'asset_model',
                   'asset_name', 'annual_return', 'annual_volatility',
                   'inflation_rate', 'loan_interest_rate', 'asset_management_fee',
                   'tax_method', 'capital_gains_tax_rate', 'isk_tax_rate',
                   'cash_interest_rate', 'annual_salary', 'salary_growth_rate',
                   'contribution_rate', 'annual_contribution')

_NARRATIVE_STAT_KEYS = ('analysis', 'main_outcome', 'bottom_line')


@dataclass
class QAContext:
    subject_type: str
    strategy_name: str
    strategy_description: str
    strategy_source: str | None
    parameters: dict
    run_conditions: dict
    summary_stats: dict
    traces: list[dict]
    state_metrics: list[dict] = field(default_factory=list)
    spec: dict | None = None
    blueprint_rules: list[str] = field(default_factory=list)
    baseline: dict | None = None
    prior_analysis: dict | None = None
    evolution: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_state_metrics(self) -> bool:
        return any(row.get(k) is not None
                   for trace in self.traces for row in trace['years']
                   for k in row if k.startswith(STATE_KEY_PREFIX))


# --- Designer build -------------------------------------------------------

def latest_artifacts(events: list[dict]) -> dict[str, dict]:
    """The most recent stage_completed artifact per stage — a refine round
    re-emits code/test_flight/behavior, and the latest is the strategy the
    user is looking at."""
    artifacts: dict[str, dict] = {}
    for event in events:
        if event.get('type') != 'stage_completed':
            continue
        payload = event.get('payload') or {}
        stage = payload.get('stage')
        if stage and isinstance(payload.get('artifact'), dict):
            artifacts[stage] = payload['artifact']
    return artifacts


def from_generation_run(run: dict, events: list[dict]) -> QAContext | None:
    """None until the build has a test flight to talk about."""
    artifacts = latest_artifacts(events)
    test = artifacts.get('test_flight')
    code = artifacts.get('code') or {}
    if not test or not code.get('code'):
        return None
    understanding = artifacts.get('understanding') or {}
    plan = (artifacts.get('blueprint') or {}).get('plan') or {}
    behavior = (artifacts.get('behavior') or {}).get('analyze')
    spec = understanding.get('spec') or run.get('spec')

    traces = _designer_traces(test.get('paths') or [])
    parameters = {name: (v.get('default') if isinstance(v, dict) else v)
                  for name, v in _plan_parameters(plan).items()}
    evolution = None
    if run.get('seed_strategy_id'):
        evolution = {'seed_strategy_id': run['seed_strategy_id'],
                     'requested_changes': (spec or {}).get('changes', []),
                     'diff': code.get('diff')}
    return QAContext(
        subject_type='generation_run',
        strategy_name=understanding.get('strategy_name') or run.get('strategy_name') or 'Unnamed strategy',
        strategy_description=(behavior or {}).get('explanation') or code.get('description', ''),
        strategy_source=code['code'],
        parameters=parameters,
        run_conditions={'kind': 'designer smoke test',
                        'num_paths': test.get('num_paths'),
                        'num_years': test.get('num_years'),
                        'initial_investment': plan.get('test_initial_investment'),
                        'note': 'Each path starts with the stated capital already invested; '
                                'markets are simulated, plus one historical backtest path.'},
        summary_stats=test.get('summary_stats') or {},
        traces=traces,
        state_metrics=test.get('state_metrics') or plan.get('state_metrics') or [],
        spec=spec,
        blueprint_rules=list(plan.get('rules') or []),
        baseline=test.get('baseline'),
        prior_analysis=behavior,
        evolution=evolution,
    )


def _plan_parameters(plan: dict) -> dict:
    out = {}
    for p in plan.get('parameters') or []:
        if isinstance(p, dict) and p.get('name'):
            out[p['name']] = {k: p.get(k) for k in ('default', 'min', 'max', 'description')}
    return out


def _designer_traces(paths: list[dict]) -> list[dict]:
    """Worst and median random paths (by final net worth) as per-year rows,
    plus the backtest path when present."""
    random_paths = [p for p in paths if not p.get('is_backtest') and p.get('years')]
    picked: list[tuple[str, dict]] = []
    if random_paths:
        ranked = sorted(random_paths, key=lambda p: _last_finite(p.get('net_worth') or []))
        picked.append(('worst path', ranked[0]))
        if len(ranked) > 2:
            picked.append(('median path', ranked[len(ranked) // 2]))
    picked.extend(('historical backtest', p) for p in paths if p.get('is_backtest'))
    traces = []
    for label, p in picked:
        years = []
        state = p.get('state') or {}
        for i, year in enumerate(p['years']):
            row: dict[str, Any] = {'year': year}
            for name, series_key in _DESIGNER_SERIES.items():
                series = p.get(series_key) or []
                row[name] = series[i] if i < len(series) else None
            for key, series in state.items():
                row[key] = series[i] if i < len(series) else None
            years.append(row)
        traces.append({'label': f"{label} ({p.get('label', '')})".strip(), 'years': years})
    return traces


def _last_finite(series: list) -> float:
    for v in reversed(series):
        if isinstance(v, (int, float)) and math.isfinite(v):
            return float(v)
    return math.inf


# --- Completed simulation ---------------------------------------------------

def from_simulation(simulation_hash: str, params: dict, stats: dict,
                    sampled_paths) -> QAContext:
    strategy_key = params.get('strategy')
    if strategy_key == 'custom':
        name = params.get('custom_strategy_name') or 'Custom strategy'
        description = (params.get('custom_strategy_ai_description')
                       or params.get('custom_strategy_description') or '')
        source = params.get('custom_strategy_code')
        strategy_params = dict(params.get('custom_strategy_params') or {})
    else:
        name, description, source, strategy_params = _builtin_strategy(strategy_key, params)

    run_params = {k: params.get(k) for k in _RUN_PARAM_KEYS if params.get(k) is not None}
    parameters = {**strategy_params}
    scalar_stats = {k: v for k, v in (stats or {}).items()
                    if k not in _NARRATIVE_STAT_KEYS and _is_scalar(v)}
    narrative = {k: stats[k] for k in _NARRATIVE_STAT_KEYS
                 if isinstance((stats or {}).get(k), str) and stats[k].strip()}
    return QAContext(
        subject_type='simulation',
        strategy_name=name,
        strategy_description=description,
        strategy_source=source,
        parameters=parameters,
        run_conditions={'kind': 'full simulation', 'simulation_hash': simulation_hash,
                        **run_params},
        summary_stats=scalar_stats,
        traces=_sampled_traces(sampled_paths),
        prior_analysis=narrative or None,
    )


def _builtin_strategy(key: str | None, params: dict) -> tuple[str, str, str | None, dict]:
    """Name, description, source, and the values of the strategy's own
    declared parameters as they were set for this run."""
    from reporting.content import STRATEGY_DESCRIPTIONS

    description = STRATEGY_DESCRIPTIONS.get(key or '', '')
    module_name, class_name = _BUILTIN_STRATEGIES.get(key or '', (None, None))
    source = None
    strategy_params: dict = {}
    if module_name:
        import importlib
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
            source = inspect.getsource(cls)
            description = description or (inspect.getdoc(cls) or '')
            declared = cls(params).parameters or {}
            strategy_params = {n: params[n] for n in declared if n in params}
        except Exception:
            logging.exception("qa: could not introspect built-in strategy %s", key)
    name = (key or 'unknown').replace('_', ' ').title()
    return name, description, source, strategy_params


def _sampled_traces(sampled_paths) -> list[dict]:
    """Worst and median sampled simulation columns as per-year rows. The
    frame is (Year, Metric) x sim-name, straight from results_dataframe, so
    any state_* metrics the strategy recorded are rows here."""
    import pandas as pd

    if sampled_paths is None or not isinstance(sampled_paths, pd.DataFrame) or sampled_paths.empty:
        return []
    try:
        net_worth = sampled_paths.xs('Net Worth', level='Metric')
    except KeyError:
        return []
    finals = net_worth.iloc[-1].dropna().sort_values()
    if finals.empty:
        return []
    picks = [('worst sampled path', finals.index[0])]
    if len(finals) > 2:
        picks.append(('median sampled path', finals.index[len(finals) // 2]))
    traces = []
    for label, column in picks:
        wide = sampled_paths[column].unstack(level='Metric').sort_index()
        state_cols = [c for c in wide.columns if str(c).startswith(STATE_KEY_PREFIX)]
        years = []
        for year, row in wide.iterrows():
            out: dict[str, Any] = {'year': int(year)}
            for name, column_name in _TRACE_COLUMNS.items():
                out[name] = _round(row.get(column_name))
            for c in state_cols:
                out[str(c)] = _finite(row.get(c))
            years.append(out)
        traces.append({'label': f"{label} ({column})", 'years': years})
    return traces


def _is_scalar(v) -> bool:
    if isinstance(v, bool) or v is None:
        return True
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    return isinstance(v, str) and len(v) < 200


def _finite(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round(v):
    f = _finite(v)
    return round(f) if f is not None else None
