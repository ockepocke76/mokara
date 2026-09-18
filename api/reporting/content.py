from core.cache import ttl_cache
from config import CONFIG
from core.param_layout import get_sidebar_layout
from reporting.components import prepare_settings_table, prepare_advanced_stats_table # New import
from collections import defaultdict

CHAPTER_ORDER = [ # noqa
    "Important Disclaimer",
    "Executive Summary",
    "Methodology Overview",
    "Strategic Analysis",
    "Input Data Analysis",
    "Simulation Settings",
    "Simulation Summary",
    "Qualitative Analysis",
]

APPENDIX_ORDER = ["Advanced Statistics", "Average Yearly Results", "Median Yearly Results", "Example Simulation Path", "Input Data Analysis", "Strategy Evaluations", "Glossary", "AI Prompt"]

# Main charts shown in the Input Data Analysis section
INPUT_DATA_PLOT_ORDER = [
    "price_history_log",
    "yearly_returns",
    "historical_drawdowns"
]

# Technical charts moved to Input Data Appendix (for quant-focused users)
INPUT_DATA_APPENDIX_PLOTS = [
    "rolling_returns",
    "autocorrelation",
    "filtered_rolling_returns"
]

SIMULATION_PLOT_ORDER = [
    "portfolio_value_overview",
    "simulation_paths_log",
    "final_net_worth_distribution",
    "yearly_cash_flow"
]

# Keys for output plots as used in PDF generation
# This matches the actual plots generated in background_tasks.py
# IMPORTANT: Order must match SIMULATION_REPORT_STRUCTURE exactly!
OUTPUT_PLOT_KEYS = [
    'portfolio_value_overview',
    'final_net_worth_distribution_bbd',
    'survival_curve',
    'simulation_paths_log',
    'cashflow_liabilities',
    'yearly_cash_flow'
]

# ============================================================================
# UNIFIED REPORT STRUCTURE MANIFEST
# ============================================================================
# This is the single source of truth for report content ordering in both UI and PDF.
# NOTE: PDF-only section: Front Page (title, date, parameters summary)
# NOTE: Table of Contents is auto-generated from this structure in both UI and PDF

from collections import OrderedDict

REPORT_STRUCTURE = OrderedDict([
    ('Important Disclaimer', [
        {'type': 'text_block', 'key': 'disclaimer'},
    ]),
    ('Executive Summary', [
        {'type': 'intro', 'key': 'executive_summary'},
        {'type': 'plot', 'key': 'portfolio_health_dashboard', 'optional': True},
        {'type': 'ai_analysis', 'key': 'gemini_scenario'},
        {'type': 'ai_analysis', 'key': 'gemini_main_outcome'},
        {'type': 'table', 'key': 'key_stats'},  # Table between AI texts
        {'type': 'ai_analysis', 'key': 'gemini_bottom_line'},
    ]),
    ('Methodology Overview', [
        {'type': 'intro', 'key': 'methodology'},
        {'type': 'text_block', 'key': 'methodology_flowchart_description'},
        {'type': 'flowchart', 'key': 'simulation_flowchart'},
        {'type': 'text_block', 'key': 'methodology_detailed'},
    ]),
    ('Strategic Analysis', [
        {'type': 'intro', 'key': 'strategic_analysis'},
        {'type': 'table', 'key': 'transaction_types'},
        {'type': 'text_block', 'key': 'strategy_description'},
        {'type': 'flowchart', 'key': 'strategy_flowchart', 'optional': True},
        {'type': 'evaluation', 'key': 'strategy_evaluation', 'optional': True},
    ]),
    ('Simulation Settings', [
        {'type': 'intro', 'key': 'simulation_settings'},
        {'type': 'table', 'key': 'settings_table'},
    ]),
    ('Input Data Analysis', [
        {'type': 'intro', 'key': 'input_data_analysis'},
        {'type': 'table', 'key': 'asset_info', 'optional': True},
        {'type': 'plot', 'key': 'price_history_log'},
        {'type': 'plot', 'key': 'yearly_returns'},
        {'type': 'plot', 'key': 'historical_drawdowns'},
    ]),
    ('Simulation Summary', [
        {'type': 'intro', 'key': 'simulation_summary'},
        
        # Outcome Section
        {'type': 'info_box', 'key': 'outcome_analysis'},
        {'type': 'plot', 'key': 'portfolio_value_overview'},
        {'type': 'plot', 'key': 'final_net_worth_distribution_bbd'},
        
        # Risk Section
        {'type': 'info_box', 'key': 'risk_analysis'},
        {'type': 'plot', 'key': 'survival_curve'},
        
        # Psychological / Path Experience
        {'type': 'info_box', 'key': 'psychological_metrics'},
        {'type': 'plot', 'key': 'simulation_paths_log'},

        # Mechanics & Advanced Stats
        {'type': 'info_box', 'key': 'advanced_stats_summary'},
        {'type': 'plot', 'key': 'cashflow_liabilities'},
        {'type': 'plot', 'key': 'yearly_cash_flow'},
    ]),
    ('Qualitative Analysis', [
        {'type': 'intro', 'key': 'qualitative_analysis'},
        {'type': 'ai_analysis', 'key': 'gemini_full_analysis'},
    ]),
    # ===== APPENDICES =====
    ('Appendices: Average Yearly Results', [
        {'type': 'dataframe', 'key': 'average_results'},
    ]),
    ('Appendices: Median Yearly Results', [
        {'type': 'dataframe', 'key': 'median_results'},
    ]),
    ('Appendices: Example Simulation Path', [
        {'type': 'dataframe', 'key': 'example_path'},
    ]),
    ('Appendices: Input Data Analysis', [
        {'type': 'intro', 'key': 'input_data_appendix_intro'},
        {'type': 'plot', 'key': 'rolling_returns'},
        {'type': 'plot', 'key': 'autocorrelation'},
    ]),
    ('Appendices: Strategy Evaluations', [
        {'type': 'intro', 'key': 'strategy_eval_intro'},
        {'type': 'text_block', 'key': 'strategy_eval_process'},
        {'type': 'text_block', 'key': 'strategy_eval_scenarios'},
        {'type': 'text_block', 'key': 'strategy_eval_metrics'},
        {'type': 'text_block', 'key': 'strategy_eval_wisdom'},
    ]),
    ('Appendices: Advanced Statistics', [
        {'type': 'intro', 'key': 'advanced_stats_intro'},
        {'type': 'table', 'key': 'advanced_stats'},
    ]),
    ('Appendices: Glossary', [
        {'type': 'glossary', 'key': 'glossary_data'},
    ]),
    ('Appendices: AI Prompt', [
        {'type': 'intro', 'key': 'ai_prompt_intro'},
        {'type': 'text_block', 'key': 'ai_prompt_text'},
        {'optional': True},  # Only if config allows
    ]),
    ('Appendices: Performance', [
        {'type': 'plot', 'key': 'timing_plot'},
    ]),
])


# Strategy descriptions for AI analysis prompts
STRATEGY_DESCRIPTIONS = {
    'trinity': 'A classic Trinity Study-inspired withdrawal strategy that withdraws a fixed percentage of the initial portfolio value each year, adjusted for inflation. This strategy sells assets as needed to fund withdrawals and maintains 100% equity allocation.',
    'buy_borrow_die': 'A leverage-based strategy that borrows against assets to fund consumption while keeping assets invested for growth. The strategy aims to minimize transaction costs and taxes by borrowing instead of selling, with the intent of eventually passing assets to heirs.',
    'get_rich_stay_rich': 'A two-phase strategy that accumulates wealth through regular contributions until reaching a target net worth (Get Rich), then switches to a sustainable withdrawal phase while maintaining the target via dynamic adjustments (Stay Rich).'
}

# ============================================================================
# CENTRALIZED REPORT STRUCTURE
# Single source of truth for plot order and flow in both UI and PDF
# ============================================================================

# Main Input Data Charts (shown in main body)
INPUT_REPORT_STRUCTURE = [
    {
        'key': 'price_history_log',
        'plot_function': 'plot_price_history_interactive',
        'title': 'Historical Price (Interactive)',
        'args': ['prices', 'asset_name', 'params'],
        'kwargs': {'theme': 'theme'},
    },
    {
        'key': 'yearly_returns',
        'plot_function': 'plot_yearly_returns_interactive',
        'title': 'Historical Yearly Returns',
        'args': ['yearly_returns', 'asset_name'],
        'kwargs': {'theme': 'theme'},
    },
    {
        'key': 'historical_drawdowns',
        'plot_function': 'plot_historical_drawdowns_interactive',
        'title': 'Historical Drawdowns',
        'args': ['drawdown_data', 'asset_name'],
        'kwargs': {'theme': 'theme'},
    },
]

