"""
PostgreSQL Database Implementation - COMPLETE

Automatically adapted from SQLiteDatabase with PostgreSQL-specific modifications.
Key changes:
- sqlite3 → psycopg2
- Thread-local connections → Connection pooling  
- AUTOINCREMENT → SERIAL
- lastrowid → RETURNING clause
- Dict row factory → RealDictCursor
"""

import psycopg2
from typing import Optional, Dict, List, Any
from psycopg2 import pool, extras,sql
import threading
import logging
import json
import io
import pickle
import re
from datetime import datetime, timezone
import pandas as pd
from pathlib import Path

from core.cache import ttl_cache

from .database_interface import DatabaseInterface, Dialect
from .utils import _sanitize_for_json
from utils.strategy_utils import calculate_strategy_hash
from db.queries import PostgreSQLQueries
from .logging_utils import log_db_call


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


class PostgreSQLDialect(Dialect):
    """PostgreSQL-specific SQL dialect."""
    
    def json_parse(self, column):
        """PostgreSQL uses  JSONB."""
        return f"{column}::jsonb"



class PostgreSQLCursor:
    """Cursor wrapper to auto-convert SQLite ? placeholders to PostgreSQL %s."""
    def __init__(self, cursor):
        self._cursor = cursor
        
    def execute(self, query, params=None):
        """Execute with automatic placeholder and parameter conversion.
        
        Simplified for PostgreSQL-only usage:
        - Queries already using %(param)s syntax are passed through unchanged
        - Legacy :param style is converted to %(param)s
        - Legacy ? style is converted to %s
        """
        if isinstance(query, str):
            # QUICK FIX: Skip transformation if query already uses PostgreSQL %(param)s syntax
            if '%(' in query:
                # Query already uses PostgreSQL-native syntax, pass through unchanged
                return self._cursor.execute(query, params)
            
            if isinstance(params, dict):
                original_query = query
                # Convert :key to %(key)s for PostgreSQL named parameters
                for key in params.keys():
                    # Regex matches :key but not ::key (casts) or :key_suffix.
                    # Pattern: (?<!:):key\b
                    query = re.sub(rf'(?<!:):{re.escape(str(key))}\b', f'%({key})s', query)
                
                # If named parameters were not used/found, check for positional (?)
                if query == original_query and '?' in query:
                    # Fallback for legacy queries using ? but receiving a dict
                    query = query.replace('?', '%s')
                    params = tuple(params.values())
            else:
                # Sequence params - Convert ? to %s for PostgreSQL (positional)
                query = query.replace('?', '%s')
        
        return self._cursor.execute(query, params)
    
    def executescript(self, script):
        return self._cursor.execute(script)
    
    def fetchone(self):
        return self._cursor.fetchone()
    
    def fetchall(self):
        return self._cursor.fetchall()
    
    @property
    def rowcount(self):
        return self._cursor.rowcount
    
    @property
    def description(self):
        return self._cursor.description
    
    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgreSQLConnection:
    """Wrapper for psycopg2 connection to ensure cursors are wrapped."""
    def __init__(self, connection):
        self._conn = connection
    
    def cursor(self, *args, **kwargs):
        """Return a wrapped cursor (or unwrapped for RealDictCursor)."""
        raw_cursor = self._conn.cursor(*args, **kwargs)
        
        # SIMPLIFIED: For PostgreSQL-only deployment, don't wrap RealDictCursor
        # RealDictCursor already uses PostgreSQL-native %(param)s syntax
        if isinstance(raw_cursor, extras.RealDictCursor):
            return raw_cursor
        
        # Wrap other cursor types for legacy SQLite syntax compatibility
        return PostgreSQLCursor(raw_cursor)
    
    def commit(self):
        return self._conn.commit()
    
    def rollback(self):
        return self._conn.rollback()
    
    def close(self):
        return self._conn.close()
        
    def __getattr__(self, name):
        return getattr(self._conn, name)


