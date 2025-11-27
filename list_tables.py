#!/usr/bin/env python3
"""
List all tables in the PostgreSQL database
"""
from database_adapter import get_connection

conn = get_connection()
c = conn.cursor()

# Get all tables from PostgreSQL
c.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
tables = [row[0] for row in c.fetchall()]

print("EXISTING TABLES:")
print("=" * 60)
for table in tables:
    print(f"  {table}")
print("=" * 60)
print(f"Total: {len(tables)} tables")

# Check if regime_signals exists
if 'regime_signals' in tables:
    print("\n✅ regime_signals table EXISTS")
else:
    print("\n❌ regime_signals table MISSING - this is the problem!")

conn.close()
