"""The base case the pages never stated - and the textbook claim it refutes.

🚨 I ASSERTED "DRIFT UP, CRASH DOWN" FROM MEMORY AND THE SECOND HALF IS FALSE
for this era. These pin the arithmetic so the panel can never quietly start
claiming a crash premium the sample does not pay.
"""
import pytest
from backend.routes_risk import tape_shape


def test_thin_history_refuses_to_quote_tails(monkeypatch):
    """⛔ Below 120 sessions the tail cells are single digits. Say so."""
    import backend.routes_risk as R

    class _DB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def order_by(self, *a): return self
        def all(self):
            class Row:
                trade_date, close = "2026-01-01", 100.0
            return [Row()] * 5
        def close(self): pass

    monkeypatch.setattr(R, "SessionLocal", lambda: _DB())
    out = tape_shape()
    assert out["status"] == "thin"
    assert "120" in out["reason"]


def _run(closes, monkeypatch):
    import backend.routes_risk as R
    from datetime import date, timedelta

    class Row:
        def __init__(self, d, c): self.trade_date, self.close = d, c

    rows = [Row(date(2024, 1, 1) + timedelta(days=i), c) for i, c in enumerate(closes)]

    class _DB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def order_by(self, *a): return self
        def all(self): return rows
        def close(self): pass

    monkeypatch.setattr(R, "SessionLocal", lambda: _DB())
    return tape_shape()


def test_a_pure_uptrend_reports_drift_up(monkeypatch):
    out = _run([100 * (1.001 ** i) for i in range(200)], monkeypatch)
    assert out["status"] == "ok"
    assert out["p_up_day"] == pytest.approx(1.0)
    assert out["mean_ret"] > 0


def test_a_left_skewed_series_is_reported_as_left_skewed(monkeypatch):
    """The panel must be ABLE to say 'crash down' - it just must not say it
    when the data does not. This proves the detector works."""
    # 🚨 The drop must be MORE than 5% of observations or the 5th percentile
    # lands exactly on the boundary and the ratio reads 1.00 - which is how the
    # first version of this test failed and briefly looked like a code bug.
    px, v = [100.0], 100.0
    for i in range(400):
        v *= (1 + (0.004 if i % 10 else -0.05))     # 10% of days are a big drop
        px.append(v)
    out = _run(px, monkeypatch)
    assert out["skew"] < 0, "a crash-shaped series must report negative skew"
    assert out["tail_ratio"] > 1.10, "left tail must register as fatter"


def test_a_right_skewed_series_is_not_called_a_crash(monkeypatch):
    """🚨 THE REGRESSION THAT MATTERS. SPY 2023-2026 has POSITIVE skew, so the
    panel must not print a crash premium. If this ever flips, the copy claiming
    'no crash premium in this sample' has silently become wrong."""
    px, v = [100.0], 100.0
    for i in range(400):
        v *= (1 + (-0.004 if i % 10 else 0.05))     # 10% of days are a big pop
        px.append(v)
    out = _run(px, monkeypatch)
    assert out["skew"] > 0
    assert out["tail_ratio"] < 1.10, "a right-skewed series must not read as left-tailed"
