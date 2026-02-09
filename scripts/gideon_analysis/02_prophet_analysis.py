#!/usr/bin/env python3
"""
GIDEON Analysis 02: Prophet Decision Analysis
=============================================
Deep dive into Prophet's predictions and their outcomes.

Run: python scripts/gideon_analysis/02_prophet_analysis.py
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
print(" GIDEON PROPHET DECISION ANALYSIS")
print("="*70)

# 1. Prophet Confidence Distribution
section("1. PROPHET CONFIDENCE DISTRIBUTION")
r, _ = query("""
    SELECT
        ROUND(oracle_confidence::numeric, 2) as conf,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND oracle_confidence IS NOT NULL
    GROUP BY ROUND(oracle_confidence::numeric, 2)
    ORDER BY conf DESC
""")
print(f"\n  {'Confidence':>10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*10} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    win_pct = (row[2] / row[1] * 100) if row[1] > 0 else 0
    print(f"  {row[0]:>10.2f} {row[1]:>7} {row[2]:>6} {win_pct:>6.1f}% ${row[3]:>11,.2f}")

# 2. Prophet Advice Values
section("2. PROPHET ADVICE VALUES")
r, _ = query("""
    SELECT COALESCE(oracle_advice, 'NULL') as advice,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY oracle_advice ORDER BY trades DESC
""")
print(f"\n  {'Advice':<20} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {str(row[0]):<20} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 3. ML Direction Analysis
section("3. ML DIRECTION ANALYSIS")
r, _ = query("""
    SELECT COALESCE(ml_direction, 'NULL') as direction,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY ml_direction ORDER BY trades DESC
""")
print(f"\n  {'ML Direction':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {str(row[0]):<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 4. ML Confidence Analysis
section("4. ML CONFIDENCE ANALYSIS")
r, _ = query("""
    SELECT
        CASE
            WHEN ml_confidence IS NULL THEN 'NULL'
            WHEN ml_confidence > 1 THEN 'BAD >1.0'
            WHEN ml_confidence >= 0.8 THEN '80-100%'
            WHEN ml_confidence >= 0.6 THEN '60-80%'
            WHEN ml_confidence >= 0.4 THEN '40-60%'
            ELSE '<40%'
        END as bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY trades DESC
""")
print(f"\n  {'ML Confidence':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 5. ML Win Probability Analysis
section("5. ML WIN PROBABILITY ANALYSIS")
r, _ = query("""
    SELECT
        CASE
            WHEN ml_win_probability IS NULL THEN 'NULL'
            WHEN ml_win_probability > 1 THEN 'BAD >1.0'
            WHEN ml_win_probability >= 0.7 THEN '70-100%'
            WHEN ml_win_probability >= 0.6 THEN '60-70%'
            WHEN ml_win_probability >= 0.5 THEN '50-60%'
            WHEN ml_win_probability >= 0.4 THEN '40-50%'
            ELSE '<40%'
        END as bucket,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(ml_win_probability)::numeric, 3) as avg_prob
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY avg_prob DESC NULLS LAST
""")
print(f"\n  {'ML WinProb':<15} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgProb':>8}")
print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*8}")
for row in r:
    print(f"  {row[0]:<15} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} {row[5] or 'N/A':>8}")

# 6. Prophet vs Actual Outcome
section("6. PROPHET PREDICTION VS ACTUAL OUTCOME")
r, _ = query("""
    SELECT
        ml_direction,
        spread_type,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY ml_direction, spread_type ORDER BY pnl
""")
print(f"\n  {'Direction':<12} {'Spread':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'Match?'}")
print(f"  {'-'*12} {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*8}")
for row in r:
    direction = row[0] or 'NULL'
    spread = row[1] or 'NULL'
    # Check if direction matches spread
    match = "✓" if (direction == 'BULLISH' and spread == 'BULL_CALL') or (direction == 'BEARISH' and spread == 'BEAR_PUT') else "✗"
    print(f"  {direction:<12} {spread:<12} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f} {match:>8}")

# 7. Confidence vs Win Rate Correlation
section("7. DOES HIGHER CONFIDENCE = HIGHER WIN RATE?")
r, _ = query("""
    WITH buckets AS (
        SELECT
            CASE
                WHEN oracle_confidence >= 0.8 THEN 'HIGH (80%+)'
                WHEN oracle_confidence >= 0.6 THEN 'MED (60-80%)'
                ELSE 'LOW (<60%)'
            END as conf_level,
            realized_pnl > 0 as win,
            realized_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL AND oracle_confidence IS NOT NULL
    )
    SELECT conf_level,
        COUNT(*) as trades,
        SUM(CASE WHEN win THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN win THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM buckets GROUP BY conf_level ORDER BY conf_level DESC
""")
print(f"\n  {'Confidence Level':<20} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<20} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 8. Check for Scale Bug (confidence > 1)
section("8. SCALE BUG CHECK (Confidence > 1.0)")
r, _ = query("""
    SELECT COUNT(*) as bad_conf,
        SUM(CASE WHEN oracle_confidence > 1 THEN 1 ELSE 0 END) as oracle_bad,
        SUM(CASE WHEN ml_confidence > 1 THEN 1 ELSE 0 END) as ml_bad,
        SUM(CASE WHEN ml_win_probability > 1 THEN 1 ELSE 0 END) as winprob_bad
    FROM gideon_positions WHERE status = 'closed'
""")
if r:
    print(f"\n  Prophet confidence > 1.0: {r[0][1]} trades")
    print(f"  ML confidence > 1.0: {r[0][2]} trades")
    print(f"  ML win_probability > 1.0: {r[0][3]} trades")
    if r[0][1] == 0 and r[0][2] == 0 and r[0][3] == 0:
        print("\n  ✅ No scale bugs detected")
    else:
        print("\n  ⚠️ SCALE BUG DETECTED - some confidence values > 1.0")

# 9. Recent Prophet Decisions
section("9. RECENT 15 PROPHET DECISIONS")
r, _ = query("""
    SELECT
        position_id,
        spread_type,
        ROUND(oracle_confidence::numeric, 2) as o_conf,
        oracle_advice,
        ml_direction,
        ROUND(ml_win_probability::numeric, 2) as ml_prob,
        ROUND(realized_pnl::numeric, 2) as pnl,
        CASE WHEN realized_pnl > 0 THEN 'WIN' ELSE 'LOSS' END as result,
        open_time::date as date
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL
    ORDER BY close_time DESC LIMIT 15
""")
print(f"\n  {'ID':<12} {'Spread':<10} {'OConf':>6} {'Advice':<12} {'MLDir':<8} {'MLProb':>6} {'P&L':>10} {'Result'}")
print(f"  {'-'*12} {'-'*10} {'-'*6} {'-'*12} {'-'*8} {'-'*6} {'-'*10} {'-'*6}")
for row in r:
    print(f"  {str(row[0])[-12:]:<12} {row[1]:<10} {row[2] or 0:>6.2f} {str(row[3])[:12]:<12} {str(row[4])[:8]:<8} {row[5] or 0:>6.2f} ${row[6]:>9,.2f} {row[7]}")

print("\n" + "="*70)
print(" END OF PROPHET ANALYSIS")
print("="*70 + "\n")
