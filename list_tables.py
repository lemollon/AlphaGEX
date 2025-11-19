#!/usr/bin/env python3
import sqlite3
from config_and_database import DB_PATH

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
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
