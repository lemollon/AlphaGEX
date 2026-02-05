#!/usr/bin/env python3
"""
HERACLES Momentum Alignment Backtest
=====================================

Tests the Signal Alignment Probability (SAP) concept:
- Calculate what momentum WAS at each historical trade
- See if momentum alignment would have predicted WIN/LOSS
- Determine optimal thresholds for production

Run on Render Shell:
    python scripts/backtest_momentum_alignment.py

Requires: heracles_scan_activity or gex_history data
"""

import os
import sys
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

# Constants
LOOKBACK_MINUTES = 5  # How far back to calculate momentum


def build_price_history_from_scans(cursor) -> Dict[datetime, Tuple[float, float]]:
    """
    Build a price history dict from all scan_activity records.
    Returns: {scan_time: (underlying_price, atr)}
    """
    cursor.execute("""
        SELECT scan_time, underlying_price, atr
        FROM heracles_scan_activity
        WHERE underlying_price > 0
        ORDER BY scan_time
    """)

    history = {}
    for row in cursor.fetchall():
        scan_time, price, atr = row
        history[scan_time] = (float(price), float(atr) if atr else 0)

    return history


def get_price_n_minutes_ago_from_history(
    price_history: Dict[datetime, Tuple[float, float]],
    timestamp: datetime,
    minutes: int
) -> Optional[Tuple[float, float]]:
    """
    Get price from N minutes before a given timestamp using pre-built history.
    Returns: (price, atr) or None
    """
    target_time = timestamp - timedelta(minutes=minutes)
    # Find closest scan within a window
    best_match = None
    best_diff = timedelta(minutes=10)  # Max window

    for scan_time, (price, atr) in price_history.items():
        diff = abs(scan_time - target_time)
        if diff < best_diff:
            best_diff = diff
            best_match = (price, atr)

    # Only return if within 3 minutes of target
    if best_match and best_diff <= timedelta(minutes=3):
        return best_match
    return None


def calculate_momentum_metrics(
    current_price: float,
    price_n_min_ago: float,
    atr: float,
    signal_direction: str
) -> Dict:
    """
    Calculate momentum metrics for a signal.

    Returns:
        momentum_pts: Raw price change in points
        momentum_atr: Price change normalized by ATR
        momentum_score: -100 to +100 (bearish to bullish)
        signal_alignment: -1 to +1 (contradicts to confirms)
        alignment_factor: 0.7 to 1.3 (probability multiplier)
    """
    if not price_n_min_ago or atr <= 0:
        return None

    momentum_pts = current_price - price_n_min_ago
    momentum_atr = momentum_pts / atr

    # Momentum score: tanh to cap extremes, scale to -100 to +100
    momentum_score = math.tanh(momentum_atr) * 100

    # Signal alignment: positive = momentum confirms signal
    if signal_direction.upper() == 'LONG':
        alignment = momentum_score / 100  # Bullish momentum confirms LONG
    else:  # SHORT
        alignment = -momentum_score / 100  # Bearish momentum confirms SHORT

    # Alignment factor: 0.7 to 1.3
    alignment_factor = 1.0 + (alignment * 0.3)

    return {
        'momentum_pts': momentum_pts,
        'momentum_atr': momentum_atr,
        'momentum_score': momentum_score,
        'alignment': alignment,
        'alignment_factor': alignment_factor
    }


