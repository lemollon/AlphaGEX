"""
Dynamic Strategy Statistics System
===================================

Automatically updates strategy win rates, confidence levels, and thresholds
based on backtest results. No manual updates required.

Changes are logged with timestamps and reasons.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path


# File paths for persistent storage
STATS_DIR = Path(__file__).parent / '.strategy_stats'
STRATEGY_STATS_FILE = STATS_DIR / 'strategy_stats.json'
MM_CONFIDENCE_FILE = STATS_DIR / 'mm_confidence.json'
CHANGE_LOG_FILE = STATS_DIR / 'change_log.jsonl'

# Ensure directory exists
STATS_DIR.mkdir(exist_ok=True)

# CACHE: To avoid reading the file on every call while still staying fresh
# Cache TTL is 60 seconds - stats will be re-read from file after this period
_stats_cache: Dict = None
_stats_cache_time: float = 0
STATS_CACHE_TTL_SECONDS = 60  # Refresh stats from file every 60 seconds


def log_change(category: str, item: str, old_value, new_value, reason: str):
    """Log all automatic changes with timestamp and reason"""
    change_entry = {
        'timestamp': datetime.now().isoformat(),
        'category': category,
        'item': item,
        'old_value': old_value,
        'new_value': new_value,
        'reason': reason
    }

    # Append to log file
    with open(CHANGE_LOG_FILE, 'a') as f:
        f.write(json.dumps(change_entry) + '\n')

    # Also print to console for visibility
    print(f"\n📊 AUTO-UPDATE: {category} > {item}")
    print(f"   Old: {old_value} → New: {new_value}")
    print(f"   Reason: {reason}")
    print(f"   Logged: {change_entry['timestamp']}\n")


def invalidate_stats_cache():
    """Force refresh of stats cache on next get_strategy_stats() call"""
    global _stats_cache, _stats_cache_time
    _stats_cache = None
    _stats_cache_time = 0


def get_strategy_stats() -> Dict:
    """
    Get current strategy statistics.
    Returns hardcoded defaults if no backtest data exists yet.

    Uses a 60-second cache to balance performance and freshness.
    Call invalidate_stats_cache() to force a refresh.
    """
    global _stats_cache, _stats_cache_time

    # Check if cache is still valid
    if _stats_cache is not None and (time.time() - _stats_cache_time) < STATS_CACHE_TTL_SECONDS:
        return _stats_cache

    if not STRATEGY_STATS_FILE.exists():
        # Return initial defaults (will be updated by first backtest)
        # CRITICAL: avg_win and avg_loss must be non-zero for Kelly calculation
        # These estimates are based on typical options trading performance
        return {
            'BULLISH_CALL_SPREAD': {
                'win_rate': 0.65,
                'avg_win': 15.0,   # Typical directional spread winner
                'avg_loss': 25.0,  # Directional spreads lose more when wrong
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'BEARISH_PUT_SPREAD': {
                'win_rate': 0.62,
                'avg_win': 15.0,
                'avg_loss': 25.0,
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'IRON_CONDOR': {
                'win_rate': 0.72,
                'avg_win': 8.0,    # Credit spreads have lower wins
                'avg_loss': 20.0,  # But larger losses when wrong
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'SHORT_CALL_CREDIT_SPREAD': {
                'win_rate': 0.70,
                'avg_win': 10.0,
                'avg_loss': 18.0,
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'SHORT_PUT_CREDIT_SPREAD': {
                'win_rate': 0.68,
                'avg_win': 10.0,
                'avg_loss': 18.0,
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'NEGATIVE_GEX_SQUEEZE': {
                'win_rate': 0.75,
                'avg_win': 20.0,   # Squeeze trades can be very profitable
                'avg_loss': 15.0,  # But managed losses when thesis is wrong
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            },
            'LONG_STRADDLE': {
                'win_rate': 0.55,
                'avg_win': 25.0,   # Straddles need big moves
                'avg_loss': 20.0,  # Theta decay hurts
                'total_trades': 0,
                'last_updated': None,
                'source': 'initial_estimate'
            }
        }

    with open(STRATEGY_STATS_FILE, 'r') as f:
        _stats_cache = json.load(f)
        _stats_cache_time = time.time()
        return _stats_cache


def update_strategy_stats(strategy_name: str, backtest_results: Dict):
    """
    Automatically update strategy statistics from backtest results.

    Args:
        strategy_name: Name of strategy (e.g., 'BULLISH_CALL_SPREAD')
        backtest_results: Results from BacktestResults.to_dict()
    """
    current_stats = get_strategy_stats()

    old_stats = current_stats.get(strategy_name, {})
    old_win_rate = old_stats.get('win_rate', 0.0)

    # Extract new stats from backtest
    new_win_rate = backtest_results['win_rate'] / 100  # Convert from percentage
    avg_win = backtest_results.get('avg_win_pct', 0.0)
    avg_loss = backtest_results.get('avg_loss_pct', 0.0)
    total_trades = backtest_results['total_trades']

    # Only update if we have significant data (at least 10 trades)
    if total_trades < 10:
        reason = f"Insufficient data ({total_trades} trades < 10 minimum). Keeping current estimate."
        print(f"⚠️  {strategy_name}: {reason}")
        return

    # Update stats
    new_stats = {
        'win_rate': round(new_win_rate, 4),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'total_trades': total_trades,
        'expectancy': round(backtest_results.get('expectancy_pct', 0.0), 2),
        'sharpe_ratio': round(backtest_results.get('sharpe_ratio', 0.0), 2),
        'last_updated': datetime.now().isoformat(),
        'source': 'backtest',
        'backtest_period': f"{backtest_results['start_date']} to {backtest_results['end_date']}"
    }

    current_stats[strategy_name] = new_stats

    # Save to file
    with open(STRATEGY_STATS_FILE, 'w') as f:
        json.dump(current_stats, f, indent=2)

    # Invalidate cache so next read gets fresh data
    invalidate_stats_cache()

    # Log the change
    reason = f"Updated from backtest ({total_trades} trades, {backtest_results['start_date']} to {backtest_results['end_date']})"
    log_change(
        category='STRATEGY_STATS',
        item=strategy_name,
        old_value=f"win_rate={old_win_rate:.1%}",
        new_value=f"win_rate={new_win_rate:.1%}, expectancy={new_stats['expectancy']:.2f}%",
        reason=reason
    )


def calculate_mm_confidence(net_gex: float, spot_price: float, flip_point: float) -> Dict:
    """
    Dynamically calculate MM state confidence based on actual GEX data.

    Confidence is based on:
    1. How far from threshold (stronger signal = higher confidence)
    2. Distance from flip point (closer = higher confidence)
    3. GEX magnitude (larger = higher confidence)

    Returns dict with MM state and calculated confidence (0-100)
    """
    from config import get_gex_thresholds

    # Get adaptive thresholds
    thresholds = get_gex_thresholds('SPY', avg_gex=None)

    # Base confidence starts at 50%
    confidence = 50.0

    # Determine state and calculate confidence
    if net_gex < thresholds['extreme_negative']:
        state = 'PANICKING'
        # How far beyond threshold? (more = higher confidence)
        excess = abs(net_gex) - abs(thresholds['extreme_negative'])
        confidence_boost = min(40, (excess / abs(thresholds['extreme_negative'])) * 40)
        confidence += confidence_boost

    elif net_gex < thresholds['high_negative']:
        state = 'TRAPPED'
        excess = abs(net_gex) - abs(thresholds['high_negative'])
        confidence_boost = min(35, (excess / abs(thresholds['high_negative'])) * 35)
        confidence += confidence_boost

    elif net_gex < thresholds['moderate_negative']:
        state = 'HUNTING'
        excess = abs(net_gex) - abs(thresholds['moderate_negative'])
        confidence_boost = min(20, (excess / abs(thresholds['moderate_negative'])) * 20)
        confidence += confidence_boost

    elif net_gex > thresholds['extreme_positive']:
        state = 'DEFENDING_AGGRESSIVE'
        excess = net_gex - thresholds['extreme_positive']
        confidence_boost = min(35, (excess / thresholds['extreme_positive']) * 35)
        confidence += confidence_boost

    elif net_gex > thresholds['moderate_positive']:
        state = 'DEFENDING'
        excess = net_gex - thresholds['moderate_positive']
        confidence_boost = min(25, (excess / thresholds['moderate_positive']) * 25)
        confidence += confidence_boost

    else:
        state = 'NEUTRAL'
        confidence = 50.0  # Neutral = exactly 50% confidence

    # Additional confidence boost for distance from flip point
    if flip_point and spot_price:
        distance_pct = abs((spot_price - flip_point) / flip_point * 100)
        if distance_pct > 2.0:  # More than 2% from flip
            flip_boost = min(10, distance_pct / 2)
            confidence += flip_boost

    # Cap at 95% (never 100% certain in markets)
    confidence = min(95.0, confidence)

    return {
        'state': state,
        'confidence': round(confidence, 1),
        'net_gex': net_gex,
        'threshold_used': get_threshold_for_state(state, thresholds)
    }


def get_threshold_for_state(state: str, thresholds: Dict) -> float:
    """Get the threshold value for a given MM state"""
    mapping = {
        'PANICKING': thresholds['extreme_negative'],
        'TRAPPED': thresholds['high_negative'],
        'HUNTING': thresholds['moderate_negative'],
        'DEFENDING': thresholds['moderate_positive'],
        'DEFENDING_AGGRESSIVE': thresholds['extreme_positive'],
        'NEUTRAL': 0
    }
    return mapping.get(state, 0)


def get_mm_states() -> Dict:
    """
    Get Market Maker states with DYNAMIC configuration.
    Confidence values are calculated, not hardcoded.
    """
    from config import get_gex_thresholds

    # Get adaptive thresholds
    thresholds = get_gex_thresholds('SPY', avg_gex=None)

    return {
        'PANICKING': {
            'threshold': thresholds['extreme_negative'],
            'behavior': 'Forced buying on rallies, panic covering',
            'confidence': 90,  # Will be overridden by calculate_mm_confidence()
            'action': 'RIDE: Maximum aggression on squeeze',
            'description': 'Extreme short gamma - MMs in capitulation mode'
        },
        'TRAPPED': {
            'threshold': thresholds['high_negative'],
            'behavior': 'Forced buying on rallies, selling on dips',
            'confidence': 85,  # Will be overridden by calculate_mm_confidence()
            'action': 'HUNT: Buy calls on any approach to flip point',
            'description': 'High short gamma - MMs trapped in losing positions'
        },
        'HUNTING': {
            'threshold': thresholds['moderate_negative'],
            'behavior': 'Aggressive positioning for direction',
            'confidence': 60,  # Will be overridden by calculate_mm_confidence()
            'action': 'WAIT: Let them show their hand first',
            'description': 'Moderate short gamma - MMs hunting for stops'
        },
        'DEFENDING': {
            'threshold': thresholds['moderate_positive'],
            'behavior': 'Selling rallies aggressively, buying dips',
            'confidence': 70,  # Will be overridden by calculate_mm_confidence()
            'action': 'FADE: Sell calls at resistance, puts at support',
            'description': 'Positive gamma - MMs defending positions'
        },
        'DEFENDING_AGGRESSIVE': {
            'threshold': thresholds['extreme_positive'],
            'behavior': 'Aggressively pinning price to flip point',
            'confidence': 85,  # Will be overridden by calculate_mm_confidence()
            'action': 'FADE_HARD: Strong mean reversion trades',
            'description': 'Extreme positive gamma - MMs have full control'
        },
        'NEUTRAL': {
            'threshold': 0,
            'behavior': 'Balanced positioning, waiting for direction',
            'confidence': 50,  # Will be overridden by calculate_mm_confidence()
            'action': 'RANGE: Iron condors between walls',
            'description': 'Neutral gamma - No strong dealer positioning'
        }
    }


def get_recent_changes(limit: int = 20) -> list:
    """Get recent automatic changes from log"""
    if not CHANGE_LOG_FILE.exists():
        return []

    changes = []
    with open(CHANGE_LOG_FILE, 'r') as f:
        for line in f:
            changes.append(json.loads(line))

    # Return most recent first
    return list(reversed(changes[-limit:]))


def print_change_summary():
    """Print summary of recent automatic updates"""
    changes = get_recent_changes(limit=10)

    if not changes:
        print("📊 No automatic updates yet")
        return

    print("\n" + "="*70)
    print("📊 RECENT AUTOMATIC UPDATES")
    print("="*70)

    for change in changes:
        print(f"\n[{change['timestamp']}]")
        print(f"  {change['category']} > {change['item']}")
        print(f"  {change['old_value']} → {change['new_value']}")
        print(f"  Reason: {change['reason']}")

    print("\n" + "="*70 + "\n")


# Initialize on import
if __name__ != '__main__':
    # Check if we need to create initial files
    if not STRATEGY_STATS_FILE.exists():
        initial_stats = get_strategy_stats()
        with open(STRATEGY_STATS_FILE, 'w') as f:
            json.dump(initial_stats, f, indent=2)
        print("✅ Initialized strategy stats with default estimates")
        print("   These will auto-update when backtests run")
