"""
Utility functions for working with strategy classes.
Provides centralized access to strategy metadata like descriptions and class mappings.
"""

import inspect
from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy


# Centralized mapping of strategy display names to their classes
STRATEGY_CLASS_MAP = {
    'Trinity Study (Asset Withdrawal)': TrinityStrategy,
    'Trinity': TrinityStrategy,
    'Buy, Borrow, Die': BuyBorrowDieStrategy,
    'Buy Borrow Die': BuyBorrowDieStrategy,
    'Get Rich Stay Rich': GetRichStayRichStrategy
}

# Mapping of strategy keys to classes (for backwards compatibility)
STRATEGY_KEY_MAP = {
    'trinity': TrinityStrategy,
    'bbd': BuyBorrowDieStrategy,
    'grsr': GetRichStayRichStrategy
}


def get_strategy_description(strategy_name_or_key: str) -> str:
    """
    Get the description for a built-in strategy.
    
    Args:
        strategy_name_or_key: Either the display name (e.g., "Trinity Study (Asset Withdrawal)")
                              or the key (e.g., "trinity")
    
    Returns:
        The strategy's docstring as a description, or empty string if not found
    """
    # Try by display name first
    strategy_class = STRATEGY_CLASS_MAP.get(strategy_name_or_key)
    
    # If not found, try by key
    if not strategy_class:
        strategy_class = STRATEGY_KEY_MAP.get(strategy_name_or_key)
    
    if strategy_class and strategy_class.__doc__:
        return inspect.cleandoc(strategy_class.__doc__)
    
    return ""


def get_strategy_class(strategy_name_or_key: str):
    """
    Get the strategy class for a given name or key.
    
    Args:
        strategy_name_or_key: Either the display name or the key
    
    Returns:
        The strategy class, or None if not found
    """
    # Try by display name first
    strategy_class = STRATEGY_CLASS_MAP.get(strategy_name_or_key)
    
    # If not found, try by key
    if not strategy_class:
        strategy_class = STRATEGY_KEY_MAP.get(strategy_name_or_key)
    
    return strategy_class


def get_builtin_strategy_info():
    """
    Get information about all built-in strategies.
    
    Returns:
        Dictionary mapping strategy names to their info (key, display_name, description)
    """
    return {
        "Get Rich Stay Rich": {
            "key": "grsr",
            "display_name": "Get Rich Stay Rich",
            "description": get_strategy_description("grsr"),
        },
        "Trinity (4% Rule)": {
            "key": "trinity",
            "display_name": "Trinity",
            "description": get_strategy_description("trinity"),
        },
        "Buy, Borrow, Die": {
            "key": "bbd",
            "display_name": "Buy Borrow Die",
            "description": get_strategy_description("bbd"),
        },
    }


import hashlib
import json

def calculate_strategy_hash(code: str, parameters: dict) -> str:
    """
    Calculate a deterministic hash for a strategy based on its code and parameters.
    Used for local versioning before Git commits.
    """
    # Normalize inputs
    code_content = code.strip()
    
    # Sort keys for deterministic JSON serialization
    param_content = json.dumps(parameters, sort_keys=True)
    
    # Combine content
    combined = f"{code_content}{param_content}".encode('utf-8')
    
    # Generate SHA256
    sha = hashlib.sha256(combined).hexdigest()
    
    # Prefix to indicate it's a draft/content hash
    return f"draft_{sha[:12]}"


def next_free_name(base: str, taken, label: str = None) -> str:
    """First name not in `taken`: the base itself, then suffixed forms.

    With label='clone': "base (clone)", "base (clone 2)", ... — the clone
    service's convention. Without a label: "base (2)", "base (3)", ... —
    the save layer's convention. One implementation so the two can't drift.
    """
    if base not in taken:
        return base
    first = f"{base} ({label})" if label else f"{base} (2)"
    if first not in taken:
        return first
    n = 2 if label else 3
    while True:
        candidate = f"{base} ({label} {n})" if label else f"{base} ({n})"
        if candidate not in taken:
            return candidate
        n += 1