# Technical Appendix Charts (for quant-focused users)
INPUT_DATA_APPENDIX_STRUCTURE = [
    {
        'key': 'rolling_returns',
        'plot_function': 'plot_rolling_returns_histogram_interactive',
        'title': 'Distribution of Rolling 1-Year Returns',
        'args': ['rolling_annual_returns', 'rolling_returns_stats', 'asset_name', 'params'],
        'kwargs': {'theme': 'theme'},
    },
    {
        'key': 'autocorrelation',
        'plot_function': 'plot_autocorrelation_interactive',
        'title': 'Autocorrelation of Daily Returns',
        'args': ['acf_data', 'asset_name'],
        'kwargs': {'theme': 'theme'},
    },
]

SIMULATION_REPORT_STRUCTURE = [
    {
        'key': 'portfolio_value_overview',
        'plot_function': 'plot_portfolio_value_overview_interactive',
        'title': 'Portfolio Value Overview',
        'args': ['dummy_df', 'params', 'final_stats'],
        'kwargs': {'precalculated_net_worth_paths': 'net_worth_percentile_paths', 
                  'precalculated_asset_paths': 'asset_percentile_paths', 
                  'currency': 'currency', 'theme': 'theme'},
    },
    {
        'key': 'final_net_worth_distribution_bbd',
        'plot_function': 'plot_final_net_worth_distribution_interactive',
        'title': 'Final Net Worth Distribution (Interactive)',
        'args': ['dummy_df', 'params', 'final_stats'],
        'kwargs': {'precalculated_hist_data': 'final_net_worths_hist', 'currency': 'currency', 'theme': 'theme'},
    },
    {
        'key': 'survival_curve',
        'plot_function': 'plot_survival_curve_interactive',
        'title': 'Portfolio Survival Curve',
        'args': ['survival_rates', 'params'],
        'kwargs': {'theme': 'theme'},
    },
    {
        'key': 'simulation_paths_log',
        'plot_function': 'plot_all_simulation_paths_interactive',
        'title': 'All Simulation Paths (Interactive)',
        'args': ['dummy_df', 'sampled_paths', 'params'],
        'kwargs': {'precalculated_asset_paths': 'asset_percentile_paths', 'backtest_path': 'backtest_path', 'currency': 'currency', 'final_stats': 'final_stats', 'theme': 'theme'},
    },
    {
        'key': 'cashflow_liabilities',
        'plot_function': 'plot_cashflow_liabilities_interactive',
        'title': 'Cash Flow & Liabilities',
        'args': ['dummy_df', 'params', 'final_stats'],
        'kwargs': {'currency': 'currency', 'theme': 'theme'},
    },
    {
        'key': 'yearly_cash_flow',
        'plot_function': 'plot_yearly_cash_flow_interactive',
        'title': 'Median Yearly Cash Flow',
        'args': ['final_stats', 'params'],
        'kwargs': {'currency': 'currency', 'theme': 'theme'},
    },
]

SECTION_INTROS = {
    "Input Data Analysis": """
    Before delving into the complexities of multi-year financial simulations, it is paramount to thoroughly understand the foundational data upon which these simulations are built. This chapter is dedicated to dissecting the historical characteristics of the chosen asset. By examining its price history, return distributions, and historical drawdowns, we can better contextualize the simulation's outcomes. For detailed technical analysis including rolling returns distributions and autocorrelation charts, see the 'Input Data Analysis' appendix.
    
    > **FX Risk Disclosure:** This simulation uses the historical returns of the underlying asset directly. No dynamic currency conversion (e.g., USD/SEK exchange rate volatility) is modeled. The results assume that the asset's performance in its native currency translates directly to your portfolio currency, effectively assuming a constant exchange rate or a perfectly hedged position. Actual results may differ significantly due to currency fluctuations.
    """,
    "Simulation Summary": """
    This chapter presents the core findings of the Monte Carlo simulation. It begins with a summary of the key outcome and risk metrics, followed by a series of visualizations that illustrate the range of potential futures. These plots show the evolution of the portfolio over time, the distribution of final outcomes, and other critical aspects of the strategy's performance.
    """,
    "Executive Summary": """
    This chapter provides a high-level synthesis of the entire simulation. It highlights the most critical findings, key performance indicators, and a bottom-line assessment of the strategy's viability, as interpreted by the AI analysis. It is designed to give a quick yet comprehensive overview of the results.
    """,
    "Qualitative Analysis": """
    This chapter presents the detailed, narrative analysis generated by the Gemini AI model. It goes beyond the raw numbers to interpret the 'why' behind the results, discussing the interplay of different variables, potential risks, and the overall robustness of the financial strategy. This qualitative assessment provides context and depth to the quantitative findings presented elsewhere in the report.
    """,
    "Simulation Settings": """
    This section provides a detailed breakdown of all the input parameters used for this simulation run. It serves as a precise record of the scenario being tested, covering everything from the general simulation setup to the specific rules governing the chosen financial strategy and asset model.
    """,
    "Advanced Statistics Appendix": """
    This appendix provides definitions and the calculated values for the advanced financial metrics used in this report. These metrics offer standardized ways to measure risk and risk-adjusted return, allowing for more nuanced comparisons between different strategies and scenarios.
    """,
}

def get_average_results_table_description(currency='SEK'):
    return f"""
    This table provides a year-by-year breakdown of the average (mean) outcome across all simulations. While the median is often used to represent the 'typical' outcome, the mean can provide insight into how extreme positive or negative outliers influence the overall result. All values are in {currency}."""

def get_median_results_table_description(currency='SEK'):
    return f"""
    This table provides a year-by-year breakdown of the median outcome across all simulations. The median is often preferred over the mean in financial simulations as it is less sensitive to extreme outliers, providing a more representative view of the 'typical' simulation path. All values are in {currency}."""

def get_example_path_table_description(currency='SEK'):
    return f"""
    This table shows the complete year-by-year data for a single, randomly selected simulation path. This provides a concrete example of one of the many possible futures generated by the Monte Carlo simulation, helping to illustrate the mechanics of the strategy over time. All values are in {currency}.
    All values represent the state of the portfolio at the end of each year, after all transactions have been completed.""" # noqa


def get_section_intro(section_key: str, currency: str = 'SEK') -> str:
    """
    Returns the introductory markdown text for a given report section.
    Cleans up the multiline string formatting for clean rendering.
    """
    raw_text = SECTION_INTROS.get(section_key, "")
    return ' '.join(raw_text.strip().split())

