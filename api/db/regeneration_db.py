import pandas as pd
import io
import json
import pickle
import logging 
# --- FIX: Use the global `db` object instead of a hardcoded Snowflake connection ---
# This makes the caching functions dialect-aware.
from .database import db

def _load_dataframe_from_db(connection, results_id, data_key):
    """Helper to load, decompress, and deserialize a DataFrame from the DB."""
    logging.debug(f"Loading DataFrame '{data_key}' for results_id {results_id} from database.")
    try:
        # Use the global db object to get the correct query syntax
        sql = db.queries.LOAD_SIMULATION_RESULTS_DATA
        
        # Use standard connection interface - works with ALL database types
        cursor = connection.cursor()
        cursor.execute(sql, {"results_id": results_id, "data_key": data_key})
        result = cursor.fetchone()

        if result and result[0]:
            buffer = io.BytesIO(result[0])
            df = pd.read_parquet(buffer)
            # If it was originally a Series (e.g., final_net_worths), convert back from single-column DataFrame
            if data_key == 'final_net_worths' and isinstance(df, pd.DataFrame) and df.shape[1] == 1:
                df = df.iloc[:, 0]

            logging.debug(f"Successfully loaded DataFrame '{data_key}' for results_id {results_id}.")
            return df
        else:
            logging.warning(f"No DataFrame found for data_key '{data_key}' and results_id {results_id}.")
            return None
    except Exception as e:
        logging.error(f"Failed to load DataFrame for data_key '{data_key}': {e}", exc_info=True)
        return None

def _load_dict_from_db(connection, results_id, data_key):
    """Helper to load and deserialize a dictionary (potentially with pandas objects) from the DB."""
    logging.debug(f"Loading dictionary '{data_key}' for results_id {results_id} from database.")
    try:
        # Use the global db object to get the correct query syntax
        sql = db.queries.LOAD_SIMULATION_RESULTS_DATA
        
        # Use standard connection interface - works with ALL database types
        cursor = connection.cursor()
        cursor.execute(sql, {"results_id": results_id, "data_key": data_key})
        result = cursor.fetchone()

        if result and result[0]:
            data_dict = pickle.loads(result[0])
            logging.debug(f"Successfully loaded dictionary '{data_key}' for results_id {results_id}.")
            return data_dict
        else:
            logging.warning(f"No dictionary found for data_key '{data_key}' and results_id {results_id}.")
            return None
    except Exception as e:
        logging.error(f"Failed to load dictionary for data_key '{data_key}': {e}", exc_info=True)
        return None

def save_asset_data_to_cache(asset_key: str, data_dict: dict):
    """Saves the input data dictionary for a specific asset to the ASSET_DATA_CACHE table."""
    # Use the global db object to get a connection for the correct dialect.
    conn = db.get_connection()
    if not conn:
        logging.error("Cannot save asset data to cache, no database connection.")
        return

    try:
        data_blob = pickle.dumps(data_dict)
        # The SAVE_ASSET_DATA_CACHE query handles both INSERT and UPDATE (MERGE/INSERT OR REPLACE).
        sql = db.queries.SAVE_ASSET_DATA_CACHE
        cursor = conn.cursor()
        cursor.execute(sql, {"asset_key": asset_key, "data_blob": data_blob})
        conn.commit()
        logging.debug(f"Successfully saved/updated asset data for key '{asset_key}' in cache.")
    except Exception as e:
        logging.error(f"Failed to save asset data for key '{asset_key}' to cache: {e}", exc_info=True)
    finally:
        db.release_connection(conn)

def load_asset_data_from_cache(asset_key: str) -> dict | None:
    """Loads the input data dictionary for a specific asset from the ASSET_DATA_CACHE table."""
    # Use the global db object to get a connection for the correct dialect.
    conn = db.get_connection()
    if not conn:
        logging.error("Cannot load asset data from cache, no database connection.")
        return None

    try:
        cursor = conn.cursor()
        sql = db.queries.LOAD_ASSET_DATA_CACHE
        cursor.execute(sql, {"asset_key": asset_key})
        result = cursor.fetchone()

        if result and result[0]:
            data_dict = pickle.loads(result[0])
            logging.debug(f"Successfully loaded asset data for key '{asset_key}' from cache.")
            return data_dict
        else:
            logging.debug(f"No asset data found for key '{asset_key}' in cache.")
            return None
    except Exception as e:
        logging.error(f"Failed to load asset data for key '{asset_key}' from cache: {e}", exc_info=True)
        return None
    finally:
         db.release_connection(conn)

