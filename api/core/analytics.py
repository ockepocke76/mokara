import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Singleton service for tracking user behavior and system events.
    Writes to ANALYTICS_EVENTS table.
    """
    
    def __init__(self, db):
        self.db = db
        
    def track(self, event_type: str, user_id: Optional[int] = None, properties: Dict[str, Any] = None):
        """
        Track a discrete event.
        
        Args:
            event_type (str): Key identifying the event (e.g., 'simulation_run')
            user_id (int, optional): ID of the user triggering the event
            properties (dict): Arbitrary payload of metadata
        """
        if properties is None:
            properties = {}
            
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Detect DB type for JSON handling
            # SQLite stores JSON as TEXT, PostgreSQL as JSONB
            # Our PostgreSQL wrapper might not auto-convert dict to JSONB string automatically in all cases,
            # but psycopg2.extras.Json usually handles it.
            # However, for maximum compatibility across both:
            # - SQLite: Needs string
            # - Postgres: Can take string or dict (if adapter set)
            # Safest approach: Dump to string if SQLite.
            
            # Simple heuristic: Check if 'sqlite' is in db class name or connection
            is_sqlite = 'sqlite' in str(type(self.db)).lower()
            
            payload = json.dumps(properties) if is_sqlite else json.dumps(properties) 
            # Actually, standard psycopg2 requires json.dumps for JSONB unless Json adapter is used.
            # Let's standardize on string for now, PG casts string to JSONB automatically.
            
            # Using ? placeholder which works for our SQLite and wrapped PG
            sql = """
                INSERT INTO ANALYTICS_EVENTS (user_id, event_type, properties)
                VALUES (?, ?, ?)
            """
            
            cursor.execute(sql, (user_id, event_type, payload))
            conn.commit()
            
            logger.debug(f"Analytics tracked: {event_type} (User: {user_id})")
            
        except Exception as e:
            # Analytics should never break the app
            logger.error(f"Failed to track analytics event '{event_type}': {e}")
        finally:
            if 'conn' in locals():
                self.db.release_connection(conn)

    # --- Standardized Event Helpers ---

    def track_simulation_run(self, user_id: Optional[int], asset: str, strategy: str, duration: int, timestamp: datetime):
        self.track('simulation_run', user_id, {
            'asset_model': asset,
            'strategy_name': strategy,
            'duration_years': duration,
            'timestamp': timestamp.isoformat()
        })
        
    def track_ai_usage(self, user_id: Optional[int], operation: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.track('ai_usage', user_id, {
            'operation_type': operation, # 'simulation_analysis', 'strategy_design', 'chat'
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens
        })
        
    def track_login(self, user_id: int, method: str):
        self.track('user_login', user_id, {
            'method': method, # 'google', 'email', 'cookie'
            'ip_address': 'masked' # We don't track IP yet
        })
