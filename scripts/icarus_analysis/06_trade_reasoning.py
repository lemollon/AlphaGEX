#!/usr/bin/env python3
"""
ICARUS Analysis 06: Trade Reasoning & Top Factors
=================================================
What factors drove trading decisions?

Run: python scripts/icarus_analysis/06_trade_reasoning.py
"""

import os
import sys
import json
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
print(" ICARUS TRADE REASONING ANALYSIS")
print("="*70)

# 1. Trade Reasoning Keywords
section("1. TRADE REASONING KEYWORDS")
r = query("""
    SELECT trade_reasoning, COUNT(*) as cnt,
           ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
    FROM icarus_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND trade_reasoning IS NOT NULL
    GROUP BY trade_reasoning ORDER BY cnt DESC LIMIT 20
""")
print(f"\n  {'Reasoning (truncated)':<50} {'Count':>6} {'Wins':>5} {'P&L':>12}")
print(f"  {'-'*50} {'-'*6} {'-'*5} {'-'*12}")
for row in r:
    reasoning = str(row[0])[:50] if row[0] else 'NULL'
    print(f"  {reasoning:<50} {row[1]:>6} {row[2]:>5} ${row[3]:>11,.2f}")

# 2. ML Top Features Analysis
section("2. ML TOP FEATURES")
r = query("""
    SELECT ml_top_features, COUNT(*) as cnt,
           ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
    FROM icarus_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND ml_top_features IS NOT NULL AND ml_top_features != ''
    GROUP BY ml_top_features ORDER BY cnt DESC LIMIT 15
""")
print(f"\n  {'Top Features':<55} {'Count':>6} {'Wins':>5} {'P&L':>12}")
print(f"  {'-'*55} {'-'*6} {'-'*5} {'-'*12}")
for row in r:
    features = str(row[0])[:55] if row[0] else 'NULL'
    print(f"  {features:<55} {row[1]:>6} {row[2]:>5} ${row[3]:>11,.2f}")

# 3. ML Model Used
section("3. ML MODEL USED")
r = query("""
    SELECT COALESCE(ml_model_name, 'NULL') as model,
           COUNT(*) as trades,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
           ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
           ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM icarus_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY ml_model_name ORDER BY trades DESC
""")
print(f"\n  {'Model':<30} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*30} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {str(row[0])[:30]:<30} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 4. Wall Type Analysis
section("4. WALL TYPE AT ENTRY")
r = query("""
    SELECT COALESCE(wall_type, 'NULL') as wall,
           COUNT(*) as trades,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
           ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
           ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM icarus_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY wall_type ORDER BY trades DESC
""")
print(f"\n  {'Wall Type':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {str(row[0])[:15]:<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 5. Wall Distance % at Entry
section("5. WALL DISTANCE % AT ENTRY")
r = query("""
    SELECT
        CASE
            WHEN wall_distance_pct IS NULL THEN 'No Data'
            WHEN wall_distance_pct < 1 THEN '<1%'
            WHEN wall_distance_pct < 2 THEN '1-2%'
            WHEN wall_distance_pct < 3 THEN '2-3%'
            WHEN wall_distance_pct < 5 THEN '3-5%'
            ELSE '>5%'
        END as distance,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM icarus_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Wall Dist':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 6. Contract Size Analysis
section("6. CONTRACT SIZE ANALYSIS")
r = query("""
    SELECT contracts,
           COUNT(*) as trades,
           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
           ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
           ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
           ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl
    FROM icarus_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY contracts ORDER BY contracts
""")
print(f"\n  {'Contracts':>10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'TotalP&L':>12} {'AvgP&L':>10}")
print(f"  {'-'*10} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*10}")
for row in r:
    print(f"  {row[0]:>10} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} ${row[5]:>9,.2f}")

# 7. Strike Width Analysis
section("7. STRIKE WIDTH ANALYSIS")
r = query("""
    SELECT
        ROUND(ABS(long_strike - short_strike)::numeric, 0) as width,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM icarus_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND long_strike IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Width':>8} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*8} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  ${row[0]:>7.0f} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 8. Expiration Analysis (days to expiry)
section("8. EXPIRATION ANALYSIS")
r = query("""
    SELECT
        CASE
            WHEN expiration IS NULL THEN 'No Data'
            WHEN expiration::date = open_time::date THEN '0DTE'
            WHEN expiration::date = open_time::date + 1 THEN '1DTE'
            WHEN expiration::date <= open_time::date + 3 THEN '2-3 DTE'
            ELSE '>3 DTE'
        END as dte,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM icarus_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'DTE':<10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*10} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<10} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 9. Recent Trade Details
section("9. LAST 10 TRADES - FULL DETAILS")
r = query("""
    SELECT
        spread_type,
        gex_regime,
        ROUND(oracle_confidence::numeric, 2) as conf,
        ml_direction,
        wall_type,
        ROUND(wall_distance_pct::numeric, 2) as wall_dist,
        close_reason,
        ROUND(realized_pnl::numeric, 2) as pnl
    FROM icarus_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    ORDER BY close_time DESC LIMIT 10
""")
print(f"\n  {'Spread':<10} {'Regime':<8} {'Conf':>5} {'MLDir':<8} {'Wall':<8} {'WallD':>6} {'CloseReason':<18} {'P&L':>10}")
print(f"  {'-'*10} {'-'*8} {'-'*5} {'-'*8} {'-'*8} {'-'*6} {'-'*18} {'-'*10}")
for row in r:
    print(f"  {row[0]:<10} {str(row[1])[:8]:<8} {row[2] or 0:>5.2f} {str(row[3])[:8]:<8} {str(row[4])[:8]:<8} {row[5] or 0:>5.1f}% {str(row[6])[:18]:<18} ${row[7]:>9,.2f}")

print("\n" + "="*70)
print(" END OF TRADE REASONING ANALYSIS")
print("="*70 + "\n")
