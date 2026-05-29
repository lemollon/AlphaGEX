"""
VIX + VVIX joint-signal study.

Question: does the VIX/VVIX relationship (divergence, ratio, exhaustion) plus the
VIX term structure predict forward volatility spikes (bearish) and vol exhaustion
(bullish)?  And would those signals have gated premium-selling entries (SPARK 1DTE
IC / FLARE 0DTE) away from their worst days?

Data (all free, in ./data):
  VIX/VVIX/VIX3M/VIX9D : CBOE daily history CSVs
  SPY                  : Yahoo daily chart JSON (adjusted close)

Pure measurement. No look-ahead: every signal uses only data up to and including
day t; every outcome is strictly forward (t+1..t+k).
"""

import json
import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")


# ----------------------------- load -----------------------------
def load_cboe(name, valcol):
    df = pd.read_csv(os.path.join(DATA, f"{name}.csv"))
    df.columns = [c.strip().upper() for c in df.columns]
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col])
    # close is last column for OHLC files, the single value col otherwise
    close = df.columns[-1]
    out = df[[date_col, close]].rename(columns={date_col: "date", close: valcol})
    return out.set_index("date")[valcol]


def load_spy():
    with open(os.path.join(DATA, "SPY_raw.json")) as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    adj = r["indicators"]["adjclose"][0]["adjclose"]
    s = pd.Series(adj, index=ts, name="spy").dropna()
    s = s[~s.index.duplicated(keep="last")]
    return s


vix = load_cboe("VIX", "vix")
vvix = load_cboe("VVIX", "vvix")
vix3m = load_cboe("VIX3M", "vix3m")
vix9d = load_cboe("VIX9D", "vix9d")
spy = load_spy()

df = pd.concat([vix, vvix, vix3m, vix9d, spy], axis=1)
df = df[df.index >= "2006-03-06"].copy()  # VVIX inception
df["spy"] = df["spy"].reindex(df.index).ffill()
df = df.dropna(subset=["vix", "vvix"])

print(f"Sample: {df.index.min().date()} -> {df.index.max().date()}  ({len(df)} trading days)")
print(f"VIX  mean {df.vix.mean():.1f}  range {df.vix.min():.1f}-{df.vix.max():.1f}")
print(f"VVIX mean {df.vvix.mean():.1f}  range {df.vvix.min():.1f}-{df.vvix.max():.1f}")
print(f"corr(VIX, VVIX) levels={df.vix.corr(df.vvix):.2f}  "
      f"daily-chg={df.vix.pct_change().corr(df.vvix.pct_change()):.2f}")


# ----------------------------- features (t only) -----------------------------
def z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

df["vix_z"] = z(df.vix)
df["vvix_z"] = z(df.vvix)
df["ratio"] = df.vvix / df.vix
df["ratio_pct"] = df.ratio.rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
df["vix_pct"] = df.vix.rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
# term structure
df["ts_3m"] = df.vix / df.vix3m            # >1 = backwardation (stress here)
df["ts_9d"] = df.vix9d / df.vix            # >1 = acute short-term stress
# local highs for exhaustion test
df["vix_hi10"] = df.vix >= df.vix.rolling(10).max()
df["vvix_hi10"] = df.vvix >= df.vvix.rolling(10).max()

# ----------------------------- forward outcomes -----------------------------
for k in (1, 3, 5, 10):
    df[f"vix_fwd{k}"] = df.vix.shift(-k) / df.vix - 1.0                 # VIX change
    df[f"vix_fwdmax{k}"] = df.vix.shift(-1).rolling(k).max().shift(-(k-1)) / df.vix - 1.0
    df[f"spy_fwd{k}"] = df.spy.shift(-k) / df.spy - 1.0                 # SPY return
ret = df.spy.pct_change()
df["spy_rv5_fwd"] = ret.shift(-5).rolling(5).std().shift(-4) * np.sqrt(252) * 100


def fwd_vix_spike(k, thresh):
    """indicator: VIX rises >= thresh at any point within next k days"""
    return df[f"vix_fwdmax{k}"] >= thresh


# ----------------------------- evaluation -----------------------------
def summarize(mask, label, outcomes):
    base = df.dropna(subset=outcomes)
    sel = base[mask.reindex(base.index).fillna(False)]
    n = len(sel)
    days_pct = 100 * n / len(base)
    print(f"\n=== {label}  (fires {n} days, {days_pct:.1f}% of sample) ===")
    if n < 30:
        print("  too few observations")
        return
    for oc in outcomes:
        s_on = sel[oc]
        s_all = base[oc]
        # t-stat of difference in means
        diff = s_on.mean() - s_all.mean()
        se = np.sqrt(s_on.var()/len(s_on) + s_all.var()/len(s_all))
        t = diff / se if se else 0
        print(f"  {oc:14}  on={s_on.mean()*100:+6.2f}%  base={s_all.mean()*100:+6.2f}%  "
              f"diff={diff*100:+6.2f}%  t={t:+5.1f}")


