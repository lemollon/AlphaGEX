#!/usr/bin/env python3
"""
VALOR (HERACLES) Loss Analysis Script
=====================================
Investigates why losses are larger than wins despite good win rate.

Run on Render: python scripts/analyze_valor_losses.py
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_adapter import get_connection
except ImportError:
    print("ERROR: Cannot import database_adapter. Run from project root.")
    sys.exit(1)


def analyze_closed_trades():
    """Analyze all closed trades for loss patterns."""
    print("\n" + "=" * 70)
    print("VALOR (HERACLES) CLOSED TRADES ANALYSIS")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # Get all closed trades with full details
    cursor.execute("""
        SELECT
            position_id,
            direction,
            entry_price,
            exit_price,
            contracts,
            realized_pnl,
            open_time,
            close_time,
            close_reason,
            stop_type,
            stop_points_used,
            gamma_regime
        FROM heracles_closed_trades
        ORDER BY close_time DESC
    """)

    trades = cursor.fetchall()
    conn.close()

    if not trades:
        print("No closed trades found!")
        return

    print(f"\nTotal Closed Trades: {len(trades)}")

    # Separate wins and losses
    wins = []
    losses = []

    for trade in trades:
        pos_id, direction, entry, exit_price, contracts, pnl, open_time, close_time, close_reason, stop_type, stop_points, gamma = trade

        trade_data = {
            "id": pos_id,
            "direction": direction,
            "entry": entry,
            "exit": exit_price,
            "contracts": contracts,
            "pnl": pnl or 0,
            "open_time": open_time,
            "close_time": close_time,
            "close_reason": close_reason,
            "stop_type": stop_type,
            "stop_points": stop_points,
            "gamma": gamma,
            "duration_seconds": (close_time - open_time).total_seconds() if close_time and open_time else 0,
            "points_moved": abs(exit_price - entry) if exit_price and entry else 0
        }

        if pnl and pnl > 0:
            wins.append(trade_data)
        else:
            losses.append(trade_data)

    # Basic stats
    total_pnl = sum(t["pnl"] for t in wins + losses)
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    print(f"\n--- BASIC STATS ---")
    print(f"Win Rate: {win_rate:.1f}% ({len(wins)} wins, {len(losses)} losses)")
    print(f"Total P&L: ${total_pnl:.2f}")

    # Win analysis
    if wins:
        avg_win = sum(t["pnl"] for t in wins) / len(wins)
        max_win = max(t["pnl"] for t in wins)
        min_win = min(t["pnl"] for t in wins)
        avg_win_duration = sum(t["duration_seconds"] for t in wins) / len(wins)
        avg_win_points = sum(t["points_moved"] for t in wins) / len(wins)

        print(f"\n--- WINS ---")
        print(f"Average Win: ${avg_win:.2f}")
        print(f"Max Win: ${max_win:.2f}")
        print(f"Min Win: ${min_win:.2f}")
        print(f"Avg Duration: {avg_win_duration:.0f} seconds ({avg_win_duration/60:.1f} min)")
        print(f"Avg Points Captured: {avg_win_points:.2f} pts")

    # Loss analysis
    if losses:
        avg_loss = sum(t["pnl"] for t in losses) / len(losses)
        max_loss = min(t["pnl"] for t in losses)  # Most negative
        min_loss = max(t["pnl"] for t in losses)  # Least negative
        avg_loss_duration = sum(t["duration_seconds"] for t in losses) / len(losses)
        avg_loss_points = sum(t["points_moved"] for t in losses) / len(losses)

        print(f"\n--- LOSSES ---")
        print(f"Average Loss: ${avg_loss:.2f}")
        print(f"Max Loss: ${max_loss:.2f}")
        print(f"Min Loss: ${min_loss:.2f}")
        print(f"Avg Duration: {avg_loss_duration:.0f} seconds ({avg_loss_duration/60:.1f} min)")
        print(f"Avg Points Lost: {avg_loss_points:.2f} pts")

    # Risk/Reward ratio
    if wins and losses:
        avg_win_amt = sum(t["pnl"] for t in wins) / len(wins)
        avg_loss_amt = abs(sum(t["pnl"] for t in losses) / len(losses))
        rr_ratio = avg_win_amt / avg_loss_amt if avg_loss_amt > 0 else 0

        print(f"\n--- RISK/REWARD ---")
        print(f"Avg Win: ${avg_win_amt:.2f}")
        print(f"Avg Loss: ${avg_loss_amt:.2f}")
        print(f"Win/Loss Ratio: {rr_ratio:.2f}:1")
        print(f"Required Win Rate for Breakeven: {100/(1+rr_ratio):.1f}%")

        # Profit factor
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        print(f"Profit Factor: {profit_factor:.2f} (>1 = profitable)")

    return trades, wins, losses


def analyze_loss_timing():
    """Analyze when losses occur - looking for gaps between scans."""
    print("\n" + "=" * 70)
    print("LOSS TIMING ANALYSIS - SCAN GAP INVESTIGATION")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # Get losses with detailed timing
    cursor.execute("""
        SELECT
            position_id,
            direction,
            entry_price,
            exit_price,
            realized_pnl,
            open_time,
            close_time,
            close_reason,
            stop_points_used
        FROM heracles_closed_trades
        WHERE realized_pnl < 0
        ORDER BY close_time DESC
    """)

    losses = cursor.fetchall()
    conn.close()

    if not losses:
        print("No losing trades found!")
        return

    print(f"\nAnalyzing {len(losses)} losing trades...\n")

    # Categorize losses by close reason
    by_reason = {}
    for loss in losses:
        pos_id, direction, entry, exit_price, pnl, open_time, close_time, reason, stop_pts = loss
        reason = reason or "UNKNOWN"

        if reason not in by_reason:
            by_reason[reason] = {"count": 0, "total_loss": 0, "losses": []}

        by_reason[reason]["count"] += 1
        by_reason[reason]["total_loss"] += pnl

        # Calculate how far past stop the exit was
        if direction == "LONG":
            expected_stop_price = entry - (stop_pts or 2.5)
            slippage = expected_stop_price - exit_price if exit_price else 0
        else:  # SHORT
            expected_stop_price = entry + (stop_pts or 2.5)
            slippage = exit_price - expected_stop_price if exit_price else 0

        by_reason[reason]["losses"].append({
            "id": pos_id,
            "pnl": pnl,
            "duration": (close_time - open_time).total_seconds() if close_time and open_time else 0,
            "slippage_points": slippage,
            "entry": entry,
            "exit": exit_price,
            "stop_pts": stop_pts
        })

    print("--- LOSSES BY CLOSE REASON ---")
    for reason, data in sorted(by_reason.items(), key=lambda x: x[1]["total_loss"]):
        avg_loss = data["total_loss"] / data["count"]
        avg_slippage = sum(l["slippage_points"] for l in data["losses"]) / len(data["losses"])

        print(f"\n{reason}:")
        print(f"  Count: {data['count']}")
        print(f"  Total Loss: ${data['total_loss']:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        print(f"  Avg Slippage Past Stop: {avg_slippage:.2f} points")

        # Show worst losses
        worst = sorted(data["losses"], key=lambda x: x["pnl"])[:3]
        if worst:
            print(f"  Worst losses: {[f'${l['pnl']:.2f} (slippage: {l['slippage_points']:.2f}pts)' for l in worst]}")


def simulate_tighter_stops():
    """Simulate what would happen with tighter stops."""
    print("\n" + "=" * 70)
    print("SIMULATION: TIGHTER STOP LOSS SCENARIOS")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # Get all closed trades
    cursor.execute("""
        SELECT
            direction,
            entry_price,
            exit_price,
            contracts,
            realized_pnl,
            stop_points_used
        FROM heracles_closed_trades
    """)

    trades = cursor.fetchall()
    conn.close()

    if not trades:
        print("No trades to analyze!")
        return

    MES_POINT_VALUE = 5.0  # $5 per point per contract

    # Current actual results
    current_pnl = sum(t[4] or 0 for t in trades)

    print(f"\nCurrent Results: ${current_pnl:.2f} ({len(trades)} trades)")

    # Simulate different stop levels
    stop_scenarios = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

    print("\n--- STOP LEVEL SIMULATIONS ---")
    print("(Assumes stop would have been hit exactly at that level)")
    print()

    for stop_pts in stop_scenarios:
        simulated_pnl = 0
        wins = 0
        losses = 0

        for trade in trades:
            direction, entry, exit_price, contracts, actual_pnl, used_stop = trade
            contracts = contracts or 1

            if not entry or not exit_price:
                continue

            # Calculate points moved
            if direction == "LONG":
                points_moved = exit_price - entry
            else:
                points_moved = entry - exit_price

            # Apply simulated stop
            if points_moved <= -stop_pts:
                # Would have been stopped out
                sim_pnl = -stop_pts * MES_POINT_VALUE * contracts
                losses += 1
            else:
                # Trade would have played out normally
                sim_pnl = points_moved * MES_POINT_VALUE * contracts
                if sim_pnl > 0:
                    wins += 1
                else:
                    losses += 1

            simulated_pnl += sim_pnl

        total_trades = wins + losses
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0
        improvement = simulated_pnl - current_pnl

        print(f"Stop at {stop_pts:.1f} pts: ${simulated_pnl:.2f} (Win Rate: {win_rate:.1f}%) [Δ: ${improvement:+.2f}]")


def simulate_time_based_exits():
    """Simulate exiting positions after X seconds regardless of P&L."""
    print("\n" + "=" * 70)
    print("SIMULATION: TIME-BASED EXIT SCENARIOS")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # We need tick data to do this properly, but we can estimate
    # based on average movement rates

    cursor.execute("""
        SELECT
            direction,
            entry_price,
            exit_price,
            contracts,
            realized_pnl,
            open_time,
            close_time
        FROM heracles_closed_trades
        WHERE open_time IS NOT NULL AND close_time IS NOT NULL
    """)

    trades = cursor.fetchall()
    conn.close()

    if not trades:
        print("No trades with timing data!")
        return

    print(f"\nAnalyzing {len(trades)} trades with timing data...")

    # Calculate average points per minute of movement
    total_points_per_min = 0
    count = 0

    for trade in trades:
        direction, entry, exit_price, contracts, pnl, open_time, close_time = trade
        if not entry or not exit_price or not open_time or not close_time:
            continue

        duration_min = (close_time - open_time).total_seconds() / 60
        if duration_min > 0:
            points_moved = abs(exit_price - entry)
            points_per_min = points_moved / duration_min
            total_points_per_min += points_per_min
            count += 1

    avg_points_per_min = total_points_per_min / count if count > 0 else 0

    print(f"Average market movement: {avg_points_per_min:.3f} points/minute")
    print(f"\n--- TIME-BASED EXIT ANALYSIS ---")
    print("(Based on average movement rate)")

    # Show duration distribution
    durations = []
    for trade in trades:
        _, _, _, _, pnl, open_time, close_time = trade
        if open_time and close_time:
            dur_sec = (close_time - open_time).total_seconds()
            durations.append({"duration": dur_sec, "pnl": pnl or 0})

    if durations:
        # Bucket by duration
        buckets = {
            "< 30s": {"trades": 0, "pnl": 0, "wins": 0},
            "30s-1m": {"trades": 0, "pnl": 0, "wins": 0},
            "1m-2m": {"trades": 0, "pnl": 0, "wins": 0},
            "2m-5m": {"trades": 0, "pnl": 0, "wins": 0},
            "> 5m": {"trades": 0, "pnl": 0, "wins": 0},
        }

        for d in durations:
            dur = d["duration"]
            pnl = d["pnl"]

            if dur < 30:
                bucket = "< 30s"
            elif dur < 60:
                bucket = "30s-1m"
            elif dur < 120:
                bucket = "1m-2m"
            elif dur < 300:
                bucket = "2m-5m"
            else:
                bucket = "> 5m"

            buckets[bucket]["trades"] += 1
            buckets[bucket]["pnl"] += pnl
            if pnl > 0:
                buckets[bucket]["wins"] += 1

        print("\nP&L by Trade Duration:")
        print("-" * 50)
        for bucket, data in buckets.items():
            if data["trades"] > 0:
                win_rate = data["wins"] / data["trades"] * 100
                avg_pnl = data["pnl"] / data["trades"]
                print(f"{bucket:>8}: {data['trades']:3} trades, ${data['pnl']:>8.2f} total, ${avg_pnl:>6.2f} avg, {win_rate:.0f}% wins")


def check_scan_frequency_impact():
    """Analyze if faster scanning would help."""
    print("\n" + "=" * 70)
    print("SCAN FREQUENCY ANALYSIS")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # Check scan activity to see how often we're scanning
    cursor.execute("""
        SELECT
            scan_time,
            signal_type,
            entry_price,
            mes_price
        FROM heracles_scan_activity
        ORDER BY scan_time DESC
        LIMIT 100
    """)

    scans = cursor.fetchall()
    conn.close()

    if len(scans) < 2:
        print("Not enough scan data!")
        return

    # Calculate time between scans
    gaps = []
    for i in range(len(scans) - 1):
        gap = (scans[i][0] - scans[i+1][0]).total_seconds()
        gaps.append(gap)

    avg_gap = sum(gaps) / len(gaps)
    max_gap = max(gaps)
    min_gap = min(gaps)

    print(f"\nScan Frequency (last 100 scans):")
    print(f"  Average gap: {avg_gap:.1f} seconds ({avg_gap/60:.2f} min)")
    print(f"  Max gap: {max_gap:.1f} seconds ({max_gap/60:.2f} min)")
    print(f"  Min gap: {min_gap:.1f} seconds")

    # Price movement between scans
    price_moves = []
    for i in range(len(scans) - 1):
        if scans[i][3] and scans[i+1][3]:
            move = abs(scans[i][3] - scans[i+1][3])
            price_moves.append(move)

    if price_moves:
        avg_move = sum(price_moves) / len(price_moves)
        max_move = max(price_moves)

        print(f"\nPrice Movement Between Scans:")
        print(f"  Average: {avg_move:.2f} points")
        print(f"  Max: {max_move:.2f} points")
        print(f"  At $5/pt, max gap move = ${max_move * 5:.2f} per contract")

    print("\n--- RECOMMENDATION ---")
    if avg_gap > 60:
        print("⚠️  Average scan gap is > 1 minute. Consider reducing scan interval.")
        print("    Current 1-min scans mean stops can be overshot by several points.")
    elif avg_gap > 30:
        print("⚠️  Average scan gap is 30-60 seconds. Could benefit from faster scanning.")
    else:
        print("✅ Scan frequency looks reasonable (< 30 seconds avg).")

    if max_move > 2:
        print(f"\n⚠️  Max price move between scans was {max_move:.2f} points!")
        print("    This could cause stops to be hit significantly past the target.")
        print("    Recommendation: Scan every 15-30 seconds instead of 1 minute.")


def main():
    print("=" * 70)
    print("VALOR (HERACLES) LOSS INVESTIGATION")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # Run all analyses
    analyze_closed_trades()
    analyze_loss_timing()
    simulate_tighter_stops()
    simulate_time_based_exits()
    check_scan_frequency_impact()

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
