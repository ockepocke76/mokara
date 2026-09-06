#!/usr/bin/env python3
"""Force database migrations to run."""
import sys
sys.path.insert(0, '/Users/oscarsverud/dev/btc_sim')

from db.database import db

print("Running database migrations...")
db.run_migrations()
print("✅ Migrations complete!")

# Verify tables were created
# Verify tables were created
conn = db.get_connection()
try:
    cursor = conn.cursor()

    # Use dialect-specific query to list tables
    from db.postgresql_db import PostgreSQLDialect
    if hasattr(db, 'dialect') and isinstance(db.dialect, PostgreSQLDialect):
        # PostgreSQL: Query information_schema
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
    else:
        # SQLite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")

    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n✅ Created {len(tables)} tables:")
    for table in tables:
        print(f"  - {table}")
finally:
    db.release_connection(conn)
