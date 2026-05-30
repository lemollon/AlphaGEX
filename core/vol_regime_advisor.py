# core/vol_regime_advisor.py
"""Volatility regime advisor — signal engine, recommendation, timing.

Pure functions operate on an injected history DataFrame (columns: vix, vvix,
vix3m, vix9d) whose LAST row is "today". Live wrapper fetches CBOE data.
Backtest evidence (hit-rates + timing) is loaded from evidence.json.
"""
import json, math, os
from typing import Dict, Optional
import numpy as np
import pandas as pd
import requests


def _num(x) -> float:
    """NaN/None-safe float coercion. `nan or 0` returns nan (NaN is truthy),
    so an explicit guard is required to keep values JSON-serializable."""
    if x is None:
        return 0.0
    try:
        f = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f

CBOE_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
CBOE_QUOTE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{sym}.json"
EVIDENCE_PATH = os.path.join(os.path.dirname(__file__), "..", "backtest",
                             "vvix_vix_analysis", "evidence.json")

SIGNAL_CONFIDENCE = {
    "backwardation": "high", "ts_flattening": "medium", "exhaustion": "medium",
    "double_floor": "low", "divergence": "low",
}
SIGNAL_BLURB = {
    "backwardation": "VIX above VIX3M — stress is here. Vol historically mean-reverts down and SPY tends to recover; fade the spike.",
    "ts_flattening": "Term structure flattening from contango — an early warning that a vol spike may be building.",
    "exhaustion": "VIX made a new high but VVIX won't confirm — vol tends to fade and SPY bounces.",
    "double_floor": "VIX and VVIX both at the floor — complacent; vol drifts up slowly. Owning optionality is cheap.",
    "divergence": "VVIX elevated while VIX calm. NOTE: 20-yr study shows this is statistically noise — low confidence.",
}

# What each signal implies for the equity stance.
SIGNAL_DIRECTION = {
    "backwardation": "bullish", "exhaustion": "bullish",
    "ts_flattening": "bearish", "double_floor": "neutral", "divergence": "bearish",
}
# Plain-English firing condition, shown next to a "how close" gauge.
SIGNAL_TRIGGER = {
    "backwardation": "Fires when VIX > VIX3M (ratio > 1.00)",
    "ts_flattening": "Fires when VIX/VIX3M > 0.95 and was < 0.90 about 20 days ago",
    "exhaustion": "Fires when VIX hits a 10-day high, VVIX does NOT confirm, and VIX is in its top quintile",
    "double_floor": "Fires when VVIX < 85 and VIX < 14",
    "divergence": "Fires when VVIX z-score > 1 while VIX z-score < 0 (low confidence)",
}

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def compute_signals(history: pd.DataFrame) -> Dict[str, dict]:
    """history: DataFrame indexed by date with columns vix,vvix,vix3m,vix9d; last row = today."""
    df = history.copy()
    df["vix_z"] = _z(df["vix"]); df["vvix_z"] = _z(df["vvix"])
    df["ts_3m"] = df["vix"] / df["vix3m"]
    df["vix_pct"] = df["vix"].rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    df["vix_hi10"] = df["vix"] >= df["vix"].rolling(10).max()
    df["vvix_hi10"] = df["vvix"] >= df["vvix"].rolling(10).max()
    r = df.iloc[-1]
    ts20 = df["ts_3m"].iloc[-21] if len(df) > 21 else float("nan")

    # NOTE: comparisons intentionally rely on NaN-compares-False so that an
    # undefined (under-filled-window) signal stays OFF. Do NOT wrap these in
    # _num — that would coerce NaN->0 and flip e.g. ts_flattening ON.
    raw = {
        "backwardation": bool(r["ts_3m"] > 1.0),
        "ts_flattening": bool(r["ts_3m"] > 0.95 and ts20 < 0.90),
        "exhaustion": bool(r["vix_hi10"] and not r["vvix_hi10"] and (r["vix_pct"] or 0) > 0.80),
        "double_floor": bool(r["vvix"] < 85 and r["vix"] < 14),
        "divergence": bool((r["vvix_z"] or 0) > 1.0 and (r["vix_z"] or 0) < 0.0),
    }
    # values ARE serialized over JSON (Task 5) — must be NaN-free, hence _num.
    values = {
        "backwardation": _num(r["ts_3m"]), "ts_flattening": _num(r["ts_3m"]),
        "exhaustion": _num(r["vix_pct"]), "double_floor": _num(r["vvix"]),
        "divergence": _num(r["vvix_z"]),
    }
    # Live readings used for the per-signal "current vs trigger" gauge.
    ts3m = _num(r["ts_3m"]); vixv = _num(r["vix"]); vvixv = _num(r["vvix"])
    vixpct = _num(r["vix_pct"]); vvixz = _num(r["vvix_z"]); vixz = _num(r["vix_z"])
    # proximity in [0,1]: progress of the binding metric toward its trigger (1 = firing).
    proximity = {
        "backwardation": _clamp01(ts3m / 1.0),
        "ts_flattening": _clamp01(ts3m / 0.95),
        "exhaustion": _clamp01(vixpct / 0.80),
        # double_floor fires as VIX→14 and VVIX→85 from above; closer = higher.
        "double_floor": _clamp01(min((28.0 - vixv) / 14.0, (115.0 - vvixv) / 30.0)) if vixv and vvixv else 0.0,
        "divergence": _clamp01(vvixz / 1.0) if vvixz > 0 else 0.0,
    }
    current_text = {
        "backwardation": f"VIX/VIX3M = {ts3m:.2f}",
        "ts_flattening": f"VIX/VIX3M = {ts3m:.2f}",
        "exhaustion": f"VIX percentile {vixpct * 100:.0f}%, VVIX {'confirming' if bool(r['vvix_hi10']) else 'not confirming'}",
        "double_floor": f"VVIX {vvixv:.0f}, VIX {vixv:.1f}",
        "divergence": f"VVIX z {vvixz:+.2f}, VIX z {vixz:+.2f}",
    }
    return {
        key: {"active": raw[key], "value": round(values[key], 4),
              "confidence": SIGNAL_CONFIDENCE[key], "blurb": SIGNAL_BLURB[key],
              "direction": SIGNAL_DIRECTION[key], "trigger_text": SIGNAL_TRIGGER[key],
              "current_text": current_text[key], "proximity": round(proximity[key], 3)}
        for key in raw
    }


