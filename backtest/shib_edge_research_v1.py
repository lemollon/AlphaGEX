"""
SHIB edge research — honest baseline strategy battery on the ~25-day minute-ish series.

Data: agape_shib_futures_scan_activity (timestamp, shib_price), ~51.5k rows,
2026-05-05 .. 2026-05-29, ~1 sample / 40s.

Costs: 0.1% slippage per side (round-trip 0.2%) + perpetual funding drag ~0.01%/8h.
We model funding as a per-bar drag proportional to holding time.

Research only. No live config touched.
"""
import math
import os
import sys
import statistics as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_adapter import get_connection

SLIP_PER_SIDE = 0.001          # 0.1% per side
ROUND_TRIP = 2 * SLIP_PER_SIDE  # 0.2%
FUNDING_PER_8H = 0.0001        # 0.01% / 8h
FUNDING_PER_SEC = FUNDING_PER_8H / (8 * 3600.0)

# ---------------------------------------------------------------------------
# Load price series ONCE
# ---------------------------------------------------------------------------
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT timestamp, shib_price
    FROM agape_shib_futures_scan_activity
    WHERE shib_price IS NOT NULL AND shib_price > 0
    ORDER BY timestamp ASC
""")
rows = cur.fetchall()
cur.close()
conn.close()

ts = [r[0] for r in rows]
px = [float(r[1]) for r in rows]
n = len(px)
t0, t1 = ts[0], ts[-1]
span_days = (t1 - t0).total_seconds() / 86400.0

# epoch seconds for holding-time / funding calcs
sec = [t.timestamp() for t in ts]
# median sampling interval
gaps = sorted(sec[i+1] - sec[i] for i in range(n - 1))
med_gap = gaps[len(gaps) // 2]

print("=" * 78)
print("SHIB EDGE RESEARCH  (research-only baseline battery)")
print("=" * 78)
print(f"rows={n}  span={span_days:.2f} days  {t0} .. {t1}")
print(f"price range {min(px):.7f} .. {max(px):.7f}  (raw SHIB, ~0.0059)")
print(f"median sample gap = {med_gap:.0f}s  (~{med_gap/60:.2f} min)")
print(f"gap p10/p50/p90 = {gaps[int(0.1*len(gaps))]:.0f}/{med_gap:.0f}/{gaps[int(0.9*len(gaps))]:.0f}s")

# ---------------------------------------------------------------------------
# Returns (log) at the native bar
# ---------------------------------------------------------------------------
ret = [math.log(px[i+1] / px[i]) for i in range(n - 1)]
mean_r = st.mean(ret)
std_r = st.pstdev(ret)

# annualization: bars per year
bars_per_year = (365.25 * 86400.0) / med_gap
ann_vol = std_r * math.sqrt(bars_per_year)

print("\n--- RETURN / VOL PROFILE (native bar) ---")
print(f"bar mean ret = {mean_r:.3e}   bar std = {std_r:.3e}")
print(f"annualized vol ~ {ann_vol*100:.1f}%   (bars/yr={bars_per_year:.0f})")
buyhold_gross = px[-1] / px[0] - 1
print(f"buy & hold gross over sample = {buyhold_gross*100:+.2f}%")

# ---------------------------------------------------------------------------
# Autocorrelation of returns at several lags (KEY DIAGNOSTIC)
# ---------------------------------------------------------------------------
def autocorr(x, lag):
    m = st.mean(x)
    num = sum((x[i] - m) * (x[i - lag] - m) for i in range(lag, len(x)))
    den = sum((v - m) ** 2 for v in x)
    return num / den if den else float("nan")

print("\n--- RETURN AUTOCORRELATION (native ~40s bars) ---")
print("lag  bars   ~time      autocorr")
for lag in (1, 2, 5, 10, 20, 50, 100):
    ac = autocorr(ret, lag)
    print(f"{lag:4d} {lag:5d}  ~{lag*med_gap/60:6.1f}m   {ac:+.4f}")

# ---------------------------------------------------------------------------
# Helper: resample to ~1-min grid by nearest-prior sample (for cleaner strat bars)
# We'll just operate on native bars but convert minute-lookbacks to bar counts.
# ---------------------------------------------------------------------------
def bars_for_minutes(mins):
    return max(1, round(mins * 60.0 / med_gap))

# ---------------------------------------------------------------------------
# Trade simulation core. A "trade" = enter at bar i (price px[i]), exit at bar j.
# direction +1 long / -1 short. Cost = round-trip slippage + funding over hold.
# Returns net fractional pnl on notional.
# ---------------------------------------------------------------------------
def trade_pnl(i, j, direction):
    gross = direction * (px[j] / px[i] - 1.0)
    hold_sec = sec[j] - sec[i]
    funding = FUNDING_PER_SEC * hold_sec  # always a drag on a held perp position
    net = gross - ROUND_TRIP - funding
    return net

def summarize(name, pnls, extra=""):
    if not pnls:
        print(f"{name:42s}  NO TRADES")
        return None
    nt = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / nt
    avg_w = st.mean(wins) if wins else 0.0
    avg_l = st.mean(losses) if losses else 0.0
    payoff = (avg_w / abs(avg_l)) if avg_l != 0 else float("inf")
    total = sum(pnls)  # additive approximation of compounded small returns
    mu = st.mean(pnls)
    sd = st.pstdev(pnls) if nt > 1 else 0.0
    sharpe = (mu / sd) if sd else 0.0  # per-trade Sharpe
    print(f"{name:42s} n={nt:5d} wr={wr*100:5.1f}% "
          f"aw={avg_w*100:+.3f}% al={avg_l*100:+.3f}% pay={payoff:4.2f} "
          f"tot={total*100:+7.2f}% shrp={sharpe:+.3f} {extra}")
    return dict(name=name, n=nt, wr=wr, avg_w=avg_w, avg_l=avg_l,
                payoff=payoff, total=total, sharpe=sharpe)

results = []

# ---------------------------------------------------------------------------
# 1. BUY & HOLD benchmark (single trade, full sample) long and short
# ---------------------------------------------------------------------------
print("\n--- 1. BUY & HOLD ---")
results.append(summarize("buyhold_long", [trade_pnl(0, n - 1, +1)]))
results.append(summarize("buyhold_short", [trade_pnl(0, n - 1, -1)]))

# ---------------------------------------------------------------------------
# 2. TIME-SERIES MOMENTUM
#    Enter in direction of return over lookback L, hold H, exit. Non-overlapping:
#    after exit, the next entry is the bar after exit. Step entries every H bars.
# ---------------------------------------------------------------------------
print("\n--- 2. TIME-SERIES MOMENTUM (L lookback, H hold) ---")
for Lmin in (15, 60, 240):
    for Hmin in (15, 60, 240):
        L = bars_for_minutes(Lmin)
        H = bars_for_minutes(Hmin)
        pnls = []
        i = L
        while i + H < n:
            mom = px[i] / px[i - L] - 1.0
            if mom > 0:
                d = +1
            elif mom < 0:
                d = -1
            else:
                i += H; continue
            pnls.append(trade_pnl(i, i + H, d))
            i += H  # non-overlapping
        results.append(summarize(f"momentum L={Lmin}m H={Hmin}m", pnls))

# ---------------------------------------------------------------------------
# 3. MEAN-REVERSION: fade moves > k std from rolling mean of price (z-score).
#    Enter against deviation, exit when z reverts toward 0 or after max hold.
# ---------------------------------------------------------------------------
print("\n--- 3. MEAN-REVERSION (window W, k std, fade) ---")
def rolling_mean_std(prices, W):
    # returns lists mean[i], std[i] using window ending at i (inclusive), for i>=W-1
    means = [None] * len(prices)
    stds = [None] * len(prices)
    s = 0.0; s2 = 0.0
    for i in range(len(prices)):
        s += prices[i]; s2 += prices[i] * prices[i]
        if i >= W:
            old = prices[i - W]
            s -= old; s2 -= old * old
        if i >= W - 1:
            m = s / W
            var = max(0.0, s2 / W - m * m)
            means[i] = m
            stds[i] = math.sqrt(var)
    return means, stds

for Wmin in (30, 120):
    for k in (1.5, 2.0, 2.5):
        W = bars_for_minutes(Wmin)
        max_hold = bars_for_minutes(Wmin)  # cap hold at the window length
        means, stds = rolling_mean_std(px, W)
        pnls = []
        i = W
        while i < n - 1:
            m = means[i]; s = stds[i]
            if m is None or s is None or s == 0:
                i += 1; continue
            z = (px[i] - m) / s
            d = 0
            if z >= k:
                d = -1  # price too high -> short
            elif z <= -k:
                d = +1  # price too low -> long
            if d == 0:
                i += 1; continue
            # exit when z crosses back through 0 or max_hold reached
            j = i + 1
            while j < n - 1 and (j - i) < max_hold:
                zj = (px[j] - means[j]) / stds[j] if (means[j] and stds[j]) else 0.0
                if (d == -1 and zj <= 0) or (d == +1 and zj >= 0):
                    break
                j += 1
            pnls.append(trade_pnl(i, j, d))
            i = j + 1  # non-overlapping
        results.append(summarize(f"meanrev W={Wmin}m k={k}", pnls))

# ---------------------------------------------------------------------------
# 4. BREAKOUT: trade breaks of rolling high/low channel (Donchian).
#    Long when price > prior W-bar high; short when < prior W-bar low. Hold H.
# ---------------------------------------------------------------------------
print("\n--- 4. BREAKOUT (Donchian channel W, hold H) ---")
def rolling_hi_lo(prices, W):
    # naive O(n*W) is too slow at 51k*big W; use deque-based sliding extrema
    from collections import deque
    his = [None] * len(prices); los = [None] * len(prices)
    dqmax = deque(); dqmin = deque()
    for i in range(len(prices)):
        while dqmax and prices[dqmax[-1]] <= prices[i]: dqmax.pop()
        dqmax.append(i)
        while dqmin and prices[dqmin[-1]] >= prices[i]: dqmin.pop()
        dqmin.append(i)
        while dqmax[0] <= i - W: dqmax.popleft()
        while dqmin[0] <= i - W: dqmin.popleft()
        if i >= W:
            # extrema over the PRIOR W bars (exclude current) -> recompute over window [i-W, i-1]
            his[i] = max(prices[i - W:i])
            los[i] = min(prices[i - W:i])
    return his, los

for Wmin in (60, 240):
    for Hmin in (30, 120):
        W = bars_for_minutes(Wmin)
        H = bars_for_minutes(Hmin)
        # prior-window extrema computed inline (slice) — W kept modest so OK
        pnls = []
        i = W
        while i + H < n:
            hi = max(px[i - W:i]); lo = min(px[i - W:i])
            d = 0
            if px[i] > hi:
                d = +1
            elif px[i] < lo:
                d = -1
            if d == 0:
                i += 1; continue
            pnls.append(trade_pnl(i, i + H, d))
            i += H
        results.append(summarize(f"breakout W={Wmin}m H={Hmin}m", pnls))

# ---------------------------------------------------------------------------
# 5. TIME-OF-DAY / DAY-OF-WEEK return pattern
# ---------------------------------------------------------------------------
print("\n--- 5. HOUR-OF-DAY & DAY-OF-WEEK mean bar return (UTC) ---")
hod = {h: [] for h in range(24)}
dow = {d: [] for d in range(7)}
for i in range(n - 1):
    h = ts[i].hour
    d = ts[i].weekday()
    hod[h].append(ret[i])
    dow[d].append(ret[i])
print("hour  n     mean_bar_ret   sum_ret%")
for h in range(24):
    v = hod[h]
    if v:
        print(f"{h:4d} {len(v):5d}   {st.mean(v):+.3e}   {sum(v)*100:+.3f}")
print("dow(0=Mon)  n     mean_bar_ret   sum_ret%")
for d in range(7):
    v = dow[d]
    if v:
        print(f"{d:9d} {len(v):6d}   {st.mean(v):+.3e}   {sum(v)*100:+.3f}")

# ---------------------------------------------------------------------------
# RANKED TABLE
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("RANKED BY AFTER-COST TOTAL RETURN")
print("=" * 78)
clean = [r for r in results if r]
clean.sort(key=lambda r: r["total"], reverse=True)
print(f"{'strategy':42s} {'n':>5s} {'wr':>6s} {'pay':>5s} {'total%':>8s} {'sharpe':>7s}")
for r in clean:
    print(f"{r['name']:42s} {r['n']:5d} {r['wr']*100:5.1f}% {r['payoff']:5.2f} "
          f"{r['total']*100:+8.2f} {r['sharpe']:+7.3f}")

print("\nDONE.")
