"""Connection pool, cursor lifecycle, migrations, and teardown.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import threading
import logging
import json
from pathlib import Path

from ..logging_utils import log_db_call


class ConnectionCore:
    """Owns the pool, cursors, and schema lifecycle; mixins build on this."""

    def __init__(self, queries, config):
        self.queries = queries
        self.config = config

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
        """Get a psycopg2 connection from the pool."""
        # Log high usage
        with self._lock:
            self._active_connections += 1
            current_active = self._active_connections
        
        # (The old per-checkout Cloud Monitoring export never worked — it
        # NameError'd on an unimported os and swallowed it; rely on Cloud
        # Run's built-in metrics instead.)
        if current_active >= 8: # 80% warning threshold
             # COMMENTED OUT TO PREVENT RECURSIVE LOGGING BOMB
             # The DatabaseHandler captures logs/stderr and writes to DB, calling get_connection...
             pass

        # Retry logic for pool exhaustion
        import time 
        for i in range(5):
            try:
                return self.pool.getconn()
            except psycopg2.pool.PoolError:
                if i == 4:
                    with self._lock: # Revert count if we fail
                        self._active_connections -= 1
                    logging.error("Connection pool exhausted after retries")
                    raise
                logging.warning(f"Connection pool exhausted, retrying ({i+1}/5)...")
                time.sleep(0.2) # Wait a bit
        
        # Fallback (should be covered by raise above)
        return self.pool.getconn()

    def release_connection(self, conn):
        """Releases the connection back to the pool."""
        try:
            self.pool.putconn(conn)
        finally:
             with self._lock:
                self._active_connections = max(0, self._active_connections - 1)

    def _get_cursor(self, conn, cursor_factory=None):
        """Helper to get a cursor (optionally with a cursor_factory, e.g. RealDictCursor)."""
        return conn.cursor(cursor_factory=cursor_factory)

    @contextmanager
    def _connection_cursor(self, cursor_factory=None, commit=True):
        """Pooled connection + cursor; commits on success, rolls back on
        exception, always releases. Methods keep their own except-and-return
        policies — this only owns the connection lifecycle."""
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn, cursor_factory=cursor_factory)
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.release_connection(conn)

    # (R5.2b: one .parent deeper than in db/postgresql_db.py — this module
    # lives in db/postgresql/, migrations stay in db/.)
    MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations" / "postgresql"

    @classmethod
    def migration_files(cls):
        """Migration files on disk, sorted by their V<N> prefix."""
        import re

        cls.MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

        def version_number(filepath):
            match = re.match(r'V(\d+)', filepath.name)
            return int(match.group(1)) if match else 999999

        return sorted(cls.MIGRATIONS_DIR.glob("V*.sql"), key=version_number)

    def get_migration_status(self, preview_lines=10):
        """Pending vs. applied migrations, for the admin dashboard."""
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute("SELECT version, applied_at FROM schema_version")
                applied_at = {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            # schema_version doesn't exist until the first run_migrations().
            logging.warning(f"Could not read schema_version: {e}")
            applied_at = {}

        on_disk = self.migration_files()
        on_disk_names = {f.name for f in on_disk}

        pending = []
        applied = []
        for f in on_disk:
            if f.name in applied_at:
                applied.append({"version": f.name, "applied_at": applied_at[f.name]})
            else:
                lines = f.read_text().splitlines()
                preview = "\n".join(lines[:preview_lines])
                if len(lines) > preview_lines:
                    preview += "\n... (truncated)"
                pending.append({"version": f.name, "preview": preview})

        # Applied but no longer on disk — deleted/renamed after being run.
        for version, ts in applied_at.items():
            if version not in on_disk_names:
                applied.append({"version": version, "applied_at": ts, "file_missing": True})
        applied.sort(key=lambda a: a["applied_at"], reverse=True)

        return {"pending": pending, "applied": applied}

    def list_tables(self):
        """Public-schema table names, for the admin schema check."""
        with self._connection_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            return [row[0] for row in cursor.fetchall()]

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
            
            migration_files = self.migration_files()
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
    def drop_all_tables(self):
        """
        DANGER: Drops all tables in the public schema.
        Used for system hard reset.
        """
        try:
            with self._connection_cursor() as cursor:
                # PostgreSQL specific: Drop schema and recreate it
                # This is cleaner than dropping individual tables
                cursor.execute("DROP SCHEMA public CASCADE;")
                cursor.execute("CREATE SCHEMA public;")
                cursor.execute("GRANT ALL ON SCHEMA public TO public;")
                cursor.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
            logging.warning("🔥🔥🔥 FULL DATABASE WIPE COMPLETED (DROP SCHEMA public) 🔥🔥🔥")
        except Exception as e:
            logging.error(f"Failed to wipe database: {e}")
            raise e

    def __del__(self):
        """Clean up pool."""
        try:
            if hasattr(self, 'pool') and self.pool and not self.pool.closed:
                self.pool.closeall()
        except Exception:
            pass
