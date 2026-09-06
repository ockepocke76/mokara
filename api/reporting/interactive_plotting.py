import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import logging
from core.stats import get_final_outcomes_quantiles
from reporting.color_scheme import ChartColors, get_chart_colors, get_theme_from_config, get_plotly_theme_template

import pandas as pd
import numpy as np

try:
    from statsmodels.tsa.stattools import acf
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

# --- Plotly Template Setup ---
# Get the theme from config and create custom template
Theme = get_theme_from_config()
template_config = get_plotly_theme_template(theme_name='dark' if Theme.__name__ == 'DarkTheme' else 'light')

pio.templates["my_theme"] = go.layout.Template(
    layout=go.Layout(**template_config['layout'])
)
pio.templates.default = "my_theme"


def _apply_legend_style(fig, position='top-left'):
    """
    Applies a standardized legend style to the plot, placing it inside the chart area
    to maximize data visibility.
    """
    layout_args = dict(
        showlegend=True,
        legend=dict(
            bgcolor='rgba(255, 255, 255, 0.6)', # Semi-transparent background
            bordercolor='rgba(0, 0, 0, 0.1)',
            borderwidth=1,
            orientation="v", # Vertical column
            # Default to top-left
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        )
    )

    if position == 'top-right':
        layout_args['legend'].update(dict(xanchor="right", x=0.99))
    elif position == 'bottom-left':
        layout_args['legend'].update(dict(yanchor="bottom", y=0.01))
    elif position == 'bottom-right':
        layout_args['legend'].update(dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99))
    
    fig.update_layout(**layout_args)

def plot_price_history_interactive(price_data, asset_name, params, theme='dark'):
    """
    Generates an interactive Plotly chart for price history with a scale toggle.
    """
    import pandas as pd
    start_date = params.get('start_date', 'N/A')
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    if price_data is None or price_data.empty:
        logging.info("Generating a dummy price history plot to extract controls.")
        # Add an empty trace as a placeholder for the dummy plot
        fig.add_trace(go.Scatter(x=[], y=[]))
    else:
        logging.info(f"Generating interactive price history plot for {asset_name}")
        fig.add_trace(go.Scatter(x=price_data.index, y=price_data, mode='lines', name='Price', line=dict(color=Colors.PRIMARY)))

    fig.update_layout(
        title=f'Historical Closing Prices of {asset_name} (from {start_date})',
        xaxis_title='Date',
        yaxis_title='Price',
        xaxis=dict(
            tickformat='%Y',  # Format ticks to show only the year
            # dtick='M12',  # REMOVED: Let Plotly handle tick frequency to avoid overcrowding
            tickangle=-45  # Angle labels for better readability in static images
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1,
                xanchor="right",
                y=1.1,
                yanchor="top",
                showactive=True,
                buttons=list([
                    dict(label="Linear",
                         method="update",
                         args=[None, {"yaxis.type": "linear"}]),
                    dict(label="Log",
                         method="update",
                         args=[None, {"yaxis.type": "log"}]),
                ]),
            )
        ]
    )
    return fig

