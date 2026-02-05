#!/usr/bin/env python3
"""
Backtest Part 2a: Find Breakout Triggers

This script:
1. Builds price timeline from scan data
2. Gets entry points (9-11am CT, NEGATIVE gamma)
3. Finds which direction triggered for each entry
4. Outputs trigger data for Part 2b

Run on Render:
python scripts/backtest_breakout_part2a.py

Or paste the inline version below.
"""

# === INLINE VERSION FOR RENDER SHELL ===
# Copy everything below and paste into Render shell

import os
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("=" * 70)
print("PART 2a: FIND BREAKOUT TRIGGERS")
print("=" * 70)

# Config
BREAKOUT = 5  # pts to trigger

# Step 1: Build price timeline
print("\n[1] Building price timeline...")
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity
    WHERE underlying_price > 0
    ORDER BY scan_time
""")
price_timeline = [(s[0], float(s[1])) for s in cursor.fetchall() if s[1]]
print(f"    {len(price_timeline)} price points loaded")

# Step 2: Get entry points (9-11am CT, NEGATIVE gamma)
print("\n[2] Getting entry points...")
cursor.execute("""
    SELECT scan_time, underlying_price, gamma_regime
    FROM heracles_scan_activity
    WHERE underlying_price > 0
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') >= 9
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') < 11
    ORDER BY scan_time
""")
entries = cursor.fetchall()
print(f"    {len(entries)} entry points found")

# Step 3: Find breakout triggers
print("\n[3] Finding breakout triggers...")
print(f"    Breakout distance: {BREAKOUT} pts")

def get_future_prices(entry_time, dur=120):
    """Get prices from entry_time to entry_time + dur minutes"""
    end = entry_time + timedelta(minutes=dur)
    return [(t, p) for t, p in price_timeline if entry_time < t <= end]

# One entry per day
seen_dates = set()
triggers = []

for scan_time, price, regime in entries:
    if scan_time.date() in seen_dates:
        continue
    seen_dates.add(scan_time.date())

    price = float(price)
    future = get_future_prices(scan_time)

    if not future:
        print(f"    {scan_time.date()}: NO DATA after entry")
        continue

    # Find breakout trigger
    direction = None
    trigger_price = 0
    trigger_idx = 0

    for i, (t, p) in enumerate(future):
        if p >= price + BREAKOUT:
            direction = "LONG"
            trigger_price = price + BREAKOUT
            trigger_idx = i
            break
        elif p <= price - BREAKOUT:
            direction = "SHORT"
            trigger_price = price - BREAKOUT
            trigger_idx = i
            break

    if direction:
        # Calculate max move from trigger
        remaining = future[trigger_idx + 1:]
        if direction == "LONG":
            max_up = max((p for t, p in remaining), default=trigger_price) - trigger_price
            max_dn = trigger_price - min((p for t, p in remaining), default=trigger_price)
        else:
            max_up = max((p for t, p in remaining), default=trigger_price) - trigger_price
            max_dn = trigger_price - min((p for t, p in remaining), default=trigger_price)

        triggers.append({
            'date': scan_time.date(),
            'entry_time': scan_time,
            'entry_price': price,
            'direction': direction,
            'trigger_price': trigger_price,
            'remaining_pts': len(remaining),
            'max_up': max_up,
            'max_dn': max_dn,
        })
        print(f"    {scan_time.date()}: {direction} @ {trigger_price:.2f} (entry={price:.2f})")
    else:
        print(f"    {scan_time.date()}: NO TRIGGER (price={price:.2f})")

# Summary
print("\n" + "=" * 70)
print("TRIGGER SUMMARY")
print("=" * 70)

total = len(seen_dates)
triggered = len(triggers)
longs = sum(1 for t in triggers if t['direction'] == 'LONG')
shorts = sum(1 for t in triggers if t['direction'] == 'SHORT')

print(f"\nTotal entry days: {total}")
print(f"Triggered: {triggered} ({triggered/total*100:.0f}%)" if total > 0 else "No data")
print(f"  LONG: {longs}")
print(f"  SHORT: {shorts}")

# Show recent triggers for Part 2b
print("\n" + "-" * 70)
print("RECENT TRIGGERS (use in Part 2b):")
print("-" * 70)
print(f"{'DATE':<12} {'DIR':<6} {'ENTRY':>8} {'TRIGGER':>8} {'MAX_UP':>8} {'MAX_DN':>8}")
print("-" * 70)

for t in triggers[-15:]:  # Last 15
    print(f"{str(t['date']):<12} {t['direction']:<6} {t['entry_price']:>8.2f} "
          f"{t['trigger_price']:>8.2f} {t['max_up']:>8.1f} {t['max_dn']:>8.1f}")

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("Part 2a complete. Run Part 2b to calculate P&L.")
print("=" * 70)