def run_backtest():
    """Run the momentum alignment backtest."""
    print("=" * 70)
    print("HERACLES MOMENTUM ALIGNMENT BACKTEST")
    print("=" * 70)
    print(f"Lookback: {LOOKBACK_MINUTES} minutes")
    print()

    conn = get_connection()
    cursor = conn.cursor()

    # First check what data we have
    print("Checking available data...")

    # Check scan_activity for all scans (for price history)
    cursor.execute("""
        SELECT COUNT(*), MIN(scan_time), MAX(scan_time), COUNT(DISTINCT DATE(scan_time))
        FROM heracles_scan_activity
        WHERE underlying_price > 0
    """)
    scan_row = cursor.fetchone()
    print(f"  heracles_scan_activity: {scan_row[0]} scans, {scan_row[3]} days ({scan_row[1]} to {scan_row[2]})")

    # Check heracles_scan_activity for trades with outcomes
    cursor.execute("""
        SELECT COUNT(*) FROM heracles_scan_activity
        WHERE trade_executed = TRUE AND trade_outcome IS NOT NULL
    """)
    trades_with_outcome = cursor.fetchone()[0]
    print(f"  trades with outcomes: {trades_with_outcome}")

    if trades_with_outcome == 0:
        print("\n[!] No HERACLES trade history found. Using simulated backtest instead...")
        return run_simulated_backtest(cursor)

    # Build price history from all scans for momentum lookback
    print("\nBuilding price history from scan_activity...")
    price_history = build_price_history_from_scans(cursor)
    print(f"  Price history entries: {len(price_history)}")

    # Get trades with outcomes
    cursor.execute("""
        SELECT
            scan_time,
            underlying_price,
            atr,
            gamma_regime,
            signal_direction,
            signal_win_probability,
            trade_outcome,
            realized_pnl
        FROM heracles_scan_activity
        WHERE trade_executed = TRUE
          AND trade_outcome IS NOT NULL
          AND underlying_price > 0
          AND atr > 0
        ORDER BY scan_time
    """)

    trades = cursor.fetchall()
    print(f"\nAnalyzing {len(trades)} trades...")

    # Analyze each trade
    results = {
        'total': 0,
        'with_momentum': 0,
        'wins': 0,
        'losses': 0,
        'by_alignment': defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0}),
        'by_regime': defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0}),
        'would_skip': 0,
        'skip_correct': 0,  # Skipped trades that were actually losses
        'skip_pnl_saved': 0.0,  # P&L from skipped losing trades
        'alignment_details': [],  # For detailed analysis
    }

    for trade in trades:
        scan_time, price, atr, regime, direction, base_prob, outcome, pnl = trade

        results['total'] += 1
        is_win = outcome == 'WIN'
        pnl_value = float(pnl) if pnl else 0.0

        if is_win:
            results['wins'] += 1
        else:
            results['losses'] += 1

        # Get price from N minutes ago using our scan history
        price_data = get_price_n_minutes_ago_from_history(price_history, scan_time, LOOKBACK_MINUTES)

        if not price_data:
            continue

        price_ago, _ = price_data
        results['with_momentum'] += 1

        # Calculate momentum metrics
        metrics = calculate_momentum_metrics(price, price_ago, atr, direction)
        if not metrics:
            continue

        alignment = metrics['alignment']
        momentum_atr = metrics['momentum_atr']

        # Bucket by alignment
        if alignment < -0.5:
            bucket = 'strong_conflict'
        elif alignment < 0:
            bucket = 'weak_conflict'
        elif alignment < 0.5:
            bucket = 'weak_confirm'
        else:
            bucket = 'strong_confirm'

        # Track details
        results['alignment_details'].append({
            'time': scan_time,
            'direction': direction,
            'regime': regime,
            'alignment': alignment,
            'momentum_atr': momentum_atr,
            'bucket': bucket,
            'outcome': outcome,
            'pnl': pnl_value
        })

        if is_win:
            results['by_alignment'][bucket]['wins'] += 1
            results['by_regime'][regime]['wins'] += 1
        else:
            results['by_alignment'][bucket]['losses'] += 1
            results['by_regime'][regime]['losses'] += 1

        results['by_alignment'][bucket]['pnl'] += pnl_value
        results['by_regime'][regime]['pnl'] += pnl_value

        # Would we have skipped this signal?
        # Skip if: strong momentum conflict (alignment < -0.5 AND abs momentum > 0.5 ATR)
        if alignment < -0.5 and abs(momentum_atr) > 0.5:
            results['would_skip'] += 1
            if not is_win:
                results['skip_correct'] += 1
                results['skip_pnl_saved'] += abs(pnl_value)

    # Print results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    if results['total'] > 0:
        print(f"\nOverall: {results['total']} trades")
        print(f"  Wins:   {results['wins']} ({results['wins']/results['total']*100:.1f}%)")
        print(f"  Losses: {results['losses']} ({results['losses']/results['total']*100:.1f}%)")
        print(f"  With momentum data: {results['with_momentum']}")

        print(f"\n--- BY ALIGNMENT BUCKET ---")
        print(f"  {'Bucket':<20} {'Trades':>7} {'Win Rate':>10} {'Total P&L':>12}")
        print(f"  {'-'*20} {'-'*7} {'-'*10} {'-'*12}")
        for bucket in ['strong_confirm', 'weak_confirm', 'weak_conflict', 'strong_conflict']:
            data = results['by_alignment'][bucket]
            total = data['wins'] + data['losses']
            if total > 0:
                win_rate = data['wins'] / total * 100
                print(f"  {bucket:<20} {total:>7} {win_rate:>9.1f}% ${data['pnl']:>10.2f}")

        print(f"\n--- BY GAMMA REGIME ---")
        print(f"  {'Regime':<12} {'Trades':>7} {'Win Rate':>10} {'Total P&L':>12}")
        print(f"  {'-'*12} {'-'*7} {'-'*10} {'-'*12}")
        for regime in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
            data = results['by_regime'][regime]
            total = data['wins'] + data['losses']
            if total > 0:
                win_rate = data['wins'] / total * 100
                print(f"  {regime:<12} {total:>7} {win_rate:>9.1f}% ${data['pnl']:>10.2f}")

        print(f"\n--- SKIP ANALYSIS ---")
        print(f"  Would have skipped: {results['would_skip']} trades")
        if results['would_skip'] > 0:
            accuracy = results['skip_correct'] / results['would_skip'] * 100
            print(f"  Skip accuracy: {results['skip_correct']}/{results['would_skip']} = {accuracy:.1f}% were losses")
            print(f"  P&L saved by skipping: ${results['skip_pnl_saved']:.2f}")

        # Key insight summary
        print(f"\n" + "=" * 70)
        print("KEY INSIGHTS")
        print("=" * 70)

        confirm_data = results['by_alignment']['strong_confirm']
        conflict_data = results['by_alignment']['strong_conflict']

        confirm_total = confirm_data['wins'] + confirm_data['losses']
        conflict_total = conflict_data['wins'] + conflict_data['losses']

        if confirm_total > 0 and conflict_total > 0:
            confirm_wr = confirm_data['wins'] / confirm_total * 100
            conflict_wr = conflict_data['wins'] / conflict_total * 100

            print(f"\n  Strong Confirm win rate:  {confirm_wr:.1f}% ({confirm_total} trades)")
            print(f"  Strong Conflict win rate: {conflict_wr:.1f}% ({conflict_total} trades)")
            print(f"  Difference: {confirm_wr - conflict_wr:+.1f}%")

            if confirm_wr > conflict_wr:
                print(f"\n  --> Momentum alignment IS predictive!")
                print(f"      Recommendation: Implement SAP with alignment factor")
            else:
                print(f"\n  --> Counter-momentum may be better (mean reversion)")
                print(f"      Recommendation: Do NOT skip conflicting signals")

    cursor.close()
    conn.close()

    return results


