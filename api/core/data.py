import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sys

# --- Robust Path Configuration ---
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from db.regeneration_db import load_asset_data_from_cache, save_asset_data_to_cache
from simulation import generate_synthetic_bootstrap_data
from core.stats import calculate_historical_mu_sigma

def _generate_asset_key(params: dict) -> str:
    """Generates a unique, deterministic key for an asset configuration."""
    model = params.get('asset_model', 'unknown')
    
    if 'parametric' in model:
        # For parametric models, the key depends on the final, assembled parameters.
        # The `params` dict is already flattened and contains the correct values.
        ret_val = params.get('annual_return', 0.0)
        vol_val = params.get('annual_volatility', 0.0)
        
        ret = f"{ret_val:.4f}"
        vol = f"{vol_val:.4f}"
        num_years = params.get('num_years', 0)
        return f"{model}_ret_{ret}_vol_{vol}_yrs_{num_years}"
    elif model == 'bootstrap_synthetic':
        # For synthetic bootstrap, key depends on all generation parameters
        key_parts = [str(params.get(k, '')) for k in ['synthetic_data_years', 'annual_return', 'annual_volatility']]
        threshold = params.get('return_threshold_rate')
        if threshold is None: threshold = 'none'
        return f"bootstrap_synthetic_{'_'.join(key_parts)}_thresh_{threshold}"
    else:
        # For bootstrap models, the key must include the return threshold.
        threshold = params.get('return_threshold_rate')
        # Convert None to 'none' for a consistent key, but keep numerical values.
        if threshold is None: threshold = 'none'
        # --- FIX: Prevent double-prefixing for bootstrap models ---
        if model.startswith('bootstrap_'):
            return f"{model}_thresh_{threshold}"
        return f"bootstrap_{model}_thresh_{threshold}"

def _slice_data_by_date_params(data_dict: dict, params: dict) -> dict:
    """
    Slices the data in the data_dict based on start_date, end_date, and num_years_backtest.
    This function is called *after* the full dataset has been loaded and processed.
    """
    logging.debug("Slicing data based on date parameters...")

    # --- Part A: Establish the "Available Window" ---
    # NEW: Prioritize dynamic bootstrap dates from UI if available
    start_date_from_ui = params.get('bootstrap_start_date')
    end_date_from_ui = params.get('bootstrap_end_date')

    if start_date_from_ui and end_date_from_ui:
        logging.debug(f"Using dynamic bootstrap date range from UI: {start_date_from_ui} to {end_date_from_ui}")
        start_date_str = start_date_from_ui
        end_date_str = end_date_from_ui
    else:
        # Fallback to static dates from assets.yml
        start_date_str = params.get('start_date', "earliest_available")
        end_date_str = params.get('end_date', "latest_available")
        logging.debug(f"No UI bootstrap dates found. Using config dates: {start_date_str} to {end_date_str}")

    # Use a reference series with a complete index to determine date boundaries
    reference_series = data_dict['prices']

    # Handle different date input types (string, date object, or special keyword)
    # Ensure we don't pass dictionaries or other invalid types to pd.to_datetime
    if start_date_str == "earliest_available" or start_date_str is None:
        slice_start = reference_series.index.min()
    elif isinstance(start_date_str, (dict, list)):
        # Invalid type - fall back to earliest
        logging.warning(f"Invalid start_date type: {type(start_date_str)}. Using earliest available.")
        slice_start = reference_series.index.min()
    else:
        # Convert string or date object to datetime
        slice_start = pd.to_datetime(start_date_str)
    
    if end_date_str == "latest_available" or end_date_str is None:
        slice_end = reference_series.index.max()
    elif isinstance(end_date_str, (dict, list)):
        # Invalid type - fall back to latest
        logging.warning(f"Invalid end_date type: {type(end_date_str)}. Using latest available.")
        slice_end = reference_series.index.max()
    else:
        # Convert string or date object to datetime
        slice_end = pd.to_datetime(end_date_str)
    
    logging.debug(f"Slicing data from {slice_start.date()} to {slice_end.date()}")

    # --- Part B: Apply num_years_backtest override if specified ---
    # This should NOT apply if we are using the UI dates, as the UI already handles this logic.
    if not (start_date_from_ui and end_date_from_ui):
        num_years_backtest = params.get('num_years_backtest')
        if num_years_backtest and isinstance(num_years_backtest, int) and num_years_backtest > 0:
            # Calculate the new start date from the end of the "Available Window"
            backtest_start_date = slice_end - pd.DateOffset(years=num_years_backtest)
            # The effective start date is the later of the original slice_start and the new backtest_start_date
            slice_start = max(slice_start, backtest_start_date)
            logging.debug(f"Applying 'num_years_backtest' of {num_years_backtest}. New effective start date: {slice_start.date()}")

    # Create a copy of the data_dict to modify
    sliced_data_dict = data_dict.copy()

    # Slice all pandas objects in the dictionary
    for key, value in sliced_data_dict.items():
        if isinstance(value, (pd.Series, pd.DataFrame)):
            # Use .loc for safe slicing, ensuring we don't get KeyErrors for out-of-bounds dates
            sliced_data_dict[key] = value.loc[slice_start:slice_end]

    # --- Part C: Recalculate mu and sigma based on the sliced data ---
    # This is critical for the accuracy of parametric models and historical metrics.
    final_prices = sliced_data_dict.get('prices')
    if final_prices is not None and not final_prices.empty:
        mu, sigma = calculate_historical_mu_sigma(final_prices)
        sliced_data_dict['mu'] = mu
        sliced_data_dict['sigma'] = sigma
        logging.debug(f"Recalculated mu and sigma on sliced data. New mu: {mu:.6f}, New sigma: {sigma:.6f}")
    else:
        # If there are no prices after slicing, reset mu and sigma
        sliced_data_dict['mu'] = 0.0
        sliced_data_dict['sigma'] = 0.0
        logging.warning("Prices are empty after slicing. mu and sigma set to 0.")

    # --- Final Integrity Check ---
    # Ensure no empty DataFrames are returned, which could cause downstream errors.
    for key, value in sliced_data_dict.items():
        if isinstance(value, (pd.Series, pd.DataFrame)) and value.empty:
            logging.error(f"Data slicing resulted in an empty DataFrame/Series for key '{key}'. "
                          f"Check date ranges: {slice_start.date()} to {slice_end.date()}. "
                          f"Asset: {params.get('asset_name', 'N/A')}")
            return None # Abort if any crucial data is now empty

    return sliced_data_dict