def build_recommendation(signals: Dict[str, dict]) -> dict:
    """Deterministic precedence -> stance + conviction + rationale."""
    def on(k): return signals[k]["active"]
    if on("backwardation"):
        return {"stance": "buy_the_bounce", "conviction": "high",
                "rationale": "Backwardation: spike is present but historically fades (VIX -8%/5d) "
                             "and SPY recovers (+0.9%/5d). Stress is real — size carefully."}
    if on("exhaustion"):
        return {"stance": "buy_the_bounce", "conviction": "medium",
                "rationale": "Exhaustion: VIX high but VVIX won't confirm — vol fades, SPY bounces."}
    if on("ts_flattening"):
        return {"stance": "lean_puts", "conviction": "medium",
                "rationale": "Term structure flattening — rising-vol warning; favor downside/puts."}
    if on("double_floor"):
        return {"stance": "neutral", "conviction": "low",
                "rationale": "Floor/complacent — vol is cheap and drifts up slowly; favor owning optionality."}
    return {"stance": "neutral", "conviction": "low",
            "rationale": "No high-confidence signal active."}

def _regime_label(signals: Dict[str, dict]) -> str:
    if signals["backwardation"]["active"]: return "backwardation_stressed"
    if signals["exhaustion"]["active"]: return "exhaustion"
    if signals["double_floor"]["active"]: return "floor_complacent"
    if signals["ts_flattening"]["active"]: return "contango_flattening"
    return "contango_calm"

def _primary_signal(signals: Dict[str, dict]) -> Optional[str]:
    for k in ("backwardation", "exhaustion", "ts_flattening", "double_floor"):
        if signals[k]["active"]: return k
    return None

