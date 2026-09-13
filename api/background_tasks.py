"""
This module contains top-level functions designed to be the target for
multiprocessing.Process.

By isolating these functions in their own file, we avoid `PicklingError`
issues that can arise when spawning processes from a complex Streamlit script.
The child process can reliably import these functions without any conflicts
related to the `__main__` module.
"""
import pandas as pd
import time
import logging

# --- Module-level imports for threading (shared across threads) ---
# These are imported here so threads don't need to re-import (unlike processes)
from db.regeneration_db import get_regeneration_data
from db.utils import _sanitize_for_json
from reporting.content import (
    get_disclaimer_text, get_methodology_description, get_strategic_analysis_content,
    get_section_intro, get_plot_description, get_structured_settings,
    get_structured_advanced_stats, get_glossary_data
)
from reporting.interactive_plotting import (
    plot_price_history_interactive, plot_yearly_returns_interactive,
    plot_rolling_returns_histogram_interactive, plot_autocorrelation_interactive,
    plot_historical_drawdowns_interactive, plot_all_simulation_paths_interactive,
    plot_final_net_worth_distribution_interactive, plot_simulation_overview_interactive,
    plot_portfolio_value_overview_interactive, plot_cashflow_liabilities_interactive,
    plot_yearly_cash_flow_interactive
)
from core.shared_logic import get_info_boxes_text
from reporting.components import (
    prepare_average_results_table, prepare_example_path_table,
    prepare_settings_table, prepare_advanced_stats_table, prepare_executive_summary,
    prepare_median_yearly_results_table, prepare_historical_stats_table,
    prepare_market_scenarios_table
)
from reporting.color_scheme import FlowchartColors, LightFlowchartColors, get_chart_theme
from reporting.flowchart import ensure_flowchart_image
from version import get_component_hashes

def run_simulation_process(progress_queue, completion_queue, ui_params, full_sim_params, simulation_hash, terminal_log_max_length, is_prod_env, process_key=None): # noqa
    """
    A top-level function that can be pickled by multiprocessing.
    It runs the simulation, saves it to the DB, and puts the resulting simulation_id into a queue.
    """
    import logging
    import traceback
    try:
        from logger import configure_logging
        configure_logging() # Ensure logs go to console/file
        
        logging.info(f"🚀 Background Process Started for hash {simulation_hash[:8]}")
        
        full_sim_params['process_key'] = process_key # noqa
        full_sim_params['is_prod_env'] = is_prod_env # noqa
        
        success, history_id = run_and_save_simulation(ui_params, full_sim_params, simulation_hash, progress_queue=progress_queue) # noqa
        completion_queue.put((success, history_id)) # Signal completion with success status and history_id.
        logging.info(f"✅ Background Process Completed for hash {simulation_hash[:8]}")
        
    except Exception as e:
        error_msg = f"❌ CRITICAL ERROR in run_simulation_process: {e}\n{traceback.format_exc()}"
        logging.error(error_msg)
        # Try to put error in queue if possible, so UI sees it?
        # completion_queue.put((False, None)) # Optional but good
        print(error_msg) # Fallback to stdout


def on_simulation_complete(simulation_hash):
    """
    Called after simulation results are saved to database.
    
    Args:
        simulation_hash: The simulation identifier
    """
    import logging
    # Auto-generation disabled per user request (Opt-in only)
    logging.info(f"✅ Simulation complete for {simulation_hash[:10]}. PDF generation is available on-demand.")


