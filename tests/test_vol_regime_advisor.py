# tests/test_vol_regime_advisor.py
import math
import pandas as pd
from core.vol_regime_advisor import compute_signals

def _history(vix_last, vix3m_last, n=300):
    # flat history then set the last row; enough rows for rolling(252)/rolling(20)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame(index=idx)
    df["vix"] = 15.0; df["vvix"] = 90.0; df["vix3m"] = 18.0; df["vix9d"] = 13.0
    df.loc[df.index[-21], "vix"] = vix3m_last  # 20 days ago for flattening test default
    df.iloc[-1, df.columns.get_loc("vix")] = vix_last
    df.iloc[-1, df.columns.get_loc("vix3m")] = vix3m_last
    return df

def test_backwardation_fires_when_vix_above_vix3m():
    df = _history(vix_last=25.0, vix3m_last=20.0)
    sigs = compute_signals(df)
    assert sigs["backwardation"]["active"] is True

def test_backwardation_off_in_contango():
    df = _history(vix_last=15.0, vix3m_last=18.0)
    sigs = compute_signals(df)
    assert sigs["backwardation"]["active"] is False

def test_divergence_flagged_low_confidence():
    df = _history(vix_last=15.0, vix3m_last=18.0)
    sigs = compute_signals(df)
    assert sigs["divergence"]["confidence"] == "low"

def test_values_are_json_safe_on_short_history():
    # Under-filled rolling windows (rolling(252)/rolling(60)) produce NaN internally;
    # the serialized `value` fields must be finite (NaN is invalid JSON downstream).
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame(index=idx)
    df["vix"] = 15.0; df["vvix"] = 90.0; df["vix3m"] = 18.0; df["vix9d"] = 13.0
    sigs = compute_signals(df)
    for key, s in sigs.items():
        assert isinstance(s["value"], float)
        assert not math.isnan(s["value"]), f"{key} value leaked NaN"

def test_short_history_keeps_undefined_signals_off():
    # With NaN ts20/vix_pct (short history), windowed signals must stay OFF,
    # not flip ON from NaN->0 coercion.
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame(index=idx)
    df["vix"] = 18.0; df["vvix"] = 90.0; df["vix3m"] = 18.0; df["vix9d"] = 13.0
    sigs = compute_signals(df)
    assert sigs["ts_flattening"]["active"] is False
    assert sigs["exhaustion"]["active"] is False

from core.vol_regime_advisor import build_recommendation, compute_report

def _sigs(active):
    base = {k: {"active": False, "value": 0.0, "confidence": "low", "blurb": ""}
            for k in ("backwardation","ts_flattening","exhaustion","double_floor","divergence")}
    for k in active: base[k]["active"] = True
    return base

def test_backwardation_is_a_tail_signal_not_a_bounce():
    # 2026-08-12 per-episode re-measure: backwardation is NOT directional at any
    # horizon (best excess -0.26%, t -1.67, 65 episodes); its content is a 2.0x
    # next-day tail. The old "buy_the_bounce (+0.9%/5d, 64% hit)" was a per-DAY
    # artefact. So: cut size, never "go long".
    rec = build_recommendation(_sigs(["backwardation", "exhaustion"]))
    assert rec["stance"] == "reduce_risk"
    assert "go long" not in rec["rationale"].lower()
    assert "bounce" not in rec["rationale"].lower() or "not" in rec["rationale"].lower()

def test_flattening_is_the_short_and_outranks_backwardation():
    # 2026-08-12 per-episode, next-open re-measure: ts_flattening is the ONE vol
    # signal with a real direction — SPY -0.93% vs its own base over ~3 sessions
    # (t -3.89, 77 episodes), gone by day 5-10. Per Leron 2026-09-04 the alert
    # reads "Volatility expansion — go short", not "cut short premium".
    # REGRESSION: on 2026-09-03 the ts_flattening early warning went out with
    # backwardation's "Fade the spike — go long" because backwardation outranked
    # it. The directional signal must win the stance.
    rec = build_recommendation(_sigs(["ts_flattening"]))
    assert rec["stance"] == "lean_puts"
    assert "go short" in rec["rationale"].lower()
    both = build_recommendation(_sigs(["ts_flattening", "backwardation"]))
    assert both["stance"] == "lean_puts"
    assert "go short" in both["rationale"].lower()
    assert "go long" not in both["rationale"].lower()
    assert "small" in both["rationale"].lower()   # backwardation's tail rides along as sizing

