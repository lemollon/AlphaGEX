#!/usr/bin/env python3
"""Diagnose why get_trading_days returns 0 despite data existing in ORAT DB."""

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

print("=== ORAT QUERY DIAGNOSTIC ===\n")

# Test 1: Column type
print("--- Test 1: Column types ---")
cur.execute("""
    SELECT column_name, data_type, udt_name
    FROM information_schema.columns
    WHERE table_name = 'orat_options_eod'
      AND column_name IN ('trade_date', 'ticker', 'expiration_date', 'underlying_price')
    ORDER BY ordinal_position;
""")
for row in cur.fetchall():
    print(f"  {row[0]:25s} {row[1]:20s} ({row[2]})")

# Test 2: Sample raw data
print("\n--- Test 2: Sample raw data (5 rows) ---")
cur.execute("SELECT trade_date, ticker FROM orat_options_eod LIMIT 5")
for row in cur.fetchall():
    print(f"  trade_date={row[0]} (type={type(row[0]).__name__}), ticker={repr(row[1])}")

# Test 3: Simple equality with string date
print("\n--- Test 3: Simple ticker = 'SPY' with string dates ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = 'SPY'
      AND trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'
""")
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 4: Same but with parameterized strings
print("\n--- Test 4: Parameterized string dates ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = %s
      AND trade_date >= %s AND trade_date <= %s
""", ('SPY', '2021-01-01', '2021-03-31'))
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 5: Parameterized with date objects
print("\n--- Test 5: Parameterized date objects ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = %s
      AND trade_date >= %s AND trade_date <= %s
""", ('SPY', date(2021, 1, 1), date(2021, 3, 31)))
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 6: ANY with list
print("\n--- Test 6: ticker = ANY(%s) with list ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = ANY(%s)
      AND trade_date >= %s AND trade_date <= %s
""", (['SPY'], '2021-01-01', '2021-03-31'))
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 7: IN instead of ANY
print("\n--- Test 7: ticker IN %s with tuple ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker IN %s
      AND trade_date >= %s AND trade_date <= %s
""", (('SPY',), '2021-01-01', '2021-03-31'))
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 8: ANY with SPX list
print("\n--- Test 8: ticker = ANY(['SPX', 'SPXW']) ---")
cur.execute("""
    SELECT COUNT(DISTINCT trade_date)
    FROM orat_options_eod
    WHERE ticker = ANY(%s)
      AND trade_date >= %s AND trade_date <= %s
""", (['SPX', 'SPXW'], '2021-01-01', '2021-03-31'))
print(f"  COUNT(DISTINCT trade_date): {cur.fetchone()[0]}")

# Test 9: Check a specific known date
print("\n--- Test 9: Specific known date ---")
cur.execute("""
    SELECT COUNT(*)
    FROM orat_options_eod
    WHERE ticker = 'SPY' AND trade_date = '2021-01-04'
""")
print(f"  Rows for SPY on 2021-01-04: {cur.fetchone()[0]}")

cur.execute("""
    SELECT COUNT(*)
    FROM orat_options_eod
    WHERE ticker = 'SPX' AND trade_date = '2021-01-04'
""")
print(f"  Rows for SPX on 2021-01-04: {cur.fetchone()[0]}")

# Test 10: Check actual date range for each ticker
print("\n--- Test 10: Actual date boundaries ---")
for t in ['SPY', 'SPX', 'VIX']:
    cur.execute("""
        SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s
    """, (t,))
    row = cur.fetchone()
    print(f"  {t}: {row[0]} → {row[1]} ({row[2]} days)")

conn.close()
print("\n=== DONE ===")
