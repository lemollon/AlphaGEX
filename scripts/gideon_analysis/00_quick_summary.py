#!/usr/bin/env python3
"""
GIDEON Analysis 00: Quick Summary
=================================
Executive summary of key metrics - run this first!

Run: python scripts/icarus_analysis/00_quick_summary.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database_adapter import get_connection

def query(sql):
    conn = get_connection()
    c = conn.cursor()
    c.execute(sql)
    results = c.fetchall()
    conn.close()
    return results

print("\n" + "="*70)
print(" GIDEON QUICK SUMMARY")
print("="*70)

# Overall
r = query("""
    SELECT
        COUNT(*),
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END),
        ROUND(SUM(realized_pnl)::numeric, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
""")
total, wins, pnl = r[0] if r else (0, 0, 0)
win_rate = (wins / total * 100) if total > 0 else 0

print(f"""
OVERALL:
  Trades: {total}
  Wins: {wins} ({win_rate:.1f}%)
  Total P&L: ${pnl:,.2f}
  Avg P&L/Trade: ${(pnl/total) if total > 0 else 0:,.2f}
""")

# Before vs After Fix
FIX_DATE = '2026-02-01'
r_before = query(f"""
    SELECT COUNT(*), SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), ROUND(SUM(realized_pnl)::numeric, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time < '{FIX_DATE}'
""")
r_after = query(f"""
    SELECT COUNT(*), SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), ROUND(SUM(realized_pnl)::numeric, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time >= '{FIX_DATE}'
""")
before = r_before[0] if r_before else (0, 0, 0)
after = r_after[0] if r_after else (0, 0, 0)

print(f"""BEFORE vs AFTER FIX ({FIX_DATE}):
  BEFORE: {before[0]} trades, {(before[1]/before[0]*100) if before[0] > 0 else 0:.1f}% WR, ${before[2] or 0:,.2f}
  AFTER:  {after[0]} trades, {(after[1]/after[0]*100) if after[0] > 0 else 0:.1f}% WR, ${after[2] or 0:,.2f}
""")

# By Spread Type
r = query("""
    SELECT spread_type,
        COUNT(*),
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 1),
        ROUND(SUM(realized_pnl)::numeric, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY spread_type ORDER BY spread_type
""")
print("BY SPREAD TYPE:")
for row in r:
    print(f"  {row[0]}: {row[1]} trades, {row[2]}% WR, ${row[3]:,.2f}")

# By Close Reason (key insight)
r = query("""
    SELECT close_reason, COUNT(*), ROUND(SUM(realized_pnl)::numeric, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY close_reason ORDER BY COUNT(*) DESC LIMIT 5
""")
print("\nBY CLOSE REASON (Top 5):")
for row in r:
    label = "OLD" if "60%" in str(row[0]) else ("NEW" if "50%" in str(row[0]) else "")
    print(f"  {row[0]}: {row[1]} trades, ${row[2]:,.2f} {label}")

# Oracle Confidence Check
r = query("""
    SELECT
        SUM(CASE WHEN oracle_confidence > 1 THEN 1 ELSE 0 END) as bad,
        ROUND(AVG(oracle_confidence)::numeric, 3) as avg
    FROM gideon_positions WHERE status = 'closed' AND oracle_confidence IS NOT NULL
""")
if r and r[0]:
    bad, avg = r[0]
    print(f"\nORACLE CONFIDENCE:")
    print(f"  Avg: {avg} {'✅ Good scale' if avg <= 1 else '⚠️ Bad scale!'}")
    print(f"  Bad (>1.0): {bad} trades {'⚠️ SCALE BUG' if bad > 0 else '✅ None'}")

# Key Recommendations
print(f"""
KEY QUESTIONS TO INVESTIGATE:
  1. Are post-fix trades ({after[0]}) performing better than pre-fix?
  2. Is BEAR_PUT still catastrophically bad?
  3. Are trades near flip point winning more?
  4. Is Friday filter reducing losses?
  5. Is Oracle confidence correlating with win rate?

Run the full analysis:
  python scripts/icarus_analysis/run_all.py
""")

print("="*70 + "\n")