def test_flattening_still_labels_contango_flattening_regime():
    # GUARD: `contango_flattening` is what ironforge's HEDGE_REGIMES keys off to
    # propose the live SPARK put-spread tail hedge. Re-labelling the signal's
    # DIRECTION must not silently disarm that risk control.
    from core.vol_regime_advisor import _regime_label
    assert _regime_label(_sigs(["ts_flattening"])) == "contango_flattening"


def test_neutral_when_nothing_active():
    rec = build_recommendation(_sigs([]))
    assert rec["stance"] == "neutral"

def test_report_has_required_keys():
    rep = compute_report(_sigs(["exhaustion"]),
                         curve={"vix":30,"vvix":110,"vix9d":28,"vix3m":26,"vix6m":25},
                         evidence={"signals":{"exhaustion":{"hit_rate":0.6,"timing_median":5,
                            "timing_p25":3,"timing_p75":8,"suggested_dte":13,"timing_cdf":[0.1]*21,
                            "fwd_spy_5":0.009,"fwd_vix_5":-0.07,"n":91}}})
    for k in ("regime_label","recommendation","summary","outlook","timing","signals","inputs"):
        assert k in rep
    assert rep["timing"]["suggested_dte"] == 13
    assert isinstance(rep["summary"], str) and len(rep["summary"]) > 0

def test_action_gives_concrete_advice_per_stance():
    from core.vol_regime_advisor import _build_action
    curve = {"vix": 15.3, "vix3m": 18.7, "vvix": 86}
    # neutral → sell premium / sit out
    a = _build_action(_sigs([]), {"stance": "neutral"}, {"suggested_dte": None}, curve)
    assert a["headline"] and a["do"] and a["plain"]
    assert "premium" in a["plain"].lower() or "cash" in a["plain"].lower()
    # lean_puts (ts_flattening) → "Volatility expansion — go short": buy puts, short clock
    a = _build_action(_sigs(["ts_flattening"]), {"stance": "lean_puts"}, {"suggested_dte": 12}, curve)
    assert a["headline"] == "Volatility expansion — go short"
    assert "~12 DTE" in a["dte_text"]
    assert "put" in a["do"].lower()
    assert "go short" in a["plain"].lower()
    assert "3 sessions" in a["plain"].lower()
    assert "go long" not in a["plain"].lower() and "buy spy calls" not in a["plain"].lower()
    # lean_puts with elevated VIX → put debit-spread guidance
    a = _build_action(_sigs(["ts_flattening", "backwardation"]), {"stance": "lean_puts"}, {"suggested_dte": 12},
                      {"vix": 30, "vix3m": 26, "vvix": 110})
    assert "put debit spread" in a["plain"].lower()
    assert "small" in a["plain"].lower()   # backwardation tail → size note
    # reduce_risk (backwardation / exhaustion) → cut short premium, NO direction either way
    a = _build_action(_sigs(["backwardation"]), {"stance": "reduce_risk"}, {"suggested_dte": 8}, curve)
    assert "premium" in a["do"].lower()
    assert "fade the spike" not in a["headline"].lower()
    assert "go long" not in a["plain"].lower()
    assert "do not buy calls" in a["plain"].lower()
    assert "do not buy puts" in a["plain"].lower()
    a = _build_action(_sigs(["exhaustion"]), {"stance": "reduce_risk"}, {"suggested_dte": 13},
                      {"vix": 30, "vix3m": 26, "vvix": 110})
    assert "premium" in a["do"].lower()
    assert "bounce" not in a["headline"].lower()

