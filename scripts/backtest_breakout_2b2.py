#!/usr/bin/env python3
"""
Part 2b-2: Simulate breakout trades

Run on Render shell:
python3 scripts/backtest_breakout_2b2.py
"""

import os
import psycopg2
from datetime import timedelta

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("PART 2b-2: SIMULATE TRADES")
print("=" * 40)

# Config
B, S, T, TR = 5, 8, 15, 5  # breakout, stop, target, trail
print(f"Config: B={B}, S={S}, T={T}, TR={TR}")

# Get price timeline
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity
    WHERE underlying_price > 0
    ORDER BY scan_time
""")
pt = [(r[0], float(r[1])) for r in cursor.fetchall()]

# Get entries
cursor.execute("""
    SELECT scan_time, underlying_price
    FROM heracles_scan_activity
    WHERE underlying_price > 0
      AND gamma_regime = 'NEGATIVE'
      AND EXTRACT(HOUR FROM scan_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 10
    ORDER BY scan_time
""")
entries = cursor.fetchall()

# Simulate
wins, losses, pnl = 0, 0, 0.0
seen = set()

for st, ep in entries:
    if st.date() in seen:
        continue
    seen.add(st.date())

    ep = float(ep)
    end = st + timedelta(minutes=120)
    fut = [(t, p) for t, p in pt if st < t <= end]
    if not fut:
        continue

    # Find trigger
    d, tp, ti = None, 0, 0
    for i, (t, p) in enumerate(fut):
        if p >= ep + B:
            d, tp, ti = "L", ep + B, i
            break
        elif p <= ep - B:
            d, tp, ti = "S", ep - B, i
            break

    if not d:
        continue

    # Manage position
    stop = tp - S if d == "L" else tp + S
    tgt = tp + T if d == "L" else tp - T
    tr_ref = tp
    ex, reason = 0, "T"

    for t, p in fut[ti+1:]:
        if d == "L":
            if p > tr_ref:
                tr_ref = p
                stop = max(stop, tr_ref - TR)
            if p >= tgt:
                ex, reason = tgt, "TGT"
                break
            if p <= stop:
                ex, reason = stop, "STP"
                break
        else:
            if p < tr_ref:
                tr_ref = p
                stop = min(stop, tr_ref + TR)
            if p <= tgt:
                ex, reason = tgt, "TGT"
                break
            if p >= stop:
                ex, reason = stop, "STP"
                break

    if reason == "T" and fut:
        ex = fut[-1][1]

    trade_pnl = ((ex - tp) if d == "L" else (tp - ex)) * 5
    pnl += trade_pnl
    if trade_pnl > 0:
        wins += 1
    else:
        losses += 1

# Results
total = wins + losses
print(f"\nRESULTS:")
print(f"  Trades: {total}")
if total > 0:
    print(f"  Wins: {wins} ({wins/total*100:.0f}%)")
    print(f"  Losses: {losses}")
    print(f"  Total P&L: ${pnl:,.2f}")
    print(f"  Avg: ${pnl/total:.2f}")

cursor.close()
conn.close()
print("\nPart 2b-2 done. Run 2b-3 to compare.")
