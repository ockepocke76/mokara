"""Simulation results, cache entries, user history, and PDF storage.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import io
import json
import logging
import pickle

import psycopg2
from psycopg2 import extras

from ..utils import _sanitize_for_json
from ..logging_utils import log_db_call
from utils.helpers import compute_log_scale_histogram


def _save_dataframe_to_db(cursor, results_id, data_key, df):
    """Helper to serialize DataFrame to PostgreSQL (BYTEA column)."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, compression='gzip')
    data_blob = buffer.getvalue()
    
    cursor.execute(
        """INSERT INTO SIMULATION_RESULTS_DATA (results_id, data_key, data_blob)
           VALUES (%s, %s, %s)
           ON CONFLICT (results_id, data_key) DO UPDATE SET data_blob = EXCLUDED.data_blob""",
        (results_id, data_key, psycopg2.Binary(data_blob))
    )


def _save_dict_to_db(cursor, results_id, data_key, data_dict):
    """Helper to serialize dict to PostgreSQL."""
    data_blob = pickle.dumps(data_dict)
    cursor.execute(
        """INSERT INTO SIMULATION_RESULTS_DATA (results_id, data_key, data_blob)
           VALUES (%s, %s, %s)
           ON CONFLICT (results_id, data_key) DO UPDATE SET data_blob = EXCLUDED.data_blob""",
        (results_id, data_key, psycopg2.Binary(data_blob))
    )


