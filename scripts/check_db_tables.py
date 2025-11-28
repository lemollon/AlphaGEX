#!/usr/bin/env python3
"""
Check what tables exist in the database
"""
from database_adapter import get_connection

print("=" * 80)
print("DATABASE TABLES CHECK")
print("=" * 80)
print("Database: PostgreSQL via DATABASE_URL")
print()

conn = get_connection()
cursor = conn.cursor()

# Get all tables from PostgreSQL
cursor.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
tables = cursor.fetchall()

print(f"Found {len(tables)} tables:\n")
for table in tables:
    table_name = table[0]
    print(f"  {table_name}")

    # Count rows
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"     - {count} rows")

    # Show schema for autonomous tables
    if 'autonomous' in table_name:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = cursor.fetchall()
        print(f"     - Columns: {', '.join([col[0] for col in columns])}")

    print()

conn.close()

print("=" * 80)
print("\nIf 'autonomous_positions' is missing, the autonomous trader")
print("   needs to be initialized by creating an instance:")
print("   from autonomous_paper_trader import AutonomousPaperTrader")
print("   trader = AutonomousPaperTrader()")
print()