class PostgreSQLDatabase(DatabaseInterface):
    """
    PostgreSQL database implementation with connection pooling.
    
    Benefits over SQLite:
    - No file locking
    - True MVCC concurrency
    - Better scaling
    """
    
    def __init__(self, queries, config):
        super().__init__(queries)
        self.config = config
        self.dialect = PostgreSQLDialect()
        
        # Create connection pool
        # Connect to DB
        # Optimized for Cloud Run and Streamlit concurrency
        import os
        pool_max = int(os.getenv('DB_POOL_MAX', 20))
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=pool_max,
            host=config.get('host', 'localhost'),
            port=config.get('port', 5432),
            database=config.get('database', 'btc_simulator'),
            user=config.get('user'),
            password=config.get('password', ''),
            sslmode=config.get('sslmode', 'prefer')
        )
        
        # Connection Tracking
        self._active_connections = 0
        self._lock = threading.Lock()
        
        logging.info(f"PostgreSQL pool created: {config.get('database')}")
    
    def get_active_connection_count(self):
        """Returns the number of currently checked-out connections."""
        with self._lock:
            return self._active_connections

    def deserialize_json_column(self, value):
        """
        Deserializes a JSON column value to dict/list.
        PostgreSQL JSONB columns may return as string depending on driver config.
        """
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value
    
    def get_database_info(self):
        """Get connection info for admin dashboard."""
        return {
            'host': self.config.get('host'),
            'database': self.config.get('database'),
            'port': self.config.get('port'),
            'user': self.config.get('user')
        }

    def get_connection(self):
        """Get connection from pool - returns WRAPPED connection."""
        # Log high usage
        with self._lock:
            self._active_connections += 1
            current_active = self._active_connections
        
        # Export pool utilization to Cloud Monitoring
        try:
            pool_max = int(os.getenv('DB_POOL_MAX', 20))
            utilization_pct = (current_active / pool_max) * 100
            
            from monitoring.cloud_monitoring import export_metric
            export_metric('db_pool_utilization', utilization_pct, {
                'pool_size': str(pool_max),
                'active_connections': str(current_active)
            })
        except Exception:
            pass  # Silently fail if monitoring unavailable
        
        # Max pool size is 10 (hardcoded in init currently)
        if current_active >= 8: # 80% warning threshold
             # COMMENTED OUT TO PREVENT RECURSIVE LOGGING BOMB
             # The DatabaseHandler captures logs/stderr and writes to DB, calling get_connection...
             pass

        # Retry logic for pool exhaustion
        import time 
        for i in range(5):
            try:
                conn = self.pool.getconn()
                return PostgreSQLConnection(conn)
            except psycopg2.pool.PoolError:
                if i == 4:
                    with self._lock: # Revert count if we fail
                        self._active_connections -= 1
                    logging.error("Connection pool exhausted after retries")
                    raise
                logging.warning(f"Connection pool exhausted, retrying ({i+1}/5)...")
                time.sleep(0.2) # Wait a bit
        
        # Fallback (should be covered by raise above)
        conn = self.pool.getconn()
        return PostgreSQLConnection(conn)
    
    def release_connection(self, conn):
        """Releases the connection back to the pool."""
        try:
            if hasattr(conn, '_conn'):
                # It's a wrapped connection
                self.pool.putconn(conn._conn)
            else:
                self.pool.putconn(conn)
        finally:
             with self._lock:
                self._active_connections = max(0, self._active_connections - 1)

    def _get_cursor(self, conn, cursor_factory=None):
        """Helper to get a wrapped cursor."""
        # Conn is already wrapped, so conn.cursor() returns PostgreSQLCursor
        return conn.cursor(cursor_factory=cursor_factory)
    

    
    def run_migrations(self, conn=None):
        """Apply PostgreSQL migrations.

        Serialized cluster-wide with an advisory lock (api startup, worker
        startup, and the admin endpoint may race otherwise), and a genuine
        migration failure ABORTS the run — later migrations must not apply
        on top of a half-failed schema.
        """
        logging.info("Running PostgreSQL migrations...")

        should_release = False
        if conn is None:
            conn = self.get_connection()
            should_release = True

        locked = False
        try:
            cursor = self._get_cursor(conn)

            # One runner at a time, cluster-wide.
            cursor.execute("SELECT pg_advisory_lock(hashtext('mokara_migrations'))")
            locked = True

            # Create schema_version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
            # Get applied migrations
            cursor.execute("SELECT version FROM schema_version")
            applied_versions = {row[0] for row in cursor.fetchall()}
            logging.info(f"Applied migrations: {applied_versions or 'None'}")
            
            # Find migration files
            migrations_dir = Path(__file__).parent / "migrations" / "postgresql"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            
            migration_files_raw = list(migrations_dir.glob("V*.sql"))
            
            # Sort by version
            def get_version_number(filepath):
                import re
                match = re.match(r'V(\d+)', filepath.name)
                return int(match.group(1)) if match else 999999
            
            migration_files = sorted(migration_files_raw, key=get_version_number)
            logging.info(f"Found {len(migration_files)} migrations")
            
            for migration_file in migration_files:
                version = migration_file.name
                if version not in applied_versions:
                    logging.info(f"Applying migration: {version}")
                    try:
                        with open(migration_file, 'r') as f:
                            sql_script = f.read()
                            cursor.execute(sql_script)
                        
                        cursor.execute(
                            "INSERT INTO schema_version (version) VALUES (%s)",
                            (version,)
                        )
                        conn.commit()
                        logging.info(f"✅ Applied: {version}")
                    except Exception as e:
                        error_str = str(e)
                        # Rollback the failed transaction first
                        conn.rollback()

                        # Legacy bootstrap tolerance: the original schema
                        # predates migration tracking, so early migrations
                        # hit objects that already exist (or drop ones that
                        # never did). Those are recorded and skipped.
                        if "already exists" in error_str or "does not exist" in error_str:
                            logging.warning(f"⚠️  Skipping {version}: {error_str}")
                            # Mark as applied anyway to prevent re-running (in new transaction)
                            cursor.execute(
                                "INSERT INTO schema_version (version) VALUES (%s) ON CONFLICT DO NOTHING",
                                (version,)
                            )
                            conn.commit()
                            continue
                        # Anything else is a real failure: abort the run —
                        # applying later migrations on a half-failed schema
                        # compounds the damage. (Previously this logged and
                        # continued.)
                        logging.error(f"❌ Failed {version}: {e}", exc_info=True)
                        raise

            logging.info("Migrations complete")
        finally:
            if locked:
                try:
                    # Control may reach here with the transaction aborted
                    # (e.g. the schema_version bootstrap failed before the
                    # per-migration loop) — executing on an aborted
                    # transaction raises and would silently LEAK the session
                    # lock into the pool, wedging every future run. Roll
                    # back first so the unlock always reaches Postgres.
                    conn.rollback()
                    cursor.execute("SELECT pg_advisory_unlock(hashtext('mokara_migrations'))")
                    conn.commit()
                except Exception:
                    logging.exception("Failed to release migration advisory lock")
            if should_release:
                self.release_connection(conn)
    
    @log_db_call
    def save_simulation_results(self, simulation_hash, params, ui_params, stats, 
                                results_dataframe, average_results_df, median_yearly_results_df,
                                gemini_content, user_id, simulation_name, is_replacement_run=False):
        """Save simulation results - PostgreSQL version."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
            
            conn.commit()
            logging.info(f"Saved simulation {simulation_hash[:10]}, history_id={history_id}")
            return history_id
            
        except Exception as e:
            logging.error(f"Failed to save simulation: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_user_simulations(self, user_email=None):
        """Fetch user simulations. If user_email is None, fetch demo simulations."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
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
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_or_create_user_id(self, user_email, user_name):
        """Get or create user."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
            # Try get
            cursor.execute("SELECT id FROM USERS WHERE email = %s", (user_email,))
            row = cursor.fetchone()
            if row:
                return row[0]
            
            # Create with RETURNING
            # Create with RETURNING
            # Try to set display_name to user_name initially
            try:
                cursor.execute(
                    "INSERT INTO USERS (email, name, display_name) VALUES (%s, %s, %s) RETURNING id",
                    (user_email, user_name, user_name)
                )
                user_id = cursor.fetchone()[0]
                conn.commit()
            except psycopg2.errors.UniqueViolation:
                # Fallback: Create without display_name, then update with {name}{id}
                conn.rollback() 
                cursor = self._get_cursor(conn) # New cursor needed
                
                # 1. Create user with NULL display_name
                cursor.execute(
                    "INSERT INTO USERS (email, name) VALUES (%s, %s) RETURNING id",
                    (user_email, user_name)
                )
                user_id = cursor.fetchone()[0]
                
                # 2. Update with ID suffix
                try:
                    suffixed_name = f"{user_name}{user_id}"
                    cursor.execute(
                        "UPDATE USERS SET display_name = %s WHERE id = %s",
                        (suffixed_name, user_id)
                    )
                    conn.commit()
                    logging.info(f"Created user {user_email} with suffixed username {suffixed_name}")
                except Exception as e:
                    # If suffix update fails, just leave as NULL (email fallback)
                    logging.warning(f"Failed to set suffixed username for {user_id}: {e}")
                    conn.commit() # Commit the user creation at least
            
            logging.info(f"Created user {user_email} (ID:{user_id})")
            return user_id
            
            logging.info(f"Created user {user_email} (ID:{user_id})")
            return user_id
            
        except Exception as e:
            logging.error(f"Failed get/create user: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)
    
    # === Login Request Tracking & Allowed Users Management ===
    
    @log_db_call
    def log_login_request(self, email, name):
        """Log or update unauthorized login attempt."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                INSERT INTO login_requests (email, name, attempt_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (email) DO UPDATE SET
                    last_attempt_at = CURRENT_TIMESTAMP,
                    attempt_count = login_requests.attempt_count + 1,
                    name = EXCLUDED.name
            """, (email.lower(), name))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to log login request: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_login_requests(self, limit=100):
        """Get all login requests ordered by most recent."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("""
                SELECT id, email, name, first_attempt_at, last_attempt_at, attempt_count, notes
                FROM login_requests
                ORDER BY last_attempt_at DESC
                LIMIT %s
            """, (limit,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get login requests: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def delete_login_request(self, email):
        """Remove a login request."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("DELETE FROM login_requests WHERE email = %s", (email.lower(),))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to delete login request: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def add_allowed_user(self, email, added_by=None, notes=None):
        """Grant access to a user."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                INSERT INTO allowed_users (email, added_by, notes)
                VALUES (%s, %s,%s)
                ON CONFLICT (email) DO NOTHING
            """, (email.lower(), added_by, notes))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to add allowed user: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def remove_allowed_user(self, email):
        """Revoke access from a user."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("DELETE FROM allowed_users WHERE email = %s", (email.lower(),))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to remove allowed user: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def delete_user(self, email):
        """
        Completely delete a user and all their associated data.
        Cascades to:
        - Simulations, Strategies (via Foreign Key on USERS)
        - Allowed Users entry
        - Login Requests
        - Subscription History
        """
        conn = self.get_connection()
        email_lower = email.lower()
        try:
            cursor = self._get_cursor(conn)
            
            # 1. Delete from Login Requests
            cursor.execute("DELETE FROM login_requests WHERE email = %s", (email_lower,))
            
            # 2. Delete from Subscription History
            # Need user_id first to be safe, or join?
            # Sub history links to user_id.
            cursor.execute("SELECT id FROM users WHERE email = %s", (email_lower,))
            row = cursor.fetchone()
            if row:
                user_id = row[0]
                cursor.execute("DELETE FROM subscription_history WHERE user_id = %s", (user_id,))
            
            # 3. Delete from Allowed Users
            cursor.execute("DELETE FROM allowed_users WHERE email = %s", (email_lower,))
            
            # 4. Delete from Users (Cascades to Sims, Strategies)
            cursor.execute("DELETE FROM users WHERE email = %s", (email_lower,))
            
            conn.commit()
            logging.info(f"Successfully deleted user: {email}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to delete user {email}: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)


    @log_db_call
    def get_allowed_users(self,):
        """Get all allowed users."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("""
                SELECT id, email, added_at, added_by, notes
                FROM allowed_users
                ORDER BY added_at DESC
            """)
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get allowed users: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)

    
    @log_db_call
    def get_beta_status(self):
        """
        Get current beta program status.
        Returns:
            dict: {'current_users': int, 'max_users': int, 'is_full': bool, 'percent_full': float}
        """
        # Cached for 5 minutes to prevent hammering the DB on every page load.
        return self._fetch_beta_status()

    @ttl_cache(ttl=300)
    def _fetch_beta_status(self):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
                
            # Get max users
            cursor.execute("SELECT setting_value FROM SYSTEM_SETTINGS WHERE setting_key = 'max_beta_users'")
            row = cursor.fetchone()
            max_users = int(row[0]) if row and row[0] is not None else 50
                
            # Get current count
            cursor.execute("SELECT COUNT(*) FROM allowed_users")
            current_users = cursor.fetchone()[0]
                
            return {
                'current_users': current_users,
                'max_users': max_users,
                'is_full': current_users >= max_users,
                'percent_full': min(current_users / max_users, 1.0) if max_users > 0 else 1.0
            }
        except Exception as e:
            logging.error(f"Failed to get beta status: {e}")
            # Fallback to conservative "Full" status on error
            return {'current_users': 0, 'max_users': 0, 'is_full': True, 'percent_full': 1.0}
        finally:
            self.release_connection(conn)

        
    @log_db_call
    def is_user_allowed(self, email):
        """
        Check if user has access.
        Auto-approves new users if 'max_beta_users' quota is not met.
        """
        conn = self.get_connection()
        email_lower = email.lower()
        try:
            cursor = self._get_cursor(conn)
            
            # 1. Check if user is ALREADY allowed (fast path)
            cursor.execute("SELECT 1 FROM allowed_users WHERE email = %s", (email_lower,))
            if cursor.fetchone() is not None:
                return True
            
            # 2. Check Beta Quota
            # Get max users (default 50)
            cursor.execute("SELECT setting_value FROM SYSTEM_SETTINGS WHERE setting_key = 'max_beta_users'")
            row = cursor.fetchone()
            max_users = int(row[0]) if row and row[0] is not None else 50
            
            # Get current count
            cursor.execute("SELECT COUNT(*) FROM allowed_users")
            current_users = cursor.fetchone()[0]
            
            # 3. Auto-approve logic
            if current_users < max_users:
                logging.info(f"Auto-approving beta user: {email} ({current_users + 1}/{max_users})")
                cursor.execute("""
                    INSERT INTO allowed_users (email, added_by, notes)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                """, (email_lower, 'system_auto_join', 'Auto-joined via Beta Quota'))
                conn.commit()
                return True
            
            logging.info(f"Beta quota full. User rejected: {email} ({current_users}/{max_users})")
            return False
            
        except Exception as e:
            logging.error(f"Failed to check allowed user: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    def get_system_setting(self, key, default=None):
        """Get a global system setting."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("SELECT setting_value FROM SYSTEM_SETTINGS WHERE setting_key = %s", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logging.error(f"Failed to get system setting '{key}': {e}")
            return default
        finally:
            self.release_connection(conn)
    
    # ============================================================================
    # USERNAME MANAGEMENT
    # ============================================================================
    
    @log_db_call
    def username_exists(self, username):
        """Check if display name already exists (case-insensitive)."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                "SELECT COUNT(*) FROM USERS WHERE LOWER(display_name) = LOWER(%s)",
                (username,)
            )
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            logging.error(f"Failed to check username existence: {e}", exc_info=True)
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_display_name(self, user_id, new_name):
        """
        Update user's display name.
        
        Args:
            user_id: User ID
            new_name: New display name
            
        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE USERS 
                SET display_name = %s,
                    display_name_updated_at = NOW()
                WHERE id = %s
                """,
                (new_name, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to update display name: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_display_name(self, user_id):
        """Get user's display name (or email as fallback)."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                "SELECT display_name, email FROM USERS WHERE id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                # Return display_name if set, otherwise fall back to email
                return row[0] if row[0] else row[1]
            return None
        except Exception as e:
            logging.error(f"Failed to get display name: {e}", exc_info=True)
            return None
        finally:
            self.release_connection(conn)

    def set_system_setting(self, key, value):
        """Set a global system setting."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                INSERT INTO SYSTEM_SETTINGS (setting_key, setting_value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) 
                DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = CURRENT_TIMESTAMP
            """, (key, str(value)))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to set system setting '{key}': {e}")
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    def migrate_allowed_users_from_file(self):
        """One-time migration from allowed_users.txt to database."""
        # ... existing implementation ...
        try:
            from pathlib import Path
            file_path = Path(__file__).parent.parent / "allowed_users.txt"
            
            if not file_path.exists():
                return 0
            
            with open(file_path, 'r') as f:
                emails = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]
            
            conn = self.get_connection()
            try:
                cursor = self._get_cursor(conn)
                migrated = 0
                for email in emails:
                    cursor.execute("""
                        INSERT INTO allowed_users (email, added_by, notes)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (email) DO NOTHING
                    """, (email, 'migration', 'Migrated from allowed_users.txt'))
                    if cursor.rowcount > 0:
                        migrated += 1
                conn.commit()
                return migrated
            except Exception as e:
                logging.error(f"Failed to migrate allowed users: {e}", exc_info=True)
                conn.rollback()
                return 0
            finally:
                self.release_connection(conn)
        except Exception as e:
            logging.error(f"Failed to read allowed_users.txt: {e}", exc_info=True)
            return 0
    
    # Continue with all other methods following the same pattern...
    
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
        conn = self.get_connection()
        logging.info(f"DEBUG: add_to_user_history called for User={user_id} Hash={simulation_hash[:8]}")
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """INSERT INTO USER_SIMULATION_HISTORY 
                   (user_id, simulation_hash, simulation_name)
                   VALUES (%s, %s, %s)
                   RETURNING id""",
                (user_id, simulation_hash, simulation_name)
            )
            history_id = cursor.fetchone()[0]
            conn.commit()
            return history_id
        except Exception as e:
            logging.error(f"Failed to add history: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)

    @log_db_call
    def create_cached_simulation_entry(self, simulation_hash, params):
        """Create pending cache entry."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """INSERT INTO CACHED_SIMULATIONS 
                   (simulation_hash, parameters, status)
                   VALUES (%s, %s, 'PENDING')
                   ON CONFLICT (simulation_hash) DO NOTHING""",
                (simulation_hash, json.dumps(_sanitize_for_json(params)))
            )
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to create cache entry: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    

    
    @log_db_call
    def update_cached_simulation_status(self, simulation_hash, status):
        """Update simulation status."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """UPDATE CACHED_SIMULATIONS 
                   SET status = %s, updated_at = CURRENT_TIMESTAMP
                   WHERE simulation_hash = %s""",
                (status, simulation_hash)
            )
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to update status: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_user_simulations_with_params(self, user_email):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def mark_simulation_as_removed(self, simulation_id, user_id=None):
        """
        Marks a simulation history entry as removed.
        If it's a demo simulation and a user_id is provided, it hides it for that user instead of deleting it.
        SECURE: Requires valid user_id and verifies ownership for non-demo simulations.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to remove simulation: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def permanently_delete_simulation(self, simulation_id):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to delete: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_all_simulations(self):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_simulation_details(self, simulation_hash):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
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
        finally:
            self.release_connection(conn)
    
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
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
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
        finally:
            self.release_connection(conn)

    @log_db_call
    def update_cached_simulation_params(self, simulation_hash, params):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(self.queries.UPDATE_SIMULATION_PARAMS, {
                'simulation_hash': simulation_hash,
                'params': json.dumps(_sanitize_for_json(params))
            })
            conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            self.release_connection(conn)
    
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
            
            # --- Git Service Initialization ---
            try:
                from services.git_service import get_git_service
                git_service = get_git_service()
            except Exception as e:
                logging.warning(f"Git service unavailable: {e}")
                git_service = None
                
            # Use passed-in values if available, otherwise they will be determined by Git logic below
            git_repo_url = None
            
            # If values were passed from UI, they are the source of truth
            # We only run the internal Git logic if they are missing or if we want to force a refresh
            # For now, let's allow them to be passed in.
            
            # Check for existence
            if strategy_id:
                cursor.execute("SELECT id, git_branch_name, code FROM CUSTOM_STRATEGIES WHERE id = %s", (strategy_id,))
            else:
                cursor.execute("SELECT id, git_branch_name, code FROM CUSTOM_STRATEGIES WHERE user_id = %s AND strategy_name = %s", (user_id, strategy_name))
            row = cursor.fetchone()
            
            if row:
                # === UPDATE EXISTING STRATEGY ===
                strategy_id, existing_branch, existing_code = row
                
                # Check for Materialization Event (Pure Reference -> Independent Strategy)
                # If we are saving code to a record that currently has NULL code, this is the first edit.
                is_materialization = (existing_code is None) and (code is not None)
                
                # 1. Handle Git Commit
                if git_service and code: # Only touch Git if we have code to save
                    try:
                        # Determine branch name
                        branch_name = existing_branch or f"strategies/user-{user_id}/strat-{strategy_id}"
                        
                        # Lazy Forking: If materializing (or branch missing), ensure branch exists
                        if is_materialization or not existing_branch:
                            try:
                                # Create branch from source SHA if available (linked to parent) or empty-template
                                if clone_source_commit_sha:
                                     logging.info(f"Materializing clone {strategy_id}: Forking from {clone_source_commit_sha}")
                                     git_service.create_branch(branch_name, from_commit_sha=clone_source_commit_sha, from_branch='empty-template')
                                else:
                                     git_service.create_branch(branch_name, from_branch='empty-template')
                            except Exception:
                                try:
                                    # Fallback to main
                                    git_service.create_branch(branch_name, from_branch='main')
                                except Exception as e:
                                    # If branch already exists, we are fine
                                    logging.warning(f"Git branch creation warning (might exist): {e}")

                        # Build metadata
                        from datetime import datetime
                        metadata = {
                            "version": "1.0",
                            "strategy_name": strategy_name,
                            "user_description": description,
                            "ai_description": ai_description,
                            "parameters": json.loads(parameters_json) if parameters_json else {},
                            "validation_status": validation_status,
                            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
                            "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
                            "evolution_history": []
                        }
                        
                        # Fetch existing metadata (if any) to preserve history
                        if not is_materialization:
                             try:
                                 existing_metadata = git_service.get_metadata(branch_name)
                                 if existing_metadata:
                                     if 'evolution_history' in existing_metadata:
                                         metadata['evolution_history'] = existing_metadata['evolution_history']
                                     if 'created_at' in existing_metadata:
                                         metadata['created_at'] = existing_metadata['created_at']
                             except Exception as e:
                                 logging.debug(f"Metadata load skipped: {e}")
                        
                        # Append evolution entry
                        if evolution_request:
                             metadata['evolution_history'].append({
                                'timestamp': datetime.now(timezone.utc).isoformat() + "Z",
                                'request': evolution_request,
                                'user_id': user_id
                             })

                        commit_msg = f"Update strategy: {strategy_name}"
                        if evolution_request:
                            commit_msg += f"\n\nEvolution request: {evolution_request[:200]}"
                        elif is_materialization:
                            commit_msg = f"Fork/Materialize strategy: {strategy_name}"

                        # Commit
                        files_to_commit = {
                            'strategy.py': code,
                            'metadata.json': json.dumps(metadata, indent=2)
                        }
                        
                        git_commit_sha = git_service.commit_multiple_files(
                            branch_name=branch_name,
                            files=files_to_commit,
                            message=commit_msg
                        )
                        
                        # Backfill SHA in metadata
                        if evolution_request and metadata['evolution_history']:
                            metadata['evolution_history'][-1]['commit_sha'] = git_commit_sha
                            git_service.commit_multiple_files(branch_name=branch_name, files={'metadata.json': json.dumps(metadata, indent=2)}, message="Update metadata SHA")
                        
                        git_branch_name = branch_name
                        git_repo_url = f"https://github.com/{git_service.repo_owner}/{git_service.repo_name}"
                        short_sha = git_commit_sha[:7] if git_commit_sha else "None"
                        logging.info(f"Git commit successful: {short_sha} on {branch_name}")

                    except Exception as e:
                        logging.error(f"Git update failed for {strategy_name}: {e}")

                # 2. Database Update
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
                        git_branch_name = %s, git_repo_url = %s,
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
                      git_branch_name, git_repo_url, 
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
                    # DB-native evolution history (V37). The git metadata above
                    # is best-effort only — mokara runs without the GitHub repo,
                    # so this column is the authoritative timeline. Aliased
                    # import: a bare `timezone` here would shadow the module
                    # import for the WHOLE function, breaking the git block
                    # above (Python scoping). Savepoint: recording the timeline
                    # must never fail the save itself (e.g. V37 not applied).
                    from datetime import datetime as _dt, timezone as _tz
                    entry = {
                        'timestamp': _dt.now(_tz.utc).isoformat(),
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
                # Logic: If code is provided -> Independent Strategy (requires Git)

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
                    # Trigger Git now
                    if git_service:
                        try:
                             # ... (Existing Git creation logic for new strats) ...
                             # We can mostly reuse the update logic block, but simpler to just implement standard creation here
                             # For brevity, reusing the standard "Insert then Update" pattern is often cleaner, 
                             # but let's implement the specific Insert for standard strat.
                             pass # Proceed to Git logic
                        except Exception:
                             pass

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
                
                # If we just inserted a Standard Strategy (with code), we should do the Git Init now.
                # However, your existing codebase did the Git Commit *before* Insert in the "Else" block (which I replaced).
                # To be robust: If we have code, we should trigger the Git Sync immediately after obtaining the ID.
                
                if code and git_service:
                     # Trigger post-creation sync (or simple "Update" call) to create branch
                     # Since we are inside the transaction, we can just call the Git logic here.
                     try:
                         branch_name = f"strategies/user-{user_id}/strat-{strategy_id}"
                         git_service.create_branch(branch_name, from_branch='empty-template')
                         
                         # Commit Initial
                         files_to_commit = {'strategy.py': code, 'metadata.json': json.dumps({"strategy_name": strategy_name}, indent=2)}
                         git_commit_sha = git_service.commit_multiple_files(branch_name=branch_name, files=files_to_commit, message=f"Initial commit: {strategy_name}")
                         
                         # Update DB with Git info
                         cursor.execute("UPDATE CUSTOM_STRATEGIES SET git_branch_name=%s, git_commit_sha=%s, git_repo_url=%s WHERE id=%s",
                                        (branch_name, git_commit_sha, f"https://github.com/{git_service.repo_owner}/{git_service.repo_name}", strategy_id))
                     except Exception as e:
                         logging.error(f"Failed to init Git for new strategy {strategy_id}: {e}")

                if parent_strategy_id:
                     self.increment_fork_count(parent_strategy_id)
                        
                # 3. Fallback: Content Hash (Critical for Identity)
                if code and not git_commit_sha:
                    # Calculate hash if Git didn't provide one (e.g. service unavailable or failure)
                    git_commit_sha = calculate_strategy_hash(code, json.loads(parameters_json) if parameters_json else {})
                    logging.info(f"Using content hash for {strategy_name} (Git unavailable/failed): {git_commit_sha}")
                    
                    # Update DB with content hash
                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES 
                        SET git_commit_sha = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (git_commit_sha, strategy_id))

            conn.commit()
            
            # --- Post-Commit Verification ---
            # Reuse existing connection to avoid pool deadlock risk.
            # commit() closed the previous transaction, so this SELECT starts a new one
            # and will only see the data if it was successfully committed.
            try:
                # Use a fresh cursor just to be clean
                verify_cursor = self._get_cursor(conn)
                verify_cursor.execute("SELECT id FROM CUSTOM_STRATEGIES WHERE id = %s", (strategy_id,))
                if not verify_cursor.fetchone():
                    logging.critical(f"CRITICAL: Strategy {strategy_id} committed but NOT found in verification check!")
                    return False
            except Exception as ve:
                logging.error(f"Verification check failed: {ve}")
                # Don't fail the save if just the check failed
                pass

            return strategy_id
        except Exception as e:
            logging.error(f"Failed to save custom strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_user_custom_strategies(self, user_id):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)
    @log_db_call
    def get_custom_strategy(self, strategy_id):
        """Fetch a specific custom strategy by ID."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
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
        finally:
            self.release_connection(conn)

    @log_db_call
    def hide_shared_item(self, user_id, item_type, item_id):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(self.queries.HIDE_SHARED_ITEM, 
                          {'user_id': user_id, 'item_type': item_type, 'item_id': item_id})
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to hide shared item: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

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
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
            
            conn.commit()
            logging.info(f"Soft deleted strategy {strategy_id} for user {user_id}")
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to soft delete strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def restore_custom_strategy(self, strategy_id, user_id):
        """
        Restores a soft-deleted strategy by clearing deleted_at timestamp.
        Note: Admin check should be done by caller before calling this method.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
            
            conn.commit()
            logging.info(f"Restored strategy {strategy_id}")
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to restore strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    
    @log_db_call
    def update_custom_strategy(self, strategy_id, user_id, strategy_name, description, ai_description, parameters_json, git_branch_name=None, git_commit_sha=None):
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
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
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to update custom strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_strategy_evolution_history(self, strategy_id):
        """
        Fetch evolution history from Git metadata.
        
        Args:
            strategy_id: Strategy ID
        
        Returns:
            List of evolution entries with timestamp, request, commit_sha, user_id
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                SELECT git_branch_name, git_commit_sha, evolution_history
                FROM CUSTOM_STRATEGIES
                WHERE id = %s
            """, (strategy_id,))

            row = cursor.fetchone()
            if not row:
                return []

            branch_name, commit_sha, db_history = row

            if isinstance(db_history, str):
                db_history = json.loads(db_history)
            db_history = db_history or []

            # Git metadata covers entries from the old GitHub-backed app;
            # the DB column (V37) covers everything since. A save with git
            # configured writes to both, so merge with dedup rather than
            # letting either source hide the other.
            git_history = []
            if branch_name:
                try:
                    from services.git_service import get_git_service
                    git_service = get_git_service()
                    metadata = git_service.get_metadata(branch_name, commit_sha)
                    if metadata and 'evolution_history' in metadata:
                        git_history = metadata['evolution_history'] or []
                except Exception as e:
                    logging.error(f"Failed to fetch evolution history from Git: {e}")

            # A git-configured save writes the same event to both stores with
            # slightly different timestamp suffixes — key on seconds + request.
            def _key(e):
                return ((e.get('timestamp') or '')[:19], e.get('request'))

            seen = {_key(e) for e in git_history}
            return git_history + [e for e in db_history if _key(e) not in seen]
        except Exception as e:
            logging.error(f"Failed to get evolution history: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)

    @log_db_call
    def increment_fork_count(self, strategy_id):
        """Increments the fork count for a strategy."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("UPDATE CUSTOM_STRATEGIES SET fork_count = COALESCE(fork_count, 0) + 1 WHERE id = %s", (strategy_id,))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to increment fork count for strategy {strategy_id}: {e}")
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def set_strategy_published_status(self, strategy_id, user_id, is_published):
        """Toggle whether a custom strategy is published to the leaderboard."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            # Verify ownership before allowing change
            cursor.execute("""
                UPDATE CUSTOM_STRATEGIES 
                SET is_published_to_leaderboard = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
            """, (is_published, strategy_id, user_id))
            conn.commit()
            
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
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    def get_simulations_needing_pdf(self, limit=10):
        """Get simulations with pending PDF status."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_simulation_pdf_storage(self, simulation_hash, storage_path, status, gen_time_ms=None, error_msg=None):
        """Update PDF storage info."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
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
            conn.commit()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_pdf_info_by_hash(self, simulation_hash):
        """Get PDF info for simulation."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def save_strategy_evaluation(self, evaluation_data):
        """Save strategy evaluation using INSERT...ON CONFLICT."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
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
            
            conn.commit()
            logging.info(f"Successfully saved evaluation for {evaluation_data['strategy_name']}")
            return True  # Return success indicator
        except Exception as e:
            logging.error(f"Failed to save evaluation: {e}", exc_info=True)
            conn.rollback()
            return False  # Return failure indicator
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_leaderboard(self, category=None, limit=50):
        """Get strategy leaderboard."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute(self.queries.GET_LEADERBOARD.replace('?', '%s'), (category, limit))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)
    
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
            
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
            # Primary lookup
            result = None
            if git_commit_sha:
                cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA.replace('?', '%s'), (git_commit_sha,))
                result = cursor.fetchone()
            
            # Fallback lookup (for clones)
            if not result and lookup_fallback_sha:
                primary_display = git_commit_sha[:7] if git_commit_sha else "None"
                fallback_display = lookup_fallback_sha[:7] if lookup_fallback_sha else "None"
                logging.info(f"Primary SHA {primary_display} not found, checking fallback {fallback_display}")
                cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA.replace('?', '%s'), (lookup_fallback_sha,))
                result = cursor.fetchone()
                
            return result
        except Exception as e:
            logging.error(f"Failed to get evaluation: {e}", exc_info=True)
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_user_tier(self, user_id):
        """Get user's tier."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("SELECT plan_tier FROM USERS WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_user_tier(self, user_id, new_tier, changed_by, reason):
        """Update user's tier."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("UPDATE USERS SET plan_tier = %s, tier_set_at = CURRENT_TIMESTAMP, tier_set_by = %s WHERE id = %s",
                         (new_tier, changed_by, user_id))
            cursor.execute("INSERT INTO SUBSCRIPTION_HISTORY (user_id, plan_tier, changed_to, changed_by, reason) VALUES (%s, %s, %s, %s, %s)",
                         (user_id, new_tier, new_tier, changed_by, reason))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_history_status(self, history_id, status):
        """Update history entry status."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("UPDATE USER_SIMULATION_HISTORY SET status = %s WHERE id = %s", (status, history_id))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def ensure_admin_user_exists(self):
        """
        Ensures at least one admin user exists.
        If no users have ADMIN tier, assigns it to the bootstrap admin email.
        """
        BOOTSTRAP_ADMIN_EMAIL = 'oscar.sverud@gmail.com'
        
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
            # Check if any user has ADMIN tier
            cursor.execute("SELECT COUNT(*) FROM USERS WHERE plan_tier = 'ADMIN'")
            admin_count = cursor.fetchone()[0]
            
            if admin_count == 0:
                # No admins exist, assign to bootstrap user
                logging.info(f"No admin users found. Auto-assigning ADMIN tier to {BOOTSTRAP_ADMIN_EMAIL}")
                
                # Get or create the bootstrap user
                cursor.execute("SELECT id FROM USERS WHERE email = %s", (BOOTSTRAP_ADMIN_EMAIL,))
                row = cursor.fetchone()
                
                if row:
                    user_id = row[0]
                    # Update existing user
                    self.update_user_tier(
                        user_id=user_id,
                        new_tier='ADMIN',
                        changed_by='SYSTEM',
                        reason='Bootstrap admin - no admins existed'
                    )
                else:
                    # Create the user if they don't exist
                    user_id = self.get_or_create_user_id(BOOTSTRAP_ADMIN_EMAIL, 'Oscar Sverud')
                    if user_id:
                        self.update_user_tier(
                            user_id=user_id,
                            new_tier='ADMIN',
                            changed_by='SYSTEM',
                            reason='Bootstrap admin - initial setup'
                        )
                logging.info(f"Successfully assigned ADMIN tier to {BOOTSTRAP_ADMIN_EMAIL}")
        except Exception as e:
            logging.error(f"Failed to ensure admin user exists: {e}", exc_info=True)
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_cached_simulation_results(self, simulation_hash, params, ui_params, stats, 
                                        results_dataframe, average_results_df, 
                                        median_yearly_results_df, gemini_content, status='COMPLETED', evaluation_data=None):
        """Update cached simulation with results."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
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
                p1 = np.percentile(final_net_worths_raw, 1)
                p99 = np.percentile(final_net_worths_raw, 99)
                counts, bin_edges = np.histogram(final_net_worths_raw, bins=200, range=(p1, p99))
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
            conn.commit()
            return results_id
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_leaderboard(self, category=None, limit=50):
        """Fetch leaderboard, optionally filtered by category."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_all_custom_strategies_for_admin(self):
        """Fetch all custom strategies for admin evaluation."""
        logging.info("Admin: Fetching all custom strategies for evaluation")
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
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
        finally:
            self.release_connection(conn)

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
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
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
        finally:
            self.release_connection(conn)

    @log_db_call
    def increment_global_counter(self, metric_key, value=1):
        """
        Increment a global persistent counter.
        Creates the row if it doesn't exist (e.g., for new metrics).
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                INSERT INTO GLOBAL_STATS (metric_key, metric_value)
                VALUES (%s, %s)
                ON CONFLICT (metric_key) 
                DO UPDATE SET metric_value = GLOBAL_STATS.metric_value + EXCLUDED.metric_value
            """, (metric_key, value))
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to increment global counter {metric_key}: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_community_stats(self):
        """
        Get aggregated community statistics from persistent GLOBAL_STATS table.
        Falls back to live counts if global stats are missing/zero (backward compatibility).
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
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
        finally:
            self.release_connection(conn)

    def cleanup_old_simulations(self, days_to_keep=30):
        """Clean up old simulations (placeholder)."""
        return 0

    # =====================================================================
    # Background Job Queue Methods
    # =====================================================================
    
    @log_db_call
    def create_background_job(self, job_type, payload, user_id=None, priority=5, 
                             idempotency_key=None, max_retries=3, timeout_seconds=900):
        """
        Create a new background job.
        
        Args:
            job_type: Type of job ('pdf_generation', 'strategy_evaluation', etc.)
            payload: Dict of job parameters (will be serialized to JSONB)
            user_id: ID of user who requested the job
            priority: 1-10, higher = more urgent (default: 5)
            idempotency_key: Unique key to prevent duplicate jobs
            max_retries: Maximum retry attempts on failure
            timeout_seconds: Timeout for processing (default: 15 minutes)
            
        Returns:
            str: Job ID (UUID as string)
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            
            # Sanitize payload for JSON (handles date/datetime/numpy objects)
            sanitized_payload = _sanitize_for_json(payload)
            
            cursor.execute("""
                INSERT INTO BACKGROUND_JOBS (
                    job_type, payload, user_id, priority, scheduled_at,
                    idempotency_key, max_retries, timeout_seconds
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING id
            """, (job_type, json.dumps(sanitized_payload), user_id, priority, 
                  idempotency_key, max_retries, timeout_seconds))
            
            job_id = cursor.fetchone()[0]
            conn.commit()
            logging.info(f"Created background job {job_id}: {job_type}")
            return str(job_id)
        except psycopg2.IntegrityError as e:
            # Idempotency key violation - job already exists
            conn.rollback()
            if idempotency_key:
                logging.info(f"Job with idempotency_key {idempotency_key} already exists")
                # Fetch existing job ID
                cursor.execute("SELECT id FROM BACKGROUND_JOBS WHERE idempotency_key = %s", (idempotency_key,))
                row = cursor.fetchone()
                return str(row[0]) if row else None
            raise
        except Exception as e:
            logging.error(f"Failed to create background job: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_job_by_id(self, job_id):
        """Get job details by ID."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("SELECT * FROM BACKGROUND_JOBS WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            
            if job:
                # Deserialize JSON columns
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                job['result'] = self.deserialize_json_column(job.get('result'))
            
            return job
        except Exception as e:
            logging.error(f"Failed to get job {job_id}: {e}", exc_info=True)
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_job_by_idempotency_key(self, idempotency_key):
        """Get job by idempotency key (for duplicate prevention)."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("SELECT * FROM BACKGROUND_JOBS WHERE idempotency_key = %s", (idempotency_key,))
            job = cursor.fetchone()
            
            if job:
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                job['result'] = self.deserialize_json_column(job.get('result'))
            
            return job
        except Exception as e:
            logging.error(f"Failed to get job by idempotency_key: {e}", exc_info=True)
            return None
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def fetch_and_lock_job(self, worker_id):
        """
        Fetch and lock the next available job for processing.
        
        Uses FOR UPDATE SKIP LOCKED to allow multiple workers to safely
        fetch different jobs concurrently without conflicts.
        
        Args:
            worker_id: Identifier of worker claiming the job
            
        Returns:
            dict: Job data, or None if no jobs available
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
            # CRITICAL: FOR UPDATE SKIP LOCKED is the magic that allows concurrent workers
            cursor.execute("""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'PROCESSING',
                    started_at = CURRENT_TIMESTAMP,
                    heartbeat_at = CURRENT_TIMESTAMP,
                    worker_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM BACKGROUND_JOBS
                    WHERE status = 'PENDING'
                      AND scheduled_at <= CURRENT_TIMESTAMP
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
            """, (worker_id,))
            
            job = cursor.fetchone()
            conn.commit()
            
            if job:
                # Deserialize JSON columns
                job['payload'] = self.deserialize_json_column(job.get('payload'))
                logging.info(f"Worker {worker_id} claimed job {job['id']}: {job['job_type']}")
            
            return job
        except Exception as e:
            logging.error(f"Failed to fetch job for worker {worker_id}: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)
    
    # Terminal job transitions are fenced: they only apply while the job is
    # still PROCESSING and (when a worker_id is given) still owned by that
    # worker. A worker whose claim was revoked by stale-job recovery — and
    # whose job may already be re-running elsewhere — must not overwrite the
    # reclaimer's state (CODE_REVIEW R2.1).
    _JOB_OWNER_FENCE = "AND status = 'PROCESSING' AND (%(worker_id)s::text IS NULL OR worker_id = %(worker_id)s)"

    @log_db_call
    def complete_job(self, job_id, result, worker_id=None):
        """
        Mark job as completed with result.

        Args:
            job_id: Job UUID
            result: Result data (will be serialized to JSONB)
            worker_id: When given, the update only applies if this worker
                still owns the job (fence against revoked claims).

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'COMPLETED',
                    result = %(result)s,
                    completed_at = CURRENT_TIMESTAMP,
                    processing_time_ms = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at)) * 1000
                WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
            """, {'result': json.dumps(_sanitize_for_json(result)),
                  'job_id': job_id, 'worker_id': worker_id})
            updated = cursor.rowcount > 0
            conn.commit()
            if updated:
                logging.info(f"Job {job_id} completed successfully")
            else:
                logging.warning(
                    f"Job {job_id}: completion by worker {worker_id} ignored — "
                    "claim no longer held (job was recovered or already terminal)")
            return updated
        except Exception as e:
            logging.error(f"Failed to mark job {job_id} as completed: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def fail_job(self, job_id, error_message, worker_id=None):
        """
        Mark job as permanently failed (after max retries exceeded).

        Args:
            job_id: Job UUID
            error_message: Error description
            worker_id: When given, only applies if this worker still owns the job.

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'FAILED',
                    error_message = %(error)s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
            """, {'error': error_message, 'job_id': job_id, 'worker_id': worker_id})
            updated = cursor.rowcount > 0
            conn.commit()
            if updated:
                logging.error(f"Job {job_id} failed permanently: {error_message}")
            else:
                logging.warning(
                    f"Job {job_id}: failure report by worker {worker_id} ignored — "
                    "claim no longer held")
            return updated
        except Exception as e:
            logging.error(f"Failed to mark job {job_id} as failed: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def drop_all_tables(self):
        """
        DANGER: Drops all tables in the public schema.
        Used for system hard reset.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # PostgreSQL specific: Drop schema and recreate it
            # This is cleaner than dropping individual tables
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
            conn.commit()
            logging.warning("🔥🔥🔥 FULL DATABASE WIPE COMPLETED (DROP SCHEMA public) 🔥🔥🔥")
        except Exception as e:
            conn.rollback()
            logging.error(f"Failed to wipe database: {e}")
            raise e
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def retry_job(self, job_id, error_message, scheduled_at, worker_id=None):
        """
        Reset job to PENDING for retry with exponential backoff.

        Args:
            job_id: Job UUID
            error_message: Error that caused retry
            scheduled_at: Unix timestamp when job should be retried
            worker_id: When given, only applies if this worker still owns the job.

        Returns:
            bool: True if the job row was updated (claim still held).
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(f"""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'PENDING',
                    retry_count = retry_count + 1,
                    error_message = %(error)s,
                    scheduled_at = to_timestamp(%(scheduled_at)s),
                    started_at = NULL,
                    heartbeat_at = NULL,
                    worker_id = NULL
                WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
            """, {'error': error_message, 'scheduled_at': scheduled_at,
                  'job_id': job_id, 'worker_id': worker_id})
            updated = cursor.rowcount > 0
            conn.commit()
            if updated:
                logging.warning(f"Job {job_id} scheduled for retry: {error_message}")
            else:
                logging.warning(
                    f"Job {job_id}: retry request by worker {worker_id} ignored — "
                    "claim no longer held")
            return updated
        except Exception as e:
            logging.error(f"Failed to retry job {job_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def heartbeat_job(self, job_id, worker_id):
        """
        Record that the given worker is still actively processing the job.

        Returns:
            bool: True if the beat landed (this worker still owns the job);
            False when the claim was revoked — the worker's eventual
            complete/fail will be fenced out, so the job is effectively
            running for nothing.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                UPDATE BACKGROUND_JOBS
                SET heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = %s AND worker_id = %s AND status = 'PROCESSING'
            """, (job_id, worker_id))
            beat = cursor.rowcount > 0
            conn.commit()
            return beat
        except Exception as e:
            logging.error(f"Heartbeat failed for job {job_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_job_status(self, job_id, status, error_message=None):
        """
        Update job status and optionally clear error message.
        
        Args:
            job_id: Job UUID
            status: New status ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
            error_message: Optional error message (None to clear)
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                UPDATE BACKGROUND_JOBS
                SET 
                    status = %s,
                    error_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, error_message, job_id))
            conn.commit()
            logging.info(f"Job {job_id} status updated to {status}")
        except Exception as e:
            logging.error(f"Failed to update job {job_id} status: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def reset_stale_jobs(self, heartbeat_timeout_seconds=300):
        """
        Re-queue PROCESSING jobs whose worker stopped heartbeating.

        Recovery keys on worker liveness, not wall-clock job age: a long
        simulation on a live worker keeps beating and is never reset mid-run
        (the old global age cutoff re-queued legitimately long jobs and
        caused concurrent double-runs — CODE_REVIEW R2.1).

        Jobs with NULL heartbeat_at were claimed by a worker that never
        beats (pre-heartbeat binary during a rolling deploy, or in-flight
        rows from before migration V38). Presuming those dead after the
        heartbeat window would re-introduce the double-run for legitimately
        long jobs — they instead get their own full timeout_seconds budget
        (default 900s) before reclaim.

        Args:
            heartbeat_timeout_seconds: silence threshold before a worker is
                presumed dead (default 5 min; beats land every ~30s).

        Returns:
            int: Number of jobs recovered
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'PENDING',
                    started_at = NULL,
                    heartbeat_at = NULL,
                    worker_id = NULL,
                    error_message = 'Recovered: worker stopped heartbeating'
                WHERE status = 'PROCESSING'
                  AND (
                    (heartbeat_at IS NOT NULL
                     AND heartbeat_at < CURRENT_TIMESTAMP - make_interval(secs => %s))
                    OR
                    (heartbeat_at IS NULL
                     AND started_at < CURRENT_TIMESTAMP
                         - make_interval(secs => COALESCE(timeout_seconds, 900)))
                  )
                RETURNING id
            """, (heartbeat_timeout_seconds,))

            recovered_ids = [row[0] for row in cursor.fetchall()]
            conn.commit()

            if recovered_ids:
                logging.warning(f"Recovered {len(recovered_ids)} stale jobs: {recovered_ids}")

            return len(recovered_ids)
        except Exception as e:
            logging.error(f"Failed to reset stale jobs: {e}", exc_info=True)
            conn.rollback()
            return 0
        finally:
            self.release_connection(conn)

    @log_db_call
    def fail_timed_out_jobs(self, heartbeat_timeout_seconds=300, default_timeout_seconds=900):
        """
        Fail PROCESSING jobs that exceeded their own timeout_seconds while
        their worker is still alive (heartbeating) — a runaway job, not a
        crash. The row goes terminal so the user gets resolution and no
        retry storm starts; the zombie worker's eventual complete/fail is
        fenced out by the PROCESSING-status guard.

        Returns:
            int: Number of jobs failed
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                UPDATE BACKGROUND_JOBS
                SET
                    status = 'FAILED',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = 'Job exceeded its timeout ('
                        || COALESCE(timeout_seconds, %s)::text || 's) while still running'
                WHERE status = 'PROCESSING'
                  AND started_at < CURRENT_TIMESTAMP
                      - make_interval(secs => COALESCE(timeout_seconds, %s))
                  AND COALESCE(heartbeat_at, started_at)
                      >= CURRENT_TIMESTAMP - make_interval(secs => %s)
                RETURNING id
            """, (default_timeout_seconds, default_timeout_seconds,
                  heartbeat_timeout_seconds))

            failed_ids = [row[0] for row in cursor.fetchall()]
            conn.commit()

            if failed_ids:
                logging.warning(f"Failed {len(failed_ids)} timed-out jobs: {failed_ids}")

            return len(failed_ids)
        except Exception as e:
            logging.error(f"Failed to fail timed-out jobs: {e}", exc_info=True)
            conn.rollback()
            return 0
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_user_jobs(self, user_id, limit=50):
        """Get recent jobs for a user (for admin/debugging)."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("""
                SELECT id, job_type, status, priority, created_at, completed_at, error_message
                FROM BACKGROUND_JOBS
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get user jobs: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def get_jobs(self, job_type=None, status=None, limit=50):
        """
        List background jobs with optional filtering.
        
        Args:
            job_type: Filter by 'job_type' column
            status: Filter by 'status' column
            limit: Max rows to return
            
        Returns:
            List of job dictionaries
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            
            query = "SELECT * FROM BACKGROUND_JOBS WHERE 1=1"
            params = []
            
            if job_type:
                query += " AND job_type = %s"
                params.append(job_type)
            
            if status:
                query += " AND status = %s"
                params.append(status)
                
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to list jobs: {e}", exc_info=True)
            return []
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_queue_stats(self):
        """Get job queue statistics (for monitoring)."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=extras.RealDictCursor)
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    AVG(CASE WHEN processing_time_ms IS NOT NULL THEN processing_time_ms ELSE NULL END) as avg_processing_ms
                FROM BACKGROUND_JOBS
                WHERE created_at > CURRENT_TIMESTAMP -  INTERVAL '24 hours'
                GROUP BY status
            """)
            rows = cursor.fetchall()
            
            stats = {row['status']: {'count': row['count'], 'avg_ms': row['avg_processing_ms']} for row in rows}
            return stats
        except Exception as e:
            logging.error(f"Failed to get queue stats: {e}", exc_info=True)
            return {}
        finally:
            self.release_connection(conn)
    
    @log_db_call
    def update_job_progress(self, job_id, progress_value, progress_message=None, worker_id=None):
        """
        Update job progress for real-time UI feedback.

        Progress writes double as heartbeats, and are fenced like the
        terminal transitions: an evicted worker must not mutate the payload
        of a job that has been reclaimed.

        Args:
            job_id: Job UUID
            progress_value: Float 0.0-1.0
            progress_message: Optional status message
            worker_id: When given, only applies if this worker still owns the job.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)

            # Update progress in payload JSONB field
            if progress_message:
                cursor.execute(f"""
                    UPDATE BACKGROUND_JOBS
                    SET payload = jsonb_set(
                        jsonb_set(payload, '{{progress_value}}', %(value)s::jsonb),
                        '{{progress_message}}', %(message)s::jsonb
                    ),
                    heartbeat_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                """, {'value': json.dumps(progress_value),
                      'message': json.dumps(progress_message),
                      'job_id': job_id, 'worker_id': worker_id})
            else:
                cursor.execute(f"""
                    UPDATE BACKGROUND_JOBS
                    SET payload = jsonb_set(payload, '{{progress_value}}', %(value)s::jsonb),
                        heartbeat_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %(job_id)s {self._JOB_OWNER_FENCE}
                """, {'value': json.dumps(progress_value),
                      'job_id': job_id, 'worker_id': worker_id})
            
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to update job progress: {e}", exc_info=True)
            conn.rollback()
        finally:
            self.release_connection(conn)

    def __del__(self):
        """Clean up pool."""
        try:
            if hasattr(self, 'pool') and self.pool and not self.pool.closed:
                self.pool.closeall()
        except Exception:
            pass


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
