import numpy as np
import pandas as pd
import numpy_financial as npf
import logging

TRADING_DAYS_PER_YEAR = 252


def get_final_outcomes_quantiles(final_outcomes):
    """Calculates p10 and p90 for a given series of final outcomes."""
    return {
        'p10': final_outcomes.quantile(0.10),
        'p90': final_outcomes.quantile(0.90),
    }

def _calculate_common_final_stats(final_net_worths, params):
    """Calculates common statistics based on the final net worth distribution."""
    stats = {}
    final_year = params['num_years']

    stats['p5_final_net_worth'] = final_net_worths.quantile(0.05)
    p10_p90_stats = get_final_outcomes_quantiles(final_net_worths)
    stats['p10_final_net_worth'] = p10_p90_stats['p10']
    stats['p25_final_net_worth'] = final_net_worths.quantile(0.25)
    stats['p75_final_net_worth'] = final_net_worths.quantile(0.75)
    stats['p90_final_net_worth'] = p10_p90_stats['p90']
    stats['p95_final_net_worth'] = final_net_worths.quantile(0.95)
    stats['median_final_net_worth'] = final_net_worths.median()
    stats['mean_final_net_worth'] = final_net_worths.mean()
    stats['min_final_net_worth'] = final_net_worths.min()
    stats['max_final_net_worth'] = final_net_worths.max()
    stats['std_final_net_worth'] = final_net_worths.std()
    stats['iqr_final_net_worth'] = stats['p75_final_net_worth'] - stats['p25_final_net_worth']

    stats['chance_of_profit'] = (final_net_worths > params['initial_investment']).mean()
    stats['chance_of_nominal_loss'] = (final_net_worths < params['initial_investment']).mean()
    real_profit_threshold = params['initial_investment'] * (1 + params['inflation_rate'])**final_year
    stats['chance_of_real_profit'] = (final_net_worths > real_profit_threshold).mean()
    stats['chance_of_real_loss'] = (final_net_worths < real_profit_threshold).mean()

    return stats

def _calculate_yearly_cash_flow_stats(results_df, params):
    """
    Calculates median yearly cash flow statistics for plotting.
    """
    stats = {}

    def safe_xs(key):
        if key in results_df.index.get_level_values(1):
            return results_df.xs(key, level=1, axis=0)
        else:
            if 'Net Worth' in results_df.index.get_level_values(1):
                return pd.DataFrame(0.0, index=results_df.xs('Net Worth', level=1, axis=0).index, columns=results_df.columns)
            else:
                return pd.DataFrame()

    final_year = params['num_years']

    # --- Yearly Median Values for Plots ---
    stats['median_debt_values'] = safe_xs('Debt').median(axis=1)
    stats['median_cash_values'] = safe_xs('Cash').median(axis=1)
    stats['median_drawdown_values'] = safe_xs('Consumption Delivered').median(axis=1)
    stats['mean_drawdown_values'] = safe_xs('Consumption Delivered').mean(axis=1)
    stats['median_yearly_contributions'] = safe_xs('Amount Contributed').median(axis=1)
    stats['median_yearly_cash_interest'] = safe_xs('Cash Interest').median(axis=1)
    stats['median_yearly_consumption'] = safe_xs('Consumption Delivered').median(axis=1)
    stats['median_yearly_interest_paid'] = safe_xs('Interest Paid').median(axis=1)
    stats['median_yearly_tax_paid'] = safe_xs('Tax Paid').median(axis=1)
    stats['median_yearly_fees_paid'] = safe_xs('Fees Paid').median(axis=1)
    
    # Median of the *total* annual costs for the overview plot and cash flow plot.
    interest_df = safe_xs('Interest Paid')
    tax_df = safe_xs('Tax Paid')
    fees_df = safe_xs('Fees Paid')
    stats['median_yearly_total_costs'] = (interest_df + tax_df + fees_df).median(axis=1)

    # --- Final Accumulated Cost Medians for Summary Table ---
    accumulated_interest_df = safe_xs('Accumulated Interest')
    accumulated_tax_df = safe_xs('Accumulated Tax')
    accumulated_fees_df = safe_xs('Accumulated Fees')
    
    stats['median_accumulated_interest'] = accumulated_interest_df.loc[final_year].median() if not accumulated_interest_df.empty else 0.0
    stats['median_accumulated_tax'] = accumulated_tax_df.loc[final_year].median() if not accumulated_tax_df.empty else 0.0
    stats['median_accumulated_fees'] = accumulated_fees_df.loc[final_year].median() if not accumulated_fees_df.empty else 0.0
    stats['mean_accumulated_interest'] = accumulated_interest_df.loc[final_year].mean() if not accumulated_interest_df.empty else 0.0
    stats['mean_accumulated_tax'] = accumulated_tax_df.loc[final_year].mean() if not accumulated_tax_df.empty else 0.0
    stats['mean_accumulated_fees'] = accumulated_fees_df.loc[final_year].mean() if not accumulated_fees_df.empty else 0.0

    # --- NEW: Calculate the median of the SUM of accumulated costs ---
    # This is more accurate than summing the medians of the individual components.
    if not accumulated_interest_df.empty and not accumulated_tax_df.empty and not accumulated_fees_df.empty:
        total_accumulated_costs = (accumulated_interest_df + accumulated_tax_df + accumulated_fees_df)
        stats['median_accumulated_total_costs'] = total_accumulated_costs.loc[final_year].median()
    else:
        stats['median_accumulated_total_costs'] = 0.0

    # --- Final Year Total Annual Cost Median for Summary Table ---
    final_year_interest = safe_xs('Interest Paid').loc[final_year] if not safe_xs('Interest Paid').empty else 0.0
    final_year_tax = safe_xs('Tax Paid').loc[final_year] if not safe_xs('Tax Paid').empty else 0.0
    final_year_fees = safe_xs('Fees Paid').loc[final_year] if not safe_xs('Fees Paid').empty else 0.0
    stats['median_total_annual_costs'] = (final_year_interest + final_year_tax + final_year_fees).median()

    return stats


