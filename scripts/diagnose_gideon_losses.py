#!/usr/bin/env python3
"""
GIDEON Loss Diagnostic Script
==============================

Comprehensive analysis to figure out why GIDEON is still losing.

Run in Render shell:
    python scripts/diagnose_icarus_losses.py

Author: Claude Code
Date: 2026-02-02
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("ERROR: database_adapter not available")
    sys.exit(1)


def run_query(query, params=None):
    """Run a database query and return results."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(query, params or ())
    results = c.fetchall()
    columns = [desc[0] for desc in c.description] if c.description else []
    conn.close()
    return results, columns


def section(title):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f" {title}")
    print('='*70)


def main():
    print("\n" + "="*70)
    print(" GIDEON LOSS DIAGNOSTIC REPORT")
    print(" " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)

    # =========================================================================
    # 1. OVERALL PERFORMANCE SUMMARY
    # =========================================================================
    section("1. OVERALL PERFORMANCE SUMMARY")

    query = """
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
            ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) as avg_win,
            ROUND(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END)::numeric, 2) as avg_loss,
            MIN(open_time) as first_trade,
            MAX(close_time) as last_trade
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
    """
    results, cols = run_query(query)
    if results and results[0]:
        r = results[0]
        print(f"  Total Trades:    {r[0]}")
        print(f"  Wins:            {r[1]}")
        print(f"  Losses:          {r[2]}")
        print(f"  Win Rate:        {r[3]}%")
        print(f"  Total P&L:       ${r[4]:,.2f}")
        print(f"  Avg P&L/Trade:   ${r[5]:,.2f}")
        print(f"  Avg Win:         ${r[6]:,.2f}" if r[6] else "  Avg Win:         N/A")
        print(f"  Avg Loss:        ${r[7]:,.2f}" if r[7] else "  Avg Loss:        N/A")
        print(f"  First Trade:     {r[8]}")
        print(f"  Last Trade:      {r[9]}")

    # =========================================================================
    # 2. PERFORMANCE BY SPREAD TYPE (BULL_CALL vs BEAR_PUT)
    # =========================================================================
    section("2. PERFORMANCE BY SPREAD TYPE")

    query = """
        SELECT
            spread_type,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY spread_type
        ORDER BY total_pnl ASC
    """
    results, cols = run_query(query)
    print(f"\n  {'Spread Type':<15} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*15} {'-'*8} {'-'*6} {'-'*8} {'-'*12} {'-'*10}")
    for r in results:
        print(f"  {r[0]:<15} {r[1]:>8} {r[2]:>6} {r[3]:>7}% ${r[4]:>11,.2f} ${r[5]:>9,.2f}")

    # =========================================================================
    # 3. PERFORMANCE BY GEX REGIME
    # =========================================================================
    section("3. PERFORMANCE BY GEX REGIME")

    query = """
        SELECT
            COALESCE(gex_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY gex_regime
        ORDER BY trades DESC
    """
    results, cols = run_query(query)
    print(f"\n  {'GEX Regime':<15} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12}")
    print(f"  {'-'*15} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for r in results:
        print(f"  {r[0]:<15} {r[1]:>8} {r[2]:>6} {r[3]:>7}% ${r[4]:>11,.2f}")

    # =========================================================================
    # 4. SPREAD TYPE + GEX REGIME COMBO (THE KEY INSIGHT)
    # =========================================================================
    section("4. SPREAD TYPE + GEX REGIME COMBO (KEY INSIGHT)")

    query = """
        SELECT
            spread_type,
            COALESCE(gex_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY spread_type, gex_regime
        ORDER BY total_pnl ASC
    """
    results, cols = run_query(query)
    print(f"\n  {'Spread':<12} {'Regime':<12} {'Trades':>7} {'Wins':>5} {'Win%':>7} {'Total P&L':>12}")
    print(f"  {'-'*12} {'-'*12} {'-'*7} {'-'*5} {'-'*7} {'-'*12}")
    for r in results:
        flag = " ⚠️" if r[4] and r[4] < 30 else ""
        print(f"  {r[0]:<12} {r[1]:<12} {r[2]:>7} {r[3]:>5} {r[4]:>6}% ${r[5]:>11,.2f}{flag}")

    # =========================================================================
    # 5. PERFORMANCE BY DAY OF WEEK
    # =========================================================================
    section("5. PERFORMANCE BY DAY OF WEEK")

    query = """
        SELECT
            EXTRACT(DOW FROM open_time) as day_num,
            TO_CHAR(open_time, 'Day') as day_name,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY EXTRACT(DOW FROM open_time), TO_CHAR(open_time, 'Day')
        ORDER BY day_num
    """
    results, cols = run_query(query)
    print(f"\n  {'Day':<12} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12}")
    print(f"  {'-'*12} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for r in results:
        flag = " ⚠️ FRIDAY" if r[0] == 5 and r[4] and r[4] < 30 else ""
        print(f"  {r[1].strip():<12} {r[2]:>8} {r[3]:>6} {r[4]:>7}% ${r[5]:>11,.2f}{flag}")

    # =========================================================================
    # 6. ORACLE CONFIDENCE ANALYSIS
    # =========================================================================
    section("6. ORACLE CONFIDENCE ANALYSIS")

    query = """
        SELECT
            CASE
                WHEN oracle_confidence IS NULL THEN 'No Oracle'
                WHEN oracle_confidence > 1 THEN 'BAD SCALE (>1)'
                WHEN oracle_confidence >= 0.8 THEN '80-100%'
                WHEN oracle_confidence >= 0.6 THEN '60-80%'
                WHEN oracle_confidence >= 0.4 THEN '40-60%'
                ELSE 'Below 40%'
            END as confidence_bucket,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(oracle_confidence)::numeric, 3) as avg_conf
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY
            CASE
                WHEN oracle_confidence IS NULL THEN 'No Oracle'
                WHEN oracle_confidence > 1 THEN 'BAD SCALE (>1)'
                WHEN oracle_confidence >= 0.8 THEN '80-100%'
                WHEN oracle_confidence >= 0.6 THEN '60-80%'
                WHEN oracle_confidence >= 0.4 THEN '40-60%'
                ELSE 'Below 40%'
            END
        ORDER BY avg_conf DESC NULLS LAST
    """
    results, cols = run_query(query)
    print(f"\n  {'Confidence':<15} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12} {'Avg Conf':>10}")
    print(f"  {'-'*15} {'-'*8} {'-'*6} {'-'*8} {'-'*12} {'-'*10}")
    for r in results:
        flag = " ⚠️ BUG!" if r[0] == 'BAD SCALE (>1)' else ""
        conf_str = f"{r[5]:.3f}" if r[5] else "N/A"
        print(f"  {r[0]:<15} {r[1]:>8} {r[2]:>6} {r[3]:>7}% ${r[4]:>11,.2f} {conf_str:>10}{flag}")

    # =========================================================================
    # 7. FLIP POINT DISTANCE ANALYSIS
    # =========================================================================
    section("7. FLIP POINT DISTANCE ANALYSIS")

    query = """
        SELECT
            CASE
                WHEN flip_point IS NULL OR flip_point = 0 THEN 'No Flip Data'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 5 THEN '>5% from flip'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 3 THEN '3-5% from flip'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 1 THEN '1-3% from flip'
                ELSE '<1% from flip'
            END as flip_distance,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100)::numeric, 2) as avg_dist
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY
            CASE
                WHEN flip_point IS NULL OR flip_point = 0 THEN 'No Flip Data'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 5 THEN '>5% from flip'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 3 THEN '3-5% from flip'
                WHEN ABS(underlying_at_entry - flip_point) / underlying_at_entry * 100 > 1 THEN '1-3% from flip'
                ELSE '<1% from flip'
            END
        ORDER BY avg_dist ASC NULLS LAST
    """
    results, cols = run_query(query)
    print(f"\n  {'Flip Distance':<18} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12} {'Avg Dist':>10}")
    print(f"  {'-'*18} {'-'*8} {'-'*6} {'-'*8} {'-'*12} {'-'*10}")
    for r in results:
        dist_str = f"{r[5]:.2f}%" if r[5] else "N/A"
        print(f"  {r[0]:<18} {r[1]:>8} {r[2]:>6} {r[3]:>7}% ${r[4]:>11,.2f} {dist_str:>10}")

    # =========================================================================
    # 8. RECENT TRADES (LAST 20)
    # =========================================================================
    section("8. RECENT TRADES (LAST 20)")

    query = """
        SELECT
            position_id,
            spread_type,
            COALESCE(gex_regime, 'UNK') as regime,
            ROUND(oracle_confidence::numeric, 2) as conf,
            ROUND(realized_pnl::numeric, 2) as pnl,
            CASE WHEN realized_pnl > 0 THEN 'WIN' ELSE 'LOSS' END as result,
            close_reason,
            open_time::date as trade_date
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        ORDER BY close_time DESC
        LIMIT 20
    """
    results, cols = run_query(query)
    print(f"\n  {'ID':<10} {'Type':<10} {'Regime':<8} {'Conf':>6} {'P&L':>10} {'Result':<6} {'Reason':<20} {'Date':<12}")
    print(f"  {'-'*10} {'-'*10} {'-'*8} {'-'*6} {'-'*10} {'-'*6} {'-'*20} {'-'*12}")
    for r in results:
        conf_str = f"{r[3]:.2f}" if r[3] else "N/A"
        reason = (r[6] or "")[:20]
        print(f"  {str(r[0])[:10]:<10} {r[1]:<10} {r[2]:<8} {conf_str:>6} ${r[4]:>9,.2f} {r[5]:<6} {reason:<20} {r[7]}")

    # =========================================================================
    # 9. TRADES AFTER FIX DATE (2026-02-01)
    # =========================================================================
    section("9. TRADES AFTER FIX DATE (2026-02-01)")

    query = """
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 2) as win_rate_pct,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
        FROM gideon_positions
        WHERE status = 'closed'
          AND realized_pnl IS NOT NULL
          AND open_time >= '2026-02-01'
    """
    results, cols = run_query(query)
    if results and results[0] and results[0][0]:
        r = results[0]
        print(f"\n  Trades after fix:  {r[0]}")
        print(f"  Wins:              {r[1]}")
        print(f"  Win Rate:          {r[2]}%")
        print(f"  Total P&L:         ${r[3]:,.2f}")
    else:
        print("\n  No trades after fix date yet (expected - market closed)")

    # =========================================================================
    # 10. OPEN POSITIONS (LIVE RIGHT NOW)
    # =========================================================================
    section("10. OPEN POSITIONS (LIVE RIGHT NOW)")

    query = """
        SELECT
            position_id,
            spread_type,
            COALESCE(gex_regime, 'UNK') as regime,
            ROUND(oracle_confidence::numeric, 2) as conf,
            ROUND(entry_debit::numeric, 2) as entry,
            open_time
        FROM gideon_positions
        WHERE status = 'open'
        ORDER BY open_time DESC
    """
    results, cols = run_query(query)
    if results:
        print(f"\n  {'ID':<10} {'Type':<12} {'Regime':<10} {'Conf':>6} {'Entry':>10} {'Opened'}")
        print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*6} {'-'*10} {'-'*20}")
        for r in results:
            conf_str = f"{r[3]:.2f}" if r[3] else "N/A"
            print(f"  {str(r[0])[:10]:<10} {r[1]:<12} {r[2]:<10} {conf_str:>6} ${r[4]:>9,.2f} {r[5]}")
    else:
        print("\n  No open positions")

    # =========================================================================
    # 11. CLOSE REASON ANALYSIS
    # =========================================================================
    section("11. CLOSE REASON ANALYSIS")

    query = """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') as reason,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
        FROM gideon_positions
        WHERE status = 'closed' AND realized_pnl IS NOT NULL
        GROUP BY close_reason
        ORDER BY trades DESC
    """
    results, cols = run_query(query)
    print(f"\n  {'Close Reason':<30} {'Trades':>8} {'Wins':>6} {'Total P&L':>12}")
    print(f"  {'-'*30} {'-'*8} {'-'*6} {'-'*12}")
    for r in results:
        print(f"  {r[0][:30]:<30} {r[1]:>8} {r[2]:>6} ${r[3]:>11,.2f}")

    # =========================================================================
    # 12. KEY DIAGNOSTIC QUESTIONS
    # =========================================================================
    section("12. KEY DIAGNOSTIC QUESTIONS")

    # Check for bad oracle confidence scale
    query = """
        SELECT COUNT(*) FROM gideon_positions
        WHERE oracle_confidence > 1 AND status = 'closed'
    """
    results, _ = run_query(query)
    bad_conf = results[0][0] if results else 0

    # Check BEAR_PUT in NEUTRAL regime
    query = """
        SELECT COUNT(*), ROUND(SUM(realized_pnl)::numeric, 2)
        FROM gideon_positions
        WHERE spread_type = 'BEAR_PUT'
          AND gex_regime = 'NEUTRAL'
          AND status = 'closed'
    """
    results, _ = run_query(query)
    bear_neutral = results[0] if results else (0, 0)

    # Check BULL_CALL in NEUTRAL regime
    query = """
        SELECT COUNT(*), ROUND(SUM(realized_pnl)::numeric, 2)
        FROM gideon_positions
        WHERE spread_type = 'BULL_CALL'
          AND gex_regime = 'NEUTRAL'
          AND status = 'closed'
    """
    results, _ = run_query(query)
    bull_neutral = results[0] if results else (0, 0)

    print(f"""
  Q1: Are there trades with BAD Oracle confidence (>1)?
      → {bad_conf} trades with confidence > 1.0 {'⚠️ SCALE BUG STILL EXISTS' if bad_conf > 0 else '✅ Fixed'}

  Q2: BEAR_PUT trades in NEUTRAL regime (wrong regime)?
      → {bear_neutral[0]} trades, ${bear_neutral[1]:,.2f} P&L {'⚠️ PROBLEM' if bear_neutral[0] > 10 else ''}

  Q3: BULL_CALL trades in NEUTRAL regime (wrong regime)?
      → {bull_neutral[0]} trades, ${bull_neutral[1]:,.2f} P&L {'⚠️ PROBLEM' if bull_neutral[0] > 10 else ''}
    """)

    # =========================================================================
    # 13. RECOMMENDATIONS
    # =========================================================================
    section("13. RECOMMENDATIONS BASED ON DATA")

    print("""
  Based on the analysis above, consider:

  1. If BEAR_PUT in NEUTRAL regime is losing big:
     → Add filter: Only allow BEAR_PUT when regime = NEGATIVE

  2. If BULL_CALL in NEUTRAL regime is losing big:
     → Add filter: Only allow BULL_CALL when regime = POSITIVE

  3. If trades >5% from flip are losing:
     → Flip distance filter may not be active yet (pre-fix trades)

  4. If Friday trades are losing:
     → Friday filter may not be active yet (pre-fix trades)

  5. If Oracle confidence >1 exists:
     → Scale bug still present in some code path
    """)

    print("\n" + "="*70)
    print(" END OF DIAGNOSTIC REPORT")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
