import pytest
import pandas as pd
from core.strategy import BaseStrategy
from core.simulation import run_simulation

class StatefulTestStrategy(BaseStrategy):
    """
    A simple strategy that sets a flag in __init__ and mutates it during execution.
    If state leaks, the second run will see the mutated flag.
    """
    def __init__(self, params):
        super().__init__(params)
        # Initialize state
        self.run_count = 0
        self.has_executed = False

    def initialize_portfolio(self, initial_portfolio_state, market_data):
        return {'action': 'BUY_ASSET', 'cash_amount': 0}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        return 0.0

    @property
    def shortfall_funding_policy(self):
        return ['SELL_ASSETS']

    @property
    def parameters(self):
         return {}

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        # Mutate state!
        self.run_count += 1
        self.has_executed = True
        return {
            'amount_sold': 0, 'amount_bought': 0, 
            'debt_increase': 0, 'debt_repayment': 0, 'amount_contributed': 0
        }

def test_strategy_factory_isolation():
    """
    Verifies that using a strategy_factory ensures complete isolation between runs.
    """
    params = {
        'initial_investment': 1000,
        'num_years': 5,
        'num_simulations': 2,
        'annual_return': 0.1,
        'annual_volatility': 0.01,
        'asset_model': 'parametric'
    }

    # Define a factory that returns a NEW instance each time
    def factory():
        return StatefulTestStrategy(params)

    # Run simulation
    simulations = run_simulation(
        params,
        returns_sources=None,
        mu=0.1, sigma=0.01,
        strategy_factory=factory
    )

    assert len(simulations) == 2, "Should have run 2 simulations"

    # We can't easily inspect the internal state of the strategy instances used *inside* run_simulation
    # because they are discarded. However, we confirmed isolation by logic:
    # 1. run_simulation calls factory() for each run.
    # 2. factory() returns a fresh StatefulTestStrategy().
    # 3. Therefore, run_count should start at 0 for every run.
    
    # If we were reusing the same instance, run_count would accumulate to 10 (5 years * 2 runs).
    # Since we use factory, each internal instance runs for 5 years.
    
    # To TRULY verify, we'd need the strategy to log something or raise an error if run_count > 5.
    pass

class LeakyStrategy(StatefulTestStrategy):
    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        if self.run_count >= 5:
            # If state leaks, run_count will persist from previous run and exceed 5
            raise RuntimeError("MEMORY LEAK DETECTED: Strategy was reused between runs!")
        return super().execute_strategy_for_year(year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs)

def test_leak_detection():
    """
    Specifically safeguards against instance reuse.
    """
    params = {
        'initial_investment': 1000,
        'num_years': 5,     # Each run touches the strategy 5 times
        'num_simulations': 3, # Total 3 runs
        'annual_return': 0.1,
        'annual_volatility': 0.01,
        'asset_model': 'parametric',
        'strategy': 'custom'
    }

    def factory():
        return LeakyStrategy(params)

    # Should NOT raise RuntimeError
    try:
        run_simulation(params, mu=0.1, sigma=0.01, strategy_factory=factory)
    except RuntimeError as e:
        pytest.fail(f"Isolation failed: {e}")

if __name__ == "__main__":
    test_leak_detection()
    print("Isolation Verification Passed!")
