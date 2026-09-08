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
