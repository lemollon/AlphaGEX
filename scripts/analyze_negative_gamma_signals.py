#!/usr/bin/env python3
"""
Analyze VALOR negative gamma signal performance by direction and signal source.

This script answers:
1. In NEGATIVE gamma, how do LONGs perform vs SHORTs?
2. What signal_source triggered each trade (GEX_MOMENTUM vs GEX_WALL_BOUNCE)?
3. What market conditions (price vs flip, near walls) led to wins vs losses?

Run: python scripts/analyze_negative_gamma_signals.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
from collections import defaultdict

print("=" * 70)
print("VALOR NEGATIVE GAMMA SIGNAL ANALYSIS")
print("=" * 70)

conn = get_connection()
cursor = conn.cursor()

# ============================================================================
# 1. CLOSED TRADES - Actual P&L by direction in negative gamma
# ============================================================================
print("\n" + "=" * 70)
print("CLOSED TRADES - NEGATIVE GAMMA ONLY")
print("=" * 70)

cursor.execute("""
    SELECT
        direction,
        COUNT(*) as count,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(realized_pnl) as total_pnl,
        AVG(realized_pnl) as avg_pnl,
        signal_source
    FROM valor_closed_trades
    WHERE gamma_regime = 'NEGATIVE'
    GROUP BY direction, signal_source
    ORDER BY direction, signal_source
