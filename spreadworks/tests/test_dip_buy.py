"""UNDERTOW dip-buy strategy + indicator tests."""
from __future__ import annotations

from datetime import date

from backend.bots.strategies.dip_buy import (
    closed_bars, rsi, sma,
)


def _bar(d: str, high: float, close: float) -> dict:
    return {"date": d, "open": close, "high": high, "low": close, "close": close}


def test_closed_bars_drops_todays_partial_and_sorts():
    hist = [
        _bar("2026-06-10", 105, 104),  # today — partial, must be dropped
        _bar("2026-06-08", 101, 100),
        _bar("2026-06-09", 103, 102),
    ]
    bars = closed_bars(hist, date(2026, 6, 10))
    assert [b["date"] for b in bars] == ["2026-06-08", "2026-06-09"]


def test_sma_simple_average_of_last_period():
    assert sma([10, 20, 30, 40], 2) == 35.0
    assert sma([10, 20, 30, 40], 4) == 25.0


def test_sma_insufficient_returns_none():
    assert sma([10, 20], 5) is None


def test_rsi_all_gains_is_100():
    # strictly rising closes -> no losses -> RSI 100
    assert rsi([1, 2, 3, 4, 5], 2) == 100.0


def test_rsi_all_losses_is_zero():
    assert rsi([5, 4, 3, 2, 1], 2) == 0.0


def test_rsi_insufficient_returns_none():
    assert rsi([5], 2) is None


from backend.bots.strategies.dip_buy import build_dip_buy_signal, DEFAULT_PARAMS


def _uptrend_history() -> list[dict]:
    """40 closed daily bars: 36 rising closes (101..136) to seat SMA(20),
    a spike high to 150, then 3 DOWN days into a pullback so RSI(2) reads
    oversold (last closes 143 -> 141 -> 140). SMA(20) ~= 131, well below the
    150 reference high, so a dip to ~140 is a real pullback inside an uptrend.
    """
    from datetime import timedelta
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        price = 101 + i
        d = base + timedelta(days=i)
        bars.append({"date": d.isoformat(), "open": price, "high": price,
                     "low": price, "close": price})
    bars.append({"date": (base + timedelta(days=36)).isoformat(),
                 "open": 144, "high": 150, "low": 143, "close": 145})
    bars.append({"date": (base + timedelta(days=37)).isoformat(),
                 "open": 145, "high": 146, "low": 142, "close": 143})
    bars.append({"date": (base + timedelta(days=38)).isoformat(),
                 "open": 143, "high": 143, "low": 140, "close": 141})
    bars.append({"date": (base + timedelta(days=39)).isoformat(),
                 "open": 141, "high": 141, "low": 139, "close": 140})
    return bars


def _chain(spot=140.0, strikes=range(120, 161, 5), bid=4.8, ask=5.2):
    opts = []
    for s in strikes:
        opts.append({"strike": s, "type": "call", "bid": bid, "ask": ask})
        opts.append({"strike": s, "type": "put", "bid": bid, "ask": ask})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": "NVDA",
            "options": opts}


def _params(**over):
    p = dict(DEFAULT_PARAMS)
    p.update(over)
    return p


def test_qualifying_dip_builds_atm_call_signal():
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
    )
    assert sig is not None
    assert sig.ticker == "NVDA"
    legs = sig.legs()
    assert len(legs) == 1
    assert legs[0]["side"] == "long" and legs[0]["type"] == "call"
    assert legs[0]["strike"] == 140  # ATM (nearest to spot 140)
    assert sig.debit == 5.0          # mid of 4.8/5.2
    # sizing: floor(25000*0.02 / (5.0*100)) = floor(500/500) = 1
    assert sig.contracts == 1
    assert sig.max_loss == 500.0     # full premium
    assert sig.pt_target_pnl == 0.40 * 500.0   # +40% of premium
    assert sig.sl_target_pnl == 0.50 * 500.0   # -50% of premium
    assert not hasattr(sig, "credit")


def test_shallow_dip_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=149.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "dip_too_shallow" in diag[0]


def test_downtrend_rejected_by_sma_gate():
    diag = []
    # spot below SMA(20): use a low spot that is still a "dip" but below trend
    sig = build_dip_buy_signal(
        chain=_chain(spot=110.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "below_sma_downtrend" in diag[0]


def test_wide_spread_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0, bid=4.0, ask=6.0),  # spread 2.0 / mid 5.0 = 40%
        history=_uptrend_history(), today=date(2026, 6, 10),
        params=_params(use_rsi_confirm=False), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "spread_too_wide" in diag[0]


def test_sizing_below_one_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0, bid=49.8, ask=50.2),  # $50 option -> $5000/ct
        history=_uptrend_history(), today=date(2026, 6, 10),
        params=_params(use_rsi_confirm=False), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "sizing_below_one" in diag[0]


def _recovering_history():
    """Reference high of 150 in the last 5 bars, but the most recent closes
    are RISING (140 -> 142 -> 143) so RSI(2) reads ~100 (NOT oversold), while
    price still sits >3% below the 150 high. Isolates the rsi_not_oversold gate.
    """
    from datetime import timedelta
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        price = 101 + i
        d = base + timedelta(days=i)
        bars.append({"date": d.isoformat(), "open": price, "high": price,
                     "low": price, "close": price})
    bars.append({"date": (base + timedelta(days=36)).isoformat(),
                 "open": 139, "high": 150, "low": 138, "close": 138})
    bars.append({"date": (base + timedelta(days=37)).isoformat(),
                 "open": 139, "high": 141, "low": 138, "close": 140})
    bars.append({"date": (base + timedelta(days=38)).isoformat(),
                 "open": 141, "high": 143, "low": 140, "close": 142})
    bars.append({"date": (base + timedelta(days=39)).isoformat(),
                 "open": 142, "high": 144, "low": 141, "close": 143})
    return bars


def test_rsi_not_oversold_rejected():
    diag = []
    # spot 144: dip vs 150 high = 4% (passes dip gate), but recent closes are
    # rising so RSI(2) ~ 100 -> rsi_not_oversold fires before the trend gate.
    sig = build_dip_buy_signal(
        chain=_chain(spot=144.0), history=_recovering_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "rsi_not_oversold" in diag[0]


def test_price_too_low_rejected():
    diag = []
    # qualifying dip/RSI/trend, but the ATM call mid is $0.10 < min_option_price 0.20
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0, bid=0.10, ask=0.10), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "price_too_low" in diag[0]
