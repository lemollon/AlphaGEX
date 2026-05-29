"""ETH-PERP directional / trend-filter counterfactual.

Finding from data: ETH's LONG side has lost money every week since 4/27 while
SHORT works (regime flip). Question: would an ENTRY filter (suppress longs in a
downtrend) have helped, out-of-sample?

Honest method: use each entry's ACTUAL realized_pnl from the DB (real outcomes,
real exits) and just include/exclude entries per a filter rule. The trend at
entry time is computed from the recorded price series (trailing MA over K hours).
Filters are generic (not fit to the test set). Train (<5/9) vs test (>=5/9)
reported separately so we see in-sample vs out-of-sample.

Run: PYTHONIOENCODING=utf-8 python -m backtest.eth_directional_filter
"""
from __future__ import annotations
import bisect
from datetime import datetime, timezone
from database_adapter import get_connection

SPLIT = datetime(2026, 5, 9, tzinfo=timezone.utc)
TABLE = "agape_eth_perp"
PRICE_COL = "eth_price"


def load():
    c = get_connection()
    cur = c.cursor()
    cur.execute(f"""SELECT side, open_time, realized_pnl
                    FROM {TABLE}_positions
                    WHERE status IN ('closed','expired') AND realized_pnl IS NOT NULL
                      AND open_time IS NOT NULL AND open_time >= '2026-02-16'
                    ORDER BY open_time""")
    entries = [{"side": s, "open_time": _aware(ot), "pnl": float(p)} for s, ot, p in cur.fetchall()]
    cur.execute(f"""SELECT timestamp, {PRICE_COL} FROM {TABLE}_scan_activity
                    WHERE {PRICE_COL} IS NOT NULL AND {PRICE_COL} > 0 ORDER BY timestamp""")
    ts, px = [], []
    for t, p in cur.fetchall():
        ts.append(_aware(t).timestamp()); px.append(float(p))
    cur.close(); c.close()
    return entries, ts, px


def _aware(t):
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def trailing_ma(ts, px, at_ts, hours):
    """Mean price over [at_ts - hours, at_ts]."""
    lo = bisect.bisect_left(ts, at_ts - hours * 3600.0)
    hi = bisect.bisect_right(ts, at_ts)
    if hi <= lo:
        return None
    seg = px[lo:hi]
    return sum(seg) / len(seg)


def price_at(ts, px, at_ts):
    i = bisect.bisect_right(ts, at_ts) - 1
    return px[i] if i >= 0 else None


def summarize(rows):
    n = len(rows)
    if not n:
        return "n=0"
    wins = [r for r in rows if r["pnl"] > 0]
    tot = sum(r["pnl"] for r in rows)
    aw = sum(r["pnl"] for r in wins) / len(wins) if wins else 0.0
    losers = [r for r in rows if r["pnl"] <= 0]
    al = sum(r["pnl"] for r in losers) / len(losers) if losers else 0.0
    payoff = (aw / abs(al)) if al else 0.0
    return (f"n={n:>4}  WR={len(wins)/n*100:>5.1f}%  total=${tot:>9.2f}  "
            f"EV=${tot/n:>7.2f}  win=${aw:>7.2f} loss=${al:>7.2f} payoff={payoff:.2f}")


def main():
    entries, ts, px = load()
    train = [e for e in entries if e["open_time"] < SPLIT]
    test  = [e for e in entries if e["open_time"] >= SPLIT]
    print(f"ETH counter-trend (mean-reversion) robustness across MA lookbacks")
    print(f"train={len(train)} (<{SPLIT.date()})  test={len(test)} (>={SPLIT.date()})")
    print("COUNTER-TREND = long when price<MA (buy dip), short when price>MA (fade rally)\n")
    for K in [3, 6, 12, 24, 48]:
        for e in entries:
            ma = trailing_ma(ts, px, e["open_time"].timestamp(), K)
            p = price_at(ts, px, e["open_time"].timestamp())
            e["uptrend"] = (ma is not None and p is not None and p >= ma)
        ct = lambda e: (e["side"] == "long" and not e["uptrend"]) or (e["side"] == "short" and e["uptrend"])
        tr = lambda e: (e["side"] == "long" and e["uptrend"]) or (e["side"] == "short" and not e["uptrend"])
        print(f"  --- {K}h MA ---")
        print(f"    COUNTER-TREND  train {summarize([e for e in train if ct(e)])}")
        print(f"    COUNTER-TREND  TEST  {summarize([e for e in test  if ct(e)])}")
        print(f"    (momentum)     TEST  {summarize([e for e in test  if tr(e)])}")
    print("\nNOTE: uses ACTUAL realized_pnl per entry (real exits); filter only includes/excludes entries.")


if __name__ == "__main__":
    main()
