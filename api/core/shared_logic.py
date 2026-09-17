"""
This module contains shared logic that is used by both the main application
and the background simulation processes. It's crucial for ensuring that
parameter assembly and data preparation are consistent across different
execution contexts.
"""
import logging
from collections import defaultdict
from config import CONFIG
from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
import pandas as pd
import hashlib
import json
import datetime

def assemble_params(ui_params: dict) -> dict:
    """
    Assembles the final, comprehensive simulation parameter dictionary.

    This is a critical function that acts as the "single source of truth" for
    simulation parameters. It merges parameters from three sources in a specific
    order of precedence:
    1.  **Base Configuration (`config.yml`):** The foundational settings.
    2.  **Asset-Specific Configuration (`assets.yml`):** Overrides from the selected asset model.
    3.  **UI Parameters:** The final user-selected values from the sidebar, which take highest precedence.

    This function also handles the "flattening" of nested parameter dictionaries
    (like those in `assets.yml`) into a single, flat dictionary for easy access
    by the simulation engine.

    Args:
        ui_params (dict): A dictionary of parameters selected by the user in the UI.

    Returns:
        dict: A single, flat dictionary containing all parameters for a simulation run.
    """
    logging.info("Assembling final simulation parameters...")
    # --- REFACTOR: Use a more intuitive override order: Base -> Asset -> UI ---
    sim_params = {}

    # 1. Load all base parameters from config.yml by iterating through the structure
    for section, section_config in CONFIG.items():
        if isinstance(section_config, dict):
            for key, param_config in section_config.items():
                if isinstance(param_config, dict) and 'value' in param_config:
                    sim_params[key] = param_config['value']

    # 2. Load asset-specific parameters, overwriting base defaults.
    asset_model_key = ui_params.get('asset_model', CONFIG['simulation']['asset_model']['value'])
    asset_model_config = CONFIG.get('asset_models', {}).get(asset_model_key, {})
    
    if asset_model_config:
        logging.info(f"Adding asset-specific parameters for model: {asset_model_key}")
        asset_specific_params = asset_model_config.get('parameters', {})
        for param_key, param_value in asset_specific_params.items():
            # If the value is a full dictionary (from the config_loader merge), extract the 'value'.
            if isinstance(param_value, dict) and 'value' in param_value:
                sim_params[param_key] = param_value['value']
            else: # Otherwise, it's a simple key-value pair (like local_file_path).
                sim_params[param_key] = param_value
    else:
        logging.warning(f"No configuration found for asset model: {asset_model_key}. Available models: {list(CONFIG.get('asset_models', {}).keys())}")

    # 3. Apply user-selected parameters from the UI, which have the highest precedence.
    sim_params.update(ui_params)

    # --- Add asset metadata for reporting (AFTER ui_params to ensure it's not overwritten) ---
    # This ensures we always use the display_name from assets.yml, not the formatted asset_model key
    sim_params['asset_name'] = asset_model_config.get('display_name', asset_model_key)
    sim_params['ticker_symbol'] = asset_model_config.get('ticker_symbol')  # Optional, None for synthetic models

    logging.debug(f"Final assembled params (first 5 items): {dict(list(sim_params.items())[:5])}")
    return sim_params

def generate_simulation_hash(params: dict) -> str:
    """
    Generates a deterministic SHA-256 hash for a dictionary of parameters.
    Keys are sorted to ensure consistency, and non-deterministic keys are removed.
    """
    # Create a copy to avoid modifying the original dict
    params_copy = params.copy()
    
    # Remove non-deterministic or user-specific keys that should not affect the simulation result
    # 'component_hashes' is excluded because it tracks code versions, not input parameters, and is added after initial hashing.
    # 'custom_strategy_param_defs' is derived metadata.
    for key in ['user_email', 'user_name', 'simulation_name', 'process_key', 'is_prod_env', 'gemini_api_key', 'pdf_report_path', 'component_hashes', 'custom_strategy_param_defs', 'custom_strategy_name', 'custom_strategy_description', 'custom_strategy_ai_description', 'custom_strategy_id']:
        params_copy.pop(key, None)

    # Sort the dictionary by key to ensure a consistent order, then convert to a JSON string
    sorted_params_str = json.dumps(params_copy, sort_keys=True, default=json_serial)
    
    # Create a SHA-256 hash of the sorted JSON string
    return hashlib.sha256(sorted_params_str.encode('utf-8')).hexdigest()

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

