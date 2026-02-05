#!/usr/bin/env python3
"""
Backtest Part 2b: Calculate P&L from Breakout Triggers

This script:
1. Builds price timeline
2. Finds triggers (same as 2a)
3. Simulates position management with trailing stops
4. Calculates P&L
5. Compares to actual directional trades

Run on Render:
python scripts/backtest_breakout_part2b.py

Or paste the inline version below.
"""

# === INLINE VERSION FOR RENDER SHELL ===
# Copy everything below and paste into Render shell

import os
import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("=" * 70)
print("PART 2b: CALCULATE P&L FROM BREAKOUT TRIGGERS")
print("=" * 70)

# Config - adjust these to test different parameters
BREAKOUT = 5   # pts to trigger breakout
STOP = 8       # initial stop loss pts
TARGET = 15    # profit target pts
TRAIL = 5      # trailing stop distance pts

print(f"\nParameters: BREAKOUT={BREAKOUT}pt, STOP={STOP}pt, TARGET={TARGET}pt, TRAIL={TRAIL}pt")

# Step 1: Build price timeline
print("\n[1] Building price timeline...")
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity
    WHERE underlying_price > 0
    ORDER BY scan_time
""")
price_timeline = [(s[0], float(s[1])) for s in cursor.fetchall() if s[1]]
print(f"    {len(price_timeline)} price points")

# Step 2: Get entries
print("\n[2] Getting entries (9-11am CT, NEGATIVE gamma)...")
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity
    WHERE underlying_price > 0
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') >= 9
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') < 11
    ORDER BY scan_time
""")
entries = cursor.fetchall()
print(f"    {len(entries)} entry points")

def get_future_prices(entry_time, dur=120):
    end = entry_time + timedelta(minutes=dur)
    return [(t, p) for t, p in price_timeline if entry_time < t <= end]

# Step 3: Simulate trades with position management
print("\n[3] Simulating trades with trailing stops...")

results = {
    'trades': 0,
    'wins': 0,
    'losses': 0,
    'total_pnl': 0.0,
    'by_direction': {'LONG': {'n': 0, 'pnl': 0}, 'SHORT': {'n': 0, 'pnl': 0}},
    'by_exit': defaultdict(lambda: {'n': 0, 'pnl': 0}),
}

seen_dates = set()
trade_log = []

for scan_time, entry_price in entries:
    if scan_time.date() in seen_dates:
        continue
    seen_dates.add(scan_time.date())

    entry_price = float(entry_price)
    future = get_future_prices(scan_time)

    if not future:
        continue

    # Phase 1: Find breakout trigger
    direction = None
    trigger_price = 0
    trigger_idx = 0

    for i, (t, p) in enumerate(future):
        if p >= entry_price + BREAKOUT:
            direction = "LONG"
            trigger_price = entry_price + BREAKOUT
            trigger_idx = i
            break
        elif p <= entry_price - BREAKOUT:
            direction = "SHORT"
            trigger_price = entry_price - BREAKOUT
            trigger_idx = i
            break

    if not direction:
        continue

    # Phase 2: Position management with trailing stop
    remaining = future[trigger_idx + 1:]

    if direction == "LONG":
        stop_price = trigger_price - STOP
        target_price = trigger_price + TARGET
        trail_high = trigger_price
    else:  # SHORT
        stop_price = trigger_price + STOP
        target_price = trigger_price - TARGET
        trail_low = trigger_price

    exit_price = 0
    exit_reason = "TIME"

    for t, p in remaining:
        if direction == "LONG":
            # Update trailing stop if price moves up
            if p > trail_high:
                trail_high = p
                new_stop = trail_high - TRAIL
                if new_stop > stop_price:
                    stop_price = new_stop

            # Check exits
            if p >= target_price:
                exit_price = target_price
                exit_reason = "TARGET"
                break
            elif p <= stop_price:
                exit_price = stop_price
                exit_reason = "TRAIL" if stop_price > trigger_price - STOP else "STOP"
                break

        else:  # SHORT
            # Update trailing stop if price moves down
            if p < trail_low:
                trail_low = p
                new_stop = trail_low + TRAIL
                if new_stop < stop_price:
                    stop_price = new_stop

            # Check exits
            if p <= target_price:
                exit_price = target_price
                exit_reason = "TARGET"
                break
            elif p >= stop_price:
                exit_price = stop_price
                exit_reason = "TRAIL" if stop_price < trigger_price + STOP else "STOP"
                break

    # Time stop - use last price
    if exit_reason == "TIME" and remaining:
        exit_price = remaining[-1][1]

    # Calculate P&L
    if direction == "LONG":
        pnl_pts = exit_price - trigger_price
    else:
        pnl_pts = trigger_price - exit_price

    pnl_dollars = pnl_pts * 5  # $5/pt for MES

    # Record results
    results['trades'] += 1
    results['total_pnl'] += pnl_dollars
    results['by_direction'][direction]['n'] += 1
    results['by_direction'][direction]['pnl'] += pnl_dollars
    results['by_exit'][exit_reason]['n'] += 1
    results['by_exit'][exit_reason]['pnl'] += pnl_dollars

    if pnl_dollars > 0:
        results['wins'] += 1
    else:
        results['losses'] += 1

    trade_log.append({
        'date': scan_time.date(),
        'dir': direction,
        'entry': entry_price,
        'trigger': trigger_price,
        'exit': exit_price,
        'reason': exit_reason,
        'pnl': pnl_dollars,
    })

