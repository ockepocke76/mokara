import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from psycopg2 import extras

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Product-analytics events (ANALYTICS_EVENTS): a write helper and the
    aggregate read used by the admin dashboard.

    Tracking must never break the request that triggered it, so every write
    swallows its own errors.
    """

    def __init__(self, db):
        self.db = db

    def track(self, event_type: str, user_id: Optional[int] = None,
              properties: Optional[Dict[str, Any]] = None) -> None:
        try:
            with self.db._connection_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ANALYTICS_EVENTS (user_id, event_type, properties) "
                    "VALUES (%s, %s, %s)",
                    (user_id, event_type, json.dumps(properties or {})),
                )
            logger.debug(f"Analytics tracked: {event_type} (User: {user_id})")
        except Exception as e:
            logger.error(f"Failed to track analytics event '{event_type}': {e}")

    # --- Standardized event helpers ---

    def track_simulation_run(self, user_id: Optional[int], asset: str, strategy: str,
                             duration: int, timestamp: datetime) -> None:
        self.track('simulation_run', user_id, {
            'asset_model': asset,
            'strategy_name': strategy,
            'duration_years': duration,
            'timestamp': timestamp.isoformat(),
        })

    # AI token usage is recorded per call in LLM_USAGE by core.llm (with
    # thinking tokens and cost) — no analytics event for it.

    def track_login(self, user_id: int, method: str) -> None:
        self.track('user_login', user_id, {'method': method})

    # --- Admin read side ---

    def summary(self, days: int = 30) -> Dict[str, Any]:
        """Aggregates over the last `days` days, computed in SQL."""
        with self.db._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cur:
            window = "timestamp >= NOW() - (%s * INTERVAL '1 day')"

            cur.execute(
                f"SELECT COUNT(*) AS events, COUNT(DISTINCT user_id) AS active_users "
                f"FROM ANALYTICS_EVENTS WHERE {window}", (days,))
            totals = cur.fetchone()

            cur.execute(
                f"SELECT DATE(timestamp) AS day, COUNT(*) AS count "
                f"FROM ANALYTICS_EVENTS WHERE {window} GROUP BY day ORDER BY day", (days,))
            per_day = [{"day": r["day"].isoformat(), "count": r["count"]} for r in cur.fetchall()]

            cur.execute(
                f"SELECT event_type, COUNT(*) AS count FROM ANALYTICS_EVENTS "
                f"WHERE {window} GROUP BY event_type ORDER BY count DESC", (days,))
            by_type = [dict(r) for r in cur.fetchall()]

            def top(prop: str):
                cur.execute(
                    f"SELECT properties->>%s AS name, COUNT(*) AS count "
                    f"FROM ANALYTICS_EVENTS "
                    f"WHERE event_type = 'simulation_run' AND {window} AND properties ? %s "
                    f"GROUP BY name ORDER BY count DESC LIMIT 5", (prop, days, prop))
                return [dict(r) for r in cur.fetchall()]

            top_assets = top('asset_model')
            top_strategies = top('strategy_name')

            cur.execute(
                f"SELECT properties->>'method' AS method, COUNT(*) AS count "
                f"FROM ANALYTICS_EVENTS WHERE event_type = 'user_login' AND {window} "
                f"GROUP BY method ORDER BY count DESC", (days,))
            logins_by_method = [dict(r) for r in cur.fetchall()]

        return {
            "days": days,
            "total_events": totals["events"],
            "active_users": totals["active_users"],
            "per_day": per_day,
            "by_type": by_type,
            "top_assets": top_assets,
            "top_strategies": top_strategies,
            "logins_by_method": logins_by_method,
        }
