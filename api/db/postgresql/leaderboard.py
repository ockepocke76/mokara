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
                            CASE WHEN u.id IS NOT NULL
                                 THEN COALESCE(u.display_name, 'anonymous')
                            END as user_name
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
                            CASE WHEN u.id IS NOT NULL
                                 THEN COALESCE(u.display_name, 'anonymous')
                            END as user_name
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
                # One query for both the filtered and the all-categories views
                # (the two branches drifted apart once already), shaped
                # page-first: the lineage counts below run per RETURNED row,
                # not per candidate row — interactive paths fetch limit=500.
                # bs resolves a built-in evaluation row to its strategies row
                # so built-ins get lineage counts too. All counts ignore
                # soft-deleted rows; the descendant walk passes THROUGH them
                # so a trashed intermediate never hides live grandchildren.
                cursor.execute("""
                    WITH page AS (
                        SELECT
                            e.*,
                            sps.excellence_score as profile_excellence_score,
                            cs.ai_description,
                            cs.description as custom_description,
                            cs.is_published_to_leaderboard,
                            CASE WHEN u.id IS NOT NULL
                                 THEN COALESCE(u.display_name, 'anonymous')
                            END as user_name,
                            COALESCE(cs.id, bs.id) as lineage_id
                        FROM STRATEGY_EVALUATIONS e
                        LEFT JOIN STRATEGY_PROFILE_SCORES sps ON e.id = sps.evaluation_id AND sps.profile_key = %(profile_key)s
                        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                        LEFT JOIN CUSTOM_STRATEGIES bs ON e.is_custom = FALSE AND bs.user_id = 0 AND bs.strategy_name = e.strategy_name
                        LEFT JOIN USERS u ON cs.user_id = u.id
                        WHERE (e.is_custom = FALSE OR cs.is_published_to_leaderboard = TRUE)
                          AND (%(category)s::text IS NULL OR e.strategy_category = %(category)s)
                        ORDER BY COALESCE(sps.excellence_score, e.excellence_score) DESC
                        LIMIT %(limit)s
                    )
                    SELECT page.*,
                           COALESCE(counts.usage_clone_count, 0) as usage_clone_count,
                           COALESCE(counts.usage_fork_count, 0) as usage_fork_count,
                           COALESCE(counts.descendant_count, 0) as descendant_count
                    FROM page
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) FILTER (WHERE d.depth = 1 AND d.unedited AND d.live) as usage_clone_count,
                            COUNT(*) FILTER (WHERE d.depth = 1 AND NOT d.unedited AND d.live) as usage_fork_count,
                            COUNT(*) FILTER (WHERE d.live) as descendant_count
                        FROM (
                            WITH RECURSIVE d AS (
                                SELECT dc.id,
                                       COALESCE(dc.is_clone_unedited, FALSE) as unedited,
                                       (dc.deleted_at IS NULL) as live, 1 as depth
                                FROM CUSTOM_STRATEGIES dc
                                WHERE dc.parent_strategy_id = page.lineage_id
                                UNION ALL
                                SELECT c2.id,
                                       COALESCE(c2.is_clone_unedited, FALSE),
                                       (c2.deleted_at IS NULL), d.depth + 1
                                FROM CUSTOM_STRATEGIES c2
                                JOIN d ON c2.parent_strategy_id = d.id
                                WHERE c2.id != d.id AND d.depth < 50
                            ) SELECT * FROM d
                        ) d
                    ) counts ON TRUE
                    ORDER BY COALESCE(page.profile_excellence_score, page.excellence_score) DESC
                """, {'profile_key': profile_key,
                      'category': (category if category and category != 'All'
                                   else None),
                      'limit': limit})

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