def compute_report(signals: Dict[str, dict], curve: dict, evidence: dict) -> dict:
    rec = build_recommendation(signals)
    primary = _primary_signal(signals)
    ev_sig = (evidence.get("signals", {}) or {}).get(primary, {}) if primary else {}
    timing = {
        "primary_signal": primary,
        "median_days": ev_sig.get("timing_median"),
        "p25_days": ev_sig.get("timing_p25"),
        "p75_days": ev_sig.get("timing_p75"),
        "suggested_dte": ev_sig.get("suggested_dte"),
        "cdf": ev_sig.get("timing_cdf"),
        "structure_note": _structure_note(rec["stance"], curve.get("vix")),
    }
    outlook = {
        # NOTE: these are RATIOS (e.g. -0.084), not percents — scale x100 at render.
        "fwd_spy_5_ratio": ev_sig.get("fwd_spy_5"),
        "fwd_vix_5_ratio": ev_sig.get("fwd_vix_5"),
        "hit_rate": ev_sig.get("hit_rate"),
        "sample_n": ev_sig.get("n"),
    }
    # attach per-signal hit_rate for the signals panel
    for k, s in signals.items():
        s["hit_rate"] = (evidence.get("signals", {}) or {}).get(k, {}).get("hit_rate")
    return {
        "regime_label": _regime_label(signals),
        "recommendation": rec,
        "action": _build_action(signals, rec, timing, curve),
        "summary": _summary(signals, curve),
        "outlook": outlook,
        "timing": timing,
        "signals": signals,
        "inputs": curve,
    }

def _nearest_trigger(signals: Dict[str, dict]) -> Optional[tuple]:
    """The inactive DIRECTIONAL signal closest to firing — what to actually watch.
    Skips neutral 'double_floor' and low-confidence 'divergence' (they aren't tradeable cues)."""
    cands = [(k, s) for k, s in signals.items()
             if not s.get("active") and k not in ("divergence", "double_floor")
             and s.get("direction") in ("bullish", "bearish") and s.get("proximity") is not None]
    if not cands:
        return None
    return max(cands, key=lambda kv: kv[1].get("proximity") or 0.0)

def _watch_line(signals: Dict[str, dict], dte_txt: str) -> Optional[str]:
    nt = _nearest_trigger(signals)
    if not nt:
        return None
    k, s = nt
    pct = round((s.get("proximity") or 0.0) * 100)
    name = k.replace("_", " ")
    if s.get("direction") == "bearish":
        return (f"Closest setup is bearish — {pct}% of the way to {name} ({s.get('current_text')}). "
                f"If it fires, buy SPY puts or a put debit spread {dte_txt} and cut short-premium risk.")
    if s.get("direction") == "bullish":
        return (f"Closest setup is bullish — {pct}% of the way to {name} ({s.get('current_text')}). "
                f"If it fires, buy SPY calls or a call debit spread {dte_txt}.")
    return None

