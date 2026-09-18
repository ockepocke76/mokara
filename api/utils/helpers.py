"""
Utility helper functions.

Common utilities extracted from app.py for reusability across the application.
"""


def is_production() -> bool:
    """
    Check if the app is running in a production environment (Cloud Run).
    Returns True if running on Cloud Run, False otherwise (local development).
    """
    import os
    return os.getenv('K_SERVICE') is not None


def slugify(text: str) -> str:
    """
    Converts a string into a URL-friendly slug.
    
    Args:
        text: Text to slugify
        
    Returns:
        URL-friendly slug string, or empty string if text is None
    """
    if text is None:
        return ""
    return text.lower().replace(' ', '-').replace('/', '-')


def generate_simulation_description(sim_params: dict) -> str:
    """
    Generates a concise description of a simulation from its parameters.
    
    Args:
        sim_params: Dictionary of simulation parameters
        
    Returns:
        Human-readable simulation description string
    """
    from core.simulation_currency import get_simulation_currency
    from core.currency_config import format_currency_amount
    
    # Extract key parameters with fallback defaults
    asset_model = sim_params.get('asset_model', 'Unknown Asset')
    strategy = sim_params.get('strategy', 'Unknown Strategy')
    num_years = sim_params.get('num_years', 0)
    initial = sim_params.get('initial_investment', 0)
    num_sims = sim_params.get('num_simulations', 0)
    
    # Format asset model name
    asset_display_map = {
        'bootstrap_gspc': 'S&P 500 (Bootstrap)',
        'bootstrap_btc': 'Bitcoin (Bootstrap)',
        'gbm_gspc': 'S&P 500 (GBM)',
        'gbm_btc': 'Bitcoin (GBM)'
    }
    asset_display = asset_display_map.get(asset_model, asset_model)
    
    # Format strategy name
    strategy_display_map = {
        'buy_and_hold': 'Buy and Hold',
        'fixed_withdrawal': 'Fixed Withdrawal',
        'percentage_withdrawal': 'Percentage Withdrawal',
        'dynamic_withdrawal': 'Dynamic Withdrawal',
        'buy_borrow_die': 'Buy, Borrow, Die',
        'trinity': 'Trinity Study',
        'guyton_klinger': 'Guyton-Klinger'
    }
    strategy_display = strategy_display_map.get(strategy, strategy)
    
    # Get currency and format initial investment
    currency = get_simulation_currency(sim_params)
    
    # Format initial investment with correct currency
    initial_formatted = format_currency_amount(initial, currency, decimals=0)
    
    return f"{asset_display} • {strategy_display} • {num_years} years • {initial_formatted} initial • {num_sims:,} simulations"


def find_report_file(simulation_record):
    """
    Find the PDF report file for a given simulation record.

    Args:
        simulation_record: Database record containing simulation info

    Returns:
        Path to report file or None if not found
    """
    import os
    report_path_str = simulation_record.get('report_path')
    if report_path_str and os.path.exists(report_path_str):
        return report_path_str
    return None


def clamp_for_log_viz(value, floor=1.0):
    """Clamp a value (which may be None/NaN/<=0) to a positive floor for a log-scale chart."""
    import numpy as np
    if value is None or not np.isfinite(value):
        return floor
    return max(value, floor)


def compute_log_scale_histogram(values, min_bins=30, max_bins=100, floor=1.0):
    """
    Bin `values` into log-spaced bins for a log-scale x-axis histogram.

    Non-finite entries (NaN/inf) are dropped before binning, so a single bad
    value can't taint the percentile/bin-edge calculation for the whole series.
    Remaining non-positive values are clamped to `floor` so they still show up
    on the low end of the log axis instead of being invisible or crashing it.
    """
    import numpy as np
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return np.array([]), np.array([floor, floor * 10])

    clamped = np.clip(clean, floor, None)
    p1 = np.percentile(clamped, 1)
    p99 = np.percentile(clamped, 99)
    if p99 <= p1:
        p99 = p1 + 1

    num_bins = int(np.clip(np.sqrt(clamped.size), min_bins, max_bins))
    bin_edges = np.geomspace(p1, p99, num_bins + 1)
    return np.histogram(clamped, bins=bin_edges)
