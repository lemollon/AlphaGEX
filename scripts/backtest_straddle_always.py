#!/usr/bin/env python3
"""
Backtest: What if HERACLES ALWAYS used straddles instead of directional trades?

This script analyzes historical scan data to simulate straddle performance
across ALL trades, not just the 9-11am window.

Run: python scripts/backtest_straddle_always.py
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

# Straddle parameters to test
STRADDLE_CONFIGS = [
    # (profit_target_pts, time_stop_min, early_exit_threshold, description)
    (15.0, 120, None, "Current: 15pt target, 2hr time stop"),
    (10.0, 60, None, "Conservative: 10pt target, 1hr time stop"),
    (20.0, 180, None, "Aggressive: 20pt target, 3hr time stop"),
    (15.0, 120, 0.5, "With early exit if move < 50% target at 50% time"),
    (10.0, 90, 0.3, "Quick scalp: 10pt, 90min, early exit at 30%"),
]

# VIX-based premium estimation (simplified)
def estimate_straddle_premium(vix: float) -> float:
    """
    Estimate ATM straddle premium in points.

    Simplified model:
    - At VIX=15: premium ≈ 2.4 pts ($12)
    - At VIX=20: premium ≈ 3.2 pts ($16)
    - At VIX=30: premium ≈ 4.8 pts ($24)
    """
    vix = max(12.0, vix)  # Floor at 12
    return (vix / 15.0) * 2.4  # Scale linearly from base


def calculate_straddle_pnl(
    entry_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    premium_pts: float,
    profit_target: float,
    time_stop_minutes: int,
    trade_duration_minutes: float,
    early_exit_threshold: Optional[float] = None
) -> Tuple[float, str, float]:
    """
    Calculate straddle P&L based on price action during the trade.

    Returns: (pnl_pts, exit_reason, exit_move)
    """
    # Calculate max move in either direction
    max_up_move = high_price - entry_price
    max_down_move = entry_price - low_price
    max_move = max(max_up_move, max_down_move)

    # Calculate move at close
    close_move = abs(close_price - entry_price)

    # Check profit target hit (assume we exit at target if reached)
    if max_move >= profit_target:
        # Hit profit target - capture 80% of move as exit value
        exit_value = profit_target * 0.80
        pnl = exit_value - premium_pts
        return pnl, "PROFIT_TARGET", profit_target

    # Check early exit (if configured)
    if early_exit_threshold and trade_duration_minutes >= (time_stop_minutes * 0.5):
        # At 50% of time, check if move is developing
        if close_move < (profit_target * early_exit_threshold):
            # Move not developing, exit early to preserve some premium
            # Assume we capture 50% of current move value
            exit_value = close_move * 0.5
            pnl = exit_value - premium_pts
            return pnl, "EARLY_EXIT", close_move

    # Time stop - exit at close price
    if trade_duration_minutes >= time_stop_minutes:
        # Time expired, exit at whatever move we have
        if close_move >= premium_pts:
            # Above breakeven
            exit_value = close_move * 0.80
        else:
            # Below breakeven - capture 50% of residual value
            exit_value = close_move * 0.5

        pnl = exit_value - premium_pts
        return pnl, "TIME_STOP", close_move

    # Trade still open (shouldn't happen in backtest)
    return 0, "OPEN", close_move


def run_backtest():
    """Run the always-straddle backtest."""
    print("=" * 70)
    print("BACKTEST: ALWAYS STRADDLE STRATEGY")
    print("=" * 70)
    print()

    conn = get_connection()
    cursor = conn.cursor()

    # Get all executed trades with price range data
    print("Fetching trade data...")
    cursor.execute("""
        SELECT
            scan_time,
            underlying_price,
            gamma_regime,
            signal_direction,
            trade_outcome,
            realized_pnl,
            vix,
            atr,
            high_price_during_trade,
            low_price_during_trade,
            close_price
        FROM heracles_scan_activity
        WHERE trade_executed = TRUE
          AND underlying_price > 0
        ORDER BY scan_time
    """)

    trades = cursor.fetchall()
    print(f"Found {len(trades)} executed trades")

    if len(trades) == 0:
        print("\nNo trades found. Let's check what data we have...")
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN trade_executed THEN 1 END) as executed,
                   COUNT(CASE WHEN trade_outcome IS NOT NULL THEN 1 END) as with_outcome
            FROM heracles_scan_activity
        """)
        row = cursor.fetchone()
        print(f"  Total scans: {row[0]}")
        print(f"  Executed: {row[1]}")
        print(f"  With outcome: {row[2]}")
        cursor.close()
        conn.close()
        return

    # Check what columns we actually have
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'heracles_scan_activity'
    """)
    columns = [row[0] for row in cursor.fetchall()]
    has_price_range = 'high_price_during_trade' in columns

    print(f"Price range tracking available: {has_price_range}")

    # If no price range data, we need to estimate from subsequent scans
    if not has_price_range:
        print("\nNo high/low price tracking - will estimate from subsequent scans...")
        return run_estimated_backtest(cursor, trades)

    # Run backtest for each configuration
    for config in STRADDLE_CONFIGS:
        profit_target, time_stop, early_exit, description = config

        print(f"\n{'='*70}")
        print(f"CONFIG: {description}")
        print(f"{'='*70}")

        results = {
            'total': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'by_regime': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'wins': 0}),
            'by_hour': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'wins': 0}),
            'exit_reasons': defaultdict(int),
        }

        for trade in trades:
            (scan_time, price, regime, direction, outcome, actual_pnl,
             vix, atr, high, low, close) = trade

            if not price or price <= 0:
                continue

            # Estimate premium based on VIX
            vix_val = float(vix) if vix else 18.0
            premium_pts = estimate_straddle_premium(vix_val)

            # Use actual price range if available, else estimate
            high_price = float(high) if high else price + 10
            low_price = float(low) if low else price - 10
            close_price = float(close) if close else price

            # Assume average trade duration of 30-60 minutes based on outcome
            # Winners typically close faster (hit target), losers hold longer
            trade_duration = 30 if outcome == 'WIN' else 60

            # Calculate straddle P&L
            pnl, exit_reason, exit_move = calculate_straddle_pnl(
                entry_price=float(price),
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                premium_pts=premium_pts,
                profit_target=profit_target,
                time_stop_minutes=time_stop,
                trade_duration_minutes=trade_duration,
                early_exit_threshold=early_exit
            )

            # Convert to dollars ($5/point for MES)
            pnl_dollars = pnl * 5

            results['total'] += 1
            results['total_pnl'] += pnl_dollars
            results['exit_reasons'][exit_reason] += 1

            is_win = pnl > 0
            if is_win:
                results['wins'] += 1
            else:
                results['losses'] += 1

            # Track by regime
            regime_str = regime or 'UNKNOWN'
            results['by_regime'][regime_str]['trades'] += 1
            results['by_regime'][regime_str]['pnl'] += pnl_dollars
            if is_win:
                results['by_regime'][regime_str]['wins'] += 1

            # Track by hour
            hour = scan_time.hour if scan_time else 0
            results['by_hour'][hour]['trades'] += 1
            results['by_hour'][hour]['pnl'] += pnl_dollars
            if is_win:
                results['by_hour'][hour]['wins'] += 1

        # Print results
        if results['total'] > 0:
            win_rate = results['wins'] / results['total'] * 100
            avg_pnl = results['total_pnl'] / results['total']

            print(f"\nOVERALL:")
            print(f"  Total trades: {results['total']}")
            print(f"  Win rate: {win_rate:.1f}%")
            print(f"  Total P&L: ${results['total_pnl']:,.2f}")
            print(f"  Avg P&L/trade: ${avg_pnl:.2f}")

            print(f"\nEXIT REASONS:")
            for reason, count in sorted(results['exit_reasons'].items()):
                pct = count / results['total'] * 100
                print(f"  {reason}: {count} ({pct:.1f}%)")

            print(f"\nBY GAMMA REGIME:")
            for regime in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
                data = results['by_regime'][regime]
                if data['trades'] > 0:
                    wr = data['wins'] / data['trades'] * 100
                    avg = data['pnl'] / data['trades']
                    print(f"  {regime}: {data['trades']} trades, {wr:.1f}% WR, "
                          f"${data['pnl']:,.2f} total (${avg:.2f}/trade)")

            print(f"\nBY HOUR (CT):")
            for hour in sorted(results['by_hour'].keys()):
                data = results['by_hour'][hour]
                if data['trades'] > 0:
                    wr = data['wins'] / data['trades'] * 100
                    print(f"  {hour:02d}:00: {data['trades']} trades, {wr:.1f}% WR, ${data['pnl']:,.2f}")

    cursor.close()
    conn.close()


def run_estimated_backtest(cursor, trades):
    """
    Run backtest estimating price ranges from subsequent scans.
    """
    print("\nBuilding price history for range estimation...")

    # Get all scans for price history
    cursor.execute("""
        SELECT scan_time, underlying_price
        FROM heracles_scan_activity
        WHERE underlying_price > 0
        ORDER BY scan_time
    """)
    all_scans = cursor.fetchall()

    # Build time -> price dict
    price_timeline = [(s[0], float(s[1])) for s in all_scans if s[1]]
    print(f"Built price timeline with {len(price_timeline)} points")

    def get_price_range(start_time: datetime, duration_minutes: int) -> Tuple[float, float, float]:
        """Get high, low, close prices for a time window."""
        end_time = start_time + timedelta(minutes=duration_minutes)

        prices_in_range = [p for t, p in price_timeline
                          if start_time <= t <= end_time]

        if not prices_in_range:
            return None, None, None

        return max(prices_in_range), min(prices_in_range), prices_in_range[-1]

    # Test just the current config for speed
    config = STRADDLE_CONFIGS[0]  # Current config
    profit_target, time_stop, early_exit, description = config

    print(f"\n{'='*70}")
    print(f"CONFIG: {description}")
    print(f"{'='*70}")

    results = {
        'total': 0,
        'wins': 0,
        'losses': 0,
        'total_pnl': 0.0,
        'by_regime': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'wins': 0}),
        'by_hour': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'wins': 0}),
        'actual_vs_straddle': {'actual_better': 0, 'straddle_better': 0},
    }

    for trade in trades:
        (scan_time, price, regime, direction, outcome, actual_pnl,
         vix, atr, _, _, _) = trade

        if not price or price <= 0 or not scan_time:
            continue

        # Get price range from subsequent scans
        high, low, close = get_price_range(scan_time, time_stop)

        if high is None:
            continue

        # Estimate premium
        vix_val = float(vix) if vix else 18.0
        premium_pts = estimate_straddle_premium(vix_val)

        # Calculate straddle P&L
        pnl, exit_reason, exit_move = calculate_straddle_pnl(
            entry_price=float(price),
            high_price=high,
            low_price=low,
            close_price=close,
            premium_pts=premium_pts,
            profit_target=profit_target,
            time_stop_minutes=time_stop,
            trade_duration_minutes=time_stop,  # Assume full duration for estimation
            early_exit_threshold=early_exit
        )

        pnl_dollars = pnl * 5
        actual_pnl_val = float(actual_pnl) if actual_pnl else 0

        results['total'] += 1
        results['total_pnl'] += pnl_dollars

        is_win = pnl > 0
        if is_win:
            results['wins'] += 1
        else:
            results['losses'] += 1

        # Compare to actual directional trade
        if pnl_dollars > actual_pnl_val:
            results['actual_vs_straddle']['straddle_better'] += 1
        else:
            results['actual_vs_straddle']['actual_better'] += 1

        # Track by regime
        regime_str = regime or 'UNKNOWN'
        results['by_regime'][regime_str]['trades'] += 1
        results['by_regime'][regime_str]['pnl'] += pnl_dollars
        if is_win:
            results['by_regime'][regime_str]['wins'] += 1

        # Track by hour
        hour = scan_time.hour
        results['by_hour'][hour]['trades'] += 1
        results['by_hour'][hour]['pnl'] += pnl_dollars
        if is_win:
            results['by_hour'][hour]['wins'] += 1

    # Print results
    if results['total'] > 0:
        win_rate = results['wins'] / results['total'] * 100
        avg_pnl = results['total_pnl'] / results['total']

        print(f"\nOVERALL (STRADDLE):")
        print(f"  Total trades: {results['total']}")
        print(f"  Win rate: {win_rate:.1f}%")
        print(f"  Total P&L: ${results['total_pnl']:,.2f}")
        print(f"  Avg P&L/trade: ${avg_pnl:.2f}")

        print(f"\nSTRADDLE vs DIRECTIONAL:")
        sb = results['actual_vs_straddle']['straddle_better']
        ab = results['actual_vs_straddle']['actual_better']
        print(f"  Straddle would have been better: {sb} trades ({sb/results['total']*100:.1f}%)")
        print(f"  Directional was better: {ab} trades ({ab/results['total']*100:.1f}%)")

        print(f"\nBY GAMMA REGIME:")
        for regime in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
            data = results['by_regime'][regime]
            if data['trades'] > 0:
                wr = data['wins'] / data['trades'] * 100
                avg = data['pnl'] / data['trades']
                print(f"  {regime}: {data['trades']} trades, {wr:.1f}% WR, "
                      f"${data['pnl']:,.2f} total (${avg:.2f}/trade)")

        print(f"\nBY HOUR (CT) - Best/Worst Hours:")
        hour_data = [(h, d) for h, d in results['by_hour'].items() if d['trades'] >= 5]
        if hour_data:
            sorted_hours = sorted(hour_data, key=lambda x: x[1]['pnl'], reverse=True)
            print("  BEST:")
            for hour, data in sorted_hours[:3]:
                wr = data['wins'] / data['trades'] * 100
                print(f"    {hour:02d}:00 CT: {data['trades']} trades, {wr:.1f}% WR, ${data['pnl']:,.2f}")
            print("  WORST:")
            for hour, data in sorted_hours[-3:]:
                wr = data['wins'] / data['trades'] * 100
                print(f"    {hour:02d}:00 CT: {data['trades']} trades, {wr:.1f}% WR, ${data['pnl']:,.2f}")

    # Calculate what actual directional trades made
    cursor.execute("""
        SELECT
            SUM(realized_pnl) as total_pnl,
            COUNT(*) as total_trades,
            COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) as wins
        FROM heracles_scan_activity
        WHERE trade_executed = TRUE AND realized_pnl IS NOT NULL
    """)
    actual_row = cursor.fetchone()

    if actual_row and actual_row[0]:
        print(f"\n{'='*70}")
        print("COMPARISON: ACTUAL DIRECTIONAL vs ALWAYS STRADDLE")
        print(f"{'='*70}")
        print(f"\n  ACTUAL DIRECTIONAL:")
        actual_pnl = float(actual_row[0])
        actual_trades = actual_row[1]
        actual_wins = actual_row[2]
        actual_wr = actual_wins / actual_trades * 100 if actual_trades > 0 else 0
        print(f"    Total P&L: ${actual_pnl:,.2f}")
        print(f"    Win Rate: {actual_wr:.1f}%")
        print(f"    Avg P&L/trade: ${actual_pnl/actual_trades:.2f}")

        print(f"\n  ALWAYS STRADDLE:")
        print(f"    Total P&L: ${results['total_pnl']:,.2f}")
        print(f"    Win Rate: {win_rate:.1f}%")
        print(f"    Avg P&L/trade: ${avg_pnl:.2f}")

        diff = results['total_pnl'] - actual_pnl
        print(f"\n  DIFFERENCE: ${diff:+,.2f} ({'STRADDLE' if diff > 0 else 'DIRECTIONAL'} better)")

    cursor.close()


if __name__ == '__main__':
    run_backtest()