def _build_action(signals: Dict[str, dict], recommendation: dict, timing: dict, curve: dict) -> dict:
    """Blunt, plain-English 'what to do' — the advice layer. NOT financial advice,
    but no hedging: it states a concrete trade, structure, DTE, and what to watch."""
    stance = recommendation.get("stance", "neutral")
    vix = curve.get("vix")
    dte = timing.get("suggested_dte")
    dte_txt = f"~{dte} DTE" if dte else "~2 weeks out (10–14 DTE)"
    watch = _watch_line(signals, dte_txt)
    iv_note = ("VIX is elevated, so use a call DEBIT SPREAD (buy 1 ATM, sell 1 OTM) rather than naked "
               "long calls — it blunts the IV crush when vol falls."
               if (_num(vix) >= 22) else "Long calls or a call debit spread both work here.")

    if stance == "lean_puts":
        return {
            "headline": "Buy downside protection now",
            "do": "Buy SPY puts or a put debit spread",
            "dte_text": dte_txt,
            "plain": (f"The VIX curve is flattening out of contango — the earliest warning that volatility is "
                      f"building. Act on it: buy SPY puts or a put debit spread {dte_txt}, and trim/close any "
                      f"short-premium positions (iron condors, credit spreads). Do NOT open new premium-selling "
                      f"trades here — you'd be short vol right as it turns up."),
            "watch": watch,
        }
    if stance in ("buy_the_bounce", "lean_calls"):
        if signals["backwardation"]["active"]:
            return {
                "headline": "Fade the spike — go long, size small",
                "do": "Buy SPY calls or a call debit spread (small size)",
                "dte_text": dte_txt,
                "plain": (f"The curve is in backwardation — historically the spike is near its peak and vol fades "
                          f"while SPY recovers (+0.9%/5d, 64% hit). Go long: buy SPY calls or a call debit spread "
                          f"{dte_txt}, but keep size SMALL — the stress is real and you can't pick the exact bottom. "
                          f"Do NOT sell premium into this. {iv_note}"),
                "watch": watch,
            }
        return {
            "headline": "Buy the bounce — go long",
            "do": "Buy SPY calls or a call debit spread",
            "dte_text": dte_txt,
            "plain": (f"VIX is high but VVIX won't confirm the move — a classic exhaustion. Vol tends to fade and "
                      f"SPY bounces over the next few days (67% hit). Buy SPY calls or a call debit spread {dte_txt}. "
                      f"{iv_note}"),
            "watch": watch,
        }
    # neutral / calm
    plain = (f"There is no high-conviction directional trade right now. Volatility is calm and in contango "
             f"(VIX {_fmt(vix)}), which is the sweet spot for SELLING premium — SPY iron condors or credit "
             f"spreads are favored while vol stays low and stable. If you only trade direction, the honest call "
             f"is to sit in cash and wait; don't force a trade.")
    if watch:
        plain += " " + watch
    return {
        "headline": "No directional trade — sell premium or sit out",
        "do": "Sell SPY iron condors / credit spreads, or hold cash",
        "dte_text": dte_txt,
        "plain": plain,
        "watch": watch,
    }

def _fmt(x, d=1):
    """Safe number format for the narrative (handles None/NaN)."""
    v = _num(x)
    return f"{v:.{d}f}" if v else "—"

def _summary(signals: Dict[str, dict], curve: dict) -> str:
    """Always-present plain-English read of the current regime + what to watch."""
    vix, vix3m, vvix = curve.get("vix"), curve.get("vix3m"), curve.get("vvix")
    if signals["backwardation"]["active"]:
        return (f"Stress is here — VIX ({_fmt(vix)}) is above VIX3M ({_fmt(vix3m)}), a backwardated curve. "
                "Historically vol fades and SPY recovers from here, so the bias is contrarian-bullish — "
                "but the spike is real, so size carefully.")
    if signals["exhaustion"]["active"]:
        return ("VIX is elevated but VVIX won't confirm the move — a classic exhaustion setup. "
                "Vol tends to fade and SPY bounce over the next few days; the lean is long / calls.")
    if signals["ts_flattening"]["active"]:
        return ("The term structure is flattening out of contango — an early warning that vol may be building. "
                "Favor downside protection / puts and trim short-premium risk.")
    if signals["double_floor"]["active"]:
        return (f"Both VIX ({_fmt(vix)}) and VVIX ({_fmt(vvix, 0)}) are pinned at the floor — a complacent tape. "
                "Vol is cheap and tends to drift up slowly; owning optionality is favored, but there's no urgent "
                "directional edge.")
    return (f"Volatility is calm and in contango (VIX {_fmt(vix)} < VIX3M {_fmt(vix3m)}). "
            "No high-confidence signal is active — a premium-selling regime. Watch for VIX rising above VIX3M "
            "(bearish flip / buy puts) or a VIX spike that VVIX won't confirm (bullish exhaustion / buy the bounce).")

def build_series(history: pd.DataFrame, n: int = 90) -> list:
    """Last n trading days of normalized VIX/VVIX for the overlay chart."""
    df = history.copy()
    df["vix_z"] = _z(df["vix"]); df["vvix_z"] = _z(df["vvix"])
    df["ratio"] = df["vvix"] / df["vix"]
    out = []
    for idx, row in df.tail(n).iterrows():
        out.append({
            "d": str(idx.date()) if hasattr(idx, "date") else str(idx),
            "vix": round(_num(row["vix"]), 2), "vvix": round(_num(row["vvix"]), 2),
            "vix_z": round(_num(row["vix_z"]), 3), "vvix_z": round(_num(row["vvix_z"]), 3),
            "ratio": round(_num(row["ratio"]), 3),
        })
    return out

