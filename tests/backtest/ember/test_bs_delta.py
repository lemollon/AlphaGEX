# tests/backtest/ember/test_bs_delta.py
import math
from quant.bs import bs_delta


def test_atm_call_delta_near_half():
    # ATM, 30 days, 20% vol -> call delta a little above 0.5
    d = bs_delta(spot=100.0, strike=100.0, t_years=30 / 365, sigma=0.20, is_call=True)
    assert 0.50 < d < 0.60


def test_atm_put_delta_near_minus_half():
    d = bs_delta(spot=100.0, strike=100.0, t_years=30 / 365, sigma=0.20, is_call=False)
    assert -0.60 < d < -0.40


def test_put_call_delta_parity():
    # call_delta - put_delta == 1 (no dividends)
    c = bs_delta(100.0, 105.0, 30 / 365, 0.25, True)
    p = bs_delta(100.0, 105.0, 30 / 365, 0.25, False)
    assert math.isclose(c - p, 1.0, abs_tol=1e-9)


def test_expired_call_is_zero_or_one():
    assert bs_delta(110.0, 100.0, 0.0, 0.20, True) == 1.0   # ITM call at expiry
    assert bs_delta(90.0, 100.0, 0.0, 0.20, True) == 0.0    # OTM call at expiry


def test_deep_otm_short_put_delta_small():
    # 16-delta-ish region: a put ~5% OTM should have |delta| well under 0.5
    d = bs_delta(100.0, 95.0, 1 / 365, 0.18, False)
    assert -0.5 < d < 0.0
