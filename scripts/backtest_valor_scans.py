#!/usr/bin/env python3
"""
VALOR (HERACLES) Scan-Based Backtester
======================================
Backtests strategies using REAL scan activity data from heracles_scan_activity.

This uses actual market conditions recorded at each scan point:
- Price data (underlying_price, bid, ask)
- GEX context (gamma_regime, gex_value, flip_point, walls)
- VIX, ATR
- Signal direction and confidence
- Actual trade outcomes

Run: python scripts/backtest_valor_scans.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Callable, Optional, Tuple

# ============================================================================
# CONFIGURATION - Adjustable parameters for strategy testing
# ============================================================================

CONFIG = {
    # Stop/Target in points (MES = $5 per point)
    'stop_points': 2.5,
    'target_points': 6.0,
    'point_value': 5.0,  # $5 per point for MES

    # Max concurrent positions
    'max_positions': 5,
    'max_same_direction': 3,

    # Min confidence to take trade
    'min_confidence': 0.5,
    'min_win_probability': 0.50,

    # Time filters (hours in CT)
    'trade_start_hour': 0,  # 0 = no restriction
    'trade_end_hour': 24,   # 24 = no restriction

    # Regime filters
    'allowed_regimes': None,  # None = all, or ['POSITIVE'], ['NEGATIVE'], etc.

    # Streak management
    'max_consecutive_losses': 0,  # 0 = disabled
    'pause_after_losses': 0,
}

# ============================================================================
# DATA LOADING
# ============================================================================

print("=" * 70)
print("VALOR (HERACLES) SCAN-BASED BACKTESTER")
print("=" * 70)
print("\nUsing REAL scan activity data from heracles_scan_activity")

db = DatabaseAdapter()

# Get all scan activity with full context
print("\nLoading scan data...")
scans = db.fetchall("""
    SELECT
        scan_id,
        scan_time,
        scan_number,
        outcome,
        action_taken,

        -- Price data
        underlying_price,
        bid_price,
        ask_price,

        -- GEX context
        gamma_regime,
        gex_value,
        flip_point,
        call_wall,
        put_wall,
        distance_to_flip_pct,

        -- Market conditions
        vix,
        atr,

        -- Signal data
        signal_direction,
        signal_source,
        signal_confidence,
        signal_win_probability,

        -- Bayesian state
        bayesian_win_probability,
        positive_gamma_win_rate,
        negative_gamma_win_rate,

        -- Session context
        is_overnight_session,
        day_of_week,
        hour_of_day,

        -- Trade result (if any)
        trade_executed,
        position_id,
        entry_price,
        stop_price,
        trade_outcome,
        realized_pnl,

        -- Stop type
        stop_type,
        stop_points_used
    FROM heracles_scan_activity
    ORDER BY scan_time ASC
