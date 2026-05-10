"""Tests for backtest.touch_pin.vehicle."""
import pytest

from backtest.touch_pin.loader import ChainEntry
from backtest.touch_pin.vehicle import build_verticals, VerticalSpec


def make_chain(specs):
    """Helper: list of (strike, c_bid, c_ask, p_bid, p_ask) → dict."""
    return {s[0]: ChainEntry(
        strike=s[0], call_bid=s[1], call_ask=s[2],
        put_bid=s[3], put_ask=s[4],
    ) for s in specs}


def test_pin_call_vertical_basic():
    chain = make_chain([
        (530, 5.00, 5.05, 0.05, 0.07),
        (533, 2.00, 2.05, 1.00, 1.05),
        (535, 0.10, 0.12, 5.00, 5.05),
        (536, 0.05, 0.07, 5.95, 6.00),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    pin_call, pin_put = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_call is not None
    assert pin_call.long_K == 535.0
    assert pin_call.short_K == 536.0
    assert pin_call.entry_mid == pytest.approx(0.11 - 0.06, rel=1e-3)
    assert pin_call.width == 1.0
    assert pin_call.side == "PIN-CALL"


def test_pin_put_vertical_basic():
    chain = make_chain([
        (529, 8.00, 8.05, 0.02, 0.04),
        (530, 5.00, 5.05, 0.05, 0.07),
        (533, 2.00, 2.05, 1.00, 1.05),
        (535, 0.10, 0.12, 5.00, 5.05),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    _, pin_put = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_put is not None
    assert pin_put.long_K == 530.0
    assert pin_put.short_K == 529.0
    assert pin_put.entry_mid == pytest.approx(0.06 - 0.03, rel=1e-3)
    assert pin_put.side == "PIN-PUT"


def test_skip_when_zero_quotes():
    chain = make_chain([
        (535, 0.0, 0.05, 0.02, 0.04),
        (536, 0.05, 0.07, 0.00, 0.04),
    ])
    walls = {"call_wall": 535.0, "put_support": 533.0}
    pin_call, _ = build_verticals(chain, walls, spot=534.0, strike_step=1.0)
    assert pin_call is None


def test_skip_when_short_strike_missing():
    chain = make_chain([
        (535, 0.10, 0.12, 5.00, 5.05),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    pin_call, _ = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_call is None


def test_skip_when_negative_debit():
    # Inverted vertical (long worth less than short) — skip
    chain = make_chain([
        (535, 0.05, 0.07, 5.00, 5.05),
        (536, 0.10, 0.12, 5.95, 6.00),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    pin_call, _ = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_call is None
