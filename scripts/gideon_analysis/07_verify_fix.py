#!/usr/bin/env python3
"""
GIDEON Fix Verification Script
==============================
Verifies that the ML → Prophet → GIDEON direction chain is working correctly.

Run this after deploying the fix to check:
1. Trades are being generated
2. Direction chain is consistent (no mismatches)
3. Win rate has improved
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timedelta
from database_adapter import get_connection

# Fix date - when the ML direction fix was deployed
FIX_DATE = "2026-02-02"

def run_verification():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("GIDEON FIX VERIFICATION REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print(f"Fix Date: {FIX_DATE}")
    print("=" * 70)

    # 1. CHECK IF TRADES ARE BEING GENERATED
    print("\n" + "=" * 70)
    print("1. TRADE GENERATION CHECK")
    print("=" * 70)

    cur.execute("""
        SELECT
            DATE(entry_time) as trade_date,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 1) as win_rate,
            ROUND(SUM(realized_pnl)::numeric, 2) as pnl
        FROM gideon_closed_trades
        WHERE entry_time >= %s::date
        GROUP BY DATE(entry_time)
        ORDER BY trade_date DESC
        LIMIT 10
    """, (FIX_DATE,))

    rows = cur.fetchall()
    if rows:
        print(f"\n  Trades since fix ({FIX_DATE}):")
        print(f"  {'Date':<12} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'P&L':>12}")
        print(f"  {'-'*12} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
        total_trades = 0
        total_wins = 0
        total_pnl = 0
        for row in rows:
            date, trades, wins, wr, pnl = row
            total_trades += trades
            total_wins += wins or 0
            total_pnl += float(pnl or 0)
            print(f"  {date} {trades:>8} {wins or 0:>6} {wr or 0:>7.1f}% ${pnl or 0:>10,.2f}")

        print(f"  {'-'*12} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
        overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
        print(f"  {'TOTAL':<12} {total_trades:>8} {total_wins:>6} {overall_wr:>7.1f}% ${total_pnl:>10,.2f}")

        if total_trades == 0:
            print("\n  ⚠️  WARNING: No trades since fix date!")
            print("      Check if Prophet is returning TRADE signals")
    else:
        print(f"\n  ⚠️  NO TRADES since {FIX_DATE}")
        print("      This could mean:")
        print("      - Bot hasn't run yet")
        print("      - Prophet is blocking all trades")
        print("      - Market was closed")

    # 2. DIRECTION MISMATCH CHECK
    print("\n" + "=" * 70)
    print("2. DIRECTION MISMATCH CHECK (The Bug We Fixed)")
    print("=" * 70)

    cur.execute("""
        SELECT
            spread_type,
            ml_direction,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 1) as win_rate,
            ROUND(SUM(realized_pnl)::numeric, 2) as pnl,
            CASE
                WHEN (spread_type = 'BULL_CALL' AND ml_direction = 'BULLISH') OR
                     (spread_type = 'BEAR_PUT' AND ml_direction = 'BEARISH')
                THEN '✓ MATCH'
                ELSE '✗ MISMATCH'
            END as status
        FROM gideon_closed_trades
        WHERE entry_time >= %s::date
          AND ml_direction IS NOT NULL
        GROUP BY spread_type, ml_direction
        ORDER BY status DESC, trades DESC
    """, (FIX_DATE,))

    rows = cur.fetchall()
    if rows:
        print(f"\n  Post-fix direction alignment:")
        print(f"  {'Spread':<12} {'ML Dir':<10} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'P&L':>12} {'Status':<12}")
        print(f"  {'-'*12} {'-'*10} {'-'*8} {'-'*6} {'-'*8} {'-'*12} {'-'*12}")

        mismatches = 0
        for row in rows:
            spread, ml_dir, trades, wins, wr, pnl, status = row
            if 'MISMATCH' in status:
                mismatches += trades
            print(f"  {spread or 'N/A':<12} {ml_dir or 'N/A':<10} {trades:>8} {wins or 0:>6} {wr or 0:>7.1f}% ${pnl or 0:>10,.2f} {status}")

        if mismatches == 0:
            print(f"\n  ✅ SUCCESS: No direction mismatches since fix!")
        else:
            print(f"\n  ⚠️  WARNING: {mismatches} trades with direction mismatch")
            print("      The fix may not be deployed yet")
    else:
        print(f"\n  No trades with ML direction data since {FIX_DATE}")

    # 3. COMPARE BEFORE VS AFTER
    print("\n" + "=" * 70)
    print("3. BEFORE vs AFTER FIX COMPARISON")
    print("=" * 70)

    cur.execute("""
        WITH before_fix AS (
            SELECT
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(realized_pnl) as pnl,
                SUM(CASE WHEN spread_type = 'BULL_CALL' AND ml_direction = 'BULLISH' THEN 0
                         WHEN spread_type = 'BEAR_PUT' AND ml_direction = 'BEARISH' THEN 0
                         WHEN ml_direction IS NOT NULL THEN 1
                         ELSE 0 END) as mismatches
            FROM gideon_closed_trades
            WHERE entry_time < %s::date
        ),
        after_fix AS (
            SELECT
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(realized_pnl) as pnl,
                SUM(CASE WHEN spread_type = 'BULL_CALL' AND ml_direction = 'BULLISH' THEN 0
                         WHEN spread_type = 'BEAR_PUT' AND ml_direction = 'BEARISH' THEN 0
                         WHEN ml_direction IS NOT NULL THEN 1
                         ELSE 0 END) as mismatches
            FROM gideon_closed_trades
            WHERE entry_time >= %s::date
        )
        SELECT
            'BEFORE' as period, trades, wins,
            ROUND(wins::numeric / NULLIF(trades, 0) * 100, 1) as win_rate,
            ROUND(pnl::numeric, 2) as pnl,
            mismatches
        FROM before_fix
        UNION ALL
        SELECT
            'AFTER' as period, trades, wins,
            ROUND(wins::numeric / NULLIF(trades, 0) * 100, 1) as win_rate,
            ROUND(pnl::numeric, 2) as pnl,
            mismatches
        FROM after_fix
    """, (FIX_DATE, FIX_DATE))

    rows = cur.fetchall()
    print(f"\n  {'Period':<10} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'P&L':>14} {'Mismatches':>12}")
    print(f"  {'-'*10} {'-'*8} {'-'*6} {'-'*8} {'-'*14} {'-'*12}")
    for row in rows:
        period, trades, wins, wr, pnl, mismatches = row
        print(f"  {period:<10} {trades or 0:>8} {wins or 0:>6} {wr or 0:>7.1f}% ${pnl or 0:>13,.2f} {mismatches or 0:>12}")

    # 4. CHECK PROPHET DIRECTION SOURCE
    print("\n" + "=" * 70)
    print("4. PROPHET DIRECTION SOURCE CHECK")
    print("=" * 70)

    cur.execute("""
        SELECT
            oracle_direction,
            ml_direction,
            COUNT(*) as trades,
            CASE WHEN oracle_direction = ml_direction THEN '✓ ALIGNED' ELSE '✗ DIFFERENT' END as status
        FROM gideon_closed_trades
        WHERE entry_time >= %s::date
          AND oracle_direction IS NOT NULL
          AND ml_direction IS NOT NULL
        GROUP BY oracle_direction, ml_direction
        ORDER BY trades DESC
    """, (FIX_DATE,))

    rows = cur.fetchall()
    if rows:
        print(f"\n  Prophet vs ML direction alignment:")
        print(f"  {'Prophet Dir':<12} {'ML Dir':<12} {'Trades':>8} {'Status':<12}")
        print(f"  {'-'*12} {'-'*12} {'-'*8} {'-'*12}")

        aligned = 0
        different = 0
        for row in rows:
            oracle_dir, ml_dir, trades, status = row
            if 'ALIGNED' in status:
                aligned += trades
            else:
                different += trades
            print(f"  {oracle_dir:<12} {ml_dir:<12} {trades:>8} {status}")

        if different == 0 and aligned > 0:
            print(f"\n  ✅ SUCCESS: Prophet direction matches ML in all {aligned} trades!")
            print("      The fix is working correctly.")
        elif aligned > 0:
            print(f"\n  ⚠️  {different} trades where Prophet != ML direction")
    else:
        print(f"\n  No trades with both Prophet and ML direction since {FIX_DATE}")

    # 5. LAST 5 TRADES DETAIL
    print("\n" + "=" * 70)
    print("5. LAST 5 TRADES (Verify Direction Chain)")
    print("=" * 70)

    cur.execute("""
        SELECT
            entry_time,
            spread_type,
            ml_direction,
            oracle_direction,
            realized_pnl,
            close_reason
        FROM gideon_closed_trades
        ORDER BY entry_time DESC
        LIMIT 5
    """)

    rows = cur.fetchall()
    if rows:
        print(f"\n  {'Entry Time':<20} {'Spread':<12} {'ML Dir':<10} {'Prophet':<10} {'P&L':>10} {'Close Reason':<20}")
        print(f"  {'-'*20} {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*20}")
        for row in rows:
            entry, spread, ml_dir, oracle_dir, pnl, reason = row
            entry_str = entry.strftime('%Y-%m-%d %H:%M') if entry else 'N/A'
            print(f"  {entry_str:<20} {spread or 'N/A':<12} {ml_dir or 'N/A':<10} {oracle_dir or 'N/A':<10} ${pnl or 0:>8,.2f} {(reason or 'N/A')[:20]:<20}")

    # 6. EXPECTED vs ACTUAL
    print("\n" + "=" * 70)
    print("6. EXPECTED IMPROVEMENT")
    print("=" * 70)

    print("""
  Based on your analysis data:

  BEFORE FIX:
  - Direction mismatch trades (ML=BULLISH, BEAR_PUT): 0% WR, -$32,575
  - Overall: 14.7% WR, -$663,946

  AFTER FIX (Expected):
  - No more direction mismatches
  - BULL_CALL when ML=BULLISH: ~53% WR (from post-fix sample)
  - Expected: Profitable trading

  MONITORING:
  - Check this report daily for the first week
  - Win rate should trend toward 50%+
  - Direction mismatches should be 0
    """)

    cur.close()
    conn.close()

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_verification()