PLOT_DESCRIPTIONS = {
    "price_history_log": "This chart presents the historical price trajectory of the asset over the selected period using a logarithmic y-axis. This scaling is particularly useful for assets with exponential growth, as it helps to visualize the relative magnitude of price changes over time. On a log scale, constant percentage growth appears as a straight line, offering a clearer perspective on the asset's compound growth rate and volatility. It provides a macroscopic view of the asset's long-term performance, illustrating its growth, periods of consolidation, and significant bull and bear markets.",
    "yearly_returns": "This bar chart displays the asset's total return for each calendar year in the dataset. It offers a clear and immediate impression of the asset's year-over-year volatility and performance. The fluctuations between positive and negative returns highlight the 'sequence of returns risk'—the danger that a series of poor returns in the early stages of a withdrawal strategy can disproportionately harm a portfolio's longevity. This plot is essential for understanding the boom-and-bust cycles that can characterize investment returns.",
    "rolling_returns": "This histogram illustrates the distribution of rolling one-year (365-day) returns. Unlike the calendar-year returns, this method provides a much larger and more granular dataset by calculating the return for every overlapping one-year period. The resulting distribution is fundamental to the 'Bootstrap' simulation methodology. It reveals the central tendency of the asset's returns (mean/median), its dispersion (volatility), and the shape of the distribution, including its skewness and the presence of 'fat tails' (i.e., a higher likelihood of extreme outcomes than a normal distribution would suggest). This gives a probabilistic view of the returns an investor might have experienced over any given one-year period.",
    "autocorrelation": "The autocorrelation plot (ACF) for daily returns is a critical diagnostic tool. It measures the correlation of the time series with a lagged version of itself. In financial markets, an efficient market should exhibit near-zero autocorrelation in returns, meaning past returns do not predict future returns. This plot helps to validate the assumption of a 'random walk.' Significant spikes outside the shaded confidence interval at various lags could suggest the presence of momentum or mean-reversion tendencies, which would have implications for the validity of the simulation models.",
    "historical_drawdowns": "This chart visualizes the historical drawdowns of the asset, which are the percentage declines from a peak to a subsequent trough. This is a crucial measure of risk, as it quantifies the magnitude and duration of the worst-performing periods an investor would have had to endure. Understanding the historical drawdown profile is vital for setting risk tolerance and for appreciating the potential for capital loss inherent in the asset. It provides a stark reminder of the downside risk that is not always apparent from price charts alone.",
    "filtered_rolling_returns": "This histogram shows the distribution of rolling annual returns after applying a specific filter—in this case, capping the returns at a certain threshold. This technique is often used in conservative financial planning to stress-test a strategy against a scenario where exceptionally high returns are excluded. By simulating futures based on this more pessimistic (or at least, less optimistic) dataset, we can assess the strategy's resilience and its dependence on outlier positive returns for success. It provides a more conservative lens through which to view the potential range of outcomes.",
    
    # Output Plot Descriptions
    "survival_curve": "This Kaplan-Meier style survival curve shows the percentage of simulations that remain successful (portfolio not depleted) at each year of the time horizon. The curve helps identify when the 'danger zone' occurs: does the risk of failure primarily happen in Year 10, Year 25, or is it spread throughout? The plot includes risk threshold lines at 95% (Safe - FIRE community standard) and 85% (Moderate Risk). Shaded zones indicate safe, moderate risk, and high risk regions. When the curve drops below 95%, it signals that the strategy has entered a zone where failure rates exceed conservative retirement planning standards. An annotation marks the first year when the success rate falls below 95%, identifying the beginning of elevated risk. A flat curve near 100% indicates a robust strategy with low failure risk throughout, while a steadily declining curve suggests accumulating risk over time, particularly from sequence-of-returns risk.",
    "simulation_paths_log": "This plot displays a random subset of simulation paths for the asset value over the entire time horizon on a logarithmic scale. The faint blue lines represent individual possible futures sampled from the thousands of simulations. The shaded area shows the Interquartile Range (25th to 75th percentile). The dashed cyan line indicates the median path across all simulations. If available, the solid white line shows the historical backtest path (what actually happened using real historical data). The logarithmic scale makes it easier to see percentage-based growth, as constant growth rates appear as straight lines.",

    "final_net_worth_distribution": "This histogram shows the distribution of final net worth (Assets - Debt) across all simulations. The x-axis is on a logarithmic scale to better represent the wide range of outcomes. This plot is crucial for understanding the probability of different results and quantifying the central tendency and spread of the final outcomes.",
    "final_net_worth_distribution_bbd": "This histogram shows the distribution of final net worth (Assets - Debt) across all simulations. The x-axis is on a logarithmic scale to better represent the wide range of outcomes. This plot is crucial for understanding the probability of different results and quantifying the central tendency and spread of the final outcomes.",
    "portfolio_value_overview": "This plot shows the evolution of portfolio values over time on a logarithmic scale. It displays the median asset value and net worth as solid lines, with shaded areas representing the Interquartile Range (25th to 75th percentile) for each metric. This visualization illustrates the 'cone of uncertainty' as it widens over the years, showing how the range of possible outcomes expands with time. The logarithmic scale makes it easier to see percentage-based growth across large magnitudes.",
    "cashflow_liabilities": "This plot tracks the year-by-year cash flow mechanics and liabilities of the strategy on a linear scale. It identifies median debt levels, cash holdings, annual consumption drawdowns, total costs (taxes, fees, interest), and any contributions. By separating these details from the large-scale portfolio growth, this view provides a clear look at the engine under the hood: how liquidity is managed, how costs impact the bottom line, and how debt evolves relative to assets.",
    "yearly_cash_flow": "This bar chart provides a comprehensive overview of the median annual cash flows in and out of the portfolio. Positive bars (Contributions) represent new capital being added. Negative bars show capital leaving the portfolio, broken down into Consumption (money withdrawn to live on, shown in yellow) and Total Costs (the sum of all taxes, fees, and interest paid, shown in red). This plot is essential for understanding the financial mechanics of the strategy year by year, illustrating how consumption is funded and the impact of ongoing costs."
}

def get_plot_description(key: str) -> str:
    """
    Returns the descriptive text for a given plot key.
    """
    return PLOT_DESCRIPTIONS.get(key, "No description available for this plot.")

def generate_plots_from_structure(structure, data_context, plotting_functions):
    """
    Generate plots based on the centralized report structure.
    
    Args:
        structure: List of plot definitions from INPUT_REPORT_STRUCTURE or SIMULATION_REPORT_STRUCTURE
        data_context: Dict containing all data needed for plotting (input_data, params, final_stats, etc.)
        plotting_functions: Dict mapping function names to actual functions
    
    Returns:
        List of dicts, each containing:
            - 'type': 'plot' or 'plot_group'
            - 'key': Plot key for description lookup
           - 'fig': The generated plotly figure
            - 'title': Plot title
            - 'description_key': Key for plot description
            - For plot_group: 'plots' list with individual plot data
    """
    import logging
    results = []
    
    for item in structure:
        # Handle plot groups (multiple plots, shared description)
        if item.get('type') == 'plot_group':
            group_plots = []
            for plot_def in item['plots']:
                try:
                    # Get the plotting function
                    func = plotting_functions.get(plot_def['plot_function'])
                    if not func:
                        logging.warning(f"Plotting function '{plot_def['plot_function']}' not found")
                        continue
                    
                    # Build args from context
                    args = [data_context.get(arg) for arg in plot_def.get('args', [])]
                    
                    # Build kwargs from context
                    kwargs = {}
                    for k, v in plot_def.get('kwargs', {}).items():
                        kwargs[k] = data_context.get(v)
                    
                    # Generate plot
                    fig = func(*args, **kwargs)
                    
                    group_plots.append({
                        'key': plot_def['key'],
                        'fig': fig,
                        'title': plot_def['title'],
                    })
                except Exception as e:
                    logging.error(f"Error generating plot '{plot_def['key']}': {e}", exc_info=True)
                    continue
            
            if group_plots:
                results.append({
                    'type': 'plot_group',
                    'plots': group_plots,
                    'description_key': item['description_key'],
                })
        
        # Handle individual plots
        else:
            # Skip if optional and data not available
            if item.get('optional'):
                # Check if all required args are available (handle pandas objects)
                skip = False
                for arg in item.get('args', []):
                    val = data_context.get(arg)
                    if val is None:
                        skip = True
                        break
                    # For pandas objects, check if empty
                    if hasattr(val, 'empty') and val.empty:
                        skip = True
                        break
                if skip:
                    logging.info(f"Skipping optional plot '{item['key']}'")
                    continue
            
            try:
                # Get the plotting function
                func = plotting_functions.get(item['plot_function'])
                if not func:
                    logging.warning(f"Plotting function '{item['plot_function']}' not found")
                    continue
                
                # Build args from context
                args = [data_context.get(arg) for arg in item.get('args', [])]
                
                # DEBUG: Log survival curve specifically
                if item['key'] == 'survival_curve':
                    logging.info(f"=== SURVIVAL CURVE DEBUG ===")
                    logging.info(f"  Plot function: {item['plot_function']}")
                    logging.info(f"  Function found: {func is not None}")
                    logging.info(f"  Args requested: {item.get('args', [])}")
                    logging.info(f"  Args values: {args}")
                    logging.info(f"  survival_rates is None: {data_context.get('survival_rates') is None}")
                    if data_context.get('survival_rates') is not None:
                        sr = data_context.get('survival_rates')
                        logging.info(f"  survival_rates type: {type(sr)}")
                        logging.info(f"  survival_rates empty: {hasattr(sr, 'empty') and sr.empty}")
                        if hasattr(sr, '__len__'):
                            logging.info(f"  survival_rates length: {len(sr)}")
                    logging.info(f"=== END SURVIVAL CURVE DEBUG ===")
                
                # Build kwargs from context
                kwargs = {}
                for k, v in item.get('kwargs', {}).items():
                    kwargs[k] = data_context.get(v)
                
                # Generate plot
                fig = func(*args, **kwargs)
                
                results.append({
                    'type': 'plot',
                    'key': item['key'],
                    'fig': fig,
                    'title': item['title'],
                    'description_key': item['key'],
                })
            except Exception as e:
                logging.error(f"Error generating plot '{item['key']}': {e}", exc_info=True)
                continue
    
    return results


def get_structured_settings(params):
    """
    Organizes simulation parameters into a structured dictionary for display,
    mirroring the sidebar layout defined in ui/layout.py.
    """
    return prepare_settings_table(params)

def get_structured_advanced_stats(stats, params):
    """Returns a structured list of dictionaries for advanced statistics, with definitions and calculated values."""
    return prepare_advanced_stats_table(stats, params)

