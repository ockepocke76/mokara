import pytest
import numpy as np
from core.simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import TrinityStrategy

@pytest.fixture
def base_params():
    """A pytest fixture to provide a default set of parameters for tests."""
    return {
        'num_simulations': 1,
        'num_years': 20,
        'initial_investment': 1_000_000, # This cash is used by the strategy to buy assets at year 0
        'initial_assets': 0,
        'initial_debt': 0,
        'inflation_rate': 0.0,
        'asset_model': 'parametric',
        'strategy': 'trinity',
        'drawdown_method': 'percentage',
        'withdrawal_rate': 0.50, # High withdrawal rate to force depletion
        'annual_return': 0.0,
        'annual_volatility': 0.0,
        'loan_interest_rate': 0.0,
        'asset_management_fee': 0.01, # 1% fee
        'isk_tax_rate': 0.01, # 1% tax
        'capital_gains_tax_rate': 0.0,
        'tax_method': 'isk',
        'initial_percentage_rate': 0.04,
    }

def test_no_negative_values_on_depletion(base_params):
    """
    Tests that even when a portfolio is completely depleted, asset values and costs
    never become negative.
    """
    # Arrange
    params = base_params.copy()
    # Ensure the strategy starts with cash to buy assets, as initial_assets is 0.
    params['initial_investment'] = 1_000_000
    strategy_map = {'trinity': TrinityStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)
    sim_results = results_df['Sim_0']

    # Assert
    # Check that asset value never drops below zero
    # With the new MultiIndex format, we must use .xs() to select by the 'Metric' level.
    asset_values = sim_results.xs('Asset Value', level='Metric')

    assert (asset_values >= 0).all(), "Asset Value should never be negative."

    # Check that all cost columns are never negative
    assert (sim_results.xs('Fees Paid', level='Metric') >= 0).all(), "Fees Paid should never be negative."
    assert (sim_results.xs('Tax Paid', level='Metric') >= 0).all(), "Tax Paid should never be negative."
    assert (sim_results.xs('Interest Paid', level='Metric') >= 0).all(), "Interest Paid should never be negative."
    assert (sim_results.xs('Consumption Delivered', level='Metric') >= 0).all(), "Consumption Delivered (consumption paid) should never be negative."

    # Verify that once asset value is zero, it stays zero
    zero_asset_years = asset_values[asset_values == 0]
    if not zero_asset_years.empty:
        first_zero_year = zero_asset_years.index.min()
        # Asset value should stay zero after the first depletion year.
        assert (asset_values.loc[first_zero_year:] == 0).all(), "Asset Value should stay zero after depletion."

        # Costs can still be incurred in the year of depletion (e.g., ISK tax on the previous year's value).
        # We must check that costs become zero in the year *after* the first full year of depletion.
        year_after_depletion = first_zero_year + 1
        if year_after_depletion <= params['num_years']:
            following_years_results = sim_results.loc[year_after_depletion:]
            assert (following_years_results.xs('Fees Paid', level='Metric') == 0).all(), "Fees should be zero in the years following depletion."
            assert (following_years_results.xs('Tax Paid', level='Metric') == 0).all(), "Taxes should be zero in the years following depletion."
