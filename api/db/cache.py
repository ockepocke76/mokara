"""
Database Query Caching Wrappers

Provides cached versions of expensive database queries to improve performance.
All caches use short TTL to balance performance with data freshness.
"""

import logging

from core.cache import ttl_cache
from db.database import db


# NOTE: intentionally NOT cached — stale results broke strategy clone/edit flows.
def get_user_custom_strategies_cached(user_id):
    """
    Cached wrapper for get_user_custom_strategies.
    
    TTL: DISABLED (Real-time)
    Reason: Strategy Designer modifies this list frequently (clone, delete, save).
    Stale cache (even with clear()) was causing missing strategies. 
    Performance impact is negligible for single-user queries.
    """
    if user_id is None:
        return []
    return db.get_user_custom_strategies(user_id)


@ttl_cache(ttl=300)
def get_leaderboard_cached(category=None, limit=10):
    """
    Cached wrapper for get_leaderboard.
    
    TTL: 5 minutes
    Impact: Saves 86-117ms per leaderboard page load
    """
    return db.get_leaderboard(category=category, limit=limit)


@ttl_cache(ttl=300)
def get_leaderboard_with_profile_cached(profile_key='balanced', category=None, limit=10):
    """
    Cached wrapper for get_leaderboard_with_profile.
    Uses pre-calculated profile scores from STRATEGY_PROFILE_SCORES table.

    TTL: 5 minutes
    Impact: Eliminates client-side score recalculation (saves ~100-500ms per profile switch)
    """
    return db.get_leaderboard_with_profile(profile_key=profile_key, category=category, limit=limit)


def clear_leaderboard_cache(context=""):
    """Invalidate the leaderboard cache after anything changes a strategy's
    publish status (single publish/unpublish, or a bulk user purge/delete)."""
    try:
        get_leaderboard_with_profile_cached.clear()
        logging.info(f"Cleared leaderboard cache{f' ({context})' if context else ''}")
    except Exception:
        logging.exception("Failed to clear leaderboard cache")





@ttl_cache(ttl=180)
def get_user_simulations_cached(user_email):
    """
    Cached wrapper for get_user_simulations.
    
    TTL: 3 minutes
    Impact: Saves query time on Run Simulation tab
    """
    # Allow None to pass through - database returns demos for anonymous users  
    return db.get_user_simulations(user_email)


@ttl_cache(ttl=300)
def get_simulation_final_stats_cached(simulation_hash):
    """
    Cached wrapper for get_regeneration_data to extract final_stats and plot data.
    
    TTL: 5 minutes
    Impact: Saves 100-200ms per preview card load in My Simulations
    Returns final_stats, params, and precalculated plot data needed for previews.
    """
    if not simulation_hash:
        return None, None, None
    
    from db.regeneration_db import get_regeneration_data
    
    # Get full regeneration package
    regen_data = get_regeneration_data(simulation_hash)
    
    if not regen_data:
        return None, None, None
    
    # Extract what we need for preview cards
    final_stats = regen_data.get('stats', {})
    params = regen_data.get('params', {})
    precalc_data = regen_data.get('precalculated_data', {})
    
    # Extract the specific plot data we need
    plot_data = {
        'net_worth_paths': precalc_data.get('net_worth_percentile_paths'),
        'asset_paths': precalc_data.get('asset_percentile_paths'),
    }
    
    return final_stats, params, plot_data