@ttl_cache(ttl=3600)
def get_glossary_data():
    """Returns a dictionary of financial terms and their definitions."""
    return {
        "Core Simulation & Statistical Concepts": {
            "Monte Carlo Simulation": "A method used to understand the impact of risk and uncertainty in financial forecasts. It works by running a large number of simulations with random variables to see the range of possible outcomes.",
            "Volatility": "A measure of how much the price of an asset varies over time. Higher volatility means higher risk and a wider range of potential outcomes. It is a key driver of both upside potential and downside risk.",
            "Annualized Volatility": "The standard deviation of returns scaled to represent a full year. It measures the degree of variation in an asset's returns over a one-year period, providing a standardized measure of risk that can be compared across different assets and time periods.",
            "Standard Deviation": "A statistical measure of the amount of variation or dispersion of a set of values. In finance, it's often used as a measure of volatility.",
            "Sequence of Returns Risk": "The risk that the order and timing of investment returns are unfavorable. Poor returns in the early years of retirement can have a much bigger impact than poor returns later on.",
            "Autocorrelation (ACF)": "The correlation of a time series with a delayed version of itself. In finance, the ACF of returns is used to test for market efficiency. If returns are random (an efficient market), the autocorrelation for any lag other than zero should be close to zero. Significant spikes outside the shaded confidence interval at various lags could suggest the presence of momentum or mean-reversion tendencies, which would have implications for the validity of the simulation models.",
            "Logarithmic Scale": "A non-linear scale used for displaying data that spans several orders of magnitude. On a log scale, constant percentage changes appear as straight lines, making it easier to visualize compound growth and relative changes.",
            "Skewness": "A measure of the asymmetry of a probability distribution. Positive skewness indicates a distribution with a longer tail on the right side (more extreme positive outcomes), while negative skewness indicates a longer tail on the left (more extreme negative outcomes). In finance, understanding skewness helps assess the likelihood of extreme gains or losses.",
            "Kurtosis": "A measure of the 'tailedness' of a probability distribution. High kurtosis indicates heavy tails and a higher probability of extreme outcomes (both positive and negative) compared to a normal distribution. This is crucial for understanding the risk of rare but severe market events.",
            "Fat Tails": "A characteristic of probability distributions where extreme events (far from the mean) occur more frequently than predicted by a normal distribution. In financial markets, fat tails mean that crashes and booms are more common than standard models suggest, making risk management more challenging.",
            "Cone of Uncertainty": "A visual representation in simulation plots showing how the range of possible outcomes widens over time. It illustrates the increasing uncertainty about future values as the time horizon extends, typically shown as shaded areas between percentile paths.",
        },
        "Financial Strategies & Methods": {
            "Trinity Study": "A well-known financial study that examined 'safe withdrawal rates' from retirement portfolios. It's famous for establishing the '4% Rule'.",
            "4% Rule": "A rule of thumb suggesting that retirees can safely withdraw 4% of their initial portfolio value each year, adjusted for inflation, without depleting their funds for at least 30 years.",
            "Asset Withdrawal": "A strategy for generating cash by selling assets from a portfolio. This is a common strategy for retirees.",
            "Loan Drawdown (Buy, Borrow, Die)": "A strategy where instead of selling assets, one borrows money against the value of the portfolio to fund expenses. The assets remain invested, allowing them to continue to grow over time. The 'die' part refers to the idea that the loan is repaid from the estate upon death, thus avoiding capital gains tax on the assets.",
            "Backtest": "A simulation run using actual historical data to see how a strategy would have performed in the past. Unlike forward-looking Monte Carlo simulations, a backtest uses the exact sequence of historical returns to provide a single 'what actually happened' scenario.",
        },
        "Portfolio Outcome & Risk Metrics": {
            "Net Worth": "The value of assets minus liabilities (debts). In this simulation, it's the asset value minus the total debt. This represents the owner's equity in the portfolio.",
            "Portfolio Success Rate": "The percentage of simulations that successfully funded consumption for the entire time horizon without failure. For the Trinity strategy, failure is defined as portfolio depletion (value reaching zero). For the Loan Drawdown strategy, failure is defined as insolvency (debt exceeding asset value).",
            "Chance of Ruin": "The inverse of Portfolio Success Rate - the percentage of simulations that failed to sustain the strategy for the full time horizon. For withdrawal strategies, this means portfolio depletion (running out of money). For leverage strategies, this means insolvency (debt exceeding asset value). Also called the failure rate.",
            "Earliest Ruin Year": "Among the simulations that failed, this indicates the year when the first failure occurred. This represents the fastest path to ruin and helps understand the minimum time buffer before failure becomes possible, even in worst-case sequences of returns.",
            "Risk of Insolvency": "The risk that liabilities (debt) will exceed the value of assets, resulting in a negative net worth.",
            "Risk of Nominal Loss": "The percentage of simulations where the final net worth is less than the initial investment, without adjusting for inflation. It measures the risk of ending with less money than you started with in absolute terms.",
            "Median Year of Ruin": "For the set of simulations that end in failure (portfolio depletion or insolvency), this is the median year in which that failure occurred. It provides insight into how quickly things can go wrong in unfavorable scenarios.",
            "Cash Flow Reliability": "A qualitative measure of the consistency of annual cash flow. A 'Low' reliability indicates that consumption drawdowns were frequently suspended (e.g., due to high LTV) or reduced (e.g., due to a percentage-based drawdown on a declining asset value).",
            "Years of Spending Left (Portfolio Longevity)": "Estimates how many additional years the portfolio could sustain withdrawals based on the final net worth and a representative withdrawal amount. Calculated as: final net worth divided by the median of all non-zero, inflation-adjusted withdrawals during the simulation. All historical withdrawals are adjusted to final-year purchasing power to ensure an accurate comparison. For withdrawal/hybrid strategies, this uses the median withdrawal across all years with actual withdrawals. For contribution-only strategies, this metric is not applicable (displayed as N/A). This approach avoids misleading results from strategies that intentionally reduce withdrawals near the end of the simulation (e.g., 'die with zero' approaches).",
            "Chance of Profit (Nominal)": "The percentage of simulations where the final net worth is greater than the initial investment in nominal terms (not adjusted for inflation).",
            "Chance of Real Profit": "The percentage of simulations where the final net worth is greater than the initial investment after adjusting the initial amount for cumulative inflation over the simulation period. This measures the growth of purchasing power.",
            "Maximum Drawdown": "The largest peak-to-trough decline in asset value during the historical period or simulation. It represents the worst-case scenario an investor would have experienced and is a key measure of downside risk. Expressed as a percentage of the peak value.",
            "Total Withdrawn": "The cumulative sum of all consumption withdrawals taken from the portfolio over the simulation period, adjusted for inflation to today's purchasing power. This represents the total lifestyle funding that the portfolio provided.",
            "Total Costs": "The sum of all fees, taxes, and interest paid over the simulation period. This includes asset management fees, capital gains taxes, wealth taxes, and loan interest costs. Represents the total drag on portfolio performance from operating expenses.",
            "Return on Investment": "The total percentage gain or loss on the initial investment, calculated as (Final Value - Initial Investment) / Initial Investment. Can be shown as total return or annualized (CAGR) for comparing across different time periods.",
            "Peak Leverage (95th %ile)": "The highest Loan-to-Value (LTV) ratio reached across 95% of simulation paths. This indicates how much borrowing pressure the strategy experiences in typical scenarios. The 95th percentile excludes the most extreme 5% of outcomes to focus on reasonably likely scenarios rather than tail events.",
            "Final Net Worth (Real | Nominal)": "The portfolio's net worth at the end of the simulation, shown in both real (inflation-adjusted to today's purchasing power) and nominal (actual future dollars) terms. This dual display helps you understand both the actual amount you'd have and what it would be worth in today's money.",
            "Total Portfolio Value (Real | Nominal)": "For withdrawal strategies, this is the sum of final net worth plus all withdrawals taken, shown in both inflation-adjusted and nominal terms. Represents the total value generated by the portfolio over its lifetime.",
            "Worst 5% Outcome": "The final net worth at the 5th percentile - meaning only 5% of simulations ended worse than this. Represents a pessimistic but plausible worst-case scenario that helps with downside risk assessment.",
            "⚠️ Cost Drag": "The percentage of total portfolio value lost to fees, taxes, and interest costs. Shows how much of your potential wealth was consumed by operating expenses. Particularly important for the FIRE community focused on minimizing unnecessary costs.",
        },
        "Transaction Types & Strategy Actions": {
            "Asset Sales": "Selling portfolio assets to generate cash. Used to fund withdrawals, pay costs, or reduce leverage. Triggers capital gains tax on any profit since purchase. Common in withdrawal-based strategies like the Trinity approach.",
            "Asset Purchases": "Buying additional assets with available cash. Increases portfolio value and future growth potential. Common in accumulation phases or when rebalancing after deleveraging.",
            "Borrowing": "Taking a loan against the portfolio's value to generate cash for expenses without selling assets. Incurs interest costs but avoids capital gains tax and keeps assets invested. Core mechanic of the Buy, Borrow, Die strategy.",
            "Debt Repayment": "Paying down existing loans to reduce interest costs and improve the loan-to-value ratio. Reduces financial leverage and risk but requires cash or asset sales to fund.",
            "Contributions": "Adding new capital to the portfolio from external sources (salary, savings, etc.). Increases portfolio value without requiring market gains. Critical during accumulation phases.",
            "Cash Buffer Management": "Maintaining cash reserves to fund near-term withdrawals without selling assets during market downturns. Helps avoid selling at unfavorable prices (sequence of returns risk mitigation).",
            "Deleveraging": "Emergency asset sales triggered when loan-to-value ratios exceed safety thresholds. Reduces debt to restore healthy leverage ratios. A critical automatic risk management mechanism in leveraged strategies.",
        },
        "Strategy Evaluation Metrics": {
            "Present Value Score": "Measures the median final net worth relative to a target value (typically the initial investment). Higher scores indicate better wealth preservation. Weighted heavily in balanced evaluations as it directly measures the primary outcome.",
            "Purchasing Power Score": "Evaluates how well the strategy maintains real (inflation-adjusted) wealth. Accounts for the erosion of purchasing power over time. Critical for long-term financial security.",
            "Withdrawal Stability": "Measures the consistency and reliability of consumption withdrawals over time. Higher scores indicate more predictable cash flows. Important for retirement planning where stable income is valued.",
            "Risk Score": "A composite measure of downside risks including failure rates, drawdowns, and leverage extremes. Lower risk scores are better. Heavily weighted in conservative evaluation profiles.",
            "Robustness Score": "Evaluates how well a strategy performs across diverse market scenarios (bull, bear, sideways, volatile). Higher scores indicate strategies that work in many conditions, not just favorable ones.",
            "Capital Efficiency": "Measures how efficiently the strategy uses capital to achieve its goals. Considers factors like tax efficiency, fee minimization, and optimal leverage use. Higher scores indicate smarter use of resources.",
            "Legacy Score": "Evaluates the potential to pass wealth to heirs. Higher final net worth and lower failure rates contribute to this score. Relevant for those prioritizing intergenerational wealth transfer.",
        },
        "Asset & Market Information": {
            "Asset Name": "The descriptive name of the investment asset used in the simulation (e.g., 'S&P 500', 'Bitcoin'). Identifies what historical data or model parameterswere used.",
            "Ticker": "The market ticker symbol for the asset (e.g., 'BTC', '^GSPC'). Used to identify and fetch historical price data from financial APIs.",
            "Start Date": "The beginning date of the historical price data used for the simulation. Earlier start dates provide more data for bootstrap sampling but may include different market regimes.",
            "End Date": "The final date of the historical price data. Represents the most recent market conditions incorporated into the simulation model.",
            "Total Trading Days": "The number of individual trading days in the historical dataset. More trading days provide a richer dataset for statistical analysis and bootstrap sampling.",
        },
        "Simulation Settings & Parameters": {
            "Initial Investment": "The starting capital amount invested at the beginning of the simulation (Year 0). All returns, withdrawals, and outcomes are relative to this baseline amount.",
            "Num Simulations": "The number of Monte Carlo simulation paths to run. More simulations provide more statistical confidence but take longer to compute. Typically 1,000-10,000 for good results.",
            "Num Years": "The time horizon for the simulation in years. Represents how long you want to test the strategy (e.g., 30 years for a typical retirement period).",
            "Simulation Name": "A user-provided identifier for this simulation run. Helps organize and distinguish between different scenarios when reviewing historical results.",
            "Strategy": "The decision-making logic that determines how the portfolio behaves each year (withdrawals, contributions, borrowing, etc.). Can be a built-in strategy like Trinity or Buy-Borrow-Die, or a custom user-designed strategy.",
            "Asset Model": "The source of return data for the simulation. Either 'Bootstrap' (randomly samples from historical returns) or 'Parametric' (generates returns from a statistical model with specified mean and volatility).",
            "Return Threshold Rate": "For bootstrap models with return filtering, this sets a maximum return cap. Returns above this threshold are excluded to create more conservative scenarios that don't rely on exceptional bull markets.",
            "Cash Interest Rate": "The annual interest rate earned on cash holdings. Applies to任何 cash buffer maintained in the portfolio. Typically set to a risk-free rate like short-term Treasury yields.",
            "Inflation Rate": "The assumed annual inflation rate used to adjust values to real (today's purchasing power) terms. Critical for understanding true wealth preservation over long time horizons.",
            "Loan Interest Rate": "The annual interest rate charged on portfolio loans (for leverage strategies). Higher rates increase the cost of borrowing and can significantly impact leveraged strategy viability.",
            "Isk Tax Rate": "The annual Swedish wealth tax rate applied to the portfolio value (Investeringssparkonto system). Charged yearly regardless of whether assets are sold or gains realized.",
            "Capital Gains Tax Rate": "The tax rate applied to profits when assets are sold. Only charged on the gain (sale price minus cost basis), making it more efficient than wealth taxes for long-term holders.",
            "Tax Method": "Which taxation system is used: 'ISK' (annual wealth tax) or 'Capital Gains' (tax on realized profits). Different methods significantly impact strategy performance and optimal behavior.",
        },
        "Info Box Metrics": {
            "Median Final Net Worth": "The middle value (50th percentile) of final net worth across all simulations. Half of outcomes are above this, half below. Preferred over mean as it's less affected by extreme outliers.",
            "Median Real Net Worth (Today's SEK)": "The median final net worth adjusted for inflation to express its value in today's purchasing power. Shows what the portfolio would actually be worth in current terms.",
            "25th Percentile Final Net Worth": "The final net worth at the 25th percentile - meaning 75% of simulations ended better than this. Represents a moderately pessimistic outcome for downside planning.",
            "75th Percentile Final Net Worth": "The final net worth at the 75th percentile - meaning only 25% of simulations ended better. Represents a moderately optimistic outcome for upside potential assessment.",
            "Chance of Ruin (Insolvency)": "For leverage strategies, the percentage of simulations where debt exceeded asset value (negative net worth), resulting in insolvency and strategy failure.",
            "Median Final LTV": "The median loan-to-value ratio at the end of the simulation across all paths. Shows typical debt levels in leveraged strategies. Lower values indicate safer final leverage states.",
            "Recovery Time": "The median time (in years) required to recover from the worst drawdown experienced during the simulation. Long recovery times test investor patience and discipline.",
            "Consecutive Losses (P90)": "At the 90th percentile (near-worst case), the longest streak of consecutive years with portfolio value declines. Extended losing streaks severely test psychological resilience.",
            "Severe Drawdowns": "The median number of distinct 20%+ drawdown events experienced. Frequent severe corrections indicate high psychological volatility even if the strategy eventually recovers.",
            "Years Below Initial": "The median number of years the portfolio value spent below the initial investment amount. Being 'underwater' triggers loss aversion and regretful decision-making.",
            "Asset Sharpe Ratio": "Risk-adjusted return of the underlying asset based on historical data. Calculated as (return - risk-free rate) / volatility. Provides a baseline benchmark independent of strategy.",
            "Asset Sortino Ratio": "Like Sharpe Ratio but only penalizes downside volatility, not upside. More intuitive as investors generally don't mind upside volatility. Higher is better.",
            "Strategy Sharpe Ratio": "Risk-adjusted return of the complete strategy including all cash flows (withdrawals, contributions, costs). Shows how efficiently the strategy generated returns per unit of risk taken.",
            "Strategy Sortino Ratio": "Downside-focused risk-adjusted return for the complete strategy. Particularly relevant for strategies where avoiding losses is more important than maximizing gains.",
        },
        "Performance & Risk-Adjusted Return Ratios": {
            "CAGR (Compound Annual Growth Rate)": "The mean annual growth rate of an investment over a specified period longer than one year. It represents the rate at which an investment would have grown if it had grown at a steady rate, smoothing out volatility. Calculated as: (Ending Value / Beginning Value)^(1/Years) - 1.",
            "Sharpe Ratio": "A measure of risk-adjusted return, calculated as the excess return (return above the risk-free rate) divided by the standard deviation of returns. A higher Sharpe Ratio indicates better risk-adjusted performance. It answers the question: 'How much extra return am I getting for each unit of risk I'm taking?'",
            "Sortino Ratio": "Similar to the Sharpe Ratio, but it only considers downside volatility (negative returns) rather than total volatility. This makes it a more relevant measure for investors who are primarily concerned with downside risk. A higher Sortino Ratio indicates better downside risk-adjusted performance.",
            "Calmar Ratio": "A risk-adjusted return metric calculated as the CAGR divided by the maximum drawdown. It measures the return per unit of downside risk. A higher Calmar Ratio indicates that the investment generated strong returns relative to its worst historical decline, making it useful for assessing strategies with different drawdown profiles.",
        },
        "LTV & Deleveraging Concepts": {
            "Loan-to-Value (LTV)": "The ratio of a loan to the value of the asset purchased or used as collateral. A higher LTV means higher leverage and higher risk.",
            "Maximum LTV": "The highest Loan-to-Value (LTV) ratio reached at any point during a single simulation run. The distribution of this metric across all simulations is a key indicator of the strategy's leverage risk.",
            "LTV Warning Threshold": "The first tier in the LTV management system. When LTV exceeds this threshold, new loan drawdowns are suspended to prevent further leverage increase. This is a proactive risk management measure designed to prevent the LTV from reaching dangerous levels.",
            "LTV Action Threshold": "The second, more critical tier in the LTV management system. When LTV exceeds this threshold, the system triggers automatic deleveraging by selling assets to pay down debt. This is an emergency measure to prevent insolvency.",
            "Target LTV": "The LTV level that the deleveraging process aims to achieve when selling assets to reduce debt. Typically set below the Action Threshold to provide a safety buffer and prevent immediate re-triggering of deleveraging.",
            "Tiered LTV Management": "A risk management system with multiple thresholds. In this simulation, it includes a 'Warning Tier' that suspends new drawdowns and an 'Action Tier' that triggers deleveraging (asset sales) to reduce debt.",
            "Deleveraging": "The act of reducing debt. In this simulation, it is an automated process triggered when the LTV exceeds the 'Action Tier' threshold, forcing the sale of assets to pay down the loan to a 'Target LTV'. This is a critical risk-mitigation mechanism.",
        },
        "Data & Return Concepts": {
            "Bootstrap (Simulation Model)": "A simulation method that uses historical data. It involves randomly sampling from historical returns to generate future return scenarios. It preserves the historical distribution of returns.",
            "Parametric (Simulation Model)": "A simulation method that uses statistical parameters (like mean and standard deviation) derived from historical data or assumptions. Returns are generated from a specified probability distribution (e.g., a normal distribution).",
            "Rolling Return": "The average annualized return for a period ending at a particular date. For example, a 'rolling 1-year return' is calculated for every day of a dataset, providing a more comprehensive view of performance than calendar-year returns.",
            "Drawdown": "This term has two meanings in the report. 1) **Market Drawdown:** The peak-to-trough decline of an investment's market value, measuring downside risk. 2) **Consumption Delivered:** The amount of money taken from the portfolio for consumption, either by selling assets or by taking a loan.",
            "Percentile Paths": "In simulation visualizations, these are lines representing specific percentiles of outcomes across all simulations. For example, the '10th percentile path' shows how the portfolio evolved in the worst 10% of scenarios, while the '90th percentile path' shows the best 10% of scenarios.",
        },
        "Market Efficiency & Behavior Concepts": {
            "Efficient Market": "A market where asset prices fully reflect all available information, making it impossible to consistently achieve returns above the market average through stock picking or market timing. In an efficient market, returns should follow a random walk.",
            "Random Walk": "A theory suggesting that stock price changes are random and unpredictable, with each price movement independent of previous movements. This is a key assumption in many financial models and implies that past price movements cannot be used to predict future movements.",
            "Momentum": "A tendency for assets that have performed well in the recent past to continue performing well in the near future, and vice versa. The presence of momentum would show up as positive autocorrelation in returns and challenges the efficient market hypothesis.",
            "Mean Reversion": "A tendency for asset prices or returns to move back toward their historical average over time. Assets that have experienced extreme gains may decline, and those with extreme losses may recover. Mean reversion would show up as negative autocorrelation in returns.",
        },
        "Psychological & Behavioral Metrics": {
            "Time Underwater": "The number of years a portfolio spends below its previous all-time peak value. This metric quantifies how long an investor must endure seeing their portfolio 'underwater'—a psychologically challenging state that often triggers panic selling. Extended underwater periods test investor discipline and are a primary driver of strategy abandonment, even for fundamentally sound approaches. Reported as the median across all simulation paths.",
            "Peak Drawdown Recovery Time": "The number of years required to recover from the worst drawdown (peak-to-trough decline) experienced during the simulation. This measures how long an investor must wait to 'break even' after their worst-case scenario. Research shows that recovery periods exceeding 3-5 years significantly increase the likelihood of investors abandoning their strategy. Reported as the median across all simulation paths.",
            "Consecutive Declining Years (P90)": "The longest streak of consecutive years where the portfolio value declined year-over-year. This metric captures sustained losing periods that severely test psychological resilience. Most investors struggle to maintain conviction after 2-3 consecutive down years, regardless of long-term fundamentals. Reported as the 90th percentile (worst-case scenario) to highlight extreme stress periods.",
            "Severe Drawdown Frequency": "The number of distinct periods where the portfolio experienced a drawdown of 20% or more from a peak. This counts major market corrections and crashes—events that trigger intense emotional responses and media panic. Frequent severe drawdowns indicate high psychological volatility, even if the strategy eventually recovers. Reported as the median across all simulation paths.",
            "Years Below Initial Investment": "The number of years where the portfolio value remains below the starting capital. Being 'down' on initial investment creates powerful regret and loss aversion, often prompting investors to 'cut their losses' prematurely. This metric is particularly relevant for retirees who may not have time to wait for recovery. Reported as the median across all simulation paths.",
        },
        "Taxation Concepts": {
            "Asset Management Fee": "An annual fee charged by a fund manager or investment service, calculated as a percentage of the total asset value. In this simulation, it is treated as an additional expense that must be covered either by selling assets (Trinity) or by increasing debt (Loan Drawdown).",
            "Capital Gains Tax": "A tax on the profit realized on the sale of a non-inventory asset. It's the difference between the sale price and the original cost (cost basis).",
            "Cost Basis": "The original value of an asset for tax purposes, usually the purchase price. It's used to calculate capital gains. In this simulation, the cost basis of the portfolio is tracked to accurately model the tax implications of deleveraging sales.",
            "Wealth Tax / ISK Tax": "A Swedish tax system (Investeringssparkonto) where a small annual tax is applied to the total value of the investment account, rather than taxing capital gains when assets are sold. This simplifies taxation by charging a fixed percentage of the account value each year, regardless of whether gains or losses were realized. It's an alternative to the traditional capital gains tax model.",
        },
        "General Statistical Terms": {
            "Median": "The middle value in a sorted list of numbers. 50% of the outcomes are above the median and 50% are below.",
            "Percentile": "A measure used in statistics indicating the value below which a given percentage of observations in a group of observations falls. For example, the 10th percentile is the value below which 10% of the observations may be found.",
            "Interquartile Range (IQR)": "A measure of statistical dispersion, being equal to the difference between the 75th and 25th percentiles. It represents the range of the middle 50% of outcomes and is less sensitive to extreme outliers than the standard deviation.",
            "Inflation-Adjusted Value (Real Value)": "The value of money or assets expressed in terms of the amount of goods or services that one unit of money can buy. It's the value after accounting for inflation.",
            "Nominal Value": "The face value of money or assets, without being adjusted for inflation.",
        }
    }