""")

if not scans:
    print("No scan activity found")
    sys.exit(0)

# Convert to list of dicts
all_scans = []
for r in scans:
    all_scans.append({
        'scan_id': r[0],
        'scan_time': r[1],
        'scan_number': r[2],
        'outcome': r[3],
        'action_taken': r[4],
        'price': float(r[5]) if r[5] else None,
        'bid': float(r[6]) if r[6] else None,
        'ask': float(r[7]) if r[7] else None,
        'regime': r[8] or 'UNKNOWN',
        'gex_value': float(r[9]) if r[9] else None,
        'flip_point': float(r[10]) if r[10] else None,
        'call_wall': float(r[11]) if r[11] else None,
        'put_wall': float(r[12]) if r[12] else None,
        'distance_to_flip_pct': float(r[13]) if r[13] else None,
        'vix': float(r[14]) if r[14] else None,
        'atr': float(r[15]) if r[15] else None,
        'signal_direction': r[16],
        'signal_source': r[17],
        'signal_confidence': float(r[18]) if r[18] else None,
        'signal_win_prob': float(r[19]) if r[19] else None,
        'bayesian_win_prob': float(r[20]) if r[20] else None,
        'positive_gamma_wr': float(r[21]) if r[21] else None,
        'negative_gamma_wr': float(r[22]) if r[22] else None,
        'is_overnight': r[23],
        'day_of_week': r[24],
        'hour': r[25],
        'trade_executed': r[26],
        'position_id': r[27],
        'actual_entry': float(r[28]) if r[28] else None,
        'actual_stop': float(r[29]) if r[29] else None,
        'actual_outcome': r[30],
        'actual_pnl': float(r[31]) if r[31] else 0,
        'stop_type': r[32],
        'stop_pts': float(r[33]) if r[33] else None,
    })

print(f"Total scans loaded: {len(all_scans)}")

# Filter to scans with valid price data
valid_scans = [s for s in all_scans if s['price'] is not None]
print(f"Scans with price data: {len(valid_scans)}")

# Filter to scans with signals
signal_scans = [s for s in valid_scans if s['signal_direction'] is not None]
print(f"Scans with signals: {len(signal_scans)}")

# Scans where trade was actually executed
executed_scans = [s for s in valid_scans if s['trade_executed']]
print(f"Trades actually executed: {len(executed_scans)}")

# Scans with known outcome
outcome_scans = [s for s in executed_scans if s['actual_outcome'] is not None]
print(f"Trades with recorded outcome: {len(outcome_scans)}")

# ============================================================================
# STRATEGY SIMULATION ENGINE
# ============================================================================

class BacktestSimulator:
    """
    Simulates trading strategies on historical scan data.

    Uses actual price movements to determine outcomes.
    """

    def __init__(self, scans: List[Dict], config: Dict):
        self.scans = scans
        self.config = config
        self.positions = []  # Simulated open positions
        self.closed_trades = []
        self.consecutive_losses = 0
        self.paused_until_idx = 0

    def simulate_entry_rule(self, scan: Dict, rule_fn: Callable[[Dict], bool]) -> bool:
        """Check if entry rule allows trade"""
        return rule_fn(scan)

    def run(self, entry_rule: Callable[[Dict], bool], name: str = "Strategy") -> Dict[str, Any]:
        """
        Run simulation with given entry rule.

        Entry rule is a function that takes a scan dict and returns True to take trade.
        """
        self.positions = []
        self.closed_trades = []
        self.consecutive_losses = 0
        self.paused_until_idx = 0
        skipped_scans = []

        for idx, scan in enumerate(self.scans):
            # Skip if no signal
            if not scan['signal_direction']:
                continue

            # Skip if no price data
            if scan['price'] is None:
                continue

            # Pause check (streak breaker)
            if self.config['max_consecutive_losses'] > 0 and idx < self.paused_until_idx:
                skipped_scans.append(scan)
                continue

            # Apply entry rule
            if not entry_rule(scan):
                skipped_scans.append(scan)
                continue

            # Check position limits
            direction = scan['signal_direction']
            open_same_dir = sum(1 for p in self.positions if p['direction'] == direction)
            if open_same_dir >= self.config['max_same_direction']:
                skipped_scans.append(scan)
                continue

            if len(self.positions) >= self.config['max_positions']:
                skipped_scans.append(scan)
                continue

            # Simulate entry
            entry_price = scan['price']
            stop_pts = self.config['stop_points']
            target_pts = self.config['target_points']

            if direction in ['LONG', 'long', 'Long']:
                stop_price = entry_price - stop_pts
                target_price = entry_price + target_pts
            else:
                stop_price = entry_price + stop_pts
                target_price = entry_price - target_pts

            position = {
                'entry_idx': idx,
                'entry_time': scan['scan_time'],
                'direction': direction,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'target_price': target_price,
                'regime': scan['regime'],
                'scan': scan,
            }

            self.positions.append(position)

            # Check if we have actual outcome data from this scan
            if scan['trade_executed'] and scan['actual_pnl'] is not None:
                # Use actual recorded outcome
                self._close_position_with_outcome(position, scan['actual_pnl'], scan['actual_outcome'])
            else:
                # Try to simulate outcome by looking at future scans
                self._simulate_position_outcome(position, idx)

        # Calculate stats
        return self._calculate_stats(name, skipped_scans)

    def _close_position_with_outcome(self, position: Dict, pnl: float, outcome: str):
        """Close position with known outcome"""
        position['pnl'] = pnl
        position['outcome'] = outcome
        position['exit_reason'] = 'ACTUAL_DATA'

        self.closed_trades.append(position)
        if position in self.positions:
            self.positions.remove(position)

        # Track consecutive losses for streak breaker
        if pnl < 0:
            self.consecutive_losses += 1
            if self.config['max_consecutive_losses'] > 0:
                if self.consecutive_losses >= self.config['max_consecutive_losses']:
                    self.paused_until_idx = position['entry_idx'] + self.config['pause_after_losses'] + 1
                    self.consecutive_losses = 0
        else:
            self.consecutive_losses = 0

    def _simulate_position_outcome(self, position: Dict, entry_idx: int):
        """
        Simulate position outcome by scanning future price data.

        Looks at subsequent scans to see if stop or target hit first.
        """
        entry_price = position['entry_price']
        stop_price = position['stop_price']
        target_price = position['target_price']
        direction = position['direction']
        is_long = direction in ['LONG', 'long', 'Long']

        # Look at next N scans for price movement
        max_lookahead = 100  # Max scans to look ahead

        for i in range(entry_idx + 1, min(entry_idx + max_lookahead, len(self.scans))):
            future_scan = self.scans[i]
            future_price = future_scan['price']

            if future_price is None:
                continue

            # Check if target hit
            if is_long and future_price >= target_price:
                pnl = self.config['target_points'] * self.config['point_value']
                self._close_position_with_outcome(position, pnl, 'WIN_TARGET')
                return

            if not is_long and future_price <= target_price:
                pnl = self.config['target_points'] * self.config['point_value']
                self._close_position_with_outcome(position, pnl, 'WIN_TARGET')
                return

            # Check if stop hit
            if is_long and future_price <= stop_price:
                pnl = -self.config['stop_points'] * self.config['point_value']
                self._close_position_with_outcome(position, pnl, 'LOSS_STOP')
                return

            if not is_long and future_price >= stop_price:
                pnl = -self.config['stop_points'] * self.config['point_value']
                self._close_position_with_outcome(position, pnl, 'LOSS_STOP')
                return

        # If no stop/target hit, close at last available price
        last_price = None
        for i in range(min(entry_idx + max_lookahead, len(self.scans)) - 1, entry_idx, -1):
            if self.scans[i]['price'] is not None:
                last_price = self.scans[i]['price']
                break

        if last_price:
            if is_long:
                pnl = (last_price - entry_price) * self.config['point_value']
            else:
                pnl = (entry_price - last_price) * self.config['point_value']

            outcome = 'WIN_TIME' if pnl > 0 else 'LOSS_TIME'
            self._close_position_with_outcome(position, pnl, outcome)

    def _calculate_stats(self, name: str, skipped_scans: List[Dict]) -> Dict[str, Any]:
        """Calculate strategy statistics"""
        if not self.closed_trades:
            return {
                'name': name,
                'trades_taken': 0,
                'trades_skipped': len(skipped_scans),
                'pnl': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
            }

        wins = [t for t in self.closed_trades if t['pnl'] > 0]
        losses = [t for t in self.closed_trades if t['pnl'] < 0]
        breakeven = [t for t in self.closed_trades if t['pnl'] == 0]

        total_pnl = sum(t['pnl'] for t in self.closed_trades)
        total_wins = sum(t['pnl'] for t in wins)
        total_losses = sum(t['pnl'] for t in losses)

        profit_factor = abs(total_wins / total_losses) if total_losses != 0 else float('inf')

        return {
            'name': name,
            'trades_taken': len(self.closed_trades),
            'trades_skipped': len(skipped_scans),
            'pnl': total_pnl,
            'wins': len(wins),
            'losses': len(losses),
            'breakeven': len(breakeven),
            'win_rate': len(wins) / len(self.closed_trades) * 100 if self.closed_trades else 0,
            'avg_win': total_wins / len(wins) if wins else 0,
            'avg_loss': total_losses / len(losses) if losses else 0,
            'profit_factor': profit_factor,
            'trades': self.closed_trades,  # For detailed analysis
        }


# ============================================================================
# ENTRY RULES (Strategies to test)
# ============================================================================

def rule_all_signals(scan: Dict) -> bool:
    """Take all signals (baseline)"""
    return True


def rule_positive_gamma_only(scan: Dict) -> bool:
    """Only trade in positive gamma regime"""
    return 'POSITIVE' in scan['regime'].upper()


def rule_negative_gamma_only(scan: Dict) -> bool:
    """Only trade in negative gamma regime"""
    return 'NEGATIVE' in scan['regime'].upper()


def rule_high_confidence(scan: Dict, min_conf: float = 0.6) -> bool:
    """Only trade high confidence signals"""
    conf = scan['signal_confidence']
    return conf is not None and conf >= min_conf


def rule_high_win_prob(scan: Dict, min_prob: float = 0.55) -> bool:
    """Only trade high win probability signals"""
    prob = scan['signal_win_prob'] or scan['bayesian_win_prob']
    return prob is not None and prob >= min_prob


def rule_rth_only(scan: Dict) -> bool:
    """Only trade during regular hours (8 AM - 4 PM CT)"""
    hour = scan['hour']
    return hour is not None and 8 <= hour < 16


def rule_extended_hours(scan: Dict) -> bool:
    """Trade 6 AM - 8 PM CT"""
    hour = scan['hour']
    return hour is not None and 6 <= hour < 20


def rule_low_vix(scan: Dict, max_vix: float = 20) -> bool:
    """Only trade when VIX is low"""
    vix = scan['vix']
    return vix is not None and vix < max_vix


def rule_high_vix(scan: Dict, min_vix: float = 18) -> bool:
    """Only trade when VIX is elevated"""
    vix = scan['vix']
    return vix is not None and vix >= min_vix


def rule_near_flip(scan: Dict, max_pct: float = 0.5) -> bool:
    """Only trade when price is near flip point"""
    dist = scan['distance_to_flip_pct']
    return dist is not None and abs(dist) <= max_pct


def rule_momentum_direction(scan: Dict) -> bool:
    """Only trade in direction of GEX momentum"""
    regime = scan['regime'].upper()
    direction = scan['signal_direction'].upper() if scan['signal_direction'] else ''

    # In NEGATIVE gamma (momentum), follow direction
    if 'NEGATIVE' in regime:
        # Check if we're trading WITH momentum (not counter)
        return True

    # In POSITIVE gamma (mean reversion), trade counter to recent move
    return 'POSITIVE' in regime


def rule_not_overnight(scan: Dict) -> bool:
    """Skip overnight session"""
    return not scan['is_overnight']


def rule_weekday_filter(scan: Dict, allowed_days: List[int] = [0, 1, 2, 3, 4]) -> bool:
    """Only trade on certain weekdays (0=Mon, 4=Fri)"""
    dow = scan['day_of_week']
    return dow in allowed_days if dow is not None else True


# ============================================================================
# RUN SIMULATIONS
# ============================================================================

print("\n" + "=" * 70)
print("RUNNING STRATEGY SIMULATIONS")
print("=" * 70)

# Use scans with actual outcome data for most accurate results
# If not enough, use all signal scans
if len(outcome_scans) >= 10:
    test_scans = valid_scans  # Use all valid scans, simulator will use actual outcomes where available
    print(f"\nUsing all {len(test_scans)} valid scans (with {len(outcome_scans)} known outcomes)")
else:
    test_scans = valid_scans
    print(f"\nUsing all {len(test_scans)} valid scans for simulation")

results = []

# Create simulator
sim = BacktestSimulator(test_scans, CONFIG)

# Test strategies
strategies = [
    ("BASELINE", rule_all_signals),
    ("POSITIVE_GAMMA", rule_positive_gamma_only),
    ("NEGATIVE_GAMMA", rule_negative_gamma_only),
    ("HIGH_CONF_60", lambda s: rule_high_confidence(s, 0.60)),
    ("HIGH_CONF_65", lambda s: rule_high_confidence(s, 0.65)),
    ("HIGH_WIN_PROB_55", lambda s: rule_high_win_prob(s, 0.55)),
    ("HIGH_WIN_PROB_60", lambda s: rule_high_win_prob(s, 0.60)),
    ("RTH_ONLY", rule_rth_only),
    ("EXTENDED_HRS", rule_extended_hours),
    ("NOT_OVERNIGHT", rule_not_overnight),
    ("LOW_VIX", lambda s: rule_low_vix(s, 20)),
    ("HIGH_VIX", lambda s: rule_high_vix(s, 18)),
    ("NEAR_FLIP_0.5", lambda s: rule_near_flip(s, 0.5)),
    ("NEAR_FLIP_1.0", lambda s: rule_near_flip(s, 1.0)),
]

# Combined strategies
combined_strategies = [
    ("POS_GAMMA_RTH", lambda s: rule_positive_gamma_only(s) and rule_rth_only(s)),
    ("NEG_GAMMA_RTH", lambda s: rule_negative_gamma_only(s) and rule_rth_only(s)),
    ("HIGH_CONF_RTH", lambda s: rule_high_confidence(s, 0.6) and rule_rth_only(s)),
    ("POS_HIGH_CONF", lambda s: rule_positive_gamma_only(s) and rule_high_confidence(s, 0.6)),
    ("NOT_OVERNIGHT_HIGH", lambda s: rule_not_overnight(s) and rule_high_confidence(s, 0.6)),
]

all_strategies = strategies + combined_strategies

print(f"\nTesting {len(all_strategies)} strategies...")

for name, rule in all_strategies:
    result = sim.run(rule, name)
    results.append(result)
    print(f"  {name}: {result['trades_taken']} trades, ${result['pnl']:.2f}")

# ============================================================================
# RESULTS
# ============================================================================

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

# Sort by P&L
results.sort(key=lambda x: x['pnl'], reverse=True)

baseline = next((r for r in results if r['name'] == 'BASELINE'), results[0])
baseline_pnl = baseline['pnl']

print("\n{:<20} {:>8} {:>8} {:>10} {:>8} {:>8} {:>10}".format(
    "Strategy", "Trades", "Skipped", "P&L", "WinRate", "PF", "vs Base"))
print("-" * 80)

for r in results:
    vs_base = r['pnl'] - baseline_pnl
    marker = " **" if r['pnl'] > baseline_pnl and r['trades_taken'] >= 5 else ""
    print("{:<20} {:>8} {:>8} ${:>9.2f} {:>7.1f}% {:>7.2f} {:>+10.2f}{}".format(
        r['name'],
        r['trades_taken'],
        r['trades_skipped'],
        r['pnl'],
        r['win_rate'],
        r['profit_factor'] if r['profit_factor'] != float('inf') else 999.99,
        vs_base,
        marker
    ))

# ============================================================================
# DETAILED ANALYSIS
# ============================================================================

print("\n" + "=" * 70)
print("TOP STRATEGIES")
print("=" * 70)

# Filter to strategies with enough trades
min_trades = max(5, len(test_scans) * 0.01)  # At least 1% of scans or 5 trades
qualified = [r for r in results if r['trades_taken'] >= min_trades]

if qualified:
    best = qualified[0]  # Already sorted by P&L
    print(f"\nBest Strategy: {best['name']}")
    print(f"  Trades: {best['trades_taken']}")
    print(f"  P&L: ${best['pnl']:.2f}")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    print(f"  Profit Factor: {best['profit_factor']:.2f}")
    print(f"  vs Baseline: ${best['pnl'] - baseline_pnl:+.2f}")

    # Best by win rate
    best_wr = max(qualified, key=lambda x: x['win_rate'])
    if best_wr['name'] != best['name']:
        print(f"\nBest Win Rate: {best_wr['name']}")
        print(f"  Win Rate: {best_wr['win_rate']:.1f}%")
        print(f"  P&L: ${best_wr['pnl']:.2f}")

# ============================================================================
# RECOMMENDATIONS
# ============================================================================

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

improvements = [r for r in results if r['pnl'] > baseline_pnl and r['trades_taken'] >= min_trades]

if improvements:
    print("\nStrategies that outperform baseline:")
    for r in improvements[:5]:
        print(f"  - {r['name']}: +${r['pnl'] - baseline_pnl:.2f} ({r['trades_taken']} trades)")

    print("\nSuggested implementation:")
    top_names = [r['name'] for r in improvements[:3]]

    if any('POSITIVE' in n for n in top_names):
        print("  - Filter to POSITIVE gamma regime")
    if any('NEGATIVE' in n for n in top_names):
        print("  - Filter to NEGATIVE gamma regime")
    if any('RTH' in n for n in top_names):
        print("  - Restrict to RTH hours (8 AM - 4 PM CT)")
    if any('CONF' in n for n in top_names):
        print("  - Require minimum signal confidence")
    if any('WIN_PROB' in n for n in top_names):
        print("  - Require minimum win probability")
    if any('VIX' in n for n in top_names):
        print("  - Add VIX filter")
else:
    print("\nNo strategy significantly outperformed baseline.")
    print("Consider: Current approach may be near-optimal for this data sample.")

print("\n" + "=" * 70)
print("NOTE: All simulations use REAL price data from heracles_scan_activity")
print("=" * 70)
