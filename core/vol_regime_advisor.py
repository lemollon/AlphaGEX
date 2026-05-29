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

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

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
    return {
        key: {"active": raw[key], "value": round(values[key], 4),
              "confidence": SIGNAL_CONFIDENCE[key], "blurb": SIGNAL_BLURB[key]}
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
        "fwd_spy_5_pct": ev_sig.get("fwd_spy_5"),
        "fwd_vix_5_pct": ev_sig.get("fwd_vix_5"),
        "hit_rate": ev_sig.get("hit_rate"),
        "sample_n": ev_sig.get("n"),
    }
    # attach per-signal hit_rate for the signals panel
    for k, s in signals.items():
        s["hit_rate"] = (evidence.get("signals", {}) or {}).get(k, {}).get("hit_rate")
    return {
        "regime_label": _regime_label(signals),
        "recommendation": rec,
        "outlook": outlook,
        "timing": timing,
        "signals": signals,
        "inputs": curve,
    }

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
            v = curve.get(c if c != "vix9d" else "vix9d")
            if v: last[c] = v
        hist = pd.concat([hist.iloc[:-1], pd.DataFrame([last], index=[hist.index[-1]])])
        signals = compute_signals(hist)
        rep = compute_report(signals, curve, _load_evidence())
        rep["as_of"] = str(hist.index[-1].date())
        rep["ok"] = True
        return rep
    except Exception as e:
        logger.error(f"get_regime_report failed: {e}")
        return {"ok": False, "regime_label": "unknown",
                "recommendation": {"stance": "neutral", "conviction": "low",
                                   "rationale": "Volatility data temporarily unavailable."},
                "outlook": {}, "timing": {}, "signals": {}, "inputs": {}}
