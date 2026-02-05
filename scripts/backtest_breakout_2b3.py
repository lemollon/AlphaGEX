#!/usr/bin/env python3
"""
Part 2b-3: Compare breakout to actual directional

Run on Render shell:
python3 scripts/backtest_breakout_2b3.py
"""

import os
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("PART 2b-3: COMPARISON")
print("=" * 40)

# Get actual directional results
cursor.execute("""
    SELECT
        SUM(realized_pnl) as pnl,
        COUNT(*) as trades,
        COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) as wins
    FROM heracles_scan_activity
    WHERE trade_executed = TRUE
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
""")
row = cursor.fetchone()
actual_pnl = float(row[0]) if row[0] else 0
actual_trades = row[1] or 0
actual_wins = row[2] or 0

print(f"\nACTUAL DIRECTIONAL (9-11am NEG):")
print(f"  Trades: {actual_trades}")
if actual_trades > 0:
    print(f"  Win Rate: {actual_wins/actual_trades*100:.0f}%")
print(f"  Total P&L: ${actual_pnl:,.2f}")

# Note: Copy breakout P&L from 2b-2
print("\n" + "-" * 40)
print("Enter breakout P&L from Part 2b-2:")
print("(or run all parts together)")

# Show all window trades for context
cursor.execute("""
    SELECT
        DATE(scan_time) as dt,
        signal_direction,
        trade_outcome,
        realized_pnl
    FROM heracles_scan_activity
    WHERE trade_executed = TRUE
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
    ORDER BY scan_time DESC
    LIMIT 15
""")
print("\nRecent actual trades:")
print(f"{'DATE':<12} {'DIR':<6} {'RESULT':<6} {'P&L':>10}")
for row in cursor.fetchall():
    dt, dir, res, pnl = row
    pnl_str = f"${pnl:.2f}" if pnl else "$0.00"
    print(f"{str(dt):<12} {dir or 'N/A':<6} {res or 'N/A':<6} {pnl_str:>10}")

cursor.close()
conn.close()
print("\nPart 2b-3 done.")