def test_each_alerting_signal_carries_its_own_action():
    # REGRESSION (2026-09-03): the scanner attached the REPORT-level headline to
    # every alert, so a bearish ts_flattening early warning went out reading
    # "Fade the spike — go long" (backwardation's headline). Each alerting signal
    # must carry its own advice, and a bearish signal can never say "go long".
    from core.vol_regime_advisor import compute_report, SIGNAL_DIRECTION
    rep = compute_report(_sigs(["ts_flattening", "backwardation"]),
                         curve={"vix": 18.0, "vvix": 85, "vix9d": 18.5, "vix3m": 17.56, "vix6m": 18.2},
                         evidence={"signals": {}})
    sig = rep["signals"]
    assert sig["ts_flattening"]["action"]["headline"] == "Volatility expansion — go short"
    assert "go long" not in sig["ts_flattening"]["action"]["plain"].lower()
    assert sig["backwardation"]["action"]["headline"] != sig["ts_flattening"]["action"]["headline"]
    assert "go long" not in sig["backwardation"]["action"]["plain"].lower()
    assert sig["exhaustion"]["action"] is not None
    assert sig["double_floor"]["action"] is None and sig["divergence"]["action"] is None
    for k, s in sig.items():
        if s["action"] and SIGNAL_DIRECTION[k] == "bearish":
            assert "go long" not in s["action"]["headline"].lower()
    # report-level action follows the directional signal, not backwardation
    assert rep["action"]["headline"] == "Volatility expansion — go short"
    assert rep["recommendation"]["stance"] == "lean_puts"
    assert rep["timing"]["primary_signal"] == "ts_flattening"
    assert rep["regime_label"] == "backwardation_stressed"   # label precedence unchanged (hedge overlay)

def test_action_text_reads_measured_evidence():
    # A re-measure must change the words, not silently disagree with them.
    from core.vol_regime_advisor import compute_report
    ev = {"signals": {"ts_flattening": {"best_horizon": "2d", "best_horizon_excess": -0.0123,
                                        "best_horizon_t": -4.5, "n_episodes_gap5": 80, "directional": True,
                                        "suggested_dte": 9, "horizons": {"1d": {"tail_lift": 1.1}}},
                      "backwardation": {"horizons": {"1d": {"tail_lift": 2.7}}, "n_episodes_gap5": 65,
                                        "directional": False, "suggested_dte": 8}}}
    rep = compute_report(_sigs(["ts_flattening", "backwardation"]),
                         curve={"vix": 18.0, "vvix": 85, "vix9d": 18.5, "vix3m": 17.56, "vix6m": 18.2},
                         evidence=ev)
    plain = rep["action"]["plain"]
    assert "-1.23%" in plain and "80 episodes" in plain and "2 sessions" in plain
    assert "2.7x" in plain
    assert "~9 DTE" in rep["action"]["dte_text"]

def test_report_includes_action():
    rep = compute_report(_sigs([]), curve={"vix": 15.3, "vvix": 86, "vix3m": 18.7},
                         evidence={"signals": {}})
    assert "action" in rep and rep["action"]["headline"]

def test_signals_carry_direction_trigger_and_proximity():
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    df = pd.DataFrame({"vix": 15.0, "vvix": 90.0, "vix3m": 18.0, "vix9d": 13.0}, index=idx)
    df.iloc[-1, df.columns.get_loc("vix")] = 25.0
    df.iloc[-1, df.columns.get_loc("vix3m")] = 20.0  # backwardation: 25/20 = 1.25
    sigs = compute_signals(df)
    b = sigs["backwardation"]
    # Corrected 2026-08-12: backwardation has NO directional edge at any horizon
    # once measured per-episode against SPY's own drift (best excess -0.26%,
    # t -1.67). Its content is the next-day TAIL (2.01x). The old "bullish" label
    # came from a raw 60d mean of +3.93% — but SPY drifts +2.86% over any 60 days,
    # so the excess is +1.07% at t 1.31, i.e. beta read as edge.
    assert b["direction"] == "tail_risk"
    assert "VIX > VIX3M" in b["trigger_text"]
    assert "VIX/VIX3M" in b["current_text"]
    assert b["proximity"] == 1.0            # 1.25 clamped to 1.0 (firing)
    assert 0.0 <= sigs["ts_flattening"]["proximity"] <= 1.0

