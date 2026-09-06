"""
Currency Helper Functions for Simulations

This module provides utilities for extracting and handling currency information
from simulation parameters, with fallback logic for legacy simulations.
"""

from typing import Optional


def get_simulation_currency(params: dict, user_currency: Optional[str] = None) -> str:
    """
    Extract the currency used for a simulation from its parameters.

    This function handles both new simulations (with currency in params)
    and legacy simulations (without currency field).

    Args:
        params: Simulation parameters dictionary
        user_currency: The current user's currency preference, used as a
                       fallback for legacy simulations that lack a currency
                       field. Pass None (default) to preserve historical
                       accuracy — legacy simulations then report SEK.

    Returns:
        Currency code (SEK, USD, or EUR)

    Examples:
        >>> params = {'initial_investment': 5000000, 'currency': 'SEK'}
        >>> get_simulation_currency(params)
        'SEK'

        >>> # Legacy simulation without currency field - defaults to SEK
        >>> old_params = {'initial_investment': 10000000}
        >>> get_simulation_currency(old_params)
        'SEK'  # Historical default

        >>> # Can optionally use the user's current currency
        >>> get_simulation_currency(old_params, user_currency='USD')
        'USD'
    """
    currency = params.get('currency')

    if currency:
        return currency

    # Fallback for legacy simulations: caller-supplied user preference
    if user_currency:
        return user_currency

    # Ultimate fallback: SEK (all historical simulations were in SEK)
    return 'SEK'


def format_simulation_currency_note(params: dict) -> str:
    """
    Generate a note about which currency was used for a simulation.

    Args:
        params: Simulation parameters dictionary

    Returns:
        Human-readable note about the currency
    """
    from core.currency_config import get_currency_info

    currency = params.get('currency')

    if currency:
        # Currency was explicitly stored
        info = get_currency_info(currency)
        return f"This simulation was run in {currency} ({info['name']})."
    else:
        # Legacy simulation - currency inferred
        inferred_currency = get_simulation_currency(params)
        info = get_currency_info(inferred_currency)
        return f"Currency: {inferred_currency} (inferred from current settings)."
