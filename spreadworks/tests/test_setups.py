"""Shared dip/rip setup detection tests."""
from __future__ import annotations
from datetime import date, timedelta
from backend.bots.strategies.setups import detect_setup, DEFAULT_SETUP_PARAMS


def _hist(closes_highs_lows):
    bars, base = [], date(2026, 4, 1)
    for i, (c, h, l) in enumerate(closes_highs_lows):
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": c, "high": h, "low": l, "close": c})
    return bars


def _dip_history():
    # 35-bar uptrend (101→135) then 5 tight pullback bars near the 150 peak.
    # All last-5 lows ≥ 144, so a spot of 147 lands in the shallow no-signal zone.
    # RSI(2) = 0 (all closes declining in the pullback) → oversold ✓
    # SMA(20) ≈ 132 → spot=140 is above it → uptrend gate passes ✓
    rows = [(101 + i, 101 + i, 101 + i) for i in range(35)]
    rows += [(149, 150, 147), (148, 149, 146), (147, 148, 146), (146, 147, 145), (144, 146, 144)]
    return _hist(rows)


def _rip_history():
    # 40-bar downtrend (160→121) then 5 bounce bars recovering from ~95 to ~110.
    # RSI(2) = 100 (two big up closes) → overbought ✓
    # SMA(20) ≈ 121 → spot=110 is below it → downtrend gate passes ✓
    # ref_high of last-5 = 111 → dip_pct = (111-110)/111 ≈ 0.9% < 3% → dip skipped ✓
    rows = [(160 - i, 160 - i, 160 - i) for i in range(40)]
    rows += [(95, 96, 94), (96, 97, 95), (97, 98, 96), (105, 106, 104), (110, 111, 109)]
    return _hist(rows)


def _p(**o):
    p = dict(DEFAULT_SETUP_PARAMS); p.update(o); return p


def test_bullish_dip_detected():
    s = detect_setup(spot=140.0, history=_dip_history(), today=date(2026, 6, 10), params=_p())
    assert s is not None and s.direction == "bullish" and s.setup == "dip"
    assert s.magnitude_pct >= 0.03 and s.reference_level == 150.0


def test_bearish_rip_detected():
    s = detect_setup(spot=110.0, history=_rip_history(), today=date(2026, 6, 10), params=_p())
    assert s is not None and s.direction == "bearish" and s.setup == "rip"
    assert s.magnitude_pct >= 0.03 and s.reference_level == 94.0


def test_no_setup_when_shallow():
    diag = []
    # spot=147 sits between ref_high=150 and ref_low=144: both dip_pct (~2%) and
    # rip_pct (~2%) are below the 3% threshold → no_setup
    s = detect_setup(spot=147.0, history=_dip_history(), today=date(2026, 6, 10),
                     params=_p(), diag=diag)
    assert s is None and "no_setup" in diag[0]
