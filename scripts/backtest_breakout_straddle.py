#!/usr/bin/env python3
"""
Backtest: Breakout "Straddle" Strategy using MES Futures

Instead of options straddles, this strategy uses OCO (one-cancels-other)
breakout orders with MES futures:

1. At market open (9-11am CT) in NEGATIVE gamma:
   - Set BUY STOP at entry + breakout_distance
   - Set SELL STOP at entry - breakout_distance
2. Whichever triggers first = position direction
3. Cancel the other order
4. Ride momentum with trailing stop

Run on Render:
python scripts/backtest_breakout_straddle.py

Or copy the inline version below.
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Can be run standalone with inline SQL
def run_backtest_inline():
    """Run backtest - copy this to Render shell"""
    import psycopg2

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cursor = conn.cursor()

    print("=" * 70)
    print("BACKTEST: BREAKOUT 'STRADDLE' STRATEGY (MES FUTURES)")
    print("=" * 70)
    print("\nStrategy: OCO breakout orders during market open volatility")
    print("  - BUY STOP above entry, SELL STOP below entry")
    print("  - First trigger = position direction")
    print("  - No premium cost (unlike options straddles)")
    print()

    # Parameters to test
    CONFIGS = [
        # (breakout_dist, stop_loss, profit_target, trail_stop, description)
        (5, 8, 15, 5, "Conservative: 5pt break, 8pt stop, 15pt target"),
        (3, 5, 10, 3, "Tight: 3pt break, 5pt stop, 10pt target"),
        (7, 10, 20, 7, "Wide: 7pt break, 10pt stop, 20pt target"),
        (5, 6, 12, 4, "Balanced: 5pt break, 6pt stop, 12pt target"),
    ]

    # Get all scans with price data for building price timelines
    print("Building price timeline from scan data...")
    cursor.execute("""
        SELECT scan_time, underlying_price
        FROM heracles_scan_activity
        WHERE underlying_price > 0
        ORDER BY scan_time
    """)
    all_scans = cursor.fetchall()

    # Build timeline: list of (time, price)
    price_timeline = [(s[0], float(s[1])) for s in all_scans if s[1]]
    print(f"  {len(price_timeline)} price points loaded")

    if len(price_timeline) < 100:
        print("\nInsufficient data for backtest")
        cursor.close()
        conn.close()
        return

    # Get scan entry points during market open (9-11am CT = 14-16 UTC typically)
    # Filter for NEGATIVE gamma regime
    cursor.execute("""
        SELECT
            scan_time,
            underlying_price,
            gamma_regime,
            vix,
            atr
        FROM heracles_scan_activity
        WHERE underlying_price > 0
          AND gamma_regime = 'NEGATIVE'
          AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') >= 9
          AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') < 11
        ORDER BY scan_time
    """)
    entry_scans = cursor.fetchall()
    print(f"  {len(entry_scans)} potential entry points (9-11am CT, NEGATIVE gamma)")

    if len(entry_scans) == 0:
        print("\nNo entry points found in straddle window")
        cursor.close()
        conn.close()
        return

    # Helper: Get price range after entry
    def get_future_prices(entry_time, duration_minutes=120):
        """Get all prices from entry_time to entry_time + duration"""
        end_time = entry_time + timedelta(minutes=duration_minutes)
        return [(t, p) for t, p in price_timeline
                if entry_time < t <= end_time]

    # Helper: Simulate breakout trade
    def simulate_breakout_trade(entry_time, entry_price, breakout_dist, stop_loss,
                                 profit_target, trail_stop, max_duration=120):
        """
        Simulate a breakout straddle trade.

        Returns: (triggered, direction, pnl, exit_reason, max_move)
        """
        buy_trigger = entry_price + breakout_dist
        sell_trigger = entry_price - breakout_dist

        future_prices = get_future_prices(entry_time, max_duration)

        if not future_prices:
            return False, None, 0, "NO_DATA", 0

        # Phase 1: Wait for breakout trigger
        triggered = False
        direction = None
        trigger_price = 0
        trigger_idx = 0

        for i, (t, price) in enumerate(future_prices):
            if price >= buy_trigger:
                triggered = True
                direction = "LONG"
                trigger_price = buy_trigger  # Assume fill at stop price
                trigger_idx = i
                break
            elif price <= sell_trigger:
                triggered = True
                direction = "SHORT"
                trigger_price = sell_trigger
                trigger_idx = i
                break

        if not triggered:
            return False, None, 0, "NO_TRIGGER", 0

        # Phase 2: Manage position
        if direction == "LONG":
            stop_price = trigger_price - stop_loss
            target_price = trigger_price + profit_target
            trail_high = trigger_price
        else:  # SHORT
            stop_price = trigger_price + stop_loss
            target_price = trigger_price - profit_target
            trail_low = trigger_price

        # Track position through remaining prices
        max_favorable = 0
        exit_price = 0
        exit_reason = "TIME_STOP"

        for t, price in future_prices[trigger_idx + 1:]:
            if direction == "LONG":
                move = price - trigger_price
                max_favorable = max(max_favorable, move)

                # Update trailing stop
                if price > trail_high:
                    trail_high = price
                    # Move stop up (but not above entry)
                    new_stop = trail_high - trail_stop
                    if new_stop > stop_price:
                        stop_price = new_stop

                # Check exits
                if price >= target_price:
                    exit_price = target_price
                    exit_reason = "PROFIT_TARGET"
                    break
                elif price <= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS" if stop_price < trigger_price else "TRAIL_STOP"
                    break

            else:  # SHORT
                move = trigger_price - price
                max_favorable = max(max_favorable, move)

                # Update trailing stop
                if price < trail_low:
                    trail_low = price
                    new_stop = trail_low + trail_stop
                    if new_stop < stop_price:
                        stop_price = new_stop

                # Check exits
                if price <= target_price:
                    exit_price = target_price
                    exit_reason = "PROFIT_TARGET"
                    break
                elif price >= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS" if stop_price > trigger_price else "TRAIL_STOP"
                    break

        # If no exit triggered, use last price (time stop)
        if exit_reason == "TIME_STOP" and future_prices:
            exit_price = future_prices[-1][1]

        # Calculate P&L
        if direction == "LONG":
            pnl_pts = exit_price - trigger_price
        else:
            pnl_pts = trigger_price - exit_price

        pnl_dollars = pnl_pts * 5  # $5/pt for MES

        return True, direction, pnl_dollars, exit_reason, max_favorable

    # Compare with actual directional trades
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
    actual_row = cursor.fetchone()
    actual_pnl = float(actual_row[0]) if actual_row[0] else 0
    actual_trades = actual_row[1] or 0
    actual_wins = actual_row[2] or 0

    print(f"\nACTUAL DIRECTIONAL (9-11am NEGATIVE gamma):")
    print(f"  Trades: {actual_trades}")
    print(f"  Total P&L: ${actual_pnl:,.2f}")
    if actual_trades > 0:
        print(f"  Win Rate: {actual_wins/actual_trades*100:.1f}%")
        print(f"  Avg P&L: ${actual_pnl/actual_trades:.2f}")

    # Run backtest for each config
    for config in CONFIGS:
        breakout_dist, stop_loss, profit_target, trail_stop, description = config

        print(f"\n{'='*70}")
        print(f"CONFIG: {description}")
        print(f"{'='*70}")

        results = {
            'total_entries': 0,
            'triggered': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'by_direction': {'LONG': {'trades': 0, 'pnl': 0}, 'SHORT': {'trades': 0, 'pnl': 0}},
            'by_exit': defaultdict(lambda: {'trades': 0, 'pnl': 0}),
            'max_favorable_avg': 0,
        }

        # Only take one entry per day (first signal)
        seen_dates = set()
        max_favorable_sum = 0

        for scan in entry_scans:
            scan_time, entry_price, regime, vix, atr = scan

            # One entry per day
            scan_date = scan_time.date()
            if scan_date in seen_dates:
                continue
            seen_dates.add(scan_date)

            results['total_entries'] += 1

            triggered, direction, pnl, exit_reason, max_fav = simulate_breakout_trade(
                entry_time=scan_time,
                entry_price=float(entry_price),
                breakout_dist=breakout_dist,
                stop_loss=stop_loss,
                profit_target=profit_target,
                trail_stop=trail_stop
            )

            if not triggered:
                continue

            results['triggered'] += 1
            results['total_pnl'] += pnl
            max_favorable_sum += max_fav

            if pnl > 0:
                results['wins'] += 1
            else:
                results['losses'] += 1

            results['by_direction'][direction]['trades'] += 1
            results['by_direction'][direction]['pnl'] += pnl

            results['by_exit'][exit_reason]['trades'] += 1
            results['by_exit'][exit_reason]['pnl'] += pnl

        # Print results
        if results['triggered'] > 0:
            win_rate = results['wins'] / results['triggered'] * 100
            avg_pnl = results['total_pnl'] / results['triggered']
            avg_max_fav = max_favorable_sum / results['triggered']

            print(f"\nRESULTS:")
            print(f"  Entry opportunities: {results['total_entries']}")
            print(f"  Triggered: {results['triggered']} ({results['triggered']/results['total_entries']*100:.0f}%)")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Total P&L: ${results['total_pnl']:,.2f}")
            print(f"  Avg P&L/trade: ${avg_pnl:.2f}")
            print(f"  Avg Max Favorable: {avg_max_fav:.1f} pts")

            print(f"\nBY DIRECTION:")
            for dir in ['LONG', 'SHORT']:
                d = results['by_direction'][dir]
                if d['trades'] > 0:
                    print(f"  {dir}: {d['trades']} trades, ${d['pnl']:,.2f}")

            print(f"\nBY EXIT REASON:")
            for reason in ['PROFIT_TARGET', 'TRAIL_STOP', 'STOP_LOSS', 'TIME_STOP']:
                d = results['by_exit'][reason]
                if d['trades'] > 0:
                    pct = d['trades'] / results['triggered'] * 100
                    print(f"  {reason}: {d['trades']} ({pct:.0f}%), ${d['pnl']:,.2f}")

            # Compare to actual
            print(f"\nCOMPARISON TO ACTUAL DIRECTIONAL:")
            if actual_pnl != 0:
                diff = results['total_pnl'] - actual_pnl
                better = "BREAKOUT" if diff > 0 else "DIRECTIONAL"
                print(f"  Breakout: ${results['total_pnl']:,.2f}")
                print(f"  Directional: ${actual_pnl:,.2f}")
                print(f"  --> {better} better by ${abs(diff):,.2f}")
        else:
            print(f"\nNo trades triggered with this config")

    cursor.close()
    conn.close()
    print(f"\n{'='*70}")


# Inline version for Render shell (copy-paste)
INLINE_SCRIPT = '''
import os
import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("=" * 70)
print("BREAKOUT STRADDLE BACKTEST")
print("=" * 70)

# Build price timeline
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity WHERE underlying_price > 0 ORDER BY scan_time
""")
price_timeline = [(s[0], float(s[1])) for s in cursor.fetchall() if s[1]]
print(f"Price points: {len(price_timeline)}")