def plot_all_simulation_paths_interactive(full_results_df=None, sampled_results_df=None, params=None, precalculated_asset_paths=None, backtest_path=None, currency='SEK', final_stats=None, theme='dark'):
    """
    Generates an interactive Plotly chart for all simulation paths with a scale toggle.
    - `full_results_df`: (Live Run) The complete DataFrame with all simulation results.
    - `sampled_results_df`: (Live Run) A smaller, sampled DataFrame for plotting faint paths.
    - `precalculated_asset_paths`: (Regeneration) A DataFrame with pre-calculated p25, p50, mean, and p75 paths.
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()
    final_outcomes_for_axis = None

    # --- Determine if we are in a live run or regeneration mode ---
    is_regeneration = precalculated_asset_paths is not None and not precalculated_asset_paths.empty

    if full_results_df.empty and not is_regeneration:
        logging.info("Generating a dummy simulation paths plot to extract controls.")
        # Add empty traces as placeholders for the dummy plot
        fig.add_trace(go.Scatter(x=[], y=[])) # for individual paths
        fig.add_trace(go.Scatter(x=[], y=[])) # for IQR
        fig.add_trace(go.Scatter(x=[], y=[])) # for median
        fig.add_trace(go.Scatter(x=[], y=[])) # for mean
    elif is_regeneration:
        logging.info("Generating simulation paths plot from pre-calculated data (regeneration).")
        sampled_asset_value_df = sampled_results_df.xs('Asset Value', level=1, axis=0)
        final_outcomes_for_axis = sampled_asset_value_df.iloc[-1] # Use sampled final outcomes for axis range
    else: # This is a live run with full data
        logging.info(f"Generating interactive simulation paths plot.")
        full_asset_value_df = full_results_df.xs('Asset Value', level=1, axis=0)
        sampled_asset_value_df = sampled_results_df.xs('Asset Value', level=1, axis=0)

        # --- Robustness Fix for UI Regeneration ---
        # If the sampled_df is the same as the full_df (which can happen during UI regeneration),
        # create a new sample to avoid plotting all paths and crashing the browser.
        if sampled_asset_value_df.shape == full_asset_value_df.shape and full_asset_value_df.shape[1] > 250:
            logging.info(f"Sampled data matches full data. Resampling to 250 paths for performance.")
            sample_cols = np.random.choice(full_asset_value_df.columns, size=250, replace=False)
            sampled_asset_value_df = full_asset_value_df[sample_cols]
        
        final_outcomes_for_axis = full_asset_value_df.iloc[-1] # Use full final outcomes for axis range

    # --- Plotting Logic (works for both live run and regeneration) ---
    if 'sampled_asset_value_df' in locals() and not sampled_asset_value_df.empty:
        # --- DYNAMIC OPACITY: Adjust line strength based on the number of paths ---
        # This makes the plot clearer when fewer paths are shown.
        num_paths = len(sampled_asset_value_df.columns)
        opacity = max(0.02, min(0.5, 10 / num_paths))

        # Plot individual simulation paths with low opacity
        for col in sampled_asset_value_df.columns:
            fig.add_trace(go.Scatter(x=sampled_asset_value_df.index, y=sampled_asset_value_df[col], mode='lines',
                                     line=dict(color=Colors.SIMULATION_PATH, width=0.75),
                                     opacity=opacity,
                                     showlegend=False,
                                     hoverinfo='skip')) # Skip hover for individual faint lines

    # --- NEW: Plot the historical backtest path if it exists ---
    if backtest_path is not None and not backtest_path.empty:
        fig.add_trace(go.Scatter(x=backtest_path.index, y=backtest_path['Asset Value'], mode='lines',
                                    name='Historical Backtest Path', line=dict(color=Colors.HISTORICAL_BACKTEST, width=1.5, dash='solid')))
    
    # Calculate and plot statistical lines
    if is_regeneration:
        p25_values = precalculated_asset_paths['p25']
        p75_values = precalculated_asset_paths['p75']
        median_values = precalculated_asset_paths['p50']
        # Load the mean values. For backwards compatibility with older simulations that might not have
        # this saved, we fall back to an empty Series.
        if 'mean' in precalculated_asset_paths.columns:
            mean_values = precalculated_asset_paths['mean']
        else:
            mean_values = pd.Series() # Fallback to an empty series if mean is not available
    elif not full_results_df.empty:
        full_asset_value_df = full_results_df.xs('Asset Value', level=1, axis=0)
        p25_values = full_asset_value_df.quantile(0.25, axis=1)
        p75_values = full_asset_value_df.quantile(0.75, axis=1)
        median_values = full_asset_value_df.median(axis=1)
        mean_values = full_asset_value_df.mean(axis=1)

    if 'p25_values' in locals(): # Check if stats were calculated
        fig.add_trace(go.Scatter(
            x=list(p75_values.index) + list(p25_values.index[::-1]),
            y=list(p75_values.values) + list(p25_values.values[::-1]),
            fill='toself',
            fillcolor=Colors.IQR_FILL,
            line=dict(color=Colors.IQR_FILL_BORDER), # No border line
            name='IQR (25th-75th Pctl)'))

        fig.add_trace(go.Scatter(x=median_values.index, y=median_values, mode='lines',
                                 name='Median Asset Value', line=dict(color=Colors.MEDIAN, width=3, dash='dash')))
        if not mean_values.empty:
            fig.add_trace(go.Scatter(x=mean_values.index, y=mean_values, mode='lines',
                                     name='Mean Asset Value', line=dict(color=Colors.MEAN, width=3, dash='dot')))

    # Add total invested reference line (Initial + Cumulative Contributions over time)
    initial_investment = params.get('initial_investment', 0)
    median_contributions = final_stats.get('median_contributions_values', {}) if final_stats else {}
    total_contributions = final_stats.get('median_total_contributions', 0) if final_stats else 0
    
    if initial_investment > 0 and 'median_values' in locals():
        years = list(median_values.index)
        
        # Build cumulative invested line: always show as "Cumulative Invested"
        label = 'Cumulative Invested'
        
        # Build cumulative investment series (Initial + Contributions)
        contrib_series = pd.Series(median_contributions)
        cumulative_contrib = contrib_series.cumsum()
        cumulative_invested = [initial_investment + cumulative_contrib.get(year, 0) for year in years]
        
        # Custom hover template
        if median_contributions and total_contributions > 0:
             # Detailed breakdown if contributions exist
             hover_template = 'Year %{x}<br>Initial: ' + f'{initial_investment:,.0f}' + '<br>+ Contributions: %{customdata:,.0f}<br>= Total: %{y:,.0f}<extra></extra>'
             customdata = [cumulative_contrib.get(year, 0) for year in years]
        else:
             # Just show total (which is initial) if no contributions
             hover_template = f'Cumulative Invested: %{{y:,.0f}}<br>(Initial: {initial_investment:,.0f})<extra></extra>'
             customdata = None
        
        fig.add_trace(go.Scatter(
            x=years,
            y=cumulative_invested,
            mode='lines',
            name=label,
            line=dict(color=Colors.INITIAL_INVESTMENT, width=2, dash='dashdot'),
            hovertemplate=hover_template,
            customdata=customdata
        ))

    # Define axis ranges based on ALL data points, including year 0
    # Don't just use final outcomes - that misses the starting values!
    if 'p25_values' in locals() and not p25_values.empty:
        # Collect ALL y-values from the statistical paths to find true min/max
        all_path_values = []
        all_path_values.extend(p25_values.values)
        all_path_values.extend(p75_values.values)
        all_path_values.extend(median_values.values)
        if not mean_values.empty:
            all_path_values.extend(mean_values.values)
        
        # Also include cumulative invested line if it exists
        if initial_investment > 0 and 'cumulative_invested' in locals():
            all_path_values.extend(cumulative_invested)
        
        # Filter positive values for valid ranges
        positive_values = [v for v in all_path_values if v > 0]
        
        if positive_values:
            data_min = min(positive_values)
            data_max = max(positive_values)
            
            # Add 10% padding
            linear_min = data_min * 0.9
            linear_max = data_max * 1.1
            axis_range = [linear_min, linear_max]
            
            # For log scale
            log_min = max(linear_min, 1)  # Log scale needs positive values
            log_max = max(linear_max, log_min * 10)  # Ensure range is valid
            log_axis_range = [np.log10(log_min), np.log10(log_max)]
        else:
            axis_range = [0, 1]
            log_axis_range = [0, 1]
    else:
        axis_range = [0, 1] # Default for dummy plot
        log_axis_range = [0, 1] # log10(1), log10(10)


    fig.update_layout(
        title="Portfolio Value Paths",
        xaxis_title='Year',
        yaxis_title=f'Portfolio Value ({currency})',
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1,
                xanchor="right",
                y=1.1,
                yanchor="top",
                showactive=True,
                buttons=list([
                    dict(label="Linear",
                         method="update",
                         args=[None, {"yaxis.type": "linear", "yaxis.range": axis_range}]),
                    dict(label="Log",
                         method="update",
                         args=[None, {"yaxis.type": "log", "yaxis.range": log_axis_range}]),
                ]),
            )
        ]
    )
    _apply_legend_style(fig, position='top-left')
    # Default to linear scale with the specified range
    fig.update_yaxes(type="linear", range=axis_range)
    return fig

def plot_final_net_worth_distribution_interactive(results_df=None, params=None, final_stats=None, add_interactive_controls=True, precalculated_final_net_worths=None, precalculated_hist_data=None, currency='SEK', theme='dark'):
    """
    Generates an interactive Plotly histogram of the final net worth distribution with a scale toggle.
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    # Determine the mode of operation based on the provided data
    if precalculated_hist_data:
        logging.info("Generating distribution plot from pre-calculated histogram data.")
        title_base = f"Distribution of Final Net Worth (Yr {params['num_years']})"
    elif results_df.empty and precalculated_final_net_worths is None:
        logging.info("Generating a dummy distribution plot as no data was provided.")
        title_base = "Distribution Plot (No Data)"
        final_net_worths = pd.Series([]) # Ensure final_net_worths exists
    elif precalculated_final_net_worths is not None: # Backwards compatibility for old data format
        logging.info("Generating distribution plot from pre-calculated final net worths.")
        final_net_worths = precalculated_final_net_worths
        title_base = f"Distribution of Final Net Worth (Yr {params['num_years']})"
    else:
        logging.info("Generating interactive final net worth distribution plot.")
        
        final_year = params['num_years']
        asset_values = results_df.xs('Asset Value', level=1, axis=0).loc[final_year]

        debt_values = results_df.xs('Debt', level=1, axis=0).loc[final_year]
        final_net_worths = asset_values - debt_values
        title_base = f"Distribution of Final Net Worth (Yr {params['num_years']})" 
    # --- Plotting Logic ---
    if precalculated_hist_data:
        # Use pre-binned data with a Scatter chart (filled area)
        # This ensures all bins are displayed without Plotly's bar consolidation
        counts = precalculated_hist_data['counts']
        bin_edges = precalculated_hist_data['bin_edges']
        
        logging.info(f"Histogram data: {len(counts)} bins, {len(bin_edges)} edges")
        logging.info(f"Bin range: {bin_edges[0]:,.0f} to {bin_edges[-1]:,.0f}")
        logging.info(f"Non-zero bins: {np.count_nonzero(counts)}")
        
        # Create x and y coordinates for the histogram outline
        x_coords = []
        y_coords = []
        for i in range(len(counts)):
            x_coords.extend([bin_edges[i], bin_edges[i+1]])
            y_coords.extend([counts[i], counts[i]])
        
        logging.info(f"Created {len(x_coords)} x-coordinates and {len(y_coords)} y-coordinates")
        
        fig.add_trace(go.Scatter(
            x=x_coords,
            y=y_coords,
            fill='tozeroy',
            name='Distribution',
            line=dict(color=Colors.DISTRIBUTION, width=1),
            fillcolor=Colors.DISTRIBUTION_FILL,
            mode='lines'
        ))
    elif 'final_net_worths' in locals() and not final_net_worths.empty:
        # Fallback to Histogram for live runs or old data
        fig.add_trace(go.Histogram(
            x=final_net_worths,
            name='Distribution',
            marker_color=Colors.DISTRIBUTION,
            opacity=0.75
        ))

    # --- Add Vertical Lines and Legend Entries ---
    median_val = final_stats.get('median_final_net_worth', 0)

    fig.add_vline(x=median_val, line_dash="dash", line_color=Colors.MEDIAN)
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f"Median: {int(median_val):,} {currency}", line=dict(color=Colors.MEDIAN, dash='dash')))
    fig.add_annotation(x=median_val, y=0.95, yref='paper', text=f"Median", showarrow=False, xanchor='left', bgcolor='rgba(231, 76, 60, 0.7)')

    # Consistently show the IQR (25th and 75th percentiles) for all strategies
    p25_val = final_stats.get('p25_final_net_worth', 0)
    p75_val = final_stats.get('p75_final_net_worth', 0)

    fig.add_vline(x=p25_val, line_dash="dot", line_color=Colors.P25)
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f"25th Pctl: {int(p25_val):,} {currency}", line=dict(color=Colors.P25, dash='dot')))
    fig.add_annotation(x=p25_val, y=0.05, yref='paper', text=f"25th Pctl", showarrow=False, xanchor='left', bgcolor='rgba(155, 89, 182, 0.7)')

    fig.add_vline(x=p75_val, line_dash="dot", line_color=Colors.P75)
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f"75th Pctl: {int(p75_val):,} {currency}", line=dict(color=Colors.P75, dash='dot')))
    fig.add_annotation(x=p75_val, y=0.95, yref='paper', text=f"75th Pctl", showarrow=False, xanchor='right', bgcolor='rgba(46, 204, 113, 0.7)')

    # Set the x-axis range to focus on the 10th to 90th percentile
    p10_val = final_stats.get('p10_final_net_worth', None)
    p90_val = final_stats.get('p90_final_net_worth', None)
    axis_range = [p10_val, p90_val] if p10_val is not None and p90_val is not None else None

    fig.update_layout(
        title=title_base,
        xaxis_title=f'Final Value ({currency})',
        yaxis_title='Frequency',
        bargap=0.01,
        xaxis_range=axis_range, # Set the visible range
        updatemenus=[]
    )
    _apply_legend_style(fig, position='top-right')
    return fig

