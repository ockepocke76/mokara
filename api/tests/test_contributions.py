
import unittest
import pandas as pd
import numpy as np

from core.simulation import run_simulation
from core.strategy import BaseStrategy
from core.portfolio import Portfolio
from core.stats import calculate_final_statistics

class ContributionStrategy(BaseStrategy):
    """A simple strategy that makes a fixed contribution each year."""
    display_name = "Contribution Strategy"

    @property
    def parameters(self) -> dict:
        return {}  # Test strategy has no configurable parameters

    def __init__(self, params: dict, contribution_amount: float = 0):
        super().__init__(params)
        self.contribution_amount = contribution_amount

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS', 'USE_CASH']

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        initial_investment = self.params.get('initial_investment', 0)
        return {'action': 'BUY_ASSET', 'cash_amount': initial_investment}

    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        return 0.0

    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        return {
            'amount_sold': 0.0,
            'amount_bought': 0.0,
            'debt_increase': 0.0,
            'debt_repayment': 0.0,
            'amount_contributed': self.contribution_amount
        }

class TestContributions(unittest.TestCase):
    def setUp(self):
        self.base_params = {
            'num_simulations': 1,
            'num_years': 5,
            'initial_investment': 100000,
            'initial_assets': 100000,
            'asset_model': 'parametric',
            'annual_return': 0.07,
            'annual_volatility': 0.15,
            'inflation_rate': 0.02,
            'loan_interest_rate': 0.03,
            'asset_management_fee': 0.0,
            'tax_method': 'isk',
            'isk_tax_rate': 0.01,
            'cash_interest_rate': 0.01
        }

    def test_portfolio_handles_contribution(self):
        """Unit test for Portfolio.execute_transactions to handle contributions."""
        params = {**self.base_params, 'initial_investment': 100000, 'initial_assets': 100000}
        portfolio = Portfolio(params)
        strategy_actions = {'amount_contributed': 5000}
        
        # In this isolated test, initial investment is cash. No initial purchase is simulated.
        initial_cash = params['initial_investment']
        
        transaction_results = portfolio.execute_transactions(
            year=1,
            strategy_actions=strategy_actions,
            consumption_drawdown=0,
            asset_value_at_start_of_year=portfolio.asset_value,
            cash_interest=0,
            shortfall_funding_policy=['USE_CASH']
        )
        
        self.assertEqual(transaction_results['amount_contributed'], 5000)
        
        # Calculate expected cash
        tax = portfolio.asset_value * params['isk_tax_rate']
        expected_cash = initial_cash + 5000 - tax
        self.assertAlmostEqual(portfolio.cash, expected_cash, places=2)

    def test_stats_calculation_with_contributions(self):
        """Unit test for stats calculation with contribution data."""
        years = 5
        sims = 2
        metrics = ['Net Worth', 'Amount Contributed', 'Consumption Delivered', 'Debt', 'Asset Value']
        index = pd.MultiIndex.from_product([range(years + 1), metrics], names=['Year', 'Metric'])
        data = np.zeros(((years + 1) * len(metrics), sims))
        results_df = pd.DataFrame(data, index=index, columns=[f'Sim_{i}' for i in range(sims)])
        
        # Set known values
        results_df.loc[(slice(None), 'Net Worth'), :] = 100000
        results_df.loc[(slice(None), 'Amount Contributed'), :] = 1000
        results_df.loc[(0, 'Amount Contributed'), :] = 0

        params = {**self.base_params, 'num_years': years, 'num_simulations': sims, 'initial_investment': 100000}
        stats = calculate_final_statistics(results_df, params)
        
        self.assertEqual(stats['mean_total_contributions'], 5000)
        self.assertEqual(stats['median_total_contributions'], 5000)

    def test_integration_with_simulation(self):
        """Integration test with run_simulation and a contributing strategy."""
        contribution_amount = 2500
        params = {
            **self.base_params, 
            'num_simulations': 1, 
            'num_years': 3,
            'annual_return': 0.0,
            'isk_tax_rate': 0.0,
            'cash_interest_rate': 0.0
        }
        strategy = ContributionStrategy(params, contribution_amount=contribution_amount)
        
        # In the simulation, initial_investment is used to buy assets, so cash starts at 0.
        # We need to provide mu and sigma, even if they are 0.
        sim_results = run_simulation(params, strategy_map={'contribution': strategy}, mu=0, sigma=0)
        
        self.assertEqual(len(sim_results), 1)
        history = sim_results[0].yearly_results
        
        for year_result in history[1:]:
            self.assertEqual(year_result['Amount Contributed'], contribution_amount)
            
        final_cash = history[-1]['Cash']
        total_contributions = contribution_amount * params['num_years']
        self.assertAlmostEqual(final_cash, total_contributions, places=2)

    def test_zero_contribution(self):
        """Test with a strategy that contributes zero."""
        params = {**self.base_params, 'num_simulations': 1, 'num_years': 3}
        strategy = ContributionStrategy(params, contribution_amount=0)
        
        sim_results = run_simulation(params, strategy_map={'contribution': strategy}, mu=0.07/365, sigma=0.15/np.sqrt(365))
        
        history = sim_results[0].yearly_results
        for year_result in history:
            self.assertEqual(year_result['Amount Contributed'], 0)
            
        # Reshape history into a format suitable for stats calculation
        history_df = pd.DataFrame(history).set_index('Year')
        results_df = history_df.unstack().to_frame(name='Sim_0')
        results_df.index.names = ['Metric', 'Year']
        results_df = results_df.swaplevel(0, 1).sort_index()

        # Add other required columns for stats calculation to avoid errors
        for metric in ['Consumption Delivered', 'Debt', 'Asset Value']:
            if (metric, 0) not in results_df.index:
                metric_df = pd.DataFrame(0, index=pd.MultiIndex.from_product([ [metric], history_df.index.unique()]), columns=['Sim_0'])
                metric_df.index.names=['Metric', 'Year']
                results_df = pd.concat([results_df, metric_df]).sort_index()

        stats = calculate_final_statistics(results_df, params)
        self.assertEqual(stats['mean_total_contributions'], 0)
        self.assertEqual(stats['median_total_contributions'], 0)

if __name__ == '__main__':
    unittest.main()