def calculate_survival_rates_by_year(results_df, params):
    """
    Calculates the survival rate (success rate) for each year of the simulation.
    
    A simulation is considered "alive" (successful) at a given year if its net worth > 0.
    This creates a Kaplan-Meier style survival curve showing when failures occur.
    
    Args:
        results_df: MultiIndex DataFrame with simulation results
        params: Simulation parameters dict
    
    Returns:
        pd.Series: Survival rates indexed by year (0 to num_years)
    """
    # Exclude backtest column if present
    stats_df = results_df
    if 'Backtest' in results_df.columns:
        stats_df = results_df.drop(columns='Backtest')
    
    # Extract Net Worth data for all years
    net_worth_df = stats_df.xs('Net Worth', level=1, axis=0)
    
    # Calculate survival rate for each year
    # Survival means net worth > 0 (not ruined)
    survival_rates = {}
    for year in range(params['num_years'] + 1):
        if year in net_worth_df.index:
            if year == 0 and params.get('initial_investment', 0) == 0:
                # Special case: If starting with 0 capital (e.g. contribution strategy),
                # we don't consider year 0 as "failed" even though net worth is 0.
                survival_rate = 1.0
            else:
                year_net_worths = net_worth_df.loc[year]
                survival_rate = (year_net_worths > 0).mean()
            survival_rates[year] = survival_rate * 100  # Convert to percentage
    
    return pd.Series(survival_rates)