""")

rows = cursor.fetchall()
if rows:
    print("\nBy Direction + Signal Source:")
    print("-" * 70)
    print(f"{'Direction':<10} {'Source':<25} {'Count':>6} {'Wins':>6} {'WinRate':>8} {'Total P&L':>12} {'Avg P&L':>10}")
    print("-" * 70)

    direction_totals = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})

    for row in rows:
        direction, count, wins, total_pnl, avg_pnl, source = row
        wins = wins or 0
        total_pnl = float(total_pnl or 0)
        avg_pnl = float(avg_pnl or 0)
        win_rate = (wins / count * 100) if count > 0 else 0
        source = source or 'UNKNOWN'

        print(f"{direction:<10} {source:<25} {count:>6} {wins:>6} {win_rate:>7.1f}% ${total_pnl:>11.2f} ${avg_pnl:>9.2f}")

        direction_totals[direction]['count'] += count
        direction_totals[direction]['wins'] += wins
        direction_totals[direction]['pnl'] += total_pnl

    print("-" * 70)
    print("\nTotals by Direction:")
    for direction, totals in direction_totals.items():
        win_rate = (totals['wins'] / totals['count'] * 100) if totals['count'] > 0 else 0
        avg_pnl = totals['pnl'] / totals['count'] if totals['count'] > 0 else 0
        print(f"  {direction}: {totals['count']} trades, {totals['wins']} wins ({win_rate:.1f}%), ${totals['pnl']:.2f} total, ${avg_pnl:.2f} avg")
else:
    print("No negative gamma closed trades found")

# ============================================================================
# 2. SCAN ACTIVITY - Signal generation patterns
# ============================================================================
print("\n" + "=" * 70)
print("SCAN ACTIVITY - NEGATIVE GAMMA SIGNALS GENERATED")
print("=" * 70)

cursor.execute("""
    SELECT
        signal_direction,
        signal_source,
        COUNT(*) as count,
        COUNT(CASE WHEN trade_executed THEN 1 END) as traded,
        SUM(CASE WHEN trade_outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN trade_outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
        SUM(realized_pnl) as total_pnl
    FROM valor_scan_activity
    WHERE gamma_regime = 'NEGATIVE'
      AND signal_direction IS NOT NULL
    GROUP BY signal_direction, signal_source
    ORDER BY signal_direction, signal_source
""")

rows = cursor.fetchall()
if rows:
    print("\nSignals Generated (NEGATIVE gamma only):")
    print("-" * 90)
    print(f"{'Direction':<10} {'Source':<25} {'Generated':>10} {'Traded':>8} {'Wins':>6} {'Losses':>8} {'P&L':>12}")
    print("-" * 90)

    for row in rows:
        direction, source, count, traded, wins, losses, pnl = row
        wins = wins or 0
        losses = losses or 0
        traded = traded or 0
        pnl = float(pnl or 0)
        source = source or 'UNKNOWN'

        print(f"{direction:<10} {source:<25} {count:>10} {traded:>8} {wins:>6} {losses:>8} ${pnl:>11.2f}")
else:
    print("No negative gamma scan activity found")

# ============================================================================
# 3. DETAILED CONTEXT - What conditions led to trades
# ============================================================================
print("\n" + "=" * 70)
print("TRADE CONTEXT ANALYSIS - NEGATIVE GAMMA")
print("=" * 70)

# Get recent negative gamma trades with full context
cursor.execute("""
    SELECT
        direction,
        signal_source,
        underlying_price,
        flip_point,
        call_wall,
        put_wall,
        realized_pnl,
        trade_outcome,
        full_reasoning,
        scan_time
    FROM valor_scan_activity
    WHERE gamma_regime = 'NEGATIVE'
      AND trade_executed = TRUE
      AND trade_outcome IS NOT NULL
    ORDER BY scan_time DESC
    LIMIT 30
""")

trades = cursor.fetchall()
if trades:
    print(f"\nLast {len(trades)} NEGATIVE gamma trades with known outcomes:")
    print("-" * 100)

    # Analyze patterns
    long_wins = []
    long_losses = []
    short_wins = []
    short_losses = []

    for trade in trades:
        direction, source, price, flip, call_wall, put_wall, pnl, outcome, reasoning, scan_time = trade
        price = float(price or 0)
        flip = float(flip or 0)
        call_wall = float(call_wall or 0)
        put_wall = float(put_wall or 0)
        pnl = float(pnl or 0)

        # Calculate context
        dist_from_flip = price - flip if flip > 0 else 0
        dist_to_call = call_wall - price if call_wall > 0 else 999
        dist_to_put = price - put_wall if put_wall > 0 else 999

        above_flip = "ABOVE" if dist_from_flip > 0 else "BELOW" if dist_from_flip < 0 else "AT"
        near_call = dist_to_call < 10  # Within 10 pts
        near_put = dist_to_put < 10

        trade_data = {
            'direction': direction,
            'source': source,
            'price': price,
            'flip': flip,
            'dist_from_flip': dist_from_flip,
            'above_flip': above_flip,
            'near_call': near_call,
            'near_put': near_put,
            'pnl': pnl,
            'outcome': outcome,
            'reasoning': reasoning[:100] if reasoning else ''
        }

        if direction == 'LONG':
            if pnl > 0:
                long_wins.append(trade_data)
            else:
                long_losses.append(trade_data)
        else:
            if pnl > 0:
                short_wins.append(trade_data)
            else:
                short_losses.append(trade_data)

    # Print pattern analysis
    print("\nPATTERN ANALYSIS:")
    print("-" * 50)

    print(f"\nLONG WINS in NEGATIVE gamma: {len(long_wins)}")
    if long_wins:
        above_flip_count = sum(1 for t in long_wins if t['above_flip'] == 'ABOVE')
        below_flip_count = sum(1 for t in long_wins if t['above_flip'] == 'BELOW')
        near_put_count = sum(1 for t in long_wins if t['near_put'])
        wall_bounce_count = sum(1 for t in long_wins if 'WALL_BOUNCE' in (t['source'] or ''))
        momentum_count = sum(1 for t in long_wins if 'MOMENTUM' in (t['source'] or ''))
        print(f"  Above flip: {above_flip_count}, Below flip: {below_flip_count}")
        print(f"  Near put wall: {near_put_count}")
        print(f"  Signal sources: WALL_BOUNCE={wall_bounce_count}, MOMENTUM={momentum_count}")
        avg_pnl = sum(t['pnl'] for t in long_wins) / len(long_wins)
        print(f"  Avg P&L: ${avg_pnl:.2f}")

    print(f"\nLONG LOSSES in NEGATIVE gamma: {len(long_losses)}")
    if long_losses:
        above_flip_count = sum(1 for t in long_losses if t['above_flip'] == 'ABOVE')
        below_flip_count = sum(1 for t in long_losses if t['above_flip'] == 'BELOW')
        near_put_count = sum(1 for t in long_losses if t['near_put'])
        near_call_count = sum(1 for t in long_losses if t['near_call'])
        wall_bounce_count = sum(1 for t in long_losses if 'WALL_BOUNCE' in (t['source'] or ''))
        momentum_count = sum(1 for t in long_losses if 'MOMENTUM' in (t['source'] or ''))
        print(f"  Above flip: {above_flip_count}, Below flip: {below_flip_count}")
        print(f"  Near put wall: {near_put_count}, Near call wall: {near_call_count}")
        print(f"  Signal sources: WALL_BOUNCE={wall_bounce_count}, MOMENTUM={momentum_count}")
        avg_pnl = sum(t['pnl'] for t in long_losses) / len(long_losses)
        print(f"  Avg P&L: ${avg_pnl:.2f}")

    print(f"\nSHORT WINS in NEGATIVE gamma: {len(short_wins)}")
    if short_wins:
        above_flip_count = sum(1 for t in short_wins if t['above_flip'] == 'ABOVE')
        below_flip_count = sum(1 for t in short_wins if t['above_flip'] == 'BELOW')
        near_call_count = sum(1 for t in short_wins if t['near_call'])
        wall_bounce_count = sum(1 for t in short_wins if 'WALL_BOUNCE' in (t['source'] or ''))
        momentum_count = sum(1 for t in short_wins if 'MOMENTUM' in (t['source'] or ''))
        print(f"  Above flip: {above_flip_count}, Below flip: {below_flip_count}")
        print(f"  Near call wall: {near_call_count}")
        print(f"  Signal sources: WALL_BOUNCE={wall_bounce_count}, MOMENTUM={momentum_count}")
        avg_pnl = sum(t['pnl'] for t in short_wins) / len(short_wins)
        print(f"  Avg P&L: ${avg_pnl:.2f}")

    print(f"\nSHORT LOSSES in NEGATIVE gamma: {len(short_losses)}")
    if short_losses:
        above_flip_count = sum(1 for t in short_losses if t['above_flip'] == 'ABOVE')
        below_flip_count = sum(1 for t in short_losses if t['above_flip'] == 'BELOW')
        near_call_count = sum(1 for t in short_losses if t['near_call'])
        near_put_count = sum(1 for t in short_losses if t['near_put'])
        wall_bounce_count = sum(1 for t in short_losses if 'WALL_BOUNCE' in (t['source'] or ''))
        momentum_count = sum(1 for t in short_losses if 'MOMENTUM' in (t['source'] or ''))
        print(f"  Above flip: {above_flip_count}, Below flip: {below_flip_count}")
        print(f"  Near call wall: {near_call_count}, Near put wall: {near_put_count}")
        print(f"  Signal sources: WALL_BOUNCE={wall_bounce_count}, MOMENTUM={momentum_count}")
        avg_pnl = sum(t['pnl'] for t in short_losses) / len(short_losses)
        print(f"  Avg P&L: ${avg_pnl:.2f}")

    # Key insight
    print("\n" + "=" * 70)
    print("KEY INSIGHTS")
    print("=" * 70)

    total_long = len(long_wins) + len(long_losses)
    total_short = len(short_wins) + len(short_losses)

    if total_long > 0:
        long_wr = len(long_wins) / total_long * 100
        long_pnl = sum(t['pnl'] for t in long_wins + long_losses)
        print(f"\nLONG in NEGATIVE gamma: {total_long} trades, {long_wr:.1f}% win rate, ${long_pnl:.2f} total")

    if total_short > 0:
        short_wr = len(short_wins) / total_short * 100
        short_pnl = sum(t['pnl'] for t in short_wins + short_losses)
        print(f"SHORT in NEGATIVE gamma: {total_short} trades, {short_wr:.1f}% win rate, ${short_pnl:.2f} total")

    # Wall bounce specific analysis
    all_trades = long_wins + long_losses + short_wins + short_losses
    wall_bounce_trades = [t for t in all_trades if 'WALL_BOUNCE' in (t['source'] or '')]
    momentum_trades = [t for t in all_trades if 'MOMENTUM' in (t['source'] or '')]

    if wall_bounce_trades:
        wb_wins = sum(1 for t in wall_bounce_trades if t['pnl'] > 0)
        wb_pnl = sum(t['pnl'] for t in wall_bounce_trades)
        print(f"\nWALL_BOUNCE signals: {len(wall_bounce_trades)} trades, {wb_wins} wins ({wb_wins/len(wall_bounce_trades)*100:.1f}%), ${wb_pnl:.2f}")

        # Breakdown by direction
        wb_long = [t for t in wall_bounce_trades if t['direction'] == 'LONG']
        wb_short = [t for t in wall_bounce_trades if t['direction'] == 'SHORT']
        if wb_long:
            wb_long_wins = sum(1 for t in wb_long if t['pnl'] > 0)
            wb_long_pnl = sum(t['pnl'] for t in wb_long)
            print(f"  LONG wall bounce: {len(wb_long)} trades, {wb_long_wins} wins, ${wb_long_pnl:.2f}")
        if wb_short:
            wb_short_wins = sum(1 for t in wb_short if t['pnl'] > 0)
            wb_short_pnl = sum(t['pnl'] for t in wb_short)
            print(f"  SHORT wall bounce: {len(wb_short)} trades, {wb_short_wins} wins, ${wb_short_pnl:.2f}")

    if momentum_trades:
        mom_wins = sum(1 for t in momentum_trades if t['pnl'] > 0)
        mom_pnl = sum(t['pnl'] for t in momentum_trades)
        print(f"\nMOMENTUM signals: {len(momentum_trades)} trades, {mom_wins} wins ({mom_wins/len(momentum_trades)*100:.1f}%), ${mom_pnl:.2f}")

        # Breakdown by direction
        mom_long = [t for t in momentum_trades if t['direction'] == 'LONG']
        mom_short = [t for t in momentum_trades if t['direction'] == 'SHORT']
        if mom_long:
            mom_long_wins = sum(1 for t in mom_long if t['pnl'] > 0)
            mom_long_pnl = sum(t['pnl'] for t in mom_long)
            print(f"  LONG momentum: {len(mom_long)} trades, {mom_long_wins} wins, ${mom_long_pnl:.2f}")
        if mom_short:
            mom_short_wins = sum(1 for t in mom_short if t['pnl'] > 0)
            mom_short_pnl = sum(t['pnl'] for t in mom_short)
            print(f"  SHORT momentum: {len(mom_short)} trades, {mom_short_wins} wins, ${mom_short_pnl:.2f}")

else:
    print("No negative gamma trades with outcomes found")

conn.close()

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