def get_info_boxes_text(params: dict, stats: dict) -> dict:
    """
    Generates the text for the summary info boxes based on simulation results.
    """
    from core.simulation_currency import get_simulation_currency
    from core.currency_config import format_currency_amount
    
    # Extract currency from simulation parameters
    currency = get_simulation_currency(params)
    
    # Format monetary values with correct currency
    median_final = format_currency_amount(int(stats.get('median_final_net_worth', 0)), currency, decimals=0)
    median_real = format_currency_amount(int(stats.get('median_real_final_net_worth', 0)), currency, decimals=0)
    p25_final = format_currency_amount(int(stats.get('p25_final_net_worth', 0)), currency, decimals=0)
    p75_final = format_currency_amount(int(stats.get('p75_final_net_worth', 0)), currency, decimals=0)
    
    outcome_items = [
        {"label": "Median Final Net Worth", "value": median_final},
        {"label": f"Median Real Net Worth (Today's {currency})", "value": median_real},
        {"label": "25th Percentile Final Net Worth", "value": p25_final},
        {"label": "75th Percentile Final Net Worth", "value": p75_final},
    ]

    risk_items = [
        {"label": "Chance of Real Profit", "value": f"{stats.get('chance_of_real_profit', 0.0):.1%}"},
    ]
    if params.get('strategy') == 'trinity':
        risk_items.append({"label": "Chance of Ruin (Portfolio Depletion)", "value": f"{stats.get('chance_of_ruin', 0.0):.1%}"})
    else: # BBD
        risk_items.append({"label": "Chance of Ruin (Insolvency)", "value": f"{stats.get('chance_of_ruin', 0.0):.1%}"})
        risk_items.append({"label": "Median Final LTV", "value": f"{stats.get('median_final_ltv', 0.0):.1%}"})
    
    # Psychological stress indicators
    psych_items = [
        {"label": "Time Underwater", "value": f"{stats.get('median_time_underwater', 0):.1f} years"},
        {"label": "Recovery Time", "value": f"{stats.get('median_recovery_time', 0):.1f} years"},
        {"label": "Consecutive Losses (P90)", "value": f"{stats.get('p90_consecutive_declines', 0):.1f} years"},
        {"label": "Severe Drawdowns", "value": f"{stats.get('median_severe_drawdown_count', 0):.1f} events"},
        {"label": "Years Below Initial", "value": f"{stats.get('median_years_below_initial', 0):.1f} years"}
    ]

    return {
        'outcome': outcome_items,
        'risk': risk_items,
        'psychological': psych_items
    }

def prepare_results_dataframe(simulations: list) -> pd.DataFrame:
    """
    Converts a list of SimulationRun objects into a structured pandas DataFrame.
    """
    all_data = {}
    monte_carlo_counter = 0
    for i, sim_result in enumerate(simulations):
        # Determine the column name based on the simulation type
        if sim_result.metadata.get('type') == 'backtest':
            col_name = 'Backtest'
        else: # Default to 'monte_carlo'
            col_name = f"Sim_{monte_carlo_counter}"
            monte_carlo_counter += 1

        # The `yearly_results` is a list of dictionaries. We first convert this
        # into a DataFrame, setting the 'Year' as the index.
        df = pd.DataFrame(sim_result.yearly_results).set_index('Year')

        # We need to stack this to create a multi-index Series (Year, Metric).
        # This matches the format expected by downstream functions like `calculate_final_statistics`.
        all_data[col_name] = df.stack()

    if not all_data:
        return pd.DataFrame()
    
    results_df = pd.concat(all_data, axis=1)
    # --- FIX: Explicitly name the stacked level 'Metric'. ---
    # The .stack() operation creates an unnamed level from the columns. Naming it here
    # prevents the "KeyError: 'Level Metric not found'" during the .unstack() operation later.
    results_df.index.names = ['Year', 'Metric']
    return results_df