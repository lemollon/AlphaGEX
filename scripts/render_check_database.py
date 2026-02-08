#!/usr/bin/env python3
"""
Render Shell Script: Check Database Connection and Tables

Run in Render shell:
    python scripts/render_check_database.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def info(msg): print(f"[INFO] {msg}")

print("=" * 60)
print("CHECKING DATABASE CONNECTION")
print("=" * 60)

# Check DATABASE_URL
db_url = os.getenv("DATABASE_URL")
if not db_url:
    fail("DATABASE_URL not set!")
    sys.exit(1)

# Mask password in URL for display
masked_url = db_url
if "@" in db_url:
    parts = db_url.split("@")
    before = parts[0]
    if ":" in before:
        user_pass = before.split("//")[-1]
        if ":" in user_pass:
            masked_url = db_url.replace(user_pass.split(":")[1], "****")
info(f"DATABASE_URL: {masked_url[:50]}...")

print("\n-- Connecting to Database --")

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Get version
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    ok(f"Connected to PostgreSQL")
    info(f"Version: {version[:70]}")

    # Check tables
    print("\n-- Checking Tables --")
    required_tables = [
        "fortress_positions",
        "solomon_positions",
        "autonomous_config",
        "bot_heartbeats",
        "bot_scan_activity",
    ]

    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
    """)
    existing_tables = [row[0] for row in cursor.fetchall()]

    for table in required_tables:
        if table in existing_tables:
            # Count rows
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            ok(f"{table}: {count} rows")
        else:
            fail(f"{table}: NOT FOUND")

    # Check for fresh start (0 trades)
    print("\n-- Fresh Start Status --")
    cursor.execute("SELECT COUNT(*) FROM fortress_positions WHERE status = 'closed'")
    fortress_closed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fortress_positions WHERE status = 'open'")
    fortress_open = cursor.fetchone()[0]

    info(f"FORTRESS: {fortress_open} open, {fortress_closed} closed")

    if fortress_closed == 0 and fortress_open == 0:
        ok("FORTRESS is in fresh start state (0 trades)")
    else:
        info(f"FORTRESS has trade history")

    conn.close()
    print("\n" + "=" * 60)
    print("DATABASE CHECK PASSED")
    sys.exit(0)

except Exception as e:
    fail(f"Database error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
