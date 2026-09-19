"""`state_*` keys on a strategy's yearly action dict land in the yearly
history as numeric metrics, and survive the results-dataframe aggregation."""
import numpy as np

from core.shared_logic import prepare_results_dataframe
from core.simulation import run_simulation, strategy_state_from_actions
from core.strategy import BaseStrategy

PARAMS = {
    'num_simulations': 2, 'num_years': 3, 'initial_investment': 1_000_000,
    'initial_assets': 1_000_000, 'initial_debt': 0, 'inflation_rate': 0.0,
    'asset_model': 'parametric', 'annual_return': 0.0, 'annual_volatility': 0.0,
    'loan_interest_rate': 0.0, 'asset_management_fee': 0.0,
    'tax_method': 'capital_gains', 'capital_gains_tax_rate': 0.0,
    'cash_interest_rate': 0.0,
}


class PhaseStrategy(BaseStrategy):
    @property
    def parameters(self) -> dict:
        return {}

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history,
                                  desired_drawdown, mandatory_costs):
        return {'amount_sold': 0.0,
                'state_transitioned': year >= 2,
                'state_ratio': year * 1.5,
                'state_label': 'retired',     # strings are dropped
                'state_nan': float('nan'),    # non-finite is dropped
                'phase': 7}                   # no prefix => not state


def test_state_keys_coerced_to_finite_floats():
    state = strategy_state_from_actions(PhaseStrategy(PARAMS).execute_strategy_for_year(
        2, {}, [], 0.0, 0.0))
    assert state == {'state_transitioned': 1.0, 'state_ratio': 3.0}


def test_state_reaches_history_and_results_dataframe():
    sims = run_simulation(PARAMS, strategy_map={'x': PhaseStrategy(PARAMS)})
    yearly = sims[0].yearly_results
    assert 'state_transitioned' not in yearly[0]  # year 0 has no decision
    assert [y['state_transitioned'] for y in yearly[1:]] == [0.0, 1.0, 1.0]
    assert yearly[3]['state_ratio'] == 4.5
    assert 'state_label' not in yearly[1]

    df = prepare_results_dataframe(sims)
    ratio = df.xs('state_ratio', level='Metric')
    assert list(ratio.index) == [1, 2, 3]
    assert np.allclose(ratio.median(axis=1).values, [1.5, 3.0, 4.5])
    # The standard metrics are untouched by the extra rows.
    assert df.xs('Net Worth', level='Metric').shape[0] == 4
