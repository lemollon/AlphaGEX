#!/usr/bin/env python3
"""
VALOR (VALOR) Strategy Backtester
=====================================
Backtests different strategies against historical trades to find improvements.

ALL SIMULATIONS USE ONLY REAL DATA - no mock/estimated outcomes.

Strategies test different FILTERS on actual historical trades:
- Direction limits (max same direction)
- Gamma regime filters
- Time filters
- Streak breakers
- Combined filters
- Configurable parameters

Run: python scripts/backtest_valor_strategies.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Callable, Optional

# ============================================================================
# CONFIGURATION - Easy to modify for testing new ideas
# ============================================================================

CONFIG = {
    # Position limits to test
    'max_same_direction_values': [1, 2, 3],

    # Time windows to test (start_hour, end_hour) in CT
    'time_windows': [
        (8, 16),   # RTH only
        (8, 17),   # Extended RTH
        (8, 20),   # Extended hours
        (6, 22),   # Most active
        (0, 24),   # All hours (baseline)
    ],

    # Streak breaker configs (max_losses, pause_trades)
    'streak_configs': [
        (2, 1),
        (2, 2),
        (3, 2),
        (3, 3),
        (3, 5),
        (4, 3),
    ],

    # Direction filters to test
    'direction_filters': ['LONG', 'SHORT', 'ALL'],

    # Stop type filters (if you want to see performance by stop type)
    'stop_types': ['FIXED', 'DYNAMIC', 'ALL'],
}

# ============================================================================
# DATA LOADING
# ============================================================================

print("=" * 70)
print("VALOR (VALOR) STRATEGY BACKTESTER")
print("=" * 70)
print("\nAll simulations use ONLY real historical trade data.")

db = DatabaseAdapter()

# Get all closed trades with full detail
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
        stop_type,
        stop_points_used,
        initial_stop,
        ml_approved,
        ml_confidence
    FROM valor_closed_trades
    ORDER BY open_time ASC
""")

if not trades:
    print("No closed trades found")
    sys.exit(0)

# Convert to list of dicts with all available data
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
        'stop_type': r[9] or 'UNKNOWN',
        'stop_pts': float(r[10] or 0),
        'initial_stop': float(r[11] or 0),
        'ml_approved': r[12],
        'ml_confidence': float(r[13] or 0) if r[13] else None
    })

print(f"\nTotal historical trades: {len(all_trades)}")
total_pnl = sum(t['pnl'] for t in all_trades)
wins = sum(1 for t in all_trades if t['pnl'] >= 0)
print(f"Baseline P&L: ${total_pnl:.2f}")
print(f"Baseline Win Rate: {wins/len(all_trades)*100:.1f}%")

# Quick data summary
print("\nData Summary:")
directions = defaultdict(int)
regimes = defaultdict(int)
stop_types = defaultdict(int)
for t in all_trades:
    directions[t['direction']] += 1
    regimes[t['regime']] += 1
    stop_types[t['stop_type']] += 1

print(f"  Directions: {dict(directions)}")
print(f"  Regimes: {dict(regimes)}")
print(f"  Stop Types: {dict(stop_types)}")

# ============================================================================
# STRATEGY SIMULATORS - All use real data only
# ============================================================================

def calculate_stats(trades: List[Dict]) -> Dict[str, Any]:
    """Calculate statistics for a set of trades"""
    if not trades:
        return {
            'trades_taken': 0,
            'trades_skipped': 0,
            'pnl': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
        }

    pnl = sum(t['pnl'] for t in trades)
    wins_list = [t['pnl'] for t in trades if t['pnl'] >= 0]
    losses_list = [t['pnl'] for t in trades if t['pnl'] < 0]

    return {
        'trades_taken': len(trades),
        'trades_skipped': 0,
        'pnl': pnl,
        'wins': len(wins_list),
        'losses': len(losses_list),
        'win_rate': len(wins_list) / len(trades) * 100 if trades else 0,
        'avg_win': sum(wins_list) / len(wins_list) if wins_list else 0,
        'avg_loss': sum(losses_list) / len(losses_list) if losses_list else 0,
    }


