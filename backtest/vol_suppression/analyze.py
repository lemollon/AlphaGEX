"""VOL SUPPRESSION + CALL-DEMAND study — the gap the vvix_vix_analysis corpus never covered.

Every existing signal is an EXPANSION lens. This asks the opposite question:
what happens after vol gets CRUSHED without the spot move to justify it, and
after the tape starts paying up for upside?

Two signals, both index-only (CBOE + Yahoo) so they need no warehouse/ORATS:

  SUPPRESSION  vol falls far more than the spot move explains.
               resid = dlnVIX - beta_t * spy_ret, beta_t from a TRAILING window
               (never today's). Large negative resid = suppressed. 2026-07-30:
               VIX -17.3% on SPY +0.31%.

  CALL DEMAND  spot-up AND vol-up on the same day — dealers paying up for
               upside convexity. 2026-08-04: SPY +1.81%, VIX +4.0%.

Discipline carried over from the ts_flattening fix (2026-08-07):
  * every rate is reported WITH its base rate and lift — a bare rate is not evidence
  * signal days cluster, so report EPISODES, not just days
  * overlapping forward windows inflate naive t -> moving-block bootstrap
  * no look-ahead: features use data <= t, outcomes are strictly t+1..t+k
"""
import io, json
import numpy as np
import pandas as pd
import requests

CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
SPY_JSON = r"C:\Users\lemol\dev\AlphaGEX\backtest\vvix_vix_analysis\data\SPY_raw.json"
RNG = np.random.default_rng(7)


def cboe(sym, col):
    d = pd.read_csv(io.StringIO(requests.get(CBOE.format(sym=sym), timeout=30).text))
    d.columns = [c.strip().upper() for c in d.columns]
    k = d.columns[0]
    d[k] = pd.to_datetime(d[k])
    return d[[k, d.columns[-1]]].rename(columns={k: "date", d.columns[-1]: col}).set_index("date")[col]


j = json.load(open(SPY_JSON))
r = j["chart"]["result"][0]
spy = pd.Series(r["indicators"]["adjclose"][0]["adjclose"],
                index=pd.to_datetime(r["timestamp"], unit="s").normalize()).dropna()
spy = spy[~spy.index.duplicated(keep="last")]

df = pd.concat([cboe("VIX", "vix"), cboe("VVIX", "vvix"), cboe("VIX3M", "vix3m"),
                cboe("VIX9D", "vix9d"), spy.rename("spy")], axis=1)
df = df[df.index >= "2006-03-06"].copy()
df["spy"] = df.spy.ffill()
df = df.dropna(subset=["vix", "spy"])

# ---------------- features (t only) ----------------
df["ret"] = df.spy.pct_change()
df["dlnvix"] = np.log(df.vix).diff()
df["dlnvix9d"] = np.log(df.vix9d).diff()
df["dlnvix3m"] = np.log(df.vix3m).diff()

# rolling VIX-SPY beta from a TRAILING window, shifted so today is excluded
W = 252
cov = df.dlnvix.rolling(W).cov(df.ret)
var = df.ret.rolling(W).var()
df["beta"] = (cov / var).shift(1)
df["resid"] = df.dlnvix - df.beta * df.ret
df["resid_z"] = ((df.resid - df.resid.rolling(W).mean().shift(1))
                 / df.resid.rolling(W).std().shift(1))
# front-end led: 9D collapsing faster than 3M = curve re-steepening from the front
df["front_led"] = df.dlnvix9d - df.dlnvix3m

# ---------------- outcomes (strictly forward) ----------------
for k in (1, 3, 5, 10, 20):
    df[f"spy_fwd{k}"] = df.spy.shift(-k) / df.spy - 1.0
    df[f"vix_fwd{k}"] = df.vix.shift(-k) / df.vix - 1.0
# forward realized vol (annualized %) — does the calm actually hold?
df["rv5_fwd"] = df.ret.shift(-1).rolling(5).std().shift(-4) * np.sqrt(252) * 100
df["rv5_trail"] = df.ret.rolling(5).std() * np.sqrt(252) * 100
# worst next-5d drawdown — the short-premium tail
df["dd5"] = df.spy.shift(-1).rolling(5).min().shift(-4) / df.spy - 1.0

print(f"sample {df.index.min().date()} -> {df.index.max().date()}  n={len(df)}")
print(f"median VIX-SPY beta = {df.beta.median():.2f}\n")


def episodes(mask):
    m = mask.fillna(False)
    return int((m != m.shift()).cumsum()[m].nunique()) if m.sum() else 0


