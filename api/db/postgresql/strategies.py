"""Custom strategies: CRUD, lineage, publishing, and evaluations.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import json
import logging
from datetime import datetime, timezone

from psycopg2 import extras

from utils.strategy_utils import calculate_strategy_hash

from ..logging_utils import log_db_call


class StrategiesMixin:
    """Custom strategies: CRUD, lineage, publishing, and evaluations. Mixed into PostgreSQLDatabase."""

    @log_db_call
    def save_custom_strategy(self, user_id, strategy_name, class_name, description, ai_description, code, 
                            parameters_json, validation_status='not_started', validation_error=None, 
                            last_validation_timestamp=None, strategy_id=None, parent_strategy_id=None, 
                            clone_source_commit_sha=None, git_branch_name=None, git_commit_sha=None, 
                            is_clone_unedited=None, evolution_request=None):
        conn = self.get_connection()
        try:
            # Ensure parameters_json is valid
            if parameters_json is None:
                parameters_json = '{}'
            elif isinstance(parameters_json, (dict, list)):
                parameters_json = json.dumps(parameters_json)
            
            # Ensure validation_error is a string/JSON if it's a dict or list
            if isinstance(validation_error, (dict, list)):
                validation_error = json.dumps(validation_error)
                
            cursor = self._get_cursor(conn)

            # Check for existence
            if strategy_id:
                cursor.execute("SELECT id FROM CUSTOM_STRATEGIES WHERE id = %s", (strategy_id,))
            else:
                cursor.execute("SELECT id FROM CUSTOM_STRATEGIES WHERE user_id = %s AND strategy_name = %s", (user_id, strategy_name))
            row = cursor.fetchone()

            if row:
                # === UPDATE EXISTING STRATEGY ===
                strategy_id = row[0]

                # Strategy identity: git_commit_sha is a content hash of the
                # code + parameters (the column name is a legacy of the old
                # GitHub-backed app; the DB is the authoritative store).
                if code and not git_commit_sha:
                     git_commit_sha = calculate_strategy_hash(code, json.loads(parameters_json))

                # If code is NULL (pure rename of a pointer), ensure we don't accidentally overwrite with NULL if we didn't mean to?
                # Actually, if code passed is NONE, we keep it NONE. If code passed is value, we update.
                
                if code:
                    # Full Update (Materialization or Code Edit)
                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES 
                    SET class_name = %s, description = %s, ai_description = %s, 
                        parameters_json = %s, validation_status = %s, validation_error = %s, 
                        last_validation_timestamp = %s, updated_at = CURRENT_TIMESTAMP,
                        git_branch_name = %s, git_repo_url = NULL,
                        last_synced_at = CURRENT_TIMESTAMP,
                        deleted_at = NULL, -- Undelete if it was recycled
                        parent_strategy_id = COALESCE(parent_strategy_id, %s),
                        clone_source_commit_sha = COALESCE(clone_source_commit_sha, %s),
                        is_clone_unedited = COALESCE(is_clone_unedited, %s),
                        -- If we are specifically saving as an unedited clone, clear existing code/SHA 
                        -- to ensure inheritance from parent works correctly (recycling fix)
                        code = CASE WHEN %s = TRUE THEN NULL ELSE %s END,
                        git_commit_sha = CASE WHEN %s = TRUE THEN NULL ELSE %s END
                    WHERE id = %s
                """, (class_name, description, ai_description, parameters_json,
                      validation_status, validation_error, last_validation_timestamp,
                      git_branch_name,
                      parent_strategy_id, clone_source_commit_sha, is_clone_unedited,
                      is_clone_unedited, code, is_clone_unedited, git_commit_sha, strategy_id))
                else:
                    # Metadata Only Update (e.g. Renaming a Pure Pointer)
                    # We do NOT update 'code' here.
                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES 
                    SET class_name = %s, description = %s, ai_description = %s,
                        parameters_json = %s, validation_status = %s, validation_error = %s, 
                        last_validation_timestamp = %s, updated_at = CURRENT_TIMESTAMP,
                        deleted_at = NULL, -- Undelete if it was recycled
                        parent_strategy_id = COALESCE(parent_strategy_id, %s),
                        clone_source_commit_sha = COALESCE(clone_source_commit_sha, %s),
                        is_clone_unedited = %s,
                        -- If we are specifically saving as an unedited clone, clear existing code/SHA 
                        -- to ensure inheritance from parent works correctly (recycling fix)
                        code = CASE WHEN %s = TRUE THEN NULL ELSE code END,
                        git_commit_sha = CASE WHEN %s = TRUE THEN NULL ELSE git_commit_sha END
                    WHERE id = %s
                """, (class_name, description, ai_description, parameters_json,
                      validation_status, validation_error, last_validation_timestamp,
                      parent_strategy_id, clone_source_commit_sha, is_clone_unedited,
                      is_clone_unedited, is_clone_unedited, strategy_id))

                if evolution_request:
                    # DB-native evolution history (V37) — this column is the
                    # authoritative timeline. Savepoint: recording the timeline
                    # must never fail the save itself (e.g. V37 not applied).
                    entry = {
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'request': evolution_request,
                        'user_id': user_id,
                        'commit_sha': git_commit_sha,
                    }
                    cursor.execute("SAVEPOINT evolution_append")
                    try:
                        cursor.execute("""
                            UPDATE CUSTOM_STRATEGIES
                            SET evolution_history = COALESCE(evolution_history, '[]'::jsonb) || %s::jsonb
                            WHERE id = %s
                        """, (json.dumps([entry]), strategy_id))
                        cursor.execute("RELEASE SAVEPOINT evolution_append")
                    except Exception:
                        logging.exception("Evolution-history append failed; saving without it")
                        cursor.execute("ROLLBACK TO SAVEPOINT evolution_append")

            else:
                # === INSERT NEW STRATEGY ===

                # Logic: If parent_strategy_id is set, and code is None -> Pure Clone (Pointer)
                # Logic: If code is provided -> Independent Strategy

                if parent_strategy_id and (code is None):
                     # === PURE REFERENCE CLONE ===
                     cursor.execute("""
                        INSERT INTO CUSTOM_STRATEGIES (
                            user_id, strategy_name, class_name, description, ai_description, code, 
                            parameters_json, validation_status, validation_error, last_validation_timestamp,
                            parent_strategy_id, clone_source_commit_sha, fork_count, cloned_at
                        ) VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (user_id, strategy_name, class_name, description, ai_description, 
                          parameters_json, validation_status, validation_error, last_validation_timestamp,
                          parent_strategy_id, clone_source_commit_sha))
                
                else:
                    # === STANDARD STRATEGY CREATION ===
                    cursor.execute("""
                        INSERT INTO CUSTOM_STRATEGIES (
                            user_id, strategy_name, class_name, description, ai_description, code, 
                            parameters_json, validation_status, validation_error, last_validation_timestamp,
                            parent_strategy_id, clone_source_commit_sha, fork_count, cloned_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (user_id, strategy_name, class_name, description, ai_description, code, 
                          parameters_json, validation_status, validation_error, last_validation_timestamp,
                          parent_strategy_id, clone_source_commit_sha))

                strategy_id = cursor.fetchone()[0]

                if parent_strategy_id:
                    # Inline on the SAME cursor/connection: calling
                    # self.increment_fork_count here would check out a second
                    # pooled connection while this one is mid-transaction
                    # (pool-exhaustion deadlock hazard).
                    cursor.execute(
                        "UPDATE CUSTOM_STRATEGIES SET fork_count = COALESCE(fork_count, 0) + 1 WHERE id = %s",
                        (parent_strategy_id,))

                # Content hash is the strategy's identity (git_commit_sha is
                # a legacy column name; the DB is the authoritative store).
                if code and not git_commit_sha:
                    git_commit_sha = calculate_strategy_hash(code, json.loads(parameters_json) if parameters_json else {})

                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES
                        SET git_commit_sha = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (git_commit_sha, strategy_id))

            conn.commit()

            return strategy_id
        except Exception as e:
            logging.error(f"Failed to save custom strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_user_custom_strategies(self, user_id):
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Fetch user's strategies OR public strategies,
                # joined with evaluation results.
                # UPDATED: Includes fallback for unedited clones to use parent's evaluation (Source SHA)
                cursor.execute("""
                    SELECT * FROM (
                        -- Use DISTINCT ON to ensure one row per strategy even if multiple evaluations exist
                        -- Prioritize actual user's strategies over public ones if ID matches
                        SELECT DISTINCT ON (c.id)
                            c.id, c.user_id, c.strategy_name,
                            COALESCE(c.class_name, p.class_name) as class_name,
                            COALESCE(c.description, p.description) as description,
                            COALESCE(c.code, p.code) as code,
                            COALESCE(c.parameters_json, p.parameters_json) as parameters_json,
                            COALESCE(c.ai_description, p.ai_description) as ai_description,
                            c.validation_status, c.validation_error,
                            c.created_at, c.updated_at, c.last_validation_timestamp,
                            c.git_branch_name, c.git_commit_sha, c.git_repo_url,
                            c.parent_strategy_id, c.clone_source_commit_sha, c.cloned_at,
                            c.is_public, c.is_published_to_leaderboard, c.fork_count,
                            c.is_clone_unedited,
                            (c.code IS NULL AND c.parent_strategy_id IS NOT NULL) as is_pure_clone,
                            e.excellence_score, e.sharpe_ratio, e.sortino_ratio,
                            (e.id IS NOT NULL) as has_evaluation
                        FROM CUSTOM_STRATEGIES c
                        LEFT JOIN CUSTOM_STRATEGIES p ON c.parent_strategy_id = p.id
                        LEFT JOIN STRATEGY_EVALUATIONS e ON (
                            e.git_commit_sha = COALESCE(c.git_commit_sha, c.clone_source_commit_sha)
                        )
                        WHERE (c.user_id = %s OR (c.is_public = TRUE AND c.user_id != 0))
                        AND c.deleted_at IS NULL
                        ORDER BY c.id, c.updated_at DESC, e.created_at DESC
                    ) sub
                    ORDER BY sub.updated_at DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get custom strategies: {e}", exc_info=True)
            return []

    @log_db_call
    def get_custom_strategy(self, strategy_id):
        """Fetch a specific custom strategy by ID."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Use LEFT JOIN for Pure Reference Cloning
                cursor.execute("""
                    SELECT
                        c.id, c.user_id, c.strategy_name,
                        COALESCE(c.class_name, p.class_name) as class_name,
                        COALESCE(c.description, p.description) as description,
                        COALESCE(c.code, p.code) as code,
                        COALESCE(c.parameters_json, p.parameters_json) as parameters_json,
                        COALESCE(c.ai_description, p.ai_description) as ai_description,
                        c.validation_status, c.validation_error,
                        c.created_at, c.updated_at, c.last_validation_timestamp,
                        c.git_branch_name, c.git_commit_sha, c.git_repo_url,
                        c.parent_strategy_id, c.clone_source_commit_sha, c.cloned_at,
                        c.is_public, c.is_published_to_leaderboard, c.fork_count,
                        c.deleted_at,
                        (c.code IS NULL AND c.parent_strategy_id IS NOT NULL) as is_pure_clone
                    FROM CUSTOM_STRATEGIES c
                    LEFT JOIN CUSTOM_STRATEGIES p ON c.parent_strategy_id = p.id
                    WHERE c.id = %s
                """, (strategy_id,))

                return cursor.fetchone()
        except Exception as e:
            logging.error(f"Failed to get custom strategy {strategy_id}: {e}", exc_info=True)
            return None

    @log_db_call
    def delete_custom_strategy(self, strategy_id, user_id):
        """DEPRECATED: Use soft_delete_custom_strategy instead."""
        return self.soft_delete_custom_strategy(strategy_id, user_id)

    @log_db_call
    def soft_delete_custom_strategy(self, strategy_id, user_id):
        """
        Soft deletes a custom strategy by setting deleted_at timestamp.
        Preserves data for lineage tracking and potential restore.
        """
        try:
            with self._connection_cursor() as cursor:
                # Verify ownership and that strategy isn't already deleted
                cursor.execute("""
                    SELECT id, user_id FROM CUSTOM_STRATEGIES
                    WHERE id = %s AND deleted_at IS NULL
                """, (strategy_id,))

                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Strategy {strategy_id} not found or already deleted")
                    return False

                _, owner_id = row
                if owner_id != user_id:
                    logging.warning(f"SECURITY: User {user_id} attempted to delete strategy {strategy_id} owned by {owner_id}")
                    return False

                # Soft delete: set timestamp
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET deleted_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (strategy_id,))

                updated = cursor.rowcount > 0
            logging.info(f"Soft deleted strategy {strategy_id} for user {user_id}")
            return updated
        except Exception as e:
            logging.error(f"Failed to soft delete strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def restore_custom_strategy(self, strategy_id, user_id):
        """
        Restores a soft-deleted strategy by clearing deleted_at timestamp.
        Note: Admin check should be done by caller before calling this method.
        """
        try:
            with self._connection_cursor() as cursor:
                # Verify strategy exists and is deleted
                cursor.execute("""
                    SELECT id, user_id FROM CUSTOM_STRATEGIES
                    WHERE id = %s AND deleted_at IS NOT NULL
                """, (strategy_id,))

                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Strategy {strategy_id} not found or not deleted")
                    return False

                # Restore: clear timestamp
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET deleted_at = NULL
                    WHERE id = %s
                """, (strategy_id,))

                updated = cursor.rowcount > 0
            logging.info(f"Restored strategy {strategy_id}")
            return updated
        except Exception as e:
            logging.error(f"Failed to restore strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def update_custom_strategy(self, strategy_id, user_id, strategy_name, description, ai_description, parameters_json, git_branch_name=None, git_commit_sha=None):
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET strategy_name = %s,
                        description = %s,
                        ai_description = %s,
                        parameters_json = %s,
                        git_branch_name = COALESCE(%s, git_branch_name),
                        git_commit_sha = COALESCE(%s, git_commit_sha),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (strategy_name, description, ai_description, parameters_json, git_branch_name, git_commit_sha, strategy_id, user_id))
                updated = cursor.rowcount > 0
            return updated
        except Exception as e:
            logging.error(f"Failed to update custom strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def get_strategy_evolution_history(self, strategy_id):
        """
        Fetch evolution history from the DB (V37 evolution_history column).

        Args:
            strategy_id: Strategy ID

        Returns:
            List of evolution entries with timestamp, request, commit_sha, user_id
        """
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute("""
                    SELECT evolution_history
                    FROM CUSTOM_STRATEGIES
                    WHERE id = %s
                """, (strategy_id,))

                row = cursor.fetchone()
                if not row:
                    return []

                db_history = row[0]

                if isinstance(db_history, str):
                    db_history = json.loads(db_history)
                return db_history or []
        except Exception as e:
            logging.error(f"Failed to get evolution history: {e}", exc_info=True)
            return []

    @log_db_call
    def set_strategy_published_status(self, strategy_id, user_id, is_published):
        """Toggle whether a custom strategy is published to the leaderboard."""
        try:
            with self._connection_cursor() as cursor:
                # Verify ownership before allowing change
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET is_published_to_leaderboard = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (is_published, strategy_id, user_id))
                success = cursor.rowcount > 0

            # Clear leaderboard cache when publish status changes
            if success:
                try:
                    from db.cache import get_leaderboard_with_profile_cached
                    get_leaderboard_with_profile_cached.clear()
                    logging.info(f"Cleared leaderboard cache after {'publishing' if is_published else 'unpublishing'} strategy {strategy_id}")
                except Exception as cache_error:
                    logging.warning(f"Failed to clear leaderboard cache: {cache_error}")

            return success
        except Exception as e:
            logging.error(f"Failed to set publish status: {e}", exc_info=True)
            return False

    @log_db_call
    def save_strategy_evaluation(self, evaluation_data):
        """Save strategy evaluation using INSERT...ON CONFLICT."""
        try:
            # Construct parameters dict ensuring all keys required by query exist
            params = {
                'strategy_name': evaluation_data['strategy_name'],
                'git_commit_sha': evaluation_data.get('git_commit_sha'), # KEY for the new architecture
                'user_id': evaluation_data.get('user_id'),
                'is_custom': evaluation_data.get('is_custom', False),
                'custom_strategy_id': evaluation_data.get('custom_strategy_id'),
                'strategy_category': evaluation_data.get('strategy_category', 'Unknown'),
                'excellence_score': evaluation_data.get('excellence_score'),
                'risk_score': evaluation_data.get('risk_score', 0.0),
                'pv_score': evaluation_data.get('pv_score', 0.0),
                'capital_efficiency_score': evaluation_data.get('capital_efficiency_score', 0.0),
                'purchasing_power_score': evaluation_data.get('purchasing_power_score', 0.0),
                'robustness_score': evaluation_data.get('robustness_score', 0.0),
                'consumption_ratio_score': evaluation_data.get('consumption_ratio_score', 0.0),
                'usability_score': evaluation_data.get('usability_score', 0.0),
                'stability_score': evaluation_data.get('stability_score', 0.0),
                'legacy_score': evaluation_data.get('legacy_score', 0.0),
                'sharpe_ratio_score': evaluation_data.get('sharpe_ratio_score'),
                'calmar_ratio_score': evaluation_data.get('calmar_ratio_score'),
                'downside_stability_score': evaluation_data.get('downside_stability_score'),
                'ulcer_index_score': evaluation_data.get('ulcer_index_score'),
                'scenario_results_json': evaluation_data['scenario_results_json']
            }
            # Sanitize numeric types to python native floats for psycopg2 compatibility
            # This handles numpy scalars (np.float64) which psycopg2 confuses for schema objects
            score_keys = [
                'excellence_score', 'risk_score', 'pv_score',
                'capital_efficiency_score', 'purchasing_power_score', 'robustness_score',
                'consumption_ratio_score', 'usability_score', 'stability_score', 'legacy_score',
                'sharpe_ratio_score', 'calmar_ratio_score', 'downside_stability_score', 'ulcer_index_score'
            ]
            for key in score_keys:
                val = params.get(key)
                if val is not None:
                    try:
                        params[key] = float(val)
                    except (ValueError, TypeError):
                        pass # Keep original if casting fails
            
            # Determine which query to use based on presence of git_commit_sha
            if params.get('git_commit_sha'):
                query = self.queries.SAVE_STRATEGY_EVALUATION_BY_SHA
                id_lookup_query = """
                    SELECT id FROM STRATEGY_EVALUATIONS 
                    WHERE git_commit_sha = %s 
                    LIMIT 1
                """
                id_lookup_param = (params['git_commit_sha'],)
            else:
                query = self.queries.SAVE_STRATEGY_EVALUATION_BY_NAME
                id_lookup_query = """
                    SELECT id FROM STRATEGY_EVALUATIONS 
                    WHERE strategy_name = %s AND git_commit_sha IS NULL
                    LIMIT 1
                """
                id_lookup_param = (params['strategy_name'],)

            with self._connection_cursor() as cursor:
                cursor.execute(query, params)

                # --- Get the evaluation_id of the just-inserted/updated row ---
                cursor.execute(id_lookup_query, id_lookup_param)
                row = cursor.fetchone()
                evaluation_id = row[0] if row else None

                # --- NEW: Insert profile scores if evaluation succeeded ---
                if evaluation_id and 'profile_scores' in evaluation_data:
                    for profile_key, score in evaluation_data['profile_scores'].items():
                        try:
                            cursor.execute("""
                                INSERT INTO STRATEGY_PROFILE_SCORES
                                (evaluation_id, profile_key, excellence_score)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (evaluation_id, profile_key)
                                DO UPDATE SET
                                    excellence_score = EXCLUDED.excellence_score,
                                    calculated_at = CURRENT_TIMESTAMP
                            """, (evaluation_id, profile_key, float(score)))
                        except Exception as e:
                            logging.error(f"Failed to insert profile score for {profile_key}: {e}")
                            # Continue with other profiles even if one fails

                    logging.info(f"Saved {len(evaluation_data['profile_scores'])} profile scores for evaluation {evaluation_id}")

            logging.info(f"Successfully saved evaluation for {evaluation_data['strategy_name']}")
            return True  # Return success indicator
        except Exception as e:
            logging.error(f"Failed to save evaluation: {e}", exc_info=True)
            return False  # Return failure indicator

    @log_db_call
    def get_strategy_evaluation(self, git_commit_sha, lookup_fallback_sha=None):
        """
        Get evaluation for specific strategy version by SHA.
        
        Args:
            git_commit_sha: The SHA of the strategy to look up
            lookup_fallback_sha: Optional fallback SHA (e.g. parent SHA for unedited clones)
            
        Returns:
            Dict with evaluation data or None
        """
        if not git_commit_sha and not lookup_fallback_sha:
            return None

        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Primary lookup
                result = None
                if git_commit_sha:
                    cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA, (git_commit_sha,))
                    result = cursor.fetchone()

                # Fallback lookup (for clones)
                if not result and lookup_fallback_sha:
                    primary_display = git_commit_sha[:7] if git_commit_sha else "None"
                    fallback_display = lookup_fallback_sha[:7] if lookup_fallback_sha else "None"
                    logging.info(f"Primary SHA {primary_display} not found, checking fallback {fallback_display}")
                    cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA, (lookup_fallback_sha,))
                    result = cursor.fetchone()

                return result
        except Exception as e:
            logging.error(f"Failed to get evaluation: {e}", exc_info=True)
            return None

    @log_db_call
    def get_all_custom_strategies_for_admin(self):
        """Fetch all custom strategies for admin evaluation."""
        logging.info("Admin: Fetching all custom strategies for evaluation")
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT
                        cs.id,
                        cs.user_id,
                        cs.strategy_name,
                        cs.class_name,
                        cs.code,
                        cs.description,
                        cs.parameters_json
                    FROM CUSTOM_STRATEGIES cs
                    ORDER BY cs.user_id, cs.strategy_name
                """)
                records = [dict(row) for row in cursor.fetchall()]
            # Use abstraction layer for JSON deserialization
            for row in records:
                if 'parameters_json' in row:
                    row['parameters_json'] = self.deserialize_json_column(row['parameters_json'])
            return records
        except Exception as e:
            logging.error(f"Failed admin fetch: {e}", exc_info=True)
            return []
