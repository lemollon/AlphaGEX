#!/usr/bin/env python3
"""
Initialize AlphaGEX Database
Creates all required tables for the system
"""
import sys
from config_and_database import init_database, DB_PATH
from autonomous_paper_trader import AutonomousPaperTrader

print("=" * 80)
print("INITIALIZING ALPHAGEX DATABASE")
print("=" * 80)
print(f"Database: {DB_PATH}")
print()

# Step 1: Initialize main database schema
print("Step 1: Creating main database schema...")
try:
    init_database()
    print("✅ Main database schema created successfully")
except Exception as e:
    print(f"❌ Error creating main schema: {e}")
    sys.exit(1)

# Step 2: Initialize autonomous trader tables
print("\nStep 2: Creating autonomous trader tables...")
try:
    trader = AutonomousPaperTrader()
    print("✅ Autonomous trader initialized successfully")
    print(f"   Starting capital: ${trader.starting_capital}")
except Exception as e:
    print(f"❌ Error initializing autonomous trader: {e}")
    sys.exit(1)

# Step 3: Verify tables exist
print("\nStep 3: Verifying tables...")
import sqlite3
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()
conn.close()

print(f"✅ Found {len(tables)} tables:")
for table in tables:
    print(f"   • {table[0]}")

print("\n" + "=" * 80)
print("✅ DATABASE INITIALIZATION COMPLETE!")
print("=" * 80)
print()
print("Your AlphaGEX system is now ready to use!")
print()