def run_and_save_simulation(ui_params, full_sim_params, simulation_hash, progress_queue=None, progress_range=(0.0, 1.0)): # noqa
    """
    Runs the full simulation and report generation process based on the provided parameters.
    This function is designed to be run in a background process.
    """
    # --- All imports are local for process safety ---
    import logging
    import random
    import numpy as np
    from core.shared_logic import (
        assemble_params, 
        get_info_boxes_text, 
        prepare_results_dataframe
    )
    from db.database import db
    from db.utils import _sanitize_for_json
    from core.data import load_and_prepare_data, prepare_simulation_inputs
    from core.stats import calculate_final_statistics, calculate_historical_price_stats
    from core.input_analysis import calculate_autocorrelation, calculate_historical_drawdowns, analyze_returns_distribution
    from core.scoring import calculate_risk_score, calculate_risk_return_score
    from simulation import run_simulation
    from reporting.analysis import (
        get_gemini_analysis_prompt, get_gemini_analysis,
        get_executive_summary_prompt, get_executive_summary_from_gemini,
        GEMINI_AVAILABLE
    )
    from version import get_component_hashes

    # Schema readiness is the worker's (or deploy's) responsibility now —
    # run_worker() migrates once at startup under an advisory lock. Running
    # migrations per simulation job added a racy no-op to every run.

    def send_progress(p, status_text=None):
        if progress_queue:
            scaled_progress = progress_range[0] + p * (progress_range[1] - progress_range[0])
            scaled_progress = max(0.0, min(1.0, scaled_progress))
            progress_queue.put((scaled_progress, status_text))

    try:
        logging.info(f"\n--- Running Simulation (Background Process) for hash: {simulation_hash[:10]}... ---")
        # --- NEW: Timing Instrumentation ---
        start_time = time.time()
        timing_data = []

        def record_timing(step_name):
            current_time = time.time() - start_time
            timing_data.append({'step': step_name, 'time_seconds': current_time})
            logging.info(f"⏱️ TIMING: {step_name} completed at {current_time:.2f}s")
        
        record_timing("Process Started")

        # Update the cache status to 'RUNNING'
        db.update_cached_simulation_status(simulation_hash, 'RUNNING')
        record_timing("Status set to RUNNING")

        if full_sim_params['enable_gemini_analysis'] and not GEMINI_AVAILABLE:
            logging.warning("Gemini AI analysis skipped: 'google-genai' is not installed.")
        
        # --- Extract currency for this simulation ---
        from core.simulation_currency import get_simulation_currency
        simulation_currency = get_simulation_currency(full_sim_params)
        logging.info(f"Running simulation in currency: {simulation_currency}")
    
        send_progress(0.05, "Loading and preparing data...")
        data = load_and_prepare_data(full_sim_params)
        record_timing("Data Loaded")

        acf_data, drawdown_data, rolling_returns_stats, historical_stats = None, None, None, None
        if data:
            if data.get('daily_returns') is not None:
                acf_data = calculate_autocorrelation(data['daily_returns'], lags=60)
            if data.get('prices') is not None:
                drawdown_data = calculate_historical_drawdowns(data['prices'])
                historical_stats = calculate_historical_price_stats(data['prices'])
            if data.get('rolling_annual_returns') is not None:
                rolling_returns_stats = analyze_returns_distribution(data['rolling_annual_returns'])

        if not data:
            raise ValueError("Failed to load or prepare data.")
        record_timing("Historical Analysis Calculated")

        send_progress(0.15, "Data loaded. Starting simulation runs...")
        # Note: asset_name is already set in assemble_params() from assets.yml display_name
        # Don't overwrite it with data['asset_name'] which might be a formatted fallback
        full_sim_params['component_hashes'] = get_component_hashes()
        db.update_cached_simulation_params(simulation_hash, full_sim_params)

        # --- REFACTOR: Prepare all return sources for the simulation engine ---
        # --- REFACTOR: Use centralized logic to prepare return sources ---
        sim_inputs = prepare_simulation_inputs(data, full_sim_params['asset_model'])
        returns_sources = sim_inputs['returns_sources']

        from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
        from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy
        strategy_class_map = {'trinity': TrinityStrategy, 'buy_borrow_die': BuyBorrowDieStrategy, 'get_rich_stay_rich': GetRichStayRichStrategy}
        strategy_key = full_sim_params.get('strategy')

        # --- REFACTOR: Use Factory Pattern for Strategy Instantiation ---
        # This ensures a FRESH strategy instance is created for every single Monte Carlo run,
        # preventing state leakage for stateful strategies (e.g., GetRichStayRich).
        strategy_factory = None

        if strategy_key == 'custom':
            from core.sandbox import execute_strategy_code
            from core.strategy import BaseStrategy
            from core.sandbox import SandboxedStrategyWrapper
            strategy_class_name = full_sim_params.get('custom_strategy_class_name', 'CustomStrategy')
            
            # 1. Get the raw, user-defined strategy class from the sandboxed execution.
            user_strategy_class = execute_strategy_code(full_sim_params['custom_strategy_code'], strategy_class_name)
            
            # Define Factory: Returns a NEW SandboxedStrategyWrapper(NEW UserStrategy)
            def custom_factory():
                return SandboxedStrategyWrapper(user_strategy_class(full_sim_params))
            
            strategy_factory = custom_factory
        else:
            strategy_class = strategy_class_map.get(strategy_key)
            if not strategy_class:
                 raise ValueError(f"Unknown strategy: {strategy_key}")

            # Define Factory: Returns a NEW Built-in Strategy
            def builtin_factory():
                return strategy_class(full_sim_params)
            
            strategy_factory = builtin_factory

        record_timing("Strategy Factory Initialized")

        # run_simulation passes the factory to the engine, which calls it for every run.
        simulations = run_simulation(
            full_sim_params,
            returns_sources=returns_sources,
            mu=data['mu'], sigma=data['sigma'],
            progress_queue=progress_queue,
            strategy_map=None, # Deprecated in favor of factory
            strategy_factory=strategy_factory, # SAFE: New instance per run
            progress_range=(0.25, 0.75)
        )
        record_timing("Monte Carlo Simulation Complete")

        results_dataframe = prepare_results_dataframe(simulations)
        
        # Define all possible metrics that might be present in the yearly results.
        # This list ensures that all downstream calculations and selections
        # are robust against missing columns for specific strategies.
        all_possible_metrics = [
            'Asset Value', 'Debt', 'Cash', 'Net Worth', 'Consumption Delivered',
            'Amount Sold', 'Amount Bought', 'Debt Change', 'Interest Paid',
            'Tax Paid', 'Fees Paid', 'Amount Contributed'
        ]

        # --- FIX: Correctly calculate the average yearly results. ---
        # 1. Calculate the mean across all simulation columns (axis=1). This returns a Series with a (Year, Metric) MultiIndex.
        # 2. Unstack the 'Metric' level to pivot the metrics into columns, with 'Year' as the index.
        average_results_df = results_dataframe.mean(axis=1).unstack(level='Metric')

        # --- BROADER SOLUTION: Ensure all expected metrics exist, filling with 0 if missing ---
        for col in all_possible_metrics:
            if col not in average_results_df.columns:
                average_results_df[col] = 0.0 # Use float for consistency with other numeric data

        # 1. Calculate derived columns
        # Now that all cost_cols are guaranteed to exist, we can safely sum them.
        cost_cols = ['Interest Paid', 'Tax Paid', 'Fees Paid'] # Re-define for clarity, they are already in all_possible_metrics
        average_results_df['Total Annual Costs'] = average_results_df[cost_cols].sum(axis=1)

        average_results_df['LTV'] = np.where(average_results_df['Asset Value'] > 0, average_results_df['Debt'] / average_results_df['Asset Value'], 0)
        average_results_df['Costs / Net Worth'] = np.where(average_results_df['Net Worth'] > 0, average_results_df['Total Annual Costs'] / average_results_df['Net Worth'], 0)

        # 2. Select and order the final, universal columns for the appendix table.
        # This structure works for any strategy (Trinity, BBD, Custom).
        final_avg_cols = [
            'Asset Value', 'Cash', 'Debt', 'Net Worth', 'LTV', 
            'Consumption Delivered', 'Amount Sold', 'Amount Contributed', 'Total Annual Costs', 'Costs / Net Worth'
        ]
        # Ensure all columns exist before selecting, filling with 0 if not.
        for col in final_avg_cols:
            if col not in average_results_df: average_results_df[col] = 0.0
        average_results_df = average_results_df[final_avg_cols]

        # --- Calculate Median Yearly Results ---
        # Apply the same correct logic for the median calculation.
        median_yearly_results_df = results_dataframe.median(axis=1).unstack(level='Metric')

        # --- BROADER SOLUTION: Apply the same defensive initialization to median results ---
        for col in all_possible_metrics:
            if col not in median_yearly_results_df.columns:
                median_yearly_results_df[col] = 0.0

        # 1. Calculate derived columns
        median_yearly_results_df['Total Annual Costs'] = median_yearly_results_df[cost_cols].sum(axis=1)
        median_yearly_results_df['LTV'] = np.where(median_yearly_results_df['Asset Value'] > 0, median_yearly_results_df['Debt'] / median_yearly_results_df['Asset Value'], 0)
        median_yearly_results_df['Costs / Net Worth'] = np.where(median_yearly_results_df['Net Worth'] > 0, median_yearly_results_df['Total Annual Costs'] / median_yearly_results_df['Net Worth'], 0)

        # 2. Select and order the final, universal columns for the appendix table.
        for col in final_avg_cols: # Use the same column order as average results
            if col not in median_yearly_results_df: median_yearly_results_df[col] = 0.0
        median_yearly_results_df = median_yearly_results_df[final_avg_cols]
        record_timing("Summary Tables Calculated")


        # Concatenate all annual returns into a single 1D array
        # This handles cases where backtest and Monte Carlo sims have different lengths
        all_annual_returns = np.concatenate([sim.annual_returns for sim in simulations])
        full_sim_params['all_annual_returns_for_stats'] = pd.Series(all_annual_returns)
        if data.get('daily_returns') is not None:
            full_sim_params['historical_daily_returns_for_stats'] = data['daily_returns']

        # --- FIX: Explicitly pass historical mu and sigma for Asset Ratio calculations ---
        # For bootstrap models, the stats function needs the historical asset characteristics
        # to calculate the Asset Sharpe/Sortino ratios correctly.
        if 'bootstrap' in full_sim_params['asset_model']:
            full_sim_params['annual_return'] = data.get('mu', 0.0) * 252 # Annualize daily mu
            full_sim_params['annual_volatility'] = data.get('sigma', 0.0) * np.sqrt(252) # Annualize daily sigma

        final_stats = {
            'acf_data': acf_data,
            'drawdown_data': drawdown_data,
            'rolling_returns_stats': rolling_returns_stats,
            'historical_stats': historical_stats
        }
        final_stats.update(calculate_final_statistics(results_dataframe, full_sim_params))

        # --- FIX: Unify Asset Sharpe/Sortino calculations ---
        # Copy the ratios from historical_stats to the top-level final_stats
        # to ensure consistency between the "Asset Information" and "Advanced Stats" sections.
        if historical_stats:
            final_stats['asset_sharpe_ratio'] = historical_stats.get('sharpe_ratio', 0.0)
            final_stats['asset_sortino_ratio'] = historical_stats.get('sortino_ratio', 0.0)
            final_stats['asset_ulcer_index'] = historical_stats.get('ulcer_index', 0.0)
        else:
            final_stats['asset_sharpe_ratio'] = 0.0
            final_stats['asset_sortino_ratio'] = 0.0
            final_stats['asset_ulcer_index'] = 0.0
            
        # --- FIX: Ensure contribution stats are available for plotting ---
        # Extract median contributions for the "Cumulative Invested" line in plots
        if 'Amount Contributed' in median_yearly_results_df.columns:
            # Convert to dict and handle any NaN values
            contribs = median_yearly_results_df['Amount Contributed'].fillna(0).to_dict()
            final_stats['median_contributions_values'] = contribs
            final_stats['median_total_contributions'] = float(median_yearly_results_df['Amount Contributed'].sum())
        else:
             final_stats['median_contributions_values'] = {}
             final_stats['median_total_contributions'] = 0.0

        final_stats['risk_score'] = calculate_risk_score(final_stats, full_sim_params)
        final_stats['risk_return_score'] = calculate_risk_return_score(final_stats, full_sim_params)
        record_timing("Final Stats & Risk Scores Completed")

        gemini_content_for_db = {
            'analysis': "Analysis was disabled.",
            'main_outcome': "Analysis was disabled.",
            'bottom_line': "Analysis was disabled."
        }
        if full_sim_params.get('enable_gemini_analysis') and GEMINI_AVAILABLE:
            send_progress(0.85, "Running analysis...")
            # Extract currency from simulation parameters
            from core.simulation_currency import get_simulation_currency
            simulation_currency = get_simulation_currency(full_sim_params)
            logging.info(f"Using currency {simulation_currency} for analysis")
            
            # Get user_id upfront to increment credits if needed
            user_email = full_sim_params.get('user_email')
            user_name = full_sim_params.get('user_name')
            user_id = db.get_or_create_user_id(user_email, user_name)
            
            api_key = full_sim_params.get('gemini_api_key')
            if api_key:
                # Get strategy description for both prompts
                strategy_key = full_sim_params.get('strategy', 'N/A')
                if strategy_key == 'custom':
                    # For custom strategies, use the AI-generated description
                    strategy_description = full_sim_params.get('custom_strategy_ai_description', 
                                                             full_sim_params.get('custom_strategy_description', 
                                                                               'A custom user-defined strategy.'))
                else:
                    # For built-in strategies, fetch from content registry
                    from reporting.content import STRATEGY_DESCRIPTIONS
                    strategy_description = STRATEGY_DESCRIPTIONS.get(strategy_key, 
                                                                    ' '.join(word.capitalize() for word in strategy_key.split('_')))
                
                # Part 1: Full Analysis
                gemini_prompt_text = get_gemini_analysis_prompt(full_sim_params, final_stats, simulation_currency, strategy_description)
                analysis = get_gemini_analysis(gemini_prompt_text, api_key) # noqa

                # Part 2: Executive Summary
                executive_summary_prompt = get_executive_summary_prompt(full_sim_params, final_stats, strategy_description, simulation_currency)
                executive_summary_text = get_executive_summary_from_gemini(executive_summary_prompt, api_key)

                # --- Increment AI Credits After Successful LLM Analysis ---
                # This is where we consume the Gemini API, so we increment credits here
                # (consistent with strategy generation behavior)
                user_id_for_credits = full_sim_params.get('user_id') or user_id
                if user_id_for_credits:
                    from core.limits import LimitEnforcer
                    limiter = LimitEnforcer(db)
                    limiter.increment_ai_credits(user_id_for_credits)
                    logging.info(f"Incremented AI credits for user {user_id_for_credits} after LLM analysis generation")

                # Split the summary into two parts for the database
                main_outcome = executive_summary_text
                bottom_line = "" # Default value
                if "Part 2: Qualitative Analysis" in executive_summary_text:
                    parts = executive_summary_text.split("Part 2: Qualitative Analysis", 1)
                    main_outcome = parts[0].replace("Part 1: Quantitative Summary", "").strip()
                    bottom_line = parts[1].strip()
                elif "Part 2:" in executive_summary_text: # A bit more robust
                    parts = executive_summary_text.split("Part 2:", 1)
                    main_outcome = parts[0].replace("Part 1: Quantitative Summary", "").strip()
                    bottom_line = parts[1].strip()

                gemini_content_for_db = {'analysis': analysis, 'main_outcome': main_outcome, 'bottom_line': bottom_line}
                record_timing("AI Analysis Completed")
        
        # Fetch strategy evaluation data for caching (avoid repeated database lookups)
        evaluation_data_for_db = None
        try:
            from reporting.strategy_evaluation_charts import get_evaluation_for_strategy
            strategy_key = full_sim_params.get('strategy', 'unknown')
            if strategy_key != 'custom':  # Only built-in strategies have evaluations
                strategy_display = ' '.join(word.capitalize() for word in strategy_key.split('_'))
                evaluation_data_for_db = get_evaluation_for_strategy(strategy_display, class_name=strategy_key)
                logging.info(f"Cached strategy evaluation data for {strategy_key}")
        except Exception as e:
            logging.warning(f"Could not fetch strategy evaluation data for caching: {e}")
        record_timing("Evaluation Data Fetched")



        simulation_name = full_sim_params.get('simulation_name', 'Untitled Simulation')

        send_progress(0.95, "Saving results to database...")
        # --- STEP 4: Handle Replacement Run ---
        # Extract the flag and pass it to the save function. This tells the database
        # to UPDATE the existing stale record instead of inserting a new one.
        is_replacement = full_sim_params.get('is_replacement_run', False)
        # Update cached simulation with results (history already created in app.py)
        results_id = db.update_cached_simulation_results(
            simulation_hash, full_sim_params, ui_params, final_stats, results_dataframe,
            average_results_df, median_yearly_results_df, gemini_content_for_db,
            status='COMPLETED', evaluation_data=evaluation_data_for_db
        )
        record_timing("Results Saved to DB")
        
         # --- GLOBAL STATS INCREMENT ---
        try:
            # 1. Increment total simulations run
            db.increment_global_counter('total_simulations_run', 1)
            
            # 2. Increment total years simulated
            num_years = full_sim_params.get('num_years', 30)
            db.increment_global_counter('total_years_simulated', num_years)
        except Exception as e:
            logging.error(f"Failed to increment global stats: {e}")
        
        # --- NEW: Auto-queue PDF generation ---
        on_simulation_complete(simulation_hash)
        
        send_progress(1.0, "Done!")

        record_timing("Process Complete")
        
        # --- Log Timing Summary ---
        timing_df = pd.DataFrame(timing_data)
        # Calculate delta between steps for cleaner view
        timing_df['delta_s'] = timing_df['time_seconds'].diff().fillna(timing_df['time_seconds'])
        logging.info(f"--- RUN SIMULATION TIMING SUMMARY ({simulation_hash[:8]}) ---\n{timing_df.to_string(index=False)}")

        logging.info(f"--- Simulation Complete. Saved under hash {simulation_hash[:10]}... with results ID: {results_id} ---")
        return True, simulation_hash

    except Exception as e:
        record_timing(f"ERROR: {str(e)}")
        logging.critical(f"An unexpected error occurred in simulation process: {e}", exc_info=True)
        db.update_cached_simulation_status(simulation_hash, 'FAILED')
        send_progress(1.0, f"Error: {e}")
        return False, None

