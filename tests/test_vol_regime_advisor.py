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

def test_backwardation_takes_precedence_as_bounce():
    rec = build_recommendation(_sigs(["backwardation", "exhaustion"]))
    assert rec["stance"] == "buy_the_bounce"

def test_flattening_leans_puts():
    rec = build_recommendation(_sigs(["ts_flattening"]))
    assert rec["stance"] == "lean_puts"

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
    # lean_puts → buy downside
    a = _build_action(_sigs(["ts_flattening"]), {"stance": "lean_puts"}, {"suggested_dte": 12}, curve)
    assert "put" in a["do"].lower() and "~12 DTE" in a["dte_text"]
    # exhaustion → buy calls
    a = _build_action(_sigs(["exhaustion"]), {"stance": "buy_the_bounce"}, {"suggested_dte": 13},
                      {"vix": 30, "vix3m": 26, "vvix": 110})
    assert "call" in a["do"].lower()
    assert "debit spread" in a["plain"].lower()   # high VIX → debit-spread guidance

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
    assert b["direction"] == "bullish"
    assert "VIX > VIX3M" in b["trigger_text"]
    assert "VIX/VIX3M" in b["current_text"]
    assert b["proximity"] == 1.0            # 1.25 clamped to 1.0 (firing)
    assert 0.0 <= sigs["ts_flattening"]["proximity"] <= 1.0

def test_summary_present_and_describes_calm_regime():
    from core.vol_regime_advisor import _summary
    s = _summary(_sigs([]), {"vix": 15.3, "vix3m": 18.7, "vvix": 86})
    assert "contango" in s.lower()
    assert "exhaustion" in s.lower()        # tells the user what would flip it bullish

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
    assert rep["recommendation"]["stance"] == "buy_the_bounce"
