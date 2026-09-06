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
