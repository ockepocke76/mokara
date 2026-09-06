import yaml
import os

from .queries import PostgreSQLQueries

def get_database(dialect=None):
    """
    Factory function to get the database implementation based on the config.
    Environment variables take precedence over config.yml for PostgreSQL.
    """
    db_config = {}
    if dialect is None:
        with open("config.yml", "r") as f:
            config = yaml.safe_load(f)
        
        db_config = config.get("database", {})
        if not db_config:
            raise ValueError("Database configuration not found in config.yml")
            
        dialect = db_config.get("dialect", "postgresql")
    
    # Override with environment variables if present (for cloud migration)
    if dialect == "postgresql" or db_config.get("dialect") == "postgresql":
        # Check if POSTGRES_HOST is explicitly set (from launch.json or .env.cloud)
        postgres_host_env = os.getenv('POSTGRES_HOST')
        
        if postgres_host_env:
            # Environment variables are set - use them (could be Cloud Run or local with explicit config)
            db_config = {
                'host': postgres_host_env,
                'port': int(os.getenv('POSTGRES_PORT', 5432)),
                'database': os.getenv('POSTGRES_DB', 'btc_simulator'),
                'user': os.getenv('POSTGRES_USER', 'postgres'),
                'password': os.getenv('POSTGRES_PASSWORD', ''),
                'sslmode': os.getenv('POSTGRES_SSLMODE', 'prefer')
            }
        else:
            # No env vars - auto-detect based on Cloud Run
            is_cloud_run = os.getenv('K_SERVICE') is not None
            
            if is_cloud_run:
                # Shouldn't happen, but just in case
                raise ValueError("Cloud Run detected but POSTGRES_HOST not set")
            else:
                # Local development: Use localhost PostgreSQL
                db_config = {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'btc_simulator_local',
                    'user': os.getenv('USER', 'postgres'),  # Current system user
                    'password': '',  # No password for local dev
                    'sslmode': 'prefer'
                }

    queries = get_queries(dialect)

    if dialect == "postgresql":
        from .postgresql_db import PostgreSQLDatabase
        # For PostgreSQL, pass the entire db_config for connection details
        return PostgreSQLDatabase(queries, db_config)
    else:
        raise ValueError(f"Unsupported database dialect: {dialect} (only postgresql is supported)")

def get_queries(dialect):
    if dialect == "postgresql":
        return PostgreSQLQueries()
    else:
        raise ValueError(f"Unsupported database dialect: {dialect} (only postgresql is supported)")
