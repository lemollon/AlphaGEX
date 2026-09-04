"""Robustness on the two headline claims before anything gets called an edge.

  CLAIM S: suppression -> SPY drifts UP over 10-20d (t_block +3.4 at 10d)
           Is it one crisis era doing all the work?
  CLAIM C: call-demand -> forward REALIZED vol LOWER (t -6.1), tails 0.55x
           Or is that just a level effect — VIX-up days living in calm regimes?
"""
import io, json
import numpy as np, pandas as pd, requests

CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
RNG = np.random.default_rng(11)


def cboe(sym, col):
    d = pd.read_csv(io.StringIO(requests.get(CBOE.format(sym=sym), timeout=30).text))
    d.columns = [c.strip().upper() for c in d.columns]
    k = d.columns[0]; d[k] = pd.to_datetime(d[k])
    return d[[k, d.columns[-1]]].rename(columns={k: "date", d.columns[-1]: col}).set_index("date")[col]


j = json.load(open(r"C:\Users\lemol\dev\AlphaGEX\backtest\vvix_vix_analysis\data\SPY_raw.json"))
r = j["chart"]["result"][0]
spy = pd.Series(r["indicators"]["adjclose"][0]["adjclose"],
                index=pd.to_datetime(r["timestamp"], unit="s").normalize()).dropna()
spy = spy[~spy.index.duplicated(keep="last")]
df = pd.concat([cboe("VIX", "vix"), cboe("VIX3M", "vix3m"), cboe("VIX9D", "vix9d"),
                spy.rename("spy")], axis=1)
df = df[df.index >= "2006-03-06"].copy(); df["spy"] = df.spy.ffill()
df = df.dropna(subset=["vix", "spy"])

df["ret"] = df.spy.pct_change()
df["dlnvix"] = np.log(df.vix).diff()
df["front_led"] = np.log(df.vix9d).diff() - np.log(df.vix3m).diff()
W = 252
df["beta"] = (df.dlnvix.rolling(W).cov(df.ret) / df.ret.rolling(W).var()).shift(1)
df["resid"] = df.dlnvix - df.beta * df.ret
df["resid_z"] = (df.resid - df.resid.rolling(W).mean().shift(1)) / df.resid.rolling(W).std().shift(1)
df["rv5_trail"] = df.ret.rolling(5).std() * np.sqrt(252) * 100
df["vix_pct"] = df.vix.rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
for k in (5, 10, 20):
    df[f"spy_fwd{k}"] = df.spy.shift(-k) / df.spy - 1.0
df["rv5_fwd"] = df.ret.shift(-1).rolling(5).std().shift(-4) * np.sqrt(252) * 100

SUPP_HARD = (df.resid_z <= -2.0) & (df.front_led < 0)
CUD = (df.ret > 0) & (df.dlnvix > 0)


def boot_t(col, mask, sub=None, block=21, iters=3000):
    d = df[[col]].copy(); d["on"] = mask.fillna(False)
    if sub is not None:
        d = d[sub.reindex(d.index).fillna(False)]
    d = d.dropna(subset=[col])
    v, on = d[col].values, d["on"].values.astype(bool)
    if on.sum() < 15: return float("nan"), on.sum()
    obs = v[on].mean() - v.mean()
    n = len(v); nb = int(np.ceil(n / block)); pool = np.arange(0, max(1, n - block + 1))
    out = np.empty(iters)
    for i in range(iters):
        st = RNG.choice(pool, size=nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:n]
        bv, bo = v[idx], on[idx]
        out[i] = (bv[bo].mean() - bv.mean()) if bo.sum() >= 3 else np.nan
    se = np.nanstd(out)
    return (obs / se if se else float("nan")), int(on.sum())


print("#" * 74)
print("# CLAIM S — suppression -> forward SPY drift. Is one era doing the work?")
print("#" * 74)
ERAS = [("2006-2009 GFC", "2006-01-01", "2009-12-31"),
        ("2010-2019 calm", "2010-01-01", "2019-12-31"),
        ("2020-2021 COVID", "2020-01-01", "2021-12-31"),
        ("2022-2026 recent", "2022-01-01", "2026-12-31")]
print(f"{'era':18}{'n':>5}{'spy_fwd10 on':>14}{'base':>9}{'diff':>9}")
for lbl, a, b in ERAS:
    sub = (df.index >= a) & (df.index <= b)
    s = pd.Series(sub, index=df.index)
    d = df[s].dropna(subset=["spy_fwd10"])
    m = SUPP_HARD.reindex(d.index).fillna(False)
    if m.sum() < 5:
        print(f"{lbl:18}{int(m.sum()):>5}{'--':>14}"); continue
    print(f"{lbl:18}{int(m.sum()):>5}{d.spy_fwd10[m].mean()*100:+13.2f}%"
          f"{d.spy_fwd10.mean()*100:+8.2f}%{(d.spy_fwd10[m].mean()-d.spy_fwd10.mean())*100:+8.2f}%")