def regenerate_ui_thread(results_queue, progress_queue, simulation_hash, thread_key=None, viewer_is_admin=False):
    """
    Thread wrapper for UI regeneration. Much simpler than process version!
    No special setup needed - shares main process's memory and modules.
    """
    thread_start = time.time()
    logging.info(f"⏱️ THREAD TIMING: Thread started for {simulation_hash[:10]} at {thread_start:.3f}")
    
    try:
        regenerate_ui_results(
            simulation_hash, 
            results_queue, 
            progress_queue=progress_queue,
            thread_key=thread_key,
            thread_start_time=thread_start,
            viewer_is_admin=viewer_is_admin
        )
        elapsed = time.time() - thread_start
        logging.info(f"⏱️ THREAD TIMING: Thread complete - total time: {elapsed:.3f}s")
    except Exception as e:
        logging.error(f"Thread error for {simulation_hash[:10]}: {e}", exc_info=True)
        results_queue.put({'type': 'error', 'message': str(e)})

def regenerate_ui_results(simulation_hash: str, results_queue, progress_queue=None, process_key=None, process_start_time=None, thread_key=None, thread_start_time=None, viewer_is_admin=False):
    """
    Regenerates all UI components (plots, tables, text) for a given simulation_id
    and sends them to the results_queue for live display.
    
    Works with both multiprocessing (process_key) and threading (thread_key).
    """
    # Import pandas at top of function to avoid UnboundLocalError
    import pandas as pd
    import os
    
    # No more local imports needed - they're at module level now!
    # This eliminates ~10 seconds of import time when using threads
    
    process_work_start = time.time()
    
    # Determine which mode we're in and log appropriately
    if thread_key:
        logging.info(f"⏱️ THREAD TIMING: Work began (imports already loaded)")
        key = thread_key
        start_time = thread_start_time
    else:
        logging.info(f"⏱️ PROCESS TIMING: Background process began work (PID: {os.getpid()})")
        key = process_key
        start_time = process_start_time
    
    logging.info(f"--- Starting UI Regeneration for Simulation Hash: {simulation_hash[:10]}... ---")

    def send_progress(progress_value, status_text):
        """Helper to send progress updates to the UI."""
        if progress_queue:
            progress_value = max(0.0, min(1.0, progress_value))
            progress_queue.put((progress_value, status_text))

    # --- Timing Tracking ---
    # Use thread_start_time if provided (threading mode), otherwise process_start_time (multiprocessing mode)
    if thread_start_time:
        start_time = thread_start_time  # Threading: measure from thread start
    elif process_start_time:
        start_time = process_start_time  # Multiprocessing: measure from process entry
    else:
        start_time = time.time()  # Direct call: measure from now
    
    timing_data = []
    
    # Record initialization overhead (only for multiprocessing - threads have no overhead!)
    if process_start_time and not thread_start_time:
        init_overhead = process_work_start - process_start_time
        timing_data.append({'step': 'Process Initialization & Imports', 'time_seconds': init_overhead})
    elif thread_start_time:
        # Threads start instantly - no initialization overhead!
        instant_start = process_work_start - thread_start_time
        timing_data.append({'step': 'Thread Start (instant!)', 'time_seconds': instant_start})
    
    def record_timing(step_name):
        nonlocal start_time
        current_time = time.time() - start_time 
        timing_data.append({'step': step_name, 'time_seconds': current_time})

    send_progress(0.05, "Fetching simulation data from database...")

    def send_special_result(res_type, data):
        if results_queue:
            logging.debug(f"send_special_result: type='{res_type}'")
            results_queue.put({'type': res_type, 'data': data})

    def send_result(res_type, data, caption=None, section=None, sub_section=None, description=None):
        if results_queue:
            logging.debug(f"send_result: type='{res_type}', caption='{caption}', section='{section}', sub_section='{sub_section}'")
            # --- FIX: Explicitly handle DataFrame to JSON string conversion ---
            # The 'dataframe' type needs to be converted to a JSON string before being sanitized.
            # Other types can be sanitized directly.
            if res_type == 'dataframe' and isinstance(data, pd.DataFrame):
                sanitized_data = data.to_json(orient='split')
            else:
                sanitized_data = data if res_type in ['plotly', 'plot'] else _sanitize_for_json(data)
            results_queue.put({
                'type': res_type, 'data': sanitized_data, 'caption': _sanitize_for_json(caption),
                'section': _sanitize_for_json(section), 'sub_section': _sanitize_for_json(sub_section),
                'description': _sanitize_for_json(description)
            })

    record_timing("Start Regeneration")
    regeneration_package = get_regeneration_data(simulation_hash, record_timing_func=record_timing)
    if not regeneration_package:
        logging.error(f"Failed to fetch regeneration data for hash {simulation_hash[:10]}.... Aborting.")
        send_result('error', f"Error: Could not load data for Simulation Hash {simulation_hash[:10]}....")
        send_progress(1.0, "Error loading data.")
        return

    send_special_result('regeneration_package', regeneration_package)

    sim_params = regeneration_package.get('params', {})
    final_stats = regeneration_package.get('stats', {})
    gemini_content = regeneration_package.get('gemini_content', {})
    precalculated_data = regeneration_package.get('precalculated_data', {})
    
    # --- Extract currency for this simulation ---
    from core.simulation_currency import get_simulation_currency
    simulation_currency = get_simulation_currency(sim_params)
    logging.info(f"Regenerating UI with currency: {simulation_currency}")

    input_data_dict = regeneration_package.get('input_data_dict')
    backtest_path = regeneration_package.get('backtest_path')

    # --- Version Check ---
    stored_hashes = sim_params.get('component_hashes', {})
    current_hashes = get_component_hashes()
    changed_components = []
    for component, current_hash in current_hashes.items():
        stored_hash = stored_hashes.get(component)
        if stored_hash != current_hash:
            changed_components.append(component)
    
    # Only show version warning to admin viewers (flag supplied by the caller)
    if changed_components and viewer_is_admin:
            send_result('warning', {
                'title': 'Outdated Report Warning',
                'body': 'This report was generated with an older version of the code. The results may be outdated. Changed components:',
                'components': changed_components
            })

    if not input_data_dict:
        logging.error(f"Failed to load cached input data for asset key '{sim_params.get('asset_key', 'N/A')}'. Aborting.")
        send_result('text', f"Error: Could not load cached input data for asset '{sim_params.get('asset_name', 'N/A')}'.")
        send_progress(1.0, "Error loading asset data.")
        return

    # ============================================================================
    # MANIFEST-DRIVEN REPORT GENERATION (Incremental Migration)
    # ============================================================================
    # Import manifest and rendering functions
    from reporting.content import REPORT_STRUCTURE
    from reporting.manifest_renderer import build_data_context, render_section_for_ui
    
    # Start timing static content generation
    # OLD CODE - Being replaced by manifest-driven approach
    # send_result('text', get_disclaimer_text(), section='Important Disclaimer')
    
    # NEW: Manifest-driven rendering for "Important Disclaimer" section
    section_name = 'Important Disclaimer'
    if section_name in REPORT_STRUCTURE:
        # Build minimal context for this section (will expand as we migrate more sections)
        context = {'disclaimer': get_disclaimer_text()}
        render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context, send_result)
    
    record_timing("Disclaimer Sent")
    
    # === Methodology Overview Section ===
    # This section has flowchart handling - keeping it for now as it's complex
    # Will migrate after simpler sections are done
    # Methodology section: intro → flowchart → detailed description
    from reporting.content import get_methodology_intro, get_methodology_detailed, get_methodology_flowchart_description
    
    # 1. Send intro text
    send_result('text', get_methodology_intro(), section='Methodology Overview', sub_section='Introduction')
    record_timing("Methodology: Intro Sent")
    
     # 2. Send flowchart immediately after intro (same sub-section to keep it together)
    import base64
    
    theme = get_chart_theme()
    bg_theme = "light" if theme == "light" else "dark"
    
    # Only generate if doesn't exist (cached simulations already have it)
    logging.info(f"⏱️ FLOWCHART CALL: Starting ensure_flowchart_image for theme={bg_theme}")
    flowchart_start =  time.time()
    methodology_flowchart_path = ensure_flowchart_image(output_dir="assets", bg=bg_theme)
    flowchart_elapsed = time.time() - flowchart_start
    logging.info(f"⏱️ FLOWCHART CALL: Completed in {flowchart_elapsed:.3f}s - path={methodology_flowchart_path}")
    record_timing("Methodology: Flowchart Generated")
    
    if methodology_flowchart_path and os.path.exists(methodology_flowchart_path):
        # Send flowchart description first
        send_result('text', f"<b>Simulation Process Flow</b><br/><br/>{get_methodology_flowchart_description()}", 
                   section='Methodology Overview', sub_section='Introduction')
        
        # Read image and convert to base64 for transmission
        with open(methodology_flowchart_path, "rb") as img_file:
            img_data = base64.b64encode(img_file.read()).decode()
        
        send_result(
            'image',
            img_data,
            caption="Simulation Methodology Flowchart",
            section='Methodology Overview',
            sub_section='Introduction'  # Same sub-section as intro
        )
        logging.info("Sent methodology flowchart to UI (cached)")
        record_timing("Methodology: Flowchart Sent")
    else:
        logging.warning("Methodology flowchart could not be generated")
    
    # 3. Send detailed methodology description
    send_result('text', get_methodology_detailed(), section='Methodology Overview', sub_section='Detailed Description')
    record_timing("Methodology Sent")
    
    # Strategic Analysis - send structured content
    cached_evaluation_data = precalculated_data.get('evaluation_data')
    strategic_content = get_strategic_analysis_content(sim_params, evaluation_data=cached_evaluation_data)
    record_timing("Strategy: Content Prepared")
    send_result('intro', strategic_content['intro'], section='Strategic Analysis')
    send_result('key_value_table', strategic_content['transaction_types'], caption='Available Transaction Types', section='Strategic Analysis')
    send_result('text', strategic_content['strategy_description'], section='Strategic Analysis')
    record_timing("Strategy Description Sent")
    
    # Add strategy flowchart if available
    flowchart_info = strategic_content.get('flowchart_info', {})
    if flowchart_info.get('available'):
        import os
        from reporting.generate_flowchart import generate_flowchart_png
        from reporting.strategy_flowcharts import get_strategy_flowchart
        
        flowchart_path = flowchart_info['dark_path'] # Keep original path logic
        
        # Only generate if flowchart doesn't already exist (caching)
        if not os.path.exists(flowchart_path):
            # Get theme-aware background color
            theme = get_chart_theme()
            bg_color = LightFlowchartColors.BACKGROUND if theme == 'light' else FlowchartColors.BACKGROUND
            
            # Generate flowchart with appropriate theme
            mermaid_code = get_strategy_flowchart(flowchart_info['key'], theme=theme)
            if mermaid_code:
                generate_flowchart_png(mermaid_code, flowchart_path, bg_color=bg_color)
                logging.info(f"Generated strategy flowchart: {flowchart_path}")
        else:
            logging.info(f"Using cached strategy flowchart: {flowchart_path}")
        
        if os.path.exists(flowchart_path):
            send_result('plot', flowchart_path, section='Strategic Analysis', caption='Strategy Decision Flow')
        record_timing("Strategy Flowchart Sent")
    
    # --- Strategy Evaluation Section ---
    evaluation_data = strategic_content.get('evaluation_data')
    if evaluation_data:
        import json
        import plotly.graph_objects as go
        from core.strategy_evaluation import METRIC_WEIGHTS
        
        # Excellence Score as text
        excellence_score = evaluation_data.get('excellence_score', 0)
        send_result('text', f"<h4>🏆 Strategy Evaluation Results</h4><p><em>This strategy has been stress-tested across 8 standardized market scenarios:</em></p><h3>Excellence Score: {excellence_score:.1f}/100</h3>", section='Strategic Analysis')
        
        # Display Market Scenarios Reference Table
        scenarios_data = prepare_market_scenarios_table()
        send_result('key_value_table', scenarios_data, caption='Scenario Definitions', section='Strategic Analysis')
        
        # Build radar chart with category-aware filtering using centralized function
        from reporting.radar_chart_data import create_radar_chart
        
        fig = create_radar_chart(
            evaluation_data=evaluation_data,
            metric_source='METRIC_WEIGHTS',
            strategy_name=evaluation_data.get('strategy_name'),
            height=400
        )
        
        # Only render if we have a chart
        if fig:
            
            send_result('plotly', fig.to_json(), section='Strategic Analysis', caption='Strategy Evaluation Radar Chart')
        
        # Component Scores table
        component_data = []
        for key, info in METRIC_WEIGHTS.items():
            if info['weight'] > 0:
                score = evaluation_data.get(key, 0)
                weight_pct = int(info['weight'] * 100)
                component_data.append({'label': f"{info['name']} ({weight_pct}% weight)", 'value': f"{score:.0f}/100"})
        
        send_result('key_value_table', component_data, caption='Component Scores', section='Strategic Analysis')
        
        # Scenario Performance table
        scenario_json = evaluation_data.get('scenario_results_json')
        if scenario_json:
            scenario_data = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
            
            scenario_df = pd.DataFrame(scenario_data)
            
            display_scenario_df = pd.DataFrame({
                'Scenario': scenario_df['name'],
                'Sortino Ratio': scenario_df['sortino_ratio'].round(2),
                'Success Rate': (scenario_df['success_rate'] * 100).round(1).astype(str) + '%'
            })
            
            send_result('dataframe', display_scenario_df.to_json(orient='split'), caption='Performance by Scenario', section='Strategic Analysis')
    else:
        send_result('text', "<p><em>📊 Strategy Evaluation: This strategy has not yet been evaluated on the leaderboard. Evaluation data will appear here once the strategy is tested.</em></p>", section='Strategic Analysis')
    record_timing("Strategy Evaluation Sent")
    
    record_timing("Static Content Sent")

    send_progress(0.25, "Re-creating settings and input analysis...")
    # Pass the flat 'sim_params' dictionary, which contains the actual simulation settings.
    structured_settings = get_structured_settings(sim_params)
    # === Simulation Settings Section ===
    # OLD CODE - Being replaced by manifest-driven approach
    # send_result('intro', get_section_intro("Simulation Settings"), section='Simulation Settings')
    # send_result('settings_table', structured_settings, section='Simulation Settings')
    
    # NEW: Manifest-driven rendering for "Simulation Settings" section
    section_name = 'Simulation Settings'
    if section_name in REPORT_STRUCTURE:
        structured_settings = prepare_settings_table(sim_params)
        context_settings = {
            'settings_table': structured_settings
        }
        render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_settings, send_result)
    
    record_timing("Settings Sent")

    # Generate Input Data Analysis plots using centralized structure
    send_progress(0.35, "Generating input data plots...")
    send_result('intro', get_section_intro("Input Data Analysis"), section='Input Data Analysis')
    
    if input_data_dict:
        # Send asset information table
        historical_stats = final_stats.get('historical_stats', {})
        if historical_stats:
            table_data = prepare_historical_stats_table(historical_stats, sim_params)
            send_result('key_value_table', table_data, caption='Asset Information', section='Input Data Analysis')

        # Import plotting functions
        from reporting.interactive_plotting import (
            plot_price_history_interactive, plot_yearly_returns_interactive,
            plot_rolling_returns_histogram_interactive, plot_autocorrelation_interactive,
            plot_historical_drawdowns_interactive
        )
        from reporting.content import INPUT_REPORT_STRUCTURE, generate_plots_from_structure
        
        # Prepare data context for plot generation
        data_context = {
            'prices': input_data_dict['prices'],
            'asset_name': input_data_dict['asset_name'],
            'params': sim_params,
            'yearly_returns': input_data_dict.get('yearly_returns'),
            'rolling_annual_returns': input_data_dict['rolling_annual_returns'],
            'rolling_returns_stats': final_stats.get('rolling_returns_stats'),
            'acf_data': final_stats.get('acf_data'),
            'drawdown_data': final_stats.get('drawdown_data'),
        }
        
        # Map function names to actual functions
        plotting_functions = {
            'plot_price_history_interactive': plot_price_history_interactive,
            'plot_yearly_returns_interactive': plot_yearly_returns_interactive,
            'plot_rolling_returns_histogram_interactive': plot_rolling_returns_histogram_interactive,
            'plot_autocorrelation_interactive': plot_autocorrelation_interactive,
            'plot_historical_drawdowns_interactive': plot_historical_drawdowns_interactive,
        }
        
        # Generate all plots from structure
        plot_results = generate_plots_from_structure(INPUT_REPORT_STRUCTURE, data_context, plotting_functions)
        
        # Send plot results to UI
        for result in plot_results:
            if result['type'] == 'plot':
                send_result('plotly', result['fig'].to_json(), result['title'], 
                           section='Input Data Analysis', 
                           description=get_plot_description(result['description_key']))
                record_timing(f"Plot: {result['title']}")

    send_progress(0.50, "Generating simulation summary...")
    # === Simulation Summary Section (Manifest-Driven) ===
    section_name = 'Simulation Summary'
    if section_name in REPORT_STRUCTURE:
        send_result('intro', get_section_intro("Simulation Summary"), section=section_name)
        
        # 1. Prepare Data Contexts
        # Info boxes
        structured_info = get_info_boxes_text(sim_params, final_stats)
        
        # Advanced stats summary
        adv_stats_summary = [
            {"label": "Asset Sharpe Ratio", "value": f"{final_stats.get('asset_sharpe_ratio', 0.0):.2f}"},
            {"label": "Asset Sortino Ratio", "value": f"{final_stats.get('asset_sortino_ratio', 0.0):.2f}"},
            {"label": "Strategy Sharpe Ratio", "value": f"{final_stats.get('strategy_sharpe_ratio', 0.0):.2f}"},
            {"label": "Strategy Sortino Ratio", "value": f"{final_stats.get('strategy_sortino_ratio', 0.0):.2f}"},
        ]
        
        # Plotting Data Context
        net_worth_percentile_paths = precalculated_data.get('net_worth_percentile_paths')
        asset_percentile_paths = precalculated_data.get('asset_percentile_paths')
        final_net_worths_hist = precalculated_data.get('final_net_worths_hist')
        sampled_paths = precalculated_data.get('sampled_paths')
        dummy_df = pd.DataFrame() # Some plots need a dummy df to init
        
        plot_context = {
            'dummy_df': dummy_df,
            'sampled_paths': sampled_paths,
            'params': sim_params,
            'final_stats': final_stats,
            'asset_percentile_paths': asset_percentile_paths,
            'net_worth_percentile_paths': net_worth_percentile_paths,
            'final_net_worths_hist': final_net_worths_hist,
            'backtest_path': backtest_path,
            'currency': simulation_currency,
            'theme': get_chart_theme(),
            'survival_rates': final_stats.get('survival_rates_by_year'),
        }
        
        # Plotting Functions
        from reporting.interactive_plotting import (
            plot_all_simulation_paths_interactive, plot_final_net_worth_distribution_interactive,
            plot_portfolio_value_overview_interactive, plot_cashflow_liabilities_interactive,
            plot_yearly_cash_flow_interactive, plot_survival_curve_interactive
        )
        from reporting.content import SIMULATION_REPORT_STRUCTURE, generate_plots_from_structure
        
        plotting_functions = {
            'plot_all_simulation_paths_interactive': plot_all_simulation_paths_interactive,
            'plot_final_net_worth_distribution_interactive': plot_final_net_worth_distribution_interactive,
            'plot_portfolio_value_overview_interactive': plot_portfolio_value_overview_interactive,
            'plot_cashflow_liabilities_interactive': plot_cashflow_liabilities_interactive,
            'plot_yearly_cash_flow_interactive': plot_yearly_cash_flow_interactive,
            'plot_survival_curve_interactive': plot_survival_curve_interactive,
        }
        
        # 2. Iterate through Manifest
        for item in REPORT_STRUCTURE[section_name]:
            item_type = item.get('type')
            key = item.get('key')
            
            if item_type == 'intro': 
                continue # Already sent above
                
            elif item_type == 'info_box':
                # Map keys to prepared data
                caption = ""
                data = []
                
                if key == 'outcome_analysis':
                     data = structured_info['outcome']
                     caption = f"Outcome Analysis (Yr {sim_params.get('num_years', 'N/A')})"
                elif key == 'risk_analysis':
                     data = structured_info['risk']
                     caption = "Risk Analysis"
                elif key == 'psychological_metrics':
                     if 'psychological' in structured_info: # Check if available
                         data = structured_info['psychological']
                         caption = "Psychological Stress Indicators"
                elif key == 'advanced_stats_summary':
                     data = adv_stats_summary
                     caption = "Advanced Statistics Summary (see appendix for details)"
                
                if data:
                    send_result('key_value_table', data, caption=caption, section=section_name)
            
            elif item_type == 'plot':
                # Find definition in SIMULATION_REPORT_STRUCTURE
                plot_def = next((p for p in SIMULATION_REPORT_STRUCTURE if p.get('key') == key), None)
                
                if plot_def:
                    try:
                        # Generate single plot
                        # We use the generate_plots_from_structure helper for a single item list to reuse logic
                        # or call directly. Let's use the helper to keep it clean.
                        single_item_list = [plot_def]
                        results = generate_plots_from_structure(single_item_list, plot_context, plotting_functions)
                        
                        for res in results:
                            if res['type'] == 'plot':
                                send_result('plotly', res['fig'].to_json(), res['title'], 
                                           section=section_name, 
                                           description=get_plot_description(res['description_key']))
                                record_timing(f"Plot: {res['title']}")
                            elif res['type'] == 'plot_group':
                                # Send each plot in the group
                                for plot_data in res['plots']:
                                    send_result('plotly', plot_data['fig'].to_json(), plot_data['title'], 
                                               section=section_name)
                                    record_timing(f"Plot: {plot_data['title']}")
                                # Send combined description after all plots in group
                                send_result('text', get_plot_description(res['description_key']), section=section_name)
                            
                    except Exception as e:
                         logging.error(f"Failed to generate plot {key}: {e}", exc_info=True)
                else:
                    logging.warning(f"Plot definition not found for key: {key}")

    record_timing("Summary Content Sent")
    send_progress(0.70, "Simulation Summary complete...")

    send_progress(0.80, "Re-creating AI analysis and summary...")
    gemini_analysis_content = gemini_content.get('analysis', "AI analysis was disabled or not found.")
    gemini_main_outcome_content = gemini_content.get('main_outcome', "AI outcome not found.")
    gemini_bottom_line_content = gemini_content.get('bottom_line', "AI bottom line not found.")
    # === Qualitative Analysis Section ===
    # OLD CODE - Being replaced by manifest-driven approach
    # send_result('intro', get_section_intro("Qualitative Analysis"), section='Qualitative Analysis')
    # send_result('text', gemini_analysis_content, 'Full Analysis', section='Qualitative Analysis')
    
    # NEW: Manifest-driven rendering for "Qualitative Analysis" section
    section_name = 'Qualitative Analysis'
    if section_name in REPORT_STRUCTURE:
        context_qualitative = {
            'gemini_analysis': gemini_analysis_content
        }
        logging.info(f"Qualitative Analysis: gemini_analysis_content length = {len(gemini_analysis_content) if gemini_analysis_content else 0}")
        logging.info(f"Qualitative Analysis: gemini_analysis_content preview = {gemini_analysis_content[:200] if gemini_analysis_content else 'EMPTY'}")
        render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_qualitative, send_result)
    
    record_timing("Qualitative Analysis Sent")

    # Use the centralized function to prepare all executive summary content
    summary_content = prepare_executive_summary(sim_params, final_stats, gemini_content, currency=simulation_currency)

    send_result('intro', get_section_intro("Executive Summary"), section='Executive Summary')
    
    # Add Traffic Light Verdict at the top for immediate risk assessment
    try:
        from reporting.executive_visuals import create_verdict_traffic_light
        verdict_fig = create_verdict_traffic_light(final_stats)
        if verdict_fig:
            send_result('plotly', verdict_fig.to_json(),
                       caption='Portfolio Survival Assessment',
                       section='Executive Summary',
                       description='Risk assessment based on long term sustainable capital preservation.')
            logging.info("Sent verdict traffic light to UI")
    except Exception as e:
        logging.warning(f"Could not generate verdict visualization: {e}")
    
    send_result('text', summary_content['scenario'], section='Executive Summary')
    send_result('text', summary_content['main_outcome'], section='Executive Summary')
    
    send_result('key_stats_table', summary_content['key_stats'], caption='Key Statistics', section='Executive Summary')
    send_result('text', summary_content['bottom_line'], section='Executive Summary')
    record_timing("AI & Summary Sent")
    send_progress(0.95, "Finalizing appendices...")

    average_results_df = precalculated_data.get('average_results_df')
    if average_results_df is not None and not average_results_df.empty:
        # Use the centralized function to format the table
        # === Average Yearly Results Appendix ===
        # OLD CODE - Being replaced by manifest-driven approach
        # df_for_ui = prepare_average_results_table(average_results_df)
        # send_result('dataframe', df_for_ui, caption=f"All values are shown in thousands of {simulation_currency} for improved readability, representing the average state of the portfolio at the end of each year, after all transactions have been completed. NOTE: Average results are heavily affected by outliers, look at median table to understand typical outcomes.", section='Appendices', sub_section='Average Yearly Results')
        
        # NEW: Manifest-driven rendering
        section_name = 'Appendices: Average Yearly Results'
        if section_name in REPORT_STRUCTURE:
            context_avg = {'average_results': average_results_df, 'currency': simulation_currency}
            render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_avg, send_result)

    median_yearly_results_df = precalculated_data.get('median_yearly_results_df')
    if median_yearly_results_df is not None and not median_yearly_results_df.empty:
        # Use the centralized function to format the table
        # === Median Yearly Results Appendix ===
        # OLD CODE - Being replaced by manifest-driven approach
        # df_for_ui = prepare_median_yearly_results_table(median_yearly_results_df)
        # send_result('dataframe', df_for_ui, caption=f"All values are shown in thousands of {simulation_currency} for improved readability, representing the median state of the portfolio at the end of each year, after all transactions have been completed.", section='Appendices', sub_section='Median Yearly Results')
        
        # NEW: Manifest-driven rendering
        section_name = 'Appendices: Median Yearly Results'
        if section_name in REPORT_STRUCTURE:
            context_median = {'median_results': median_yearly_results_df, 'currency': simulation_currency}
            render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_median, send_result)

    record_timing("Appendix: Average Yearly Results")

    # --- Create the new "Example Simulation Path" table ---
    sampled_paths = precalculated_data.get('sampled_paths')
    if sampled_paths is not None and not sampled_paths.empty:
        # --- FIX: Handle both MultiIndex and single-level index gracefully ---
        if isinstance(sampled_paths.columns, pd.MultiIndex):
            # When multiple simulations are sampled, select the first one.
            sim_name = sampled_paths.columns.levels[0][0]
            # Select all columns belonging to the first simulation name.
            raw_example_df = sampled_paths[sim_name]
        else:
            # When only one simulation is sampled, the index is already flat.
            sim_name = "Sim_0" # Default name if not available
            raw_example_df = sampled_paths
        example_table_df = prepare_example_path_table(raw_example_df)
        caption = f"Showing results for a single, randomly selected simulation path ({sim_name}). All values are shown in thousands of {simulation_currency} for improved readability, representing the state of the portfolio at the end of each year, after all transactions have been completed." # Keep the caption as it is
        # === Example Simulation Path Appendix ===
        # OLD CODE - Being replaced by manifest-driven approach
        # send_result('dataframe', example_table_df, caption=caption, section='Appendices', sub_section='Example Simulation Path')
        
        # NEW: Manifest-driven rendering
        section_name = 'Appendices: Example Simulation Path'
        if section_name in REPORT_STRUCTURE:
            context_example = {'example_path': example_table_df, 'currency': simulation_currency}
            render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_example, send_result)

    # --- Input Data Analysis Appendix (Technical Charts) ---
    try:
        from reporting.content import INPUT_DATA_APPENDIX_STRUCTURE, generate_plots_from_structure
        from reporting.content import INPUT_DATA_APPENDIX_STRUCTURE
        from reporting.interactive_plotting import (
            plot_rolling_returns_histogram_interactive, plot_autocorrelation_interactive
        )
        
        send_result('intro', get_section_intro("Input Data Analysis Appendix"), 
                   section='Appendices', sub_section='Input Data Analysis')
        
        if input_data_dict:
            data_context = {
                'prices': input_data_dict['prices'],
                'asset_name': input_data_dict['asset_name'],
                'params': sim_params,
                'yearly_returns': input_data_dict.get('yearly_returns'),
                'rolling_annual_returns': input_data_dict['rolling_annual_returns'],
                'rolling_returns_stats': final_stats.get('rolling_returns_stats'),
                'acf_data': final_stats.get('acf_data'),
                'drawdown_data': final_stats.get('drawdown_data'),
            }
            
            plotting_functions = {
                'plot_rolling_returns_histogram_interactive': plot_rolling_returns_histogram_interactive,
                'plot_autocorrelation_interactive': plot_autocorrelation_interactive,
            }
            
            for item in INPUT_DATA_APPENDIX_STRUCTURE:
                plot_key = item['key']
                plot_function_name = item['plot_function']
                title = item['title']
                
                plot_func = plotting_functions.get(plot_function_name)
                if plot_func:
                    try:
                        args = [data_context.get(arg) for arg in item.get('args', [])]
                        kwargs = {
                            k: data_context.get(v) if isinstance(v, str) else v 
                            for k, v in item.get('kwargs', {}).items()
                        }
                        fig = plot_func(*args, **kwargs)
                        send_result('plotly', fig.to_json(), title, 
                                   section='Appendices', sub_section='Input Data Analysis')
                    except Exception as e:
                        logging.warning(f"Could not generate {plot_key}: {e}")
    except Exception as e:
        logging.warning(f"Could not generate Input Data appendix: {e}")

    # === Strategy Evaluations Appendix ===
    # OLD CODE - Being replaced by manifest-driven approach
    # try:
    #     from reporting.content import get_strategy_evaluations_content
    #     eval_content = get_strategy_evaluations_content()
    #     send_result('intro', eval_content['intro'], section='Appendices', sub_section='Strategy Evaluations')
    #     send_result('text', eval_content['process'], section='Appendices', sub_section='Strategy Evaluations')
    #     send_result('text', eval_content['scenarios'], section='Appendices', sub_section='Strategy Evaluations')
    #     send_result('text', eval_content['metrics'], section='Appendices', sub_section='Strategy Evaluations')
    #     send_result('text', eval_content['wisdom'], section='Appendices', sub_section='Strategy Evaluations')
    # except Exception as e:
    #     logging.warning(f"Could not generate Strategy Evaluations appendix: {e}")
    
    # NEW: Manifest-driven rendering for "Appendices: Strategy Evaluations" section
    try:
        section_name = 'Appendices: Strategy Evaluations'
        if section_name in REPORT_STRUCTURE:
            from reporting.content import get_strategy_evaluations_content
            context_strategy_eval = {'strategy_eval_content': get_strategy_evaluations_content()}
            render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_strategy_eval, send_result)
    except Exception as e:
        logging.warning(f"Could not generate Strategy Evaluations appendix: {e}")

    # === Advanced Statistics Appendix Section ===
    # OLD CODE - Being replaced by manifest-driven approach
    # send_result('intro', get_section_intro("Advanced Statistics Appendix"), section='Appendices', sub_section='Advanced Statistics')
    # structured_adv_stats = prepare_advanced_stats_table(final_stats, sim_params)
    # send_result('advanced_stats_table', structured_adv_stats, section='Appendices', sub_section='Advanced Statistics')
    
    # NEW: Manifest-driven rendering for "Appendices: Advanced Statistics" section
    section_name = 'Appendices: Advanced Statistics'
    if section_name in REPORT_STRUCTURE:
        context_adv_stats = {
            'advanced_stats': prepare_advanced_stats_table(final_stats, sim_params)
        }
        render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_adv_stats, send_result)
    
    # === Glossary Appendix Section ===
    # OLD CODE - Being replaced by manifest-driven approach
    # glossary_data = get_glossary_data()
    # send_result('glossary', glossary_data, section='Appendices', sub_section='Glossary')
    
    # NEW: Manifest-driven rendering for "Appendices: Glossary" section
    section_name = 'Appendices: Glossary'
    if section_name in REPORT_STRUCTURE:
        context_glossary = {'glossary': get_glossary_data()}
        render_section_for_ui(section_name, REPORT_STRUCTURE[section_name], context_glossary, send_result)

    # === AI Prompt Appendix ===
    # OLD CODE - replaced by manifest-driven approach
    # (Removed broken local config_loader import)
    pass

    record_timing("Appendices Sent")
    
    # === Performance Appendix ===
    # NOTE: This section generates a timing plot - keeping current implementation
    # Future: could migrate to manifest approach with plot generation
    import plotly.graph_objects as go
    timing_df = pd.DataFrame(timing_data)
    timing_fig = go.Figure(data=go.Scatter(
        x=list(range(len(timing_df))),
        y=timing_df['time_seconds'],  # Fixed: use 'time_seconds' not 'elapsed'
        mode='lines+markers',
        name='Elapsed Time'
    ))
    timing_fig.update_layout(
        title='Report Generation Performance',
        xaxis_title='Step',
        yaxis_title='Time (seconds)',
        hovermode='closest'
    )
    timing_fig.update_xaxes(tickvals=list(range(len(timing_df))), ticktext=timing_df['step'].tolist())
    
    send_result('plotly', timing_fig.to_json(), 'Performance Timing', 
                section='Appendices', sub_section='Performance')
    record_timing("Performance Plot Sent")
    logging.info(f"--- Final Timing Data for Sim Hash {simulation_hash[:10]}... ---\n{timing_df.to_string(index=False)}")

    send_progress(1.0, "Done!")
    logging.info(f"--- UI Regeneration COMPLETE for Simulation Hash: {simulation_hash[:10]}... ---")

