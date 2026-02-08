#!/usr/bin/env python3
"""
Render Shell Script: Run Database Migrations

Run in Render shell:
    python scripts/render_run_migrations.py          # Dry run (show what would happen)
    python scripts/render_run_migrations.py --apply  # Actually run migrations

This runs:
- Migration 013: FORTRESS extended columns + fresh start
- Migration 014: All bots fresh start
"""

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def warn(msg): print(f"[WARN] {msg}")
def info(msg): print(f"[INFO] {msg}")

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true", help="Actually run migrations")
args = parser.parse_args()

print("=" * 60)
print("DATABASE MIGRATIONS")
print("=" * 60)

if not args.apply:
    warn("DRY RUN MODE - No changes will be made")
    warn("Run with --apply to actually execute migrations")
    print()

# Migrations to run
migrations = [
    ("013_ares_extended_columns.sql", "FORTRESS extended columns + fresh start"),
    ("014_all_bots_fresh_start.sql", "All bots fresh start reset"),
]

migrations_dir = os.path.join(PROJECT_ROOT, "db", "migrations")

# Check migrations exist
print("-- Checking Migration Files --")
for filename, description in migrations:
    path = os.path.join(migrations_dir, filename)
    if os.path.exists(path):
        size = os.path.getsize(path)
        ok(f"{filename} ({size} bytes)")
    else:
        fail(f"{filename} NOT FOUND")
        sys.exit(1)

if not args.apply:
    print("\n-- Migration Contents (Preview) --")
    for filename, description in migrations:
        path = os.path.join(migrations_dir, filename)
        print(f"\n{filename}:")
        with open(path, 'r') as f:
            lines = f.readlines()
            # Show first 20 lines
            for line in lines[:20]:
                print(f"  {line.rstrip()}")
            if len(lines) > 20:
                print(f"  ... ({len(lines) - 20} more lines)")

    print("\n" + "=" * 60)
    print("DRY RUN COMPLETE")
    print("Run with --apply to execute these migrations")
    sys.exit(0)

# Actually run migrations
print("\n-- Connecting to Database --")
try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    ok("Connected to database")
except Exception as e:
    fail(f"Database connection failed: {e}")
    sys.exit(1)

print("\n-- Running Migrations --")
for filename, description in migrations:
    path = os.path.join(migrations_dir, filename)
    info(f"Running {filename}...")

    try:
        with open(path, 'r') as f:
            sql = f.read()

        cursor.execute(sql)
        conn.commit()
        ok(f"{filename}: {description}")

    except Exception as e:
        fail(f"{filename} failed: {e}")
        conn.rollback()
        # Continue with next migration

# Verify fresh start
print("\n-- Verifying Fresh Start --")
try:
    cursor.execute("SELECT COUNT(*) FROM fortress_positions")
    ares_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM solomon_positions")
    solomon_count = cursor.fetchone()[0]

    if ares_count == 0:
        ok(f"FORTRESS: 0 positions (fresh start)")
    else:
        warn(f"FORTRESS: {ares_count} positions remain")

    if solomon_count == 0:
        ok(f"SOLOMON: 0 positions (fresh start)")
    else:
        warn(f"SOLOMON: {solomon_count} positions remain")

except Exception as e:
    warn(f"Verification query failed: {e}")

conn.close()

print("\n" + "=" * 60)
print("MIGRATIONS COMPLETE")
sys.exit(0)
