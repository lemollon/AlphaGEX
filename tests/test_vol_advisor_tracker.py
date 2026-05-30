# tests/test_vol_advisor_tracker.py
import pandas as pd
from services.vol_advisor_tracker import score_row

def _fwd(vix_path, spy_path):
    idx = pd.date_range("2024-02-01", periods=len(vix_path), freq="B")
    return pd.DataFrame({"vix": vix_path, "spy": spy_path}, index=idx)

def test_buy_the_bounce_correct_when_spy_up_in_window():
    row = {"stance": "buy_the_bounce", "predicted_dir": "spy_up",
           "horizon_days": 5, "window_p75_days": 8, "vix": 30.0, "spy": 500.0}
    fwd = _fwd([30,29,28,27,26,25,24,23], [500,501,503,505,506,507,508,509])
    res = score_row(row, fwd)
    assert res["correct"] is True
    assert res["in_window"] is True
    assert res["event_landed_day"] is not None

def test_lean_puts_incorrect_when_spy_rises():
    row = {"stance": "lean_puts", "predicted_dir": "spy_down",
           "horizon_days": 5, "window_p75_days": 8, "vix": 14.0, "spy": 500.0}
    fwd = _fwd([14,14,14,14,15,15,15,15], [500,502,504,506,508,510,512,514])
    res = score_row(row, fwd)
    assert res["correct"] is False
