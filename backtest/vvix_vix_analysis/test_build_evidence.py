# backtest/vvix_vix_analysis/test_build_evidence.py
import json, os, subprocess, sys

HERE = os.path.dirname(__file__)

def test_evidence_json_shape():
    # regenerate then validate
    subprocess.run([sys.executable, os.path.join(HERE, "build_evidence.py")], check=True)
    with open(os.path.join(HERE, "evidence.json")) as f:
        ev = json.load(f)
    assert "signals" in ev and "as_of" in ev
    for key in ("backwardation", "ts_flattening", "exhaustion", "double_floor", "divergence"):
        s = ev["signals"][key]
        for field in ("n", "hit_rate", "fwd_vix_5", "fwd_spy_5", "t_fwd_spy_5",
                      "timing_median", "timing_p25", "timing_p75", "timing_cdf", "suggested_dte"):
            assert field in s, f"{key} missing {field}"
        assert 0.0 <= s["hit_rate"] <= 1.0
        cdf = s["timing_cdf"]
        assert len(cdf) == 21
        assert all(0.0 <= x <= 1.0 for x in cdf)
        assert all(cdf[i] <= cdf[i+1] + 1e-9 for i in range(len(cdf)-1)), "CDF must be monotonic"


def _ev():
    with open(os.path.join(HERE, "evidence.json")) as f:
        return json.load(f)


def test_episode_estimates_present_and_smaller_than_day_count():
    ev = _ev()
    for key, s in ev["signals"].items():
        assert "n_episodes_gap5" in s, f"{key} missing episode count"
        # Episodes must never exceed firing days; if they're equal the signal
        # doesn't cluster and the whole correction is moot.
        assert s["n_episodes_gap5"] <= s["n"], key


def test_horizons_carry_base_rates_and_excess():
    """A rate or mean without its base is what mislabeled ts_flattening."""
    ev = _ev()
    for key, s in ev["signals"].items():
        for h, v in s.get("horizons", {}).items():
            for field in ("mean", "mean_base", "excess", "t", "up_rate",
                          "up_base", "up_lift", "tail_rate", "tail_base", "tail_lift"):
                assert field in v, f"{key}/{h} missing {field}"
            assert abs(v["excess"] - (v["mean"] - v["mean_base"])) < 1e-12, f"{key}/{h}"
            assert 0.0 <= v["up_rate"] <= 1.0 and 0.0 <= v["up_base"] <= 1.0


def test_best_horizon_uses_excess_not_raw_drift():
    """Regression: raw-mean t picks 60d for every signal because SPY drifts up.

    Guard that no signal reports 60d as best while its up_lift there is ~1.0 —
    that combination is beta being read as edge.
    """
    ev = _ev()
    for key, s in ev["signals"].items():
        bh = s.get("best_horizon")
        if bh != "60d":
            continue
        lift = s["horizons"]["60d"]["up_lift"]
        assert abs(lift - 1.0) > 0.15, (
            f"{key}: best_horizon=60d with up_lift {lift:.2f} — that is drift")


def test_ts_flattening_is_short_horizon_and_negative():
    """The measured shape: nothing intraday, real at 2-5 sessions, gone by 10."""
    h = _ev()["signals"]["ts_flattening"]["horizons"]
    assert abs(h["intraday"]["t"]) < 1.0, "intraday should be noise"
    assert h["3d"]["excess"] < 0 and h["3d"]["t"] < -2.0, "3d edge missing"
    assert abs(h["10d"]["t"]) < 2.0, "10d should have decayed"


def test_backwardation_is_a_tail_signal_not_directional():
    """Its value is the next-day tail, not direction — the 60d bullish read was drift."""
    s = _ev()["signals"]["backwardation"]
    assert s["horizons"]["1d"]["tail_lift"] > 1.5, "tail lift should be large"
    assert not s["directional"] or abs(s["best_horizon_t"]) >= 2.0
