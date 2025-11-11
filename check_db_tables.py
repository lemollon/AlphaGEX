#!/usr/bin/env python3
"""
Check what tables exist in the database
"""
import sqlite3
from config_and_database import DB_PATH

print("=" * 80)
print("DATABASE TABLES CHECK")
print("=" * 80)
print(f"Database: {DB_PATH}")
print()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()

print(f"Found {len(tables)} tables:\n")
for table in tables:
    table_name = table[0]
    print(f"  📊 {table_name}")

    # Count rows
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"     └─ {count} rows")

    # Show schema for autonomous tables
    if 'autonomous' in table_name:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"     └─ Columns: {', '.join([col[1] for col in columns])}")

    print()

conn.close()

print("=" * 80)
print("\n💡 If 'autonomous_positions' is missing, the autonomous trader")
print("   needs to be initialized by creating an instance:")
print("   from autonomous_paper_trader import AutonomousPaperTrader")
print("   trader = AutonomousPaperTrader()")
print()
