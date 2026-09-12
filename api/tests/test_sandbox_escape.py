"""Regression tests for the sandbox __builtins__ escape.

exec() injects the REAL builtins module into any globals dict that lacks a
'__builtins__' key. The sandbox must pin that key to RestrictedPython's
safe_builtins so generated code can never reach open/eval/__import__.
"""
import pytest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core import sandbox
from core.sandbox import execute_strategy_code


def test_safe_globals_pin_builtins():
    pinned = sandbox._safe_globals.get('__builtins__')
    assert isinstance(pinned, dict)
    for name in ('open', 'eval', 'exec', 'compile', 'input', 'vars'):
        assert name not in pinned
    assert pinned['__import__'] is sandbox._guarded_import


def test_guarded_import_allowlist():
    assert sandbox._guarded_import('math').sqrt(4) == 2.0
    with pytest.raises(ImportError):
        sandbox._guarded_import('os')
    with pytest.raises(ImportError):
        sandbox._guarded_import('subprocess')


VALID_BODY = """
    def __init__(self, params=None):
        super().__init__(params)

    def get_yearly_actions(self, year, portfolio_value, context=None):
        return {'contribution': 0.0, 'withdrawal': 0.0}
"""


@pytest.mark.parametrize(
    "payload",
    [
        "LEAK = open('/etc/hosts')",
        "LEAK = eval('1+1')",
        "LEAK = __import__('os')",
        "LEAK = __builtins__['open']",
    ],
)
def test_dangerous_builtins_unreachable(payload):
    code = (
        "from core.strategy import BaseStrategy\n"
        f"{payload}\n"
        "class CustomStrategy(BaseStrategy):\n"
        f"{VALID_BODY}"
    )
    with pytest.raises(Exception):
        execute_strategy_code(code, "CustomStrategy")


# ---------------------------------------------------------------------------
# Module/attribute policy: pandas/numpy escape hatches must be unreachable.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        # pickle deserialization = arbitrary code execution
        "LEAK = pd.read_pickle('/tmp/x.pkl')",
        # arbitrary file reads
        "LEAK = pd.read_csv('/etc/passwd')",
        # numpy pickle loader
        "LEAK = np.load('/tmp/x.npy', allow_pickle=True)",
        # file writes through instance methods
        "LEAK = pd.DataFrame({'a': [1]}).to_csv('/tmp/leak.csv')",
        "LEAK = np.array([1]).tofile('/tmp/leak.bin')",
        "LEAK = np.array([1]).dump('/tmp/leak.pkl')",
        # expression evaluators
        "LEAK = pd.eval('1+1')",
        "LEAK = pd.DataFrame({'a': [1]}).query('a > 0')",
        # gateway submodules (np.ctypeslib -> ctypes -> anything)
        "LEAK = np.ctypeslib",
        "LEAK = np.testing",
        "LEAK = pd.io",
        # the from-import bytecode extracts attributes with a plain getattr,
        # bypassing RestrictedPython's _getattr_ — the module proxy must hold
        "from pandas import read_pickle",
        "from numpy import load",
    ],
)
def test_pandas_numpy_escapes_blocked(payload):
    code = (
        "from core.strategy import BaseStrategy\n"
        f"{payload}\n"
        "class CustomStrategy(BaseStrategy):\n"
        f"{VALID_BODY}"
    )
    with pytest.raises(Exception):
        execute_strategy_code(code, "CustomStrategy")


def test_module_proxy_policy_direct():
    """The proxies themselves enforce the policy on plain getattr."""
    pd_proxy = sandbox._guarded_import('pandas')
    with pytest.raises(AttributeError):
        pd_proxy.read_pickle
    with pytest.raises(AttributeError):
        pd_proxy.read_csv
    np_proxy = sandbox._guarded_import('numpy')
    with pytest.raises(AttributeError):
        np_proxy.load
    with pytest.raises(AttributeError):
        np_proxy.ctypeslib
    # legitimate numeric surface stays available
    assert np_proxy.array([1, 2]).sum() == 3
    assert np_proxy.random.default_rng(0) is not None
    assert pd_proxy.DataFrame({'a': [1]}).shape == (1, 1)
    assert sandbox._guarded_import('math').sqrt(4) == 2.0


def test_globals_hold_proxies_not_raw_modules():
    import types

    for name in ('np', 'pd', 'math'):
        assert not isinstance(sandbox._safe_globals[name], types.ModuleType)
    assert 'getattr' not in sandbox._safe_globals['__builtins__']


# ---------------------------------------------------------------------------
# Resource limits: the validation dry run must reject runaway code instead
# of hanging the caller.
# ---------------------------------------------------------------------------

WORKING_STRATEGY = """
from core.strategy import BaseStrategy
import numpy as np

class CustomStrategy(BaseStrategy):
    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'cash_amount': 0.0}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return float(np.abs(-40000.0))

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        {LOOP}
        return {'amount_sold': float(desired_drawdown), 'debt_increase': 0.0}

    @property
    def shortfall_funding_policy(self):
        return ['SELL_ASSETS']

    @property
    def parameters(self):
        return {}
"""


def test_valid_strategy_passes_isolated_validation():
    code = WORKING_STRATEGY.replace("{LOOP}", "pass")
    cls = execute_strategy_code(code, "CustomStrategy")
    assert cls is not None


def test_infinite_loop_is_rejected_by_timeout(monkeypatch):
    monkeypatch.setenv("SANDBOX_VALIDATION_TIMEOUT_SECONDS", "3")
    code = WORKING_STRATEGY.replace(
        "{LOOP}", "counter = 0\n        while True:\n            counter = counter + 1"
    )
    with pytest.raises(ValueError, match="timed out"):
        execute_strategy_code(code, "CustomStrategy")