print("\n  ex-crisis check (drop 2008-2009 and 2020 entirely):")
nocrisis = ~(((df.index >= "2008-01-01") & (df.index <= "2009-12-31")) |
             ((df.index >= "2020-02-01") & (df.index <= "2020-12-31")))
for c in ("spy_fwd10", "spy_fwd20"):
    t, n = boot_t(c, SUPP_HARD, pd.Series(nocrisis, index=df.index))
    d = df[nocrisis].dropna(subset=[c]); m = SUPP_HARD.reindex(d.index).fillna(False)
    print(f"    {c}: on={d[c][m].mean()*100:+.2f}%  base={d[c].mean()*100:+.2f}%  "
          f"t_block={t:+.2f}  (n={n})")

print("\n" + "#" * 74)
print("# CLAIM C — call-demand -> lower forward RV. Level effect, or real?")
print("#" * 74)
print("  Unconditional:")
d = df.dropna(subset=["rv5_fwd"]); m = CUD.reindex(d.index).fillna(False)
t, n = boot_t("rv5_fwd", CUD)
print(f"    rv5_fwd on={d.rv5_fwd[m].mean():.2f} base={d.rv5_fwd.mean():.2f} t={t:+.2f} (n={n})")

print("\n  Within VIX-percentile buckets (controls for the vol LEVEL):")
print(f"    {'bucket':14}{'n':>5}{'on':>8}{'base':>8}{'diff':>8}")
for lo, hi, lbl in [(0.0, 0.33, "VIX low"), (0.33, 0.66, "VIX mid"), (0.66, 1.01, "VIX high")]:
    sub = (df.vix_pct >= lo) & (df.vix_pct < hi)
    d = df[sub.fillna(False)].dropna(subset=["rv5_fwd"])
    m = CUD.reindex(d.index).fillna(False)
    if m.sum() < 15: continue
    print(f"    {lbl:14}{int(m.sum()):>5}{d.rv5_fwd[m].mean():8.2f}{d.rv5_fwd.mean():8.2f}"
          f"{d.rv5_fwd[m].mean()-d.rv5_fwd.mean():+8.2f}")

print("\n  vs the honest control — ALL up-days (is it the UP day, or the vol-up?):")
UP = df.ret > 0
UP_VOLDN = (df.ret > 0) & (df.dlnvix <= 0)
d = df.dropna(subset=["rv5_fwd"])
for lbl, s in [("all up-days", UP), ("up & vol DOWN (normal)", UP_VOLDN), ("up & vol UP (CUD)", CUD)]:
    m = s.reindex(d.index).fillna(False)
    print(f"    {lbl:24} n={int(m.sum()):>5}  rv5_fwd={d.rv5_fwd[m].mean():6.2f}  "
          f"(base {d.rv5_fwd.mean():.2f})")

print("\n  next-day tail within buckets (|SPY|>=1.5%):")
b = df.dropna(subset=["spy_fwd5"]).copy()
b["f1"] = b.spy.shift(-1) / b.spy - 1.0
b = b.dropna(subset=["f1"])
for lbl, s in [("all up-days", UP), ("up & vol DOWN", UP_VOLDN), ("up & vol UP (CUD)", CUD)]:
    m = s.reindex(b.index).fillna(False)
    ev = b.f1.abs() >= 0.015
    print(f"    {lbl:24} on={ev[m].mean()*100:5.1f}%  base={ev.mean()*100:5.1f}%  "
          f"lift={ev[m].mean()/ev.mean():.2f}x")

print("\n" + "#" * 74)
print("# The 2026-07-30 numbers, stated correctly")
print("#" * 74)
for d_ in ["2026-07-29", "2026-07-30", "2026-08-04"]:
    t_ = pd.Timestamp(d_); r_ = df.loc[t_]
    exp = r_.beta * r_.ret
    print(f"  {d_}  SPY {r_.ret*100:+6.2f}%   dlnVIX actual {r_.dlnvix*100:+6.1f}%   "
          f"beta-explained {exp*100:+6.1f}%   unexplained {(r_.dlnvix-exp)*100:+6.1f}%  "
          f"resid_z {r_.resid_z:+.2f}")
