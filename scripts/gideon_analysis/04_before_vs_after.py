#!/usr/bin/env python3
"""
GIDEON Analysis 04: Before vs After Fix Comparison
==================================================
Compare trades before and after the 2026-02-01 fixes.

Run: python scripts/gideon_analysis/04_before_vs_after.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database_adapter import get_connection

def query(sql, params=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(sql, params or ())
    results = c.fetchall()
    conn.close()
    return results

def section(title):
    print(f"\n{'='*70}\n {title}\n{'='*70}")

print("\n" + "="*70)
print(" GIDEON BEFORE VS AFTER FIX COMPARISON")
print(" Fix Date: 2026-02-01")
print("="*70)

FIX_DATE = '2026-02-01'

# 1. Overall Before vs After
section("1. OVERALL COMPARISON")
r = query(f"""
    SELECT
        CASE WHEN open_time < '{FIX_DATE}' THEN 'BEFORE Fix' ELSE 'AFTER Fix' END as period,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)::numeric, 2) as avg_loss
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Period':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'TotalP&L':>12} {'AvgP&L':>10} {'AvgWin':>9} {'AvgLoss':>9}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*10} {'-'*9} {'-'*9}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} ${row[5]:>9,.2f} ${row[6] or 0:>8,.2f} ${row[7] or 0:>8,.2f}")

# 2. By Close Reason (shows old vs new stop/profit config)
section("2. CLOSE REASON COMPARISON")
r = query(f"""
    SELECT
        CASE WHEN open_time < '{FIX_DATE}' THEN 'BEFORE' ELSE 'AFTER' END as period,
        close_reason,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1, close_reason ORDER BY 1, trades DESC
""")
print(f"\n  {'Period':<8} {'Close Reason':<25} {'Trades':>7} {'Wins':>6} {'P&L':>12}")
print(f"  {'-'*8} {'-'*25} {'-'*7} {'-'*6} {'-'*12}")
for row in r:
    print(f"  {row[0]:<8} {str(row[1])[:25]:<25} {row[2]:>7} {row[3]:>6} ${row[4]:>11,.2f}")

# 3. By Spread Type Before vs After
section("3. SPREAD TYPE BEFORE VS AFTER")
r = query(f"""
    SELECT
        CASE WHEN open_time < '{FIX_DATE}' THEN 'BEFORE' ELSE 'AFTER' END as period,
        spread_type,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1, spread_type ORDER BY 1, spread_type
""")
print(f"\n  {'Period':<8} {'Spread':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*8} {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<8} {row[1]:<12} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f}")

# 4. Prophet Confidence Before vs After
section("4. PROPHET CONFIDENCE BEFORE VS AFTER")
r = query(f"""
    SELECT
        CASE WHEN open_time < '{FIX_DATE}' THEN 'BEFORE' ELSE 'AFTER' END as period,
        ROUND(AVG(oracle_confidence)::numeric, 3) as avg_conf,
        ROUND(MIN(oracle_confidence)::numeric, 3) as min_conf,
        ROUND(MAX(oracle_confidence)::numeric, 3) as max_conf,
        SUM(CASE WHEN oracle_confidence > 1 THEN 1 ELSE 0 END) as bad_scale
    FROM gideon_positions
    WHERE status = 'closed' AND oracle_confidence IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Period':<8} {'AvgConf':>8} {'MinConf':>8} {'MaxConf':>8} {'BadScale':>10}")
print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
for row in r:
    flag = " ⚠️" if row[4] > 0 else ""
    print(f"  {row[0]:<8} {row[1]:>8.3f} {row[2]:>8.3f} {row[3]:>8.3f} {row[4]:>10}{flag}")

# 5. Day by Day After Fix
section("5. DAY BY DAY AFTER FIX")
r = query(f"""
    SELECT
        open_time::date as trade_date,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(SUM(SUM(realized_pnl)) OVER (ORDER BY open_time::date)::numeric, 2) as cumulative_pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time >= '{FIX_DATE}'
    GROUP BY open_time::date ORDER BY trade_date
""")
print(f"\n  {'Date':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'Cumulative':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*12}")
for row in r:
    print(f"  {row[0]} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} ${row[5]:>11,.2f}")

# 6. R:R Ratio Before vs After
section("6. RISK/REWARD RATIO COMPARISON")
r = query(f"""
    SELECT
        CASE WHEN open_time < '{FIX_DATE}' THEN 'BEFORE' ELSE 'AFTER' END as period,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(ABS(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END))::numeric, 2) as avg_loss,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) /
              NULLIF(ABS(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)), 0)::numeric, 2) as rr_ratio
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Period':<8} {'AvgWin':>10} {'AvgLoss':>10} {'R:R Ratio':>10} {'Breakeven WR':>12}")
print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*12}")
for row in r:
    breakeven = 1 / (1 + (row[3] or 1)) * 100
    print(f"  {row[0]:<8} ${row[1] or 0:>9,.2f} ${row[2] or 0:>9,.2f} {row[3] or 0:>9.2f}:1 {breakeven:>11.1f}%")

# 7. Recent 20 Trades (All After Fix)
section("7. RECENT 20 TRADES (POST-FIX)")
r = query(f"""
    SELECT
        position_id,
        spread_type,
        ROUND(oracle_confidence::numeric, 2) as conf,
        close_reason,
        ROUND(realized_pnl::numeric, 2) as pnl,
        CASE WHEN realized_pnl > 0 THEN 'WIN' ELSE 'LOSS' END as result,
        open_time::date as date
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time >= '{FIX_DATE}'
    ORDER BY close_time DESC LIMIT 20
""")
if r:
    print(f"\n  {'ID':<12} {'Spread':<10} {'Conf':>5} {'CloseReason':<18} {'P&L':>10} {'Result':<6} {'Date'}")
    print(f"  {'-'*12} {'-'*10} {'-'*5} {'-'*18} {'-'*10} {'-'*6} {'-'*12}")
    for row in r:
        print(f"  {str(row[0])[-12:]:<12} {row[1]:<10} {row[2] or 0:>5.2f} {str(row[3])[:18]:<18} ${row[4]:>9,.2f} {row[5]:<6} {row[6]}")
else:
    print("\n  No trades after fix date yet")

# 8. Summary Stats
section("8. SUMMARY")
r_before = query(f"""
    SELECT COUNT(*), ROUND(SUM(realized_pnl)::numeric, 2),
           ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time < '{FIX_DATE}'
""")
r_after = query(f"""
    SELECT COUNT(*), ROUND(SUM(realized_pnl)::numeric, 2),
           ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2)
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL AND open_time >= '{FIX_DATE}'
""")

before = r_before[0] if r_before else (0, 0, 0)
after = r_after[0] if r_after else (0, 0, 0)

print(f"""
  BEFORE FIX (< {FIX_DATE}):
    Trades: {before[0]}
    P&L: ${before[1] or 0:,.2f}
    Win Rate: {before[2] or 0}%

  AFTER FIX (>= {FIX_DATE}):
    Trades: {after[0]}
    P&L: ${after[1] or 0:,.2f}
    Win Rate: {after[2] or 0}%

  IMPROVEMENT:
    Win Rate Change: {(after[2] or 0) - (before[2] or 0):+.2f}%
    P&L per Trade (Before): ${(before[1] or 0) / max(before[0], 1):,.2f}
    P&L per Trade (After): ${(after[1] or 0) / max(after[0], 1):,.2f}
""")

print("="*70)
print(" END OF BEFORE VS AFTER COMPARISON")
print("="*70 + "\n")
