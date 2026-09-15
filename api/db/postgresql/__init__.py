"""PostgreSQL database implementation, split into per-domain mixins (R5.2b).

The public entry point is unchanged: import PostgreSQLDatabase from
db.postgresql_db (which also applies the ttl_cache wrapping of read-heavy
methods). This package only assembles the class from its domain modules;
method bodies moved verbatim from the old single-file implementation.
"""

from .core import ConnectionCore
from .users import UsersMixin
from .simulations import SimulationsMixin
from .strategies import StrategiesMixin
from .leaderboard import LeaderboardMixin
from .jobs import JobsMixin
from .system import SystemMixin


class PostgreSQLDatabase(UsersMixin, SimulationsMixin, StrategiesMixin,
                         LeaderboardMixin, JobsMixin, SystemMixin,
                         ConnectionCore):
    """
    PostgreSQL database implementation with connection pooling.
    """


__all__ = ['PostgreSQLDatabase']