def calculate_final_statistics(results_df, params):
    """Calculates and returns a dictionary of final statistics from the simulation results."""
    final_year = params['num_years']
    stats = {}

    # --- NEW: Exclude the deterministic backtest path from all statistical calculations ---
    stats_df = results_df
    if 'Backtest' in results_df.columns:
        logging.info("Excluding 'Backtest' column from statistical calculations.")
        stats_df = results_df.drop(columns='Backtest')

    # --- FIX: Align data selection with the new DataFrame structure ---
    # The results_df now has a MultiIndex on the rows (Year, Metric).
    # We need to select data from the index (axis=0), not the columns (axis=1).
    # We select all 'Net Worth' rows, then pick the data for the final year.
    final_net_worths = stats_df.xs('Net Worth', level=1, axis=0).loc[final_year]

    # --- Unified Common Calculations ---
    # Standardize ruin condition: net worth <= 0 is considered failure for all strategies.
    chance_of_ruin_fraction = (final_net_worths <= 0).mean() if not final_net_worths.empty else 0.0
    stats['chance_of_ruin'] = chance_of_ruin_fraction
    stats['success_rate'] = 1.0 - chance_of_ruin_fraction

    # Real (inflation-adjusted) net worth
    inflation_multiplier = (1 + params['inflation_rate']) ** final_year
    real_final_net_worths = final_net_worths / inflation_multiplier
    stats['median_real_final_net_worth'] = real_final_net_worths.median()
    stats['mean_real_final_net_worth'] = real_final_net_worths.mean()

    # Total withdrawn/borrowed for consumption
    drawdown_df = stats_df.xs('Consumption Delivered', level=1, axis=0) # Corrected axis
    total_withdrawn = drawdown_df.astype(np.longdouble).sum()
    stats['median_total_withdrawn'] = total_withdrawn.median()
    stats['mean_total_withdrawn'] = total_withdrawn.mean()

    # Total contributions
    if 'Amount Contributed' in stats_df.index.get_level_values(1):
        contribution_df = stats_df.xs('Amount Contributed', level=1, axis=0)
        total_contributions = contribution_df.astype(np.longdouble).sum()
        stats['median_total_contributions'] = total_contributions.median()
        stats['mean_total_contributions'] = total_contributions.mean()
    else:
        stats['median_total_contributions'] = 0.0
        stats['mean_total_contributions'] = 0.0

    # Median year of ruin and worst 5% ruin year
    failed_sim_cols = final_net_worths.index[final_net_worths <= 0]
    if not failed_sim_cols.empty:
        net_worth_df = stats_df.xs('Net Worth', level=1, axis=0) # Corrected axis
        ruin_years = net_worth_df[failed_sim_cols].apply(lambda sim: sim[sim <= 0].index.min())
        stats['median_year_of_ruin'] = ruin_years.median()
        # p5_year_of_ruin: The 5th percentile (earliest ruin in worst 5% of failed cases)
        stats['p5_year_of_ruin'] = ruin_years.quantile(0.05)
        stats['earliest_year_of_ruin'] = ruin_years.min()
    else:
        stats['median_year_of_ruin'] = None
        stats['p5_year_of_ruin'] = None
        stats['earliest_year_of_ruin'] = None

    # --- Strategy-Aware "Years of Spending Left" Calculation ---
    # This metric calculates how many years of withdrawals the final net worth could sustain,
    # using a representative withdrawal amount rather than just the final year's withdrawal.
    # This prevents misleading results from strategies that intentionally taper withdrawals.
    
    # Check if any withdrawals occurred across all simulations
    total_withdrawals = drawdown_df.sum(axis=0)  # Sum across all years for each simulation
    has_withdrawals = (total_withdrawals > 0).any()
    
    if not has_withdrawals:
        # Contribution-only strategy - years remaining is not applicable
        stats['median_years_of_spending_left'] = None
        stats['mean_years_of_spending_left'] = None
    else:
        # Inflation-adjust all withdrawals to final year dollars for accurate comparison
        inflation_rate = params['inflation_rate']
        final_year = params['num_years']
        
        # Create inflation-adjusted copy of drawdown data
        inflation_adjusted_df = drawdown_df.copy()
        for year in drawdown_df.index:
            years_to_final = final_year - year
            inflation_multiplier = (1 + inflation_rate) ** years_to_final
            inflation_adjusted_df.loc[year] = drawdown_df.loc[year] * inflation_multiplier
        
        # Calculate median of non-zero, inflation-adjusted withdrawals for each simulation path
        def get_median_nonzero_withdrawal(path_withdrawals):
            """Get median of non-zero withdrawals for a single simulation path."""
            nonzero = path_withdrawals[path_withdrawals > 0]
            return nonzero.median() if len(nonzero) > 0 else 0.0
        
        # Apply to each simulation column to get representative withdrawal per path
        representative_withdrawals = inflation_adjusted_df.apply(get_median_nonzero_withdrawal, axis=0)
        
        # Calculate years remaining for each path
        # representative_withdrawals are now in final-year dollars, matching final_net_worths
        years_of_spending_left = final_net_worths.divide(
            representative_withdrawals.replace(0, np.nan)
        )
        stats['median_years_of_spending_left'] = years_of_spending_left.median()
        stats['mean_years_of_spending_left'] = years_of_spending_left.mean()

    # --- Debt & LTV-Specific Calculations ---
    # Instead of checking the strategy name, we check if any debt was ever recorded.
    # This is more efficient and works for any strategy (including custom ones) that doesn't use debt.
    debt_df = stats_df.xs('Debt', level=1, axis=0) # Corrected axis
    if debt_df.sum().sum() > 0:
        # Debt exists, so calculate LTV-related stats.
        asset_values_df = stats_df.xs('Asset Value', level=1, axis=0) # Corrected axis
        with np.errstate(divide='ignore', invalid='ignore'):
            ltv_df = debt_df.div(asset_values_df).replace([np.inf, -np.inf], 0).fillna(0)
        max_ltv_per_sim = ltv_df.max(axis=0)
        stats['p50_max_ltv'] = max_ltv_per_sim.quantile(0.50)
        stats['p75_max_ltv'] = max_ltv_per_sim.quantile(0.75)
        stats['p90_max_ltv'] = max_ltv_per_sim.quantile(0.90)
        stats['p95_max_ltv'] = max_ltv_per_sim.quantile(0.95)
        stats['median_final_ltv'] = ltv_df.loc[final_year].median()
        stats['ltv_chances'] = {i: (max_ltv_per_sim > i/100.0).mean() for i in range(5, 51, 5)}

        if params.get('drawdown_method') == 'percentage' and params.get('max_drawdown') is not None:
            stats['chance_drawdown_capped'] = (drawdown_df.loc[final_year] >= params['max_drawdown']).mean()
        else:
            stats['chance_drawdown_capped'] = 0.0
        if params.get('enable_tiered_ltv', False):
            stats['chance_drawdown_suspended'] = (drawdown_df.iloc[1:] == 0).any().mean()
        else:
            stats['chance_drawdown_suspended'] = 0.0
    else:
        # No debt was recorded, so all LTV-related stats are zero.
        stats['p50_max_ltv'] = 0.0
        stats['p75_max_ltv'] = 0.0
        stats['p90_max_ltv'] = 0.0
        stats['p95_max_ltv'] = 0.0
        stats['median_final_ltv'] = 0.0
        stats['ltv_chances'] = {i: 0.0 for i in range(5, 51, 5)}
        stats['chance_drawdown_capped'] = 0.0
        stats['chance_drawdown_suspended'] = 0.0

    # Calculate and merge common, cost, and advanced stats
    common_stats = _calculate_common_final_stats(final_net_worths, params)
    stats.update(common_stats)
    yearly_stats = _calculate_yearly_cash_flow_stats(stats_df, params)
    stats.update(yearly_stats)

    # --- Advanced Financial Metrics ---
    # Calculate annualized returns for each simulation path
    initial_investment = params['initial_investment']
    
    # --- Corrected Annualized Return Calculation using IRR ---
    # The previous CAGR calculation was incorrect as it didn't account for cash flows.
    # We now calculate the Internal Rate of Return (IRR) for each simulation path,
    # which is the correct way to measure return for a portfolio with withdrawals/contributions.
    annualized_returns = []
    drawdown_df = stats_df.xs('Consumption Delivered', level=1, axis=0) # Corrected axis
    
    for i in range(params['num_simulations']):
        final_nw = final_net_worths.iloc[i]
        # If the final net worth is negative, the annualized return is -100% by definition.
        # This avoids IRR calculation errors with unconventional cash flows from failed sims.
        if final_nw <= 0:
            annualized_returns.append(-1.0)
        else:
            sim_col = f'Sim_{i}'
            # Cash flows: initial investment (negative), annual drawdowns (positive)
            cash_flows = [-initial_investment] + drawdown_df[sim_col].iloc[1:].to_list()
            # The final net worth is the terminal value, which is added to the final cash flow for IRR calculation.
            cash_flows[-1] += final_nw
            
            try:
                annualized_returns.append(npf.irr(cash_flows))
            except (ValueError, TypeError):
                annualized_returns.append(0.0) # Default to 0% if IRR fails for other reasons
    annualized_returns = pd.Series(annualized_returns)
    
    # Risk-Free Rate (using inflation as a proxy)
    risk_free_rate = params.get('inflation_rate', 0.0)

    # --- 1. Strategy-Based Ratios (using IRR of full paths) ---
    # These are best for comparing different strategies against each other.
    mean_annual_return = annualized_returns.mean()
    std_annual_return = annualized_returns.std()
    if std_annual_return > 0:
        stats['strategy_sharpe_ratio'] = (mean_annual_return - risk_free_rate) / std_annual_return
    else:
        stats['strategy_sharpe_ratio'] = 0.0

    # Sortino Ratio (penalizes only downside deviation)
    downside_returns = annualized_returns[annualized_returns < risk_free_rate]
    downside_deviation = np.sqrt((downside_returns - risk_free_rate).pow(2).sum() / len(annualized_returns))
    stats['downside_volatility'] = downside_deviation
    if downside_deviation > 0:
        stats['strategy_sortino_ratio'] = (mean_annual_return - risk_free_rate) / downside_deviation
    else:
        stats['strategy_sortino_ratio'] = 99.0 if mean_annual_return > risk_free_rate else 0.0

    # Calmar Ratio (return relative to max drawdown)
    # Note: strategy_max_drawdown is computed later in the function and will be negative
    # We compute calmar_ratio after max_drawdown is available, so store mean_annual_return
    stats['_mean_annual_return'] = float(mean_annual_return)

    # --- 2. Asset-Based Ratios (using historical daily returns) ---
    # These are best for evaluating the underlying asset itself, independent of strategy.
    # --- FIX: Check if the key exists AND is not None before checking if it's empty. ---
    # This handles parametric models where the key may not be present at all.
    historical_returns = params.get('historical_daily_returns_for_stats')
    if historical_returns is not None and not historical_returns.empty:
        daily_returns = params['historical_daily_returns_for_stats']
        
        # Use arithmetic mean for Sharpe ratio calculation
        mean_daily_return = daily_returns.mean()
        annualized_mean_return = mean_daily_return * TRADING_DAYS_PER_YEAR
        
        std_daily_return = daily_returns.std()
        annualized_volatility = std_daily_return * np.sqrt(TRADING_DAYS_PER_YEAR)

        if annualized_volatility > 0:
            stats['asset_sharpe_ratio'] = (annualized_mean_return - risk_free_rate) / annualized_volatility
        else:
            stats['asset_sharpe_ratio'] = 0.0

        # Sortino Ratio for the asset
        daily_risk_free_rate = (1 + risk_free_rate)**(1/TRADING_DAYS_PER_YEAR) - 1
        downside_daily_returns = daily_returns[daily_returns < daily_risk_free_rate]
        downside_deviation_daily = np.sqrt((downside_daily_returns - daily_risk_free_rate).pow(2).sum() / len(daily_returns))
        annualized_downside_deviation = downside_deviation_daily * np.sqrt(TRADING_DAYS_PER_YEAR)

        if annualized_downside_deviation > 0:
            stats['asset_sortino_ratio'] = (annualized_mean_return - risk_free_rate) / annualized_downside_deviation
        else:
            stats['asset_sortino_ratio'] = 99.0 if annualized_mean_return > risk_free_rate else 0.0
    else:
        # If no historical data is available, set to 0
        stats['asset_sharpe_ratio'] = 0.0
        stats['asset_sortino_ratio'] = 0.0

    # Value at Risk (VaR) and Conditional Value at Risk (CVaR) at 95% confidence
    stats['var_95_loss'] = initial_investment - stats['p5_final_net_worth']
    cvar_outcomes = final_net_worths[final_net_worths <= stats['p5_final_net_worth']]
    stats['cvar_95_loss'] = initial_investment - cvar_outcomes.mean() if not cvar_outcomes.empty else stats['var_95_loss']
    
    # --- Strategy Ulcer Index (from simulation paths) ---
    # Calculate Ulcer Index for each simulation path's net worth trajectory
    net_worth_df = stats_df.xs('Net Worth', level=1, axis=0)
    ulcer_indices = []
    for col in net_worth_df.columns:
        path_net_worth = net_worth_df[col]
        # Only calculate for paths with positive values
        if (path_net_worth > 0).all():
            ulcer_indices.append(calculate_ulcer_index(path_net_worth))
        else:
            # For failed paths, use a high penalty value
            ulcer_indices.append(100.0)
    
    ulcer_series = pd.Series(ulcer_indices)
    stats['median_strategy_ulcer_index'] = ulcer_series.median()
    stats['mean_strategy_ulcer_index'] = ulcer_series.mean()
    
    # --- Strategy Max Drawdown (from simulation paths) ---
    # Calculate max drawdown for each simulation path's net worth trajectory
    max_drawdown_list = []
    for col in net_worth_df.columns:
        path_net_worth = net_worth_df[col]
        if len(path_net_worth) > 1:
            max_drawdown_list.append(calculate_max_drawdown(path_net_worth))
    
    if max_drawdown_list:
        stats['strategy_max_drawdown'] = float(pd.Series(max_drawdown_list).median())
    else:
        stats['strategy_max_drawdown'] = 0.0
    
    # Calmar Ratio = Mean Annual Return / |Max Drawdown|
    # Uses _mean_annual_return stored earlier during Sharpe/Sortino computation
    mean_return = stats.get('_mean_annual_return', 0.0)
    max_dd = abs(stats.get('strategy_max_drawdown', 0.0))
    if max_dd > 0.01:  # Avoid division by near-zero drawdown
        stats['strategy_calmar_ratio'] = float(mean_return / max_dd)
    else:
        stats['strategy_calmar_ratio'] = 10.0 if mean_return > 0 else 0.0
    # Clean up temp key
    stats.pop('_mean_annual_return', None)
    
    # --- Psychological Stress Metrics (from simulation paths) ---
    # Calculate behavioral finance metrics that show how difficult the strategy is to follow
    time_underwater_list = []
    recovery_time_list = []
    consecutive_declines_list = []
    severe_drawdown_count_list = []
    years_below_initial_list = []
    
    for col in net_worth_df.columns:
        path_net_worth = net_worth_df[col]
        
        # Only calculate for paths that didn't fail completely
        if (path_net_worth > 0).any():
            time_underwater_list.append(calculate_time_underwater(path_net_worth))
            recovery_time_list.append(calculate_recovery_time(path_net_worth))
            consecutive_declines_list.append(calculate_consecutive_declines(path_net_worth))
            severe_drawdown_count_list.append(calculate_severe_drawdown_count(path_net_worth, threshold=0.20))
            years_below_initial_list.append(calculate_years_below_initial(path_net_worth, initial_investment))
    
    # Report median for most metrics, P90 for consecutive declines (worst-case scenario)
    if time_underwater_list:
        stats['median_time_underwater'] = float(pd.Series(time_underwater_list).median())
        stats['median_recovery_time'] = float(pd.Series(recovery_time_list).median())
        stats['p90_consecutive_declines'] = float(pd.Series(consecutive_declines_list).quantile(0.90))
        stats['median_severe_drawdown_count'] = float(pd.Series(severe_drawdown_count_list).median())
        stats['median_years_below_initial'] = float(pd.Series(years_below_initial_list).median())
    else:
        # All paths failed - set to high values to indicate extreme stress
        stats['median_time_underwater'] = float(params['num_years'])
        stats['median_recovery_time'] = float(params['num_years'])
        stats['p90_consecutive_declines'] = float(params['num_years'])
        stats['median_severe_drawdown_count'] = 0.0
        stats['median_years_below_initial'] = float(params['num_years'])

    # --- Survival Curve Data ---
    # Calculate year-by-year survival rates for Kaplan-Meier style visualization
    stats['survival_rates_by_year'] = calculate_survival_rates_by_year(stats_df, params)

    return stats