@ttl_cache(ttl=3600)
def get_flat_glossary_lookup():
    """
    Flattens get_glossary_data()'s category groupings into one label ->
    tooltip dict, for O(1) lookups when enriching many metric rows in a
    single report render (a fresh linear scan per label is wasteful).
    """
    flat = {}
    for terms in get_glossary_data().values():
        flat.update(terms)
    return flat

def get_metric_tooltip(label):
    """
    Looks up a metric's glossary definition by exact label match, for
    enriching key/value report tables with hover tooltips.

    Returns the tooltip text, or None if the label has no glossary entry.
    """
    return get_flat_glossary_lookup().get(label)

@ttl_cache(ttl=3600)
def get_methodology_flowchart_description():
    """
    Returns the description text for the methodology flowchart.
    This is used in both UI and PDF to maintain consistency and eliminate duplication.
    """
    return "The following flowchart illustrates the step-by-step process of the Monte Carlo simulation:"

@ttl_cache(ttl=3600)
def get_methodology_intro():
    """Returns a brief introduction to the Monte Carlo simulation methodology."""
    return """
    This Monte Carlo simulation evaluates financial strategies for generating liquidity from a portfolio over multi-decade timeframes. By running thousands of scenarios with randomized market returns, we can quantify the range of potential outcomes and assess the risk-reward profile of different approaches such as <b>Asset Withdrawal</b> (Trinity Study) and <b>Loan Drawdown</b> (Buy, Borrow, Die).
    """

