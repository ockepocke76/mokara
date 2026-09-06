"""
Tier-based limit enforcement for simulations and strategies.
Provides clean interface for checking limits before user actions.
READS FROM STATIC CODE DEFINITIONS (tier_config/tiers.py)
"""

from typing import Tuple, Optional
import logging
import json

from tier_config.tiers import TIERS, DEFAULT_TIER_ID
from tier_config.models import Tier

logger = logging.getLogger(__name__)

class LimitEnforcer:
    """Enforces tier-based usage limits using Code-First definitions."""
    
    def __init__(self, db):
        self.db = db
    
    def get_tier_config(self, tier_id: str) -> Tier:
        """Get configuration object for a specific tier"""
        if tier_id not in TIERS:
            logger.warning(f"Tier '{tier_id}' not found, using default tier")
            return TIERS[DEFAULT_TIER_ID]
        return TIERS[tier_id]
    
    def get_user_tier(self, user_id: Optional[int]) -> str:
        """Get user's current tier ID, returns 'ANONYMOUS' if user_id is None"""
        if user_id is None:
            return 'ANONYMOUS'
        user = self._get_user(user_id)
        return user.get('plan_tier', DEFAULT_TIER_ID) if user else DEFAULT_TIER_ID
    
    def check_simulation_limit(self, user_id: Optional[int]) -> Tuple[bool, str, dict]:
        """
        Check if user can create a new simulation.
        
        Returns:
            (allowed: bool, message: str, usage_info: dict)
        """
        # Handle anonymous users
        if user_id is None:
            tier_config = TIERS['ANONYMOUS']
            # Anonymous users have limit 0 in new config, which effectively blocks them.
            # But maybe we want specific messaging?
            # The logic below handles limit 0: "0/0 simulations used" -> Blocked?
            # Wait, 0/0 is >= limit. So it returns Blocked.
            pass 
        
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        limit = tier_config.max_simulations
        
        if user_id is None:
             # Using new config, ANONYMOUS limit is 0.
             current_count = 0
        else:
             current_count = self._count_user_simulations(user_id)
        
        usage_info = {
            'current': current_count,
            'limit': limit,
            'tier': tier_id,
            'tier_name': tier_config.name,
            'unlimited': tier_config.is_unlimited,
        }
        
        if user_id is None and limit == 0:
             return (
                False,
                "⚠️ Please log in to create simulations",
                usage_info
            )
        
        if tier_config.is_unlimited:
            return True, f"✅ {current_count} simulations created", usage_info
        
        if current_count >= limit:
            message = (
                f"🚫 {tier_config.name} tier limit reached ({current_count}/{limit} simulations). "
                f"Delete old simulations or contact admin for tier upgrade."
            )
            return False, message, usage_info
        
        message = f"📊 {current_count}/{limit} simulations used"
        return True, message, usage_info
    
    def check_strategy_limit(self, user_id: Optional[int]) -> Tuple[bool, str, dict]:
        """
        Check if user can create a new custom strategy.
        
        Returns:
            (allowed: bool, message: str, usage_info: dict)
        """
        if user_id is None:
             tier_config = TIERS['ANONYMOUS']
             usage_info = {
                'current': 0, 'limit': 0, 'tier': 'ANONYMOUS', 
                'tier_name': tier_config.name, 'unlimited': False
             }
             return (
                False,
                "⚠️ Please log in to create strategies",
                usage_info
            )
        
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        limit = tier_config.max_strategies
        current_count = self._count_user_strategies(user_id)
        
        usage_info = {
            'current': current_count,
            'limit': limit,
            'tier': tier_id,
            'tier_name': tier_config.name,
            'unlimited': tier_config.is_unlimited,
        }
        
        if tier_config.is_unlimited:
            return True, f"✅ {current_count} strategies created", usage_info
        
        if current_count >= limit:
            message = (
                f"🚫 {tier_config.name} tier limit reached ({current_count}/{limit} strategies). "
                f"Delete old strategies or contact admin for tier upgrade."
            )
            return False, message, usage_info
        
        message = f"🧠 {current_count}/{limit} strategies used"
        return True, message, usage_info
    
    def check_feature_access(self, user_id: Optional[int], feature_name: str) -> bool:
        """Check if user has access to a specific feature."""
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        
        # Check if feature exists in TierFeatures dataclass
        if hasattr(tier_config.features, feature_name):
            return getattr(tier_config.features, feature_name)
        
        # Fallback/Edge case: 'ai_analysis' isn't in TierFeatures but used in logic?
        # If the code asks for a feature not in the model, default to False.
        # Note: 'ai_analysis' logic was historically boolean, but new config uses credits.
        # If UI checks 'ai_analysis', we might need to Map it.
        if feature_name == 'ai_analysis':
             return tier_config.ai_generation_credits_monthly > 0
             
        return False
    
    def get_tier_badge(self, user_id: Optional[int]) -> str:
        """Get emoji badge for user's tier (for UI display)"""
        if user_id is None:
            return TIERS['ANONYMOUS'].badge
        tier_id = self.get_user_tier(user_id)
        return self.get_tier_config(tier_id).badge
    
    def get_tier_display_name(self, user_id: Optional[int]) -> str:
        """Get human-readable tier name"""
        if user_id is None:
            return TIERS['ANONYMOUS'].name
        tier_id = self.get_user_tier(user_id)
        return self.get_tier_config(tier_id).name
    
    def get_tier_color(self, user_id: int) -> str:
        """Get color code for user's tier"""
        tier_id = self.get_user_tier(user_id)
        return self.get_tier_config(tier_id).color
    
    def get_mc_iterations_limit(self, user_id: int, is_custom_strategy: bool = False) -> int:
        """Get Monte Carlo iteration limit."""
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        
        if is_custom_strategy:
            return tier_config.max_mc_iterations_custom
        else:
            return tier_config.max_mc_iterations_builtin
    
    def check_ai_credits(self, user_id: int) -> Tuple[bool, str, dict]:
        """Check if user has AI generation credits remaining."""
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        monthly_limit = tier_config.ai_generation_credits_monthly
        
        # Get current month
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        
        # Get usage for current month
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            query = "SELECT credits_used FROM AI_CREDIT_USAGE WHERE user_id = %s AND month = %s"
            # Auto-detect SQLite vs PostgreSQL placeholder is tricky here without DB wrapper helper
            # But the db object handles connection/cursor wrapping in new PostgreSQL code
            # Wait, db.get_connection() returns PostgreSQLConnection which returns PostgreSQLCursor
            # PostgreSQLCursor handles ? -> %s conversion!
            # So I can use ? safely if the DB is wrapped!
            
            # Using ? for compatibility with the wrapper's fallback
            if hasattr(self.db, 'dialect') and self.db.dialect.__class__.__name__ == 'PostgreSQLDialect':
                 # Wrapper handles ? -> %s
                 cursor.execute("SELECT credits_used FROM AI_CREDIT_USAGE WHERE user_id = ? AND month = ?", (user_id, current_month))
            else:
                 cursor.execute("SELECT credits_used FROM AI_CREDIT_USAGE WHERE user_id = ? AND month = ?", (user_id, current_month))
                 
            row = cursor.fetchone()
            credits_used = row[0] if row else 0
        except Exception as e:
            logger.error(f"Error checking AI credits: {e}")
            credits_used = 0
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)
        
        usage_info = {
            'current': credits_used,
            'limit': monthly_limit,
            'month': current_month,
            'tier': tier_id,
            'unlimited': monthly_limit >= 999999,
        }
        
        if monthly_limit >= 999999:
            return True, f"✅ {credits_used} AI generations this month", usage_info
        
        if credits_used >= monthly_limit:
            message = f"🚫 Monthly AI limit reached ({credits_used}/{monthly_limit}). Resets next month."
            return False, message, usage_info
        
        message = f"🤖 {credits_used}/{monthly_limit} AI credits used this month"
        return True, message, usage_info
    
    def increment_ai_credits(self, user_id: int) -> None:
        """Increment AI credit usage for current month"""
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Insert or update
            # Using ? placeholders as they are supported by both SQLite (natively) 
            # and our PostgreSQL wrapper (via auto-conversion)
            cursor.execute("""
                INSERT INTO AI_CREDIT_USAGE (user_id, month, credits_used)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, month)
                DO UPDATE SET 
                    credits_used = AI_CREDIT_USAGE.credits_used + 1,
                    last_updated = CURRENT_TIMESTAMP
            """, (user_id, current_month))
            conn.commit()
            
            logger.info(f"Incremented AI credits for user {user_id} in {current_month}")
        except Exception as e:
            logger.error(f"Error incrementing AI credits: {e}")
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)
    
    def get_retention_days(self, user_id: int) -> Optional[int]:
        """Get simulation retention period in days."""
        tier_id = self.get_user_tier(user_id)
        tier_config = self.get_tier_config(tier_id)
        return tier_config.simulation_retention_days
    
    def clear_cache(self):
        """No-op: Config is static now."""
        pass
    
    # --- Private helper methods ---
    
    def _get_user(self, user_id: int) -> Optional[dict]:
        """Fetch user record from database"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM USERS WHERE id = ?", (user_id,))
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)
    
    def _count_user_simulations(self, user_id: int) -> int:
        """Count active (non-removed) simulations for user"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            # Changed FALSE to 0/False handling? 
            # SQLite uses 0/1 for boolean. PostgreSQL uses TRUE/FALSE.
            # Our PostgreSQL wrapper might not auto-convert boolean literals in SQL string!
            # Safest is to use parameter binding for the boolean value.
            cursor.execute("""
                SELECT COUNT(*) 
                FROM USER_SIMULATION_HISTORY 
                WHERE user_id = ? AND is_removed = ?
            """, (user_id, False))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting simulations for user {user_id}: {e}")
            return 0
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)
    
    def _count_user_strategies(self, user_id: int) -> int:
        """Count custom strategies for user (excluding soft-deleted)"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) 
                FROM CUSTOM_STRATEGIES 
                WHERE user_id = ?
                AND deleted_at IS NULL
            """, (user_id,))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting strategies for user {user_id}: {e}")
            return 0
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)
