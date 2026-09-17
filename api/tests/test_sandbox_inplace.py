"""In-place assignment support in the sandbox (R5.10).

The old source-level regex rewriter corrupted `**=` and `//=` and only
accidentally enabled attribute/subscript augmented assignment. Now plain
names go through a real _inplacevar_ and attribute/subscript targets are
desugared at the AST level by the policy.
"""
from core.sandbox import execute_strategy_code

STRATEGY = """
from core.strategy import BaseStrategy

class CustomStrategy(BaseStrategy):
    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        self.counter = 0.0
        return {'cash_amount': 0.0}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        {BODY}
        return float(result)

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        return {'amount_sold': float(desired_drawdown), 'debt_increase': 0.0}

    @property
    def shortfall_funding_policy(self):
        return ['SELL_ASSETS']

    @property
    def parameters(self):
        return {}
"""


def _run_drawdown(body_lines, expected):
    body = "\n        ".join(body_lines)
    code = STRATEGY.replace("{BODY}", body)
    cls = execute_strategy_code(code, "CustomStrategy", isolate=False)
    instance = cls({'initial_investment': 1_000_000})
    result = instance.get_annual_drawdown(1, {}, [])
    assert result == expected, f"expected {expected}, got {result}"


def test_plain_name_inplace_operators():
    _run_drawdown(["result = 40000.0", "result += 2000.0"], 42000.0)
    _run_drawdown(["result = 6.0", "result -= 2.0", "result *= 7.0"], 28.0)
    _run_drawdown(["result = 84.0", "result /= 2.0"], 42.0)


def test_power_and_floordiv_no_longer_corrupted():
    # The old regex turned `x **= 2` into `x * = x * * 2` (SyntaxError).
    _run_drawdown(["result = 2.0", "result **= 2"], 4.0)
    _run_drawdown(["result = 85.0", "result //= 2"], 42.0)
    _run_drawdown(["result = 85.0", "result %= 43.0"], 42.0)


def test_attribute_augassign_desugars():
    _run_drawdown(
        ["self.counter = 40.0", "self.counter += 2.0", "result = self.counter"],
        42.0,
    )


def test_subscript_augassign_desugars():
    _run_drawdown(
        ["totals = {'a': 40.0}", "totals['a'] += 2.0", "result = totals['a']"],
        42.0,
    )


def test_list_augassign_extends():
    _run_drawdown(
        ["xs = [1.0, 2.0]", "xs += [39.0]", "result = xs[0] + xs[1] + xs[2]"],
        42.0,
    )