def test_summary_present_and_describes_calm_regime():
    from core.vol_regime_advisor import _summary
    s = _summary(_sigs([]), {"vix": 15.3, "vix3m": 18.7, "vvix": 86})
    assert "contango" in s.lower()
    # tells the user what would flip it: ratio toward 0.95 = go short; VIX > VIX3M = cut size
    assert "go short" in s.lower() and "cut size" in s.lower()
    assert "buy the bounce" not in s.lower()   # no vol signal measures bullish any more

def test_build_series_shape():
    import pandas as pd
    from core.vol_regime_advisor import build_series
    idx = pd.date_range("2024-01-01", periods=120, freq="B")
    df = pd.DataFrame({"vix": 15.0, "vvix": 90.0, "vix3m": 18.0, "vix9d": 13.0}, index=idx)
    ser = build_series(df, n=90)
    assert len(ser) == 90
    for row in ser:
        for k in ("d", "vix", "vvix", "vix_z", "vvix_z", "ratio"):
            assert k in row
        assert isinstance(row["ratio"], float)

import core.vol_regime_advisor as adv

def test_get_regime_report_uses_injected_history(monkeypatch):
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    hist = pd.DataFrame({"vix":15.0,"vvix":90.0,"vix3m":18.0,"vix9d":13.0}, index=idx)
    hist.iloc[-1, hist.columns.get_loc("vix")] = 26.0
    hist.iloc[-1, hist.columns.get_loc("vix3m")] = 20.0
    monkeypatch.setattr(adv, "fetch_cboe_history", lambda: hist)
    monkeypatch.setattr(adv, "_live_curve", lambda: {"vix":26.0,"vvix":110.0,"vix9d":24.0,"vix3m":20.0,"vix6m":19.0})
    rep = adv.get_regime_report()
    assert rep["regime_label"] == "backwardation_stressed"
    # This history fires BOTH backwardation (26/20) and ts_flattening (ratio was
    # 0.83 twenty sessions ago). The directional signal wins the stance; the
    # label still says backwardation_stressed for the hedge overlay.
    assert rep["signals"]["ts_flattening"]["active"] and rep["signals"]["backwardation"]["active"]
    assert rep["recommendation"]["stance"] == "lean_puts"
    assert rep["action"]["headline"] == "Volatility expansion — go short"
    assert "go long" not in rep["action"]["plain"].lower()

def test_overlay_live_curve_appends_today_dated_row_on_new_session():
    # Intraday on a later trading day: CBOE history lags to the prior session,
    # so the live curve must land on a NEW row dated today (not overwrite y'day).
    import pandas as pd
    from core.vol_regime_advisor import overlay_live_curve
    idx = pd.to_datetime(["2026-06-05", "2026-06-08"])  # Fri, Mon closes
    hist = pd.DataFrame({"vix": [16.0, 20.26], "vvix": [90.0, 97.33],
                         "vix3m": [21.0, 21.65], "vix9d": [15.0, 22.37]}, index=idx)
    curve = {"vix": 19.95, "vvix": 96.72, "vix3m": 21.49, "vix9d": 22.71}
    out = overlay_live_curve(hist, curve, pd.Timestamp("2026-06-09"))  # Tue
    assert str(out.index[-1].date()) == "2026-06-09"          # stamped today
    assert out.iloc[-1]["vix"] == 19.95                       # live value
    assert out.iloc[-2]["vix"] == 20.26                       # y'day close preserved
    assert len(out) == 3                                      # appended, not overwritten

def test_overlay_live_curve_refreshes_in_place_on_weekend():
    # Saturday: no new trading session — refresh last row in place, keep its date.
    import pandas as pd
    from core.vol_regime_advisor import overlay_live_curve
    idx = pd.to_datetime(["2026-06-04", "2026-06-05"])  # Thu, Fri
    hist = pd.DataFrame({"vix": [16.0, 17.0], "vvix": [90.0, 91.0],
                         "vix3m": [21.0, 21.0], "vix9d": [15.0, 15.0]}, index=idx)
    curve = {"vix": 17.5, "vvix": 92.0, "vix3m": 21.0, "vix9d": 15.0}
    out = overlay_live_curve(hist, curve, pd.Timestamp("2026-06-06"))  # Sat
    assert str(out.index[-1].date()) == "2026-06-05"          # no Saturday row
    assert out.iloc[-1]["vix"] == 17.5                        # still refreshed live
    assert len(out) == 2

