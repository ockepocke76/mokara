import pytest
import numpy as np
import pandas as pd
from core.simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import BaseStrategy

@pytest.fixture
def engine_test_params():
    """A pytest fixture for a default set of parameters for engine responsibility tests."""
    return {
        'num_simulations': 1,
        'num_years': 5,
        'initial_investment': 10_000_000,
        'initial_assets': 0,
        'initial_debt': 0,
        'inflation_rate': 0.0,
        'asset_model': 'parametric',
        'annual_return': 0.0,
        'annual_volatility': 0.0,
        'loan_interest_rate': 0.0,
        'asset_management_fee': 0.0,
        'tax_method': 'capital_gains',
        'capital_gains_tax_rate': 0.0,
    }

# --- Test Strategy 1: A strategy that stubbornly refuses to deleverage ---
class NoDeleveragingStrategy(BaseStrategy):
    """A strategy that borrows aggressively and NEVER sells, to test the engine's neutrality."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        # This strategy's philosophy is to borrow for all needs, including shortfalls.
        return ['BORROW']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        # Borrows a large, fixed amount each year to quickly raise LTV
        return 2_000_000

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # --- FIX: The strategy must explicitly plan to fund the TOTAL cash need. ---
        # The total cash need is both the desired drawdown for consumption AND any mandatory costs.
        # This strategy's philosophy is to borrow for all needs.
        return {
            'amount_sold': 0.0,
            'debt_increase': desired_drawdown + mandatory_costs,
        }

def test_engine_does_not_deleverage_on_its_own(engine_test_params):
    """
    **Purpose:** Verifies the engine does NOT contain deleveraging logic.
    **Method:** Runs a strategy that intentionally drives LTV to a high level but never commands a sale.
    **Assertion:** The test asserts that no assets were sold, proving the engine did not intervene.
    """
    # Arrange
    params = engine_test_params.copy()
    params['strategy'] = 'custom' # Use our custom test strategy
    params['num_years'] = 3
    
    strategy_map = {'custom': NoDeleveragingStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']

    # --- Assert ---
    # In year 3, debt will be 6M and assets 10M. LTV will be 60%.
    # A "smart" engine might try to sell, but our "dumb" engine should not.
    # --- FIX: Select data using the new (Year, Metric) MultiIndex structure ---
    debt_y3 = sim_results.loc[(3, 'Debt')]
    asset_value_y3 = sim_results.loc[(3, 'Asset Value')]
    final_ltv = debt_y3 / asset_value_y3
    assert final_ltv > 0.5, "Test setup failed: LTV did not become high as expected."
    
    # The crucial assertion: The engine must not sell any assets, even with high LTV,
    # because the strategy did not command it.
    assert sim_results.xs('Amount Sold', level='Metric').sum() == 0


# --- Test Strategy 4: A strategy that checks if the engine is doing its job ---
class CostAwarenessTestStrategy(BaseStrategy):
    """A strategy that exists only to verify the engine is correctly calculating and passing mandatory costs."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        # Buy assets to ensure there's a basis for fees.
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        # This is a required abstract property. We must implement it.
        return ['BORROW', 'USE_CASH']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0 # No consumption

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # This is the core of the test.
        # We assert that the engine has correctly calculated and passed the costs.
        # If a future refactoring breaks this and passes 0, this test will fail.
        assert mandatory_costs > 0, "Engine failed to pass a non-zero mandatory_costs value to the strategy."
        
        # The strategy doesn't need to do anything else.
        return {}

