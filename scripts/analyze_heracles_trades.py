#!/usr/bin/env python3
"""
HERACLES Trade Analysis Script
==============================

Analyzes closed trades to understand stop loss impact and optimize parameters.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


def analyze_heracles_trades():
    """Main analysis function"""
    print("=" * 70)
    print("HERACLES (VALOR) TRADE ANALYSIS")
    print("=" * 70)
    print(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Overall Performance
    print("\n" + "=" * 70)
    print("1. OVERALL PERFORMANCE")
    print("=" * 70)

    cursor.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss
        FROM heracles_closed_trades
    """)
    row = cursor.fetchone()

    if not row or row[0] == 0:
        print("No closed trades found!")
        return

    total, wins, losses, total_pnl, avg_pnl, avg_win, avg_loss = row
    win_rate = (wins / total * 100) if total > 0 else 0

    print(f"Total Trades: {total}")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Losses: {losses} ({100-win_rate:.1f}%)")
    print(f"Total P&L: ${float(total_pnl or 0):.2f}")
    print(f"Avg P&L: ${float(avg_pnl or 0):.2f}")
    print(f"Avg Win: ${float(avg_win or 0):.2f}")
    print(f"Avg Loss: ${float(avg_loss or 0):.2f}")

    # 2. Close Reason Analysis
    print("\n" + "=" * 70)
    print("2. CLOSE REASON ANALYSIS (Key for Stop Loss Evaluation)")
    print("=" * 70)

    cursor.execute("""
        SELECT
            close_reason,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl
        FROM heracles_closed_trades
        GROUP BY close_reason
        ORDER BY count DESC
    """)

    print(f"\n{'Close Reason':<30} {'Count':>6} {'Wins':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print("-" * 80)

    for row in cursor.fetchall():
        reason, count, wins, total_pnl, avg_pnl = row
        win_pct = (wins / count * 100) if count > 0 else 0
        print(f"{str(reason or 'N/A'):<30} {count:>6} {wins or 0:>6} {win_pct:>6.1f}% ${float(total_pnl or 0):>10.2f} ${float(avg_pnl or 0):>9.2f}")

    # 3. Gamma Regime Performance
    print("\n" + "=" * 70)
    print("3. GAMMA REGIME PERFORMANCE")
    print("=" * 70)

    cursor.execute("""
        SELECT
            gamma_regime,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl
        FROM heracles_closed_trades
        GROUP BY gamma_regime
        ORDER BY count DESC
    """)

    print(f"\n{'Regime':<15} {'Count':>8} {'Wins':>8} {'Win%':>8} {'Total P&L':>12}")
    print("-" * 55)

    for row in cursor.fetchall():
        regime, count, wins, total_pnl = row
        win_pct = (wins / count * 100) if count > 0 else 0
        print(f"{str(regime or 'N/A'):<15} {count:>8} {wins or 0:>8} {win_pct:>7.1f}% ${float(total_pnl or 0):>10.2f}")

    # 4. Direction Analysis
    print("\n" + "=" * 70)
    print("4. DIRECTION ANALYSIS")
    print("=" * 70)

    cursor.execute("""
        SELECT
            direction,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(realized_pnl) as total_pnl
        FROM heracles_closed_trades
        GROUP BY direction
    """)

    print(f"\n{'Direction':<10} {'Count':>8} {'Wins':>8} {'Win%':>8} {'Total P&L':>12}")
    print("-" * 50)

    for row in cursor.fetchall():
        direction, count, wins, total_pnl = row
        win_pct = (wins / count * 100) if count > 0 else 0
        print(f"{str(direction):<10} {count:>8} {wins or 0:>8} {win_pct:>7.1f}% ${float(total_pnl or 0):>10.2f}")

    # 5. Recent Trades
    print("\n" + "=" * 70)
    print("5. RECENT TRADES (Last 20)")
    print("=" * 70)

    cursor.execute("""
        SELECT
            close_time,
            direction,
            gamma_regime,
            entry_price,
            exit_price,
            realized_pnl,
            close_reason,
            hold_duration_minutes
        FROM heracles_closed_trades
        ORDER BY close_time DESC
        LIMIT 20
    """)

    print(f"\n{'Time':<18} {'Dir':<6} {'Regime':<10} {'Entry':>9} {'Exit':>9} {'P&L':>9} {'Reason':<20}")
    print("-" * 95)

    for row in cursor.fetchall():
        close_time, direction, regime, entry, exit_p, pnl, reason, duration = row
        time_str = close_time.strftime('%m/%d %H:%M') if close_time else 'N/A'
        print(f"{time_str:<18} {direction:<6} {str(regime or ''):<10} {float(entry or 0):>9.2f} {float(exit_p or 0):>9.2f} ${float(pnl or 0):>8.2f} {str(reason or ''):<20}")

    # 6. MAE/MFE Analysis
    print("\n" + "=" * 70)
    print("6. PRICE EXCURSION (MAE/MFE)")
    print("=" * 70)

    cursor.execute("""
        SELECT
            direction,
            entry_price,
            exit_price,
            high_price_since_entry,
            low_price_since_entry,
            realized_pnl
        FROM heracles_closed_trades
        WHERE high_price_since_entry IS NOT NULL
          AND low_price_since_entry IS NOT NULL
          AND high_price_since_entry > 0
          AND low_price_since_entry > 0
        ORDER BY close_time DESC
    """)

    rows = cursor.fetchall()
    if rows:
        all_mae = []
        all_mfe = []
        winning_mae = []
        losing_mae = []

        for direction, entry, exit_p, high, low, pnl in rows:
            entry = float(entry)
            high = float(high)
            low = float(low)
            pnl = float(pnl or 0)

            if direction == 'LONG':
                mae = entry - low
                mfe = high - entry
            else:
                mae = high - entry
                mfe = entry - low

            all_mae.append(mae)
            all_mfe.append(mfe)
            if pnl > 0:
                winning_mae.append(mae)
            else:
                losing_mae.append(mae)

        print(f"\nTrades with price tracking: {len(rows)}")
        print(f"\nOverall:")
        print(f"  Avg MAE (drawdown): {sum(all_mae)/len(all_mae):.2f} pts (${sum(all_mae)/len(all_mae)*5:.2f})")
        print(f"  Max MAE:            {max(all_mae):.2f} pts")
        print(f"  Avg MFE (runup):    {sum(all_mfe)/len(all_mfe):.2f} pts")

        if winning_mae:
            print(f"\nWinning trades MAE: {sum(winning_mae)/len(winning_mae):.2f} pts avg")
        if losing_mae:
            print(f"Losing trades MAE:  {sum(losing_mae)/len(losing_mae):.2f} pts avg")

        print(f"\n*** STOP SURVIVAL ANALYSIS ***")
        for stop_pts in [2, 3, 4, 5, 6, 7, 8]:
            survived = sum(1 for mae in all_mae if mae <= stop_pts)
            pct = survived / len(all_mae) * 100
            print(f"  {stop_pts}-pt stop: {pct:>5.1f}% survive ({survived}/{len(all_mae)})")
    else:
        print("No price tracking data available yet.")

    # 7. Current Config
    print("\n" + "=" * 70)
    print("7. CURRENT CONFIG")
    print("=" * 70)

    cursor.execute("""
        SELECT config_key, config_value FROM heracles_config
        WHERE config_key IN (
            'initial_stop_points', 'breakeven_activation_points',
            'trailing_stop_points', 'profit_target_points'
        )
    """)

    for key, value in cursor.fetchall():
        print(f"  {key}: {value}")

    conn.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    analyze_heracles_trades()