def get_regeneration_data(simulation_hash, record_timing_func=None):
    """
    Fetches all necessary data from the database to regenerate a report for a given simulation_hash.

    This function connects to the database and retrieves:
    - The original simulation parameters.
    - The full final statistics dictionary.
    - All pre-calculated DataFrames (e.g., percentile paths, sampled paths).
    - A `record_timing_func` can be passed to log performance metrics.
    - The AI-generated analysis text.

    Returns:
        A dictionary containing all the re-hydrated data, or None if a critical piece of data is missing.
    """
    logging.debug(f"Fetching all necessary data for regenerating simulation hash: {simulation_hash[:10]}...")
    # --- FIX: Use the global db object for the connection, not the Snowflake-specific one ---
    # This makes the regeneration process dialect-aware.
    # The `get_process_safe_db_connection` is for Snowflake; `db.get_connection` is for the active dialect.
    conn = db.get_connection()

    try:
        if record_timing_func:
            record_timing_func("DB Connection Established")
        # --- FIX: Fetch the complete parameter snapshot directly from the database. ---
        # The `get_simulation_details` function now returns the fully assembled parameters
        # that were saved at the time of the simulation run. This eliminates the need
        # to call `assemble_params` here, fixing the regeneration bug.
        params, stats, results_id = db.get_simulation_details(simulation_hash)
        if not params or not stats:
            logging.error(f"Could not find combined data for simulation hash: {simulation_hash[:10]}.... Aborting regeneration.")
            return None

        # The get_simulation_details function now merges gemini_content into stats.
        # We extract the AI content from the stats blob.
        gemini_content = {
            'analysis': stats.get('analysis', ''),
            'main_outcome': stats.get('main_outcome', ''),
            'bottom_line': stats.get('bottom_line', '')
        }

        # --- FIX: Convert median time-series data from dicts back to pandas Series ---
        # The data is stored as a dict in the JSON blob, not a list.
        if 'median_drawdown_values' in stats and isinstance(stats['median_drawdown_values'], dict):
            stats['median_drawdown_values'] = pd.Series(stats['median_drawdown_values'])
        if 'median_debt_values' in stats and isinstance(stats['median_debt_values'], dict):
            stats['median_debt_values'] = pd.Series(stats['median_debt_values'])
        # --- FIX: Re-hydrate acf_data from list to numpy array ---
        # The acf_values are stored as a list in JSON but the plotting function expects a numpy array.
        if 'acf_data' in stats and isinstance(stats['acf_data'], dict):
            if 'acf_values' in stats['acf_data'] and isinstance(stats['acf_data']['acf_values'], list):
                import numpy as np
                stats['acf_data']['acf_values'] = np.array(stats['acf_data']['acf_values'])
        # --- FIX: Re-hydrate drawdown_data from dictionary to pandas Series with DatetimeIndex ---
        # The data is now stored as a dict {date_str: value} to preserve the index.
        if 'drawdown_data' in stats and isinstance(stats['drawdown_data'], dict):
            drawdown_dict = stats['drawdown_data']
            # Convert string keys back to datetime objects for the index.
            stats['drawdown_data'] = pd.Series(drawdown_dict.values(), index=pd.to_datetime(list(drawdown_dict.keys())))

        if record_timing_func:
            record_timing_func("Fetch: Combined Data")

        # 4. Load all pre-calculated DataFrames
        data_keys_to_load = [
            ('net_worth_percentile_paths', 'df'),
            ('asset_percentile_paths', 'df'),
            ('final_net_worths_hist', 'dict'), # Changed from 'final_net_worths' (df) to 'final_net_worths_hist' (dict)
            ('sampled_paths', 'df'),
            ('average_results_df', 'df'),
            ('median_yearly_results_df', 'df'),
            ('backtest_path', 'df'), # Load the backtest path as a DataFrame
            ('evaluation_data', 'dict'), # Cached strategy evaluation data
        ]
        precalculated_data = {}
        for key, data_type in data_keys_to_load:
            loader_func = _load_dataframe_from_db if data_type == 'df' else _load_dict_from_db # noqa
            precalculated_data[key] = loader_func(conn, results_id, key)
            if record_timing_func:
                record_timing_func(f"Fetch: {key}")
        # input_data_dict is now loaded via load_asset_data_from_cache using params['asset_key']
        
        # --- OPTIMIZATION: Consolidate data loading ---
        # Load the cached asset input data with proper date slicing
        # Use load_and_prepare_data() to ensure data is sliced according to bootstrap_start_date/bootstrap_end_date
        from core.data import load_and_prepare_data
        input_data_dict = load_and_prepare_data(params)
        if not input_data_dict:
            logging.error(f"Failed to load and prepare input data during regeneration.")
            # Return None to indicate failure, as the report cannot be generated without this data.
            return None
        if record_timing_func:
            record_timing_func("Fetch: Asset Cache")

        # Assemble the final data package
        regeneration_package = {
            "params": params,
            "stats": stats,
            "gemini_content": gemini_content,
            "precalculated_data": precalculated_data,
            "input_data_dict": input_data_dict, # Pass this to the top level
            "backtest_path": precalculated_data.get('backtest_path') # Pass this to the top level
        }

        logging.debug(f"Successfully fetched all regeneration data for simulation hash: {simulation_hash[:10]}...")
        return regeneration_package

    except Exception as e:
        logging.error(f"An error occurred while fetching regeneration data for hash {simulation_hash[:10]}...: {e}", exc_info=True)
        return None
    finally:
        db.release_connection(conn)