def calculate_max_drawdown(prices: pd.Series) -> float:
    """
    Calculates the maximum drawdown from a price series.
    Drawdown is expressed as a negative percentage.
    """
    if prices.empty:
        return 0.0
    
    # Calculate the cumulative maximum of the price series
    cumulative_max = prices.cummax()
    # Calculate the drawdown series
    drawdown = (prices - cumulative_max) / cumulative_max
    # Find the minimum value of the drawdown series, which is the max drawdown
    max_drawdown = drawdown.min()
    
    return max_drawdown if pd.notna(max_drawdown) else 0.0


def calculate_ulcer_index(prices: pd.Series) -> float:
    """
    Calculates the Ulcer Index, a measure of downside risk that considers
    both the depth and duration of drawdowns from peak values.
    
    The Ulcer Index squares each drawdown percentage, takes the mean,
    and returns the square root. This emphasizes larger, prolonged drawdowns
    more than smaller, brief ones.
    
    Args:
        prices: A pandas Series of prices, indexed by date.
    
    Returns:
        The Ulcer Index as a percentage (e.g., 5.0 = 5% Ulcer Index).
    """
    if prices.empty or len(prices) < 2:
        return 0.0
    
    # Calculate the cumulative maximum of the price series
    cumulative_max = prices.cummax()
    
    # Calculate the drawdown series as a percentage (positive values)
    # Drawdown = (Peak - Current) / Peak * 100
    drawdown_pct = ((cumulative_max - prices) / cumulative_max) * 100
    
    # Square each drawdown, take the mean, and return the square root
    ulcer_index = np.sqrt((drawdown_pct ** 2).mean())
    
    return ulcer_index if pd.notna(ulcer_index) else 0.0