# Get entries (9-11am CT, NEGATIVE gamma)
cursor.execute("""
    SELECT scan_time, underlying_price, gamma_regime
    FROM heracles_scan_activity
    WHERE underlying_price > 0 AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
    ORDER BY scan_time
""")
entries = cursor.fetchall()
print(f"Entry points: {len(entries)}")

# Config: breakout=5pt, stop=8pt, target=15pt, trail=5pt
BREAKOUT, STOP, TARGET, TRAIL = 5, 8, 15, 5

def get_future_prices(entry_time, dur=120):
    end = entry_time + timedelta(minutes=dur)
    return [(t, p) for t, p in price_timeline if entry_time < t <= end]

results = {'trades': 0, 'wins': 0, 'pnl': 0.0}
seen_dates = set()

for scan_time, price, regime in entries:
    if scan_time.date() in seen_dates:
        continue
    seen_dates.add(scan_time.date())

    price = float(price)
    future = get_future_prices(scan_time)
    if not future:
        continue

    # Find breakout trigger
    direction = None
    trigger_price = 0
    for i, (t, p) in enumerate(future):
        if p >= price + BREAKOUT:
            direction, trigger_price = "LONG", price + BREAKOUT
            future = future[i+1:]
            break
        elif p <= price - BREAKOUT:
            direction, trigger_price = "SHORT", price - BREAKOUT
            future = future[i+1:]
            break

    if not direction:
        continue

    # Manage position
    if direction == "LONG":
        stop, target = trigger_price - STOP, trigger_price + TARGET
        trail_high = trigger_price
    else:
        stop, target = trigger_price + STOP, trigger_price - TARGET
        trail_low = trigger_price

    exit_price, exit_reason = 0, "TIME"
    for t, p in future:
        if direction == "LONG":
            if p > trail_high:
                trail_high = p
                stop = max(stop, trail_high - TRAIL)
            if p >= target:
                exit_price, exit_reason = target, "TARGET"
                break
            if p <= stop:
                exit_price, exit_reason = stop, "STOP"
                break
        else:
            if p < trail_low:
                trail_low = p
                stop = min(stop, trail_low + TRAIL)
            if p <= target:
                exit_price, exit_reason = target, "TARGET"
                break
            if p >= stop:
                exit_price, exit_reason = stop, "STOP"
                break

    if exit_reason == "TIME" and future:
        exit_price = future[-1][1]

    pnl = ((exit_price - trigger_price) if direction == "LONG" else (trigger_price - exit_price)) * 5
    results['trades'] += 1
    results['pnl'] += pnl
    if pnl > 0:
        results['wins'] += 1

