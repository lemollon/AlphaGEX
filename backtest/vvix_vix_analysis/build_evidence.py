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


def _load_spy_open():
    """SPY OPEN on the ADJUSTED scale.

    The signal is computed FROM a session's close, so the earliest you can act is
    the next open. Scoring from the close silently credits you with the overnight
    gap, which for ts_flattening averages +0.24% (t 2.03) against a +0.033% base
    — 7x normal, and entirely uncapturable.

    `open` is raw while `adjclose` is dividend/split adjusted, so the open must be
    put on the adjusted scale (factor = adjclose/close) before any ratio is taken.
    Mixing the two scales produces impossible numbers (a -13% mean intraday move
    and a 1.4% "SPY up" base rate, observed 2026-08-12).
    """
    with open(os.path.join(DATA, "SPY_raw.json")) as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    q = r["indicators"]["quote"][0]
    adj = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts)
    close = pd.Series(q["close"], index=ts)
    opn = pd.Series(q["open"], index=ts)
    s = (opn * (adj / close)).rename("spy_open").dropna()
    return s[~s.index.duplicated(keep="last")]


# Quiet sessions required before a re-fire counts as a NEW event. These signals
# persist for days; a run broken by one quiet session is the same episode, not
# two. 5 was chosen to match the ~4.6-session mean run length.
EPISODE_GAP = 5

# Horizon decay profile. A signal with no horizon attached gets used at the wrong
# timescale: ts_flattening is worth nothing intraday (t 0.10), peaks at 3 sessions
# and is dead by 10, while backwardation is a 1-day TAIL signal that turns
# bullish only over 20-60 sessions.
HORIZON_DAYS = [1, 2, 3, 5, 10, 20, 60]
BIG_MOVE = 0.015


def episode_starts(mask):
    """Index positions of the FIRST firing day of each independent episode.

    🚨 This is the estimator that matters. Averaging over every firing day counts
    the LATER days of an episode — days conditioned on the episode having already
    run, when the market is typically bouncing. For ts_flattening that inverts the
    sign of the 5d SPY mean: +0.36% over 355 days vs -0.44% over 77 episodes.
    """
    idx = np.flatnonzero(np.asarray(mask.fillna(False).values, dtype=bool))
    if idx.size == 0:
        return idx
    starts = [idx[0]]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > EPISODE_GAP:
            starts.append(b)
    return np.array(starts)


def _t(series):
    s = pd.Series(series).dropna()
    if len(s) < 5 or s.std(ddof=1) == 0:
        return 0.0
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

