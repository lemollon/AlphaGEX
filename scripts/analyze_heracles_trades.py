#!/usr/bin/env python3
"""
HERACLES Trade Analysis Script
==============================

Run on Render shell to analyze closed trades and identify issues
with the trading logic (e.g., losers bigger than winners).

Usage:
    python scripts/analyze_heracles_trades.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


def analyze_heracles_trades():
    """Pull and analyze all HERACLES closed trades"""

    print("=" * 80)
    print("HERACLES TRADE ANALYSIS")
    print("=" * 80)
    print(f"Analysis Time: {datetime.now().isoformat()}")
    print()

    conn = get_connection()
    cursor = conn.cursor()

    # =========================================================================
    # 1. OVERALL STATISTICS
    # =========================================================================
    print("\n" + "=" * 80)
    print("1. OVERALL STATISTICS")
    print("=" * 80)

    cursor.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
            MAX(realized_pnl) as best_trade,
            MIN(realized_pnl) as worst_trade,
            SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as gross_profit,
            ABS(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END)) as gross_loss
        FROM heracles_closed_trades
    """)

    row = cursor.fetchone()
    if row:
        total, wins, losses, total_pnl, avg_pnl, avg_win, avg_loss, best, worst, gross_profit, gross_loss = row
        win_rate = (wins / total * 100) if total > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

        print(f"Total Trades:    {total}")
        print(f"Winners:         {wins} ({win_rate:.1f}%)")
        print(f"Losers:          {losses} ({100-win_rate:.1f}%)")
        print(f"Total P&L:       ${float(total_pnl or 0):.2f}")
        print(f"Avg Trade P&L:   ${float(avg_pnl or 0):.2f}")
        print(f"Avg Winner:      ${float(avg_win or 0):.2f}")
        print(f"Avg Loser:       ${float(avg_loss or 0):.2f}")
        print(f"Best Trade:      ${float(best or 0):.2f}")
        print(f"Worst Trade:     ${float(worst or 0):.2f}")
        print(f"Gross Profit:    ${float(gross_profit or 0):.2f}")
        print(f"Gross Loss:      ${float(gross_loss or 0):.2f}")
        print(f"Profit Factor:   {profit_factor:.2f}")

        # Risk/Reward Analysis
        if avg_win and avg_loss:
            risk_reward = abs(float(avg_win) / float(avg_loss))
            print(f"Risk/Reward:     {risk_reward:.2f}:1")

            # Expected Value calculation
            ev = (win_rate/100 * float(avg_win)) + ((100-win_rate)/100 * float(avg_loss))
            print(f"Expected Value:  ${ev:.2f} per trade")

    # =========================================================================
    # 2. ANALYSIS BY GAMMA REGIME
    # =========================================================================
    print("\n" + "=" * 80)
    print("2. ANALYSIS BY GAMMA REGIME")
    print("=" * 80)

    cursor.execute("""
        SELECT
            gamma_regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss
        FROM heracles_closed_trades
        GROUP BY gamma_regime
        ORDER BY gamma_regime
    """)

    for row in cursor.fetchall():
        regime, trades, wins, total_pnl, avg_pnl, avg_win, avg_loss = row
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"\n{regime or 'UNKNOWN'} GAMMA:")
        print(f"  Trades:     {trades}")
        print(f"  Win Rate:   {win_rate:.1f}%")
        print(f"  Total P&L:  ${float(total_pnl or 0):.2f}")
        print(f"  Avg Win:    ${float(avg_win or 0):.2f}")
        print(f"  Avg Loss:   ${float(avg_loss or 0):.2f}")

    # =========================================================================
    # 3. ANALYSIS BY CLOSE REASON
    # =========================================================================
    print("\n" + "=" * 80)
    print("3. ANALYSIS BY CLOSE REASON")
    print("=" * 80)

    cursor.execute("""
        SELECT
            close_reason,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl
        FROM heracles_closed_trades
        GROUP BY close_reason
        ORDER BY trades DESC
    """)

    for row in cursor.fetchall():
        reason, trades, wins, total_pnl, avg_pnl = row
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"\n{reason or 'UNKNOWN'}:")
        print(f"  Trades:    {trades}")
        print(f"  Win Rate:  {win_rate:.1f}%")
        print(f"  Total P&L: ${float(total_pnl or 0):.2f}")
        print(f"  Avg P&L:   ${float(avg_pnl or 0):.2f}")

    # =========================================================================
    # 4. ANALYSIS BY SIGNAL SOURCE
    # =========================================================================
    print("\n" + "=" * 80)
    print("4. ANALYSIS BY SIGNAL SOURCE")
    print("=" * 80)

    cursor.execute("""
        SELECT
            signal_source,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss
        FROM heracles_closed_trades
        GROUP BY signal_source
        ORDER BY trades DESC
    """)

    for row in cursor.fetchall():
        source, trades, wins, total_pnl, avg_pnl, avg_win, avg_loss = row
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"\n{source or 'UNKNOWN'}:")
        print(f"  Trades:    {trades}")
        print(f"  Win Rate:  {win_rate:.1f}%")
        print(f"  Total P&L: ${float(total_pnl or 0):.2f}")
        print(f"  Avg Win:   ${float(avg_win or 0):.2f}")
        print(f"  Avg Loss:  ${float(avg_loss or 0):.2f}")

    # =========================================================================
    # 5. INDIVIDUAL TRADE DETAILS (Last 50)
    # =========================================================================
    print("\n" + "=" * 80)
    print("5. LAST 50 CLOSED TRADES")
    print("=" * 80)

    cursor.execute("""
        SELECT
            position_id,
            direction,
            contracts,
            entry_price,
            exit_price,
            realized_pnl,
            gamma_regime,
            signal_source,
            close_reason,
            vix_at_entry,
            open_time,
            close_time,
            hold_duration_minutes,
            high_price_since_entry,
            low_price_since_entry
        FROM heracles_closed_trades
        ORDER BY close_time DESC
        LIMIT 50
    """)

    columns = [desc[0] for desc in cursor.description]
    trades = [dict(zip(columns, row)) for row in cursor.fetchall()]

    print(f"\n{'ID':<12} {'DIR':<6} {'ENTRY':<10} {'EXIT':<10} {'P&L':<10} {'REGIME':<10} {'REASON':<20} {'DURATION'}")
    print("-" * 100)

    for t in trades:
        pos_id = t['position_id'][-8:] if t['position_id'] else 'N/A'
        direction = t['direction'] or 'N/A'
        entry = float(t['entry_price']) if t['entry_price'] else 0
        exit_p = float(t['exit_price']) if t['exit_price'] else 0
        pnl = float(t['realized_pnl']) if t['realized_pnl'] else 0
        regime = (t['gamma_regime'] or 'N/A')[:8]
        reason = (t['close_reason'] or 'N/A')[:18]
        duration = t['hold_duration_minutes'] or 0

        pnl_color = '+' if pnl >= 0 else ''
        print(f"{pos_id:<12} {direction:<6} {entry:<10.2f} {exit_p:<10.2f} {pnl_color}{pnl:<9.2f} {regime:<10} {reason:<20} {duration}m")

    # =========================================================================
    # 6. STOP LOSS ANALYSIS
    # =========================================================================
    print("\n" + "=" * 80)
    print("6. STOP LOSS ANALYSIS (from positions table)")
    print("=" * 80)

    cursor.execute("""
        SELECT
            position_id,
            direction,
            entry_price,
            initial_stop,
            current_stop,
            close_price,
            realized_pnl,
            trailing_active,
            close_reason,
            high_price_since_entry,
            low_price_since_entry
        FROM heracles_positions
        WHERE status != 'open'
        ORDER BY close_time DESC
        LIMIT 20
    """)

    print(f"\n{'ID':<10} {'DIR':<6} {'ENTRY':<9} {'I_STOP':<9} {'C_STOP':<9} {'EXIT':<9} {'P&L':<8} {'TRAIL':<6} {'REASON'}")
    print("-" * 100)

    for row in cursor.fetchall():
        pos_id, direction, entry, initial_stop, current_stop, close_price, pnl, trailing, reason, high, low = row
        pos_id = pos_id[-8:] if pos_id else 'N/A'
        entry = float(entry) if entry else 0
        i_stop = float(initial_stop) if initial_stop else 0
        c_stop = float(current_stop) if current_stop else 0
        close_p = float(close_price) if close_price else 0
        pnl_val = float(pnl) if pnl else 0
        trail = 'Yes' if trailing else 'No'
        reason = (reason or 'N/A')[:15]

        # Calculate stop distance
        stop_dist = abs(entry - i_stop)

        pnl_sign = '+' if pnl_val >= 0 else ''
        print(f"{pos_id:<10} {direction:<6} {entry:<9.2f} {i_stop:<9.2f} {c_stop:<9.2f} {close_p:<9.2f} {pnl_sign}{pnl_val:<7.2f} {trail:<6} {reason}")

    # =========================================================================
    # 7. CONFIG CHECK
    # =========================================================================
    print("\n" + "=" * 80)
    print("7. CURRENT HERACLES CONFIG")
    print("=" * 80)

    cursor.execute("""
        SELECT config_key, config_value
        FROM heracles_config
        ORDER BY config_key
    """)

    for key, value in cursor.fetchall():
        print(f"  {key}: {value}")

    # =========================================================================
    # 8. OPEN POSITIONS CHECK
    # =========================================================================
    print("\n" + "=" * 80)
    print("8. CURRENT OPEN POSITIONS")
    print("=" * 80)

    cursor.execute("""
        SELECT
            position_id,
            direction,
            contracts,
            entry_price,
            initial_stop,
            current_stop,
            trailing_active,
            gamma_regime,
            open_time
        FROM heracles_positions
        WHERE status = 'open'
        ORDER BY open_time DESC
    """)

    open_positions = cursor.fetchall()
    print(f"\nTotal Open Positions: {len(open_positions)}")

    if open_positions:
        print(f"\n{'ID':<10} {'DIR':<6} {'QTY':<5} {'ENTRY':<10} {'I_STOP':<10} {'C_STOP':<10} {'TRAIL':<6} {'REGIME':<10} {'OPEN TIME'}")
        print("-" * 100)

        for row in open_positions:
            pos_id, direction, contracts, entry, initial_stop, current_stop, trailing, regime, open_time = row
            pos_id = pos_id[-8:] if pos_id else 'N/A'
            entry = float(entry) if entry else 0
            i_stop = float(initial_stop) if initial_stop else 0
            c_stop = float(current_stop) if current_stop else 0
            trail = 'Yes' if trailing else 'No'
            regime = (regime or 'N/A')[:8]
            open_str = open_time.strftime('%m/%d %H:%M') if open_time else 'N/A'

            print(f"{pos_id:<10} {direction:<6} {contracts:<5} {entry:<10.2f} {i_stop:<10.2f} {c_stop:<10.2f} {trail:<6} {regime:<10} {open_str}")

    # =========================================================================
    # 9. RISK/REWARD ISSUE DETECTION
    # =========================================================================
    print("\n" + "=" * 80)
    print("9. RISK/REWARD ISSUE DETECTION")
    print("=" * 80)

    # Check if losers are consistently bigger than winners
    cursor.execute("""
        SELECT
            direction,
            AVG(CASE WHEN realized_pnl > 0 THEN ABS(exit_price - entry_price) END) as avg_win_points,
            AVG(CASE WHEN realized_pnl < 0 THEN ABS(exit_price - entry_price) END) as avg_loss_points,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win_dollars,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss_dollars
        FROM heracles_closed_trades
        GROUP BY direction
    """)

    for row in cursor.fetchall():
        direction, win_pts, loss_pts, win_dol, loss_dol = row
        print(f"\n{direction or 'UNKNOWN'} Trades:")
        print(f"  Avg Win (points):   {float(win_pts or 0):.2f}")
        print(f"  Avg Loss (points):  {float(loss_pts or 0):.2f}")
        print(f"  Avg Win ($):        ${float(win_dol or 0):.2f}")
        print(f"  Avg Loss ($):       ${float(loss_dol or 0):.2f}")

        if win_pts and loss_pts:
            ratio = float(win_pts) / float(loss_pts)
            print(f"  Point Ratio:        {ratio:.2f} (win/loss)")

            if ratio < 1:
                print(f"  ⚠️ WARNING: Winners are smaller than losers!")

    # =========================================================================
    # 10. RECOMMENDATIONS
    # =========================================================================
    print("\n" + "=" * 80)
    print("10. ANALYSIS SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    # Re-fetch key metrics
    cursor.execute("""
        SELECT
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
            COUNT(*) as total
        FROM heracles_closed_trades
    """)
    avg_win, avg_loss, total = cursor.fetchone()

    if avg_win and avg_loss:
        avg_win = float(avg_win)
        avg_loss = float(avg_loss)

        print(f"\nKey Finding: Avg Win = ${avg_win:.2f}, Avg Loss = ${avg_loss:.2f}")

        if abs(avg_loss) > avg_win:
            print("\n⚠️ ISSUE DETECTED: Losers are bigger than winners!")
            print("\nPossible causes and fixes:")
            print("  1. Stop loss too wide (3 points = $15 per contract)")
            print("     → Consider tighter stop: 2 points = $10")
            print("  2. Not trailing stops aggressively enough")
            print("     → Current: Trail at 1 point after +2 pts profit")
            print("     → Consider: Trail at 0.5 points")
            print("  3. Exiting winners too early")
            print("     → Check if trailing stop is activating properly")
            print("  4. Position sizing issue with stop distance")
            print("     → Verify ATR-based stop is not too wide")
        else:
            print("\n✅ Risk/Reward ratio appears healthy")

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    analyze_heracles_trades()