# Step 4: Get actual directional performance
print("\n[4] Getting actual directional performance...")
cursor.execute("""
    SELECT SUM(realized_pnl), COUNT(*),
           COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END)
    FROM heracles_scan_activity
    WHERE trade_executed = TRUE
      AND realized_pnl IS NOT NULL
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') >= 9
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') < 11
""")
actual = cursor.fetchone()
actual_pnl = float(actual[0]) if actual[0] else 0
actual_trades = actual[1] or 0
actual_wins = actual[2] or 0

# Print Results
print("\n" + "=" * 70)
print("BREAKOUT STRATEGY RESULTS")
print("=" * 70)

if results['trades'] > 0:
    win_rate = results['wins'] / results['trades'] * 100
    avg_pnl = results['total_pnl'] / results['trades']

    print(f"\nTrades: {results['trades']}")
    print(f"Win Rate: {win_rate:.1f}% ({results['wins']}W / {results['losses']}L)")
    print(f"Total P&L: ${results['total_pnl']:,.2f}")
    print(f"Avg P&L/trade: ${avg_pnl:.2f}")

    print(f"\nBY DIRECTION:")
    for d in ['LONG', 'SHORT']:
        data = results['by_direction'][d]
        if data['n'] > 0:
            print(f"  {d}: {data['n']} trades, ${data['pnl']:,.2f}")

    print(f"\nBY EXIT REASON:")
    for reason in ['TARGET', 'TRAIL', 'STOP', 'TIME']:
        data = results['by_exit'][reason]
        if data['n'] > 0:
            pct = data['n'] / results['trades'] * 100
            print(f"  {reason}: {data['n']} ({pct:.0f}%), ${data['pnl']:,.2f}")
else:
    print("\nNo trades executed")

# Comparison
print("\n" + "=" * 70)
print("COMPARISON: BREAKOUT vs ACTUAL DIRECTIONAL")
print("=" * 70)

print(f"\nACTUAL DIRECTIONAL (same time window):")
print(f"  Trades: {actual_trades}")
if actual_trades > 0:
    print(f"  Win Rate: {actual_wins/actual_trades*100:.1f}%")
    print(f"  Total P&L: ${actual_pnl:,.2f}")
    print(f"  Avg P&L: ${actual_pnl/actual_trades:.2f}")

print(f"\nBREAKOUT STRATEGY:")
print(f"  Trades: {results['trades']}")
if results['trades'] > 0:
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${results['total_pnl']:,.2f}")
    print(f"  Avg P&L: ${avg_pnl:.2f}")

diff = results['total_pnl'] - actual_pnl
better = "BREAKOUT" if diff > 0 else "DIRECTIONAL"
print(f"\n--> {better} is better by ${abs(diff):,.2f}")

# Trade log
print("\n" + "-" * 70)
print("RECENT TRADES:")
print("-" * 70)
print(f"{'DATE':<12} {'DIR':<6} {'ENTRY':>8} {'TRIGGER':>8} {'EXIT':>8} {'REASON':<8} {'P&L':>10}")
print("-" * 70)

for t in trade_log[-20:]:
    print(f"{str(t['date']):<12} {t['dir']:<6} {t['entry']:>8.2f} {t['trigger']:>8.2f} "
          f"{t['exit']:>8.2f} {t['reason']:<8} ${t['pnl']:>9.2f}")

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("Part 2b complete.")
print("=" * 70)
