#!/usr/bin/env python3
"""
GIDEON Analysis 05: VIX Analysis
================================
How does VIX affect GIDEON performance?

Run: python scripts/icarus_analysis/05_vix_analysis.py
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
print(" GIDEON VIX ANALYSIS")
print("="*70)

# 1. VIX Level at Entry
section("1. VIX LEVEL AT ENTRY")
r = query("""
    SELECT
        CASE
            WHEN vix_at_entry IS NULL THEN 'No VIX Data'
            WHEN vix_at_entry < 12 THEN 'Very Low (<12)'
            WHEN vix_at_entry < 15 THEN 'Low (12-15)'
            WHEN vix_at_entry < 18 THEN 'Normal (15-18)'
            WHEN vix_at_entry < 22 THEN 'Elevated (18-22)'
            WHEN vix_at_entry < 28 THEN 'High (22-28)'
            ELSE 'Very High (>28)'
        END as vix_level,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
        ROUND(AVG(vix_at_entry)::numeric, 2) as avg_vix
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY avg_vix NULLS LAST
""")
print(f"\n  {'VIX Level':<18} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'AvgVIX':>8}")
print(f"  {'-'*18} {'-'*7} {'-'*6} {'-'*7} {'-'*12} {'-'*8}")
for row in r:
    print(f"  {row[0]:<18} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f} {row[5] or 'N/A':>8}")

# 2. VIX + Spread Type Combo
section("2. VIX LEVEL + SPREAD TYPE")
r = query("""
    SELECT
        CASE
            WHEN vix_at_entry IS NULL THEN 'No VIX'
            WHEN vix_at_entry < 15 THEN 'Low (<15)'
            WHEN vix_at_entry < 20 THEN 'Normal (15-20)'
            ELSE 'High (>20)'
        END as vix_level,
        spread_type,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1, spread_type ORDER BY 1, spread_type
""")
print(f"\n  {'VIX Level':<15} {'Spread':<12} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*15} {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<15} {row[1]:<12} {row[2]:>7} {row[3]:>6} {row[4]:>6}% ${row[5]:>11,.2f}")

# 3. Winners vs Losers - VIX Comparison
section("3. WINNERS VS LOSERS - VIX AT ENTRY")
r = query("""
    SELECT
        CASE WHEN realized_pnl > 0 THEN 'WINNERS' ELSE 'LOSERS' END as outcome,
        COUNT(*) as trades,
        ROUND(AVG(vix_at_entry)::numeric, 2) as avg_vix,
        ROUND(MIN(vix_at_entry)::numeric, 2) as min_vix,
        ROUND(MAX(vix_at_entry)::numeric, 2) as max_vix
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND vix_at_entry IS NOT NULL
    GROUP BY 1
""")
print(f"\n  {'Outcome':<10} {'Trades':>7} {'AvgVIX':>8} {'MinVIX':>8} {'MaxVIX':>8}")
print(f"  {'-'*10} {'-'*7} {'-'*8} {'-'*8} {'-'*8}")
for row in r:
    print(f"  {row[0]:<10} {row[1]:>7} {row[2]:>8.2f} {row[3]:>8.2f} {row[4]:>8.2f}")

# 4. VIX Regime Analysis (correlate with CLAUDE.md VIX regimes)
section("4. VIX REGIME ANALYSIS (per CLAUDE.md)")
r = query("""
    SELECT
        CASE
            WHEN vix_at_entry IS NULL THEN 'No Data'
            WHEN vix_at_entry < 15 THEN 'LOW (<15) - thin premiums'
            WHEN vix_at_entry < 22 THEN 'NORMAL (15-22) - ideal'
            WHEN vix_at_entry < 28 THEN 'ELEVATED (22-28) - widen strikes'
            WHEN vix_at_entry < 35 THEN 'HIGH (28-35) - reduce 50%'
            ELSE 'EXTREME (>35) - skip ICs'
        END as vix_regime,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_pct,
        ROUND(SUM(realized_pnl)::numeric, 2) as pnl
    FROM gideon_positions WHERE status = 'closed' AND realized_pnl IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'VIX Regime':<35} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>12}")
print(f"  {'-'*35} {'-'*7} {'-'*6} {'-'*7} {'-'*12}")
for row in r:
    print(f"  {row[0]:<35} {row[1]:>7} {row[2]:>6} {row[3]:>6}% ${row[4]:>11,.2f}")

# 5. VIX Correlation with Entry Debit
section("5. VIX VS ENTRY DEBIT")
r = query("""
    SELECT
        CASE
            WHEN vix_at_entry < 15 THEN 'Low VIX'
            WHEN vix_at_entry < 20 THEN 'Normal VIX'
            ELSE 'High VIX'
        END as vix_level,
        ROUND(AVG(entry_debit)::numeric, 2) as avg_debit,
        ROUND(AVG(max_profit)::numeric, 2) as avg_max_profit,
        ROUND(AVG(max_loss)::numeric, 2) as avg_max_loss,
        COUNT(*) as trades
    FROM gideon_positions
    WHERE status = 'closed' AND vix_at_entry IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
print(f"\n  {'VIX Level':<12} {'AvgDebit':>10} {'AvgMaxProfit':>14} {'AvgMaxLoss':>12} {'Trades':>8}")
print(f"  {'-'*12} {'-'*10} {'-'*14} {'-'*12} {'-'*8}")
for row in r:
    print(f"  {row[0]:<12} ${row[1]:>9,.2f} ${row[2]:>13,.2f} ${row[3]:>11,.2f} {row[4]:>8}")

# 6. VIX Distribution
section("6. VIX DISTRIBUTION AT ENTRY")
r = query("""
    SELECT
        ROUND(vix_at_entry::numeric, 0) as vix,
        COUNT(*) as trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
    FROM gideon_positions
    WHERE status = 'closed' AND realized_pnl IS NOT NULL AND vix_at_entry IS NOT NULL
    GROUP BY ROUND(vix_at_entry::numeric, 0)
    ORDER BY vix
""")
print(f"\n  VIX Distribution:")
for row in r:
    win_pct = (row[2] / row[1] * 100) if row[1] > 0 else 0
    bar = "█" * min(int(row[1] / 5), 40)
    print(f"  VIX {int(row[0]):>2}: {bar} ({row[1]} trades, {win_pct:.0f}% WR)")

print("\n" + "="*70)
print(" END OF VIX ANALYSIS")
print("="*70 + "\n")
