#!/usr/bin/env python3
"""
VALOR (VALOR) Streak Analysis
=================================
Analyzes win/loss streaks to understand the pattern.

Run: python scripts/analyze_valor_streaks.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter
from datetime import datetime, timedelta
from collections import defaultdict

print("=" * 70)
print("VALOR (VALOR) STREAK ANALYSIS")
print("=" * 70)

db = DatabaseAdapter()

# Get all closed trades ordered by time
rows = db.fetchall("""
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
        stop_points_used
    FROM valor_closed_trades
    ORDER BY close_time ASC
""")

if not rows:
    print("No closed trades found")
    sys.exit(0)

trades = []
for r in rows:
    trades.append({
        'id': r[0],
        'direction': r[1],
        'regime': r[2],
        'entry': float(r[3] or 0),
        'exit': float(r[4] or 0),
        'pnl': float(r[5] or 0),
        'reason': r[6],
        'open_time': r[7],
        'close_time': r[8],
        'stop_type': r[9] or 'UNKNOWN',
        'stop_pts': float(r[10] or 0)
    })

print(f"\nTotal trades: {len(trades)}")

# ============================================================================
# 1. STREAK ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("1. WIN/LOSS STREAKS")
print("=" * 70)

streaks = []
current_streak = {'type': None, 'count': 0, 'pnl': 0, 'trades': []}

for t in trades:
    outcome = 'WIN' if t['pnl'] >= 0 else 'LOSS'

    if current_streak['type'] == outcome:
        current_streak['count'] += 1
        current_streak['pnl'] += t['pnl']
        current_streak['trades'].append(t)
    else:
        if current_streak['type']:
            streaks.append(current_streak.copy())
        current_streak = {'type': outcome, 'count': 1, 'pnl': t['pnl'], 'trades': [t]}

if current_streak['type']:
    streaks.append(current_streak)

win_streaks = [s for s in streaks if s['type'] == 'WIN']
loss_streaks = [s for s in streaks if s['type'] == 'LOSS']

print(f"\nTotal streaks: {len(streaks)}")
print(f"  Win streaks: {len(win_streaks)}")
print(f"  Loss streaks: {len(loss_streaks)}")

if win_streaks:
    max_win = max(win_streaks, key=lambda x: x['count'])
    avg_win = sum(s['count'] for s in win_streaks) / len(win_streaks)
    print(f"\nWin streaks:")
    print(f"  Longest: {max_win['count']} trades (${max_win['pnl']:.2f})")
    print(f"  Average: {avg_win:.1f} trades")

if loss_streaks:
    max_loss = max(loss_streaks, key=lambda x: x['count'])
    avg_loss = sum(s['count'] for s in loss_streaks) / len(loss_streaks)
    print(f"\nLoss streaks:")
    print(f"  Longest: {max_loss['count']} trades (${max_loss['pnl']:.2f})")
    print(f"  Average: {avg_loss:.1f} trades")

print("\nStreak distribution:")
for length in range(1, 8):
    w = len([s for s in win_streaks if s['count'] == length])
    l = len([s for s in loss_streaks if s['count'] == length])
    if w or l:
        print(f"  {length}-trade: {w} win streaks, {l} loss streaks")

# ============================================================================
# 2. CORRELATION ANALYSIS (Same direction trades)
# ============================================================================
print("\n" + "=" * 70)
print("2. DIRECTION CORRELATION")
print("=" * 70)

# Group trades by close_time proximity (within 5 minutes)
grouped_trades = []
current_group = []

for t in trades:
    if not current_group:
        current_group = [t]
    else:
        last_time = current_group[-1]['close_time']
        if t['close_time'] and last_time:
            diff = (t['close_time'] - last_time).total_seconds()
            if diff < 300:  # 5 minutes
                current_group.append(t)
            else:
                grouped_trades.append(current_group)
                current_group = [t]
        else:
            current_group.append(t)

if current_group:
    grouped_trades.append(current_group)

# Analyze groups with multiple same-direction trades
same_dir_groups = []
for group in grouped_trades:
    if len(group) >= 2:
        directions = [t['direction'] for t in group]
        if len(set(directions)) == 1:  # All same direction
            total_pnl = sum(t['pnl'] for t in group)
            same_dir_groups.append({
                'count': len(group),
                'direction': directions[0],
                'pnl': total_pnl,
                'outcome': 'WIN' if total_pnl >= 0 else 'LOSS'
            })

if same_dir_groups:
    print(f"\nFound {len(same_dir_groups)} groups of same-direction trades:")
    wins = sum(1 for g in same_dir_groups if g['outcome'] == 'WIN')
    losses = len(same_dir_groups) - wins
    print(f"  Group outcomes: {wins} wins, {losses} losses")
    print(f"  Total P&L from groups: ${sum(g['pnl'] for g in same_dir_groups):.2f}")

    # How much would limiting to 1 position have saved?
    excess_loss = 0
    for group in grouped_trades:
        if len(group) >= 2:
            # If we only took the first trade
            first_pnl = group[0]['pnl']
            total_pnl = sum(t['pnl'] for t in group)
            if total_pnl < first_pnl:
                excess_loss += (first_pnl - total_pnl)

    print(f"\n  If limited to 1 position, would have avoided: ${excess_loss:.2f} in losses")

# ============================================================================
# 3. REGIME ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("3. PERFORMANCE BY GAMMA REGIME")
print("=" * 70)

regime_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0, 'trades': []})

for t in trades:
    regime = t['regime'] or 'UNKNOWN'
    regime_stats[regime]['trades'].append(t)
    regime_stats[regime]['pnl'] += t['pnl']
    if t['pnl'] >= 0:
        regime_stats[regime]['wins'] += 1
    else:
        regime_stats[regime]['losses'] += 1

for regime, stats in sorted(regime_stats.items()):
    total = stats['wins'] + stats['losses']
    win_rate = (stats['wins'] / total * 100) if total > 0 else 0
    avg_pnl = stats['pnl'] / total if total > 0 else 0
    print(f"\n{regime}:")
    print(f"  Trades: {total}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${stats['pnl']:.2f}")
    print(f"  Avg P&L: ${avg_pnl:.2f}")

# ============================================================================
# 4. TIME OF DAY ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("4. PERFORMANCE BY HOUR")
print("=" * 70)

hour_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})

for t in trades:
    if t['open_time']:
        hour = t['open_time'].hour
        hour_stats[hour]['pnl'] += t['pnl']
        if t['pnl'] >= 0:
            hour_stats[hour]['wins'] += 1
        else:
            hour_stats[hour]['losses'] += 1

print("\nHour (CT) | Trades | Win Rate | Total P&L")
print("-" * 50)
for hour in sorted(hour_stats.keys()):
    stats = hour_stats[hour]
    total = stats['wins'] + stats['losses']
    win_rate = (stats['wins'] / total * 100) if total > 0 else 0
    marker = "✓" if win_rate > 55 else ("✗" if win_rate < 45 else " ")
    print(f"  {hour:02d}:00   | {total:6} | {win_rate:5.1f}%  | ${stats['pnl']:+8.2f} {marker}")

# ============================================================================
# 5. STOP TYPE ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("5. FIXED vs DYNAMIC STOPS")
print("=" * 70)

stop_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0, 'avg_pts': []})

for t in trades:
    stop_type = t['stop_type']
    stop_stats[stop_type]['pnl'] += t['pnl']
    stop_stats[stop_type]['avg_pts'].append(t['stop_pts'])
    if t['pnl'] >= 0:
        stop_stats[stop_type]['wins'] += 1
    else:
        stop_stats[stop_type]['losses'] += 1

for stop_type, stats in sorted(stop_stats.items()):
    total = stats['wins'] + stats['losses']
    win_rate = (stats['wins'] / total * 100) if total > 0 else 0
    avg_pts = sum(stats['avg_pts']) / len(stats['avg_pts']) if stats['avg_pts'] else 0
    print(f"\n{stop_type}:")
    print(f"  Trades: {total}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${stats['pnl']:.2f}")
    print(f"  Avg Stop Points: {avg_pts:.2f}")

# ============================================================================
# 6. RECOMMENDATIONS
# ============================================================================
print("\n" + "=" * 70)
print("6. RECOMMENDATIONS")
print("=" * 70)

recommendations = []

# Check regime performance
for regime, stats in regime_stats.items():
    total = stats['wins'] + stats['losses']
    win_rate = (stats['wins'] / total * 100) if total > 0 else 0
    if win_rate < 45 and total >= 5:
        recommendations.append(f"Consider avoiding {regime} regime (win rate: {win_rate:.0f}%)")
    elif win_rate > 55 and total >= 5:
        recommendations.append(f"Focus on {regime} regime (win rate: {win_rate:.0f}%)")

# Check hour performance
bad_hours = []
good_hours = []
for hour, stats in hour_stats.items():
    total = stats['wins'] + stats['losses']
    win_rate = (stats['wins'] / total * 100) if total > 0 else 0
    if win_rate < 40 and total >= 3:
        bad_hours.append(hour)
    elif win_rate > 60 and total >= 3:
        good_hours.append(hour)

if bad_hours:
    recommendations.append(f"Avoid trading during hours: {', '.join(f'{h}:00' for h in bad_hours)}")
if good_hours:
    recommendations.append(f"Best trading hours: {', '.join(f'{h}:00' for h in good_hours)}")

# Check streaks
if loss_streaks and max(s['count'] for s in loss_streaks) >= 4:
    recommendations.append("Implement streak circuit breaker (pause after 3 consecutive losses)")

# Check correlation
if same_dir_groups and len(same_dir_groups) >= 3:
    recommendations.append("Limit same-direction positions to reduce correlated losses")

if recommendations:
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
else:
    print("  No specific recommendations - data looks balanced")

print("\n" + "=" * 70)