def simulate_filter(trades: List[Dict],
                   filter_fn: Callable[[Dict], bool],
                   name: str = "") -> Dict[str, Any]:
    """
    Generic filter simulator - applies filter function to trades.
    Filter returns True to KEEP the trade.
    """
    taken = [t for t in trades if filter_fn(t)]
    skipped = [t for t in trades if not filter_fn(t)]

    stats = calculate_stats(taken)
    stats['trades_skipped'] = len(skipped)
    stats['skipped_pnl'] = sum(t['pnl'] for t in skipped)
    return stats


def simulate_max_same_direction(trades: List[Dict], max_same: int) -> Dict[str, Any]:
    """Limit positions in same direction (tracks open positions over time)"""
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

    stats = calculate_stats(taken)
    stats['trades_skipped'] = len(skipped)
    stats['skipped_pnl'] = sum(t['pnl'] for t in skipped)
    return stats


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

    stats = calculate_stats(taken)
    stats['trades_skipped'] = len(skipped)
    stats['skipped_pnl'] = sum(t['pnl'] for t in skipped)
    return stats


def simulate_combined(trades: List[Dict],
                     max_same_dir: Optional[int] = None,
                     allowed_regimes: Optional[List[str]] = None,
                     start_hour: int = 0,
                     end_hour: int = 24,
                     allowed_directions: Optional[List[str]] = None,
                     allowed_stop_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Combine multiple filters with configurable options"""
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
        if not skip_reason and allowed_regimes:
            if t['regime'] not in allowed_regimes:
                skip_reason = "regime"

        # Direction filter
        if not skip_reason and allowed_directions:
            if t['direction'] not in allowed_directions:
                skip_reason = "direction"

        # Stop type filter
        if not skip_reason and allowed_stop_types:
            if t['stop_type'] not in allowed_stop_types:
                skip_reason = "stop_type"

        # Same direction limit
        if not skip_reason and max_same_dir is not None:
            open_positions = [p for p in open_positions
                            if p['close_time'] and t['open_time'] and p['close_time'] > t['open_time']]
            same_dir = sum(1 for p in open_positions if p['direction'] == t['direction'])
            if same_dir >= max_same_dir:
                skip_reason = "max_same_dir"

        if skip_reason:
            skipped.append(t)
        else:
            taken.append(t)
            open_positions.append(t)

    stats = calculate_stats(taken)
    stats['trades_skipped'] = len(skipped)
    stats['skipped_pnl'] = sum(t['pnl'] for t in skipped)
    return stats


# ============================================================================
# RUN SIMULATIONS
# ============================================================================

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

strategies = {}

# 1. BASELINE - All trades as-is
strategies['BASELINE'] = calculate_stats(all_trades)

# 2. Direction limits
for max_dir in CONFIG['max_same_direction_values']:
    name = f'MAX_{max_dir}_SAME_DIR'
    strategies[name] = simulate_max_same_direction(all_trades, max_dir)

# 3. Time windows
time_window_names = {
    (8, 16): 'RTH_ONLY',
    (8, 17): 'RTH_EXTENDED',
    (8, 20): 'EXTENDED_HRS',
    (6, 22): 'ACTIVE_HRS',
}
for start, end in CONFIG['time_windows']:
    if (start, end) == (0, 24):
        continue  # Skip all hours (that's baseline)
    name = time_window_names.get((start, end), f'TIME_{start}_{end}')
    strategies[name] = simulate_filter(
        all_trades,
        lambda t, s=start, e=end: t['open_time'] and s <= t['open_time'].hour < e
    )

# 4. Regime filters
all_regime_patterns = set()
for t in all_trades:
    all_regime_patterns.add(t['regime'])

positive_regimes = [r for r in all_regime_patterns if 'POSITIVE' in r.upper()]
negative_regimes = [r for r in all_regime_patterns if 'NEGATIVE' in r.upper()]
neutral_regimes = [r for r in all_regime_patterns if 'NEUTRAL' in r.upper()]

if positive_regimes:
    strategies['POSITIVE_ONLY'] = simulate_filter(
        all_trades, lambda t: t['regime'] in positive_regimes
    )
if negative_regimes:
    strategies['NEGATIVE_ONLY'] = simulate_filter(
        all_trades, lambda t: t['regime'] in negative_regimes
    )
if neutral_regimes:
    strategies['NEUTRAL_ONLY'] = simulate_filter(
        all_trades, lambda t: t['regime'] in neutral_regimes
    )
if positive_regimes and neutral_regimes:
    strategies['NON_NEGATIVE'] = simulate_filter(
        all_trades, lambda t: t['regime'] in positive_regimes + neutral_regimes
    )

# 5. Streak breakers
for max_losses, pause in CONFIG['streak_configs']:
    name = f'STREAK_{max_losses}_PAUSE_{pause}'
    strategies[name] = simulate_streak_breaker(all_trades, max_losses, pause)

# 6. Direction filters (if we have both)
if len(directions) > 1:
    strategies['LONG_ONLY'] = simulate_filter(
        all_trades, lambda t: t['direction'] in ['LONG', 'long', 'Long']
    )
    strategies['SHORT_ONLY'] = simulate_filter(
        all_trades, lambda t: t['direction'] in ['SHORT', 'short', 'Short']
    )

# 7. Stop type filters (if we have both)
if len(stop_types) > 1:
    strategies['FIXED_ONLY'] = simulate_filter(
        all_trades, lambda t: t['stop_type'] == 'FIXED'
    )
    strategies['DYNAMIC_ONLY'] = simulate_filter(
        all_trades, lambda t: t['stop_type'] == 'DYNAMIC'
    )

# 8. ML filters (if we have ML data)
ml_trades = [t for t in all_trades if t['ml_approved'] is not None]
if ml_trades:
    strategies['ML_APPROVED'] = simulate_filter(
        all_trades, lambda t: t['ml_approved'] == True
    )
    strategies['ML_REJECTED'] = simulate_filter(
        all_trades, lambda t: t['ml_approved'] == False
    )

# 9. Combined strategies
strategies['COMBO_SAFE'] = simulate_combined(
    all_trades,
    max_same_dir=2,
    allowed_regimes=positive_regimes or None,
    start_hour=8,
    end_hour=16
)

strategies['COMBO_MODERATE'] = simulate_combined(
    all_trades,
    max_same_dir=2,
    start_hour=8,
    end_hour=20
)

strategies['COMBO_CAUTIOUS'] = simulate_combined(
    all_trades,
    max_same_dir=1,
    start_hour=6,
    end_hour=22
)

# Print results
print("\n{:<20} {:>8} {:>8} {:>10} {:>8} {:>10} {:>8}".format(
    "Strategy", "Trades", "Skipped", "P&L", "WinRate", "vs Base", "AvgTrade"))
print("-" * 80)

baseline_pnl = strategies['BASELINE']['pnl']

sorted_strategies = sorted(strategies.items(), key=lambda x: x[1]['pnl'], reverse=True)

for name, result in sorted_strategies:
    trades_taken = result['trades_taken']
    trades_skipped = result.get('trades_skipped', 0)
    pnl = result['pnl']
    win_rate = result.get('win_rate', (result['wins'] / trades_taken * 100) if trades_taken > 0 else 0)
    vs_base = pnl - baseline_pnl
    avg_trade = pnl / trades_taken if trades_taken > 0 else 0

    marker = "★" if pnl > baseline_pnl else ""
    print("{:<20} {:>8} {:>8} ${:>9.2f} {:>7.1f}% {:>+10.2f} ${:>7.2f} {}".format(
        name, trades_taken, trades_skipped, pnl, win_rate, vs_base, avg_trade, marker))

# ============================================================================
# DETAILED ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("DETAILED ANALYSIS")
print("=" * 70)

# Find best
best = max(strategies.items(), key=lambda x: x[1]['pnl'])
print(f"\n★ Best Strategy by P&L: {best[0]}")
print(f"  P&L: ${best[1]['pnl']:.2f}")
print(f"  Improvement: ${best[1]['pnl'] - baseline_pnl:.2f} vs baseline")
print(f"  Trades: {best[1]['trades_taken']} taken")

# Best by win rate (with min trades)
min_trades = len(all_trades) * 0.2  # At least 20% of trades
qualified = {k: v for k, v in strategies.items() if v['trades_taken'] >= min_trades}
if qualified:
    best_wr = max(qualified.items(), key=lambda x: x[1].get('win_rate', 0))
    print(f"\n★ Best Win Rate (≥{int(min_trades)} trades): {best_wr[0]}")
    print(f"  Win Rate: {best_wr[1].get('win_rate', 0):.1f}%")
    print(f"  P&L: ${best_wr[1]['pnl']:.2f}")

# Best by avg trade (with min trades)
if qualified:
    best_avg = max(qualified.items(), key=lambda x: x[1]['pnl'] / x[1]['trades_taken'] if x[1]['trades_taken'] > 0 else 0)
    avg_trade = best_avg[1]['pnl'] / best_avg[1]['trades_taken'] if best_avg[1]['trades_taken'] > 0 else 0
    print(f"\n★ Best Avg Trade (≥{int(min_trades)} trades): {best_avg[0]}")
    print(f"  Avg Trade: ${avg_trade:.2f}")
    print(f"  P&L: ${best_avg[1]['pnl']:.2f}")

# ============================================================================
# WIN/LOSS ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("WIN/LOSS ANALYSIS")
print("=" * 70)

wins_list = [t for t in all_trades if t['pnl'] >= 0]
losses_list = [t for t in all_trades if t['pnl'] < 0]

if wins_list:
    avg_win = sum(t['pnl'] for t in wins_list) / len(wins_list)
    max_win = max(t['pnl'] for t in wins_list)
    print(f"\nWINS: {len(wins_list)}")
    print(f"  Avg Win: ${avg_win:.2f}")
    print(f"  Max Win: ${max_win:.2f}")
    print(f"  Total: ${sum(t['pnl'] for t in wins_list):.2f}")

if losses_list:
    avg_loss = sum(t['pnl'] for t in losses_list) / len(losses_list)
    max_loss = min(t['pnl'] for t in losses_list)
    print(f"\nLOSSES: {len(losses_list)}")
    print(f"  Avg Loss: ${avg_loss:.2f}")
    print(f"  Max Loss: ${max_loss:.2f}")
    print(f"  Total: ${sum(t['pnl'] for t in losses_list):.2f}")

if wins_list and losses_list:
    profit_factor = abs(sum(t['pnl'] for t in wins_list) / sum(t['pnl'] for t in losses_list)) if sum(t['pnl'] for t in losses_list) != 0 else float('inf')
    print(f"\nProfit Factor: {profit_factor:.2f}")
    print(f"Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "")

# ============================================================================
# RECOMMENDATIONS
# ============================================================================
print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

improvements = []
for name, result in strategies.items():
    if result['pnl'] > baseline_pnl and name != 'BASELINE':
        improvements.append((name, result['pnl'] - baseline_pnl, result))

if improvements:
    improvements.sort(key=lambda x: x[1], reverse=True)
    print("\nStrategies that would have improved P&L:")
    for name, improvement, result in improvements[:10]:
        trades_pct = result['trades_taken'] / len(all_trades) * 100
        print(f"  • {name}: +${improvement:.2f} ({trades_pct:.0f}% of trades)")

    # Check patterns
    print("\nPotential improvements to implement:")

    top_names = [x[0] for x in improvements[:5]]

    if any('SAME_DIR' in name for name in top_names):
        best_dir = next((n for n in top_names if 'SAME_DIR' in n), None)
        if best_dir:
            max_dir = int(best_dir.split('_')[1])
            print(f"  → Limit to max {max_dir} same-direction positions")

    if any('POSITIVE' in name for name in top_names):
        print("  → Consider filtering to POSITIVE gamma regime only")

    if any('NEGATIVE' in name for name in top_names):
        print("  → Consider filtering to NEGATIVE gamma regime only")

    if any('RTH' in name or 'TIME' in name for name in top_names):
        best_time = next((n for n in top_names if 'RTH' in n or 'TIME' in n), None)
        if best_time:
            print(f"  → Consider time restriction: {best_time}")

    if any('STREAK' in name for name in top_names):
        best_streak = next((n for n in top_names if 'STREAK' in n), None)
        if best_streak:
            parts = best_streak.split('_')
            losses = parts[1]
            pause = parts[3]
            print(f"  → Implement streak breaker: pause {pause} trades after {losses} losses")

    if any('FIXED' in name for name in top_names):
        print("  → FIXED stops outperform DYNAMIC - stick with FIXED")

    if any('ML_APPROVED' in name for name in top_names):
        print("  → ML model is providing value - require ML approval")
else:
    print("\nNo strategy significantly outperformed baseline.")
    print("The current approach may be near-optimal for this data sample.")

print("\n" + "=" * 70)
print("NOTE: These are filters on actual historical trades.")
print("No mock or estimated data is used in these calculations.")
print("=" * 70)
