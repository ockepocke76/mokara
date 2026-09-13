#!/usr/bin/env python3
"""Run database migrations (deploy-time / CI entry point).

A genuine migration failure raises and exits non-zero — CI and deploy
steps must fail loudly rather than continue on a half-migrated schema.
"""
from db.database import db

print("Running database migrations...")
db.run_migrations()
print("✅ Migrations complete!")

# Verify tables exist
conn = db.get_connection()
try:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n✅ {len(tables)} tables present:")
    for table in tables:
        print(f"  - {table}")
finally:
    db.release_connection(conn)