def plot_yearly_returns_interactive(yearly_returns_data, asset_name, theme='dark'):
    """
    Generates an interactive Plotly bar chart for yearly returns.
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    if yearly_returns_data is None or yearly_returns_data.empty:
        logging.info("Generating a dummy yearly returns plot.")
        fig.add_trace(go.Bar(x=[], y=[]))
    else:
        logging.info(f"Generating interactive yearly returns plot for {asset_name}")
        plot_data = yearly_returns_data.copy()
        plot_data.index = plot_data.index.year
        
        # Assign colors based on positive or negative returns
        colors = [Colors.NEGATIVE_RETURN if val < 0 else Colors.POSITIVE_RETURN for val in plot_data.values]

        fig.add_trace(go.Bar(
            x=plot_data.index, 
            y=plot_data.values, 
            name='Yearly Return',
            marker_color=colors,
            hovertemplate='<b>Year %{x}</b><br>Return: %{y:.2f}%<extra></extra>'
        ))

    fig.update_layout(
        title=f'Historical Calendar Year-over-Year {asset_name} Returns',
        xaxis_title='Year',
        yaxis_title='Return (%)',
        showlegend=False
    )
    return fig

def plot_rolling_returns_histogram_interactive(returns_data, returns_stats, asset_name, params, is_filtered=False, threshold=None, theme='dark'):
    """
    Generates an interactive Plotly histogram for rolling returns.
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    # --- FIX: Handle cases where returns_stats is None (e.g., for parametric models) ---
    # This prevents an AttributeError when trying to call .get() on a NoneType object.
    if returns_stats is None:
        returns_stats = {}

    if returns_data is None or returns_data.empty:
        logging.info("Generating a dummy rolling returns histogram.")
        fig.add_trace(go.Histogram(x=[]))
    else:
        logging.info(f"Generating interactive rolling returns histogram for {asset_name}")
        start_date = params.get('start_date', 'N/A')
        title_prefix = f"{asset_name} Data since {start_date}"
        if is_filtered:
            title = f'Distribution of Rolling 365-Day Returns (Filtered <= {threshold}%) - {title_prefix}'
        else:
            title = f'Distribution of Rolling 365-Day Returns ({title_prefix})'
        
        # Unpack pre-calculated stats
        mean_return = returns_stats.get('mean', 0)
        median_return = returns_stats.get('median', 0)
        p25_return = returns_stats.get('p25', 0)
        p75_return = returns_stats.get('p75', 0)

        # --- FIX: Visually indicate the return threshold on the plot ---
        threshold_val = params.get('return_threshold_rate')
        if threshold_val is not None and pd.api.types.is_number(threshold_val):
            threshold_percent = threshold_val * 100
            fig.add_vline(x=threshold_percent, line_dash="longdash", line_color=Colors.THRESHOLD_WARNING, annotation_text=f"Threshold: {threshold_percent:.1f}%", annotation_position="top left")
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'Return Cap: {threshold_percent:.1f}%',
                                     line=dict(color=Colors.THRESHOLD_WARNING, dash='longdash')))

        # --- Add Histogram Trace ---

        fig.add_trace(go.Histogram(
            x=returns_data,
            name='Frequency',
            marker_color=Colors.DISTRIBUTION,
            opacity=0.75,
            hovertemplate='Return: %{x:.2f}%<br>Count: %{y}<extra></extra>'
        ))

        # --- Add Vertical Lines and Legend Entries ---
        # Use add_vline for the visual line and an invisible scatter trace for the legend.
        fig.add_vline(x=mean_return, line_dash="dash", line_color=Colors.MEAN)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'Mean: {mean_return:.2f}%',
                                 line=dict(color=Colors.MEAN, dash='dash')))

        fig.add_vline(x=median_return, line_dash="solid", line_color=Colors.MEDIAN)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'Median: {median_return:.2f}%',
                                 line=dict(color=Colors.MEDIAN, dash='solid')))

        fig.add_vline(x=p25_return, line_dash="dot", line_color=Colors.P25)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'25th Pctl: {p25_return:.2f}%',
                                 line=dict(color=Colors.P25, dash='dot')))

        fig.add_vline(x=p75_return, line_dash="dot", line_color=Colors.P75)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'75th Pctl: {p75_return:.2f}%',
                                 line=dict(color=Colors.P75, dash='dot')))

    fig.update_layout(
        title=title,
        xaxis_title='Annual Return (%)',
        yaxis_title='Frequency',
        bargap=0.01,
        showlegend=True
    )
    _apply_legend_style(fig, position='top-right')
    return fig