def load_and_prepare_data(params):
    """
    Loads or generates asset data based on the selected asset_model.
    This function is the single source of truth for data preparation.
    """
    data_df = None
    asset_key = _generate_asset_key(params)
    logging.debug(f"Generated asset key: {asset_key}")

    # --- NEW: Add a flag to disable caching for testing purposes ---
    disable_cache = params.get('_disable_cache', False)

    # 1. Check cache first
    if not disable_cache:
        cached_data = load_asset_data_from_cache(asset_key)
        if cached_data:
            logging.debug(f"CACHE HIT for asset key '{asset_key}'. Using cached data.")
            # --- NEW LOGIC: Slice the data *after* loading from cache ---
            sliced_data = _slice_data_by_date_params(cached_data, params)
            if sliced_data is None:
                logging.error("Slicing cached data resulted in an error. Aborting.")
                return None
            return sliced_data

    logging.debug(f"CACHE MISS for asset key '{asset_key}'. Loading/generating new data.")
    
    asset_model = params['asset_model']
    
    
    # Get asset name from params (loaded from assets.yml via config system)
    asset_name = params.get('display_name', asset_model.replace('_', ' ').title())

    if asset_model in ['parametric', 'parametric_60_40']:
        logging.debug(f"--- HANDLING PARAMETRIC MODEL: {asset_model} ---")
        mu_daily = (1 + params['annual_return'])**(1/365) - 1
        sigma_daily = params['annual_volatility'] / np.sqrt(365)

        # Generate one example history for plotting, ensuring enough data for rolling calcs
        num_days_for_plot = (365 * params['num_years']) + 1
        dates = pd.date_range(end=datetime.now(), periods=num_days_for_plot, freq='D')
        synthetic_daily_returns = np.random.normal(mu_daily, sigma_daily, len(dates))
        daily_returns_series = pd.Series(synthetic_daily_returns, index=dates)
        initial_price = 20000
        example_prices = pd.Series(initial_price * (1 + daily_returns_series).cumprod(), name="Close")
        
        daily_returns_for_plot = example_prices.pct_change(fill_method=None).dropna() # Now has 365*N days
        rolling_annual_returns_for_plot = daily_returns_for_plot.rolling(window=365).apply(lambda x: (1 + x).prod() - 1).dropna() * 100

        logging.debug(f"Using theoretical parameters for simulation: Daily Mu={mu_daily:.6f}, Daily Sigma={sigma_daily:.6f}")
        data_dict = {
            "asset_name": asset_name, 
            "prices": example_prices, 
            "mu": mu_daily, 
            "sigma": sigma_daily,
            "yearly_returns": None,
            "daily_returns": daily_returns_for_plot,
            "rolling_annual_returns": rolling_annual_returns_for_plot
        }
        if not disable_cache:
            save_asset_data_to_cache(asset_key, data_dict)
        # --- NEW LOGIC: Slice the newly generated data before returning ---
        sliced_data = _slice_data_by_date_params(data_dict, params)
        if sliced_data is None: return None
        return sliced_data


    elif 'bootstrap' in asset_model:
        if asset_model == 'bootstrap_synthetic':
            data_dict = generate_synthetic_bootstrap_data(params)
            if not disable_cache:
                save_asset_data_to_cache(asset_key, data_dict)
            return data_dict

        # --- Path Correction for Cloud Deployment ---
        base_path = Path(__file__).parent.parent
        file_path = params['local_file_path']
        date_col = params['date_column']
        price_col = params['price_column']

        try:
            logging.debug(f"--- LOADING LOCAL CSV DATA ({file_path}) ---")
            data_df = pd.read_csv(base_path / file_path)

            if pd.api.types.is_numeric_dtype(data_df[date_col]):
                data_df[date_col] = pd.to_datetime(data_df[date_col], unit='s')
            else:
                data_df[date_col] = pd.to_datetime(data_df[date_col])

            data_df.set_index(date_col, inplace=True)

            # Use ticker from params (loaded from assets.yml)
            ticker = params.get('ticker_symbol')
            if ticker and 'ticker' in data_df.columns:
                data_df = data_df[data_df['ticker'] == ticker]

        except FileNotFoundError:
            logging.error(f"File '{file_path}' not found.")
            return None
        except Exception as e:
            logging.error(f"An error occurred while loading data: {e}", exc_info=True)
            return None
    
    if data_df is None or data_df.empty:
        logging.error("Could not load data. Aborting.")
        return None

    logging.info("--- Processing full dataset for caching ---")
    # --- REFACTOR: Process the ENTIRE dataset first, before any slicing ---
    # This ensures the cache stores the complete, processed data.
    prices = data_df[price_col]

    # --- FIX: Calculate mu and sigma from the ORIGINAL, non-resampled prices. ---
    # This prevents the dilution of statistics by zero-return weekend days that are
    # introduced by the `resample('D').ffill()` operation.
    mu, sigma = calculate_historical_mu_sigma(prices)

    daily_prices = prices.resample('D').last().ffill()
    daily_returns = daily_prices.pct_change().dropna()
    yearly_prices = daily_prices.resample('YE').last()
    yearly_returns = yearly_prices.pct_change().dropna() * 100
    rolling_annual_returns = daily_returns.rolling(window=365).apply(lambda x: (1 + x).prod() - 1).dropna() * 100

    # --- FIX: Apply return threshold directly to the prepared data ---
    # This ensures that all downstream uses (simulation, plotting) see the capped returns.
    threshold = params.get('return_threshold_rate')
    if threshold is not None and pd.api.types.is_number(threshold):
        logging.info(f"Applying return threshold of {threshold:.2%} to rolling annual returns.")
        rolling_annual_returns = rolling_annual_returns.clip(upper=threshold * 100)

    
    data_dict = {
        "asset_name": asset_name, "prices": prices, "daily_returns": daily_returns, 
        "mu": mu, "sigma": sigma, "yearly_returns": yearly_returns, 
        "rolling_annual_returns": rolling_annual_returns
    }
    if not disable_cache:
        save_asset_data_to_cache(asset_key, data_dict)

    # --- NEW LOGIC: Slice the newly generated data before returning ---
    sliced_data = _slice_data_by_date_params(data_dict, params)
    if sliced_data is None: return None
    return sliced_data


