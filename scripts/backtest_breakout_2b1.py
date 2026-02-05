#!/usr/bin/env python3
"""
Part 2b-1: Build price timeline and count entries

Run on Render shell:
python3 scripts/backtest_breakout_2b1.py
"""

import os
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("PART 2b-1: BUILD DATA")
print("=" * 40)

# Build price timeline
cursor.execute("""
    SELECT COUNT(*) FROM heracles_scan_activity
    WHERE underlying_price > 0
""")
total = cursor.fetchone()[0]
print(f"Total price points: {total}")

# Get entries count
cursor.execute("""
    SELECT COUNT(DISTINCT DATE(scan_time))
    FROM heracles_scan_activity
    WHERE underlying_price > 0
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
""")
days = cursor.fetchone()[0]
print(f"Entry days (9-11am NEGATIVE): {days}")

# Show sample entries
cursor.execute("""
    SELECT DATE(scan_time), MIN(underlying_price), MAX(underlying_price)
    FROM heracles_scan_activity
    WHERE underlying_price > 0
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
    GROUP BY DATE(scan_time)
    ORDER BY DATE(scan_time) DESC
    LIMIT 10
""")
print("\nRecent entry days:")
print(f"{'DATE':<12} {'LOW':>10} {'HIGH':>10} {'RANGE':>8}")
for row in cursor.fetchall():
    d, lo, hi = row
    print(f"{str(d):<12} {lo:>10.2f} {hi:>10.2f} {hi-lo:>8.1f}")

cursor.close()
conn.close()
print("\nPart 2b-1 done. Run 2b-2 next.")