def _structure_note(stance: str, vix: Optional[float]) -> str:
    if stance in ("buy_the_bounce", "lean_calls") and vix and vix >= 22:
        return "VIX is elevated — long single calls face IV crush; a call debit spread or shorter DTE fits better."
    if stance == "lean_puts" and vix and vix < 16:
        return "VIX is low — long puts are relatively cheap; single long puts are reasonable."
    return "Standard long premium is reasonable in this IV regime; mind theta near the suggested DTE."


import logging
logger = logging.getLogger(__name__)
_HISTORY_CACHE = {"date": None, "df": None}

def _read_cboe_csv(sym: str, col: str) -> pd.Series:
    import io
    txt = requests.get(CBOE_HISTORY_URL.format(sym=sym), timeout=10).text
    df = pd.read_csv(io.StringIO(txt))
    df.columns = [c.strip().upper() for c in df.columns]
    d = df.columns[0]
    df[d] = pd.to_datetime(df[d])
    return df[[d, df.columns[-1]]].rename(columns={d: "date", df.columns[-1]: col}).set_index("date")[col]

def fetch_cboe_history() -> pd.DataFrame:
    """Daily VIX/VVIX/VIX3M/VIX9D history from CBOE, cached once per UTC date in-process."""
    today = pd.Timestamp.utcnow().normalize()
    if _HISTORY_CACHE["date"] == today and _HISTORY_CACHE["df"] is not None:
        return _HISTORY_CACHE["df"]
    df = pd.concat([
        _read_cboe_csv("VIX", "vix"), _read_cboe_csv("VVIX", "vvix"),
        _read_cboe_csv("VIX3M", "vix3m"), _read_cboe_csv("VIX9D", "vix9d"),
    ], axis=1).dropna(subset=["vix", "vvix"])
    _HISTORY_CACHE.update(date=today, df=df)
    return df

def _cboe_quote(sym: str) -> Optional[float]:
    """Latest value for a CBOE index from the delayed-quotes CDN (~15-min)."""
    try:
        data = (requests.get(CBOE_QUOTE_URL.format(sym=sym), timeout=8).json() or {}).get("data", {})
        for k in ("current_price", "price", "last", "close"):
            v = data.get(k)
            if v is not None and float(v) > 0:
                return float(v)
    except Exception as e:
        logger.debug(f"CBOE quote {sym} failed: {e}")
    return None

def _live_curve() -> dict:
    """Live curve: VIX/VVIX from origin/main's vix_fetcher; 9D/3M/6M from CBOE delayed quotes."""
    from data.vix_fetcher import get_vix_with_source, get_vvix_with_source
    vix, _ = get_vix_with_source()
    vvix, _ = get_vvix_with_source()
    return {"vix": vix, "vvix": vvix,
            "vix9d": _cboe_quote("VIX9D"), "vix3m": _cboe_quote("VIX3M"), "vix6m": _cboe_quote("VIX6M")}

def _load_evidence() -> dict:
    try:
        with open(os.path.normpath(EVIDENCE_PATH)) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"evidence.json unavailable: {e}")
        return {"signals": {}}

def get_regime_report() -> dict:
    """Live report. Never raises; degrades to neutral if data is missing."""
    try:
        hist = fetch_cboe_history()
        curve = _live_curve()
        # ensure today's live curve is the last row so signals reflect intraday-latest
        last = hist.iloc[-1].copy()
        for c in ("vix", "vvix", "vix3m", "vix9d"):
            v = curve.get(c)
            if v: last[c] = v
        hist = pd.concat([hist.iloc[:-1], pd.DataFrame([last], index=[hist.index[-1]])])
        signals = compute_signals(hist)
        rep = compute_report(signals, curve, _load_evidence())
        rep["series"] = build_series(hist)
        rep["as_of"] = str(hist.index[-1].date())
        rep["ok"] = True
        return rep
    except Exception as e:
        logger.error(f"get_regime_report failed: {e}")
        return {"ok": False, "regime_label": "unknown",
                "recommendation": {"stance": "neutral", "conviction": "low",
                                   "rationale": "Volatility data temporarily unavailable."},
                "outlook": {}, "timing": {}, "signals": {}, "inputs": {}}
