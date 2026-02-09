#!/usr/bin/env python3
"""
GIDEON Analysis 01: Complete Trade Breakdown
=============================================
Detailed breakdown of every trade dimension.

Run: python scripts/gideon_analysis/01_trade_breakdown.py
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
    cols = [d[0] for d in c.description] if c.description else []
    conn.close()
    return results, cols

def section(title):
    print(f"\n{'='*70}\n {title}\n{'='*70}")

print("\n" + "="*70)
print(" GIDEON COMPLETE TRADE BREAKDOWN")
print("="*70)

# 1. Overall Summary
section("1. OVERALL SUMMARY")
r, _ = query("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
        ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)::numeric, 2) as avg_loss
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
""")
if r:
    print(f"  Total: {r[0][0]} | Wins: {r[0][1]} | Win%: {r[0][2]}% | P&L: ${r[0][3]:,.2f}")
    print(f"  Avg P&L: ${r[0][4]:,.2f} | Avg Win: ${r[0][5]:,.2f} | Avg Loss: ${r[0][6]:,.2f}")
    if r[0][5] and r[0][6]:
        rr = abs(r[0][5] / r[0][6])
        breakeven = 1 / (1 + rr) * 100
        print(f"  R:R Ratio: {rr:.2f}:1 | Break-even Win Rate: {breakeven:.1f}%")

# 2. By Spread Type
section("2. BY SPREAD TYPE")
r, _ = query("""
    SELECT spread_type, COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
        ROUND(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END)::numeric, 2) as avg_loss
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY spread_type ORDER BY pnl
""")
print(f"\n  {'Type':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgWin':>9} {'AvgLoss':>9}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*9} {'-'*9}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} ${row[5] or 0:>8,.2f} ${row[6] or 0:>8,.2f}")

# 3. By Close Reason
section("3. BY CLOSE REASON (CRITICAL)")
r, _ = query("""
    SELECT close_reason, COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY close_reason ORDER BY trades DESC
""")
print(f"\n  {'Reason':<25} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*25} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    flag = " ← OLD CONFIG" if "60%" in str(row[0]) else (" ← NEW CONFIG" if "50%" in str(row[0]) else "")
    print(f"  {str(row[0])[:25]:<25} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}{flag}")

# 4. By Day of Week
section("4. BY DAY OF WEEK")
r, _ = query("""
    SELECT TO_CHAR(open_time, 'Day') as day,
        EXTRACT(DOW FROM open_time) as dow,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY TO_CHAR(open_time, 'Day'), EXTRACT(DOW FROM open_time) ORDER BY dow
""")
print(f"\n  {'Day':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    flag = " ← FRIDAY" if row[1] == 5 else ""
    print(f"  {row[0].strip():<12} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f}{flag}")

# 5. By Hour of Day
section("5. BY HOUR OF DAY (CT)")
r, _ = query("""
    SELECT EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') ORDER BY hour
""")
print(f"\n  {'Hour':>6} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {int(row[0]):>6} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 6. By Week
section("6. BY WEEK (TREND)")
r, _ = query("""
    SELECT DATE_TRUNC('week', open_time)::date as week,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY DATE_TRUNC('week', open_time) ORDER BY week
""")
print(f"\n  {'Week':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 7. By Prophet Confidence Bucket
section("7. BY PROPHET CONFIDENCE")
r, _ = query("""
    SELECT
        CASE
            WHEN oracle_confidence IS NULL THEN 'NULL'
            WHEN oracle_confidence > 1 THEN 'BAD >1.0'
            WHEN oracle_confidence >= 0.9 THEN '90-100%'
            WHEN oracle_confidence >= 0.8 THEN '80-90%'
            WHEN oracle_confidence >= 0.7 THEN '70-80%'
            WHEN oracle_confidence >= 0.6 THEN '60-70%'
            WHEN oracle_confidence >= 0.5 THEN '50-60%'
            ELSE '<50%'
        END as bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(oracle_confidence)::numeric, 3) as avg_conf
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY avg_conf DESC NULLS LAST
""")
print(f"\n  {'Confidence':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgConf':>8}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*8}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} {row[5] or 'N/A':>8}")

# 8. By GEX Regime
section("8. BY GEX REGIME")
r, _ = query("""
    SELECT COALESCE(gex_regime, 'NULL') as regime,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY gex_regime ORDER BY trades DESC
""")
print(f"\n  {'Regime':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 9. Spread Type + Regime Combo
section("9. SPREAD TYPE + REGIME COMBO")
r, _ = query("""
    SELECT spread_type, COALESCE(gex_regime, 'NULL') as regime,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY spread_type, gex_regime ORDER BY pnl
""")
print(f"\n  {'Type':<12} {'Regime':<10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*10} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:<10} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f}")

# 10. Entry Debit Analysis
section("10. ENTRY DEBIT ANALYSIS")
r, _ = query("""
    SELECT
        CASE
            WHEN entry_debit < 1.0 THEN '<$1.00'
            WHEN entry_debit < 1.5 THEN '$1.00-1.49'
            WHEN entry_debit < 2.0 THEN '$1.50-1.99'
            WHEN entry_debit < 2.5 THEN '$2.00-2.49'
            ELSE '>=$2.50'
        END as debit_range,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(entry_debit)::numeric, 2) as avg_debit
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY avg_debit
""")
print(f"\n  {'Debit Range':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgDebit':>9}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*9}")
for row in r:
    print(f"  {row[0]:<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} ${row[5]:>8,.2f}")

print("\n" + "="*70)
print(" END OF TRADE BREAKDOWN")
print("="*70 + "\n")
