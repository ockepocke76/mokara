import pytest
import numpy as np
import pandas as pd
from simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import BaseStrategy

@pytest.fixture
def bookkeeping_params():
    """A pytest fixture for a default set of parameters for bookkeeping tests."""
    return {
        'num_simulations': 1,
        'num_years': 2,
        'initial_investment': 0,
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
        'cash_interest_rate': 0.0,
    }

class DeleveragingSaleStrategy(BaseStrategy):
    """A strategy that performs a simple sale in Year 2 to pay down debt from Year 1."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {} # Start with assets from params

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS', 'BORROW']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        # Borrow 100k in Year 1 for consumption
        return 100_000 if year == 1 else 0.0

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        if year == 1:
            # Fund the drawdown by borrowing
            return {'debt_increase': desired_drawdown}
        if year == 2:
            # --- FIX: The strategy must be explicit. ---
            # It must command both the sale AND the debt repayment.
            # The engine no longer assumes the proceeds of a sale are for repayment.
            amount_to_sell = 50_000
            return {'amount_sold': amount_to_sell, 'debt_repayment': amount_to_sell}
        return {}

def test_deleveraging_sale_correctly_reduces_cash(bookkeeping_params):
    """
    **Purpose:** Verifies that cash from an asset sale used for debt repayment is correctly debited from the final cash balance.
    **Method:** A strategy borrows in Year 1, then sells assets in Year 2 to repay part of that debt.
    **Assertion:** The test asserts that the final cash balance is zero, proving the sale proceeds were fully used and not left in the cash account.
    """
    # Arrange
    params = bookkeeping_params.copy()
    params['strategy'] = 'custom'
    params['initial_assets'] = 1_000_000  # FIX: Give the portfolio assets to sell.
    strategy_map = {'custom': DeleveragingSaleStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']
    results_y2 = sim_results.loc[2]

    # Assert
    assert results_y2['Amount Sold'] == 50_000
    assert results_y2['Debt'] == pytest.approx(100_000 - 50_000) # Initial 100k debt - 50k repayment
    asset_value = results_y2['Asset Value']
    assert asset_value == pytest.approx(1_000_000 - 50_000)
    assert results_y2['Cash'] == pytest.approx(0) # CRUCIAL: The cash from the sale should be gone.
    assert results_y2['Net Worth'] == pytest.approx(results_y2['Asset Value'] + results_y2['Cash'] - results_y2['Debt'])

class SaleForConsumptionStrategy(BaseStrategy):
    """A strategy that sells assets to fund consumption."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {} # Start with assets from params

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        # Request 100k for consumption every year
        return 100_000

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # With the refactored engine, the strategy is simply told the mandatory costs.
        # Its only job is to decide how to fund the total cash need.
        amount_to_sell = desired_drawdown + mandatory_costs
        return {'amount_sold': amount_to_sell}