def hit_rate(mask, k, thresh, label):
    base = df.dropna(subset=[f"vix_fwdmax{k}"])
    spike = fwd_vix_spike(k, thresh).reindex(base.index).fillna(False)
    on = mask.reindex(base.index).fillna(False)
    p_spike_given_on = spike[on].mean()
    p_spike_base = spike.mean()
    lift = p_spike_given_on / p_spike_base if p_spike_base else float("nan")
    print(f"  {label:38} P(VIX +{int(thresh*100)}% in {k}d | signal)={p_spike_given_on*100:4.1f}%  "
          f"base={p_spike_base*100:4.1f}%  lift={lift:.2f}x")


# ---- Signal definitions (all use t-only data) ----
S_diverge   = (df.vvix_z > 1.0) & (df.vix_z < 0.0)                    # VVIX hot, VIX calm
S_ratio_hi  = (df.ratio_pct > 0.90) & (df.vix_pct < 0.50)            # convexity rich, VIX low
S_backward  = df.ts_3m > 1.0                                          # already stressed
S_ts_flat   = (df.ts_3m > 0.95) & (df.ts_3m.shift(20) < 0.90)        # contango->flat over a month
S_exhaust   = df.vix_hi10 & (~df.vvix_hi10) & (df.vix_pct > 0.80)    # VIX new high, VVIX won't confirm
S_complacent= (df.vvix < 85) & (df.vix < 14)                         # double floor

OUT_VIX = ["vix_fwd1", "vix_fwd3", "vix_fwd5", "vix_fwd10"]
OUT_SPY = ["spy_fwd1", "spy_fwd3", "spy_fwd5"]

print("\n" + "#"*78)
print("# A. FORWARD VIX CHANGE  (positive = vol rising = bearish for premium sellers)")
print("#"*78)
summarize(S_diverge,    "DIVERGENCE: VVIX z>1 & VIX z<0", OUT_VIX)
summarize(S_ratio_hi,   "RATIO RICH: VVIX/VIX pct>90 & VIX pct<50", OUT_VIX)
summarize(S_backward,   "BACKWARDATION: VIX>VIX3M", OUT_VIX)
summarize(S_ts_flat,    "TERM-STRUCTURE FLATTENING (20d)", OUT_VIX)
summarize(S_complacent, "DOUBLE FLOOR: VVIX<85 & VIX<14", OUT_VIX)

print("\n" + "#"*78)
print("# B. FORWARD SPY RETURN  (direction check)")
print("#"*78)
summarize(S_diverge,    "DIVERGENCE: VVIX z>1 & VIX z<0", OUT_SPY)
summarize(S_ratio_hi,   "RATIO RICH", OUT_SPY)
summarize(S_backward,   "BACKWARDATION", OUT_SPY)
summarize(S_exhaust,    "EXHAUSTION: VIX hi, VVIX won't confirm (bullish?)", OUT_SPY + ["vix_fwd5", "vix_fwd10"])

print("\n" + "#"*78)
print("# C. SPIKE HIT-RATE (does the signal raise the odds of a real vol spike?)")
print("#"*78)
for k, th in [(5, 0.20), (5, 0.30), (10, 0.30)]:
    print(f"\n-- horizon {k}d, threshold +{int(th*100)}% --")
    hit_rate(S_diverge,    k, th, "DIVERGENCE")
    hit_rate(S_ratio_hi,   k, th, "RATIO RICH")
    hit_rate(S_backward,   k, th, "BACKWARDATION")
    hit_rate(S_ts_flat,    k, th, "TS FLATTENING")
    hit_rate(S_complacent, k, th, "DOUBLE FLOOR")

print("\n" + "#"*78)
print("# D. PREMIUM-SELLER GATING  (next-day risk for SPARK 1DTE IC / FLARE 0DTE)")
print("#"*78)
# 'bad day' for a short-gamma IC seller = large next-day SPY move
for mv in (0.010, 0.015, 0.020):
    bad = (df.spy_fwd1.abs() >= mv)
    base = df.dropna(subset=["spy_fwd1"])
    bad = bad.reindex(base.index).fillna(False)
    print(f"\n-- next-day |SPY move| >= {mv*100:.1f}%  (base rate {bad.mean()*100:.1f}%) --")
    for sig, lbl in [(S_diverge, "DIVERGENCE"), (S_ratio_hi, "RATIO RICH"),
                     (S_backward, "BACKWARDATION"), (S_ts_flat, "TS FLATTENING")]:
        on = sig.reindex(base.index).fillna(False)
        if on.sum() < 30:
            print(f"  {lbl:16} too few"); continue
        p_bad_on = bad[on].mean()
        lift = p_bad_on / bad.mean()
        # downside skew on signal days
        dn = base.spy_fwd1[on].mean()
        print(f"  {lbl:16} P(bad|sig)={p_bad_on*100:4.1f}%  lift={lift:.2f}x  "
              f"mean next-day SPY={dn*100:+.2f}%  (fires {on.sum()}d)")

print("\n[done]")
