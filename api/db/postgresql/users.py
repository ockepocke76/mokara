"""User accounts, access management, tiers, and login requests.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import psycopg2
from psycopg2 import extras
import logging

from core.cache import ttl_cache

from ..logging_utils import log_db_call


# Tables with a user_id FK to USERS(id) that isn't ON DELETE CASCADE — must be
# cleared before the user row itself can go. background_jobs uses ON DELETE
# SET NULL so it doesn't need to be listed here.
_USER_OWNED_TABLES = [
    'user_settings', 'user_simulation_history', 'custom_strategies',
    'strategy_evaluations', 'subscription_history', 'ai_credit_usage',
    'logs', 'simulations_old', 'user_hidden_items', 'strategy_generation_runs',
]


class UsersMixin:
    """User accounts, access management, tiers, and login requests. Mixed into PostgreSQLDatabase."""

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

        except Exception as e:
            logging.error(f"Failed get/create user: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            self.release_connection(conn)

    @log_db_call
    def log_login_request(self, email, name):
        """Log or update unauthorized login attempt."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO login_requests (email, name, attempt_count)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (email) DO UPDATE SET
                        last_attempt_at = CURRENT_TIMESTAMP,
                        attempt_count = login_requests.attempt_count + 1,
                        name = EXCLUDED.name
                """, (email.lower(), name))
        except Exception as e:
            logging.error(f"Failed to log login request: {e}", exc_info=True)

    @log_db_call
    def get_login_requests(self, limit=100):
        """Get all login requests ordered by most recent."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
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

    @log_db_call
    def delete_login_request(self, email):
        """Remove a login request."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("DELETE FROM login_requests WHERE email = %s", (email.lower(),))
        except Exception as e:
            logging.error(f"Failed to delete login request: {e}", exc_info=True)

    @log_db_call
    def add_allowed_user(self, email, added_by=None, notes=None):
        """Grant access to a user."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO allowed_users (email, added_by, notes)
                    VALUES (%s, %s,%s)
                    ON CONFLICT (email) DO NOTHING
                """, (email.lower(), added_by, notes))
        except Exception as e:
            logging.error(f"Failed to add allowed user: {e}", exc_info=True)

    @log_db_call
    def remove_allowed_user(self, email):
        """Revoke access from a user."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("DELETE FROM allowed_users WHERE email = %s", (email.lower(),))
        except Exception as e:
            logging.error(f"Failed to remove allowed user: {e}", exc_info=True)

    @log_db_call
    def delete_users_by_id(self, user_ids):
        """
        Completely delete users and all their associated data, by id.

        None of the USERS(id) foreign keys are ON DELETE CASCADE, and a DB
        trigger refuses to delete a public/leaderboard-published strategy —
        so a bare `DELETE FROM users` fails for any user with real data.
        This unpublishes strategies first, then clears dependents in the
        right order, then the user rows themselves. Safe to call with an
        empty list (no-op).
        """
        if not user_ids:
            return 0
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(
                    "UPDATE custom_strategies SET is_public = false, is_published_to_leaderboard = false "
                    "WHERE user_id = ANY(%s) AND (is_public OR is_published_to_leaderboard)",
                    (user_ids,))
                if cursor.rowcount:
                    from db.cache import clear_leaderboard_cache
                    clear_leaderboard_cache(f"deleting {len(user_ids)} user(s)")

                # strategy_versions.created_by_user_id has no FK to users (a
                # version node outlives any one strategy by design), so it
                # never blocks the deletes below but also never cascades.
                cursor.execute(
                    "DELETE FROM strategy_versions WHERE created_by_user_id = ANY(%s)",
                    (user_ids,))

                for table in _USER_OWNED_TABLES:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id = ANY(%s)", (user_ids,))

                # login_requests/allowed_users are keyed by (lowercased) email,
                # not user_id — matched case-insensitively since users.email
                # isn't normalized to lowercase on insert.
                cursor.execute(
                    "DELETE FROM login_requests WHERE lower(email) IN "
                    "(SELECT lower(email) FROM users WHERE id = ANY(%s))",
                    (user_ids,))
                cursor.execute(
                    "DELETE FROM allowed_users WHERE lower(email) IN "
                    "(SELECT lower(email) FROM users WHERE id = ANY(%s))",
                    (user_ids,))

                cursor.execute("DELETE FROM users WHERE id = ANY(%s)", (user_ids,))
                deleted = cursor.rowcount

            logging.info(f"Deleted {deleted} user(s) and their dependent data")
            return deleted

        except Exception as e:
            logging.error(f"Failed to delete users ({len(user_ids)} ids): {e}", exc_info=True)
            return 0

    @log_db_call
    def delete_user(self, email):
        """Completely delete a user (by email) and all their associated data.

        Also clears any login_requests/allowed_users entry for the email even
        if no `users` row exists yet (allow-listed or attempted login, but
        never completed signup).
        """
        email_lower = email.lower()
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("DELETE FROM login_requests WHERE lower(email) = %s", (email_lower,))
                cursor.execute("DELETE FROM allowed_users WHERE lower(email) = %s", (email_lower,))
                cursor.execute("SELECT id FROM users WHERE lower(email) = %s", (email_lower,))
                row = cursor.fetchone()

            if not row:
                logging.info(f"delete_user: no users row for {email}; cleared login_requests/allowed_users only")
                return False

            deleted = self.delete_users_by_id([row[0]])
            if deleted:
                logging.info(f"Successfully deleted user: {email}")
            return bool(deleted)

        except Exception as e:
            logging.error(f"Failed to delete user {email}: {e}", exc_info=True)
            return False

    @log_db_call
    def get_allowed_users(self,):
        """Get all allowed users."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT id, email, added_at, added_by, notes
                    FROM allowed_users
                    ORDER BY added_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get allowed users: {e}", exc_info=True)
            return []

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
        try:
            with self._connection_cursor(commit=False) as cursor:
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

    @log_db_call
    def is_user_allowed(self, email):
        """
        Check if user has access.
        Auto-approves new users if 'max_beta_users' quota is not met.
        """
        email_lower = email.lower()
        try:
            with self._connection_cursor() as cursor:
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
                    return True

                logging.info(f"Beta quota full. User rejected: {email} ({current_users}/{max_users})")
                return False

        except Exception as e:
            logging.error(f"Failed to check allowed user: {e}", exc_info=True)
            return False

    @log_db_call
    def username_exists(self, username):
        """Check if display name already exists (case-insensitive)."""
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM USERS WHERE LOWER(display_name) = LOWER(%s)",
                    (username,)
                )
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            logging.error(f"Failed to check username existence: {e}", exc_info=True)
            return False

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
        try:
            with self._connection_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE USERS
                    SET display_name = %s,
                        display_name_updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_name, user_id)
                )
                updated = cursor.rowcount > 0
            return updated
        except Exception as e:
            logging.error(f"Failed to update display name: {e}", exc_info=True)
            return False

    @log_db_call
    def get_display_name(self, user_id):
        """Get user's display name (or email as fallback)."""
        try:
            with self._connection_cursor(commit=False) as cursor:
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

    def migrate_allowed_users_from_file(self):
        """One-time migration from allowed_users.txt to database."""
        # ... existing implementation ...
        try:
            from pathlib import Path
            # (R5.2b: one .parent deeper than in db/postgresql_db.py — this
            # module lives in db/postgresql/; the file lives next to api/.)
            file_path = Path(__file__).parent.parent.parent / "allowed_users.txt"
            
            if not file_path.exists():
                return 0
            
            with open(file_path, 'r') as f:
                emails = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]
            
            try:
                with self._connection_cursor() as cursor:
                    migrated = 0
                    for email in emails:
                        cursor.execute("""
                            INSERT INTO allowed_users (email, added_by, notes)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (email) DO NOTHING
                        """, (email, 'migration', 'Migrated from allowed_users.txt'))
                        if cursor.rowcount > 0:
                            migrated += 1
                    return migrated
            except Exception as e:
                logging.error(f"Failed to migrate allowed users: {e}", exc_info=True)
                return 0
        except Exception as e:
            logging.error(f"Failed to read allowed_users.txt: {e}", exc_info=True)
            return 0

    @log_db_call
    def get_user_tier(self, user_id):
        """Get user's tier."""
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute("SELECT plan_tier FROM USERS WHERE id = %s", (user_id,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)
            return None

    @log_db_call
    def update_user_tier(self, user_id, new_tier, changed_by, reason):
        """Update user's tier."""
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("UPDATE USERS SET plan_tier = %s, tier_set_at = CURRENT_TIMESTAMP, tier_set_by = %s WHERE id = %s",
                             (new_tier, changed_by, user_id))
                cursor.execute("INSERT INTO SUBSCRIPTION_HISTORY (user_id, plan_tier, changed_to, changed_by, reason) VALUES (%s, %s, %s, %s, %s)",
                             (user_id, new_tier, new_tier, changed_by, reason))
        except Exception as e:
            logging.error(f"Failed: {e}", exc_info=True)

    @log_db_call
    def ensure_admin_user_exists(self):
        """
        Ensures at least one admin user exists.
        If no users have ADMIN tier, assigns it to the bootstrap admin email.
        """
        BOOTSTRAP_ADMIN_EMAIL = 'oscar.sverud@gmail.com'

        try:
            with self._connection_cursor(commit=False) as cursor:
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