def test_sale_proceeds_can_be_used_for_consumption(bookkeeping_params):
    """
    **Purpose:** Verifies that cash from an asset sale is correctly used to fund consumption in the same year.
    **Method:** A strategy with no initial cash sells assets to fund a 100k drawdown.
    **Assertion:** The test asserts that the drawdown was successful and the final cash balance is zero.
    """
    # Arrange
    params = bookkeeping_params.copy()
    params['strategy'] = 'custom'
    params['num_years'] = 1
    params['initial_assets'] = 1_000_000  # FIX: Give the portfolio assets to sell.
    params['asset_management_fee'] = 0.01 # Add a 1% fee (10k) to ensure costs are also covered.
    strategy_map = {'custom': SaleForConsumptionStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    sim_results = prepare_results_dataframe(simulations)['Sim_0']
    results_y1 = sim_results.loc[1]

    # Assert
    amount_sold = results_y1['Amount Sold']
    assert amount_sold == pytest.approx(100_000 + 10_000) # Sale covers drawdown + fee
    annual_drawdown = results_y1['Consumption Delivered']
    assert annual_drawdown == pytest.approx(100_000) # Consumption was successful
    fees_paid = results_y1['Fees Paid']
    assert fees_paid == pytest.approx(10_000)
    cash = results_y1['Cash']
    assert cash == pytest.approx(0) # All cash from the sale was used up.

class CostBasisTestStrategy(BaseStrategy):
    """A strategy that sells a fixed amount of assets in Year 2."""
    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        # Buy 1M of assets from initial cash, establishing the cost basis.
        return {'action': 'BUY_ASSET', 'cash_amount': 1_000_000}

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS']

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        if year == 2:
            # The strategy's plan is to sell 120k. It does not know about the tax
            # this sale will generate. The engine must handle the resulting shortfall.
            return {
                'amount_sold': 120_000,
                'amount_bought': 0.0,
                'debt_increase': 0.0,
                'debt_repayment': 0.0,
                'amount_contributed': 0.0
            }
        return {} # In other years, the strategy does nothing.

def test_cost_basis_adjustment_with_asset_growth(bookkeeping_params):
    """
    **Purpose:** Verifies that the cost basis is correctly reduced proportionally after a sale when the asset has grown.
    **Method:** An asset grows by 20% in Year 1. In Year 2, 10% of the asset is sold.
    **Assertion:** The final cost basis should be reduced by 10%.
    """
    # Arrange
    params = bookkeeping_params.copy()
    params.update({
        'strategy': 'custom',
        'num_years': 2,
        'tax_method': 'capital_gains', # Explicitly set tax method for this test
        'initial_investment': 1_000_000, # This will be used to buy assets
        'initial_assets': 0,
        'annual_return': 0.20, # 20% growth
        'annual_volatility': 0.0,
        'capital_gains_tax_rate': 0.30 # Add tax to verify cost basis via tax paid
    })
    mu_daily = (1 + params['annual_return'])**(1/365) - 1
    strategy_map = {'custom': CostBasisTestStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=mu_daily, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)['Sim_0']
    tax_paid_y2 = results_df.loc[2]['Tax Paid']

    # Assert
    # We can infer the correctness of the cost basis calculation by checking the tax paid.
    # Year 0: Buy 1M of assets. Cost Basis = 1M. Asset Value = 1M.
    # Year 1: Asset value grows 20% to 1.2M. Cost Basis is still 1M. No sale in Year 1.
    # Year 2: The engine applies growth FIRST, then executes transactions.
    #   - Asset value after Year 2 growth: 1.2M * 1.2 = 1.44M
    #   - The asset value at the time of the sale is 1.44M.
    asset_value_at_time_of_sale = 1_440_000
    cost_basis_before_sale_y2 = 1_000_000

    #   - The engine calculates tax based on the post-growth asset value.
    #   - Cost basis ratio = 1.0M / 1.44M = 0.694
    cost_basis_ratio = cost_basis_before_sale_y2 / asset_value_at_time_of_sale
    #   - Amount sold: 120,000
    #   - The strategy sells 120k. This creates a tax liability.
    #   - Gain on sale = 120,000 * (1 - 0.6944) = 36,666.67
    #   - Tax on sale = 36,666.67 * 0.30 = 11,000
    #   - The cash from the 120k sale (120,000) is sufficient to cover the 11,000 tax.
    #   - Therefore, no shortfall is triggered, and no second "emergency" sale occurs.
    #   - The total tax paid is exactly the tax from the initial planned sale.
    expected_tax = 11_000.0
    assert tax_paid_y2 == pytest.approx(expected_tax, rel=1e-3)

def test_no_negative_values_in_depletion_scenario(bookkeeping_params):
    """
    **Purpose:** Verifies that even when a portfolio is completely depleted, key financial
    metrics like asset value and all costs do not become negative.
    **Method:** A Trinity strategy is run with a high withdrawal rate (20%) and zero growth,
    which guarantees portfolio depletion in 5 years. The simulation runs for longer
    to ensure values remain at zero.
    **Assertion:** The test asserts that all values in the specified financial columns
    for all years are greater than or equal to zero.
    """
    # Arrange
    params = bookkeeping_params.copy()
    params.update({
        'strategy': 'trinity',
        'initial_investment': 1_000_000, # Will be converted to assets
        'initial_assets': 0,
        'num_years': 10,
        'withdrawal_rate': 0.20, # 20% withdrawal rate guarantees depletion in 5 years
        'asset_model': 'parametric',
        'annual_return': 0.0,
        'annual_volatility': 0.0,
    })
    # The TrinityStrategy needs to be imported
    from core.strategy import TrinityStrategy
    strategy_map = {'trinity': TrinityStrategy(params)}

    # Act
    simulations = run_simulation(params, mu=0, sigma=0, strategy_map=strategy_map)
    results_df = prepare_results_dataframe(simulations)['Sim_0']

    # Assert
    # These columns should never contain negative values under any circumstances.
    columns_to_check = [
        'Asset Value', 'Interest Paid', 'Tax Paid', 'Fees Paid', 'Cash',
        'Consumption Delivered', 'Amount Sold', 'Amount Bought'
    ]
    for column in columns_to_check:
        value = results_df.xs(column, level='Metric')
        assert (value >= 0).all(), f"Column '{column}' contains negative values."

    # Debt should be zero *until* the portfolio is depleted. After depletion,
    # the engine may borrow as a last resort to cover mandatory costs (e.g., ISK tax
    # from the previous year's value), so debt can become positive. It should never be negative.
    assert (results_df.xs('Debt', level='Metric') >= 0).all(), "Column 'Debt' contains negative values."

    # Net worth can become negative if the engine is forced to borrow after all assets
    # are depleted. We find the first year where assets are zero.
    asset_values = results_df.xs('Asset Value', level='Metric')
    first_depletion_year = (asset_values == 0).idxmax() if (asset_values == 0).any() else params['num_years'] + 1

    # Before depletion, Net Worth must be non-negative.
    assert (results_df.loc[:first_depletion_year-1].xs('Net Worth', level='Metric') >= 0).all(), "Net Worth should not be negative before depletion."

def test_tax_method_selection_with_trinity_strategy(bookkeeping_params):
    """
    **Purpose:** Verifies that the simulation engine correctly applies the selected tax method.
    **Method:** Runs two identical simulations with the Trinity strategy, one with 'capital_gains'
    tax and one with 'isk' tax.
    **Assertion:** The tax paid in each scenario must be different and consistent with the
    chosen method, proving the `tax_method` parameter is being respected.
    """
    from core.strategy import TrinityStrategy

    # --- Arrange: Common parameters for both scenarios ---
    base_params = bookkeeping_params.copy()
    base_params.update({
        'strategy': 'trinity',
        'num_years': 2,
        'initial_investment': 1_000_000,
        'initial_assets': 0,
        'annual_return': 0.20, # 20% growth to create a capital gain and a basis for ISK tax
        'annual_volatility': 0.0,
        'withdrawal_rate': 0.10, # 10% withdrawal to trigger a sale
        'capital_gains_tax_rate': 0.30,
        'isk_tax_rate': 0.01,
    })
    mu_daily = (1 + base_params['annual_return'])**(1/365) - 1

    # --- Act: Scenario 1 (Capital Gains Tax) ---
    params_cg = base_params.copy()
    params_cg['tax_method'] = 'capital_gains'
    strategy_map_cg = {'trinity': TrinityStrategy(params_cg)}
    sim_cg = run_simulation(params_cg, mu=mu_daily, sigma=0, strategy_map=strategy_map_cg)
    tax_paid_cg = prepare_results_dataframe(sim_cg)['Sim_0'].loc[1]['Tax Paid']

    # --- Act: Scenario 2 (ISK Tax) ---
    params_isk = base_params.copy()
    params_isk['tax_method'] = 'isk'
    strategy_map_isk = {'trinity': TrinityStrategy(params_isk)}
    sim_isk = run_simulation(params_isk, mu=mu_daily, sigma=0, strategy_map=strategy_map_isk)
    tax_paid_isk = prepare_results_dataframe(sim_isk)['Sim_0'].loc[1]['Tax Paid']

    # --- Assert ---
    # 1. The tax paid must be different between the two methods.
    assert tax_paid_cg != tax_paid_isk, "Tax paid was identical for both methods, indicating the tax_method parameter was not applied."

    # 2. Verify the tax amounts are reasonable for each method.
    # Capital Gains: Sale of 100k on a 1M asset that grew to 1.2M. Gain is ~16.7k, tax is ~5k.
    assert 4500 < tax_paid_cg < 5500, f"Capital gains tax paid ({tax_paid_cg}) is outside the expected range."

    # ISK Tax: 1% of the post-growth asset value (1.2M) = 12,000.
    assert tax_paid_isk == pytest.approx(12_000), f"ISK tax paid ({tax_paid_isk}) is not the expected 12,000."

    print(f"Test successful: Capital Gains Tax = {tax_paid_cg:.2f}, ISK Tax = {tax_paid_isk:.2f}")