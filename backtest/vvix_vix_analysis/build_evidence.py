# backtest/vvix_vix_analysis/build_evidence.py
"""Generate evidence.json: per-signal backtest hit-rates + timing distributions.
Reuses the loaders/feature logic from analyze.py. Pure historical stats; no look-ahead."""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")

def _load_cboe(name, col):
    df = pd.read_csv(os.path.join(DATA, f"{name}.csv"))
    df.columns = [c.strip().upper() for c in df.columns]
    d = df.columns[0]
    df[d] = pd.to_datetime(df[d])
    return df[[d, df.columns[-1]]].rename(columns={d: "date", df.columns[-1]: col}).set_index("date")[col]

def _load_spy():
    with open(os.path.join(DATA, "SPY_raw.json")) as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    s = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts, name="spy").dropna()
    return s[~s.index.duplicated(keep="last")]

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

def build():
    vix = _load_cboe("VIX", "vix"); vvix = _load_cboe("VVIX", "vvix")
    vix3m = _load_cboe("VIX3M", "vix3m"); vix9d = _load_cboe("VIX9D", "vix9d")
    spy = _load_spy()
    df = pd.concat([vix, vvix, vix3m, vix9d, spy], axis=1)
    df = df[df.index >= "2006-03-06"].copy()
    df["spy"] = df["spy"].ffill()
    df = df.dropna(subset=["vix", "vvix"])

    df["vix_z"] = _z(df.vix); df["vvix_z"] = _z(df.vvix)
    df["ts_3m"] = df.vix / df.vix3m
    df["vix_pct"] = df.vix.rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    df["vix_hi10"] = df.vix >= df.vix.rolling(10).max()
    df["vvix_hi10"] = df.vvix >= df.vvix.rolling(10).max()
    for k in (1, 3, 5, 10):
        df[f"vix_fwd{k}"] = df.vix.shift(-k) / df.vix - 1.0
        df[f"vix_fwdmax{k}"] = df.vix.shift(-1).rolling(k).max().shift(-(k-1)) / df.vix - 1.0
        df[f"spy_fwd{k}"] = df.spy.shift(-k) / df.spy - 1.0

    signals = {
        "backwardation": df.ts_3m > 1.0,
        "ts_flattening": (df.ts_3m > 0.95) & (df.ts_3m.shift(20) < 0.90),
        "exhaustion": df.vix_hi10 & (~df.vvix_hi10) & (df.vix_pct > 0.80),
        "double_floor": (df.vvix < 85) & (df.vix < 14),
        "divergence": (df.vvix_z > 1.0) & (df.vix_z < 0.0),
    }
    # canonical "correct" call per signal
    correct = {
        "backwardation": df.spy_fwd5 > 0,
        "ts_flattening": df.vix_fwdmax5 >= 0.20,
        "exhaustion": df.spy_fwd3 > 0,
        "double_floor": df.vix_fwd10 > 0,
        "divergence": df.vix_fwdmax5 >= 0.20,
    }
    # timing: trading-days until the signal's event (capped at 21)
    def days_to_event(mask, kind):
        out = []
        idx = df.index
        for i in np.where(mask.fillna(False).values)[0]:
            base_vix = df.vix.values[i]; base_spy = df.spy.values[i]
            landed = None
            for k in range(1, 22):
                if i + k >= len(df): break
                v = df.vix.values[i+k]; p = df.spy.values[i+k]
                if kind == "vol_down" and v <= base_vix * 0.90: landed = k; break
                if kind == "spy_up" and p >= base_spy * 1.005: landed = k; break
                if kind == "vix_spike" and v >= base_vix * 1.20: landed = k; break
                if kind == "vix_up" and v > base_vix: landed = k; break
            out.append(landed)
        return [x for x in out if x is not None], len(out)
    kind = {"backwardation": "spy_up", "ts_flattening": "vix_spike",
            "exhaustion": "vol_down", "double_floor": "vix_up", "divergence": "vix_spike"}

    base_spy5_up = (df.spy_fwd5 > 0).mean()
    out = {"as_of": str(df.index.max().date()),
           "sample_start": str(df.index.min().date()),
           "n_days": int(len(df)), "signals": {}}
    for key, mask in signals.items():
        m = mask.fillna(False)
        n = int(m.sum())
        sel = df[m]
        landed_days, total = days_to_event(mask, kind[key])
        arr = np.array(landed_days) if landed_days else np.array([21])
        cdf = [float((arr <= k).mean()) for k in range(1, 22)]
        p75 = int(np.percentile(arr, 75))
        suggested_dte = int(np.ceil(p75 * 7 / 5 * 1.3) + 2)  # trading->calendar, +30% buffer, +2d
        def tstat(col):
            s_on = sel[col].dropna(); s_all = df[col].dropna()
            if len(s_on) < 5: return 0.0
            se = np.sqrt(s_on.var()/len(s_on) + s_all.var()/len(s_all))
            return float((s_on.mean() - s_all.mean())/se) if se else 0.0
        out["signals"][key] = {
            "n": n,
            "hit_rate": float(correct[key][m].mean()) if n else 0.0,
            "fwd_vix_1": float(sel.vix_fwd1.mean()), "fwd_vix_3": float(sel.vix_fwd3.mean()),
            "fwd_vix_5": float(sel.vix_fwd5.mean()), "fwd_vix_10": float(sel.vix_fwd10.mean()),
            "fwd_spy_3": float(sel.spy_fwd3.mean()), "fwd_spy_5": float(sel.spy_fwd5.mean()),
            "t_fwd_spy_5": tstat("spy_fwd5"), "t_fwd_vix_5": tstat("vix_fwd5"),
            "timing_median": int(np.median(arr)), "timing_p25": int(np.percentile(arr, 25)),
            "timing_p75": p75, "timing_cdf": cdf, "suggested_dte": suggested_dte,
            "event_landed_rate": float(len(landed_days)/total) if total else 0.0,
        }
    with open(os.path.join(HERE, "evidence.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out

if __name__ == "__main__":
    build()
    print("evidence.json written")