@ttl_cache(ttl=3600)
def get_methodology_detailed():
    """Returns the comprehensive methodology description with all technical details."""
    return """
    <b>Stage 1: Asset Return Modeling</b><br/>
    This stage defines the asset's return characteristics, which form the basis for the simulation. Two models are available:
    <br/>• <i>Bootstrap Model:</i> This model loads historical price data for an asset (e.g., BTC/USD or a stock index). It then computes the historical distribution of rolling annual returns. This method is designed to capture the asset's authentic historical volatility and return profile, including phenomena such as "fat tails" (extreme events) and sequence risk. The simulation then samples directly from these historical returns.
    <br/>• <i>Parametric Model:</i> This model simulates returns based on user-defined parameters for expected annual return and volatility. Daily returns are drawn from a normal distribution, a standard assumption in financial modeling for assets like a global index fund. This allows for testing scenarios that may differ from historical performance.
    <br/><br/>
    <b>Stage 2: Monte Carlo Simulation Engine</b><br/>
    This is the core of the analysis, where thousands of parallel "possible futures" are simulated to assess the range of outcomes. The simulation operates using two nested loops:
    <br/><br/>
    <u>Scenario Loop (Outer):</u> For each of the N scenarios (e.g., 10,000 simulations):
    <br/>• Initialize a fresh portfolio with starting capital
    <br/>• Execute the initial strategy setup (Year 0)
    <br/>• Enter the Year Loop
    <br/><br/>
    <u>Year Loop (Inner):</u> For each year in the time horizon, the following events occur sequentially:
    <br/><br/>
    1. <u>Market Event:</u> The asset's performance for the year is determined. In 'Bootstrap' mode, an annual return is randomly selected from the historical data. In 'Parametric' mode, 365 days of small, random price changes are simulated based on the specified parameters. The portfolio's asset value is updated accordingly.
    <br/><br/>
    2. <u>Interest Accrual:</u> Interest is calculated and applied to both cash holdings (positive interest) and outstanding debt (interest costs).
    <br/><br/>
    3. <u>Strategy Execution:</u> Each simulation uses a <b>Strategy</b> (the decision-making logic) to determine what actions to take. The strategy evaluates the current portfolio state, historical performance, and mandatory costs to decide on the optimal course of action.
    <br/><br/>
    <b>Available Actions:</b> Strategies can issue commands to perform various actions, including:
    <br/>• <i>Sell Assets:</i> Liquidate a portion of the portfolio to generate cash (used by the Trinity/Withdrawal strategy)
    <br/>• <i>Take Loan:</i> Borrow money against the portfolio value (used by the Buy, Borrow, Die strategy)
    <br/>• <i>Repay Debt:</i> Pay down outstanding loans to reduce leverage
    <br/>• <i>Add Contributions:</i> Inject new capital into the portfolio
    <br/>• <i>Suspend Drawdowns:</i> Temporarily halt consumption withdrawals based on risk thresholds
    <br/><br/>
    <b>Built-in Strategies:</b> The simulation includes pre-built strategies like "Asset Withdrawal" (Trinity Study approach) and "Loan Drawdown" (Buy, Borrow, Die). However, custom strategies can be designed to combine any of these actions based on sophisticated logic, market conditions, or risk metrics.
    <br/><br/>
    4. <u>Portfolio Management:</u> A <b>Portfolio Manager</b> (the execution and bookkeeping engine) executes the strategy's commands while maintaining accurate records of all transactions, costs, taxes, and portfolio state. This includes:
    <br/>• Executing asset sales and purchases
    <br/>• Processing loan drawdowns and repayments
    <br/>• Calculating and applying transaction costs
    <br/>• Computing capital gains taxes
    <br/>• Tracking cost basis for tax purposes
    <br/><br/>
    5. <u>Risk Management (LTV Thresholds):</u> For loan-based strategies, a tiered Loan-to-Value (LTV) management system can be enabled to prevent insolvency. This includes a <b>Warning Tier</b> that proactively suspends new loan drawdowns if LTV exceeds a lower threshold (e.g., 50%), and an <b>Action Tier</b> that triggers emergency deleveraging (forced asset sales to repay debt) if LTV breaches a higher, more critical threshold (e.g., 70%). The portfolio manager executes these risk management actions automatically when triggered by the strategy.
    <br/><br/>
    6. <u>State Recording:</u> At the end of each year, the portfolio's complete state is recorded, including Asset Value, Debt, Net Worth, Cash Position, and all transaction details. This creates a comprehensive year-by-year history for each simulation path.
    <br/><br/>
    After completing all years in the Year Loop, the final scenario results are stored, and the process repeats for the next scenario.
    <br/><br/>
    <b>Stage 3: Results Analysis & Insights</b><br/>
    Following the completion of all simulations, this stage consolidates the results to provide meaningful insights:
    <br/><br/>
    • <u>Statistical Aggregation:</u> The data from all simulations is aggregated, and key statistics are calculated. To provide a robust view of the "typical" outcome and its variability, this analysis focuses on the <b>median</b> (50th percentile) and the <b>Interquartile Range (IQR)</b>, which represents the 25th to 75th percentile of outcomes. These metrics are less sensitive to extreme outliers than the mean and standard deviation, making them more suitable for analyzing the often-skewed distributions found in financial modeling.
    <br/><br/>
    • <u>Visualization Generation:</u> Interactive plots and charts are created to illustrate the range of outcomes, including time-series projections, distribution histograms, and comparative analyses.
    <br/><br/>
    • <u>AI-Powered Analysis:</u> An AI model reviews the quantitative results to provide qualitative insights, risk assessments, and strategic recommendations. This narrative analysis helps interpret the "why" behind the numbers and offers context for decision-making.
    <br/><br/>
    • <u>PDF Report Compilation:</u> All findings, visualizations, and analyses are compiled into a comprehensive PDF report for review and archiving.
    """

