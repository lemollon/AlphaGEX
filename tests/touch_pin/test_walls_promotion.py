"""Smoke check for promoted quant.walls module."""
import inspect
import pytest

from quant.walls import StrikeGamma, Walls, compute_intraday_walls


def test_dataclasses_importable():
    sg = StrikeGamma(strike=500.0, call_gamma_oi=1.0, put_gamma_oi=0.5, net_gamma=0.5)
    assert sg.net_gamma == pytest.approx(0.5)


def test_compute_walls_callable_signature():
    sig = inspect.signature(compute_intraday_walls)
    params = list(sig.parameters.keys())
    assert "db_url" in params
    assert "trade_date" in params
    assert "expiration_date" in params
    assert "target_minute" in params
    assert "t_years_at_open" in params
