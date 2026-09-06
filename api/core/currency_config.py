"""
Currency Configuration Module

This module defines currency-specific configurations including:
- Currency metadata (symbols, locales)
- Conversion ratios for UI parameter ranges

Architecture:
- Simulations run in the user's selected currency (SEK, USD, or EUR)
- Parameter ranges are converted dynamically for UI display based on currency
- Asset prices are converted using historical FX data (separate module)
- No conversion needed at display time - values are already in user's currency
"""

# Default currency for non-logged-in users
DEFAULT_CURRENCY = 'USD'

# Static currency conversion ratios (for UI parameter ranges only)
# These are used to scale slider ranges appropriately for each currency
CURRENCY_RATIOS = {
    'USD': 1.0,      # Base ratio
    'SEK': 10.0,     # 1 USD ≈ 10 SEK (for scaling ranges)
    'EUR': 0.95,     # 1 USD ≈ 0.95 EUR (for scaling ranges)
}

# Currency metadata
CURRENCY_METADATA = {
    'USD': {
        'name': 'US Dollar',
        'symbol': '$',
        'locale': 'en_US',
    },
    'SEK': {
        'name': 'Swedish Krona',
        'symbol': 'SEK',
        'locale': 'sv_SE',
    },
    'EUR': {
        'name': 'Euro',
        'symbol': '€',
        'locale': 'en_EU',
    },
}


def get_currency_ratio(currency_code: str) -> float:
    """
    Get the ratio for scaling UI ranges for a currency.
    
    Args:
        currency_code: Currency code (USD, SEK, EUR)
        
    Returns:
        Ratio for scaling UI parameter ranges
    """
    return CURRENCY_RATIOS.get(currency_code, 1.0)


def convert_parameter_range(base_range: dict, to_currency: str) -> dict:
    """
    Scale a parameter range for UI display based on currency.
    
    This is used to show appropriate slider ranges for each currency.
    For example, if USD range is 100K-1M, SEK range becomes 1M-10M.
    
    The actual simulation values are NOT converted - they stay in the
    user's selected currency.
    
    Args:
        base_range: Dictionary with 'min', 'max', 'step', 'value' keys
        to_currency: Target currency code for UI display
        
    Returns:
        Dictionary with scaled range values for UI
    """
    ratio = get_currency_ratio(to_currency)
    
    return {
        'min': int(base_range.get('min', 0) * ratio),
        'max': int(base_range.get('max', 0) * ratio),
        'step': int(base_range.get('step', 1) * ratio),
        'value': int(base_range.get('value', 0) * ratio),
        # Preserve other keys like display_name, description, etc.
        **{k: v for k, v in base_range.items() if k not in ['min', 'max', 'step', 'value']}
    }


def get_currency_info(currency_code: str) -> dict:
    """
    Get metadata for a specific currency.
    
    Args:
        currency_code: Currency code (USD, SEK, EUR)
        
    Returns:
        Dictionary with currency metadata
    """
    metadata = CURRENCY_METADATA.get(currency_code, CURRENCY_METADATA['SEK'])
    ratio = get_currency_ratio(currency_code)
    
    return {
        **metadata,
        'code': currency_code,
        'ratio': ratio,
    }


def format_currency_amount(amount: float, currency_code: str, decimals: int = 0) -> str:
    """
    Format an amount with appropriate currency symbol and thousands separators.
    
    Args:
        amount: Amount to format
        currency_code: Currency code
        decimals: Number of decimal places
        
    Returns:
        Formatted currency string
    """
    info = get_currency_info(currency_code)
    symbol = info['symbol']
    
    # Format the number first with standard formatting
    if decimals == 0:
        formatted = f"{amount:,.0f}"
    else:
        formatted = f"{amount:,.{decimals}f}"
    
    # Use locale-appropriate thousand separators
    # USD uses commas (10,000,000), SEK and EUR use spaces (10 000 000)
    if currency_code in ['SEK', 'EUR']:
        # Replace commas with spaces for European format
        formatted = formatted.replace(',', ' ')
    
    # For USD and EUR, put symbol before amount; for SEK, after
    if currency_code in ['USD', 'EUR']:
        return f"{symbol}{formatted}"
    else:
        return f"{formatted} {symbol}"


def format_compact_currency(amount: float, currency_code: str, decimals: int = 1) -> str:
    """
    Format a large currency amount with compact notation (K, M, B).
    
    Examples:
    - 2,500,000 USD -> 2.5 M USD
    - 54,000 USD -> 54.0 K USD
    
    Args:
        amount: Number to format
        currency_code: Currency code (USD, SEK, etc.)
        decimals: Number of decimal places (default 1)
        
    Returns:
        Formatted string (e.g. "2.5 M USD")
    """
    abs_amount = abs(amount)
    
    if abs_amount >= 1_000_000_000:
        val = amount / 1_000_000_000
        suffix = "B"
    elif abs_amount >= 1_000_000:
        val = amount / 1_000_000
        suffix = "M"
    elif abs_amount >= 1_000:
        val = amount / 1_000
        suffix = "K"
    else:
        # No compacting needed for small numbers
        return format_currency_amount(amount, currency_code, decimals=0)
        
    # Format the number
    if decimals == 0:
        formatted_val = f"{val:.0f}"
    else:
        formatted_val = f"{val:.{decimals}f}".rstrip('0').rstrip('.')
        
    # Replace dot with comma for European locales if desired?
    # Actually, standard K/M/B notation often keeps dot, but let's follow the app's style.
    # The user example was "2,7 M USD" (European style uses comma for decimal)
    # But usually code output is 2.7. Let's stick to 2.7 for now unless locale specifically demands otherwise.
    # Wait, the user request specifically showed "2,7 M USD" in their example text, 
    # but also "2,678,971 USD" as the BEFORE. 
    # The prompt says: "as... 2,7 M USD".
    # And "54 K USD".
    
    # Let's support the requested ",7" style if the currency suggests it?
    # SEK/EUR use comma for decimals. USD uses dot.
    if currency_code in ['SEK', 'EUR']:
        formatted_val = formatted_val.replace('.', ',')
        
    return f"{formatted_val} {suffix} {currency_code}"

def get_parameter_description(param_config: dict, currency_code: str) -> str:
    """
    Get the description for a parameter, appending currency if applicable.
    
    Args:
        param_config: Parameter configuration dictionary from config.yml
        currency_code: User's selected currency code
        
    Returns:
        Description with currency appended if is_currency is True
    """
    description = param_config.get('description', '')
    
    if param_config.get('is_currency', False):
        # Append currency to description
        currency_info = get_currency_info(currency_code)
        currency_name = currency_info['name']
        return f"{description} Currency: {currency_name} ({currency_code})."
    
    return description