def get_methodology_description():
    """
    Returns the complete methodology description.
    This is kept for backward compatibility with PDF generation.
    """
    return f"""
    <b>Methodology Overview</b><br/><br/>
    {get_methodology_intro()}
    <br/><br/>
    {get_methodology_detailed()}
    """


def get_methodology_with_flowchart_content(styles):
    """
    Returns methodology content with flowchart image for PDF.
    Matches UI structure: intro → flowchart → detailed description.
    Uses white background flowchart for better PDF printing.
    """
    from reportlab.platypus import Paragraph, Spacer, Image
    from reportlab.lib.units import inch
    from reporting.flowchart import ensure_flowchart_image
    import os
    
    content = []
    
    # 1. Add methodology intro text
    content.append(Paragraph(get_methodology_intro(), styles['Justify']))
    content.append(Spacer(1, 0.3 * inch))
    
    # 2. Add flowchart section
    content.append(Paragraph("<b>Simulation Process Flow</b>", styles['H3']))
    content.append(Spacer(1, 0.1 * inch))
    content.append(Paragraph(get_methodology_flowchart_description(), styles['Normal']))
    content.append(Spacer(1, 0.2 * inch))
    
    # Ensure flowchart exists (light background for PDF)
    flowchart_path = ensure_flowchart_image(output_dir="assets", bg="light")
    
    if flowchart_path and os.path.exists(flowchart_path):
        # Add flowchart image - resize to fit page width
        img = Image(flowchart_path, width=6.5*inch, height=6.5*inch)  # Square 1:1 ratio
        content.append(img)
    else:
        content.append(Paragraph(
            "<i>Flowchart image not available. Install mermaid-cli or Playwright to generate flowcharts.</i>",
            styles['Normal']
        ))
    
    content.append(Spacer(1, 0.3 * inch))
    
    # 3. Add detailed methodology description
    content.append(Paragraph(get_methodology_detailed(), styles['Justify']))
    
    return content



@ttl_cache(ttl=3600)
def get_disclaimer_text():
    return """\n    <b>Important Disclaimer: Not Financial Advice</b><br/><br/>
    This document and its contents are for informational and educational purposes only and do not constitute financial, investment, legal, or tax advice. The simulations and analyses presented herein are based on historical data and mathematical models, which have inherent limitations.
    <br/><br/>
    <b>No Guarantee of Future Performance:</b> Past performance, whether actual or simulated, is not indicative of future results. The future performance of any asset or financial strategy is unknown and subject to a wide range of market, economic, and other risks. There is no guarantee that any of the outcomes projected in this report will be realized.
    <br/><br/>
    <b>Simulation-Based Analysis:</b> The results in this report are the output of a Monte Carlo simulation, which is a tool for modeling the probability of different outcomes. The simulation relies on assumptions about asset returns, volatility, and other economic factors that may not hold true in the future. The range of outcomes presented does not represent all possible scenarios.
    <br/><br/>
    <b>Consult a Professional:</b> You should not make any financial decisions based solely on the information contained in this report. Before making any investment or financial planning decisions, you should consult with a qualified and licensed financial advisor who can assess your individual circumstances and risk tolerance.
    <br/><br/>
    The author and publisher of this report disclaim all liability for any direct or indirect loss or damage arising from the use of, or reliance on, the information and analysis contained herein.
    """



