"""
PostgreSQL Database Implementation - COMPLETE

Automatically adapted from SQLiteDatabase with PostgreSQL-specific modifications.
Key changes:
- sqlite3 → psycopg2
- Thread-local connections → Connection pooling
- AUTOINCREMENT → SERIAL
- lastrowid → RETURNING clause
- Dict row factory → RealDictCursor

R5.2b: the implementation now lives in the db/postgresql/ package as
per-domain mixins assembled into the same PostgreSQLDatabase class. This
module stays the public import path and applies the ttl_cache wrapping of
read-heavy methods.
"""

from core.cache import ttl_cache

from .postgresql import PostgreSQLDatabase
# Legacy re-exports: these helpers historically lived at module level here.
from .postgresql.simulations import _save_dataframe_to_db, _save_dict_to_db


# Cache read-heavy methods (self hashes by identity; db is a singleton)
PostgreSQLDatabase.get_leaderboard = ttl_cache(ttl=300)(PostgreSQLDatabase.get_leaderboard)
PostgreSQLDatabase.get_strategy_evaluation = ttl_cache(ttl=300)(PostgreSQLDatabase.get_strategy_evaluation)

# Community Stats Cache (1 hour)
PostgreSQLDatabase.get_community_stats = ttl_cache(ttl=3600)(PostgreSQLDatabase.get_community_stats)

# Longer cache
PostgreSQLDatabase.get_simulation_details = ttl_cache(ttl=3600)(PostgreSQLDatabase.get_simulation_details)
# check_simulation_cache deliberately uncached: breaks realtime status updates.

# Strategy caching — short TTL for editable admin list
PostgreSQLDatabase.get_all_custom_strategies_for_admin = ttl_cache(ttl=60)(PostgreSQLDatabase.get_all_custom_strategies_for_admin)
