#!/usr/bin/env python3
"""
GIDEON Analysis 03: Flip Point & Wall Analysis
===============================================
Analysis of trades relative to GEX flip point and walls.

Run: python scripts/icarus_analysis/03_flip_and_walls.py
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
print(" GIDEON FLIP POINT & WALL ANALYSIS")
print("="*70)

# 1. Flip Point Distance Analysis
section("1. DISTANCE TO FLIP POINT")
r = query("""
    SELECT
        CASE
            WHEN flip_point IS NULL OR flip_point = 0 OR underlying_at_entry = 0 THEN 'No Data'
            WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 < 0.5 THEN '<0.5%'
            WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 < 1.0 THEN '0.5-1.0%'
            WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 < 2.0 THEN '1.0-2.0%'
            WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 < 3.0 THEN '2.0-3.0%'
            WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 < 5.0 THEN '3.0-5.0%'
            ELSE '>5.0%'
        END as distance_bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(ABS(underlying_at_entry - flip_point) / NULLIF(underlying_at_entry, 0) * 100)::numeric, 3) as avg_dist
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY avg_dist NULLS LAST
""")
print(f"\n  {'Distance':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgDist':>8}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*8}")
for row in r:
    dist = f"{row[5]:.2f}%" if row[5] else "N/A"
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} {dist:>8}")

# 2. Above vs Below Flip Point
section("2. PRICE POSITION RELATIVE TO FLIP")
r = query("""
    SELECT
        CASE
            WHEN flip_point IS NULL OR flip_point = 0 THEN 'No Flip Data'
            WHEN underlying_at_entry > flip_point THEN 'ABOVE Flip'
            WHEN underlying_at_entry < flip_point THEN 'BELOW Flip'
            ELSE 'AT Flip'
        END as position,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY trades DESC
""")
print(f"\n  {'Position':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 3. Above/Below Flip + Spread Type Combo
section("3. FLIP POSITION + SPREAD TYPE COMBO")
r = query("""
    SELECT
        CASE
            WHEN flip_point IS NULL OR flip_point = 0 THEN 'No Flip'
            WHEN underlying_at_entry > flip_point THEN 'ABOVE'
            ELSE 'BELOW'
        END as flip_pos,
        spread_type,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1, spread_type ORDER BY pnl
""")
print(f"\n  {'FlipPos':<10} {'Spread':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'Logic'}")
print(f"  {'-'*10} {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*15}")
for row in r:
    # Check if trade makes sense
    flip_pos = row[0]
    spread = row[1]
    logic = ""
    if flip_pos == 'ABOVE' and spread == 'BULL_CALL':
        logic = "✓ Makes sense"
    elif flip_pos == 'BELOW' and spread == 'BEAR_PUT':
        logic = "✓ Makes sense"
    elif flip_pos == 'ABOVE' and spread == 'BEAR_PUT':
        logic = "? Contrarian"
    elif flip_pos == 'BELOW' and spread == 'BULL_CALL':
        logic = "? Contrarian"
    print(f"  {flip_pos:<10} {spread:<12} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f} {logic}")

# 4. Distance to Call Wall
section("4. DISTANCE TO CALL WALL")
r = query("""
    SELECT
        CASE
            WHEN call_wall IS NULL OR call_wall = 0 OR underlying_at_entry = 0 THEN 'No Data'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 0.5 THEN '<0.5%'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 1.0 THEN '0.5-1.0%'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 2.0 THEN '1.0-2.0%'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 3.0 THEN '2.0-3.0%'
            ELSE '>3.0%'
        END as distance_bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Dist to Call':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 5. Distance to Put Wall
section("5. DISTANCE TO PUT WALL")
r = query("""
    SELECT
        CASE
            WHEN put_wall IS NULL OR put_wall = 0 OR underlying_at_entry = 0 THEN 'No Data'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 0.5 THEN '<0.5%'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 1.0 THEN '0.5-1.0%'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 2.0 THEN '1.0-2.0%'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 3.0 THEN '2.0-3.0%'
            ELSE '>3.0%'
        END as distance_bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Dist to Put':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<12} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 6. Between Walls Analysis
section("6. PRICE POSITION VS WALLS")
r = query("""
    SELECT
        CASE
            WHEN call_wall IS NULL OR put_wall IS NULL OR call_wall = 0 OR put_wall = 0 THEN 'No Wall Data'
            WHEN underlying_at_entry > call_wall THEN 'ABOVE Call Wall'
            WHEN underlying_at_entry < put_wall THEN 'BELOW Put Wall'
            ELSE 'Between Walls'
        END as position,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY trades DESC
""")
print(f"\n  {'Position':<18} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*18} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<18} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 7. Wall Distance for BULL_CALL (should be near put wall)
section("7. BULL_CALL - DISTANCE TO PUT WALL (Support)")
r = query("""
    SELECT
        CASE
            WHEN put_wall IS NULL OR put_wall = 0 THEN 'No Put Wall'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 1.0 THEN '<1% (Near Support)'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 2.0 THEN '1-2%'
            WHEN (underlying_at_entry - put_wall) / underlying_at_entry * 100 < 3.0 THEN '2-3%'
            ELSE '>3% (Far from Support)'
        END as distance,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND spread_type = 'BULL_CALL'
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Distance':<22} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*22} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<22} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 8. Wall Distance for BEAR_PUT (should be near call wall)
section("8. BEAR_PUT - DISTANCE TO CALL WALL (Resistance)")
r = query("""
    SELECT
        CASE
            WHEN call_wall IS NULL OR call_wall = 0 THEN 'No Call Wall'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 1.0 THEN '<1% (Near Resistance)'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 2.0 THEN '1-2%'
            WHEN (call_wall - underlying_at_entry) / underlying_at_entry * 100 < 3.0 THEN '2-3%'
            ELSE '>3% (Far from Resistance)'
        END as distance,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND spread_type = 'BEAR_PUT'
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'Distance':<25} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*25} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<25} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 9. Winners vs Losers - Flip Distance Comparison
section("9. WINNERS VS LOSERS - FLIP DISTANCE")
r = query("""
    SELECT
        CASE WHEN realized_pnl > 0 THEN 'WINNERS' ELSE 'LOSERS' END as outcome,
        COUNT(*) as trades,
        ROUND(AVG(ABS(underlying_at_entry - flip_point) / NULLIF(underlying_at_entry, 0) * 100)::numeric, 3) as avg_flip_dist,
        ROUND(AVG(ABS(underlying_at_entry - call_wall) / NULLIF(underlying_at_entry, 0) * 100)::numeric, 3) as avg_call_dist,
        ROUND(AVG(ABS(underlying_at_entry - put_wall) / NULLIF(underlying_at_entry, 0) * 100)::numeric, 3) as avg_put_dist
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
        AND flip_point IS NOT NULL AND flip_point > 0
    GROUP BY 1
""")
print(f"\n  {'Outcome':<10} {'Trades':>7} {'AvgFlipDist':>12} {'AvgCallDist':>12} {'AvgPutDist':>12}")
print(f"  {'-'*10} {'-'*7} {'-'*12} {'-'*12} {'-'*12}")
for row in r:
    print(f"  {row[0]:<10} {row[1]:>7} {row[2]:>11.3f}% {row[3]:>11.3f}% {row[4]:>11.3f}%")

print("\n" + "="*70)
print(" END OF FLIP & WALL ANALYSIS")
print("="*70 + "\n")