def get_strategic_analysis_content(params, evaluation_data=None):
    """
    Returns structured content for the Strategic Analysis chapter.
    
    This function generates a dynamic chapter that works for all strategy types,
    including built-in and custom strategies. It provides:
    1. General introduction to transaction types
    2. Table of possible transaction types
    3. Strategy-specific description
    
    Args:
        params (dict): Simulation parameters containing strategy information
        evaluation_data (dict, optional): Cached strategy evaluation data to skip database lookup
        
    Returns:
        dict: Structured content with 'intro', 'transaction_types', and 'strategy_description'
    """
    
    # General introduction about transaction types
    intro_text = """
    Financial strategies in this simulation operate by executing various types of transactions to achieve their goals. 
    Understanding the available transaction types is essential for interpreting how a strategy works and why it produces 
    certain outcomes. This chapter first introduces the general toolkit of transactions available to any strategy, 
    then describes the specific approach used in this simulation.
    """
    
    # Define all possible transaction types (only actions strategies can control)
    transaction_types = [
        {
            "label": "Asset Sales",
            "value": "Selling assets to generate cash for consumption, costs, or debt repayment. Triggers capital gains tax."
        },
        {
            "label": "Asset Purchases",
            "value": "Buying assets with available cash to increase portfolio value and future growth potential."
        },
        {
            "label": "Borrowing",
            "value": "Taking loans against portfolio value to fund expenses without selling assets. Incurs interest costs."
        },
        {
            "label": "Debt Repayment",
            "value": "Paying down existing debt to reduce interest costs and improve the loan-to-value ratio."
        },
        {
            "label": "Contributions",
            "value": "Adding new capital to the portfolio from external sources (e.g., salary, savings)."
        },
        {
            "label": "Cash Buffer Management",
            "value": "Holding cash reserves to fund withdrawals in down markets, reducing the need to sell assets at unfavorable prices."
        },
        {
            "label": "Deleveraging",
            "value": "Strategy-triggered asset sales when LTV ratios exceed thresholds, used to reduce debt and restore healthy leverage ratios."
        }
    ]
    
    # Get strategy-specific description
    strategy_key = params.get('strategy', 'unknown')
    
    # Built-in strategy descriptions
    strategy_descriptions = {
        'trinity': """
            <b>Trinity Study Strategy (Asset Withdrawal)</b><br/><br/>
            This is a traditional decumulation strategy based on the famous Trinity Study. The strategy operates by 
            systematically selling assets each year to fund living expenses.<br/><br/>
            
            <b>Core Mechanics:</b><br/>
            - Each year, a predetermined percentage of the initial portfolio value is withdrawn<br/>
            - The withdrawal amount is adjusted annually for inflation<br/>
            - All cash needs (consumption + costs) are funded by selling assets<br/>
            - No debt is ever taken<br/><br/>
            
            <b>Primary Goal:</b> Ensure the portfolio is not depleted before the end of the time horizon. 
            Success means the portfolio provides the desired cash flow for the entire period, even if the 
            final value is less than the starting value.<br/><br/>
            
            <b>Key Risk:</b> Portfolio depletion, especially from "sequence of returns risk" where poor 
            returns in early years can disproportionately harm the portfolio's longevity.<br/><br/>
            
            <b>Transaction Pattern:</b> This strategy uses only Asset Sales and Cost Payments. It never 
            borrows, contributes additional capital, or purchases assets after the initial investment.
        """,
        
        'buy_borrow_die': """
            <b>Buy, Borrow, Die Strategy (Loan Drawdown)</b><br/><br/>
            This is a leveraging strategy that avoids selling assets by borrowing against the portfolio 
            to fund living expenses. The name refers to the lifecycle: Buy assets, Borrow against them, 
            and let the estate settle the debt upon death (avoiding capital gains tax).<br/><br/>
            
            <b>Core Mechanics:</b><br/>
            - Assets remain fully invested, preserving compound growth potential<br/>
            - Each year, new loans are taken to fund consumption and costs<br/>
            - Interest on accumulated debt compounds over time<br/>
            - Sophisticated LTV (Loan-to-Value) management prevents excessive leverage<br/><br/>
            
            <b>Primary Goal:</b> Fund living expenses while preserving the portfolio's real (inflation-adjusted) 
            value. Success means maintaining purchasing power while avoiding insolvency.<br/><br/>
            
            <b>Key Risks:</b> Insolvency (debt exceeding asset value) and forced deleveraging. If the LTV 
            ratio breaches critical thresholds, assets must be sold to reduce debt, often at inopportune 
            times, which can permanently impair portfolio value.<br/><br/>
            
            <b>Transaction Pattern:</b> This strategy primarily uses Borrowing and Cost Payments. It may 
            trigger Deleveraging (asset sales for debt repayment) when LTV ratios become too high. It never 
            contributes additional capital or purchases assets after the initial investment.
        """,
        
        'get_rich_stay_rich': """
            <b>Get Rich, Stay Rich Strategy</b><br/><br/>
            This is a three-phase lifecycle strategy designed to first build wealth through contributions 
            and growth, then transition to sustainable withdrawals once a target net worth is achieved.<br/><br/>
            
            <b>Phase 1 - Get Rich (Accumulation):</b><br/>
            - Make regular contributions to the portfolio<br/>
            - Invest all available cash into assets<br/>
            - No withdrawals for consumption<br/>
            - Continue until asset value reaches the inflation-adjusted target net worth<br/><br/>
            
            <b>Phase 2 - Build Buffer (Transition):</b><br/>
            - Continue contributions<br/>
            - Sell asset growth above the target to build a cash reserve<br/>
            - Accumulate a cash buffer equal to several years of planned spending<br/>
            - Transition to Phase 3 when buffer is fully built<br/><br/>
            
            <b>Phase 3 - Stay Rich (Decumulation):</b><br/>
            - Begin regular withdrawals for consumption<br/>
            - In good years: sell assets to fund spending and replenish cash buffer<br/>
            - In bad years: use cash buffer to reduce or avoid asset sales<br/>
            - Dynamic cash management smooths consumption through market volatility<br/><br/>
            
            <b>Primary Goal:</b> Build wealth to a target level, then maintain that wealth while funding 
            a sustainable lifestyle. Success means reaching the target and maintaining purchasing power 
            throughout the withdrawal phase.<br/><br/>
            
            <b>Key Risk:</b> Market downturns during the transition or early withdrawal phase can delay 
            or prevent reaching the target, or deplete the cash buffer requiring asset sales in down markets.<br/><br/>
            
            <b>Transaction Pattern:</b> This strategy uses all transaction types except Borrowing and 
            Deleveraging. It actively uses Contributions (Phase 1-2), Asset Purchases (Phase 1-2), 
            Asset Sales (Phase 2-3), and Cost Payments (all phases).
        """
    }
    
    # Get the appropriate description
    if strategy_key == 'custom':
        # For custom strategies, use the AI-generated description from the database
        custom_desc = params.get(
            'custom_strategy_ai_description',
            params.get('custom_strategy_description', 'No description provided for this custom strategy.'),
        )
        strategy_description = f"""
            <b>Custom Strategy: {params.get('custom_strategy_name', 'User-Defined Strategy')}</b><br/><br/>
            {custom_desc}
        """
    else:
        # Use built-in description or fallback
        strategy_description = strategy_descriptions.get(
            strategy_key,
            f"<b>Strategy: {strategy_key.replace('_', ' ').title()}</b><br/><br/>No detailed description available for this strategy."
        )
    
    # Determine flowchart availability for built-in strategies
    import os
    strategy_map = {
        'trinity': 'trinity',
        'buy_borrow_die': 'bbd',
        'get_rich_stay_rich': 'grsr'
    }
    
    flowchart_info = {
        'available': strategy_key in strategy_map,
        'key': strategy_map.get(strategy_key, None),
        'dark_path': f"assets/{strategy_map[strategy_key]}_strategy_flowchart.png" if strategy_key in strategy_map else None,
        'white_path': f"assets/{strategy_map[strategy_key]}_strategy_flowchart_white.png" if strategy_key in strategy_map else None,
    }
    
    # Check if flowcharts need generation
    if flowchart_info['available']:
        flowchart_info['needs_generation_dark'] = not os.path.exists(flowchart_info['dark_path'])
        flowchart_info['needs_generation_white'] = not os.path.exists(flowchart_info['white_path'])
    
    # Fetch strategy evaluation data from leaderboard (or use cached data if provided)
    if evaluation_data is None:
        # No cached data - fetch from database (initial simulation run)
        try:
            from reporting.strategy_evaluation_charts import get_evaluation_for_strategy
            
            if strategy_key == 'custom':
                lookup_display_name = params.get('custom_strategy_name', 'Custom Strategy')
                lookup_class_name = params.get('custom_strategy_class_name')
            else:
                # Convert snake_case to display name for lookup
                lookup_display_name = ' '.join(word.capitalize() for word in strategy_key.split('_'))
                lookup_class_name = strategy_key
                
            evaluation_data = get_evaluation_for_strategy(
                lookup_display_name, 
                class_name=lookup_class_name,
                git_commit_sha=params.get('git_commit_sha'),
                clone_source_commit_sha=params.get('clone_source_commit_sha')
            )
        except Exception as e:
            import logging
            logging.warning(f"Could not fetch strategy evaluation data: {e}")
    else:
        # Using cached evaluation data (viewing saved simulation)
        import logging
        logging.info(f"Using cached evaluation data for strategy {strategy_key}")
    
    return {
        'intro': ' '.join(intro_text.strip().split()),
        'transaction_types': transaction_types,
        'strategy_description': strategy_description,
        'flowchart_info': flowchart_info,
        'evaluation_data': evaluation_data  # None if not evaluated yet
    }


def get_strategy_evaluations_content():
    """
    Returns content for the Strategy Evaluations appendix.
    
    This uses the centralized evaluation_info module which is the
    single source of truth shared with the UI leaderboard.
    """
    from utils.evaluation_info import get_evaluation_works_full_markdown
    
    # Get the complete markdown from centralized source
    full_markdown = get_evaluation_works_full_markdown()
    
    # Split into sections for flexibility in rendering
    # (some renderers may want to handle sections separately)
    sections = full_markdown.split('### ')
    
    result = {
        'intro': f"Strategies on the leaderboard are stress-tested across **8 standardized market scenarios** to evaluate robustness and performance. This appendix explains the evaluation methodology.",
        'full_content': full_markdown
    }
    
    # Also provide individual sections for backwards compatibility
    for section in sections:
        if section.startswith('Evaluation Process'):
            result['process'] = '### ' + section.strip()
        elif section.startswith('Market Scenarios'):
            result['scenarios'] = '### ' + section.strip()
        elif section.startswith('Score Components'):
            result['metrics'] = '### ' + section.strip()
        elif section.startswith('🧠 Wisdom of the Crowd'):
            result['wisdom'] = '### ' + section.strip()
    
    return result


