# core/vol_regime_advisor.py
"""Volatility regime advisor — signal engine, recommendation, timing.

Pure functions operate on an injected history DataFrame (columns: vix, vvix,
vix3m, vix9d) whose LAST row is "today". Live wrapper fetches CBOE data.
Backtest evidence (hit-rates + timing) is loaded from evidence.json.
"""
import json, math, os, re
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
    # 2026-08-12 re-measure, per EPISODE and from the next session's OPEN. The
    # previous text used per-DAY averages, which count the later days of a
    # multi-session episode and inverted the ts_flattening sign (+0.36% over 355
    # days vs -0.93% over 77 episodes).
    "backwardation": "VIX above VIX3M — stress is here. NOT directional at any horizon "
                     "once measured against SPY's own drift (best excess -0.26%, t -1.67). "
                     "Its real content is the TAIL: the next-day move is 2.0x more likely "
                     "to exceed 1.5%. Cut size; do not pick a side.",
    "ts_flattening": "Term structure flattening from contango. This IS directional, but only "
                     "over ~3 sessions: SPY runs -0.93% against its own base (t -3.89, 77 "
                     "episodes), fading by day 5 and gone by day 10. Worth nothing intraday "
                     "(t -0.06). Next-day tail is only 1.08x — the ~1.8x figure belongs to "
                     "2-3 days, not tomorrow.",
    "exhaustion": "VIX made a new high but VVIX won't confirm — vol tends to fade and SPY bounces.",
    "double_floor": "VIX and VVIX both at the floor — complacent; vol drifts up slowly. Owning optionality is cheap.",
    "divergence": "VVIX elevated while VIX calm. NOTE: 20-yr study shows this is statistically noise — low confidence.",
}

