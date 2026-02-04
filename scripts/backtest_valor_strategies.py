#!/usr/bin/env python3
"""
VALOR (HERACLES) Strategy Backtester
=====================================
Backtests different strategies against historical trades to find improvements.

Strategies tested:
1. BASELINE: All trades as-is
2. MAX_2_SAME_DIR: Max 2 positions in same direction
3. MAX_1_SAME_DIR: Max 1 position in same direction
4. POSITIVE_GAMMA_ONLY: Only trade in positive gamma
5. NO_OVERNIGHT: Skip trades opened after 4 PM CT
6. STREAK_BREAKER: Pause after 3 consecutive losses
7. COMBINED: Best combination of above

Run: python scripts/backtest_valor_strategies.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any

print("=" * 70)
print("VALOR (HERACLES) STRATEGY BACKTESTER")
print("=" * 70)

db = DatabaseAdapter()

# Get all closed trades AND scan activity (to see what was skipped)
trades = db.fetchall("""
    SELECT
        position_id,
        direction,
        gamma_regime,
        entry_price,
        close_price,
        realized_pnl,
        close_reason,
        open_time,
        close_time,
        stop_type
    FROM heracles_closed_trades
    ORDER BY open_time ASC
""")

if not trades:
    print("No closed trades found")
    sys.exit(0)

# Convert to list of dicts
all_trades = []
for r in trades:
    all_trades.append({
        'id': r[0],
        'direction': r[1],
        'regime': r[2] or 'UNKNOWN',
        'entry': float(r[3] or 0),
        'exit': float(r[4] or 0),
        'pnl': float(r[5] or 0),
        'reason': r[6],
        'open_time': r[7],
        'close_time': r[8],
        'stop_type': r[9] or 'UNKNOWN'
    })

print(f"\nTotal historical trades: {len(all_trades)}")
total_pnl = sum(t['pnl'] for t in all_trades)
wins = sum(1 for t in all_trades if t['pnl'] >= 0)
print(f"Baseline P&L: ${total_pnl:.2f}")
print(f"Baseline Win Rate: {wins/len(all_trades)*100:.1f}%")

# ============================================================================
# STRATEGY SIMULATORS
# ============================================================================

def simulate_baseline(trades: List[Dict]) -> Dict[str, Any]:
    """Take all trades as-is"""
    pnl = sum(t['pnl'] for t in trades)
    wins = sum(1 for t in trades if t['pnl'] >= 0)
    return {
        'trades_taken': len(trades),
        'trades_skipped': 0,
        'pnl': pnl,
        'wins': wins,
        'losses': len(trades) - wins
    }


def simulate_max_same_direction(trades: List[Dict], max_same: int) -> Dict[str, Any]:
    """Limit positions in same direction"""
    taken = []
    skipped = []
    open_positions = []  # Track simulated open positions

    for t in trades:
        # Close any positions that would have closed by now
        open_positions = [p for p in open_positions
                        if p['close_time'] and t['open_time'] and p['close_time'] > t['open_time']]

        # Count same direction
        same_dir = sum(1 for p in open_positions if p['direction'] == t['direction'])

        if same_dir < max_same:
            taken.append(t)
            open_positions.append(t)
        else:
            skipped.append(t)

    pnl = sum(t['pnl'] for t in taken)
    wins = sum(1 for t in taken if t['pnl'] >= 0)
    return {
        'trades_taken': len(taken),
        'trades_skipped': len(skipped),
        'pnl': pnl,
        'wins': wins,
        'losses': len(taken) - wins if taken else 0,
        'skipped_pnl': sum(t['pnl'] for t in skipped)
    }


def simulate_regime_filter(trades: List[Dict], allowed_regimes: List[str]) -> Dict[str, Any]:
    """Only trade in certain gamma regimes"""
    taken = [t for t in trades if t['regime'] in allowed_regimes]
    skipped = [t for t in trades if t['regime'] not in allowed_regimes]

    pnl = sum(t['pnl'] for t in taken)
    wins = sum(1 for t in taken if t['pnl'] >= 0)
    return {
        'trades_taken': len(taken),
        'trades_skipped': len(skipped),
        'pnl': pnl,
        'wins': wins,
        'losses': len(taken) - wins if taken else 0,
        'skipped_pnl': sum(t['pnl'] for t in skipped)
    }


def simulate_time_filter(trades: List[Dict], start_hour: int, end_hour: int) -> Dict[str, Any]:
    """Only trade during certain hours"""
    taken = []
    skipped = []

    for t in trades:
        if t['open_time']:
            hour = t['open_time'].hour
            if start_hour <= hour < end_hour:
                taken.append(t)
            else:
                skipped.append(t)
        else:
            taken.append(t)  # Include if no timestamp

    pnl = sum(t['pnl'] for t in taken)
    wins = sum(1 for t in taken if t['pnl'] >= 0)
    return {
        'trades_taken': len(taken),
        'trades_skipped': len(skipped),
        'pnl': pnl,
        'wins': wins,
        'losses': len(taken) - wins if taken else 0,
        'skipped_pnl': sum(t['pnl'] for t in skipped)
    }


def simulate_streak_breaker(trades: List[Dict], max_consecutive_losses: int, pause_trades: int) -> Dict[str, Any]:
    """Pause trading after N consecutive losses"""
    taken = []
    skipped = []
    consecutive_losses = 0
    pause_remaining = 0

    for t in trades:
        if pause_remaining > 0:
            skipped.append(t)
            pause_remaining -= 1
            # Still track if this would have been a win to reset
            if t['pnl'] >= 0:
                consecutive_losses = 0
            continue

        taken.append(t)

        if t['pnl'] < 0:
            consecutive_losses += 1
            if consecutive_losses >= max_consecutive_losses:
                pause_remaining = pause_trades
                consecutive_losses = 0
        else:
            consecutive_losses = 0

    pnl = sum(t['pnl'] for t in taken)
    wins = sum(1 for t in taken if t['pnl'] >= 0)
    return {
        'trades_taken': len(taken),
        'trades_skipped': len(skipped),
        'pnl': pnl,
        'wins': wins,
        'losses': len(taken) - wins if taken else 0,
        'skipped_pnl': sum(t['pnl'] for t in skipped)
    }


def simulate_hedged_pairs(trades: List[Dict], stop_pts: float = 2.5, target_pts: float = 6.0) -> Dict[str, Any]:
    """
    Simulate opening LONG and SHORT at the same time (hedged).

    For each trade entry, we simulate opening both directions:
    - LONG: wins if price goes up by target_pts before down by stop_pts
    - SHORT: wins if price goes down by target_pts before up by stop_pts

    Since we don't have tick data, we estimate based on actual trade outcomes:
    - If original LONG won → LONG hits target, SHORT hits stop
    - If original LONG lost → Check if it was stopped or other reason
    """
    pairs = []
    point_value = 5.0  # $5 per point for MES

    for t in trades:
        entry = t['entry']
        exit_price = t['exit']
        direction = t['direction']

        # Calculate the actual move
        if direction in ['LONG', 'long', 'Long']:
            actual_move = exit_price - entry  # Positive = good for long
        else:
            actual_move = entry - exit_price  # Positive = good for short

        # Simulate the hedge pair
        # We need to estimate what would have happened to the opposite trade

        # If the original trade won (hit target ~+6 pts)
        if t['pnl'] > 0:
            # Original direction hit target
            # Opposite direction would have been stopped out (price moved against it)
            winning_pnl = target_pts * point_value  # +$30
            losing_pnl = -stop_pts * point_value    # -$12.50
            pair_pnl = winning_pnl + losing_pnl     # +$17.50
            pair_outcome = 'WIN'

        # If the original trade lost (hit stop ~-2.5 pts)
        elif t['pnl'] < 0:
            # Original direction hit stop
            # But what happened to the opposite direction?
            # If price moved enough to stop one side, the other side should have profited

            # Check if it was a small loss (just hit stop) or large loss (slippage)
            expected_loss = -stop_pts * point_value
            actual_loss = t['pnl']

            if actual_loss >= expected_loss * 0.8:  # Within 20% of expected stop loss
                # Clean stop - opposite direction should have profited
                # But may not have hit full target yet
                # Estimate: opposite gained what original lost
                opposite_gain = abs(actual_loss)  # Mirror the move
                if opposite_gain >= target_pts * point_value:
                    opposite_gain = target_pts * point_value  # Cap at target
                pair_pnl = actual_loss + opposite_gain
                pair_outcome = 'HEDGE_PROFIT' if pair_pnl > 0 else 'HEDGE_LOSS'
            else:
                # Large slippage loss - volatile move
                # Opposite probably hit target before we got stopped
                winning_pnl = target_pts * point_value  # +$30
                pair_pnl = actual_loss + winning_pnl
                pair_outcome = 'WIN' if pair_pnl > 0 else 'VOLATILE_LOSS'
        else:
            # Breakeven - rare
            pair_pnl = 0
            pair_outcome = 'BREAKEVEN'

        pairs.append({
            'original_trade': t,
            'pair_pnl': pair_pnl,
            'outcome': pair_outcome
        })

    total_pnl = sum(p['pair_pnl'] for p in pairs)
    wins = sum(1 for p in pairs if p['pair_pnl'] > 0)

    return {
        'trades_taken': len(pairs) * 2,  # Each pair is 2 trades
        'pairs': len(pairs),
        'trades_skipped': 0,
        'pnl': total_pnl,
        'wins': wins,
        'losses': len(pairs) - wins,
        'avg_pair_pnl': total_pnl / len(pairs) if pairs else 0,
        'outcomes': {
            'WIN': sum(1 for p in pairs if p['outcome'] == 'WIN'),
            'HEDGE_PROFIT': sum(1 for p in pairs if p['outcome'] == 'HEDGE_PROFIT'),
            'HEDGE_LOSS': sum(1 for p in pairs if p['outcome'] == 'HEDGE_LOSS'),
            'VOLATILE_LOSS': sum(1 for p in pairs if p['outcome'] == 'VOLATILE_LOSS'),
            'BREAKEVEN': sum(1 for p in pairs if p['outcome'] == 'BREAKEVEN'),
        }
    }


def simulate_hedged_selective(trades: List[Dict], min_confidence: float = 0.6) -> Dict[str, Any]:
    """
    Only hedge on high-confidence signals.
    For lower confidence, take directional trade only.

    Since we don't have confidence in historical data, we simulate based on regime:
    - POSITIVE gamma (mean reversion) = higher confidence = directional only
    - NEGATIVE gamma (momentum) = lower confidence = hedge
    """
    point_value = 5.0
    stop_pts = 2.5
    target_pts = 6.0

    results = []

    for t in trades:
        regime = t['regime']

        # Decide: hedge or directional?
        if 'NEGATIVE' in regime.upper():
            # Lower confidence in momentum - HEDGE
            if t['pnl'] > 0:
                # Original won, opposite stopped
                pair_pnl = (target_pts - stop_pts) * point_value  # +$17.50
            else:
                # Original stopped, opposite should have gained
                pair_pnl = t['pnl'] + abs(t['pnl'])  # Roughly breakeven or small profit
                if pair_pnl < -stop_pts * point_value:
                    pair_pnl = -stop_pts * point_value  # Cap loss
            trade_type = 'HEDGED'
        else:
            # Higher confidence - DIRECTIONAL only
            pair_pnl = t['pnl']
            trade_type = 'DIRECTIONAL'

        results.append({
            'pnl': pair_pnl,
            'type': trade_type
        })

    total_pnl = sum(r['pnl'] for r in results)
    hedged_count = sum(1 for r in results if r['type'] == 'HEDGED')
    directional_count = len(results) - hedged_count

    return {
        'trades_taken': len(results) + hedged_count,  # Hedged = 2 trades
        'trades_skipped': 0,
        'pnl': total_pnl,
        'wins': sum(1 for r in results if r['pnl'] > 0),
        'losses': sum(1 for r in results if r['pnl'] < 0),
        'hedged_trades': hedged_count,
        'directional_trades': directional_count
    }


def simulate_combined(trades: List[Dict], max_same_dir: int, allowed_regimes: List[str],
                      start_hour: int, end_hour: int) -> Dict[str, Any]:
    """Combine multiple filters"""
    taken = []
    skipped = []
    open_positions = []

    for t in trades:
        skip_reason = None

        # Time filter
        if t['open_time']:
            hour = t['open_time'].hour
            if not (start_hour <= hour < end_hour):
                skip_reason = "time"

        # Regime filter
        if not skip_reason and t['regime'] not in allowed_regimes:
            skip_reason = "regime"

        # Direction limit
        if not skip_reason:
            open_positions = [p for p in open_positions
                            if p['close_time'] and t['open_time'] and p['close_time'] > t['open_time']]
            same_dir = sum(1 for p in open_positions if p['direction'] == t['direction'])
            if same_dir >= max_same_dir:
                skip_reason = "direction"

        if skip_reason:
            skipped.append(t)
        else:
            taken.append(t)
            open_positions.append(t)

    pnl = sum(t['pnl'] for t in taken)
    wins = sum(1 for t in taken if t['pnl'] >= 0)
    return {
        'trades_taken': len(taken),
        'trades_skipped': len(skipped),
        'pnl': pnl,
        'wins': wins,
        'losses': len(taken) - wins if taken else 0,
        'skipped_pnl': sum(t['pnl'] for t in skipped)
    }


# ============================================================================
# RUN SIMULATIONS
# ============================================================================

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

strategies = {}

# 1. Baseline
strategies['BASELINE'] = simulate_baseline(all_trades)

# 2. Max 2 same direction
strategies['MAX_2_SAME_DIR'] = simulate_max_same_direction(all_trades, 2)

# 3. Max 1 same direction
strategies['MAX_1_SAME_DIR'] = simulate_max_same_direction(all_trades, 1)

# 4. Positive gamma only
strategies['POSITIVE_ONLY'] = simulate_regime_filter(all_trades, ['POSITIVE', 'GammaRegime.POSITIVE'])

# 5. Negative gamma only
strategies['NEGATIVE_ONLY'] = simulate_regime_filter(all_trades, ['NEGATIVE', 'GammaRegime.NEGATIVE'])

# 6. RTH only (8 AM - 4 PM CT)
strategies['RTH_ONLY'] = simulate_time_filter(all_trades, 8, 16)

# 7. No overnight (8 AM - 5 PM CT)
strategies['NO_OVERNIGHT'] = simulate_time_filter(all_trades, 8, 17)

# 8. Streak breaker (pause after 3 losses for 2 trades)
strategies['STREAK_3_PAUSE_2'] = simulate_streak_breaker(all_trades, 3, 2)

# 9. Streak breaker (pause after 3 losses for 5 trades)
strategies['STREAK_3_PAUSE_5'] = simulate_streak_breaker(all_trades, 3, 5)

# 10. Combined: Max 2 same dir + RTH + Positive gamma
strategies['COMBINED_SAFE'] = simulate_combined(all_trades, 2, ['POSITIVE', 'GammaRegime.POSITIVE'], 8, 16)

# 11. Combined: Max 1 same dir + all regimes + extended hours
strategies['COMBINED_CAUTIOUS'] = simulate_combined(all_trades, 1, ['POSITIVE', 'NEGATIVE', 'NEUTRAL', 'GammaRegime.POSITIVE', 'GammaRegime.NEGATIVE', 'GammaRegime.NEUTRAL'], 8, 20)

# 12. Hedged: Open LONG and SHORT simultaneously
strategies['HEDGED_ALL'] = simulate_hedged_pairs(all_trades)

# 13. Hedged Selective: Hedge only in NEGATIVE gamma, directional in POSITIVE
strategies['HEDGED_SELECTIVE'] = simulate_hedged_selective(all_trades)

# Print results
print("\n{:<20} {:>8} {:>8} {:>10} {:>8} {:>10}".format(
    "Strategy", "Trades", "Skipped", "P&L", "WinRate", "vs Base"))
print("-" * 70)

baseline_pnl = strategies['BASELINE']['pnl']

for name, result in sorted(strategies.items(), key=lambda x: x[1]['pnl'], reverse=True):
    trades_taken = result['trades_taken']
    trades_skipped = result['trades_skipped']
    pnl = result['pnl']
    win_rate = (result['wins'] / trades_taken * 100) if trades_taken > 0 else 0
    vs_base = pnl - baseline_pnl

    marker = "★" if pnl > baseline_pnl else ""
    print("{:<20} {:>8} {:>8} ${:>9.2f} {:>7.1f}% {:>+10.2f} {}".format(
        name, trades_taken, trades_skipped, pnl, win_rate, vs_base, marker))

# ============================================================================
# BEST STRATEGY ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("ANALYSIS")
print("=" * 70)

# Find best
best = max(strategies.items(), key=lambda x: x[1]['pnl'])
print(f"\n★ Best Strategy: {best[0]}")
print(f"  P&L: ${best[1]['pnl']:.2f}")
print(f"  Improvement: ${best[1]['pnl'] - baseline_pnl:.2f} vs baseline")
print(f"  Trades: {best[1]['trades_taken']} taken, {best[1]['trades_skipped']} skipped")
print(f"  Win Rate: {best[1]['wins']/best[1]['trades_taken']*100:.1f}%" if best[1]['trades_taken'] > 0 else "")

# Find best that doesn't skip too many trades
active_strategies = {k: v for k, v in strategies.items()
                     if v['trades_taken'] >= len(all_trades) * 0.5}  # At least 50% of trades

if active_strategies:
    best_active = max(active_strategies.items(), key=lambda x: x[1]['pnl'])
    if best_active[0] != best[0]:
        print(f"\n★ Best Active Strategy (≥50% trades): {best_active[0]}")
        print(f"  P&L: ${best_active[1]['pnl']:.2f}")
        print(f"  Improvement: ${best_active[1]['pnl'] - baseline_pnl:.2f} vs baseline")

# ============================================================================
# RECOMMENDATIONS
# ============================================================================
print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

improvements = []
for name, result in strategies.items():
    if result['pnl'] > baseline_pnl and name != 'BASELINE':
        improvements.append((name, result['pnl'] - baseline_pnl))

if improvements:
    improvements.sort(key=lambda x: x[1], reverse=True)
    print("\nStrategies that would have improved P&L:")
    for name, improvement in improvements[:5]:
        print(f"  • {name}: +${improvement:.2f}")

    # Specific recommendations
    print("\nImplementation suggestions:")
    if any('SAME_DIR' in name for name, _ in improvements[:3]):
        print("  1. Add max_positions_per_direction config (suggest: 2)")
    if any('POSITIVE' in name for name, _ in improvements[:3]):
        print("  2. Add regime filter to only trade POSITIVE gamma")
    if any('RTH' in name or 'OVERNIGHT' in name for name, _ in improvements[:3]):
        print("  3. Restrict trading to RTH (8 AM - 4 PM CT)")
    if any('STREAK' in name for name, _ in improvements[:3]):
        print("  4. Add streak circuit breaker (pause after 3 losses)")
else:
    print("\nNo strategy significantly outperformed baseline.")
    print("Consider: The current approach may be near-optimal for this data.")

print("\n" + "=" * 70)
