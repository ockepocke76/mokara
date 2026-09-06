import pytest
import numpy as np
import pandas as pd
from simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import BaseStrategy

@pytest.fixture
def robustness_params():
    """A pytest fixture for a default set of parameters for engine robustness tests."""
    return {
        'num_simulations': 1,
        'num_years': 5,
        'initial_investment': 1_000_000, # This will be used to buy assets in Year 0
        'initial_assets': 1_000_000,
        'initial_debt': 0,
        'inflation_rate': 0.0,
        'asset_model': 'parametric',
        'annual_return': 0.0,
        'annual_volatility': 0.0,
        'loan_interest_rate': 0.0,
        'asset_management_fee': 0.0, # Default to 0, tests can override
        'tax_method': 'capital_gains', # More common for these tests
        'isk_tax_rate': 0.0,
        'cash_interest_rate': 0.0,
    }

# --- Test Strategy 1: The Overspender ---
class OverspendingStrategy(BaseStrategy):
    """A strategy that requests a huge drawdown with no plan to fund it."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters
    
    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {} # Start with assets from params

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['BORROW'] # This strategy's philosophy is to borrow for all needs.

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 1_000_000_000 # Request an absurd amount

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # This strategy provides no funding plan.
        return {}

def test_engine_prevents_overspending(robustness_params):
    """
    **Purpose:** Verifies the engine does not fund a consumption drawdown if the strategy provides no funding plan.
    **Method:** A strategy requests a 1B drawdown but provides no funding. The engine should only borrow to cover mandatory costs, and the consumption drawdown should be zero.
    **Assertion:** The test asserts that the `Consumption Delivered` (consumption paid) is zero, and the debt increase only covers the mandatory fee.
    """
    # Arrange
    params = robustness_params.copy()
    params['strategy'] = 'custom'
    params['initial_investment'] = 0 # Start with 0 cash
    params['initial_assets'] = 1_000_000
    params['asset_management_fee'] = 0.01 # 1% fee on 1M assets = 10,000

    strategy_map = {'custom': OverspendingStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']
    results_y1 = sim_results.loc[1]

    # Assert
    # 1. The engine's shortfall policy should only borrow to cover the mandatory fee (10k),
    #    as it no longer funds consumption drawdowns via the shortfall mechanism.
    assert results_y1['Debt Change'] == pytest.approx(10_000)
    # 2. Since the strategy provided no funds for the 1B drawdown, the actual consumption paid must be zero.
    assert results_y1['Consumption Delivered'] == pytest.approx(0)
    # 3. The final cash balance must be exactly zero, as the borrowed 10k was used to pay the fee.
    assert results_y1['Cash'] == pytest.approx(0)


# --- Test Strategy 2: The Reinvestor Illusion ---
class ReinvestorIllusionStrategy(BaseStrategy):
    """A strategy that tries to buy assets with cash it doesn't have."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['USE_CASH']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # Try to buy 1B of assets, even though we only have 100k cash.
        return {'amount_bought': 1_000_000_000}