def _truly_lightweight_debug_process(progress_queue, results_queue, process_key=None):
    """
    A truly lightweight debug process with ZERO non-standard library imports.
    This ensures an almost instantaneous startup time by avoiding all app-specific
    module loading (like config parsing or logging setup), which can cause issues.
    """
    import time
    from datetime import datetime
    import pandas as pd
    import plotly.graph_objects as go

    print(f"[{datetime.now()}] --- Starting Truly Lightweight Debug Process ---")
    
    progress_data = []
    start_time = time.time()

    total_duration_seconds = 5
    progress_increment = 0.05  # 5%
    num_steps = int(1 / progress_increment)
    sleep_per_step = total_duration_seconds / num_steps
    
    for i in range(num_steps + 2): # Loop one extra time to ensure 100% is sent
        progress = min(i * progress_increment, 1.0)
        status = f"Running debug task... {int(progress * 100)}%" if progress < 1.0 else "Debug process complete!"

        if progress_queue:
            progress_queue.put((progress, status))
        
        current_time = time.time() - start_time
        progress_data.append({'time': current_time, 'progress': progress})

        if progress < 1.0:
            time.sleep(sleep_per_step)
        else:
            break # Exit loop after sending 100%
    
    # Generate plot and send to results queue
    df = pd.DataFrame(progress_data)
    fig = go.Figure(data=go.Scatter(x=df['time'], y=df['progress'], mode='lines+markers'))
    fig.update_layout(title="Debug Process: Progress vs. Time", xaxis_title="Time (seconds)", yaxis_title="Progress", yaxis_range=[0, 1])
    
    # Add section and sub-section for correct rendering
    results_queue.put({
        'type': 'plotly', 'data': fig.to_json(), 'caption': 'Debug Process Progress vs. Time',
        'section': 'Debug Output', 'sub_section': 'Performance'
    })

    print(f"[{datetime.now()}] --- Truly Lightweight Debug Process Complete ---")