def plot_autocorrelation_interactive(acf_data, asset_name, theme='dark'):
    """
    Generates an interactive Plotly chart for autocorrelation of daily returns
    from pre-calculated ACF data.
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    if not STATSMODELS_AVAILABLE:
        logging.warning("Cannot generate autocorrelation plot: 'statsmodels' is not installed.")
        fig.update_layout(title=f'Autocorrelation Plot Skipped for {asset_name}', annotations=[dict(text="statsmodels library not found", showarrow=False)])
        return fig

    if acf_data is None:
        logging.info("Generating a dummy autocorrelation plot as no data was provided.")
        fig.add_trace(go.Bar(x=[], y=[]))
        fig.update_layout(title=f'Autocorrelation Plot Not Available for {asset_name}')
    else:
        logging.info(f"Generating interactive autocorrelation plot for {asset_name}")
        
        acf_values = acf_data['acf_values']
        conf_interval = acf_data['conf_interval']
        lags = acf_data['lags']
        lag_numbers = np.arange(1, lags + 1)

        # Add the confidence interval as a shaded area
        fig.add_trace(go.Scatter(
            x=np.concatenate([lag_numbers, lag_numbers[::-1]]),
            y=np.concatenate([[conf_interval] * lags, [-conf_interval] * lags]),
            fill='toself',
            fillcolor=Colors.ACF_CONFIDENCE_FILL,
            line=dict(color=Colors.ACF_CONFIDENCE_BORDER),
            hoverinfo="skip",
            showlegend=False
        ))

        # Add the ACF values as a bar chart
        fig.add_trace(go.Bar(
            x=lag_numbers,
            y=acf_values,
            name='ACF',
            marker_color=Colors.ACF_BAR,
            hovertemplate='Lag: %{x}<br>Correlation: %{y:.3f}<extra></extra>'
        ))

    fig.update_layout(
        title=f'Autocorrelation of Daily Returns for {asset_name}',
        xaxis_title='Lag (Days)',
        yaxis_title='Autocorrelation',
        showlegend=False,
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor='#303C55'),
        yaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor='#303C55')
    )
    return fig

def plot_historical_drawdowns_interactive(drawdowns, asset_name, theme='dark'):
    """
    Generates an interactive Plotly chart for historical drawdowns.
    """
    import pandas as pd
    fig = go.Figure()

    if drawdowns is None or drawdowns.empty:
        logging.info("Generating a dummy historical drawdowns plot.")
        fig.add_trace(go.Scatter(x=[], y=[]))
    else:
        logging.info(f"Generating interactive historical drawdowns plot for {asset_name}")

        fig.add_trace(go.Scatter(
            x=drawdowns.index,
            y=drawdowns,
            fill='tozeroy', # Fill area to the y=0 line
            mode='lines',
            line=dict(color=ChartColors.DRAWDOWN_LINE, width=1.5),
            fillcolor=ChartColors.DRAWDOWN_FILL,
            name='Drawdown',
            hovertemplate='<b>Date:</b> %{x|%Y-%m-%d}<br><b>Drawdown:</b> %{y:.2f}%<extra></extra>'
        ))

    fig.update_layout(
        title=f'Historical Drawdowns of {asset_name}',
        xaxis_title='Date',
        yaxis_title='Drawdown from Peak (%)', # noqa
        showlegend=False,
        xaxis=dict(
            tickformat='%Y',  # Format ticks to show only the year
            dtick='M12',  # Show tick every 12 months (yearly)
            tickangle=-45  # Angle labels for better readability in static images
        )
    )
    return fig
def plot_simulation_overview_interactive(df, params, final_stats, precalculated_net_worth_paths=None, precalculated_asset_paths=None, currency='SEK'):
    """
    Generates an interactive plot summarizing the simulation outcomes, including
    median asset value, net worth, debt, and annual drawdown, using a dual-axis layout.
    """
    # --- Create a figure with a secondary y-axis ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Use precalculated data if available
    if precalculated_net_worth_paths is not None and precalculated_asset_paths is not None:
        net_worth_paths = pd.DataFrame(precalculated_net_worth_paths)
        asset_paths = pd.DataFrame(precalculated_asset_paths)
    # --- FIX: Check if df is empty or not a MultiIndex before using .xs() ---
    # This handles the case where a dummy DataFrame is passed from app.py to get controls.
    elif not df.empty and isinstance(df.index, pd.MultiIndex):
        # Fallback to calculating from the full dataframe if needed
        net_worth_df = df.xs('Net Worth', level='Metric', axis=0)
        asset_df = df.xs('Asset Value', level='Metric', axis=0)
        net_worth_paths = pd.DataFrame({
            'p25': net_worth_df.quantile(0.25, axis=1),
            'p50': net_worth_df.quantile(0.50, axis=1),
            'p75': net_worth_df.quantile(0.75, axis=1)
        })
        asset_paths = pd.DataFrame({
            'p25': asset_df.quantile(0.25, axis=1),
            'p50': asset_df.quantile(0.50, axis=1),
            'p75': asset_df.quantile(0.75, axis=1)
        })
    else:
        # If df is empty or invalid, create empty structures to prevent crashing.
        logging.info("Generating a dummy simulation overview plot (empty/invalid df).")
        fig.update_layout(title="Simulation Outcome Overview", xaxis_title='Year', yaxis_title=f'Value ({currency})')
        return fig

    years = net_worth_paths.index

    # --- Plot IQR for Net Worth (Primary Axis) ---
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p75'],
        fill=None, mode='lines', line_color=ChartColors.NET_WORTH_IQR, name='Net Worth IQR', showlegend=False
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p25'],
        fill='tonexty', mode='lines', line_color=ChartColors.NET_WORTH_IQR, name='Net Worth IQR', showlegend=True
    ), secondary_y=False)

    # --- Plot IQR for Asset Value (Primary Axis) ---
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p75'],
        fill=None, mode='lines', line_color=ChartColors.ASSET_VALUE_IQR, name='Asset Value IQR', showlegend=False
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p25'],
        fill='tonexty', mode='lines', line_color=ChartColors.ASSET_VALUE_IQR, name='Asset Value IQR', showlegend=True
    ), secondary_y=False)

    # --- Plot Median Lines (Primary Axis) ---
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p50'],
        mode='lines', line=dict(color=ChartColors.NET_WORTH_MEDIAN, width=3), name='Median Net Worth'
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p50'],
        mode='lines', line=dict(color=ChartColors.ASSET_VALUE_MEDIAN, width=3), name='Median Asset Value'
    ), secondary_y=False)

    # --- Plot Smaller Metrics (Secondary Axis) - Plotted last to appear in foreground ---
    median_contributions = pd.Series(final_stats.get('median_contributions_values', {}))
    if not median_contributions.empty and median_contributions.sum() > 0:
        fig.add_trace(go.Scatter(
            x=median_contributions.index, y=median_contributions.values,
            mode='lines', name='Median Amount Contributed', line=dict(color=ChartColors.CONTRIBUTIONS, dash='longdashdot')
        ), secondary_y=True)

    median_total_costs = pd.Series(final_stats.get('median_yearly_total_costs', {}))
    if not median_total_costs.empty:
        fig.add_trace(go.Scatter(
            x=median_total_costs.index, y=median_total_costs.values,
            mode='lines', name='Median Total Costs', line=dict(color=ChartColors.TOTAL_COSTS, dash='longdash')
        ), secondary_y=True)

    median_debt = pd.Series(final_stats.get('median_debt_values', {}))
    if not median_debt.empty:
        fig.add_trace(go.Scatter(
            x=median_debt.index, y=median_debt.values,
            mode='lines', name='Median Debt', line=dict(color=ChartColors.DEBT, dash='dash')
        ), secondary_y=True)

    median_cash = pd.Series(final_stats.get('median_cash_values', {}))
    if not median_cash.empty:
        fig.add_trace(go.Scatter(
            x=median_cash.index, y=median_cash.values,
            mode='lines', name='Median Cash', line=dict(color=ChartColors.CASH, dash='dot')
        ), secondary_y=True)

    median_drawdown = pd.Series(final_stats.get('median_drawdown_values', {}))
    if not median_drawdown.empty:
        fig.add_trace(go.Scatter(
            x=median_drawdown.index, y=median_drawdown.values,
            mode='lines', name='Median Consumption Delivered', line=dict(color=ChartColors.DRAWDOWN, dash='dashdot')
        ), secondary_y=True)

    # --- Update Layout ---
    fig.update_layout(
        xaxis_title='Year',
        template='plotly_white',
        hovermode='x unified'
    )
    _apply_legend_style(fig, position='top-left')
    
    # --- Configure Y-Axes ---
    fig.update_yaxes(
        title_text=f"<b>Primary Axis:</b> Portfolio Value ({currency})",
        type='log',
        secondary_y=False
    )
    fig.update_yaxes(
        title_text=f"<b>Secondary Axis:</b> Yearly Amounts ({currency})",
        type='linear',
        secondary_y=True,
        showgrid=False, # Hide gridlines for the secondary axis to reduce clutter
        rangemode='tozero' # Ensure axis starts at 0
    )

    return fig


def plot_portfolio_value_overview_interactive(df, params, final_stats, precalculated_net_worth_paths=None, precalculated_asset_paths=None, currency='SEK', theme='dark', show_title=True):
    """
    Generates an interactive plot showing portfolio value evolution with uncertainty bands.
    Displays median asset value and net worth with IQR shaded areas on a logarithmic scale.
    This is the first of two plots that replace the old dual-axis overview plot.
    
    Args:
        show_title: If False, suppresses title for mobile/compact layouts
    """
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    # Use precalculated data if available
    if precalculated_net_worth_paths is not None and precalculated_asset_paths is not None:
        net_worth_paths = pd.DataFrame(precalculated_net_worth_paths)
        asset_paths = pd.DataFrame(precalculated_asset_paths)
    elif not df.empty and isinstance(df.index, pd.MultiIndex):
        # Fallback to calculating from the full dataframe if needed
        net_worth_df = df.xs('Net Worth', level='Metric', axis=0)
        asset_df = df.xs('Asset Value', level='Metric', axis=0)
        net_worth_paths = pd.DataFrame({
            'p25': net_worth_df.quantile(0.25, axis=1),
            'p50': net_worth_df.quantile(0.50, axis=1),
            'p75': net_worth_df.quantile(0.75, axis=1)
        })
        asset_paths = pd.DataFrame({
            'p25': asset_df.quantile(0.25, axis=1),
            'p50': asset_df.quantile(0.50, axis=1),
            'p75': asset_df.quantile(0.75, axis=1)
        })
    else:
        # If df is empty or invalid, create empty structures to prevent crashing
        logging.info("Generating a dummy portfolio value overview plot (empty/invalid df).")
        layout_params = {'xaxis_title': 'Year', 'yaxis_title': f'Value ({currency})'}
        if not is_mobile and show_title:
            layout_params['title'] = "Portfolio Value Overview"
        fig.update_layout(**layout_params)
        return fig

    years = net_worth_paths.index

    # Plot IQR for Net Worth
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p75'],
        fill=None, mode='lines', line_color=Colors.NET_WORTH_IQR, name='Net Worth IQR', showlegend=False,
        cliponaxis=True  # Ensure data is clipped to axis boundaries
    ))
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p25'],
        fill='tonexty', mode='lines', line_color=Colors.NET_WORTH_IQR, name='Net Worth IQR', showlegend=True,
        cliponaxis=True
    ))

    # Plot IQR for Asset Value
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p75'],
        fill=None, mode='lines', line_color=Colors.ASSET_VALUE_IQR, name='Asset Value IQR', showlegend=False,
        cliponaxis=True
    ))
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p25'],
        fill='tonexty', mode='lines', line_color=Colors.ASSET_VALUE_IQR, name='Asset Value IQR', showlegend=True,
        cliponaxis=True
    ))

    # Plot Median Lines
    fig.add_trace(go.Scatter(
        x=years, y=net_worth_paths['p50'],
        mode='lines', line=dict(color=Colors.NET_WORTH_MEDIAN, width=3), name='Median Net Worth',
        cliponaxis=True
    ))
    fig.add_trace(go.Scatter(
        x=years, y=asset_paths['p50'],
        mode='lines', line=dict(color=Colors.ASSET_VALUE_MEDIAN, width=3), name='Median Asset Value',
        cliponaxis=True
    ))

    # Add total invested reference line (Initial + Cumulative Contributions over time)
    initial_investment = params.get('initial_investment', 0)
    median_contributions = final_stats.get('median_contributions_values', {}) if final_stats else {}
    total_contributions = final_stats.get('median_total_contributions', 0) if final_stats else 0
    
    if initial_investment > 0:
        # Build cumulative invested line: always show as "Cumulative Invested"
        label = 'Cumulative Invested'
        
        # Build cumulative investment series (Initial + Contributions)
        contrib_series = pd.Series(median_contributions)
        cumulative_contrib = contrib_series.cumsum()
        # Use .loc to explicitly access by label, not position
        cumulative_invested = [initial_investment + (cumulative_contrib.loc[year] if year in cumulative_contrib.index else 0) for year in years]
        
        # Custom hover template
        if median_contributions and total_contributions > 0:
             # Detailed breakdown if contributions exist
             hover_template = 'Year %{x}<br>Initial: ' + f'{initial_investment:,.0f}' + '<br>+ Contributions: %{customdata:,.0f}<br>= Total: %{y:,.0f}<extra></extra>'
             customdata = [(cumulative_contrib.loc[year] if year in cumulative_contrib.index else 0) for year in years]
        else:
             # Just show total (which is initial) if no contributions
             hover_template = f'Cumulative Invested: %{{y:,.0f}}<br>(Initial: {initial_investment:,.0f})<extra></extra>'
             customdata = None
        
        fig.add_trace(go.Scatter(
            x=years,
            y=cumulative_invested,
            mode='lines',
            name=label,
            line=dict(color=Colors.INITIAL_INVESTMENT, width=2, dash='dashdot'),
            hovertemplate=hover_template,
            customdata=customdata
        ))

    # Use same layout for both mobile and desktop
    # Interactivity is controlled via the Plotly config (staticPlot=True for mobile)
    
    # Calculate y-axis range to include ALL data points from year 0 to final year
    # This ensures starting values are visible, not just ending values
    all_y_values = []
    all_y_values.extend(net_worth_paths['p25'].values)
    all_y_values.extend(net_worth_paths['p75'].values)
    all_y_values.extend(asset_paths['p25'].values)
    all_y_values.extend(asset_paths['p75'].values)
    if initial_investment > 0:
        all_y_values.extend(cumulative_invested)
    
    # Filter out any zero/negative values for log scale
    positive_values = [v for v in all_y_values if v > 0]
    if positive_values:
        y_min = min(positive_values)
        y_max = max(positive_values)
        # Add some padding (10% on each side in log space)
        y_range = [np.log10(y_min * 0.9), np.log10(y_max * 1.1)]
    else:
        y_range = None
    
    layout_params = {
        'xaxis_title': 'Year',
        'yaxis_title': f'Value ({currency})',
        'hovermode': 'x unified',
        'template': 'my_theme',
        'height': 500,
        'showlegend': True,
        'yaxis': {
            'type': 'log',
            'range': y_range  # Explicit range ensures year 0 is visible
        }
    }
    
    # Only add title if show_title is True
    if show_title:
        layout_params['title'] = 'Portfolio Value Overview<br><sub>Median net worth and asset value over time</sub>'
    
    fig.update_layout(**layout_params)
    _apply_legend_style(fig, position='top-left')

    return fig


def plot_cashflow_liabilities_interactive(df, params, final_stats, currency='SEK', theme='dark'):
    """
    Generates an interactive plot showing cash flow and liability metrics over time.
    Displays median debt, cash, annual drawdown, total costs, and contributions on a linear scale.
    This is the second of two plots that replace the old dual-axis overview plot.
    """
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    # Extract time series data from final_stats
    median_contributions = pd.Series(final_stats.get('median_contributions_values', {}))
    median_total_costs = pd.Series(final_stats.get('median_yearly_total_costs', {}))
    median_debt = pd.Series(final_stats.get('median_debt_values', {}))
    median_cash = pd.Series(final_stats.get('median_cash_values', {}))
    median_drawdown = pd.Series(final_stats.get('median_drawdown_values', {}))

    # Plot each metric if data is available
    if not median_contributions.empty and median_contributions.sum() > 0:
        fig.add_trace(go.Scatter(
            x=median_contributions.index, y=median_contributions.values,
            mode='lines', name='Median Amount Contributed', line=dict(color=Colors.CONTRIBUTIONS, dash='longdashdot')
        ))

    if not median_total_costs.empty:
        fig.add_trace(go.Scatter(
            x=median_total_costs.index, y=median_total_costs.values,
            mode='lines', name='Median Total Costs', line=dict(color=Colors.TOTAL_COSTS, dash='longdash')
        ))

        # Add Cumulative Costs Overlay (FIRE community request)
        cumulative_costs = median_total_costs.cumsum()
        fig.add_trace(go.Scatter(
            x=cumulative_costs.index, y=cumulative_costs.values,
            mode='lines', 
            name='Cumulative Costs', 
            line=dict(color=Colors.TOTAL_COSTS, width=1, dash='solid'),
            fill='tozeroy', 
            fillcolor='rgba(128, 0, 128, 0.1)', # Very light purple fill to not obscure other lines
            hovertemplate='Cumulative Costs: %{y:,.0f}<extra></extra>'
        ))

    if not median_debt.empty:
        fig.add_trace(go.Scatter(
            x=median_debt.index, y=median_debt.values,
            mode='lines', name='Median Debt', line=dict(color=Colors.DEBT, dash='dash')
        ))

    if not median_cash.empty:
        fig.add_trace(go.Scatter(
            x=median_cash.index, y=median_cash.values,
            mode='lines', name='Median Cash', line=dict(color=Colors.CASH, dash='dot')
        ))

    if not median_drawdown.empty:
        fig.add_trace(go.Scatter(
            x=median_drawdown.index, y=median_drawdown.values,
            mode='lines', name='Median Consumption Delivered', line=dict(color=Colors.DRAWDOWN, dash='dashdot')
        ))

    # Update Layout
    fig.update_layout(
        title='Cash Flow & Liabilities',
        xaxis_title='Year',
        yaxis_title=f'Amount ({currency})',
        yaxis_type='linear',
        yaxis_rangemode='tozero',  # Ensure axis starts at 0
        hovermode='x unified'
    )
    _apply_legend_style(fig, position='top-left')

    return fig


def plot_simulation_overview_interactive_old(results_df, params, final_stats, precalculated_net_worth_paths=None, precalculated_asset_paths=None, currency='SEK'):
    """
    Generates the main interactive summary plot combining several key metrics.
    """
    import pandas as pd
    fig = go.Figure()

    if results_df.empty and precalculated_net_worth_paths is None:
        logging.info("Generating a dummy simulation overview plot as no data was provided.")
        # Add empty traces as placeholders
        fig.add_trace(go.Scatter(x=[], y=[])) # Asset IQR
        fig.add_trace(go.Scatter(x=[], y=[])) # Asset Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Net Worth IQR
        fig.add_trace(go.Scatter(x=[], y=[])) # Net Worth Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Debt Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Drawdown Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Cash Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Total Costs Median
        fig.add_trace(go.Scatter(x=[], y=[])) # Contribution Median
        bottom_lim = 1000
    elif precalculated_net_worth_paths is not None:
        logging.info("Generating simulation overview plot from pre-calculated paths.")
        p25_net_worth = precalculated_net_worth_paths['p25']
        median_net_worth = precalculated_net_worth_paths['p50']
        p75_net_worth = precalculated_net_worth_paths['p75']
        
        # Also load the pre-calculated asset paths if they exist
        if precalculated_asset_paths is not None:
            p25_asset_values = precalculated_asset_paths['p25']
            median_asset_values = precalculated_asset_paths['p50']
            p75_asset_values = precalculated_asset_paths['p75']

    else:
        logging.info("Generating interactive simulation outcome overview plot.")
        asset_value_df = results_df.xs('Asset Value', level=1, axis=1)
        debt_df = results_df.xs('Debt', level=1, axis=1)
        cash_df = results_df.xs('Cash', level=1, axis=1)
        drawdown_df = results_df.xs('Consumption Delivered', level=1, axis=1)

        net_worth_df = pd.DataFrame(asset_value_df.values - debt_df.values, index=asset_value_df.index, columns=asset_value_df.columns)

        median_asset_values = asset_value_df.median(axis=1)
        p25_asset_values = asset_value_df.quantile(0.25, axis=1)
        p75_asset_values = asset_value_df.quantile(0.75, axis=1)

        median_cash_values = cash_df.median(axis=1)
        median_net_worth = net_worth_df.median(axis=1)
        p25_net_worth = net_worth_df.quantile(0.25, axis=1)
        p75_net_worth = net_worth_df.quantile(0.75, axis=1)

        if 'Amount Contributed' in results_df.index.get_level_values(1):
            contribution_df = results_df.xs('Amount Contributed', level=1, axis=1)
            median_contribution_values = contribution_df.median(axis=1)

    # --- Calculations that can be done in both cases ---
    if precalculated_net_worth_paths is not None or not results_df.empty:
        # These stats are always available from the `final_stats` dictionary
        # --- FIX: Ensure drawdown/debt values are pandas Series before use ---
        # The data can arrive as a list or dict when re-hydrated from the database JSON blob.
        median_drawdown_values = pd.Series(final_stats.get('median_drawdown_values', {}))
        median_debt_values = pd.Series(final_stats.get('median_debt_values', {}))
        median_cash_values = pd.Series(final_stats.get('median_cash_values', {}))
        median_total_costs = pd.Series(final_stats.get('median_yearly_total_costs', {}))
        median_contribution_values = pd.Series(final_stats.get('median_contribution_values', {}))
        if median_drawdown_values.dtype == 'object': median_drawdown_values = median_drawdown_values.astype(float)
        if median_debt_values.dtype == 'object': median_debt_values = median_debt_values.astype(float)
        if median_cash_values.dtype == 'object': median_cash_values = median_cash_values.astype(float)
        if median_total_costs.dtype == 'object': median_total_costs = median_total_costs.astype(float)
        if median_contribution_values.dtype == 'object': median_contribution_values = median_contribution_values.astype(float)

        if 'debt_df' in locals(): # If not regenerating, prefer the directly calculated value
            median_debt_values = debt_df.median(axis=1)

        # --- Plotting ---
        # Plot Asset Value IQR and Median if the data is available
        if 'median_asset_values' in locals() and not median_asset_values.empty:
            fig.add_trace(go.Scatter(
                x=list(p75_asset_values.index) + list(p25_asset_values.index[::-1]),
                y=list(p75_asset_values.values) + list(p25_asset_values.values[::-1]),
                fill='toself', fillcolor='rgba(100, 255, 218, 0.2)',
                line=dict(color='rgba(255,255,255,0)'), name='Asset Value IQR'
            ))
            fig.add_trace(go.Scatter(x=median_asset_values.index, y=median_asset_values, mode='lines',
                                     name='Median Asset Value', line=dict(color='#64ffda', width=3)))
        
        # Plot Net Worth IQR and Median
        fig.add_trace(go.Scatter(
            x=list(p75_net_worth.index) + list(p25_net_worth.index[::-1]),
            y=list(p75_net_worth.values) + list(p25_net_worth.values[::-1]),
            fill='toself', fillcolor='rgba(52, 152, 219, 0.2)',
            line=dict(color='rgba(255,255,255,0)'), name='Net Worth IQR'
        ))
        fig.add_trace(go.Scatter(x=median_net_worth.index, y=median_net_worth, mode='lines',
                                 name='Median Net Worth', line=dict(color='#3498db', width=3)))

        # Plot Median Debt and Drawdown
        if not median_debt_values.empty:
            fig.add_trace(go.Scatter(x=median_debt_values.index, y=median_debt_values, mode='lines',
                                     name='Median Debt', line=dict(color='#e74c3c', width=2, dash='dash')))

        if not median_cash_values.empty:
            fig.add_trace(go.Scatter(x=median_cash_values.index, y=median_cash_values, mode='lines',
                                     name='Median Cash', line=dict(color='#2ecc71', width=2, dash='dashdot')))

        drawdown_label = "Median Consumption Delivered"
        if not median_drawdown_values.empty:
            fig.add_trace(go.Scatter(x=median_drawdown_values.index, y=median_drawdown_values, mode='lines',
                                     name=drawdown_label, line=dict(color='#f1c40f', width=2, dash='dot')))

        if not median_total_costs.empty:
            fig.add_trace(go.Scatter(x=median_total_costs.index, y=median_total_costs, mode='lines',
                                     name='Median Total Costs', line=dict(color='#f39c12', width=2, dash='dash')))

        if not median_contribution_values.empty:
            fig.add_trace(go.Scatter(x=median_contribution_values.index, y=median_contribution_values, mode='lines',
                                     name='Median Amount Contributed', line=dict(color='#9b59b6', width=2, dash='longdash')))
        
        bottom_lim = max(1000, params.get('initial_investment', 100000) / 100)

    # --- FIX: Use .get() to prevent KeyError for asset_name ---
    asset_name = params.get('asset_name', 'the Asset')
    fig.update_layout(
        title=f"Simulation Outcome Overview for '{asset_name}'",
        xaxis_title='Year',
        yaxis_title=f'Value ({currency})',
        legend_title_text='Metrics',
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1,
                xanchor="right",
                y=1.1,
                yanchor="top",
                showactive=True,
                buttons=list([
                    dict(label="Log",
                         method="update",
                         args=[{"visible": [True] * 9}, {"yaxis.type": "log", "yaxis.range": [np.log10(bottom_lim), None]}]),
                    dict(label="Linear",
                         method="update",
                         args=[{"visible": [True] * 9}, {"yaxis.type": "linear", "yaxis.range": None}]),
                ]),
            )
        ]
    )
    # Default to log scale
    fig.update_yaxes(type="log", range=[np.log10(bottom_lim), None])
    return fig

def plot_yearly_cash_flow_interactive(final_stats, params, currency='SEK', theme='dark', show_title=True):
    """
    Generates an interactive Plotly bar chart for median yearly cash flows.
    
    Args:
        show_title: If False, suppresses title for mobile/compact layouts
    """
    import pandas as pd
    # Get theme-aware colors
    Colors = get_chart_colors(theme)
    fig = go.Figure()

    # Extract data from final_stats, ensuring they are pandas Series
    median_contributions = pd.Series(final_stats.get('median_yearly_contributions', {}))
    median_cash_interest = pd.Series(final_stats.get('median_yearly_cash_interest', {}))
    median_consumption = pd.Series(final_stats.get('median_yearly_consumption', {}))
    median_interest_paid = pd.Series(final_stats.get('median_yearly_interest_paid', {}))
    median_tax_paid = pd.Series(final_stats.get('median_yearly_tax_paid', {}))
    median_fees_paid = pd.Series(final_stats.get('median_yearly_fees_paid', {}))

    # Skip year 0 for all series
    if not median_contributions.empty:
        median_contributions = median_contributions.iloc[1:]
    if not median_cash_interest.empty:
        median_cash_interest = median_cash_interest.iloc[1:]
    if not median_consumption.empty:
        median_consumption = median_consumption.iloc[1:]
    if not median_interest_paid.empty:
        median_interest_paid = median_interest_paid.iloc[1:]
    if not median_tax_paid.empty:
        median_tax_paid = median_tax_paid.iloc[1:]
    if not median_fees_paid.empty:
        median_fees_paid = median_fees_paid.iloc[1:]

    if all(s.empty for s in [median_contributions, median_cash_interest, median_consumption, median_interest_paid, median_tax_paid, median_fees_paid]):
        logging.info("Generating empty cash flow plot as no data was provided.")
        fig.add_trace(go.Bar(x=[], y=[]))
        fig.update_layout(title='Median Yearly Cash Flow (No Data Available)')
    else:
        logging.info("Generating interactive median yearly cash flow plot.")

        # --- Positive Cash Flows ---
        fig.add_trace(go.Bar(
            x=median_contributions.index,
            y=median_contributions.values,
            name='Contributions',
            marker_color="#25a55a", # Green
            hovertemplate=f'<b>Year %{{x}}</b><br>Contribution: %{{y:,.0f}} {currency}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=median_cash_interest.index,
            y=median_cash_interest.values,
            name='Cash Interest',
            marker_color="#B0F4CD", # Darker Green
            hovertemplate=f'<b>Year %{{x}}</b><br>Cash Interest: %{{y:,.0f}} {currency}<extra></extra>'
        ))

        # --- Negative Cash Flows ---
        fig.add_trace(go.Bar(
            x=median_consumption.index,
            y=-median_consumption.values, # Make values negative
            name='Consumption',
            marker_color='#f1c40f', # Yellow
            hovertemplate=f'<b>Year %{{x}}</b><br>Consumption: %{{y:,.0f}} {currency}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=median_interest_paid.index,
            y=-median_interest_paid.values,
            name='Interest Paid',
            marker_color='#e74c3c', # Red
            hovertemplate=f'<b>Year %{{x}}</b><br>Interest Paid: %{{y:,.0f}} {currency}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=median_tax_paid.index,
            y=-median_tax_paid.values,
            name='Tax Paid',
            marker_color="#8d2b1e", # Darker Red
            hovertemplate=f'<b>Year %{{x}}</b><br>Tax Paid: %{{y:,.0f}} {currency}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=median_fees_paid.index,
            y=-median_fees_paid.values,
            name='Fees Paid',
            marker_color="#3e140f", # Red
            hovertemplate=f'<b>Year %{{x}}</b><br>Fees Paid: %{{y:,.0f}} {currency}<extra></extra>'
        ))

        layout_params = {
            'barmode': 'relative',
            'xaxis_title': 'Year',
            'yaxis_title': f'Amount ({currency})'
        }
        
        if show_title:
            layout_params['title'] = 'Median Annual Cash Flow Over Time'
        
        fig.update_layout(**layout_params)
        _apply_legend_style(fig, position='top-right')

    return fig


def plot_survival_curve_interactive(survival_rates, params, theme='dark'):
    """
    Generates an interactive Kaplan-Meier style survival curve showing
    the percentage of simulations that remain successful over time.
    
    Args:
        survival_rates: pd.Series with years as index and survival rates as values (0-100%)
        params: Simulation parameters dict 
        theme: Color theme ('dark' or 'light')
    
    Returns:
        Plotly figure object
    """
    Colors = get_chart_colors(theme)
    fig = go.Figure()
    
    # Handle different input types: None, list, or pandas Series
    if survival_rates is None:
        logging.info("Generating a dummy survival curve plot (survival_rates is None).")
        fig.add_trace(go.Scatter(x=[], y=[]))
    elif isinstance(survival_rates, list) and len(survival_rates) == 0:
        logging.info("Generating a dummy survival curve plot (survival_rates is empty list).")
        fig.add_trace(go.Scatter(x=[], y=[]))
    elif hasattr(survival_rates, 'empty') and survival_rates.empty:
        logging.info("Generating a dummy survival curve plot (survival_rates Series is empty).")
        fig.add_trace(go.Scatter(x=[], y=[]))
    else:
        logging.info("Generating interactive survival curve plot.")
        
        # Convert list to pandas Series if needed
        import pandas as pd
        if isinstance(survival_rates, list):
            logging.info("Converting survival_rates from list to Series")
            # Assume list index corresponds to years 0, 1, 2, ...
            survival_rates = pd.Series(survival_rates, index=range(len(survival_rates)))
        
        # Now we can safely use .index and .values
        fig.add_trace(go.Scatter(
            x=survival_rates.index,
            y=survival_rates.values,
            mode='lines',
            name='Success Rate',
            line=dict(color=Colors.PRIMARY, width=3),
            hovertemplate='<b>Year %{x}</b><br>Success Rate: %{y:.1f}%<extra></extra>'
        ))
        
        # Add horizontal reference lines for key thresholds
        # 95% - Safe threshold (FIRE community standard)
        fig.add_hline(
            y=95,
            line_dash="dash",
            line_color=Colors.P75,
            annotation_text="95% Safe Threshold",
            annotation_position="right"
        )
        
        # 85% - Moderate risk threshold
        fig.add_hline(
            y=85,
            line_dash="dot",
            line_color=Colors.THRESHOLD_WARNING,
            annotation_text="85% Moderate Risk",
            annotation_position="right"
        )
        
        # Add shaded regions to indicate risk zones
        fig.add_hrect(
            y0=95, y1=100,
            fillcolor=Colors.P75,
            opacity=0.1,
            line_width=0,
            annotation_text="Safe Zone",
            annotation_position="top right"
        )
        
        fig.add_hrect(
            y0=85, y1=95,
            fillcolor=Colors.THRESHOLD_WARNING,
            opacity=0.1,
            line_width=0,
            annotation_text="Moderate Risk",
            annotation_position="top right"
        )
        
        fig.add_hrect(
            y0=0, y1=85,
            fillcolor=Colors.NEGATIVE_RETURN,
            opacity=0.1,
            line_width=0,
            annotation_text="High Risk",
            annotation_position="top right"
        )
        
        # Find and annotate the year when survival first drops below 95%
        below_95 = survival_rates[survival_rates < 95]
        if not below_95.empty:
            first_risky_year = below_95.index[0]
            first_risky_rate = below_95.iloc[0]
            fig.add_annotation(
                x=first_risky_year,
                y=first_risky_rate,
                text=f"Risk begins<br>Year {first_risky_year}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor=Colors.THRESHOLD_WARNING,
                bgcolor="rgba(255, 255, 255, 0.8)",
                bordercolor=Colors.THRESHOLD_WARNING,
                borderwidth=2
            )
    
    fig.update_layout(
        title="Portfolio Survival Curve (Kaplan-Meier Style)",
        xaxis_title='Year',
        yaxis_title='Success Rate (%)',
        yaxis=dict(
            range=[0, 100],
            ticksuffix='%'
        ),
        hovermode='x unified',
        showlegend=False
    )
    
    return fig