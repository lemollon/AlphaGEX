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