def generate_pdf_from_ui_data_process(completion_queue, ui_results_list, regeneration_package, simulation_id):
    """
    Generates a PDF report from the already-loaded UI results data.
    This is more efficient as it reuses the data fetched for the 'View' mode.
    This function is designed to be run in a background process.
    """
    # --- All imports are local for process safety ---
    import logging
    import io
    import tempfile
    import os
    import pandas as pd
    from logger import configure_logging
    from reporting.pdf import generate_pdf_report
    from core.shared_logic import get_info_boxes_text
    from reporting.components import prepare_example_path_table
    from reporting.content import INPUT_DATA_PLOT_ORDER, INPUT_DATA_APPENDIX_PLOTS, SIMULATION_PLOT_ORDER

    # This check is necessary because plotly is an optional dependency for this process
    try:
        import plotly.io as pio
        PLOTLY_AVAILABLE = True
    except ImportError:
        PLOTLY_AVAILABLE = False

    configure_logging() # Configure logging for this new process
    logging.info(f"--- Starting PDF Generation from UI Data for Sim ID: {simulation_id} ---")
    try:
        if not PLOTLY_AVAILABLE:
            logging.error("Cannot generate PDF from UI data: 'plotly' and 'kaleido' are not installed.")
            completion_queue.put((False, None))
            return

        sim_params = regeneration_package.get('params', {})
        final_stats = regeneration_package.get('stats', {})
        gemini_content = regeneration_package.get('gemini_content', {})
        average_results_df = regeneration_package.get('precalculated_data', {}).get('average_results_df')
        median_yearly_results_df = regeneration_package.get('precalculated_data', {}).get('median_yearly_results_df')
        
        # Prepare example_path_df from sampled_paths (same logic as UI generation)
        example_path_df = None
        sampled_paths = regeneration_package.get('precalculated_data', {}).get('sampled_paths')
        if sampled_paths is not None and not sampled_paths.empty:
            if isinstance(sampled_paths.columns, pd.MultiIndex):
                sim_name = sampled_paths.columns.levels[0][0]
                raw_example_df = sampled_paths[sim_name]
            else:
                raw_example_df = sampled_paths
            example_path_df = prepare_example_path_table(raw_example_df)

        input_plot_buffers_for_pdf = []
        output_plot_buffers_for_pdf = []
        appendix_plot_buffers_for_pdf = []
        
        # --- EXTRACT PLOTS FROM UI RESULTS LIST ---
        # Plots are sent via send_result('plotly', ...) during UI regeneration
        # They're stored in ui_results_list with section/caption metadata
        
        logging.info(f"Extracting plots from {len(ui_results_list)} UI results...")
        
        # Log all plotly items for debugging
        plotly_items = [item for item in ui_results_list if item.get('type') == 'plotly']
        logging.info(f"Found {len(plotly_items)} plotly items in UI results")
        for item in plotly_items:
            logging.info(f"  - '{item.get('caption')}' in section='{item.get('section')}', sub_section='{item.get('sub_section')}'")
        
        # 1. Extract Main Input Data Plots (section='Input Data Analysis')
        input_plot_captions = [
            'Historical Price (Interactive)',
            'Historical Yearly Returns',
            'Historical Drawdowns'
        ]
        
        for caption in input_plot_captions:
            for item in ui_results_list:
                if (item.get('type') == 'plotly' and 
                    item.get('caption') == caption and 
                    item.get('section') == 'Input Data Analysis'):
                    try:
                        fig = pio.from_json(item['data'])
                        input_plot_buffers_for_pdf.append(io.BytesIO(pio.to_image(fig, format='png')))
                        logging.info(f"Extracted input plot: {caption}")
                    except Exception as e:
                        logging.warning(f"Failed to extract input plot '{caption}': {e}")
                    break
        
        # 2. Extract Appendix Input Data Plots (section='Appendices', sub_section='Input Data Analysis')
        appendix_plot_captions = [
            'Distribution of Rolling 1-Year Returns',
            'Autocorrelation of Daily Returns',
        ]
        
        for caption in appendix_plot_captions:
            for item in ui_results_list:
                if (item.get('type') == 'plotly' and 
                    item.get('caption') == caption and 
                    item.get('section') == 'Appendices' and
                    item.get('sub_section') == 'Input Data Analysis'):
                    try:
                        fig = pio.from_json(item['data'])
                        appendix_plot_buffers_for_pdf.append(io.BytesIO(pio.to_image(fig, format='png')))
                        logging.info(f"Extracted appendix plot: {caption}")
                    except Exception as e:
                        logging.warning(f"Failed to extract appendix plot '{caption}': {e}")
                    break
        
        # 3. Extract Simulation Output Plots (section='Simulation Summary')
        # Order matters - must match SIMULATION_PLOT_ORDER
        output_plot_captions = [
            'Portfolio Value Overview',  # portfolio_value_overview
            'All Simulation Paths (With Percentiles)',  # simulation_paths_log
            'Final Net Worth Distribution',  # final_net_worth_distribution
            'Median Annual Cash Flow Over Time',  # yearly_cash_flow
            'Portfolio Survival Curve'  # survival_curve
        ]
        
        for caption in output_plot_captions:
            for item in ui_results_list:
                if (item.get('type') == 'plotly' and 
                    item.get('caption') == caption and 
                    item.get('section') == 'Simulation Summary'):
                    try:
                        fig = pio.from_json(item['data'])
                        # Apply log scale transformations where needed
                        if 'All Simulation Paths' in caption or 'Final Net Worth Distribution' in caption:
                            fig.update_layout(xaxis_type='log')
                        output_plot_buffers_for_pdf.append(io.BytesIO(pio.to_image(fig, format='png')))
                        logging.info(f"Extracted output plot: {caption}")
                    except Exception as e:
                        logging.warning(f"Failed to extract output plot '{caption}': {e}")
                    break
        
        # 4. Extract Verdict Gauge (section='Executive Summary')
        logging.info(f"Searching for Verdict Gauge in {len(ui_results_list)} UI results...")
        verdict_plot_buffer = None
        for item in ui_results_list:
            if (item.get('type') == 'plotly' and 
                item.get('caption') == 'Portfolio Survival Assessment' and 
                item.get('section') == 'Executive Summary'):
                try:
                    fig = pio.from_json(item['data'])
                    verdict_plot_buffer = io.BytesIO(pio.to_image(fig, format='png', width=600, height=350))
                    logging.info("Extracted Verdict Gauge for PDF")
                except Exception as e:
                    logging.warning(f"Failed to extract Verdict Gauge: {e}")
                break
        
        if not verdict_plot_buffer:
            logging.warning("⚠️ Verdict Gauge NOT found in UI results")
        else:
            logging.info("✅ Verdict Gauge extracted successfully")

        logging.info("All data prepared. Generating final PDF.")
        info_for_pdf = get_info_boxes_text(sim_params, final_stats)
        from reporting.content import OUTPUT_PLOT_KEYS, STRATEGY_DESCRIPTIONS
        output_plot_keys = OUTPUT_PLOT_KEYS

        # Generate AI prompt text for the appendix
        gemini_prompt_text = ""
        if sim_params.get('show_ai_prompt', False):
            try:
                from reporting.analysis import get_gemini_analysis_prompt
                strategy_key = sim_params.get('strategy', '')
                if strategy_key == 'custom':
                    strategy_desc = sim_params.get('custom_strategy_description', 'A custom strategy.')
                else:
                    strategy_desc = STRATEGY_DESCRIPTIONS.get(strategy_key, strategy_key.replace('_', ' ').title())
                gemini_prompt_text = get_gemini_analysis_prompt(sim_params, final_stats, sim_params.get('currency', DEFAULT_CURRENCY), strategy_desc)
            except Exception as e:
                logging.warning(f"Could not generate AI prompt for PDF: {e}")

        pdf_buffer = generate_pdf_report(sim_params, input_plot_buffers_for_pdf, output_plot_buffers_for_pdf, output_plot_keys, info_for_pdf, gemini_content.get('analysis', ''), gemini_prompt_text, {}, final_stats, average_results_df, median_yearly_results_df, example_path_df, gemini_content.get('main_outcome', ''), gemini_content.get('bottom_line', ''), appendix_plot_buffers=appendix_plot_buffers_for_pdf, verdict_plot_buffer=verdict_plot_buffer, to_buffer=True)
        
        # Save buffer to a temporary file and pass the path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(pdf_buffer.getbuffer())
            temp_file_path = temp_pdf.name

        completion_queue.put((True, temp_file_path))
        logging.info(f"--- PDF Generation from UI Data COMPLETE for Sim ID: {simulation_id} ---")
    except Exception as e:
        logging.error(f"Error in generate_pdf_from_ui_data_process: {e}", exc_info=True)
        completion_queue.put((False, None))


