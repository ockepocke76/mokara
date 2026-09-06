"""
Derive the BaseStrategy API-surface text from the class itself.

The old app hand-maintained this text inside prompt templates (twice), and it
drifted from core/strategy.py. Prompt builders render it from inspect instead,
so the contract the LLM sees is always the one the engine enforces.
"""
import inspect

from core.strategy import BaseStrategy

# The normalized (lowercase snake_case) keys each portfolio_history record
# carries when it reaches a strategy. SandboxedStrategyWrapper and the engine
# normalize Portfolio.record_yearly_snapshot's Title Case keys to these.
HISTORY_KEYS = [
    'year', 'asset_value', 'debt', 'cash', 'net_worth',
    'consumption_delivered', 'amount_sold', 'amount_bought',
    'amount_contributed', 'debt_change', 'interest_paid', 'tax_paid',
    'fees_paid', 'accumulated_interest', 'accumulated_tax',
    'accumulated_fees', 'cash_interest',
]

# Presentation order: the members a generated strategy must or may implement.
_MEMBER_ORDER = [
    'parameters',
    '__init__',
    'initialize_portfolio',
    'get_annual_drawdown',
    'execute_strategy_for_year',
    'shortfall_funding_policy',
    'evaluation_category',
    'default_tax_method',
    'reset',
]


def _member_doc(name: str) -> str:
    attr = inspect.getattr_static(BaseStrategy, name)
    if isinstance(attr, property):
        fn = attr.fget
        kind = 'property'
    else:
        fn = attr
        kind = 'method'
    is_abstract = getattr(fn, '__isabstractmethod__', False) or name in getattr(
        BaseStrategy, '__abstractmethods__', frozenset())
    required = 'REQUIRED' if is_abstract else 'optional (has default)'
    try:
        sig = str(inspect.signature(fn))
    except (TypeError, ValueError):
        sig = '(...)'
    doc = inspect.getdoc(fn) or ''
    return f"### {kind} {name}{sig} — {required}\n{doc}"


def strategy_api_docs() -> str:
    """The full BaseStrategy contract as prompt-ready text."""
    parts = [
        "## The BaseStrategy contract (from the engine source — authoritative)",
        inspect.getdoc(BaseStrategy) or '',
    ]
    parts.extend(_member_doc(name) for name in _MEMBER_ORDER)
    parts.append(
        "### portfolio_history record keys\n"
        "Every record in portfolio_history is a dict with exactly these "
        "lowercase snake_case keys:\n" + ", ".join(HISTORY_KEYS)
    )
    return "\n\n".join(parts)
