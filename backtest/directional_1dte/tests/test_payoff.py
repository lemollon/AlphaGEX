import pytest
from backtest.directional_1dte.payoff import compute_payoff


class TestBullCall:
    """Bull call spread: long ATM call, short OTM call."""

    def test_full_payoff_above_short_strike(self):
        # Long 500, short 502, spot at 510 -> max payoff = width = 2
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 510.0) == 2.0

    def test_zero_payoff_below_long_strike(self):
        # Long 500, short 502, spot at 495 -> 0
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 495.0) == 0.0

    def test_partial_payoff_between_strikes(self):
        # Long 500, short 502, spot at 501 -> 1.0
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 501.0) == 1.0

    def test_payoff_at_long_strike(self):
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 500.0) == 0.0

    def test_payoff_at_short_strike(self):
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 502.0) == 2.0


class TestBearPut:
    """Bear put spread: long ATM put, short OTM put."""

    def test_full_payoff_below_short_strike(self):
        # Long 500, short 498, spot at 490 -> max payoff = 2
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 490.0) == 2.0

    def test_zero_payoff_above_long_strike(self):
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 505.0) == 0.0

    def test_partial_payoff_between_strikes(self):
        # Long 500, short 498, spot at 499 -> 1.0
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 499.0) == 1.0


def test_payoff_bounded_by_width():
    # Way above
    assert compute_payoff("BULL_CALL", 500.0, 502.0, 999.0) == 2.0
    # Way below
    assert compute_payoff("BEAR_PUT", 500.0, 498.0, 0.0) == 2.0


def test_unknown_spread_type_raises():
    with pytest.raises(ValueError, match="Unknown spread_type"):
        compute_payoff("UNKNOWN", 500.0, 502.0, 501.0)
