# tests/test_vol_regime_advisor.py
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