# What each signal implies for the equity stance.
#
# 🚨 Corrected 2026-08-12 against per-episode, tradeable-open evidence. The prior
# assignment had the two main signals the wrong way round: `backwardation` was
# labelled directional when it is a pure tail signal (2.01x next-day, excess
# t -1.67), and `ts_flattening` was labelled tail_risk when it is the only signal
# with a real direction (-0.93% over 3 sessions, t -3.89) and a next-day tail of
# just 1.08x. `_regime_label` must still return contango_flattening — the live
# HEDGE_REGIMES keying off it is pinned by a regression test.
SIGNAL_DIRECTION = {
    "backwardation": "tail_risk", "exhaustion": "tail_risk",
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


def _horizon_sessions(hz) -> str:
    """'3d' -> '3 sessions', 'intraday' -> 'the session', None -> '3 sessions'."""
    if not hz or hz == "intraday":
        return "the session" if hz == "intraday" else "3 sessions"
    m = re.match(r"(\d+)d", str(hz))
    if m:
        n = int(m.group(1))
        return "1 session" if n == 1 else f"{n} sessions"
    return str(hz)

def _direction_phrase(sig: dict) -> str:
    """Per-episode, next-open evidence for the ONE directional signal, read from the
    measured numbers when compute_report has attached them (fallback = the 2026-08-12
    re-measure, so a bare build_recommendation() still tells the truth)."""
    ex = sig.get("horizon_excess"); t = sig.get("horizon_t"); n = sig.get("n_episodes")
    hz = _horizon_sessions(sig.get("horizon") or "3d")
    if isinstance(ex, (int, float)) and isinstance(t, (int, float)) and n:
        return (f"SPY runs {ex * 100:+.2f}% against its own base over the next ~{hz} "
                f"(t {t:+.2f}, {n} episodes)")
    return "SPY runs -0.93% against its own base over the next ~3 sessions (t -3.89, 77 episodes)"

def _tail_phrase(sig: dict, fallback: float) -> str:
    tail = sig.get("tail_lift_1d")
    if not isinstance(tail, (int, float)):
        tail = fallback
    return f"the next session's move is {tail:.1f}x more likely to exceed 1.5%"

def build_recommendation(signals: Dict[str, dict]) -> dict:
    """Deterministic precedence -> stance + conviction + rationale.

    Precedence follows the 2026-08-12 per-EPISODE, next-OPEN re-measure, not the
    old per-day averages that inverted the signs:
      * ts_flattening is the ONE signal with a real direction (SPY -0.93% vs its
        own base over ~3 sessions, t -3.89, 77 episodes; gone by day 5-10). It is
        a SHORT, and it outranks the tail signals because a direction is a trade
        and a tail warning is only a size modifier that rides along in the text.
      * backwardation (2.0x next-day tail) and exhaustion (3.6x) are NOT
        directional at any horizon. They are sizing signals: cut short premium,
        do not pick a side. The old "fade the spike, go long (+0.9%/5d, 64%)"
        text was the per-day artefact and is retired.
    """
    def on(k): return signals[k]["active"]
    if on("ts_flattening"):
        sig = signals["ts_flattening"]
        hold = _horizon_sessions(sig.get("horizon") or "3d")
        tail = ""
        if on("backwardation"):
            tail = (" VIX is also above VIX3M (backwardation), so "
                    + _tail_phrase(signals["backwardation"], 2.0)
                    + " — that argues for a SMALL put, not for skipping it.")
        return {"stance": "lean_puts", "conviction": "medium",
                "rationale": "Volatility expansion — go short. Term structure flattening is the one vol "
                             f"signal with a measured direction: {_direction_phrase(sig)}, fading by day 5. "
                             f"Buy SPY puts or a put debit spread and be out within ~{hold}." + tail}
    if on("backwardation"):
        return {"stance": "reduce_risk", "conviction": "high",
                "rationale": "Backwardation: VIX above VIX3M. NOT directional at any horizon once measured "
                             f"against SPY's own drift; the content is the TAIL — "
                             f"{_tail_phrase(signals['backwardation'], 2.0)}. Cut short-premium size; "
                             "do not pick a side."}
    if on("exhaustion"):
        return {"stance": "reduce_risk", "conviction": "medium",
                "rationale": "Exhaustion: VIX at a 10-day high without VVIX confirming. NOT directional, "
                             f"but {_tail_phrase(signals['exhaustion'], 3.6)}. Cut short-premium size; "
                             "do not bet the bounce."}
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
    # Same precedence as build_recommendation: the directional signal first, so
    # timing/DTE/outlook describe the trade the action actually recommends.
    for k in ("ts_flattening", "backwardation", "exhaustion", "double_floor"):
        if signals[k]["active"]: return k
    return None

def _evidence_note(ev_k: dict) -> str:
    """One line stating what the signal actually predicts, and over what window.

    An alert with no horizon gets used at the wrong timescale — that is how a
    3-session signal ended up driving a same-day short-premium trim. Every claim
    here is per-EPISODE and measured from the next session's OPEN (the first
    price reachable after a close-based signal), so it is what you could trade.
    """
    if not ev_k:
        return ""
    n = ev_k.get("n_episodes_gap5") or 0
    if n < 15:
        return f"Only {n} independent episodes — too few to draw a conclusion."
    hz = ev_k.get("best_horizon")
    t = ev_k.get("best_horizon_t") or 0.0
    ex = ev_k.get("best_horizon_excess") or 0.0
    # 🚨 `or 0.0` would be right for a missing key but WRONG for a measured 0.0,
    # and 0.00 is the single most informative value here (double_floor has zero
    # >=1.5% next-day moves across 56 episodes). Distinguish absent from zero.
    tail = ((ev_k.get("horizons") or {}).get("1d") or {}).get("tail_lift")
    parts = []
    if ev_k.get("directional") and hz:
        parts.append(
            f"Directional over ~{hz}: SPY {ex * 100:+.2f}% vs its own base "
            f"(t {t:+.2f}, {n} episodes).")
    else:
        parts.append(f"NOT directional at any horizon ({n} episodes).")
    if tail is not None and tail >= 1.5:
        parts.append(f"Next-day move is {tail:.2f}x more likely to exceed 1.5% - "
                     f"this is a SIZING signal: cut size, do not pick a side.")
    elif tail is not None and tail < 0.5:
        parts.append(f"Next-day tail is {tail:.2f}x base - unusually CALM; "
                     f"this is the safest state for selling premium.")
    return " ".join(parts)


def compute_report(signals: Dict[str, dict], curve: dict, evidence: dict) -> dict:
    # Attach the measured evidence to each signal FIRST so the recommendation and
    # action text read the numbers instead of restating stale copies of them.
    for k, s in signals.items():
        ev_k = (evidence.get("signals", {}) or {}).get(k, {})
        s["hit_rate"] = ev_k.get("hit_rate")
        # Horizon + direction come FROM the measured evidence, never hardcoded.
        # The hardcoded strings drifted twice: ts_flattening shipped "buy puts"
        # against its own evidence, and then shipped a "~1.8x fatter next-day
        # move" that belongs to 2-3 SESSIONS (next-day lift is 1.08). Reading the
        # numbers means a re-measure updates the UI instead of silently
        # disagreeing with it.
        s["horizon"] = ev_k.get("best_horizon")
        s["horizon_excess"] = ev_k.get("best_horizon_excess")
        s["horizon_t"] = ev_k.get("best_horizon_t")
        s["is_directional"] = ev_k.get("directional")
        h1 = (ev_k.get("horizons") or {}).get("1d") or {}
        s["tail_lift_1d"] = h1.get("tail_lift")
        s["n_episodes"] = ev_k.get("n_episodes_gap5")
        s["evidence_note"] = _evidence_note(ev_k)
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
    # Per-signal action, so an alert for signal X carries X's own advice. The
    # scanner used to staple the REPORT-level headline onto every alert, which
    # is how a bearish ts_flattening early warning went out reading "Fade the
    # spike — go long" (backwardation's old headline) on 2026-09-03.
    for k, s in signals.items():
        ev_k = (evidence.get("signals", {}) or {}).get(k, {})
        s["action"] = _signal_action(k, signals, ev_k.get("suggested_dte"), curve)
    return {
        "regime_label": _regime_label(signals),
        "recommendation": rec,
        "action": _build_action(signals, rec, timing, curve),
        "summary": _summary(signals, curve),
        "outlook": outlook,
        "timing": timing,
        "signals": signals,
        "inputs": curve,
        "elevation_watch": compute_elevation_watch(curve, signals, evidence),
    }

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def compute_elevation_watch(curve: dict, signals: Dict[str, dict], evidence: dict) -> dict:
    """Forward-looking 'volatility about to pick up / stay elevated' read.

    This is deliberately an EARLY, leading composite — it does not wait for
    backwardation/ts_flattening to actually fire (which only happens once vol is
    already rising). It blends four reads from data we already have:

      * compression   — VIX/VIX3M climbing toward the 0.95 flattening line
      * front_kink     — VIX9D above 30-day VIX (near-term stress building)
      * proximity      — how close the bearish vol signals are to firing (0..1)
      * complacency    — VIX *and* VVIX both at the floor = spring-loaded; a
                         spike from here is violent but its TIMING is not
                         predictable, so complacency alone never exceeds WATCH.

    Returns a level (CALM/WATCH/ELEVATED/HIGH), a 0–100 score, the human-readable
    drivers, the expected resolution window (from the armed signal's historical
    timing), and an honest plain-English note. Pure + total; never raises.

    HONESTY: this flags ELEVATED RISK, not a dated prediction. Vol spikes from a
    dead-calm base are largely unpredictable from vol data alone; the value here
    is an early, persistent caution + a probabilistic window, not a crystal ball.
    """
    vix = curve.get("vix") or 0.0
    vix3m = curve.get("vix3m") or 0.0
    vix9d = curve.get("vix9d") or 0.0
    vvix = curve.get("vvix") or 0.0

    ratio = (vix / vix3m) if (vix and vix3m) else None
    compression = _clamp01((ratio - 0.85) / 0.15) if ratio is not None else 0.0  # 1.0 at ratio>=1.00
    front_kink = _clamp01(((vix9d / vix) - 1.0) / 0.10) if (vix and vix9d) else 0.0  # 1.0 at 9D>=10% over 30D
    vix_fuel = _clamp01((18.0 - vix) / 6.0) if vix else 0.0    # full at VIX<=12
    vvix_fuel = _clamp01((92.0 - vvix) / 12.0) if vvix else 0.0  # full at VVIX<=80
    complacency = min(vix_fuel, vvix_fuel)                      # need BOTH at the floor
    bear_prox = max(
        (signals.get("ts_flattening", {}) or {}).get("proximity") or 0.0,
        (signals.get("divergence", {}) or {}).get("proximity") or 0.0,
    )

    # Expansion track: vol is actively building. Proximity carries the most
    # weight (it's the validated machinery), term structure confirms.
    expansion = 0.5 * bear_prox + 0.3 * compression + 0.2 * front_kink
    score = round(100 * max(expansion, 0.5 * complacency))

    if expansion >= 0.75:
        level = "HIGH"
    elif expansion >= 0.50:
        level = "ELEVATED"
    elif complacency >= 0.5 or expansion >= 0.30:
        level = "WATCH"
    else:
        level = "CALM"

    drivers = []
    if bear_prox >= 0.85:
        drivers.append(f"bearish vol signal armed ({round(bear_prox * 100)}% to firing)")
    if compression >= 0.5 and ratio is not None:
        drivers.append(f"term structure compressing (VIX/VIX3M {ratio:.2f}, toward 0.95)")
    if front_kink >= 0.5:
        drivers.append(f"near-term kink (VIX9D {vix9d:.1f} > VIX {vix:.1f})")
    if complacency >= 0.5:
        drivers.append(f"spring-loaded: VIX {vix:.1f} & VVIX {vvix:.0f} both at the floor")

    # Expected resolution window — from the armed bearish signal's evidence timing.
    armed_key = "ts_flattening" if (signals.get("ts_flattening", {}) or {}).get("proximity", 0) >= bear_prox else "divergence"
    ev = (evidence.get("signals", {}) or {}).get(armed_key, {}) if evidence else {}
    window = {
        "signal": armed_key,
        "p25_days": ev.get("timing_p25"),
        "median_days": ev.get("timing_median"),
        "p75_days": ev.get("timing_p75"),
    }

    if level == "HIGH":
        note = ("Vol is elevated and fragile — expect continued chop/expansion before it calms. "
                "Cut/avoid short premium until the term structure normalizes.")
    elif level == "ELEVATED":
        note = "Vol is building — risk of a pickup is rising; tighten or stand down short premium."
    elif level == "WATCH" and complacency >= 0.5 and expansion < 0.30:
        note = ("Spring-loaded: VIX and VVIX are both at the floor. A spike from here would be violent, "
                "but the timing is not predictable — treat premium as thin and size down.")
    elif level == "WATCH":
        note = "Early warning — the term structure is starting to compress; watch for it to accelerate."
    else:
        note = "Conditions calm — no elevation building."

    return {
        "level": level,
        "score": score,
        "drivers": drivers,
        "expected_window": window,
        "note": note,
        "components": {
            "expansion": round(expansion, 3),
            "compression": round(compression, 3),
            "front_kink": round(front_kink, 3),
            "complacency": round(complacency, 3),
            "bear_proximity": round(bear_prox, 3),
        },
    }

def _nearest_trigger(signals: Dict[str, dict]) -> Optional[tuple]:
    """The inactive DIRECTIONAL signal closest to firing — what to actually watch.
    Skips neutral 'double_floor' and low-confidence 'divergence' (they aren't tradeable cues)."""
    cands = [(k, s) for k, s in signals.items()
             if not s.get("active") and k not in ("divergence", "double_floor")
             and s.get("direction") in ("bullish", "bearish", "tail_risk") and s.get("proximity") is not None]
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
    if s.get("direction") == "tail_risk":
        return (f"Closest setup is a tail warning — {pct}% of the way to {name} ({s.get('current_text')}). "
                f"If it fires, cut short-premium size or widen wings; it is not a directional cue.")
    if s.get("direction") == "bearish":
        return (f"Closest setup is bearish — {pct}% of the way to {name} ({s.get('current_text')}). "
                f"If it fires, buy SPY puts or a put debit spread {dte_txt} and cut short-premium risk.")
    if s.get("direction") == "bullish":
        return (f"Closest setup is bullish — {pct}% of the way to {name} ({s.get('current_text')}). "
                f"If it fires, buy SPY calls or a call debit spread {dte_txt}.")
    return None

SHORT_HEADLINE = "Volatility expansion — go short"
CUT_SIZE_HEADLINE = "Vol spike — cut short-premium size, no direction"

def _short_action(signals: Dict[str, dict], dte_txt: str, curve: dict) -> dict:
    """ts_flattening: the one directional vol signal. A SHORT with a short clock."""
    vix = curve.get("vix")
    sig = signals.get("ts_flattening", {}) or {}
    bw = (signals.get("backwardation", {}) or {}).get("active")
    hold = _horizon_sessions(sig.get("horizon") or "3d")
    watch = _watch_line(signals, dte_txt)
    put_note = ("VIX is elevated, so use a put DEBIT SPREAD (buy 1 ATM, sell 1 OTM) rather than naked "
                "long puts — it blunts the IV crush if vol snaps back."
                if (_num(vix) >= 22) else "Long puts or a put debit spread both work here — puts are still cheap at this VIX.")
    tail_note = ""
    if bw:
        tail_note = (" VIX is also above VIX3M (backwardation), so "
                     + _tail_phrase(signals["backwardation"], 2.0)
                     + " — that argues for a SMALL put, not for skipping it.")
    plain = (f"Volatility is expanding — the term structure is flattening out of contango"
             f"{', and the curve has inverted' if bw else ''}. This is the one vol signal with a measured "
             f"direction: {_direction_phrase(sig)}, and the edge is gone by day 5, so it is a SHORT trade "
             f"with a short clock. Go short: buy SPY puts or a put debit spread {dte_txt} and take it off "
             f"within ~{hold} — do not hold it for a week. Do NOT sell premium into this.{tail_note} {put_note}")
    return {
        "headline": SHORT_HEADLINE,
        "do": f"Buy SPY puts or a put debit spread; exit within ~{hold}",
        "dte_text": dte_txt,
        "plain": plain,
        "watch": watch,
    }

def _cut_size_action(key: str, signals: Dict[str, dict], dte_txt: str, curve: dict) -> dict:
    """backwardation / exhaustion: NOT directional. The content is the next-day tail."""
    sig = signals.get(key, {}) or {}
    watch = _watch_line(signals, dte_txt)
    fallback = 2.0 if key == "backwardation" else 3.6
    cause = ("VIX is above VIX3M — the curve has inverted" if key == "backwardation"
             else "VIX is at a 10-day high but VVIX will not confirm it")
    plain = (f"{cause}. This is a TAIL signal, not a direction: measured per episode from the next open, "
             f"SPY shows no edge either way, but {_tail_phrase(sig, fallback)}. The exposure to cut is "
             f"SHORT PREMIUM — trim or skip iron condors and credit spreads, or widen wings. Do NOT buy "
             f"calls to fade the spike and do NOT buy puts to chase it; if you stay short premium, hedge "
             f"the tail rather than betting on direction.")
    return {
        "headline": CUT_SIZE_HEADLINE,
        "do": "Trim/skip iron condors and credit spreads; hedge the tail if you stay short premium",
        "dte_text": dte_txt,
        "plain": plain,
        "watch": watch,
    }

def _signal_action(key: str, signals: Dict[str, dict], dte, curve: dict) -> Optional[dict]:
    """The advice that belongs to ONE signal, for alerts about that signal."""
    dte_txt = f"~{dte} DTE" if dte else "~2 weeks out (10–14 DTE)"
    if key == "ts_flattening":
        return _short_action(signals, dte_txt, curve)
    if key in ("backwardation", "exhaustion"):
        return _cut_size_action(key, signals, dte_txt, curve)
    return None

def _build_action(signals: Dict[str, dict], recommendation: dict, timing: dict, curve: dict) -> dict:
    """Blunt, plain-English 'what to do' — the advice layer. NOT financial advice,
    but no hedging: it states a concrete trade, structure, DTE, and what to watch."""
    stance = recommendation.get("stance", "neutral")
    vix = curve.get("vix")
    dte = timing.get("suggested_dte")
    dte_txt = f"~{dte} DTE" if dte else "~2 weeks out (10–14 DTE)"
    watch = _watch_line(signals, dte_txt)

    if stance == "lean_puts":
        return _short_action(signals, dte_txt, curve)
    if stance == "reduce_risk":
        key = "backwardation" if (signals.get("backwardation", {}) or {}).get("active") else "exhaustion"
        return _cut_size_action(key, signals, dte_txt, curve)
    if stance in ("buy_the_bounce", "lean_calls"):
        # No live signal emits this any more (no vol signal measured bullish), but
        # the stance stays valid for the UI type and any future re-measure.
        iv_note = ("VIX is elevated, so use a call DEBIT SPREAD (buy 1 ATM, sell 1 OTM) rather than naked "
                   "long calls — it blunts the IV crush when vol falls."
                   if (_num(vix) >= 22) else "Long calls or a call debit spread both work here.")
        return {
            "headline": "Buy the bounce — go long",
            "do": "Buy SPY calls or a call debit spread",
            "dte_text": dte_txt,
            "plain": f"Buy SPY calls or a call debit spread {dte_txt}. {iv_note}",
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
    if signals["ts_flattening"]["active"]:
        bw = signals["backwardation"]["active"]
        return ("Volatility expansion — the term structure is flattening out of contango"
                f"{f' and VIX ({_fmt(vix)}) is above VIX3M ({_fmt(vix3m)})' if bw else ''}. "
                "This is the one vol signal with a measured direction: SPY drifts lower for about 3 sessions, "
                "so the lean is short / puts, and the edge is gone within a week."
                + (" The inverted curve adds a fat next-day tail, so keep the put small." if bw else ""))
    if signals["backwardation"]["active"]:
        return (f"Stress is here — VIX ({_fmt(vix)}) is above VIX3M ({_fmt(vix3m)}), a backwardated curve. "
                "Measured per episode this is NOT a direction: SPY shows no edge either way, but the "
                "next-day move is about 2x more likely to exceed 1.5%. Cut short-premium size; don't pick a side.")
    if signals["exhaustion"]["active"]:
        return ("VIX is at a 10-day high but VVIX won't confirm the move. Measured per episode this is NOT "
                "a bounce signal — SPY shows no edge either way — but the next-day tail is about 3.6x base. "
                "Cut short-premium size; don't bet the bounce.")
    if signals["double_floor"]["active"]:
        return (f"Both VIX ({_fmt(vix)}) and VVIX ({_fmt(vvix, 0)}) are pinned at the floor — a complacent tape. "
                "Vol is cheap and tends to drift up slowly; owning optionality is favored, but there's no urgent "
                "directional edge.")
    return (f"Volatility is calm and in contango (VIX {_fmt(vix)} < VIX3M {_fmt(vix3m)}). "
            "No high-confidence signal is active — a premium-selling regime. Watch for the VIX/VIX3M ratio "
            "climbing toward 0.95 (volatility expansion / go short) or VIX crossing above VIX3M (fat tail / cut size).")

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
    if stance == "lean_puts":
        if vix and vix >= 22:
            return "VIX is elevated — long single puts face IV crush if vol snaps back; a put debit spread fits better."
        return "Puts are still cheap at this VIX — long puts or a put debit spread; the hold is ~3 sessions, so mind theta."
    if stance == "reduce_risk":
        return ("Sizing note, not a structure note: the edge here is carrying LESS short premium, "
                "not putting on a new position.")
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

def overlay_live_curve(history: pd.DataFrame, curve: dict, today: pd.Timestamp) -> pd.DataFrame:
    """Overlay the live intraday curve as the most-recent row of the history.

    The CBOE daily history file only updates after the session closes, so during
    a live session its last row is the PRIOR session. When `today` is a later
    trading day than the last history row (and we have a live VIX), append the
    live curve as a new, correctly-dated row — so `as_of`, the series, and the
    rolling lookbacks all reflect the current session instead of mislabeling
    today's intraday values with yesterday's date. Otherwise (same date, no live
    VIX, or a weekend) refresh the existing last row in place.

    Pure: operates on the injected frame, never touches the network. `today`
    must be a tz-naive trade date (Eastern).
    """
    if history is None or history.empty:
        return history
    last = history.iloc[-1].copy()
    for c in ("vix", "vvix", "vix3m", "vix9d"):
        v = curve.get(c)
        if v:
            last[c] = v
    today = pd.Timestamp(today).normalize()
    last_date = history.index[-1].normalize()
    is_trading_day = today.weekday() < 5  # Mon–Fri (holidays carry live last-close; rare, low impact)
    has_live_vix = bool(curve.get("vix"))
    if today > last_date and is_trading_day and has_live_vix:
        return pd.concat([history, pd.DataFrame([last], index=[today])])
    return pd.concat([history.iloc[:-1], pd.DataFrame([last], index=[history.index[-1]])])

def get_regime_report() -> dict:
    """Live report. Never raises; degrades to neutral if data is missing."""
    try:
        hist = fetch_cboe_history()
        curve = _live_curve()
        # Overlay today's live curve so signals + as_of reflect the current
        # session (CBOE's daily file lags until after the close).
        today_et = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
        hist = overlay_live_curve(hist, curve, today_et)
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