def boot_t(col, mask, block=21, iters=3000):
    d = df[[col]].copy()
    d["on"] = mask.fillna(False)
    d = d.dropna(subset=[col])
    v, on = d[col].values, d["on"].values.astype(bool)
    if on.sum() < 20:
        return float("nan")
    obs = v[on].mean() - v.mean()
    n = len(v); nb = int(np.ceil(n / block))
    pool = np.arange(0, n - block + 1)
    out = np.empty(iters)
    for i in range(iters):
        st = RNG.choice(pool, size=nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:n]
        bv, bo = v[idx], on[idx]
        out[i] = (bv[bo].mean() - bv.mean()) if bo.sum() >= 5 else np.nan
    se = np.nanstd(out)
    return obs / se if se else float("nan")


def report(mask, label, cols=("spy_fwd1", "spy_fwd5", "spy_fwd10", "spy_fwd20",
                              "vix_fwd5", "rv5_fwd", "dd5")):
    m = mask.fillna(False)
    n, ep = int(m.sum()), episodes(m)
    print(f"\n=== {label} ===")
    print(f"    fires {n} days / {ep} episodes ({100*n/len(df):.1f}% of sample)")
    if n < 30:
        print("    too few"); return
    print(f"    {'outcome':10} {'on':>9} {'base':>9} {'diff':>9} {'t_block':>8}")
    for c in cols:
        base = df[c].dropna(); on = df[c][m].dropna()
        if len(on) < 20:
            continue
        unit = "" if c == "rv5_fwd" else "%"
        sc = 1.0 if c == "rv5_fwd" else 100.0
        print(f"    {c:10} {on.mean()*sc:+8.2f}{unit} {base.mean()*sc:+8.2f}{unit} "
              f"{(on.mean()-base.mean())*sc:+8.2f}{unit} {boot_t(c, m):+8.2f}")


# ---------------- signal definitions ----------------
# SUPPRESSION: vol crushed well beyond what spot explains
SUPP = df.resid_z <= -1.5
SUPP_HARD = (df.resid_z <= -2.0) & (df.front_led < 0)      # + front-end led

# CALL DEMAND: spot up AND vol up the same day
CUD = (df.ret > 0) & (df.dlnvix > 0)
CUD_HARD = (df.ret > 0.005) & (df.dlnvix > 0.02)           # meaningful on both legs

print("#" * 78)
print("# A. VOL SUPPRESSION — what follows a day when vol is crushed w/o a spot move?")
print("#" * 78)
report(SUPP, "SUPPRESSION  resid_z <= -1.5")
report(SUPP_HARD, "SUPPRESSION HARD  resid_z <= -2.0 & front-end led")

print("\n" + "#" * 78)
print("# B. CALL DEMAND — spot-up AND vol-up (dealers paying up for upside)")
print("#" * 78)
report(CUD, "CALL DEMAND  SPY up & VIX up")
report(CUD_HARD, "CALL DEMAND HARD  SPY +>0.5% & VIX +>2%")

print("\n" + "#" * 78)
print("# C. THE COMBO — suppression, then call demand within 3 days (the Jul-30 shape)")
print("#" * 78)
COMBO = SUPP & (CUD.shift(-1).fillna(False) | CUD.shift(-2).fillna(False))
# NOTE: COMBO peeks forward by construction — it is DESCRIPTIVE only, never tradeable.
print(f"    (descriptive only — uses t+1/t+2, not tradeable) fires {int(COMBO.sum())}")

print("\n" + "#" * 78)
print("# D. PREMIUM-SELLER READ — is a suppression day a good day to SELL premium?")
print("#" * 78)
b = df.dropna(subset=["spy_fwd1"])
for lbl, sig in [("SUPPRESSION", SUPP), ("SUPP HARD", SUPP_HARD), ("CALL DEMAND", CUD)]:
    m = sig.reindex(b.index).fillna(False)
    print(f"\n  -- {lbl} --")
    for th in (0.010, 0.015):
        ev = b.spy_fwd1.abs() >= th
        print(f"     next-day |SPY|>={th*100:.1f}%   on={ev[m].mean()*100:5.1f}%  "
              f"base={ev.mean()*100:5.1f}%  lift={ev[m].mean()/ev.mean():.2f}x")

print("\n" + "#" * 78)
print("# E. THE 2026-07-30 EVENT — where did it sit?")
print("#" * 78)
for d in ["2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05"]:
    t = pd.Timestamp(d)
    if t not in df.index:
        continue
    r_ = df.loc[t]
    tags = []
    if SUPP.get(t, False): tags.append("SUPPRESSION")
    if SUPP_HARD.get(t, False): tags.append("HARD")
    if CUD.get(t, False): tags.append("CALL_DEMAND")
    print(f"  {d}  ret={r_.ret*100:+6.2f}%  dlnVIX={r_.dlnvix*100:+6.1f}%  "
          f"beta={r_.beta:+5.2f}  resid_z={r_.resid_z:+5.2f}  {' '.join(tags)}")
print(f"\n  resid_z percentile of 2026-07-30: "
      f"{(df.resid_z < df.resid_z.loc['2026-07-30']).mean()*100:.1f}th")