def test_engine_prevents_buying_with_nonexistent_cash(robustness_params):
    """
    **Purpose:** Verifies the engine caps asset purchases at the available cash balance.
    **Assertion:** The `Amount Bought` is limited to the actual cash on hand, and the final cash balance is non-negative.
    """
    # Arrange
    params = robustness_params.copy()
    params['strategy'] = 'custom'
    params['initial_investment'] = 100_000 # Start with 100k cash
    params['initial_assets'] = 0
    strategy_map = {'custom': ReinvestorIllusionStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']
    results_y1 = sim_results.loc[1]

    # Assert
    # The engine must cap the purchase at the available 100k cash.
    assert results_y1['Amount Bought'] == pytest.approx(100_000)
    # The final cash balance must be zero.
    assert results_y1['Cash'] == pytest.approx(0)
    # The asset value should now be 100k.
    assert results_y1['Asset Value'] == pytest.approx(100_000)


# --- Test Strategy 3: The Trinity Liar ---
class TrinityLiarStrategy(BaseStrategy):
    """A strategy that sells assets but then tries to use the cash to buy more assets before consumption is paid."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS'] # This strategy sells assets to cover needs.

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 100_000 # Request 100k for consumption

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # Sell 100k to fund consumption, but also try to buy 100k.
        return {'amount_sold': 100_000, 'amount_bought': 100_000}

def test_engine_prioritizes_consumption_over_reinvestment(robustness_params):
    """
    **Purpose:** Verifies that consumption and costs are paid before any reinvestment (`amount_bought`) occurs.
    """
    params = robustness_params.copy()
    params.update({'strategy': 'custom', 'initial_investment': 0})
    strategy_map = {'custom': TrinityLiarStrategy(params)}
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']
    results_y1 = sim_results.loc[1]

    # The strategy sold 100k. This cash MUST be used for the 100k consumption first.
    # There should be no cash left to buy assets.
    assert results_y1['Amount Bought'] == 0
    assert results_y1['Consumption Delivered'] == pytest.approx(100_000)
    assert results_y1['Cash'] == pytest.approx(0)
class ShortfallFundingStrategy(BaseStrategy):
    """A strategy that intentionally creates a funding shortfall for the engine to handle."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {} # Start with assets from params

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 100_000 # Request 100k for consumption every year

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['BORROW'] # This strategy's philosophy is to borrow for all needs.

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # This strategy has no plan to fund the drawdown or costs.
        # It relies entirely on the engine's "universal backstop" to borrow.
        return {}

def test_engine_correctly_funds_shortfall_with_interest(robustness_params):
    """
    **Purpose:** Verifies the engine's shortfall policy borrows only for mandatory costs, not for consumption.
    **Method:** A strategy requests a drawdown but provides no funding. The engine should only borrow to cover the mandatory fee.
    **Assertion:** The debt increase equals the mandatory fee, and the unfunded `Consumption Delivered` is zero. Interest paid in the current year is zero as debt is new.
    """
    # Arrange
    params = robustness_params.copy()
    params.update({
        'strategy': 'custom', 'num_years': 1, # Test for a single year
        'initial_investment': 0, # CRITICAL: Start with zero cash to force borrowing
        'initial_assets': 1_000_000,
        'loan_interest_rate': 0.10, # 10% interest
        'asset_management_fee': 0.01, # 1% fee on 1M assets = 10,000
    })
    strategy_map = {'custom': ShortfallFundingStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    results_y1 = prepare_results_dataframe(simulations)['Sim_0'].loc[1]

    # Assert
    # 1. At the start of Year 1, debt is 0. Therefore, interest paid *in* Year 1 must be 0.
    assert results_y1['Interest Paid'] == pytest.approx(0)

    # 2. The strategy provided no funding. The engine's shortfall policy must borrow to cover mandatory costs only.
    fee = 10_000
    expected_borrowing = fee # 10,000

    # 3. The engine borrows 10k to cover the fee. This becomes the `Debt Change` and the final `Debt`.
    assert results_y1['Debt Change'] == pytest.approx(expected_borrowing)
    assert results_y1['Debt'] == pytest.approx(expected_borrowing)

    # 4. The borrowed cash is used for the fee. Since the 100k drawdown was not funded by the strategy,
    #    the actual consumption paid (`Consumption Delivered`) must be zero.
    assert results_y1['Consumption Delivered'] == pytest.approx(0)
    assert results_y1['Fees Paid'] == pytest.approx(fee)
    assert results_y1['Cash'] == pytest.approx(0)

class CashFlowConfuserStrategy(BaseStrategy):
    """A strategy that sells an asset and immediately tries to buy another, to test the cash flow priority."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {} # Start with assets from params

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 100_000 # Request 100k for consumption

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS'] # This strategy sells assets to cover needs.

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # Sell 100k to fund consumption, but also try to buy 100k.
        return {'amount_sold': 100_000, 'amount_bought': 100_000}

def test_engine_prioritizes_consumption_over_reinvestment_from_sale(robustness_params):
    """
    **Purpose:** Verifies the engine's cash flow waterfall correctly prioritizes consumption over reinvestment.
    **Method:** A strategy sells an asset to fund a drawdown but simultaneously requests to buy an asset with the same amount.
    **Assertion:** The test asserts that the consumption was fully funded and that no assets were bought, proving that consumption takes precedence.
    """
    # Arrange
    params = robustness_params.copy()
    params.update({'strategy': 'custom', 'initial_investment': 0, 'num_years': 1}) # No initial cash to force use of sale proceeds
    strategy_map = {'custom': CashFlowConfuserStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    results_y1 = prepare_results_dataframe(simulations)['Sim_0'].loc[1]

    # Assert
    # The 100k from the sale must be used for the 100k drawdown. No cash should be left for buying.
    assert results_y1['Consumption Delivered'] == pytest.approx(100_000)
    assert results_y1['Amount Bought'] == pytest.approx(0)
    assert results_y1['Cash'] == pytest.approx(0)
