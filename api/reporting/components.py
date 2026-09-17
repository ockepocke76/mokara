"""
This module centralizes the data preparation and formatting logic for report components.

The functions in this module take raw simulation data (e.g., DataFrames, stats dictionaries)
and transform it into a display-ready format. This creates a "single source of truth"
for how data is presented, which is then consumed by different rendering endpoints
like the PDF generator (`reporting/pdf.py`) and the UI generator (`background_tasks.py`).

This approach eliminates code duplication and ensures consistency across all reports.
"""
from collections import defaultdict
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from config import CONFIG # Needed for _get_config_by_path and parameter definitions
from core.param_layout import get_sidebar_layout # Needed to build the layout structure
from core.strategy import TrinityStrategy, BuyBorrowDieStrategy # Needed for strategy display names

def prepare_average_results_table(average_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepares and formats the 'Average Yearly Results' DataFrame for display.

    This function handles column selection based on strategy and formats all
    numerical values into display-ready strings.

    Args:
        average_results_df (pd.DataFrame): The raw, unformatted average results.

    Returns:
        pd.DataFrame: A formatted DataFrame ready for rendering.
    """
    if average_results_df is None or average_results_df.empty:
        return pd.DataFrame()

    df_for_table = average_results_df.copy()
    df_for_table.index.name = 'Year'
    df_for_table = df_for_table.reset_index()

    # --- FIX: Select and order a standardized set of columns for display. ---
    # This ensures the table is clean and consistent for any strategy.
    final_cols = [
        'Year', 'Asset Value', 'Cash', 'Debt', 'Net Worth', 'LTV',
        'Consumption Delivered', 'Amount Sold', 'Amount Contributed', 'Total Annual Costs', 'Costs / Net Worth'
    ]
    existing_cols = [col for col in final_cols if col in df_for_table.columns]
    df_for_table = df_for_table[existing_cols]

    # Format numeric columns into strings
    for col in df_for_table.columns:
        if col == 'LTV':
            # Format LTV as a percentage
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{x:.1%}")
        elif col == 'Costs / Net Worth':
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{x:.1%}")
        elif col != 'Year':
            # Divide by 1000 and format with thousand separators
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{int(x / 1000):,}".replace(',', ' '))

    return df_for_table

def prepare_median_yearly_results_table(median_yearly_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepares and formats the 'Median Yearly Results' DataFrame for display.

    This function handles column selection based on strategy and formats all
    numerical values into display-ready strings.

    Args:
        median_yearly_results_df (pd.DataFrame): The raw, unformatted median results.

    Returns:
        pd.DataFrame: A formatted DataFrame ready for rendering.
    """
    if median_yearly_results_df is None or median_yearly_results_df.empty:
        return pd.DataFrame()

    df_for_table = median_yearly_results_df.copy()
    df_for_table.index.name = 'Year'
    df_for_table = df_for_table.reset_index()

    # --- FIX: Select and order a standardized set of columns for display. ---
    # This ensures the table is clean and consistent for any strategy.
    final_cols = [
        'Year', 'Asset Value', 'Cash', 'Debt', 'Net Worth', 'LTV',
        'Consumption Delivered', 'Amount Sold', 'Amount Contributed', 'Total Annual Costs', 'Costs / Net Worth'
    ]
    existing_cols = [col for col in final_cols if col in df_for_table.columns]
    df_for_table = df_for_table[existing_cols]

    # Format numeric columns into strings
    for col in df_for_table.columns:
        if col == 'LTV':
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{x:.1%}")
        elif col == 'Costs / Net Worth':
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{x:.1%}")
        elif col != 'Year':
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{int(x / 1000):,}".replace(',', ' '))

    return df_for_table

def prepare_market_scenarios_table() -> List[Dict[str, str]]:
    """
    Creates a static reference list defining the 8 standardized market scenarios.
    Formatted as Key-Value pairs for the 'key_value_table' renderer.
    
    Returns:
        List[Dict[str, str]]: A list of dicts with 'label' and 'value'.
    """
    scenarios = [
        ("1. Bull Market",       "12%", "15%", "15%"),
        ("2. Normal Market",     "8%",  "18%", "25%"),
        ("3. Bear Market",       "-2%", "20%", "20%"),
        ("4. High Volatility",   "8%",  "30%", "15%"),
        ("5. Low Volatility",    "5%",  "10%", "10%"),
        ("6. Extreme Bull",      "20%", "25%", "5%"),
        ("7. Extreme Bear",      "-10%","35%", "5%"),
        ("8. Sideways Market",   "3%",  "22%", "5%"),
    ]
    
    table_data = []
    for name, ret, vol, wgt in scenarios:
        # Format: Label="Scenario (Weight)", Value="Return / Volatility"
        table_data.append({
            "label": f"{name} ({wgt} weight)",
            "value": f"Return: {ret} | Volatility: {vol}"
        })
        
    return table_data

def _generate_transaction_summary(row: pd.Series) -> str:
    """
    Generates a human-readable summary of the financial transactions for a given year.

    Args:
        row (pd.Series): A row from the simulation results DataFrame for a single year.

    Returns:
        str: A concise, narrative summary of the year's events.
    """
    # Year 0 is always the initial investment
    if row.name == 0:
        return f"Initial Investment: Bought {int(row.get('Amount Bought', 0) / 1000):,}k of assets."


    # Helper to safely convert values to float
    def safe_float(val):
        """Convert value to float, handling strings and None."""
        if val is None or val == '':
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
    
    # --- Extract all relevant financial actions for the year ---
    amount_sold = safe_float(row.get('Amount Sold', 0))
    amount_bought = safe_float(row.get('Amount Bought', 0))
    amount_contributed = safe_float(row.get('Amount Contributed', 0))
    debt_increase = safe_float(row.get('Debt Change', 0))
    drawdown = safe_float(row.get('Consumption Delivered', 0))

    # Calculate total costs directly from the row's data
    interest_paid = safe_float(row.get('Interest Paid', 0))
    tax_paid = safe_float(row.get('Tax Paid', 0))
    fees_paid = safe_float(row.get('Fees Paid', 0))
    
    total_costs_k = int((interest_paid + tax_paid + fees_paid) / 1000)
    tax_paid_k = int(tax_paid / 1000)
    drawdown_k = int(drawdown / 1000)

    # --- Build the summary string piece by piece for clarity ---
    summary_parts = []

    # --- Priority 1: Deleveraging Event ---
    # A deleveraging event is a sale specifically to repay debt.
    if amount_sold > 0 and row.get('Debt Change', 0) < 0:
        debt_repayment_k = int(abs(row.get('Debt Change', 0)) / 1000)
        summary_parts.append(f"Deleveraging: Sold {int(amount_sold / 1000):,}k to repay {debt_repayment_k:,}k debt and pay {tax_paid_k:,}k tax.")
        # A deleveraging event is the primary story, so we can usually return here.
        return " ".join(summary_parts)

    # --- Priority 2: Standard Asset Sale (e.g., Trinity, Stay Rich phase) ---
    if amount_sold > 0:
        funding_reasons = []
        amount_sold_k = int(amount_sold / 1000)

        # Calculate the portion of the sale that went to cash reserves
        cash_outflows_k = drawdown_k + total_costs_k
        cash_buffer_increase_k = amount_sold_k - cash_outflows_k

        if drawdown_k > 0: funding_reasons.append(f"{drawdown_k:,}k drawdown")
        if total_costs_k > 0: funding_reasons.append(f"{total_costs_k:,}k costs")
        if cash_buffer_increase_k > 0: funding_reasons.append(f"{cash_buffer_increase_k:,}k cash reserve")
        
        if funding_reasons:
            # Use a more natural phrasing
            summary_parts.append(f"Sold {amount_sold_k:,}k to fund {', '.join(funding_reasons)}.")
        else: # A sale occurred but not for drawdown or costs (e.g., to build a cash buffer)
            summary_parts.append(f"Sold {int(amount_sold / 1000):,}k to increase cash reserves.")

    # --- Priority 3: Standard Borrowing (e.g., BBD) ---
    if debt_increase > 0:
        funding_reasons = []
        if drawdown_k > 0: funding_reasons.append(f"{drawdown_k:,}k drawdown")
        if total_costs_k > 0: funding_reasons.append(f"{total_costs_k:,}k costs")
        
        if funding_reasons:
            summary_parts.append(f"Borrowed {int(debt_increase / 1000):,}k to fund {', '.join(funding_reasons)}.")
        else: # Borrowing occurred but not for drawdown or costs (e.g., to buy assets)
            summary_parts.append(f"Borrowed {int(debt_increase / 1000):,}k.")

    # --- Priority 4: Contributions & Asset Purchases ---
    if amount_contributed > 0:
        if total_costs_k > 0:
            summary_parts.append(f"Contributed {int(amount_contributed / 1000):,}k to cover {total_costs_k:,}k costs and for investment.")
        else:
            summary_parts.append(f"Contributed {int(amount_contributed / 1000):,}k.")

    if amount_bought > 0:
        summary_parts.append(f"Bought {int(amount_bought / 1000):,}k of assets.")

    # --- Fallback for years with no major transactions ---
    if not summary_parts:
        if total_costs_k > 0:
            return f"Incurred {total_costs_k:,}k in passive costs (interest/fees)."
        return "No significant transactions."

    return " ".join(summary_parts)

def prepare_example_path_table(raw_example_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepares and formats a single example simulation path DataFrame for display.

    This function handles column selection and formats all numerical values
    into display-ready strings (in thousands of SEK). It also generates
    a transaction summary column.

    Args:
        raw_example_df (pd.DataFrame): The raw, unformatted DataFrame for a single simulation path.

    Returns:
        pd.DataFrame: A formatted DataFrame ready for rendering.
    """
    if raw_example_df is None or raw_example_df.empty:
        return pd.DataFrame()

    # --- FIX: Pivot the incoming "long" data to "wide" format. ---
    # The raw_example_df arrives with a (Year, Metric) MultiIndex. We need to
    # unstack the 'Metric' level to turn metrics into columns, which is the
    # format expected by the rest of this function.
    if isinstance(raw_example_df.index, pd.MultiIndex):
        raw_example_df = raw_example_df.unstack(level='Metric')
        # --- FIX: Remove the name from the columns index after unstacking. ---
        # The .unstack() operation on a Series gives the columns a 'name' attribute ('Metric').
        # If this name is present when .reset_index() is called later, pandas creates a MultiIndex on the columns.
        # Clearing the name attribute here prevents this, ensuring a flat column index for all subsequent operations.
        
        # If unstacking created a MultiIndex on the columns, flatten it by taking the metric names.
        if isinstance(raw_example_df.columns, pd.MultiIndex):
            raw_example_df.columns = raw_example_df.columns.get_level_values(1)

        raw_example_df.columns.name = None
        # Convert all column names to strings to avoid mixed-type warning
        raw_example_df.columns = raw_example_df.columns.astype(str)

    # --- NEW: Check for and handle duplicate columns before processing ---
    if raw_example_df.columns.has_duplicates:
        import logging
        
        # Find all duplicate columns
        dupes = raw_example_df.columns[raw_example_df.columns.duplicated()].unique()

        # Define columns for which duplicates are expected due to the data generation process.
        # For these, we will silently use the first instance.
        EXPECTED_DUPLICATE_METRICS = [
            'Accumulated Fees', 'Accumulated Interest', 'Accumulated Tax', 'Amount Bought', 
            'Amount Contributed', 'Amount Sold', 'Consumption Delivered', 'Asset Value', 'Cash', 
            'Cash Interest', 'Debt', 'Debt Change', 'Fees Paid', 'Interest Paid', 'Net Worth', 'Tax Paid'
        ]

        # Warn about any UNEXPECTED duplicate columns.
        unexpected_dupes = [d for d in dupes if d not in EXPECTED_DUPLICATE_METRICS]
        if unexpected_dupes:
            logging.warning(
                f"Data for example path has unexpected duplicate columns: {unexpected_dupes}. "
                "This may indicate an issue in data preparation. Only the first instance of each column will be used."
            )

        # For each duplicate column NOT in the expected list, check if values are consistent.
        for col in unexpected_dupes:
            dupe_cols_df = raw_example_df.loc[:, col]
            # Check if all values in each row of the duplicated columns are the same
            is_consistent = dupe_cols_df.apply(lambda row: row.nunique(dropna=False) <= 1, axis=1)
            if not is_consistent.all():
                inconsistent_rows = dupe_cols_df[~is_consistent]
                for idx, row_values in inconsistent_rows.iterrows():
                    logging.warning(
                        f"Unexpected duplicate column '{col}' has different values at index {idx}. "
                        f"Values: {row_values.tolist()}. Using the first instance."
                    )
        
        # De-duplicate columns by taking the first instance. This prevents errors in downstream processing.
        raw_example_df = raw_example_df.loc[:, ~raw_example_df.columns.duplicated(keep='first')]


    df_for_table = raw_example_df.copy()
    df_for_table.index.name = 'Year'


    # --- FIX: Generate the summary column before resetting the index. ---
    # This now works correctly because raw_example_df has a simple column index.
    df_for_table['Transactions'] = raw_example_df.apply(_generate_transaction_summary, axis=1)
    
    # Check if 'Year' already exists as a column (not just in index)
    if 'Year' not in df_for_table.columns:
        df_for_table = df_for_table.reset_index()
    # If Year is already a column, just reset index without adding it
    elif df_for_table.index.name == 'Year':
        df_for_table = df_for_table.reset_index(drop=True)

    # --- FIX: Re-add the column selection and formatting logic. ---
    # This logic was accidentally removed, causing the function to return None.

    # Select and format columns based on whether debt was used.
    # Convert Debt to numeric first to avoid string/int comparison errors
    if 'Debt' in df_for_table.columns:
        debt_values = pd.to_numeric(df_for_table['Debt'], errors='coerce').fillna(0)
        has_debt = debt_values.sum() > 0
    else:
        has_debt = False
    
    if has_debt:
        cols_to_show = ['Year', 'Asset Value', 'Cash', 'Debt', 'Net Worth', 'Consumption Delivered', 'Interest Paid', 'Tax Paid', 'Fees Paid', 'Transactions']
    else: # Withdrawal strategy
        cols_to_show = ['Year', 'Asset Value', 'Cash', 'Net Worth', 'Consumption Delivered', 'Amount Sold', 'Tax Paid', 'Fees Paid', 'Transactions']

    # Select only the columns that actually exist in the DataFrame.
    existing_cols_to_show = [col for col in cols_to_show if col in df_for_table.columns]
    df_for_table = df_for_table[existing_cols_to_show]

    # Format numeric columns for display.
    for col in df_for_table.columns:
        if col not in ['Year', 'Transactions']:
            # Divide by 1000 and format with thousand separators.
            df_for_table[col] = df_for_table[col].fillna(0).apply(lambda x: f"{int(x / 1000):,}".replace(',', ' ') if pd.api.types.is_number(x) else x)

    return df_for_table

def _get_config_by_path(config_path: str):
    """Navigates the nested CONFIG dictionary using a dot-separated path."""
    keys = config_path.split('.')
    conf = CONFIG
    for key in keys:
        conf = conf[key]
    return conf

def prepare_settings_table(params: dict) -> List[Dict[str, Any]]:
    """
    Organizes simulation parameters into a structured list for display.

    This function iterates directly over the saved parameters from a simulation run,
    formats them for readability, and groups them into logical sections. This ensures
    that the report accurately reflects exactly what was run.
    """
    from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
    from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy

    layout = get_sidebar_layout()
    grouped_settings = defaultdict(dict)
    
    # --- Robust Extraction of Parameters ---
    import logging
    effective_params = params.get('all_params')
    if not effective_params:
        effective_params = params
        # logging.debug("prepare_settings_table: Using flat params")
    else:
        # logging.debug("prepare_settings_table: Using nested all_params")
        pass
        
    # Overwrite params reference with the effective one for the rest of function
    params = effective_params


    # A mapping to group parameters into sections.
    # The order here defines the order of the sections in the final output.
    section_map = {
        'simulation_name': 'General', 'num_years': 'General', 'num_simulations': 'General', 'initial_investment': 'General',
        'strategy': 'Strategy',
        'asset_model': 'Asset Model', 'annual_return': 'Asset Model', 'annual_volatility': 'Asset Model',
        'return_threshold_rate': 'Asset Model', 'asset_management_fee': 'Asset Model',
        'inflation_rate': 'Economic Assumptions', 'cash_interest_rate': 'Economic Assumptions', 'loan_interest_rate': 'Economic Assumptions',
        'tax_method': 'Tax', 'isk_tax_rate': 'Tax', 'capital_gains_tax_rate': 'Tax',
    }

    # A list of internal or irrelevant parameters to exclude from the report.
    exclude_keys = [
        'user_email', 'user_name', 'gemini_api_key', 'process_key', 'is_prod_env',
        'all_annual_returns_for_stats', 'historical_daily_returns_for_stats',
        'custom_strategy_code', 'custom_strategy_class_name', 'custom_strategy_params',
        'component_hashes', 'all_params', 'is_replacement_run', 'asset_key',
        'local_file_path', 'date_column', 'price_column', 'start_date', 'end_date',
        'num_years_backtest', '_disable_cache'
    ]

    # --- Step 1: Process all known, general parameters ---
    for key, value in params.items():
        if key in exclude_keys or not section_map.get(key):
            continue

        section = section_map.get(key)
        label = key.replace('_', ' ').title()

        # Format the value for display
        formatted_value = str(value)
        if isinstance(value, bool):
            formatted_value = "Enabled" if value else "Disabled"
        elif isinstance(value, float):
            if 'rate' in key or 'threshold' in key or 'fee' in key or 'percent' in key:
                formatted_value = f"{value:.2%}"
            else:
                formatted_value = f"{value:,.2f}"
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
        elif key == 'strategy':
                if value == 'custom':
                    # For custom strategies, use the specific name.
                    formatted_value = params.get('custom_strategy_name', 'Custom Strategy')
                else:
                    # For built-in strategies, use their display_name.
                    from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy
                    strategy_class_map = {'trinity': TrinityStrategy, 'buy_borrow_die': BuyBorrowDieStrategy, 'get_rich_stay_rich': GetRichStayRichStrategy}
                    strategy_class = strategy_class_map.get(value)
                    formatted_value = getattr(strategy_class, 'display_name', str(value).replace('_', ' ').title()) if strategy_class else str(value).replace('_', ' ').title()
        elif key == 'asset_model':
            # Use asset metadata from params (populated from assets.yml)
            display_name = params.get('asset_name', str(value).replace('_', ' ').title())
            ticker = params.get('ticker_symbol')
            formatted_value = f"{display_name} ({ticker})" if ticker else display_name
        else:
            formatted_value = str(value).replace('_', ' ').title()

        grouped_settings[section][label] = formatted_value

    # --- Step 2: Process strategy-specific parameters ---
    strategy_key = params.get('strategy')
    param_source = {}
    if strategy_key == 'custom':
        # --- FIX: Use the param definitions passed directly in params ---
        # This makes the function stateless and usable in background processes.
        param_source = params.get('custom_strategy_param_defs', {})
    else:
        strategy_class_map = {
            'trinity': TrinityStrategy,
            'buy_borrow_die': BuyBorrowDieStrategy,
            'get_rich_stay_rich': GetRichStayRichStrategy
        }
        strategy_class = strategy_class_map.get(strategy_key)
        if strategy_class:
            # Instantiate strategy to access the parameters property
            strategy_instance = strategy_class(params)
            param_source = strategy_instance.parameters

    for key, config in param_source.items():
        if key in params:
            value = params[key]
            label = config.get('description', key.replace('_', ' ').title())

            if 'slider_format' in config and '%%' in config['slider_format']:
                formatted_value = config['slider_format'] % (value * 100)
            elif 'slider_format' in config and '%d' in config['slider_format']:
                formatted_value = f"{value:,.0f}"
            else:
                formatted_value = str(value)
            
            grouped_settings['Strategy'][label] = formatted_value

    # Convert the defaultdict to the desired list of dictionaries format
    section_order = ['General', 'Strategy', 'Asset Model', 'Economic Assumptions', 'Tax', 'Other']
    final_settings = []
    for section_name in section_order:
        if section_name in grouped_settings:
            final_settings.append({
                "title": section_name,
                "metrics": [{"label": k, "value": v} for k, v in grouped_settings[section_name].items()]
            })

    return final_settings

def prepare_advanced_stats_table(stats: Dict[str, Any], params: Dict[str, Any], currency: str = 'SEK') -> List[Dict[str, Any]]:
    """
    Prepares a structured list of dictionaries for advanced statistics,
    with definitions and calculated values, ready for display.

    Args:
        stats (Dict[str, Any]): The raw statistics dictionary from the simulation.
        params (Dict[str, Any]): The simulation parameters.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing an advanced metric
                              with its name, value, definition, and context.
    """
    metrics_definitions = [
         {
            'name': 'Asset Sharpe Ratio', 'key': 'asset_sharpe_ratio', 'fmt': "{:.2f}",
            'definition': "Measures the risk-adjusted return of the **underlying asset itself**, based on its historical performance (CAGR and volatility). It ignores the strategy's cash flows and simulation outcomes.",
            'sim_context': "This ratio is a stable benchmark of the asset's historical risk-adjusted return. It should be comparable to the 'Sharpe Ratio' in the 'Asset Information' table, though minor differences can occur due to calculation nuances (e.g., arithmetic vs. geometric mean returns).",
            'real_world': "For context, the long-term historical Sharpe Ratio for a broad market index like the S&P 500 is typically in the range of 0.4 to 0.5. This metric allows for a direct comparison to such real-world benchmarks."
        },
        {
            'name': 'Asset Sortino Ratio', 'key': 'asset_sortino_ratio', 'fmt': "{:.2f}",
            'definition': "Similar to the Asset Sharpe Ratio, but only penalizes for downside volatility. It is also calculated using the asset's **historical performance**.",
            'sim_context': "This provides a downside-risk-adjusted view of the underlying asset's historical performance, serving as a stable benchmark.",
            'real_world': "The Sortino Ratio is almost always higher than the Sharpe Ratio. For the S&P 500, it has historically been in the 0.6 to 0.8 range."
        },
        {
            'name': 'Strategy Sharpe Ratio', 'key': 'strategy_sharpe_ratio', 'fmt': "{:.2f}",
            'definition': "Measures the risk-adjusted return of the **entire financial strategy**, accounting for all cash flows (e.g., withdrawals, loans). It is calculated using the Internal Rate of Return (IRR) of each simulation path.",
            'sim_context': "This ratio tells you how much return the overall strategy generated (above inflation) for every unit of risk taken. It is the best metric for comparing the holistic performance of one strategy versus another.",
            'real_world': "This is a custom, strategy-specific metric. It is not directly comparable to the historical Sharpe Ratio of an asset, but values above 1.0 are generally considered very good."
        },
        {
            'name': 'Strategy Sortino Ratio', 'key': 'strategy_sortino_ratio', 'fmt': "{:.2f}",
            'definition': "An improvement on the Strategy Sharpe Ratio, this measures the strategy's excess return per unit of 'downside' risk. It only penalizes for outcomes where the annualized return was less than the risk-free rate.",
            'sim_context': "This answers: 'How much return did my strategy generate for only the downside risk I took on?' It is often more intuitive as it doesn't penalize for 'good' volatility (i.e., better-than-expected returns).",
            'real_world': "Like the Strategy Sharpe, this is a custom metric. A value of 99.0 indicates no downside returns were observed in the simulation, a theoretically perfect outcome."
        },
        {
            'name': 'Value at Risk (95%)', 'key': 'var_95_loss', 'fmt': f"{{:,.0f}} {currency}",
            'definition': "A statistical measure of the potential for loss. The 95% VaR represents the maximum loss from the initial investment that is not expected to be exceeded in 95% of the simulation outcomes.",
            'sim_context': f"This value represents the loss from your initial investment of {params.get('initial_investment', 0):,} {currency} that you would not expect to exceed in 19 out of 20 scenarios. It is the 5th percentile worst-case outcome in terms of capital loss.",
            'real_world': "This is a common risk management metric used by banks and hedge funds to quantify potential losses. A lower VaR relative to the initial investment indicates lower tail risk."
        },
        {
            'name': 'Conditional Value at Risk (95%)', 'key': 'cvar_95_loss', 'fmt': f"{{:,.0f}} {currency}",
            'definition': "Also known as Expected Shortfall, CVaR goes a step further than VaR. It answers the question: 'If the 5% worst-case scenarios happen, what is the average loss?' It provides a clearer picture of the expected magnitude of losses in the tail end of the distribution.",
            'sim_context': "This value tells you that if you are unlucky enough to land in the worst 5% of outcomes, this is the average loss you could expect to see from your initial investment. It is always greater than or equal to the VaR.",
            'real_world': "CVaR is considered a more robust measure of tail risk than VaR because it is not blind to the severity of losses beyond the VaR threshold. It is a critical metric for understanding the potential for catastrophic failure."
        }
    ]

    # Populate the values from the stats dictionary
    for metric in metrics_definitions:
        value = stats.get(metric['key'])
        if value is not None and isinstance(value, (int, float)):
            metric['value_str'] = metric['fmt'].format(value)
        else:
            metric['value_str'] = 'N/A'
    
    return metrics_definitions

def prepare_median_drawdown_table(median_drawdown_values: pd.Series) -> (List[List[str]], List[List[str]]):
    """
    Prepares and formats the median drawdown data into two lists for a two-column layout.

    Args:
        median_drawdown_values (pd.Series): A Series of median drawdown values, indexed by year.

    Returns:
        A tuple containing two lists of lists (data1, data2), ready for rendering
        in two separate tables. Returns (None, None) if input is empty.
    """
    # Ensure data is a Series first, as it might be a dict or list when coming from JSON
    if not isinstance(median_drawdown_values, pd.Series) and median_drawdown_values is not None:
        median_drawdown_values = pd.Series(median_drawdown_values)

    if median_drawdown_values is None or median_drawdown_values.empty:
        return None, None

    # Prepare data for the table, skipping year 0
    plot_data = median_drawdown_values.iloc[1:]
    
    # Create a two-column layout by splitting the data into two lists
    num_rows = len(plot_data)
    split_point = (num_rows + 1) // 2
    
    data1 = [["Year", f"Amount ({currency})"]] + [[f"{idx}", f"{int(val):,}"] for idx, val in plot_data.iloc[:split_point].items()]
    data2 = [["Year", f"Amount ({currency})"]] + [[f"{idx}", f"{int(val):,}"] for idx, val in plot_data.iloc[split_point:].items()]

    return data1, data2

def prepare_executive_summary(params: Dict[str, Any], stats: Dict[str, Any], gemini_content: Dict[str, str], currency: str = 'SEK') -> Dict[str, Any]:
    """
    Assembles the content for the Executive Summary into a structured dictionary.

    This function centralizes the logic for formatting the scenario description,
    key statistics, and the AI-generated executive summary.

    Args:
        params (Dict[str, Any]): The simulation parameters.
        stats (Dict[str, Any]): The final calculated statistics.
        gemini_content (Dict[str, str]): The AI-generated text for the summary,
                                         containing 'main_outcome' and 'bottom_line'.

    Returns:
        Dict[str, Any]: A dictionary containing the formatted text for each
                        part of the executive summary.
    """
    from core.currency_config import format_currency_amount
    
    if params.get('strategy') == 'custom':
        strategy_display = params.get('custom_strategy_name', 'Custom Strategy')
    else:
        strategy_display = ' '.join(word.capitalize() for word in params.get('strategy', '').split('_'))
    initial_formatted = format_currency_amount(params.get('initial_investment', 0), currency, decimals=0)
    scenario_text = (
        f"This report analyzes a \"{strategy_display}\" strategy using {params.get('asset_name', 'the asset')}, "
        f"starting with {initial_formatted} over {params.get('num_years', 0)} years."
    )

    # Extract key values
    initial_investment = params.get('initial_investment', 0)
    median_final_net_worth = stats.get('median_final_net_worth', 0)
    median_real_final_net_worth = stats.get('median_real_final_net_worth', 0)
    total_withdrawn = stats.get('median_total_withdrawn', 0)
    total_contributed = stats.get('median_total_contributions', 0)
    median_interest = stats.get('median_accumulated_interest', 0)
    median_tax = stats.get('median_accumulated_tax', 0)
    median_fees = stats.get('median_accumulated_fees', 0)
    
    key_stats = []
    
    # === PERFORMANCE METRICS ===
    # Always show final net worth (real vs nominal)
    real_formatted = format_currency_amount(int(median_real_final_net_worth), currency, decimals=0)
    nominal_formatted = format_currency_amount(int(median_final_net_worth), currency, decimals=0)
    key_stats.append({
        "label": "Final Net Worth (Real | Nominal)",
        "value": f"{real_formatted} | {nominal_formatted}"
    })
    
    # Calculate and show return based on strategy type
    if total_withdrawn > 0:
        # Withdrawal strategy: show total portfolio value (real and nominal)
        total_value_nominal = median_final_net_worth + total_withdrawn
        total_value_real = median_real_final_net_worth + total_withdrawn  # Withdrawn is already in real terms
        
        total_real_formatted = format_currency_amount(int(total_value_real), currency, decimals=0)
        total_nominal_formatted = format_currency_amount(int(total_value_nominal), currency, decimals=0)
        final_formatted = format_currency_amount(int(median_final_net_worth), currency, decimals=0)
        withdrawn_formatted = format_currency_amount(int(total_withdrawn), currency, decimals=0)
        
        key_stats.append({
            "label": "Total Portfolio Value (Real | Nominal)",
            "value": f"{total_real_formatted} | {total_nominal_formatted} (Final: {final_formatted} + Withdrawn: {withdrawn_formatted})"
        })
        
        # Calculate return on initial investment
        if initial_investment > 0:
            total_return_pct = ((total_value_nominal - initial_investment) / initial_investment) * 100
            num_years = params.get('num_years', 1)
            annualized_return = ((total_value_nominal / initial_investment) ** (1 / num_years) - 1) * 100
            key_stats.append({
                "label": "Return on Investment",
                "value": f"{total_return_pct:.1f}% ({annualized_return:.1f}% annualized)"
            })
    elif total_contributed > 0:
        # Contribution strategy: show net gain
        total_invested = initial_investment + total_contributed
        net_gain = median_final_net_worth - total_invested
        if total_invested > 0:
            return_pct = (net_gain / total_invested) * 100
            invested_formatted = format_currency_amount(int(total_invested), currency, decimals=0)
            initial_formatted = format_currency_amount(int(initial_investment), currency, decimals=0)
            contrib_formatted = format_currency_amount(int(total_contributed), currency, decimals=0)
            gain_formatted = format_currency_amount(int(net_gain), currency, decimals=0)
            key_stats.append({
                "label": "Total Invested",
                "value": f"{invested_formatted} (Initial: {initial_formatted} + Contributions: {contrib_formatted})"
            })
            key_stats.append({
                "label": "Net Gain",
                "value": f"{gain_formatted} ({return_pct:.1f}% return)"
            })
    else:
        # Simple accumulation: show return on initial investment
        if initial_investment > 0:
            return_pct = ((median_final_net_worth - initial_investment) / initial_investment) * 100
            num_years = params.get('num_years', 1)
            annualized_return = ((median_final_net_worth / initial_investment) ** (1 / num_years) - 1) * 100
            key_stats.append({
                "label": "Return on Investment",
                "value": f"{return_pct:.1f}% ({annualized_return:.1f}% annualized)"
            })
    
    # Success rate
    key_stats.append({
        "label": "Portfolio Success Rate",
        "value": f"{stats.get('success_rate', 0.0):.1%}"
    })
    
    # === CASH FLOW METRICS (Conditional) ===
    if total_withdrawn > 0:
        withdrawn_formatted = format_currency_amount(int(total_withdrawn), currency, decimals=0)
        key_stats.append({
            "label": "Total Withdrawn",
            "value": withdrawn_formatted
        })
        
        # Portfolio longevity - only show if metric is available (not None)
        median_longevity = stats.get('median_years_of_spending_left')
        if median_longevity is not None and median_longevity != 'N/A':
            key_stats.append({
                "label": "Years of Spending Left (Portfolio Longevity)",
                "value": f"{median_longevity:.1f} years remaining"
            })

    
    # === COST METRICS (Enhanced for FIRE community) ===
    total_costs = median_interest + median_tax + median_fees
    if total_costs > 0:
        cost_breakdown = []
        if median_tax > 0:
            cost_breakdown.append(f"Tax: {format_currency_amount(int(median_tax), currency, decimals=0)}")
        if median_fees > 0:
            cost_breakdown.append(f"Fees: {format_currency_amount(int(median_fees), currency, decimals=0)}")
        if median_interest > 0:
            cost_breakdown.append(f"Interest: {format_currency_amount(int(median_interest), currency, decimals=0)}")
        
        costs_formatted = format_currency_amount(int(total_costs), currency, decimals=0)
        key_stats.append({
            "label": "Total Costs",
            "value": f"{costs_formatted} ({' | '.join(cost_breakdown)})"
        })
        
        # FIRE-focused Cost Impact: What percentage of total value was lost to costs?
        total_value_generated = median_final_net_worth + total_withdrawn + total_costs
        if total_value_generated > 0:
            cost_drag_pct = (total_costs / total_value_generated) * 100
            # Also show costs relative to what could have been withdrawn
            costs_vs_withdrawn = (total_costs / total_withdrawn * 100) if total_withdrawn > 0 else 0
            key_stats.append({
                "label": "⚠️ Cost Drag",
                "value": f"{cost_drag_pct:.1f}% of value ({costs_vs_withdrawn:.0f}% of withdrawals)"
            })
    
    # === RISK METRICS ===
    key_stats.append({
        "label": "Chance of Ruin",
        "value": f"{stats.get('chance_of_ruin', 0.0):.1%}"
    })
    
    # Worst case scenario (5th percentile)
    p5_net_worth = stats.get('p5_final_net_worth', 0)
    if p5_net_worth is not None:
        p5_formatted = format_currency_amount(int(p5_net_worth), currency, decimals=0)
        key_stats.append({
            "label": "Worst 5% Outcome",
            "value": p5_formatted
        })
    
    # Minimum survival duration - when did the earliest failures run out of money?
    earliest_ruin_year = stats.get('earliest_year_of_ruin')
    if earliest_ruin_year is not None:
        chance_of_ruin = stats.get('chance_of_ruin', 0.0)
        if chance_of_ruin > 0:
            key_stats.append({
                "label": "Earliest Ruin Year",
                "value": f"Year {int(earliest_ruin_year)} (in worst {chance_of_ruin:.0%} of cases)"
            })
    
    # Leverage metrics (conditional on debt usage)
    if median_interest > 0:
        p95_ltv = stats.get('p95_max_ltv', 0.0) * 100
        key_stats.append({
            "label": "Peak Leverage (95th %ile)",
            "value": f"{p95_ltv:.1f}%"
        })

    return {
        'scenario': f"<b>The Scenario:</b> {scenario_text}",
        'key_stats': key_stats,
        'main_outcome': gemini_content.get('main_outcome', "AI outcome not found."),
        'bottom_line': gemini_content.get('bottom_line', "AI bottom line not found.")
    }

def prepare_historical_stats_table(stats: Dict[str, Any], params: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Prepares and formats the historical asset statistics for display in a table.

    Args:
        stats (Dict[str, Any]): The raw historical statistics dictionary.
        params (Dict[str, Any]): Simulation parameters containing asset metadata.

    Returns:
        List[Dict[str, str]]: A list of dictionaries, where each dictionary is a metric
                              with a 'label' and a 'value'.
    """
    from datetime import datetime
    if not stats:
        return []

    # Get asset metadata directly from params (populated from assets.yml)
    asset_name = params.get('asset_name', 'Unknown Asset')
    ticker_symbol = params.get('ticker_symbol')  # Optional, None for synthetic models

    # Define the order and formatting for each metric
    metric_definitions = [
        # Asset metadata from params
        {'label': 'Asset Name', 'value': asset_name},
    ]
    
    # Only add ticker if available (real assets have it, synthetic don't)
    if ticker_symbol:
        metric_definitions.append({'label': 'Ticker', 'value': ticker_symbol})
    
    # Historical statistics from calculated data
    metric_definitions.extend([
        {'label': 'Start Date', 'key': 'start_date', 'fmt': lambda x: x.strftime('%Y-%m-%d')},
        {'label': 'End Date', 'key': 'end_date', 'fmt': lambda x: x.strftime('%Y-%m-%d')},
        {'label': 'Total Trading Days', 'key': 'total_trading_days', 'fmt': '{:,.0f}'},
        {'label': 'CAGR', 'key': 'cagr', 'fmt': '{:.2%}'},
        {'label': 'Annualized Volatility', 'key': 'annualized_volatility', 'fmt': '{:.2%}'},
        {'label': 'Sharpe Ratio', 'key': 'sharpe_ratio', 'fmt': '{:.2f}'},
        {'label': 'Sortino Ratio', 'key': 'sortino_ratio', 'fmt': '{:.2f}'},
        {'label': 'Maximum Drawdown', 'key': 'max_drawdown', 'fmt': '{:.2%}'},
        {'label': 'Calmar Ratio', 'key': 'calmar_ratio', 'fmt': '{:.2f}'},
        {'label': 'Skewness', 'key': 'skewness', 'fmt': '{:.2f}'},
        {'label': 'Kurtosis', 'key': 'kurtosis', 'fmt': '{:.2f}'},
    ])

    table_data = []
    for metric in metric_definitions:
        # Handle both pre-defined values and values from the stats dict
        if 'value' in metric:
            value = metric['value']
        else:
            value = stats.get(metric['key'])
        if value is not None:
            try:
                # Handle date strings from deserialized JSON
                if isinstance(value, str) and 'date' in metric.get('key', ''):
                    value = datetime.fromisoformat(value.split(' ')[0])  # Handle 'YYYY-MM-DD HH:MM:SS'
                if 'fmt' in metric and callable(metric['fmt']):
                    formatted_value = metric['fmt'](value)
                elif 'fmt' in metric:
                    formatted_value = metric['fmt'].format(value)
                else:
                    formatted_value = str(value)
            except (ValueError, TypeError):
                formatted_value = str(value)  # Fallback
            table_data.append({'label': metric['label'], 'value': formatted_value})

    return table_data