def build():
    vix = _load_cboe("VIX", "vix"); vvix = _load_cboe("VVIX", "vvix")
    vix3m = _load_cboe("VIX3M", "vix3m"); vix9d = _load_cboe("VIX9D", "vix9d")
    spy = _load_spy(); spy_open = _load_spy_open()
    df = pd.concat([vix, vvix, vix3m, vix9d, spy, spy_open], axis=1)
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

    # TRADEABLE returns: entry at the NEXT session's open (the signal is built
    # from this session's close, so that open is the first reachable price).
    df["spy_entry"] = df.spy_open.shift(-1)
    df["spy_gap"] = df.spy_entry / df.spy - 1.0          # the uncapturable piece
    df["spy_op_intraday"] = df.spy.shift(-1) / df.spy_entry - 1.0
    for k in HORIZON_DAYS:
        df[f"spy_op{k}"] = df.spy.shift(-k) / df.spy_entry - 1.0

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

    # Next-day tail events — the SIZING claim (a fat tail is not a direction).
    # Reported per-signal as a lift vs base so a bare rate can't read as skill.
    tail_abs = df.spy_fwd1.abs() >= 0.015
    tail_dn = df.spy_fwd1 <= -0.015

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
        # A hit_rate is meaningless without the rate you'd get for free. Ship both
        # plus the lift, so a 19% "hit rate" against a 16% base can never again be
        # read as skill (that misread put "buy puts" on ts_flattening in prod).
        hr = float(correct[key][m].mean()) if n else 0.0
        hr_base = float(correct[key].mean())
        # episodes = consecutive firing runs. Signal days cluster hard, so `n`
        # days badly overstates the independent sample size.
        episodes = int((m != m.shift()).cumsum()[m].nunique()) if n else 0
        out["signals"][key] = {
            "n": n,
            "n_episodes": episodes,
            "hit_rate": hr,
            "hit_rate_base": hr_base,
            "hit_rate_lift": float(hr / hr_base) if hr_base else 0.0,
            "tail_lift_abs_15": float(tail_abs[m].mean() / tail_abs.mean()) if n and tail_abs.mean() else 0.0,
            "tail_lift_down_15": float(tail_dn[m].mean() / tail_dn.mean()) if n and tail_dn.mean() else 0.0,
            "fwd_vix_1": float(sel.vix_fwd1.mean()), "fwd_vix_3": float(sel.vix_fwd3.mean()),
            "fwd_vix_5": float(sel.vix_fwd5.mean()), "fwd_vix_10": float(sel.vix_fwd10.mean()),
            "fwd_spy_3": float(sel.spy_fwd3.mean()), "fwd_spy_5": float(sel.spy_fwd5.mean()),
            "t_fwd_spy_5": tstat("spy_fwd5"), "t_fwd_vix_5": tstat("vix_fwd5"),
            "timing_median": int(np.median(arr)), "timing_p25": int(np.percentile(arr, 25)),
            "timing_p75": p75, "timing_cdf": cdf, "suggested_dte": suggested_dte,
            "event_landed_rate": float(len(landed_days)/total) if total else 0.0,
        }

        # ---------------- corrected, episode-based, tradeable-entry ------------
        # Everything above this line is kept only for backward compatibility with
        # consumers already reading those keys. These are the estimates to trust.
        ep = episode_starts(m)
        esel = df.iloc[ep] if len(ep) else df.iloc[[]]
        rec = out["signals"][key]
        rec["n_episodes_gap5"] = int(len(ep))
        rec["episode_gap"] = EPISODE_GAP
        rec["gap_overnight_mean"] = float(esel.spy_gap.mean()) if len(ep) else 0.0
        rec["gap_overnight_t"] = _t(esel.spy_gap) if len(ep) else 0.0

        horizons = {}
        cols = [("intraday", "spy_op_intraday")] + [(f"{k}d", f"spy_op{k}") for k in HORIZON_DAYS]
        for label, col in cols:
            s_on = esel[col].dropna() if len(ep) else pd.Series(dtype=float)
            s_all = df[col].dropna()
            if len(s_on) < 10 or s_all.empty:
                continue
            base_up = float((s_all > 0).mean())
            up = float((s_on > 0).mean())
            big = float((s_on.abs() >= BIG_MOVE).mean())
            big_base = float((s_all.abs() >= BIG_MOVE).mean())
            # 🚨 t must be on the EXCESS over the unconditional mean, not on the
            # raw mean. SPY drifts up over long horizons no matter what fired, so
            # a raw-mean t picks 60d for every signal (+3.65%, t 4.81) when its
            # up_lift is 1.07 — that is beta, not edge. Same failure mode as a
            # hit rate quoted without its base rate.
            se = np.sqrt(s_on.var(ddof=1) / len(s_on) + s_all.var(ddof=1) / len(s_all))
            excess = float(s_on.mean() - s_all.mean())
            t_excess = float(excess / se) if se else 0.0
            horizons[label] = {
                "mean": float(s_on.mean()), "mean_base": float(s_all.mean()),
                "excess": excess, "t": t_excess, "t_raw": _t(s_on),
                "n": int(len(s_on)),
                "up_rate": up, "up_base": base_up,
                "up_lift": float(up / base_up) if base_up else 0.0,
                "tail_rate": big, "tail_base": big_base,
                "tail_lift": float(big / big_base) if big_base else 0.0,
            }
        rec["horizons"] = horizons
        # The horizon with the largest EXCESS t — what the alert should quote.
        if horizons:
            best = max(horizons.items(), key=lambda kv: abs(kv[1]["t"]))
            rec["best_horizon"] = best[0]
            rec["best_horizon_t"] = best[1]["t"]
            rec["best_horizon_mean"] = best[1]["mean"]
            rec["best_horizon_excess"] = best[1]["excess"]
            rec["directional"] = bool(abs(best[1]["t"]) >= 2.0)
        else:
            rec["best_horizon"] = None
            rec["best_horizon_t"] = 0.0
            rec["best_horizon_mean"] = 0.0
            rec["directional"] = False

        # Decay watch: is the edge still there in the most recent third? A signal
        # that worked 2009-2019 and stopped should be flagged, not silently kept.
        stab = {}
        if len(ep) >= 15 and rec["best_horizon"]:
            bcol = ("spy_op_intraday" if rec["best_horizon"] == "intraday"
                    else f"spy_op{rec['best_horizon'][:-1]}")
            # Excess-based, to match how best_horizon is chosen. At 1-3 sessions
            # the unconditional drift is tiny so this barely moves the number, but
            # a stability check that disagrees with the selection criterion is
            # just a second chance to fool yourself.
            for lo, hi in ((2009, 2015), (2016, 2020), (2021, 2030)):
                w = esel[(esel.index.year >= lo) & (esel.index.year <= hi)][bcol].dropna()
                if len(w) < 5:
                    continue
                allw = df[(df.index.year >= lo) & (df.index.year <= hi)][bcol].dropna()
                se = np.sqrt(w.var(ddof=1) / len(w) + allw.var(ddof=1) / len(allw)) \
                    if len(allw) > 1 else 0.0
                ex = float(w.mean() - allw.mean()) if len(allw) else float(w.mean())
                stab[f"{lo}_{hi}"] = {"n": int(len(w)), "mean": float(w.mean()),
                                      "excess": ex,
                                      "t": float(ex / se) if se else 0.0}
        rec["stability"] = stab
    with open(os.path.join(HERE, "evidence.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out

if __name__ == "__main__":
    build()
    print("evidence.json written")
