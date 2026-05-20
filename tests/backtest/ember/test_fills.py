# tests/backtest/ember/test_fills.py
import math
import pytest
from backtest.ember.models import Quote, Leg
from backtest.ember.fills import (
    leg_price, signed_cashflow, commission,
    FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP, COMMISSION_PER_LEG,
)

# A short put credit spread: sell 95P, buy 90P
LEGS = [Leg(95.0, "P", -1), Leg(90.0, "P", 1)]
QUOTES = {
    (95.0, "P"): Quote(bid=1.00, ask=1.20, close=1.10),  # short leg
    (90.0, "P"): Quote(bid=0.40, ask=0.55, close=0.48),  # long leg
}


def test_leg_price_buy_vs_sell_ask_cross():
    q = QUOTES[(95.0, "P")]
    assert leg_price(q, buying=True, fill=FILL_ASK_CROSS) == 1.20   # pay ask
    assert leg_price(q, buying=False, fill=FILL_ASK_CROSS) == 1.00  # receive bid


def test_open_credit_ask_cross_is_conservative():
    # OPEN: sell 95P at bid (+1.00), buy 90P at ask (-0.55) -> credit 0.45
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_ASK_CROSS)
    assert math.isclose(cf, 0.45, abs_tol=1e-9)


def test_close_cost_ask_cross_is_conservative():
    # CLOSE: buy back 95P at ask (-1.20), sell 90P at bid (+0.40) -> -0.80
    cf = signed_cashflow(LEGS, QUOTES, action="close", fill=FILL_ASK_CROSS)
    assert math.isclose(cf, -0.80, abs_tol=1e-9)


def test_mid_open_credit():
    # mids: 95P=1.10, 90P=0.475 -> open credit = 1.10 - 0.475 = 0.625
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_MID)
    assert math.isclose(cf, 0.625, abs_tol=1e-9)


def test_mid_slip_penalizes_both_sides():
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_MID_SLIP, slippage=0.03)
    # sell 95P at 1.10-0.03=1.07, buy 90P at 0.475+0.03=0.505 -> 0.565
    assert math.isclose(cf, 0.565, abs_tol=1e-9)


def test_commission_four_legs_open_and_close():
    legs4 = LEGS + [Leg(105.0, "C", -1), Leg(110.0, "C", 1)]
    assert commission(legs4, contracts=1) == COMMISSION_PER_LEG * 4 * 2
    assert commission(legs4, contracts=3) == COMMISSION_PER_LEG * 4 * 2 * 3


def test_unknown_fill_raises():
    with pytest.raises(ValueError):
        leg_price(QUOTES[(90.0, "P")], buying=True, fill="bogus")