# --- PDF Background Worker Functions ---

def pdf_worker_process(stop_event):
    """
    Background worker that generates PDFs for pending simulations.
    Runs continuously until stop_event is set.
    
    This is a top-level function designed to be run in a separate process.
    
    Args:
        stop_event: multiprocessing.Event to signal worker shutdown
    """
    import time
    import logging
    from logger import configure_logging
    from db.database import db
    from db.pdf_storage import get_pdf_storage
    
    configure_logging()
    logging.info("🚀 PDF worker process started")
    
    storage = get_pdf_storage()
    
    # Initialize cleanup timer to run shortly after startup, then daily
    last_cleanup_time = 0 
    CLEANUP_INTERVAL = 86400 # 24 hours
    
    while not stop_event.is_set():
        # --- Periodic Retention Cleanup ---
        current_time = time.time()
        if current_time - last_cleanup_time > CLEANUP_INTERVAL:
            try:
                logging.info("🧹 Starting daily simulation retention cleanup...")
                # Verify method exists (it might not on SnowflakeDatabase yet)
                if hasattr(db, 'cleanup_old_simulations'):
                    deleted_count = db.cleanup_old_simulations()
                    logging.info(f"✅ Daily cleanup complete. Soft-deleted {deleted_count} old simulations.")
                else:
                    logging.warning("⚠️ cleanup_old_simulations not implemented on current database backend.")
                
                last_cleanup_time = current_time
            except Exception as e:
                logging.error(f"❌ Error during daily retention cleanup: {e}")

        try:
            # Get pending simulations
            pending = db.get_simulations_needing_pdf(limit=5)
            
            if not pending:
                time.sleep(10)  # Wait before checking again
                continue
            
            logging.info(f"Found {len(pending)} simulations needing PDF generation")
            
            for sim in pending:
                if stop_event.is_set():
                    break
                
                simulation_hash = sim['simulation_hash']
                
                try:
                    # Mark as processing
                    db.update_simulation_pdf_storage(
                        simulation_hash=simulation_hash,
                        storage_path=None,
                        status='processing'
                    )
                    
                    logging.info(f"📄 Generating PDF for {simulation_hash[:10]}...")
                    
                    # Generate PDF using helper function
                    start_time = time.time()
                    pdf_buffer = _generate_pdf_for_simulation(simulation_hash)
                    gen_time_ms = int((time.time() - start_time) * 1000)
                    
                    # Save using storage abstraction
                    storage_path = storage.save_pdf(simulation_hash, pdf_buffer)
                    
                    # Update database
                    db.update_simulation_pdf_storage(
                        simulation_hash=simulation_hash,
                        storage_path=storage_path,
                        status='ready',
                        gen_time_ms=gen_time_ms
                    )
                    
                    logging.info(f"✅ PDF generated successfully for {simulation_hash[:10]}... in {gen_time_ms}ms")
                    
                except Exception as e:
                    logging.error(f"❌ PDF generation failed for {simulation_hash[:10]}...: {e}", exc_info=True)
                    db.update_simulation_pdf_storage(
                        simulation_hash=simulation_hash,
                        storage_path=None,
                        status='failed',
                        error_msg=str(e)[:500]  # Limit error message length
                    )
        
        except Exception as e:
            logging.error(f"PDF worker error: {e}", exc_info=True)
            time.sleep(10)
    
    logging.info("🛑 PDF worker process stopped")


