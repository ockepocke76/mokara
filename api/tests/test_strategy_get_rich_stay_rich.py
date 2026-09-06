import pytest
import numpy as np
import pandas as pd
from simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy

@pytest.fixture
def base_params():
    """A pytest fixture to provide a default set of parameters for tests."""
    return {
        'num_simulations': 1,
        'num_years': 10,
        'initial_investment': 1_000_000,
        'annual_contribution': 100_000,
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'strategy': 'get_rich_stay_rich',
        'target_net_worth': 10_000_000,
        'cash_years_on_stay_rich': 2,
        'withdrawal_rate': 0.04,
        'annual_return': 0.0,
        'annual_volatility': 0.0,
    }

def test_get_rich_phase(base_params):
    """
    Tests the GetRich phase of the GetRichStayRichStrategy.
    """
    # Arrange
    params = base_params.copy()
    strategy_map = {'get_rich_stay_rich': GetRichStayRichStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)
    sim_results = results_df['Sim_0']

    # Assert
    # Check that the portfolio is 100% invested in the asset and contributions are made
    for year in range(1, params['num_years'] + 1):
        year_results = sim_results.loc[year]
        contribution = params['annual_contribution'] * (1 + params['inflation_rate'])**(year - 1)
        assert year_results['Amount Contributed'] == pytest.approx(contribution)
        assert year_results['Amount Bought'] == pytest.approx(contribution)

def test_stay_rich_phase_transition(base_params):
    """
    Tests the three-phase transition: Get Rich → Build Buffer → Stay Rich.
    Verifies that buffer building phase activates and builds cash before withdrawals start.
    """
    # Arrange
    params = base_params.copy()
    params['initial_investment'] = 9_000_000
    params['annual_contribution'] = 1_000_000
    params['target_net_worth'] = 10_000_000
    params['inflation_rate'] = 0.0  # No inflation for simpler testing
    params['num_years'] = 5
    params['annual_return'] = 0.07  # 7% growth
    params['cash_years_on_stay_rich'] = 2
    params['withdrawal_rate'] = 0.04

    strategy = GetRichStayRichStrategy(params)
    strategy_map = {'get_rich_stay_rich': strategy}

    # Act
    simulations = run_simulation(params, mu=0.07/365, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)
    sim_results = results_df['Sim_0']

    # --- Assert Year 1: Get Rich Phase ---
    results_y1 = sim_results.loc[1]
    assert results_y1['Amount Contributed'] == pytest.approx(1_000_000)
    assert results_y1['Amount Sold'] == 0
    assert results_y1['Consumption Delivered'] == 0  # No drawdown in Get Rich phase

    # --- Assert Year 2: Build Buffer Phase ---
    # Assets hit target, now building cash buffer
    results_y2 = sim_results.loc[2]
    assert results_y2['Amount Contributed'] > 0  # Contributions continue
    assert results_y2['Amount Sold'] > 0  # Selling growth to build cash
    assert results_y2['Consumption Delivered'] == 0  # No drawdown yet
    assert results_y2['Cash'] > 0  # Cash buffer starting to build
    
    # --- Assert Year 3: Stay Rich Phase (if buffer is built) ---
    # With 7% growth, buffer should be built by Year 3
    results_y3 = sim_results.loc[3]
    # Once buffer is built, contributions stop and drawdowns start
    if results_y3['Consumption Delivered'] > 0:
        assert results_y3['Amount Contributed'] == 0  # Contributions stop in Stay Rich
        assert results_y3['Cash'] > 0  # Buffer exists


def test_stay_rich_dynamic_cash_buffer(base_params):
    """
    Tests the three-phase flow with buffer building.
    Verifies that cash buffer is built before Stay Rich phase starts.
    """
    # Arrange
    params = base_params.copy()
    params.update({
        'num_years': 8,
        'initial_investment': 9_500_000,
        'annual_contribution': 500_000,
        'target_net_worth': 10_000_000,
        'cash_years_on_stay_rich': 2,  # 2 years for faster buffer building
        'withdrawal_rate': 0.04,
        'inflation_rate': 0.0,  # No inflation for simpler testing
        'annual_return': 0.07,  # 7% growth
        'annual_volatility': 0.0,
    })

    strategy = GetRichStayRichStrategy(params)
    strategy_map = {'get_rich_stay_rich': strategy}

    # Act
    simulations = run_simulation(params, mu=0.07/365, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)
    sim_results = results_df['Sim_0']

    # --- Assert Year 1: Get Rich Phase ---
    results_y1 = sim_results.loc[1]
    assert results_y1['Net Worth'] >= 10_000_000  # Reaches target
    assert results_y1['Consumption Delivered'] == 0  # No drawdown yet

    # --- Assert Year 2: Build Buffer Phase ---
    results_y2 = sim_results.loc[2]
    assert results_y2['Amount Contributed'] > 0  # Contributions continue
    assert results_y2['Consumption Delivered'] == 0  # No drawdown during buffer building
    assert results_y2['Cash'] > 0  # Cash buffer building
    
    # --- Assert Year 3+: Eventually reaches Stay Rich ---
    # Find the first year with drawdown (Stay Rich activated)
    stay_rich_year = None
    for year in range(2, 9):
        if sim_results.loc[year]['Consumption Delivered'] > 0:
            stay_rich_year = year
            break
    
    assert stay_rich_year is not None, "Should eventually reach Stay Rich phase"
    results_stay_rich = sim_results.loc[stay_rich_year]
    assert results_stay_rich['Cash'] > 0  # Buffer exists when Stay Rich starts
    assert results_stay_rich['Amount Contributed'] == 0  # Contributions stop

def test_stay_rich_cash_interest_accrual(base_params):
    """
    Tests that interest is correctly accrued on cash holdings during the Stay Rich phase.
    With positive growth, a cash buffer is built and earns interest.
    """
    # Arrange
    params = base_params.copy()
    params.update({
        'num_years': 5,
        'initial_investment': 9_500_000,
        'annual_contribution': 500_000,
        'target_net_worth': 10_000_000,
        'cash_years_on_stay_rich': 2,
        'withdrawal_rate': 0.04,
        'cash_interest_rate': 0.05, # Use a non-zero interest rate for the test
        'inflation_rate': 0.0, # No inflation to simplify calculations
        'annual_return': 0.05,  # 5% growth to build buffer
        'annual_volatility': 0.0,
    })

    strategy = GetRichStayRichStrategy(params)
    strategy_map = {'get_rich_stay_rich': strategy}

    # Act
    simulations = run_simulation(params, mu=0.05/365, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)
    sim_results = results_df['Sim_0']

    # --- Assert Year 1: Get Rich Phase ---
    # Net worth reaches 10M (with growth), no cash is held yet.
    results_y1 = sim_results.loc[1]
    assert results_y1['Net Worth'] >= 10_000_000
    assert results_y1['Cash'] == 0
    assert results_y1['Cash Interest'] == 0

    # --- Assert Year 2: Transition to Stay Rich ---
    results_y2 = sim_results.loc[2]
    # No interest yet (cash at start of Y2 was 0)
    assert results_y2['Cash Interest'] == 0

    # --- Assert Year 3: Buffer Built and Interest Earned ---
    # With 5% growth in Year 2-3, buffer is built
    # Interest is earned on the buffer created in Year 2
    results_y3 = sim_results.loc[3]
    # Cash buffer should exist
    assert results_y3['Cash'] > 0
    # Interest should be positive (earned on Y2's cash balance)
    assert results_y3['Cash Interest'] > 0