def test_engine_informs_strategy_of_mandatory_costs(engine_test_params):
    """
    **Purpose:** Verifies the engine correctly calculates mandatory costs and passes them to the strategy.
    **Method:** Runs a special test strategy that asserts the `mandatory_costs` argument is greater than zero.
    **Assertion:** The test passes if the simulation runs without an assertion error from the strategy.
    """
    params = engine_test_params.copy()
    # --- FIX: Start with assets directly to ensure costs are calculated in Year 1 ---
    # The fee is calculated on the asset value at the start of the year.
    # By setting initial_assets, we ensure there's a value to apply the fee to.
    params.update({
        'strategy': 'custom', 'num_years': 1, 'asset_management_fee': 0.01,
        'initial_assets': 1_000_000, 'initial_investment': 0 # Start with assets, no cash
    })
    strategy_map = {'custom': CostAwarenessTestStrategy(params)}

    # This test will fail with an `AssertionError` from within the strategy if the engine is broken.
    run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)


# --- Test Strategy 2: A strategy that stubbornly refuses to suspend drawdowns ---
class NoDrawdownSuspensionStrategy(BaseStrategy):
    """A strategy that always requests a drawdown, regardless of LTV, to test the engine's neutrality."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        # This strategy's philosophy is to borrow for all needs.
        return ['BORROW']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        # This strategy's core logic: ALWAYS request a 1M drawdown.
        # It has no internal LTV check.
        return 1_000_000

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # Funds the drawdown by borrowing.
        return {
            'amount_sold': 0.0,
            'debt_increase': desired_drawdown,
            'amount_bought': 0.0,
            'debt_repayment': 0.0
        }

def test_engine_does_not_suspend_drawdowns_on_its_own(engine_test_params):
    """
    **Purpose:** Verifies the engine does NOT contain logic to suspend drawdowns based on LTV.
    **Method:** Runs a strategy that always requests a drawdown, even when LTV is high.
    **Assertion:** The test asserts that the drawdown was still executed, proving the engine did not intervene.
    """
    # Arrange
    params = engine_test_params.copy()
    params['strategy'] = 'custom'
    params['num_years'] = 2
    
    strategy_map = {'custom': NoDrawdownSuspensionStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']

    # --- Assert ---
    # At the start of Year 2, debt is 1M and assets are 10M. LTV is 10%.
    # A strategy might suspend drawdowns here, but the engine should not care.
    # The strategy will request another 1M drawdown.
    # --- FIX: Select data using the new (Year, Metric) MultiIndex structure ---
    debt_y1 = sim_results.loc[(1, 'Debt')]
    asset_value_y1 = sim_results.loc[(1, 'Asset Value')]
    ltv_at_start_of_y2 = debt_y1 / asset_value_y1
    assert ltv_at_start_of_y2 > 0.05, "Test setup failed: LTV at start of Y2 was not high enough."

    # The crucial assertion: The engine must execute the drawdown requested by the strategy,
    # even though the LTV was elevated.
    assert sim_results.loc[(2, 'Consumption Delivered')] == 1_000_000


# --- Test Strategy 3: A strategy that makes a "pointless" sale ---
class PointlessSaleStrategy(BaseStrategy):
    """A strategy that sells assets in Year 2 for no reason, to test the engine's blind execution."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        # This strategy sells assets, so it should sell to cover shortfalls too.
        return ['SELL_ASSETS']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0 # No consumption needed

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # In year 2, sell 500k of assets for no apparent reason.
        amount_to_sell = 500_000 if year == 2 else 0.0
        return {
            'amount_sold': amount_to_sell,
            'debt_increase': 0.0,
            'amount_bought': 0.0,
            'debt_repayment': 0.0
        }

def test_engine_blindly_executes_sale_command(engine_test_params):
    """
    **Purpose:** Verifies the engine blindly executes any 'amount_sold' command from the strategy.
    """
    params = engine_test_params.copy()
    params.update({'strategy': 'custom', 'num_years': 2})
    strategy_map = {'custom': PointlessSaleStrategy(params)}
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']

    # --- FIX: Select data using the new (Year, Metric) MultiIndex structure ---
    assert sim_results.loc[(1, 'Amount Sold')] == 0
    assert sim_results.loc[(2, 'Amount Sold')] == 500_000