def _generate_pdf_for_simulation(simulation_hash):
    """
    Helper function to generate PDF for a simulation.
    Loads simulation data and generates PDF using existing logic.
    
    Args:
        simulation_hash: Simulation identifier
        
    Returns:
        BytesIO buffer containing the PDF
    """
    from reporting.pdf import generate_pdf_report
    from reporting.content import INPUT_DATA_PLOT_ORDER, SIMULATION_PLOT_ORDER
    from reporting.components import prepare_example_path_table
    from core.shared_logic import get_info_boxes_text
    from db.regeneration_db import get_regeneration_data, load_asset_data_from_cache
    from core.data import _generate_asset_key
    from reporting.interactive_plotting import (
        plot_price_history_interactive, plot_yearly_returns_interactive,
        plot_rolling_returns_histogram_interactive, plot_autocorrelation_interactive,
        plot_historical_drawdowns_interactive, plot_portfolio_value_overview_interactive,
        plot_cashflow_liabilities_interactive, plot_all_simulation_paths_interactive,
        plot_cashflow_liabilities_interactive, plot_all_simulation_paths_interactive,
        plot_final_net_worth_distribution_interactive, plot_yearly_cash_flow_interactive,
        plot_survival_curve_interactive
    )
    import plotly.io as pio
    import pandas as pd
    import io
    import logging
    
    # Load simulation data
    regeneration_package = get_regeneration_data(simulation_hash)
    
    sim_params = regeneration_package.get('params', {})
    final_stats = regeneration_package.get('stats', {})
    gemini_content = regeneration_package.get('gemini_content', {})
    precalculated_data = regeneration_package.get('precalculated_data', {})
    
    # Load input data with proper date slicing
    # Use load_and_prepare_data() instead of load_asset_data_from_cache() to ensure
    # the data is sliced according to bootstrap_start_date/bootstrap_end_date parameters
    from core.data import load_and_prepare_data
    input_data_dict = load_and_prepare_data(sim_params)
    
    # Prepare DataFrames
    average_results_df = precalculated_data.get('average_results_df')
    median_yearly_results_df = precalculated_data.get('median_yearly_results_df')
    
    # Prepare example path
    example_path_df = None
    sampled_paths = precalculated_data.get('sampled_paths')
    if sampled_paths is not None and not sampled_paths.empty:
        if isinstance(sampled_paths.columns, pd.MultiIndex):
            raw_example_df = sampled_paths[sampled_paths.columns.levels[0][0]]
        else:
            raw_example_df = sampled_paths
        example_path_df = prepare_example_path_table(raw_example_df)
    
    # Generate input plots
    input_plot_buffers = []
    
    if input_data_dict:
        logging.info("Re-generating input data plots for PDF...")
        
        # Import plotting functions
        from reporting.interactive_plotting import (
            plot_price_history_interactive, plot_yearly_returns_interactive,
            plot_rolling_returns_histogram_interactive, plot_autocorrelation_interactive,
            plot_historical_drawdowns_interactive
        )
        from reporting.content import INPUT_REPORT_STRUCTURE, generate_plots_from_structure
        
        # Prepare data context for plot generation
        data_context = {
            'prices': input_data_dict['prices'],
            'asset_name': input_data_dict['asset_name'],
            'params': sim_params,
            'yearly_returns': input_data_dict.get('yearly_returns'),
            'rolling_annual_returns': input_data_dict['rolling_annual_returns'],
            'rolling_returns_stats': final_stats.get('rolling_returns_stats'),
            'acf_data': final_stats.get('acf_data'),
            'drawdown_data': final_stats.get('drawdown_data'),
        }
        
        # Map function names to actual functions
        plotting_functions = {
            'plot_price_history_interactive': plot_price_history_interactive,
            'plot_yearly_returns_interactive': plot_yearly_returns_interactive,
            'plot_rolling_returns_histogram_interactive': plot_rolling_returns_histogram_interactive,
            'plot_autocorrelation_interactive': plot_autocorrelation_interactive,
            'plot_historical_drawdowns_interactive': plot_historical_drawdowns_interactive,
        }
        
        # Generate all plots from structure
        plot_results = generate_plots_from_structure(INPUT_REPORT_STRUCTURE, data_context, plotting_functions)
        
        # Convert plots to PNG buffers for PDF
        for result in plot_results:
            if result['type'] == 'plot':
                input_plot_buffers.append(io.BytesIO(pio.to_image(result['fig'], format='png')))
    
    # Regenerate output plots from precalculated data using centralized structure
    logging.info("Re-generating simulation output plots for PDF...")
    
    output_plot_buffers = []
    net_worth_percentile_paths = precalculated_data.get('net_worth_percentile_paths')
    asset_percentile_paths = precalculated_data.get('asset_percentile_paths')
    final_net_worths_hist = precalculated_data.get('final_net_worths_hist')
    sampled_paths = precalculated_data.get('sampled_paths')
    backtest_path = precalculated_data.get('backtest_path')
    dummy_df = pd.DataFrame()
    
    # Import plotting functions
    from reporting.interactive_plotting import (
        plot_all_simulation_paths_interactive, plot_final_net_worth_distribution_interactive,
        plot_portfolio_value_overview_interactive, plot_cashflow_liabilities_interactive,
        plot_yearly_cash_flow_interactive
    )
    from reporting.content import SIMULATION_REPORT_STRUCTURE, generate_plots_from_structure
    from core.simulation_currency import get_simulation_currency
    
    currency = get_simulation_currency(sim_params)
    
    # Prepare data context for plot generation
    data_context = {
        'dummy_df': dummy_df,
        'sampled_paths': sampled_paths,
        'params': sim_params,
        'final_stats': final_stats,
        'asset_percentile_paths': asset_percentile_paths,
        'net_worth_percentile_paths': net_worth_percentile_paths,
        'final_net_worths_hist': final_net_worths_hist,
        'backtest_path': backtest_path,
        'currency': currency,
        'currency': currency,
        'theme': 'light', # PDF always uses light theme (white paper)
        'survival_rates': final_stats.get('survival_rates_by_year'),
    }
    
    # Map function names to actual functions
    plotting_functions = {
        'plot_all_simulation_paths_interactive': plot_all_simulation_paths_interactive,
        'plot_final_net_worth_distribution_interactive': plot_final_net_worth_distribution_interactive,
        'plot_portfolio_value_overview_interactive': plot_portfolio_value_overview_interactive,
        'plot_cashflow_liabilities_interactive': plot_cashflow_liabilities_interactive,
        'plot_yearly_cash_flow_interactive': plot_yearly_cash_flow_interactive,
        'plot_cashflow_liabilities_interactive': plot_cashflow_liabilities_interactive,
        'plot_yearly_cash_flow_interactive': plot_yearly_cash_flow_interactive,
        'plot_survival_curve_interactive': plot_survival_curve_interactive,
    }
    
    # Generate all plots from structure
    plot_results = generate_plots_from_structure(SIMULATION_REPORT_STRUCTURE, data_context, plotting_functions)
    
    # Convert plots to PNG buffers for PDF
    for result in plot_results:
        if result['type'] == 'plot':
            output_plot_buffers.append(io.BytesIO(pio.to_image(result['fig'], format='png')))
        elif result['type'] == 'plot_group':
            # Add each plot in the group
            for plot_data in result['plots']:
                output_plot_buffers.append(io.BytesIO(pio.to_image(plot_data['fig'], format='png')))
    
    # Generate appendix plots (technical charts)
    appendix_plot_buffers = []
    if input_data_dict:
        logging.info("Re-generating appendix plots for PDF...")
        from reporting.content import INPUT_DATA_APPENDIX_STRUCTURE
        
        # Reuse the same data_context and plotting_functions from input plots
        data_context = {
            'prices': input_data_dict['prices'],
            'asset_name': input_data_dict['asset_name'],
            'params': sim_params,
            'rolling_annual_returns': input_data_dict['rolling_annual_returns'],
            'rolling_returns_stats': final_stats.get('rolling_returns_stats'),
            'acf_data': final_stats.get('acf_data'),
        }
        
        plotting_functions = {
            'plot_rolling_returns_histogram_interactive': plot_rolling_returns_histogram_interactive,
            'plot_autocorrelation_interactive': plot_autocorrelation_interactive,
        }
        
        plot_results = generate_plots_from_structure(INPUT_DATA_APPENDIX_STRUCTURE, data_context, plotting_functions)
        
        for result in plot_results:
            if result['type'] == 'plot':
                appendix_plot_buffers.append(io.BytesIO(pio.to_image(result['fig'], format='png')))
    
    # Generate verdict gauge
    logging.info("=== VERDICT GAUGE GENERATION START ===")
    verdict_plot_buffer = None
    try:
        from reporting.executive_visuals import create_verdict_traffic_light
        logging.info("Re-generating Verdict Gauge for PDF...")
        verdict_fig = create_verdict_traffic_light(final_stats)
        logging.info(f"Verdict figure created: {verdict_fig is not None}")
        if verdict_fig:
            verdict_plot_buffer = io.BytesIO(pio.to_image(verdict_fig, format='png', width=600, height=350))
            logging.info(f"✅ Successfully generated Verdict Gauge for PDF (buffer size: {len(verdict_plot_buffer.getvalue())} bytes)")
        else:
            logging.warning("⚠️ Verdict figure was None")
    except Exception as e:
        logging.error(f"❌ Could not generate Verdict Gauge for PDF: {e}", exc_info=True)
    
    
    # Prepare info boxes and plot keys
    info_for_pdf = get_info_boxes_text(sim_params, final_stats)
    from reporting.content import OUTPUT_PLOT_KEYS
    output_plot_keys = OUTPUT_PLOT_KEYS
    
    # Prepare data dict for PDF
    data_for_pdf = input_data_dict.copy() if input_data_dict else {}
    
    # Ensure historical_stats is available for the Asset Information table
    # final_stats contains a nested 'historical_stats' dict with the actual asset statistics
    if 'historical_stats' not in data_for_pdf and final_stats:
        # Extract the historical_stats sub-dict from final_stats (not the entire final_stats)
        data_for_pdf['historical_stats'] = final_stats.get('historical_stats', {})
    
    # Generate PDF
    # Generate AI prompt text for the appendix if enabled
    gemini_prompt_text = ""
    if sim_params.get('show_ai_prompt', False):
        try:
            from reporting.analysis import get_gemini_analysis_prompt
            from reporting.content import STRATEGY_DESCRIPTIONS
            strategy_key = sim_params.get('strategy', '')
            if strategy_key == 'custom':
                strategy_desc = sim_params.get('custom_strategy_description', 'A custom strategy.')
            else:
                strategy_desc = STRATEGY_DESCRIPTIONS.get(strategy_key, strategy_key.replace('_', ' ').title())
            gemini_prompt_text = get_gemini_analysis_prompt(sim_params, final_stats, sim_params.get('currency', DEFAULT_CURRENCY), strategy_desc)
        except Exception as e:
            logging.warning(f"Could not generate AI prompt for PDF: {e}")

    pdf_buffer = generate_pdf_report(
        sim_params, input_plot_buffers, output_plot_buffers, output_plot_keys,
        info_for_pdf, gemini_content.get('analysis', ''), gemini_prompt_text, data_for_pdf,
        final_stats, average_results_df, median_yearly_results_df, example_path_df,
        gemini_content.get('main_outcome', ''), gemini_content.get('bottom_line', ''),
        appendix_plot_buffers=appendix_plot_buffers,
        verdict_plot_buffer=verdict_plot_buffer,
        to_buffer=True
    )
    
    return pdf_buffer