def test_overlay_live_curve_no_live_vix_keeps_last_date():
    # Missing live VIX (fetch failed): never invent a today row.
    import pandas as pd
    from core.vol_regime_advisor import overlay_live_curve
    idx = pd.to_datetime(["2026-06-05", "2026-06-08"])
    hist = pd.DataFrame({"vix": [16.0, 20.0], "vvix": [90.0, 97.0],
                         "vix3m": [21.0, 21.5], "vix9d": [15.0, 22.0]}, index=idx)
    out = overlay_live_curve(hist, {"vix": None, "vvix": 96.0}, pd.Timestamp("2026-06-09"))
    assert str(out.index[-1].date()) == "2026-06-08"
    assert out.iloc[-1]["vvix"] == 96.0                       # other live fields still applied
    assert len(out) == 2

from core.vol_regime_advisor import compute_elevation_watch

def _sig_prox(**prox):
    base = {k: {"active": False, "value": 0.0, "confidence": "low", "blurb": "",
                "direction": "neutral", "proximity": 0.0}
            for k in ("backwardation","ts_flattening","exhaustion","double_floor","divergence")}
    for k, p in prox.items():
        base[k]["proximity"] = p
    base["ts_flattening"]["direction"] = "tail_risk"
    base["divergence"]["direction"] = "bearish"
    return base

_EV = {"signals": {"ts_flattening": {"timing_p25": 2, "timing_median": 5, "timing_p75": 11}}}

def test_elevation_calm_in_healthy_contango():
    curve = {"vix": 15.0, "vix3m": 20.0, "vix9d": 14.0, "vvix": 95.0}  # vvix not at floor
    w = compute_elevation_watch(curve, _sig_prox(ts_flattening=0.2), _EV)
    assert w["level"] == "CALM"
    assert w["score"] < 25

def test_elevation_watch_when_spring_loaded():
    # Both VIX and VVIX at the floor, but no expansion yet -> WATCH, capped, with the
    # honest "timing not predictable" note (this is the 6/04-style complacent setup).
    curve = {"vix": 13.0, "vix3m": 17.0, "vix9d": 12.5, "vvix": 80.0}
    w = compute_elevation_watch(curve, _sig_prox(ts_flattening=0.2), _EV)
    assert w["level"] == "WATCH"
    assert w["components"]["complacency"] >= 0.5
    assert "not predictable" in w["note"]

def test_elevation_high_when_armed_and_compressing():
    # ts_flattening at 0.98 + ratio 0.94 + 9D kink -> HIGH (today's 6/09 setup).
    curve = {"vix": 19.87, "vix3m": 21.31, "vix9d": 22.14, "vvix": 95.81}
    w = compute_elevation_watch(curve, _sig_prox(ts_flattening=0.98), _EV)
    assert w["level"] == "HIGH"
    assert w["expected_window"]["median_days"] == 5      # pulled from evidence timing
    assert any("armed" in d for d in w["drivers"])

def test_elevation_never_raises_on_empty():
    w = compute_elevation_watch({}, _sig_prox(), {})
    assert w["level"] in ("CALM", "WATCH", "ELEVATED", "HIGH")
    assert isinstance(w["score"], int)


def test_direction_never_gates_whether_a_signal_is_watched():
    """Regression for the 2026-08-07 silent outage.

    PR #2764 relabelled ts_flattening 'bearish' -> 'tail_risk'. scanner.ts then
    filtered activeKeys on `dir === 'bullish' || dir === 'bearish'`, so the signal
    silently stopped alerting for five days. Membership must come from
    ALERTING_SIGNAL_KEYS; `direction` only describes meaning.

    This pins the Python side: every alerting signal may carry ANY direction value
    without that implying it should be dropped.
    """
    from core.vol_regime_advisor import SIGNAL_DIRECTION
    alerting = {"backwardation", "exhaustion", "ts_flattening"}
    assert alerting <= set(SIGNAL_DIRECTION), "alerting key missing a direction"
    # At least one alerting signal is deliberately non-bullish/bearish — if that
    # is ever untrue the outage mode becomes invisible again.
    assert any(SIGNAL_DIRECTION[k] not in ("bullish", "bearish") for k in alerting)