def prepare_simulation_inputs(data_dict: dict, asset_model: str) -> dict:
    """
    Extracts and formats simulation inputs (returns_sources, mu, sigma) from the loaded data dictionary.
    
    This function consolidates the logic previously duplicated in background_tasks.py,
    ensuring both the main simulation engine and the sandbox use the exact same input preparation.
    
    Args:
        data_dict: The dictionary returned by load_and_prepare_data().
        asset_model: The asset model string (e.g., 'parametric', 'bootstrap_sp500').
        
    Returns:
        A dictionary containing:
        - returns_sources: Dict with 'monte_carlo' and 'backtest' return series.
        - mu: Daily mean return.
        - sigma: Daily volatility.
    """
    returns_sources = {'monte_carlo': None, 'backtest': None}
    
    if data_dict is None:
        return {'returns_sources': returns_sources, 'mu': 0.0, 'sigma': 0.0}

    # Extract statistics
    mu = data_dict.get('mu', 0.0)
    sigma = data_dict.get('sigma', 0.0)

    if 'bootstrap' in asset_model:
        # The source for Monte Carlo sampling is the rolling annual returns.
        if data_dict.get('rolling_annual_returns') is not None:
             returns_sources['monte_carlo'] = data_dict['rolling_annual_returns'] / 100.0
        
        # The source for the backtest is the daily returns, compounded annually.
        # This correctly calculates the historical calendar year returns.
        if data_dict.get('daily_returns') is not None:
            returns_sources['backtest'] = data_dict['daily_returns'].resample('YE').apply(lambda x: (1 + x).prod() - 1)
            
    return {
        'returns_sources': returns_sources,
        'mu': mu,
        'sigma': sigma
    }