def run_strategy_evaluation_process(progress_queue, completion_queue, strategy_configs, process_key=None):
    """
    Background process to evaluate multiple strategies across standardized scenarios.
    
    Args:
        progress_queue: For progress updates (0.0 to 1.0, status_text)
        completion_queue: Put results when done
        strategy_configs: List of config dicts with keys:
            - class: Strategy class (for built-in) or None (for custom)
            - name: Display name for strategy
            - params: Additional parameters
            - is_custom: True for custom strategies
            - user_id: User ID for custom strategies
            - custom_strategy_id: ID in CUSTOM_STRATEGIES table
            - code: Strategy code (for custom strategies)
            - class_name: Class name to extract from code (for custom)
        process_key: Process identifier
    """
    from logger import configure_logging
    configure_logging()
    import logging
    
    from core.strategy_evaluation import evaluate_strategy
    from core.sandbox import execute_strategy_code
    from db.database import db
    
    logging.info(f"===== Starting strategy evaluation process (PID: {process_key}) =====")
    
    results = []
    total = len(strategy_configs)
    
    for i, config in enumerate(strategy_configs):
        name = config['name']
        progress_queue.put(((i / total), f"Evaluating {name} across 8 scenarios..."))
        
        try:
            logging.info(f"[{i+1}/{total}] Evaluating {name}")
            
            # Get strategy class - either from config or by loading code
            if config.get('is_custom') and config.get('code'):
                # Dynamically load custom strategy from code
                logging.info(f"  Loading custom strategy code for {name}")
                strategy_class = execute_strategy_code(config['code'], config['class_name'])
            else:
                # Use built-in strategy class
                strategy_class = config['class']
            
            # Run evaluation
            eval_result = evaluate_strategy(strategy_class, name, config.get('params', {}))
            
            # Add custom strategy tracking fields
            if config.get('is_custom'):
                eval_result['user_id'] = config.get('user_id')
                eval_result['is_custom'] = True
                eval_result['custom_strategy_id'] = config.get('custom_strategy_id')
            
            # Save to database
            eval_id = db.save_strategy_evaluation(eval_result)
            
            if eval_id:
                results.append({'strategy': name, 'status': 'success', 'score': eval_result['excellence_score']})
                logging.info(f"✓ {name}: {eval_result['excellence_score']:.2f}/100")
            else:
                results.append({'strategy': name, 'status': 'failed', 'error': 'Database save failed'})
                
        except Exception as e:
            logging.error(f"Failed to evaluate {name}: {e}", exc_info=True)
            results.append({'strategy': name, 'status': 'failed', 'error': str(e)})
    
    progress_queue.put((1.0, f"Evaluation complete! ({len([r for r in results if r['status'] == 'success'])}/{total} succeeded)"))
    completion_queue.put(results)
    logging.info(f"===== Strategy evaluation process complete =====")