class SimulationsMixin:
    """Simulation results, cache entries, user history, and PDF storage. Mixed into PostgreSQLDatabase."""

    @log_db_call
    def save_simulation_results(self, simulation_hash, params, ui_params, stats, 
                                results_dataframe, average_results_df, median_yearly_results_df,
                                gemini_content, user_id, simulation_name, is_replacement_run=False):
        """Save simulation results - PostgreSQL version."""
        try:
            with self._connection_cursor() as cursor:
                # Create results entry with RETURNING
                cursor.execute(
                    """INSERT INTO SIMULATION_RESULTS (stats, gemini_content, pdf_status)
                       VALUES (%s, %s, NULL)
                       RETURNING id""",
                    (json.dumps(_sanitize_for_json(stats)), gemini_content)
                )
                results_id = cursor.fetchone()[0]

                # Save DataFrames
                _save_dataframe_to_db(cursor, results_id, 'results_dataframe', results_dataframe)
                _save_dataframe_to_db(cursor, results_id, 'average_results_df', average_results_df)
                _save_dataframe_to_db(cursor, results_id, 'median_yearly_results_df', median_yearly_results_df)

                # Update or insert cached simulation
                cursor.execute(
                    """INSERT INTO CACHED_SIMULATIONS
                       (simulation_hash, parameters, ui_parameters, status, results_id)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (simulation_hash) DO UPDATE SET
                       results_id = EXCLUDED.results_id,
                       status = EXCLUDED.status,
                       updated_at = CURRENT_TIMESTAMP""",
                    (simulation_hash, json.dumps(_sanitize_for_json(params)),
                     json.dumps(_sanitize_for_json(ui_params)), 'COMPLETED', results_id)
                )

                # Add to user history
                cursor.execute(
                    """INSERT INTO USER_SIMULATION_HISTORY
                       (user_id, simulation_hash, simulation_name, status)
                       VALUES (%s, %s, %s, %s)
                       RETURNING id""",
                    (user_id, simulation_hash, simulation_name, 'completed')
                )
                history_id = cursor.fetchone()[0]

            logging.info(f"Saved simulation {simulation_hash[:10]}, history_id={history_id}")
            return history_id

        except Exception as e:
            logging.error(f"Failed to save simulation: {e}", exc_info=True)
            return None

    @log_db_call
    def get_user_simulations(self, user_email=None):
        """Fetch user simulations. If user_email is None, fetch demo simulations."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                if user_email is None:
                    # For anonymous users, fetch demo/public simulations
                    cursor.execute(self.queries.GET_USER_SIMULATIONS_WITH_PARAMS, {'email': None})
                else:
                    # For authenticated users, fetch their simulations
                    cursor.execute(self.queries.GET_USER_SIMULATIONS_WITH_PARAMS, {'email': user_email})

                rows = cursor.fetchall()
            logging.info(f"[DEDUP] Fetched {len(rows)} rows from database")
            
            # Deduplicate by simulation_hash (keep first occurrence)
            # This prevents the same simulation appearing multiple times when:
            # - User owns a public simulation (matches both OR conditions)
            # - Same simulation has multiple history entries
            seen_hashes = set()
            deduped_rows = []
            duplicates_removed = 0
            for row in rows:
                sim_hash = row.get('simulation_hash')
                if sim_hash and sim_hash not in seen_hashes:
                    seen_hashes.add(sim_hash)
                    deduped_rows.append(row)
                elif sim_hash and sim_hash in seen_hashes:
                    duplicates_removed += 1
                    logging.debug(f"[DEDUP] Skipping duplicate: hash={sim_hash[:10]}, history_id={row.get('id')}")
                elif not sim_hash:  # No hash - keep it anyway (shouldn't happen)
                    deduped_rows.append(row)
            
            logging.info(f"[DEDUP] Removed {duplicates_removed} duplicates, returning {len(deduped_rows)} unique simulations")
            
            # Post-process: ensure parameters/all_params is a dict, not str
            for row in deduped_rows:
                # Use abstraction layer for JSON deserialization
                if 'all_params' in row:
                    row['all_params'] = self.deserialize_json_column(row['all_params'])
                    if row['all_params'] is None or not isinstance(row['all_params'], dict):
                        row['all_params'] = {}
                    # Also set simulation_parameters for compatibility
                    row['simulation_parameters'] = row['all_params']
            return deduped_rows
        except Exception as e:
            logging.error(f"Failed to get simulations: {e}", exc_info=True)
            return []

    @log_db_call
    def check_simulation_cache(self, simulation_hash):
        """
        Check if simulation is cached.
        Handles stale PENDING/RUNNING states automagically.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """SELECT status, results_id, component_hashes, parameters, updated_at, created_at,
                          EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - COALESCE(updated_at, created_at))) AS age_seconds
                   FROM CACHED_SIMULATIONS
                   WHERE simulation_hash = %s""",
                (simulation_hash,)
            )
            row = cursor.fetchone()

            if row:
                status, results_id, hashes, parameters, updated_at, created_at, age_seconds = row
                
                # Deserialize component hashes from JSONB
                hashes = self.deserialize_json_column(hashes)
                
                # Fallback: If component_hashes column is NULL (legacy), try to extract from parameters
                if not hashes and parameters:
                    try:
                        params_dict = self.deserialize_json_column(parameters)
                        if isinstance(params_dict, dict):
                            hashes = params_dict.get('component_hashes')
                    except Exception as e:
                        logging.warning(f"Failed to extract fallback hashes from parameters: {e}")
                
                # Check for stale pending state (older than 5 minutes).
                # Age is computed in SQL against the DB clock — comparing a
                # Python-side naive now() with the column broke as soon as
                # server TZ and column semantics diverged (e.g. UTC on
                # Cloud Run).
                if status in ['PENDING', 'RUNNING']:
                    logging.info(f"STALE CHECK: Hash={simulation_hash[:8]} Status={status} Age={age_seconds}s")
                    if age_seconds is not None and age_seconds > 300:  # 5 minutes
                        logging.warning(f"Found stale simulation {status} for {simulation_hash} (age: {age_seconds:.0f}s). invalidating.")
                        # Treat as not found so it triggers a re-run
                        try:
                            cursor.execute("UPDATE CACHED_SIMULATIONS SET status = 'FAILED' WHERE simulation_hash = %s", (simulation_hash,))
                            conn.commit()
                        except Exception:
                            conn.rollback()
                        return None, None, None
                
                return status, results_id, hashes
                
            return None, None, None
        except Exception as e:
            logging.error(f"Cache check failed: {e}", exc_info=True)
            return None, None, None
        finally:
            self.release_connection(conn)

    @log_db_call
    def add_to_user_history(self, user_id, simulation_hash, simulation_name):
        """Add simulation to user history."""
        logging.info(f"DEBUG: add_to_user_history called for User={user_id} Hash={simulation_hash[:8]}")
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(
                    """INSERT INTO USER_SIMULATION_HISTORY
                       (user_id, simulation_hash, simulation_name)
                       VALUES (%s, %s, %s)
                       RETURNING id""",
                    (user_id, simulation_hash, simulation_name)
                )
                history_id = cursor.fetchone()[0]
            return history_id
        except Exception as e:
            logging.error(f"Failed to add history: {e}", exc_info=True)
            return None

    @log_db_call
    def create_cached_simulation_entry(self, simulation_hash, params):
        """Create pending cache entry."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(
                    """INSERT INTO CACHED_SIMULATIONS
                       (simulation_hash, parameters, status)
                       VALUES (%s, %s, 'PENDING')
                       ON CONFLICT (simulation_hash) DO NOTHING""",
                    (simulation_hash, json.dumps(_sanitize_for_json(params)))
                )
        except Exception as e:
            logging.error(f"Failed to create cache entry: {e}", exc_info=True)

    @log_db_call
    def update_cached_simulation_status(self, simulation_hash, status):
        """Update simulation status."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(
                    """UPDATE CACHED_SIMULATIONS
                       SET status = %s, updated_at = CURRENT_TIMESTAMP
                       WHERE simulation_hash = %s""",
                    (status, simulation_hash)
                )
        except Exception as e:
            logging.error(f"Failed to update status: {e}", exc_info=True)

    @log_db_call
    def get_user_simulations_with_params(self, user_email):
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute(self.queries.GET_USER_SIMULATIONS_WITH_PARAMS, {'email': user_email})
                rows = cursor.fetchall()
            for row in rows:
                # Use abstraction layer for JSON deserialization
                if 'all_params' in row:
                    row['all_params'] = self.deserialize_json_column(row['all_params'])
                    if row['all_params'] is None or not isinstance(row['all_params'], dict):
                        row['all_params'] = {}
                else:
                    row['all_params'] = {}
            return rows
        except Exception as e:
            return []

    @log_db_call
    def mark_simulation_as_removed(self, simulation_id, user_id=None):
        """
        Marks a simulation history entry as removed.
        If it's a demo simulation and a user_id is provided, it hides it for that user instead of deleting it.
        SECURE: Requires valid user_id and verifies ownership for non-demo simulations.
        """
        try:
            with self._connection_cursor() as cursor:
                # Check if it is a public simulation by joining with CACHED_SIMULATIONS
                cursor.execute("""
                    SELECT cs.is_public, h.user_id
                    FROM USER_SIMULATION_HISTORY h
                    JOIN CACHED_SIMULATIONS cs ON h.simulation_hash = cs.simulation_hash
                    WHERE h.id = %s
                """, (simulation_id,))
                row = cursor.fetchone()

                if not row:
                    logging.warning(f"Simulation {simulation_id} not found")
                    return False

                is_public = row[0]
                owner_user_id = row[1]

                if is_public:
                    # Soft delete for user (hide it via USER_HIDDEN_ITEMS)
                    # If user_id is None, it means an admin or system is trying to remove a public simulation,
                    # in which case we use the owner_user_id to hide it from the original creator's view.
                    # This logic might need refinement based on exact requirements for public simulation removal.
                    return self.hide_shared_item(user_id or owner_user_id, 'simulation', simulation_id)
                else:
                    # For private simulations, we perform a soft delete (set is_removed = TRUE)
                    # This assumes that the user_id check for ownership is handled upstream or
                    # that only the owner can trigger this for private simulations.
                    # If user_id is provided, we can add an extra check:
                    if user_id and owner_user_id != user_id:
                        logging.warning(f"SECURITY: User {user_id} attempted to remove private simulation {simulation_id} owned by {owner_user_id}")
                        return False

                    cursor.execute("UPDATE USER_SIMULATION_HISTORY SET is_removed = TRUE WHERE id = %s", (simulation_id,))
                    return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to remove simulation: {e}", exc_info=True)
            return False

    @log_db_call
    def permanently_delete_simulation(self, simulation_id):
        try:
            with self._connection_cursor() as cursor:
                # Defensive check: Ensure we're not deleting a public simulation's history entry
                cursor.execute("""
                    SELECT cs.is_public
                    FROM USER_SIMULATION_HISTORY h
                    JOIN CACHED_SIMULATIONS cs ON h.simulation_hash = cs.simulation_hash
                    WHERE h.id = %s
                """, (simulation_id,))
                row = cursor.fetchone()

                if row and row[0]:  # is_public = TRUE
                    raise ValueError(f"Cannot delete public simulation history entry (id: {simulation_id}). Public simulations should not be deleted.")

                # Deleting from history. Cache remains for others/deduplication.
                cursor.execute("DELETE FROM USER_SIMULATION_HISTORY WHERE id = %s", (simulation_id,))
        except Exception as e:
            logging.error(f"Failed to delete: {e}", exc_info=True)
            raise

    @log_db_call
    def get_all_simulations(self):
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute(self.queries.GET_ALL_SIMULATIONS)
                records = [dict(row) for row in cursor.fetchall()]
            # Use abstraction layer for JSON deserialization
            for row in records:
                if 'all_params' in row:
                    row['all_params'] = self.deserialize_json_column(row['all_params'])
                    if row['all_params'] is None or not isinstance(row['all_params'], dict):
                        row['all_params'] = {}
                else:
                    row['all_params'] = {}
            return records
        except Exception as e:
            return []

    @log_db_call
    def get_simulation_details(self, simulation_hash):
        try:
            with self._connection_cursor(commit=False) as cursor:
                # Use inline query to access CACHED_SIMULATIONS structure correctly
                # Returns: parameters (jsonb), stats (jsonb), component_hashes (text), results_id (int)
                cursor.execute("""
                    SELECT
                        c.parameters,
                        r.stats,
                        r.gemini_content,
                        c.component_hashes,
                        c.results_id
                    FROM CACHED_SIMULATIONS c
                    JOIN SIMULATION_RESULTS r ON c.results_id = r.id
                    WHERE c.simulation_hash = %s
                """, (simulation_hash,))

                row = cursor.fetchone()
            if row:
                params, stats, gemini_content, component_hashes, results_id = row[0], row[1], row[2], row[3], row[4]
                
                # Use the abstraction layer for JSON deserialization
                params = self.deserialize_json_column(params)
                stats = self.deserialize_json_column(stats)
                gemini_content = self.deserialize_json_column(gemini_content)
                component_hashes = self.deserialize_json_column(component_hashes)
                
                # CRITICAL FIX: Merge gemini_content into stats for backwards compatibility
                #This ensures regeneration_db.py can find it
                if gemini_content and isinstance(gemini_content, dict):
                    stats.update(gemini_content)
                
                # CRITICAL FIX: Merge component_hashes into params for staleness detection
                if component_hashes:
                    params['component_hashes'] = component_hashes
                        
                return params, stats, results_id
            return None, None, None
        except Exception as e:
            logging.error(f"Failed to get simulation details: {e}", exc_info=True)
            return None, None, None

    @log_db_call
    def get_simulation_access(self, simulation_hash, user_id=None):
        """Access facts for one cached simulation, for router-level checks.

        Returns None when the hash is unknown, else a dict:
          {'is_public': bool, 'history_id': int or None}
        history_id is the given user's own live history entry for this hash
        (None when user_id is None or they have no entry). Simulation hashes
        are deterministic functions of the parameters — not unguessable —
        so visibility must be enforced by the caller, not by hash secrecy.
        """
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT is_public FROM CACHED_SIMULATIONS WHERE simulation_hash = %s",
                    (simulation_hash,))
                row = cursor.fetchone()
                if not row:
                    return None
                access = {'is_public': bool(row[0]), 'history_id': None}
                if user_id is not None:
                    cursor.execute("""
                        SELECT id FROM USER_SIMULATION_HISTORY
                        WHERE simulation_hash = %s AND user_id = %s AND is_removed = FALSE
                        ORDER BY id LIMIT 1
                    """, (simulation_hash, user_id))
                    h = cursor.fetchone()
                    if h:
                        access['history_id'] = h[0]
                return access
        except Exception as e:
            logging.error(f"Failed to get simulation access: {e}", exc_info=True)
            return None

    @log_db_call
    def update_history_status(self, history_id, status):
        """Update history entry status."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("UPDATE USER_SIMULATION_HISTORY SET status = %s WHERE id = %s", (status, history_id))
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)

    @log_db_call
    def update_cached_simulation_results(self, simulation_hash, params, ui_params, stats, 
                                        results_dataframe, average_results_df, 
                                        median_yearly_results_df, gemini_content, status='COMPLETED', evaluation_data=None):
        """Update cached simulation with results."""
        try:
            with self._connection_cursor() as cursor:
                # Create results entry (pdf_status NULL = no auto-generation, user must click button)
                cursor.execute("INSERT INTO SIMULATION_RESULTS (stats, gemini_content, evaluation_data) VALUES (%s, %s, %s) RETURNING id",
                             (json.dumps(_sanitize_for_json(stats)), json.dumps(gemini_content), json.dumps(_sanitize_for_json(evaluation_data)) if evaluation_data else None))
                results_id = cursor.fetchone()[0]


                # CRITICAL FIX: Calculate and save ALL precalculated data (matching SQLite implementation)
                # This fixes empty plots by ensuring all data needed for visualization is stored
                import numpy as np
                import pandas as pd

                percentile_paths = None
                asset_percentile_paths = None
                final_net_worths_hist_data = None
                sampled_paths = None
                backtest_path_df = None

                if results_dataframe is not None and not results_dataframe.empty:
                    monte_carlo_df =results_dataframe
                    if 'Backtest' in results_dataframe.columns:
                        backtest_path_df = results_dataframe['Backtest'].unstack(level='Metric')
                        monte_carlo_df = results_dataframe.drop(columns='Backtest')

                    asset_value_df = monte_carlo_df.xs('Asset Value', level=1, axis=0)
                    net_worth_df = monte_carlo_df.xs('Net Worth', level=1, axis=0)

                    percentile_paths = pd.DataFrame({
                        'p25': net_worth_df.quantile(0.25, axis=1),
                        'p50': net_worth_df.median(axis=1),
                        'p75': net_worth_df.quantile(0.75, axis=1)
                    })

                    asset_percentile_paths = pd.DataFrame({
                        'p25': asset_value_df.quantile(0.25, axis=1),
                        'p50': asset_value_df.median(axis=1),
                        'p75': asset_value_df.quantile(0.75, axis=1)
                    })

                    final_net_worths_raw = net_worth_df.iloc[-1]
                    # Log-spaced bins (matching the log-scale x-axis) with bin count
                    # scaled to sample size (num_simulations ranges 1,000-10,000+).
                    counts, bin_edges = compute_log_scale_histogram(final_net_worths_raw)
                    final_net_worths_hist_data = {'counts': counts, 'bin_edges': bin_edges}

                    num_sims = params.get('num_simulations', 10000)
                    num_to_sample = min(num_sims, 50)
                    sim_names = results_dataframe.columns.unique()
                    sampled_sim_names = np.random.choice(sim_names, num_to_sample, replace=False)
                    sampled_paths = results_dataframe[sampled_sim_names]

                # Save ALL data blobs (matching SQLite's save order)
                _save_dataframe_to_db(cursor, results_id, 'net_worth_percentile_paths', percentile_paths)
                _save_dataframe_to_db(cursor, results_id, 'asset_percentile_paths', asset_percentile_paths)
                _save_dict_to_db(cursor, results_id, 'final_net_worths_hist', final_net_worths_hist_data)
                _save_dataframe_to_db(cursor, results_id, 'sampled_paths', sampled_paths)
                _save_dataframe_to_db(cursor, results_id, 'average_results_df', average_results_df)
                _save_dataframe_to_db(cursor, results_id, 'median_yearly_results_df', median_yearly_results_df)

                # Save backtest path if available
                if backtest_path_df is not None:
                    _save_dataframe_to_db(cursor, results_id, 'backtest_path', backtest_path_df)

                # Save evaluation data if available
                if evaluation_data:
                    _save_dict_to_db(cursor, results_id, 'evaluation_data', evaluation_data)
                    logging.info(f"Saved evaluation data for results_id {results_id}")

                # Update cached simulation with component hashes
                component_hashes = params.get('component_hashes', {})
                cursor.execute("""UPDATE CACHED_SIMULATIONS
                                 SET results_id = %s,
                                     status = %s,
                                     component_hashes = %s,
                                     updated_at = CURRENT_TIMESTAMP
                                 WHERE simulation_hash = %s""",
                             (results_id, status, json.dumps(component_hashes), simulation_hash))
                return results_id
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return None

    def cleanup_old_simulations(self, days_to_keep=30):
        """Clean up old simulations (placeholder)."""
        return 0

    @log_db_call
    def hide_shared_item(self, user_id, item_type, item_id):
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(self.queries.HIDE_SHARED_ITEM,
                              {'user_id': user_id, 'item_type': item_type, 'item_id': item_id})
            return True
        except Exception as e:
            logging.error(f"Failed to hide shared item: {e}", exc_info=True)
            return False

    def get_simulations_needing_pdf(self, limit=10):
        """Get simulations with pending PDF status."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Use query direct or from queries object if verified available
                cursor.execute("""
                    SELECT
                        cs.simulation_hash,
                        sr.id as results_id,
                        sr.pdf_status
                    FROM CACHED_SIMULATIONS cs
                    JOIN SIMULATION_RESULTS sr ON cs.results_id = sr.id
                    WHERE sr.pdf_status = 'pending'
                    ORDER BY sr.created_at ASC
                    LIMIT %s
                """, (limit,))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return []

    @log_db_call
    def update_simulation_pdf_storage(self, simulation_hash, storage_path, status, gen_time_ms=None, error_msg=None):
        """Update PDF storage info."""
        try:
            with self._connection_cursor() as cursor:
                if gen_time_ms is not None:
                    cursor.execute("""
                        UPDATE SIMULATION_RESULTS
                        SET pdf_storage_path = %s,
                            pdf_status = %s,
                            pdf_generated_at = CURRENT_TIMESTAMP,
                            pdf_generation_time_ms = %s,
                            pdf_error_message = %s
                        WHERE id = (
                            SELECT results_id FROM CACHED_SIMULATIONS
                            WHERE simulation_hash = %s
                        )
                    """, (storage_path, status, gen_time_ms, error_msg, simulation_hash))
                else:
                    cursor.execute("""
                        UPDATE SIMULATION_RESULTS
                        SET pdf_storage_path = %s,
                            pdf_status = %s,
                            pdf_error_message = %s
                        WHERE id = (
                            SELECT results_id FROM CACHED_SIMULATIONS
                            WHERE simulation_hash = %s
                        )
                    """, (storage_path, status, error_msg, simulation_hash))
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)

    @log_db_call
    def get_pdf_info_by_hash(self, simulation_hash):
        """Get PDF info for simulation."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT
                        sr.pdf_status,
                        sr.pdf_storage_path,
                        sr.pdf_generated_at,
                        sr.pdf_generation_time_ms,
                        sr.pdf_error_message
                    FROM CACHED_SIMULATIONS cs
                    JOIN SIMULATION_RESULTS sr ON cs.results_id = sr.id
                    WHERE cs.simulation_hash = %s
                """, (simulation_hash,))
                return cursor.fetchone()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return None