def calculate_time_underwater(net_worth_series: pd.Series) -> int:
    """
    Calculates the number of years spent with net worth below its previous peak.
    
    Args:
        net_worth_series: A pandas Series of net worth values indexed by year.
    
    Returns:
        The number of years spent underwater (below previous peak).
    """
    if net_worth_series.empty or len(net_worth_series) < 2:
        return 0
    
    cumulative_max = net_worth_series.cummax()
    underwater = net_worth_series < cumulative_max
    return int(underwater.sum())


def calculate_recovery_time(net_worth_series: pd.Series) -> int:
    """
    Calculates the time needed to recover from the worst drawdown.
    
    Args:
        net_worth_series: A pandas Series of net worth values indexed by year.
    
    Returns:
        The number of years from the worst drawdown to recovery (or 0 if no recovery).
    """
    if net_worth_series.empty or len(net_worth_series) < 2:
        return 0
    
    cumulative_max = net_worth_series.cummax()
    drawdown_pct = (net_worth_series - cumulative_max) / cumulative_max
    
    # Find the point of maximum drawdown
    worst_dd_idx = drawdown_pct.idxmin()
    
    # Find when/if recovery happens after that point
    peak_at_worst = cumulative_max.loc[worst_dd_idx]
    future_values = net_worth_series.loc[worst_dd_idx:]
    
    recovery_points = future_values[future_values >= peak_at_worst]
    
    if recovery_points.empty:
        # Never recovered
        return len(future_values) - 1  # Years remaining after worst drawdown
    else:
        # Time from worst drawdown to recovery
        recovery_idx = recovery_points.index[0]
        return int(recovery_idx - worst_dd_idx)