def run_simulated_backtest(cursor):
    """
    Run a simulated backtest using gex_history data.
    Simulates what HERACLES signals WOULD have been and estimates outcomes.
    """
    print("\n" + "=" * 70)
    print("SIMULATED BACKTEST (No trade history - using GEX data)")
    print("=" * 70)

    # Get GEX snapshots with price data
    cursor.execute("""
        SELECT
            timestamp,
            spot_price,
            net_gex,
            flip_point,
            call_wall,
            put_wall
        FROM gex_history
        WHERE spot_price > 0
          AND flip_point > 0
          AND symbol = 'SPX'
        ORDER BY timestamp
        LIMIT 5000
    """)

    snapshots = cursor.fetchall()
    print(f"Found {len(snapshots)} GEX snapshots")

    if len(snapshots) < 100:
        print("Not enough data for meaningful backtest")
        return None

    # Simulate signals
    print("\nSimulating HERACLES signals...")

    # Build price history for momentum lookback
    price_history = {}  # timestamp -> price
    for ts, price, *_ in snapshots:
        price_history[ts] = price

    # Stats tracking
    signals = {
        'total': 0,
        'positive_gamma': {'long': 0, 'short': 0},
        'negative_gamma': {'long': 0, 'short': 0},
        'by_momentum': defaultdict(int),
        'simulated_outcomes': defaultdict(lambda: {'estimated_win': 0, 'estimated_loss': 0})
    }

    prev_ts = None
    prev_price = None

    for i, (ts, price, net_gex, flip, call_wall, put_wall) in enumerate(snapshots):
        if i < 10:  # Need some history
            prev_ts, prev_price = ts, price
            continue

        # Determine regime
        if net_gex > 0:
            regime = 'POSITIVE'
        elif net_gex < 0:
            regime = 'NEGATIVE'
        else:
            continue

        # Calculate distance from flip
        distance_pct = ((price - flip) / flip) * 100

        # Would we signal?
        signal_direction = None
        if regime == 'POSITIVE':
            if distance_pct > 0.3:  # Above flip - SHORT
                signal_direction = 'SHORT'
                signals['positive_gamma']['short'] += 1
            elif distance_pct < -0.3:  # Below flip - LONG
                signal_direction = 'LONG'
                signals['positive_gamma']['long'] += 1
        else:  # NEGATIVE
            if distance_pct > 0.5:  # Momentum LONG
                signal_direction = 'LONG'
                signals['negative_gamma']['long'] += 1
            elif distance_pct < -0.5:  # Momentum SHORT
                signal_direction = 'SHORT'
                signals['negative_gamma']['short'] += 1

        if not signal_direction:
            prev_ts, prev_price = ts, price
            continue

        signals['total'] += 1

        # Calculate momentum
        if prev_price and prev_price > 0:
            momentum_pts = price - prev_price
            atr_estimate = abs(momentum_pts) * 2  # Rough ATR estimate
            if atr_estimate > 0:
                momentum_atr = momentum_pts / atr_estimate
            else:
                momentum_atr = 0

            # Calculate alignment
            if signal_direction == 'LONG':
                alignment = 1 if momentum_pts > 0 else -1
            else:
                alignment = 1 if momentum_pts < 0 else -1

            # Bucket
            if alignment > 0 and abs(momentum_atr) > 0.5:
                bucket = 'strong_confirm'
            elif alignment > 0:
                bucket = 'weak_confirm'
            elif abs(momentum_atr) > 0.5:
                bucket = 'strong_conflict'
            else:
                bucket = 'weak_conflict'

            signals['by_momentum'][bucket] += 1

            # Simulate outcome: look at next price movement toward/away from flip
            if i + 5 < len(snapshots):
                future_price = snapshots[i + 5][1]  # 5 snapshots later

                if signal_direction == 'LONG':
                    simulated_win = future_price > price
                else:
                    simulated_win = future_price < price

                if simulated_win:
                    signals['simulated_outcomes'][bucket]['estimated_win'] += 1
                else:
                    signals['simulated_outcomes'][bucket]['estimated_loss'] += 1

        prev_ts, prev_price = ts, price

    # Print results
    print(f"\nTotal signals: {signals['total']}")
    print(f"\nPositive Gamma signals:")
    print(f"  LONG (below flip):  {signals['positive_gamma']['long']}")
    print(f"  SHORT (above flip): {signals['positive_gamma']['short']}")
    print(f"\nNegative Gamma signals:")
    print(f"  LONG (momentum):  {signals['negative_gamma']['long']}")
    print(f"  SHORT (momentum): {signals['negative_gamma']['short']}")

    print(f"\n--- BY MOMENTUM ALIGNMENT ---")
    for bucket in ['strong_confirm', 'weak_confirm', 'weak_conflict', 'strong_conflict']:
        count = signals['by_momentum'][bucket]
        outcomes = signals['simulated_outcomes'][bucket]
        total = outcomes['estimated_win'] + outcomes['estimated_loss']
        if total > 0:
            win_rate = outcomes['estimated_win'] / total * 100
            print(f"  {bucket:20s}: {count:4d} signals, ~{win_rate:.1f}% estimated win rate")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    print("""
    If 'strong_confirm' has higher win rate than 'strong_conflict':
      → Momentum alignment IS predictive
      → We should boost/reduce probability based on alignment

    If 'strong_conflict' has HIGHER win rate:
      → Counter-momentum is actually better (true mean reversion)
      → We should NOT skip conflicting signals

    This is SIMULATED data - real trade outcomes needed for production.
    """)

    cursor.close()

    return signals


if __name__ == '__main__':
    results = run_backtest()
