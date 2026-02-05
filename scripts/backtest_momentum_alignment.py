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


def get_price_n_minutes_ago(cursor, timestamp, minutes: int, symbol: str = 'SPX') -> Optional[float]:
    """
    Get price from N minutes before a given timestamp.
    Uses gex_history which has spot_price snapshots.
    """
    target_time = timestamp - timedelta(minutes=minutes)
    # Allow 2-minute window to find a price
    cursor.execute("""
        SELECT spot_price, timestamp
        FROM gex_history
        WHERE symbol = %s
          AND timestamp BETWEEN %s AND %s
        ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
        LIMIT 1
    """, (symbol, target_time - timedelta(minutes=2), target_time + timedelta(minutes=2), target_time))

    row = cursor.fetchone()
    return float(row[0]) if row else None


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

    # Check gex_history for price data
    cursor.execute("""
        SELECT COUNT(*), MIN(timestamp), MAX(timestamp), COUNT(DISTINCT DATE(timestamp))
        FROM gex_history
    """)
    gex_row = cursor.fetchone()
    print(f"  gex_history: {gex_row[0]} records, {gex_row[3]} days ({gex_row[1]} to {gex_row[2]})")

    # Check heracles_scan_activity for trades
    cursor.execute("""
        SELECT COUNT(*) FROM heracles_scan_activity
        WHERE trade_executed = TRUE AND trade_outcome IS NOT NULL
    """)
    trades_with_outcome = cursor.fetchone()[0]
    print(f"  heracles_scan_activity trades with outcomes: {trades_with_outcome}")

    if trades_with_outcome == 0:
        print("\n⚠️  No HERACLES trade history found. Using simulated backtest instead...")
        return run_simulated_backtest(cursor)

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
        'by_alignment': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'by_regime': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'would_skip': 0,
        'skip_correct': 0,  # Skipped trades that were actually losses
    }

    for trade in trades:
        scan_time, price, atr, regime, direction, base_prob, outcome, pnl = trade

        results['total'] += 1
        is_win = outcome == 'WIN'

        if is_win:
            results['wins'] += 1
        else:
            results['losses'] += 1

        # Get price from N minutes ago
        price_ago = get_price_n_minutes_ago(cursor, scan_time, LOOKBACK_MINUTES)

        if not price_ago:
            continue

        results['with_momentum'] += 1

        # Calculate momentum metrics
        metrics = calculate_momentum_metrics(price, price_ago, atr, direction)
        if not metrics:
            continue

        alignment = metrics['alignment']

        # Bucket by alignment
        if alignment < -0.5:
            bucket = 'strong_conflict'
        elif alignment < 0:
            bucket = 'weak_conflict'
        elif alignment < 0.5:
            bucket = 'weak_confirm'
        else:
            bucket = 'strong_confirm'

        if is_win:
            results['by_alignment'][bucket]['wins'] += 1
            results['by_regime'][regime]['wins'] += 1
        else:
            results['by_alignment'][bucket]['losses'] += 1
            results['by_regime'][regime]['losses'] += 1

        # Would we have skipped this signal?
        # Skip if: alignment < -0.6 AND momentum > 1.5 ATR
        if alignment < -0.6 and abs(metrics['momentum_atr']) > 1.5:
            results['would_skip'] += 1
            if not is_win:
                results['skip_correct'] += 1

    # Print results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    print(f"\nOverall: {results['total']} trades")
    print(f"  Wins:   {results['wins']} ({results['wins']/results['total']*100:.1f}%)")
    print(f"  Losses: {results['losses']} ({results['losses']/results['total']*100:.1f}%)")
    print(f"  With momentum data: {results['with_momentum']}")

    print(f"\n--- BY ALIGNMENT BUCKET ---")
    for bucket in ['strong_confirm', 'weak_confirm', 'weak_conflict', 'strong_conflict']:
        data = results['by_alignment'][bucket]
        total = data['wins'] + data['losses']
        if total > 0:
            win_rate = data['wins'] / total * 100
            print(f"  {bucket:20s}: {total:4d} trades, {win_rate:.1f}% win rate")

    print(f"\n--- BY GAMMA REGIME ---")
    for regime in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
        data = results['by_regime'][regime]
        total = data['wins'] + data['losses']
        if total > 0:
            win_rate = data['wins'] / total * 100
            print(f"  {regime:12s}: {total:4d} trades, {win_rate:.1f}% win rate")

    print(f"\n--- SKIP ANALYSIS ---")
    print(f"  Would have skipped: {results['would_skip']} trades")
    if results['would_skip'] > 0:
        accuracy = results['skip_correct'] / results['would_skip'] * 100
        print(f"  Skip accuracy: {results['skip_correct']}/{results['would_skip']} ({accuracy:.1f}% were actually losses)")

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