def calculate_consecutive_declines(net_worth_series: pd.Series) -> int:
    """
    Calculates the longest streak of consecutive years with declining net worth.
    
    Args:
        net_worth_series: A pandas Series of net worth values indexed by year.
    
    Returns:
        The maximum number of consecutive years with year-over-year declines.
    """
    if net_worth_series.empty or len(net_worth_series) < 2:
        return 0
    
    # Calculate year-over-year changes
    is_declining = net_worth_series.diff() < 0
    
    # Find longest consecutive streak of True values
    max_streak = 0
    current_streak = 0
    
    for declining in is_declining:
        if declining:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    return max_streak


def calculate_severe_drawdown_count(net_worth_series: pd.Series, threshold: float = 0.20) -> int:
    """
    Calculates the number of distinct periods where drawdown exceeded the threshold.
    
    Args:
        net_worth_series: A pandas Series of net worth values indexed by year.
        threshold: The drawdown threshold (default 0.20 = 20%).
    
    Returns:
        The number of distinct severe drawdown events.
    """
    if net_worth_series.empty or len(net_worth_series) < 2:
        return 0
    
    cumulative_max = net_worth_series.cummax()
    drawdown = (cumulative_max - net_worth_series) / cumulative_max
    
    # Identify periods where drawdown exceeds threshold
    severe = drawdown > threshold
    
    # Count transitions from False to True (new severe drawdown events)
    # Use shift to detect start of new events
    severe_starts = severe & ~severe.shift(1, fill_value=False)
    
    return int(severe_starts.sum())


