import numpy as np
import logging
import pandas as pd
from datetime import datetime
from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
from core.portfolio import Portfolio

class SimulationResult:
    """A simple class to hold the results of a single simulation run."""
    def __init__(self, yearly_results, annual_returns, metadata):
        self.yearly_results = yearly_results
        self.annual_returns = annual_returns
        self.metadata = metadata


STATE_KEY_PREFIX = 'state_'


def strategy_state_from_actions(strategy_actions: dict) -> dict:
    """Decision-state a strategy chose to expose for the year (`state_*` keys
    on its action dict), coerced to floats so they aggregate like every other
    yearly metric. Non-numeric or non-finite values are dropped."""
    state = {}
    for key, value in (strategy_actions or {}).items():
        if not key.startswith(STATE_KEY_PREFIX) or isinstance(value, str):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            state[key] = number
    return state

def run_simulation(params, returns_sources=None, mu=None, sigma=None, progress_queue=None, strategy_map=None, progress_range=(0.0, 1.0), strategy_factory=None):
    """Runs a Monte Carlo simulation based on the provided parameters.
    
    Args:
        params: Simulation parameters
        returns_sources: Historical return data sources
        mu: Mean return (for parametric models)
        sigma: Volatility (for parametric models)
        progress_queue: Queue for progress updates
        strategy_map: Dict with single instantiated strategy (legacy approach)
        progress_range: Range for progress reporting
        strategy_factory: Optional callable that returns a fresh strategy instance.
                         If provided, a new instance is created for each simulation,
                         making evaluation immune to reset() implementation bugs.
    """
    logging.info(f"Starting simulation run with {params.get('num_simulations', 0)} iterations.")
    
    # Determine strategy source - factory or legacy map
    use_factory = strategy_factory is not None
    
    if use_factory:
        # Create one instance just for initialization/validation
        strategy_instance = strategy_factory()
    else:
        # Legacy: use pre-instantiated strategy from map
        strategy_key = next(iter(strategy_map))
        strategy_instance = strategy_map[strategy_key]
        if not strategy_instance:
            raise ValueError(f"Unknown strategy: {params.get('strategy')}")

    # --- FIX: Set the default tax method from the strategy if not already specified. ---
    if 'tax_method' not in params:
        params['tax_method'] = strategy_instance.default_tax_method

    all_simulations = []
    return_scenarios = []

    # --- Phase 1: Generate all return scenarios upfront ---
    # 1a. Add the historical backtest scenario if applicable.
    if returns_sources and returns_sources.get('backtest') is not None:
        historical_annual_returns = returns_sources['backtest']
        num_backtest_years = min(params['num_years'], len(historical_annual_returns))
        # --- FIX: Use the LATEST `num_years` of historical data, not the earliest. ---
        # This provides a more relevant, recent backtest.
        backtest_returns = historical_annual_returns.iloc[-num_backtest_years:].tolist()
        return_scenarios.append((backtest_returns, {'type': 'backtest'}))

    # 1b. Add all Monte Carlo scenarios.
    num_sims = params['num_simulations']
    monte_carlo_source = returns_sources.get('monte_carlo') if returns_sources else None
    for _ in range(num_sims):
        annual_returns_for_sim = []
        if 'bootstrap' in params.get('asset_model', '') and monte_carlo_source is not None and not monte_carlo_source.empty:
            annual_returns_for_sim = np.random.choice(monte_carlo_source.values, size=params['num_years']).tolist()
        elif params.get('asset_model') in ['parametric', 'parametric_60_40']:
            # --- FIX: Use the correct mathematical formulation for log-normal returns. ---
            # The user provides an arithmetic mean return. We convert this to the mean of the log-returns.
            log_mu_annual = np.log(1 + params['annual_return']) - 0.5 * (params['annual_volatility']**2)
            log_sigma_annual = params['annual_volatility']
            
            log_returns_matrix = np.random.normal(log_mu_annual, log_sigma_annual, params['num_years'])
            annual_returns_for_sim = (np.exp(log_returns_matrix) - 1).tolist()

        return_scenarios.append((annual_returns_for_sim, {'type': 'monte_carlo'}))

    # --- Phase 2: Unified Simulation Loop ---
    # --- FIX: The total number of scenarios is the number of Monte Carlo sims + 1 for the backtest (if present). ---
    total_scenarios = len(return_scenarios)
    report_interval = max(1, total_scenarios // 100)

    for i, (annual_returns_for_sim, metadata) in enumerate(return_scenarios):
        if (i + 1) % 1000 == 0:  # Log to file less frequently
            logging.info(f"Running simulation #{i+1}...")

        if progress_queue and (i % report_interval == 0 or i == total_scenarios - 1):
            local_progress = (i + 1) / total_scenarios
            progress = progress_range[0] + local_progress * (progress_range[1] - progress_range[0])
            status_text = f"Running scenario {i+1} of {total_scenarios}..."
            progress_queue.put((progress, status_text))

        # Get strategy for this simulation
        if use_factory:
            # Create fresh instance - immune to reset() bugs
            strategy = strategy_factory()
        else:
            # Legacy: reuse instance with reset
            strategy = strategy_instance
            strategy.reset()
 
        portfolio = Portfolio(params)

        # --- "Year 0" Initialization Phase ---
        initial_portfolio_state = portfolio.get_state()
        initial_actions = strategy.initialize_portfolio(initial_portfolio_state, pd.DataFrame())
        amount_bought, debt_taken = portfolio.apply_initial_strategy(initial_actions)

        # Record Year 0 state
        portfolio.record_yearly_snapshot(
            year=0,
            transaction_results={'amount_bought': amount_bought, 'debt_change': debt_taken},
            cash_interest=0
        )

        # The simulation runs for the number of years specified in its return sequence.
        for year_index, annual_return in enumerate(annual_returns_for_sim):
            year = year_index + 1

            # --- FIX: Apply growth first, then capture the asset value ---
            # The asset value after growth is needed for correct cost basis ratio calculation.
            # Cost basis ratio = cost_basis / asset_value_after_growth
            portfolio.apply_asset_growth(annual_return)
            asset_value_at_start_of_year = portfolio.asset_value

            cash_interest = portfolio.accrue_and_apply_cash_interest()
            portfolio_state = portfolio.get_state()
            portfolio_history = portfolio.history
            mandatory_costs = portfolio.calculate_mandatory_costs(proposed_sale=0.0)

            # --- FIX: Pass the correct cost basis to the strategy ---
            # The strategy needs the portfolio's current cost basis to make informed decisions,
            # especially if it needs to estimate tax implications itself.
            portfolio_state['cost_basis'] = portfolio.cost_basis
            # --- FIX: Convert history keys to snake_case for the strategy ---
            # The strategy (especially AI-generated) expects 'consumption_delivered' (snake_case),
            # but the portfolio history stores 'Consumption Delivered' (Title Case) for reporting.
            strategy_friendly_history = [
                {k.lower().replace(' ', '_'): v for k, v in record.items()}
                for record in portfolio_history
            ]

            consumption_drawdown = strategy.get_annual_drawdown(year, portfolio_state, strategy_friendly_history)
            
            strategy_actions = strategy.execute_strategy_for_year(
                year, portfolio_state, strategy_friendly_history, consumption_drawdown, mandatory_costs=mandatory_costs
            )
            shortfall_policy = strategy.shortfall_funding_policy

            transaction_results = portfolio.execute_transactions(
                year, strategy_actions, consumption_drawdown, asset_value_at_start_of_year,
                0, # Cash interest is now calculated after transactions.
                shortfall_policy
            )

            portfolio.record_yearly_snapshot(year, transaction_results, cash_interest,
                                             strategy_state=strategy_state_from_actions(strategy_actions))

        all_simulations.append(SimulationResult(yearly_results=portfolio.history, annual_returns=annual_returns_for_sim, metadata=metadata))

    logging.info("Simulation run finished.")
    return all_simulations

def generate_synthetic_bootstrap_data(params):
    """
    Generates a synthetic dataset for use with the bootstrap simulation method.
    This is useful for testing bootstrap features in a controlled environment.
    """
    logging.info("--- GENERATING SYNTHETIC BOOTSTRAP DATA ---")
    
    # Parameters from config
    num_years_history = params.get('synthetic_data_years', 50)
    annual_return = params['annual_return']
    annual_volatility = params['annual_volatility']
    initial_price = 1000

    # Convert to daily parameters
    mu_daily = (1 + annual_return)**(1/365) - 1
    sigma_daily = annual_volatility / np.sqrt(365)

    # Generate the price history
    # Generate one extra day to ensure the rolling window has enough data after pct_change()
    num_days = (365 * num_years_history) + 1
    dates = pd.date_range(end=datetime.now(), periods=num_days, freq='D')
    daily_returns_sim_series = pd.Series(np.random.normal(mu_daily, sigma_daily, num_days))
    prices = pd.Series(initial_price * (1 + daily_returns_sim_series).cumprod(), index=dates, name="Close")

    # Calculate the necessary return series from the generated prices
    daily_returns = prices.pct_change(fill_method=None).dropna()
    yearly_prices = prices.resample('YE').last()
    yearly_returns = yearly_prices.pct_change(fill_method=None).dropna() * 100
    
    # Use a more robust and efficient method for rolling returns calculation
    log_returns = np.log(1 + daily_returns)
    rolling_annual_returns = (np.exp(log_returns.rolling(window=365).sum()) - 1).dropna() * 100
    
    return {
        "asset_name": params.get('display_name', "Synthetic Bootstrap"),
        "prices": prices, "daily_returns": daily_returns,
        "mu": daily_returns.mean(), "sigma": daily_returns.std(),
        "yearly_returns": yearly_returns, "rolling_annual_returns": rolling_annual_returns,
        "start_date": dates.min().strftime('%Y-%m-%d')
    }