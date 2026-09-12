"""
W5 engine prep: seeded paired test sims, evaluation_category validation,
inspect-derived strategy API docs.
"""
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.sandbox import execute_strategy_code
from core.sandbox_tester import run_sandbox_test
from core.strategy_docs import HISTORY_KEYS, strategy_api_docs

SIMPLE_STRATEGY = '''
class SeedTestStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {'withdrawal_rate': {'description': 'Annual withdrawal', 'default': 0.04}}

    @property
    def shortfall_funding_policy(self):
        return ['USE_CASH', 'SELL_ASSETS']

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        rate = self.params.get('withdrawal_rate', 0.04)
        return self.params.get('initial_investment', 1000000) * rate

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        need = desired_drawdown + mandatory_costs
        return {'amount_sold': need, 'amount_bought': 0.0,
                'debt_increase': 0.0, 'debt_repayment': 0.0, 'amount_contributed': 0.0}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''

BAD_CATEGORY_STRATEGY = SIMPLE_STRATEGY.replace(
    "return 'WITHDRAWAL_ONLY'", "return 'SPEND_IT_ALL'"
).replace("class SeedTestStrategy", "class BadCategoryStrategy")

TEST_PARAMS = {'num_years': 5, 'num_random_paths': 3, 'initial_investment': 1000000}


def _final_net_worths(result):
    assert result['success'], result.get('error')
    return [p['yearly_results'][-1]['Net Worth'] for p in result['random_paths']]


def test_same_seed_gives_identical_market_paths():
    a = run_sandbox_test(SIMPLE_STRATEGY, 'SeedTestStrategy', dict(TEST_PARAMS), seed=42)
    b = run_sandbox_test(SIMPLE_STRATEGY, 'SeedTestStrategy', dict(TEST_PARAMS), seed=42)
    assert _final_net_worths(a) == _final_net_worths(b)


def test_different_seeds_give_different_paths():
    a = run_sandbox_test(SIMPLE_STRATEGY, 'SeedTestStrategy', dict(TEST_PARAMS), seed=42)
    b = run_sandbox_test(SIMPLE_STRATEGY, 'SeedTestStrategy', dict(TEST_PARAMS), seed=43)
    assert _final_net_worths(a) != _final_net_worths(b)


def test_evaluation_category_validated():
    # Strict at generation time: the validate node rejects a bad category.
    with pytest.raises(ValueError, match="evaluation_category"):
        execute_strategy_code(
            BAD_CATEGORY_STRATEGY, 'BadCategoryStrategy', strict_category=True
        )
    # Tolerant by default so strategies saved before category validation
    # existed still load (the category is coerced downstream).
    assert (
        execute_strategy_code(BAD_CATEGORY_STRATEGY, 'BadCategoryStrategy')
        is not None
    )


def test_default_evaluation_category_still_passes():
    # A strategy that does not override evaluation_category falls back to
    # the base class's 'HYBRID' and must keep validating.
    no_category = SIMPLE_STRATEGY.replace(
        "    def evaluation_category(self):\n        return 'WITHDRAWAL_ONLY'\n", ""
    ).replace("class SeedTestStrategy", "class NoCategoryStrategy")
    assert execute_strategy_code(no_category, 'NoCategoryStrategy') is not None


def test_strategy_api_docs_derived_from_source():
    docs = strategy_api_docs()
    for member in ['parameters', 'initialize_portfolio', 'get_annual_drawdown',
                   'execute_strategy_for_year', 'shortfall_funding_policy',
                   'evaluation_category']:
        assert member in docs
    assert 'REQUIRED' in docs
    for key in HISTORY_KEYS:
        assert key in docs
    # Docstring content actually flows through from the class
    assert 'USE_CASH' in docs


# --- Category-aware smoke-test capital (mirror of STANDARD_EVAL_PARAMS) ----

CONTRIB_STRATEGY = '''
class ContribTestStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {}

    @property
    def shortfall_funding_policy(self):
        return ['USE_CASH', 'SELL_ASSETS']

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        return {'amount_sold': mandatory_costs, 'amount_bought': 0.0,
                'debt_increase': 0.0, 'debt_repayment': 0.0, 'amount_contributed': 50000.0}

    def evaluation_category(self):
        return 'CONTRIBUTION_ONLY'
'''


def test_capital_params_follow_category():
    from core.sandbox_tester import capital_params_for_category
    from core.strategy_evaluation import STANDARD_EVAL_PARAMS

    assert capital_params_for_category('WITHDRAWAL_ONLY') == {
        'initial_investment': STANDARD_EVAL_PARAMS['WITHDRAWAL_ONLY']['initial_investment']}
    contrib = capital_params_for_category('CONTRIBUTION_ONLY')
    assert contrib['initial_investment'] == 100_000
    assert contrib['annual_contribution'] == 50_000
    assert capital_params_for_category('NO_SUCH_CATEGORY') == {}


def test_smoke_test_uses_category_capital():
    # A contribution strategy is smoke-tested from the accumulation-scale
    # start ($100k), not the withdrawal-scale $1M that would swamp it.
    result = run_sandbox_test(CONTRIB_STRATEGY, 'ContribTestStrategy',
                              {'num_years': 3, 'num_random_paths': 2}, seed=7)
    assert result['success'], result.get('error')
    first_year_nw = result['random_paths'][0]['yearly_results'][0]['Net Worth']
    assert first_year_nw < 500_000  # started near 100k, not 1M

    # An explicit caller override still wins.
    result = run_sandbox_test(CONTRIB_STRATEGY, 'ContribTestStrategy',
                              {'num_years': 3, 'num_random_paths': 2,
                               'initial_investment': 1_000_000}, seed=7)
    assert result['success'], result.get('error')
    first_year_nw = result['random_paths'][0]['yearly_results'][0]['Net Worth']
    assert first_year_nw > 500_000


STATEFUL_STRATEGY = '''
class StatefulTestStrategy(BaseStrategy):
    def __init__(self, params):
        super().__init__(params)
        self.triggered = False

    def reset(self):
        self.triggered = False

    @property
    def parameters(self):
        return {}

    @property
    def shortfall_funding_policy(self):
        return ['USE_CASH', 'SELL_ASSETS']

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        if self.triggered:
            return 99999.0
        if year >= 3:
            self.triggered = True
        return 0.0

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        need = desired_drawdown + mandatory_costs
        return {'amount_sold': need, 'amount_bought': 0.0,
                'debt_increase': 0.0, 'debt_repayment': 0.0, 'amount_contributed': 0.0}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''


def test_strategy_state_never_leaks_between_paths():
    # The backtest scenario runs FIRST and flips `triggered` at year 3; a
    # shared instance then made every Monte Carlo path start pre-triggered
    # (the year-1 "instant retirement" bug from the first real user run).
    result = run_sandbox_test(STATEFUL_STRATEGY, 'StatefulTestStrategy',
                              {'num_years': 6, 'num_random_paths': 4,
                               'initial_investment': 1_000_000}, seed=11)
    assert result['success'], result.get('error')
    for path in result['random_paths']:
        yearly = path['yearly_results']
        # Years 1-2 precede the trigger in EVERY fresh path.
        for row in yearly[1:3]:
            assert row['Consumption Delivered'] == 0.0, (
                f"state leaked into {path['path_label']} year {row['Year']}")