# Results
print(f"\\nBREAKOUT RESULTS:")
print(f"  Trades: {results['trades']}")
if results['trades'] > 0:
    print(f"  Win Rate: {results['wins']/results['trades']*100:.1f}%")
    print(f"  Total P&L: ${results['pnl']:,.2f}")
    print(f"  Avg P&L: ${results['pnl']/results['trades']:.2f}")

# Compare to actual
cursor.execute("""
    SELECT SUM(realized_pnl) FROM heracles_scan_activity
    WHERE trade_executed AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
""")
actual = cursor.fetchone()[0] or 0
print(f"\\nACTUAL DIRECTIONAL: ${float(actual):,.2f}")
print(f"DIFFERENCE: ${results['pnl'] - float(actual):+,.2f}")

cursor.close()
conn.close()
'''

if __name__ == '__main__':
    try:
        from database_adapter import get_connection
        # Can run locally with database_adapter
        print("Running with database_adapter...")

        import psycopg2
        conn = get_connection()
        cursor = conn.cursor()

        # Execute the same logic
        exec(compile(INLINE_SCRIPT.replace("os.environ['DATABASE_URL']", ""), '<string>', 'exec'))

    except ImportError:
        print("Run this on Render shell:")
        print("-" * 40)
        print(INLINE_SCRIPT)
