#!/usr/bin/env python3
"""Diagnose corrupted index on orat_options_eod.

Round 2 showed: date filter alone returns 14M rows, ticker alone returns 1239 days,
but combining them returns 0. EXPLAIN shows idx_orat_options_date_ticker is used.
This suggests a corrupted B-tree index.

This script:
1. Forces sequential scan (bypasses all indexes) to confirm data exists
2. If confirmed, attempts REINDEX to fix the corrupted index
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

# Need a writable connection for REINDEX
conn = psycopg2.connect(ORAT_URL, connect_timeout=30)
conn.autocommit = True  # REINDEX requires autocommit
cur = conn.cursor()

print("=== INDEX CORRUPTION DIAGNOSTIC ===\n")

# Test 1: Force sequential scan — bypass ALL indexes
print("--- Test 1: Sequential scan (indexes disabled) ---")
cur.execute("SET enable_indexscan = off")
cur.execute("SET enable_bitmapscan = off")
cur.execute("SET enable_indexonlyscan = off")

cur.execute("""
    SELECT COUNT(*)
    FROM orat_options_eod
    WHERE ticker = 'SPY' AND trade_date = '2021-01-04'
""")
seqscan_count = cur.fetchone()[0]
print(f"  SeqScan: WHERE ticker='SPY' AND trade_date='2021-01-04' → {seqscan_count} rows")

cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = 'SPY'
      AND trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'
""")
seqscan_days = cur.fetchone()[0]
print(f"  SeqScan: SPY trading days in Q1 2021 → {seqscan_days} days")

cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = 'SPX'
      AND trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'
""")
seqscan_spx = cur.fetchone()[0]
print(f"  SeqScan: SPX trading days in Q1 2021 → {seqscan_spx} days")

# Re-enable indexes
cur.execute("RESET enable_indexscan")
cur.execute("RESET enable_bitmapscan")
cur.execute("RESET enable_indexonlyscan")

# Test 2: Index scan (normal) — same query
print("\n--- Test 2: Index scan (normal mode) — same query ---")
cur.execute("""
    SELECT COUNT(*)
    FROM orat_options_eod
    WHERE ticker = 'SPY' AND trade_date = '2021-01-04'
""")
idxscan_count = cur.fetchone()[0]
print(f"  IndexScan: WHERE ticker='SPY' AND trade_date='2021-01-04' → {idxscan_count} rows")

# Diagnosis
print(f"\n--- DIAGNOSIS ---")
if seqscan_count > 0 and idxscan_count == 0:
    print("  ⚠️  CONFIRMED: INDEX IS CORRUPTED")
    print(f"  Sequential scan found {seqscan_count} rows, index scan found 0")
    print("  The B-tree index idx_orat_options_date_ticker has stale/corrupt pages")

    print("\n--- Attempting REINDEX ---")
    indexes_to_fix = [
        'idx_orat_options_date_ticker',
        'idx_orat_options_date',
        'idx_orat_options_0dte',
        'idx_orat_options_ticker',
    ]
    for idx_name in indexes_to_fix:
        try:
            print(f"  REINDEX {idx_name}...", end=" ", flush=True)
            cur.execute(f"REINDEX INDEX {idx_name}")
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            conn.rollback()

    # Verify fix
    print("\n--- Verifying fix ---")
    cur.execute("""
        SELECT COUNT(*)
        FROM orat_options_eod
        WHERE ticker = 'SPY' AND trade_date = '2021-01-04'
    """)
    fixed_count = cur.fetchone()[0]
    print(f"  Post-REINDEX: WHERE ticker='SPY' AND trade_date='2021-01-04' → {fixed_count} rows")

    if fixed_count > 0:
        print("  ✅ INDEX FIXED! Queries should work now.")

        # Run the full test
        cur.execute("""
            SELECT COUNT(DISTINCT trade_date)
            FROM orat_options_eod
            WHERE ticker = 'SPY'
              AND trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'
        """)
        print(f"  SPY trading days Q1 2021: {cur.fetchone()[0]}")

        cur.execute("""
            SELECT COUNT(DISTINCT trade_date)
            FROM orat_options_eod
            WHERE ticker = 'SPX'
              AND trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'
        """)
        print(f"  SPX trading days Q1 2021: {cur.fetchone()[0]}")
    else:
        print("  ❌ REINDEX did not fix the issue. May need REINDEX TABLE.")
        print("  Try running: REINDEX TABLE orat_options_eod;")

elif seqscan_count == 0 and idxscan_count == 0:
    print("  ❌ BOTH seq scan and index scan return 0.")
    print("  The data genuinely doesn't exist for this ticker+date combo.")
    print("  This is NOT an index corruption issue.")

    # Check what's actually there
    print("\n  Let's check what's actually stored...")
    cur.execute("SET enable_indexscan = off")
    cur.execute("SET enable_bitmapscan = off")
    cur.execute("SET enable_indexonlyscan = off")

    cur.execute("""
        SELECT ticker, trade_date, COUNT(*)
        FROM orat_options_eod
        WHERE trade_date = '2021-01-04'
        GROUP BY ticker, trade_date
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"    ticker={r[0]}, trade_date={r[1]}, count={r[2]}")
    else:
        print("    No data at all for 2021-01-04!")

        # Check nearest dates
        cur.execute("""
            SELECT DISTINCT trade_date FROM orat_options_eod
            WHERE trade_date >= '2020-12-28' AND trade_date <= '2021-01-08'
            ORDER BY trade_date
        """)
        dates = [r[0] for r in cur.fetchall()]
        print(f"    Dates near 2021-01-04: {dates}")

    cur.execute("RESET enable_indexscan")
    cur.execute("RESET enable_bitmapscan")
    cur.execute("RESET enable_indexonlyscan")

elif seqscan_count > 0 and idxscan_count > 0:
    print("  ✅ Both scans return data. Index appears healthy.")
    print(f"  SeqScan: {seqscan_count}, IndexScan: {idxscan_count}")
    print("  The original issue may have been transient or connection-related.")

conn.close()
print("\n=== DONE ===")
