#!/usr/bin/env python3
"""Diagnose why get_trading_days returns 0 despite data existing in ORAT DB.

Round 2: The MIN/MAX show data from 2020-2025 but ALL date-filtered queries
return 0. This suggests table partitioning, row-level security, or a view.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / '.env')

import psycopg2

ORAT_URL = os.getenv(
    "ORAT_DATABASE_URL",
    "postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest"
)

conn = psycopg2.connect(ORAT_URL, connect_timeout=30)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()

print("=== ORAT QUERY DIAGNOSTIC — ROUND 2 ===\n")

# Test A: Is it a table, view, or materialized view?
print("--- Test A: Table type ---")
cur.execute("""
    SELECT table_type FROM information_schema.tables
    WHERE table_name = 'orat_options_eod'
""")
rows = cur.fetchall()
for r in rows:
    print(f"  table_type: {r[0]}")
if not rows:
    print("  NOT FOUND in information_schema.tables!")

# Check pg_class for partitioning
cur.execute("""
    SELECT relkind, relispartition, relhassubclass
    FROM pg_class WHERE relname = 'orat_options_eod'
""")
row = cur.fetchone()
if row:
    kinds = {'r': 'ordinary table', 'p': 'PARTITIONED TABLE', 'v': 'view',
             'm': 'materialized view', 'f': 'foreign table'}
    print(f"  relkind: {row[0]} ({kinds.get(row[0], 'unknown')})")
    print(f"  relispartition: {row[1]}")
    print(f"  relhassubclass (has child partitions): {row[2]}")

# Test B: Check for child partitions
print("\n--- Test B: Child partitions ---")
cur.execute("""
    SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) as partition_bound
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    JOIN pg_class p ON p.oid = i.inhparent
    WHERE p.relname = 'orat_options_eod'
    ORDER BY c.relname
""")
partitions = cur.fetchall()
if partitions:
    print(f"  PARTITIONED! {len(partitions)} child partitions:")
    for p in partitions:
        print(f"    {p[0]}: {p[1]}")
else:
    print("  No child partitions found")

# Test C: Check schema
print("\n--- Test C: Schema search path ---")
cur.execute("SHOW search_path")
print(f"  search_path: {cur.fetchone()[0]}")
cur.execute("SELECT current_schema()")
print(f"  current_schema: {cur.fetchone()[0]}")
cur.execute("""
    SELECT schemaname, tablename FROM pg_tables
    WHERE tablename = 'orat_options_eod'
""")
for r in cur.fetchall():
    print(f"  Found in schema: {r[0]}.{r[1]}")

# Test D: Row-level security
print("\n--- Test D: Row-level security ---")
cur.execute("""
    SELECT relrowsecurity, relforcerowsecurity
    FROM pg_class WHERE relname = 'orat_options_eod'
""")
row = cur.fetchone()
if row:
    print(f"  RLS enabled: {row[0]}")
    print(f"  RLS forced: {row[1]}")

# Test E: Get the FIRST 10 actual trade_dates (no filter)
print("\n--- Test E: First 10 trade_dates (unfiltered, ordered) ---")
cur.execute("""
    SELECT DISTINCT trade_date FROM orat_options_eod
    ORDER BY trade_date LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]} (type={type(r[0]).__name__})")

# Test F: Last 10 trade_dates
print("\n--- Test F: Last 10 trade_dates ---")
cur.execute("""
    SELECT DISTINCT trade_date FROM orat_options_eod
    ORDER BY trade_date DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Test G: Count with ONLY date filter (no ticker)
print("\n--- Test G: Date filter only (no ticker) ---")
cur.execute("SELECT COUNT(*) FROM orat_options_eod WHERE trade_date >= '2021-01-01'")
print(f"  trade_date >= '2021-01-01': {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM orat_options_eod WHERE trade_date < '2021-01-01'")
print(f"  trade_date < '2021-01-01': {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM orat_options_eod")
print(f"  Total rows (no filter): {cur.fetchone()[0]}")

# Test H: Try querying a specific partition directly (if partitioned)
if partitions:
    print(f"\n--- Test H: Query first partition directly ---")
    first_part = partitions[0][0]
    cur.execute(f"SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM {first_part}")
    row = cur.fetchone()
    print(f"  {first_part}: {row[0]} rows, {row[1]} → {row[2]}")

    if len(partitions) > 1:
        last_part = partitions[-1][0]
        cur.execute(f"SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM {last_part}")
        row = cur.fetchone()
        print(f"  {last_part}: {row[0]} rows, {row[1]} → {row[2]}")

# Test I: Check indexes
print("\n--- Test I: Indexes on orat_options_eod ---")
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'orat_options_eod'
    ORDER BY indexname
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1][:100]}")

# Test J: EXPLAIN a simple filtered query
print("\n--- Test J: EXPLAIN filtered query ---")
cur.execute("""
    EXPLAIN SELECT COUNT(*) FROM orat_options_eod
    WHERE ticker = 'SPY' AND trade_date = '2021-01-04'
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

conn.close()
print("\n=== DONE ===")
