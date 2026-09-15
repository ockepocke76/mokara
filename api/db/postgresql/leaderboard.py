"""Leaderboard queries and community statistics.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import logging

from psycopg2 import extras

from ..logging_utils import log_db_call


class LeaderboardMixin:
    """Leaderboard queries and community statistics. Mixed into PostgreSQLDatabase."""

    @log_db_call
    def get_leaderboard(self, category=None, limit=50):
        """Fetch leaderboard, optionally filtered by category."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                if category and category != 'All':
                    cursor.execute("""
                        SELECT
                            e.*,
                            cs.ai_description,
                            cs.description as custom_description,
                            cs.is_published_to_leaderboard,
                            COALESCE(u.display_name, u.email) as user_name,
                            u.email as user_email
                        FROM STRATEGY_EVALUATIONS e
                        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                        LEFT JOIN USERS u ON cs.user_id = u.id
                        WHERE e.strategy_category = %s
                          AND (e.is_custom = FALSE OR cs.is_published_to_leaderboard = TRUE)
                        ORDER BY e.excellence_score DESC
                        LIMIT %s
                    """, (category, limit))
                else:
                    cursor.execute("""
                        SELECT
                            e.*,
                            cs.ai_description,
                            cs.description as custom_description,
                            cs.is_published_to_leaderboard,
                            COALESCE(u.display_name, u.email) as user_name,
                            u.email as user_email
                        FROM STRATEGY_EVALUATIONS e
                        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                        LEFT JOIN USERS u ON cs.user_id = u.id
                        WHERE (e.is_custom = FALSE OR cs.is_published_to_leaderboard = TRUE)
                        ORDER BY e.excellence_score DESC
                        LIMIT %s
                    """, (limit,))

                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to fetch leaderboard: {e}", exc_info=True)
            return []

    @log_db_call
    def get_leaderboard_with_profile(self, profile_key='balanced', category=None, limit=50):
        """
        Fetch leaderboard using pre-calculated profile scores from STRATEGY_PROFILE_SCORES.
        
        Args:
            profile_key: Weight profile to use ('balanced', 'conservative', etc.)
            category: Optional category filter
            limit: Max number of results
        
        Returns:
            List of strategy evaluations with profile_excellence_score
        """
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                if category and category != 'All':
                    cursor.execute("""
                        SELECT
                            e.*,
                            sps.excellence_score as profile_excellence_score,
                            cs.ai_description,
                            cs.description as custom_description,
                            cs.is_published_to_leaderboard,
                            COALESCE(u.display_name, u.email) as user_name,
                            u.email as user_email,
                            (SELECT COUNT(*) FROM CUSTOM_STRATEGIES WHERE parent_strategy_id = cs.id AND is_clone_unedited = TRUE) as usage_clone_count,
                            (SELECT COUNT(*) FROM CUSTOM_STRATEGIES WHERE parent_strategy_id = cs.id AND is_clone_unedited = FALSE) as usage_fork_count
                        FROM STRATEGY_EVALUATIONS e
                        LEFT JOIN STRATEGY_PROFILE_SCORES sps ON e.id = sps.evaluation_id AND sps.profile_key = %s
                        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                        LEFT JOIN USERS u ON cs.user_id = u.id
                        WHERE e.strategy_category = %s
                          AND (e.is_custom = FALSE OR cs.is_published_to_leaderboard = TRUE)
                        ORDER BY COALESCE(sps.excellence_score, e.excellence_score) DESC
                        LIMIT %s
                    """, (profile_key, category, limit))
                else:
                    cursor.execute("""
                        SELECT
                            e.*,
                            sps.excellence_score as profile_excellence_score,
                            cs.ai_description,
                            cs.description as custom_description,
                            cs.is_published_to_leaderboard,
                            COALESCE(u.display_name, u.email) as user_name,
                            u.email as user_email
                        FROM STRATEGY_EVALUATIONS e
                        LEFT JOIN STRATEGY_PROFILE_SCORES sps ON e.id = sps.evaluation_id AND sps.profile_key = %s
                        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                        LEFT JOIN USERS u ON cs.user_id = u.id
                        WHERE (e.is_custom = FALSE OR cs.is_published_to_leaderboard = TRUE)
                        ORDER BY COALESCE(sps.excellence_score, e.excellence_score) DESC
                        LIMIT %s
                    """, (profile_key, limit))

                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to fetch leaderboard with profile: {e}", exc_info=True)
            return []

    @log_db_call
    def get_community_stats(self):
        """
        Get aggregated community statistics from persistent GLOBAL_STATS table.
        Falls back to live counts if global stats are missing/zero (backward compatibility).
        """
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Fetch all global stats
                cursor.execute("SELECT metric_key, metric_value FROM GLOBAL_STATS")
                rows = cursor.fetchall()
                stats_map = {row['metric_key']: row['metric_value'] for row in rows}

                # 1. Total Simulations Run
                total_sims = stats_map.get('total_simulations_run', 0)
                if total_sims == 0: # Fallback
                    cursor.execute("SELECT count(*) as count FROM user_simulation_history")
                    row = cursor.fetchone()
                    total_sims = row['count'] if row else 0

                # 2. Total Strategies Created
                total_strategies = stats_map.get('total_strategies_created', 0)
                if total_strategies == 0: # Fallback
                    cursor.execute("SELECT count(*) as count FROM custom_strategies")
                    row = cursor.fetchone()
                    total_strategies = row['count'] if row else 0

                # 3. Total Years Simulated (New!)
                total_years = stats_map.get('total_years_simulated', 0)

                # 4. Most Popular (by completed runs) - Still calculated live for now, or could cached?
                # Live calculation is fine for "Top 5 List", but "Global Stats" above are persistent.
                # Use grouped aggregation handling both standard (strategy key) and custom (custom_strategy_name)
                cursor.execute("""
                    SELECT
                        COALESCE(parameters::jsonb->>'custom_strategy_name', parameters::jsonb->>'strategy') as strategy_identifier,
                        COUNT(*) as count
                    FROM CACHED_SIMULATIONS
                    WHERE parameters::jsonb->>'strategy' IS NOT NULL
                    GROUP BY 1
                    ORDER BY count DESC
                    LIMIT 5
                """)
                top_rows = cursor.fetchall()

            # Map technical keys to friendly names
            friendly_names = {
                'trinity': 'Trinity Strategy',
                'buy_borrow_die': 'Buy Borrow Die',
                'get_rich_stay_rich': 'Get Rich Stay Rich',
                'custom': 'Custom Strategy' # Fallback if name missing
            }

            top_strategies = []
            for row in top_rows:
                raw_name = row['strategy_identifier']
                display_name = friendly_names.get(raw_name, raw_name)
                if display_name == raw_name and '_' in display_name:
                     display_name = display_name.replace('_', ' ').title()
                top_strategies.append({'strategy_name': display_name, 'count': row['count']})

            return {
                'total_simulations': total_sims,
                'total_strategies': total_strategies,
                'total_years_simulated': total_years,
                'top_strategies': top_strategies
            }

        except Exception as e:
            logging.error(f"Failed to get community stats: {e}", exc_info=True)
            return {'total_simulations': 0, 'total_strategies': 0, 'top_strategies': [], 'total_years_simulated': 0}
