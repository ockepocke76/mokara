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
