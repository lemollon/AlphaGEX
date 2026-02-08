#!/usr/bin/env python3
"""
VALOR Profit Target Backtest
================================

Simulates different profit target levels against historical trades
using high/low price data to determine if targets would have been hit.

Usage:
    python scripts/test_profit_targets.py
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

# MES contract specs
MES_POINT_VALUE = 5.0


def backtest_profit_targets():
    """Backtest different profit target levels against historical trades."""

    print("=" * 80)
    print("VALOR PROFIT TARGET BACKTEST")
    print("=" * 80)

    conn = get_connection()
    cursor = conn.cursor()

    # Get all closed trades with high/low data
    cursor.execute("""
        SELECT
            position_id,
            direction,
            contracts,
            entry_price,
            exit_price,
            realized_pnl,
            high_price_since_entry,
            low_price_since_entry,
            close_reason
        FROM valor_closed_trades
        WHERE high_price_since_entry > 0 AND low_price_since_entry > 0
        ORDER BY close_time DESC
    """)

    trades = cursor.fetchall()

    if not trades:
        print("\nNo trades with high/low data available for backtesting.")
        print("High/low tracking may have been added recently.")

        # Check how many trades exist without high/low data
        cursor.execute("SELECT COUNT(*) FROM valor_closed_trades")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM valor_closed_trades
            WHERE high_price_since_entry > 0 AND low_price_since_entry > 0
        """)
        with_data = cursor.fetchone()[0]

        print(f"\nTotal closed trades: {total}")
        print(f"Trades with high/low data: {with_data}")
        print("\nNeed more trades with high/low tracking to run this analysis.")
        return

    print(f"\nAnalyzing {len(trades)} trades with high/low data...")

    # Test different profit target levels
    target_levels = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]

    # Also test different stop levels
    stop_levels = [2.0, 2.5, 3.0]

    print("\n" + "=" * 80)
    print("CURRENT PERFORMANCE (No Profit Target)")
    print("=" * 80)

    # Calculate current stats
    total_pnl = sum(float(t[5]) for t in trades)
    wins = sum(1 for t in trades if float(t[5]) > 0)
    losses = len(trades) - wins
    avg_win = sum(float(t[5]) for t in trades if float(t[5]) > 0) / wins if wins > 0 else 0
    avg_loss = sum(float(t[5]) for t in trades if float(t[5]) < 0) / losses if losses > 0 else 0

    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate: {wins/len(trades)*100:.1f}%")
    print(f"Total P&L: ${total_pnl:.2f}")
    print(f"Avg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
    print(f"Risk/Reward: {abs(avg_win/avg_loss):.2f}:1" if avg_loss != 0 else "N/A")

    print("\n" + "=" * 80)
    print("SIMULATED PROFIT TARGETS")
    print("=" * 80)

    results = []

    for target in target_levels:
        sim_pnl = 0
        sim_wins = 0
        sim_losses = 0
        target_hits = 0

        for trade in trades:
            pos_id, direction, contracts, entry, exit_price, actual_pnl, high, low, reason = trade

            entry = float(entry)
            contracts = int(contracts)
            high = float(high)
            low = float(low)
            actual_pnl = float(actual_pnl)

            # Check if profit target would have been hit
            if direction == "SHORT":
                # For shorts, profit target is below entry
                target_price = entry - target
                would_hit_target = low <= target_price
            else:  # LONG
                # For longs, profit target is above entry
                target_price = entry + target
                would_hit_target = high >= target_price

            if would_hit_target:
                # Would have exited at profit target
                target_hits += 1
                pnl = target * contracts * MES_POINT_VALUE
                sim_pnl += pnl
                sim_wins += 1
            else:
                # Would have hit stop or actual exit
                sim_pnl += actual_pnl
                if actual_pnl > 0:
                    sim_wins += 1
                else:
                    sim_losses += 1

        sim_total = sim_wins + sim_losses
        sim_win_rate = sim_wins / sim_total * 100 if sim_total > 0 else 0
        improvement = sim_pnl - total_pnl

        results.append({
            'target': target,
            'pnl': sim_pnl,
            'wins': sim_wins,
            'losses': sim_losses,
            'win_rate': sim_win_rate,
            'target_hits': target_hits,
            'improvement': improvement
        })

        better = "BETTER" if improvement > 0 else "WORSE"
        print(f"\n{target:.1f} Point Target:")
        print(f"  Target Hits: {target_hits}/{len(trades)} ({target_hits/len(trades)*100:.1f}%)")
        print(f"  Simulated P&L: ${sim_pnl:.2f} ({better}: ${improvement:+.2f})")
        print(f"  Win Rate: {sim_win_rate:.1f}%")

    print("\n" + "=" * 80)
    print("COMBINED: TIGHTER STOPS + PROFIT TARGETS")
    print("=" * 80)

    # Simulate with tighter 2.5 point stop + various targets
    new_stop = 2.5

    for target in [4.0, 5.0, 6.0]:
        sim_pnl = 0
        sim_wins = 0
        sim_losses = 0
        target_hits = 0
        stop_hits = 0

        for trade in trades:
            pos_id, direction, contracts, entry, exit_price, actual_pnl, high, low, reason = trade

            entry = float(entry)
            contracts = int(contracts)
            high = float(high)
            low = float(low)

            if direction == "SHORT":
                target_price = entry - target
                stop_price = entry + new_stop
                would_hit_target = low <= target_price
                would_hit_stop = high >= stop_price
            else:
                target_price = entry + target
                stop_price = entry - new_stop
                would_hit_target = high >= target_price
                would_hit_stop = low <= stop_price

            # Determine which would hit first (simplified: check if target reachable before stop)
            if would_hit_target and not would_hit_stop:
                # Clean target hit
                target_hits += 1
                pnl = target * contracts * MES_POINT_VALUE
                sim_pnl += pnl
                sim_wins += 1
            elif would_hit_stop and not would_hit_target:
                # Clean stop hit
                stop_hits += 1
                pnl = -new_stop * contracts * MES_POINT_VALUE
                sim_pnl += pnl
                sim_losses += 1
            elif would_hit_target and would_hit_stop:
                # Both levels touched - use actual outcome as proxy
                # (In reality we'd need tick data to know which hit first)
                if float(actual_pnl) > 0:
                    target_hits += 1
                    pnl = target * contracts * MES_POINT_VALUE
                    sim_pnl += pnl
                    sim_wins += 1
                else:
                    stop_hits += 1
                    pnl = -new_stop * contracts * MES_POINT_VALUE
                    sim_pnl += pnl
                    sim_losses += 1
            else:
                # Neither hit - would still be open (use trailing stop logic)
                # Use actual outcome scaled
                sim_pnl += float(actual_pnl)
                if float(actual_pnl) > 0:
                    sim_wins += 1
                else:
                    sim_losses += 1

        sim_total = sim_wins + sim_losses
        sim_win_rate = sim_wins / sim_total * 100 if sim_total > 0 else 0
        improvement = sim_pnl - total_pnl

        avg_sim_win = (target * 4 * MES_POINT_VALUE)  # Assuming 4 contracts avg
        avg_sim_loss = (new_stop * 4 * MES_POINT_VALUE)
        rr_ratio = target / new_stop

        print(f"\n2.5pt Stop + {target:.0f}pt Target (R/R = {rr_ratio:.1f}:1):")
        print(f"  Target Hits: {target_hits}, Stop Hits: {stop_hits}")
        print(f"  Simulated P&L: ${sim_pnl:.2f} (vs actual ${total_pnl:.2f})")
        print(f"  Change: ${improvement:+.2f} ({improvement/abs(total_pnl)*100:+.1f}%)" if total_pnl != 0 else f"  Change: ${improvement:+.2f}")
        print(f"  Win Rate: {sim_win_rate:.1f}%")

    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    # Find best performing configuration
    best = max(results, key=lambda x: x['pnl'])

    if best['improvement'] > 0:
        print(f"\nBest profit target: {best['target']:.1f} points")
        print(f"Would improve P&L by: ${best['improvement']:.2f}")
        print(f"Target hit rate: {best['target_hits']}/{len(trades)} trades")
    else:
        print("\nNo profit target improves results.")
        print("Recommendation: Use tighter stops only, let winners run.")

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    backtest_profit_targets()