def calculate_years_below_initial(net_worth_series: pd.Series, initial_investment: float) -> int:
    """
    Calculates the number of years where net worth is below the initial investment.
    
    Args:
        net_worth_series: A pandas Series of net worth values indexed by year.
        initial_investment: The starting investment amount.
    
    Returns:
        The number of years spent below initial investment.
    """
    if net_worth_series.empty:
        return 0
    
    below_initial = net_worth_series < initial_investment
    return int(below_initial.sum())


def calculate_historical_price_stats(prices: pd.Series, risk_free_rate: float = 0.0) -> dict:
    """
    Calculates a comprehensive set of financial statistics for a given historical price series.

    Args:
        prices: A pandas Series of prices, indexed by date.
        risk_free_rate: The annual risk-free rate for Sharpe/Sortino calculations.

    Returns:
        A dictionary containing key historical statistics.
    """
    if prices.empty or len(prices) < 2:
        return {}

    # --- Basic Return & Volatility ---
    daily_returns = prices.pct_change().dropna()
    
    # Average trading days per year
    total_days = (prices.index.max() - prices.index.min()).days
    total_trading_days = len(prices)
    years = total_days / 365.25
    avg_trading_days_per_year = total_trading_days / years if years > 0 else TRADING_DAYS_PER_YEAR

    annualized_volatility = daily_returns.std() * np.sqrt(avg_trading_days_per_year)

    # --- CAGR ---
    start_price = prices.iloc[0]
    end_price = prices.iloc[-1]
    cagr = (end_price / start_price) ** (1 / years) - 1 if years > 0 else 0.0

    # --- Sharpe & Sortino Ratios ---
    # Use arithmetic mean of daily returns for Sharpe ratio calculation
    mean_daily_return = daily_returns.mean()
    annualized_mean_return = mean_daily_return * avg_trading_days_per_year

    if annualized_volatility > 0:
        sharpe_ratio = (annualized_mean_return - risk_free_rate) / annualized_volatility
    else:
        sharpe_ratio = 0.0

    daily_risk_free_rate = (1 + risk_free_rate)**(1/avg_trading_days_per_year) - 1
    downside_daily_returns = daily_returns[daily_returns < daily_risk_free_rate]
    downside_deviation_daily = np.sqrt((downside_daily_returns - daily_risk_free_rate).pow(2).sum() / len(daily_returns))
    annualized_downside_deviation = downside_deviation_daily * np.sqrt(avg_trading_days_per_year)

    if annualized_downside_deviation > 0:
        sortino_ratio = (annualized_mean_return - risk_free_rate) / annualized_downside_deviation
    else:
        sortino_ratio = 99.0 if annualized_mean_return > risk_free_rate else 0.0

    # --- Drawdown & Calmar ---
    max_drawdown = calculate_max_drawdown(prices)
    calmar_ratio = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0
    ulcer_index = calculate_ulcer_index(prices)

    # --- Distributional Properties ---
    skewness = daily_returns.skew()
    kurtosis = daily_returns.kurt()

    return {
        'start_date': prices.index.min(),
        'end_date': prices.index.max(),
        'total_trading_days': total_trading_days,
        'cagr': cagr,
        'annualized_volatility': annualized_volatility,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'max_drawdown': max_drawdown,
        'calmar_ratio': calmar_ratio,
        'ulcer_index': ulcer_index,
        'skewness': skewness,
        'kurtosis': kurtosis,
        'avg_trading_days_per_year': avg_trading_days_per_year,
    }


def calculate_historical_mu_sigma(prices: pd.Series) -> tuple[float, float]:
    """
    Calculates the historical mu and sigma from a price series.

    Args:
        prices: A pandas Series of prices, indexed by date. 
                It is assumed that this series contains only trading days.

    Returns:
        A tuple containing the calculated mu and sigma.
        chnanged comment.
    """
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if log_returns.empty:
        return 0.0, 0.0
    
    mu = log_returns.mean()
    sigma = log_returns.std()
    
    return mu, sigma