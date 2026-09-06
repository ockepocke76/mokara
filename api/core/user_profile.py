"""
User Profile Management Module

This module handles the unified management of user data, spanning multiple tables
to create a cohesive "User Profile" object. It abstracts the underlying database
structure (USERS table + USER_SETTINGS table) to provide a simple API for
retrieving and updating user information.

Architecture:
- UserProfileService: Main entry point for profile operations.
- Expandable: Designed to easily add new fields (Age, Surname, etc.) by mapping
  them to the correct table columns.
"""

import logging
from typing import Dict, Any, Optional
from core.currency_config import CURRENCY_METADATA, DEFAULT_CURRENCY

class UserProfileService:
    """
    Service for managing user profiles.
    Unifies data from 'users' and 'user_settings' tables.
    """
    
    # Mapping of logical profile fields to database columns/tables
    # Format: 'field_name': ('table', 'column_name')
    FIELD_MAPPING = {
        'name': ('users', 'name'),
        'email': ('users', 'email'),
        'plan_tier': ('users', 'plan_tier'),
        'currency': ('user_settings', 'default_currency'),
        # Future fields can be added here easily:
        # 'age': ('user_settings', 'age'), # If added to DB
        # 'surname': ('users', 'surname'), # If added to DB
    }



    @staticmethod
    def get_user_profile(db, user_id: int) -> Dict[str, Any]:
        """
        Get the full user profile, joining necessary tables.
        
        Args:
            db: Database connection object
            user_id: The user's ID
            
        Returns:
            Dictionary containing combined profile data.
            Returns default structure if user not found.
        """
        if not user_id:
            return _get_default_profile()

        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Hybrid Fetch: Try to get currency from either location.
            # 1. First tried 'default_currency' column.
            # 2. If null, we might need to check 'setting_key' rows (but for now let's prioritize the column if it exists).
            
            # Note: Since we are writing to BOTH in the update, reading column is fine.
            query = f"""
                SELECT 
                    u.name, 
                    u.email, 
                    u.plan_tier,
                    COALESCE(s.default_currency, '{DEFAULT_CURRENCY}') as currency
                FROM USERS u
                LEFT JOIN USER_SETTINGS s ON u.id = s.user_id 
                AND (s.setting_key = 'default_currency' OR s.setting_key IS NULL)
                WHERE u.id = ?
                LIMIT 1
            """
            
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            
            if not row:
                # Fallback: Just get user data if join failed completely
                cursor.execute("SELECT name, email, plan_tier FROM USERS WHERE id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    return {
                        'name': user_row[0],
                        'email': user_row[1],
                        'plan_tier': user_row[2],
                        'currency': DEFAULT_CURRENCY
                    }
                logging.warning(f"User profile not found for ID {user_id}")
                return _get_default_profile()
                
            columns = [desc[0].lower() for desc in cursor.description]
            profile_data = dict(zip(columns, row))
            
            return profile_data
            
        except Exception as e:
            logging.error(f"Failed to fetch user profile: {e}", exc_info=True)
            return _get_default_profile()
        finally:
            db.release_connection(conn)

    @staticmethod
    def update_user_profile(db, user_id: int, **kwargs) -> bool:
        """
        Update fields in the user profile. Automatically routes updates to the
        correct database tables based on FIELD_MAPPING.
        
        Args:
            db: Database connection object
            user_id: The user's ID
            **kwargs: Key-value pairs of fields to update (e.g., currency='USD', name='John')
            
        Returns:
            True if all updates succeeded, False if any failed.
        """
        if not user_id:
            return False
            
        users_updates = {}
        settings_updates = {}
        
        # 1. Sort fields into their respective tables
        for key, value in kwargs.items():
            if key in UserProfileService.FIELD_MAPPING:
                table, column = UserProfileService.FIELD_MAPPING[key]
                if table == 'users':
                    users_updates[column] = value
                elif table == 'user_settings':
                    settings_updates[column] = value
            else:
                logging.warning(f"Attempted to update unknown profile field: {key}")

        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            success = True
            
            # 2. Execute updates for USERS table
            if users_updates:
                set_clause = ", ".join([f"{col} = ?" for col in users_updates.keys()])
                values = list(users_updates.values())
                values.append(user_id)
                
                sql = f"UPDATE USERS SET {set_clause} WHERE id = ?"
                cursor.execute(sql, values)
                
            # 3. Execute updates for USER_SETTINGS table (Upsert logic)
            if settings_updates:
                # SQLite/Postgres compatible Upsert logic handling
                # We first check if the row exists, then insert or update.
                # Since USER_SETTINGS has a PK on user_id, we can use UPSERT syntax if available,
                # but a robust cross-compatible approach is often safer for simple KV updates.
                # However, for USER_SETTINGS (user_id PK), we can used standardized ON CONFLICT.
                
                # Check DB type compatibility via the interface would be ideal, but standard SQL works here
                # because we are explicitly handling column updates.
                
                # For `default_currency`:
                if 'default_currency' in settings_updates:
                    currency = settings_updates['default_currency']
                    cursor.execute("""
                        UPDATE USER_SETTINGS 
                        SET default_currency = ?, setting_value = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE user_id = ? AND setting_key = 'default_currency'
                    """, (currency, currency, user_id))
                    
                    if cursor.rowcount == 0:
                        # Try inserting a new row ensuring setting_key is populated to satisfy NOT NULL constraint
                        # We also populate default_currency column to maintain hybrid compatibility
                        cursor.execute("""
                            INSERT INTO USER_SETTINGS (user_id, setting_key, setting_value, default_currency, updated_at)
                            VALUES (?, 'default_currency', ?, ?, CURRENT_TIMESTAMP)
                        """, (user_id, currency, currency))

            conn.commit()
            logging.info(f"Updated profile for user {user_id}: {kwargs.keys()}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to update user profile: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            db.release_connection(conn)


def _get_default_profile() -> Dict[str, Any]:
    """Returns the default profile structure."""
    return {
        'name': 'Guest',
        'email': '',
        'plan_tier': 'free',
        'currency': DEFAULT_CURRENCY
    }

# --- Helper Functions for UI consumptions ---

def get_currency_options() -> dict:
    """Returns simplified currency options for UI selectors."""
    return {code: f"{data['name']} ({code}) - {data['symbol']}" 
            for code, data in CURRENCY_METADATA.items()}
