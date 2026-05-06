import datetime as dt
import pandas as pd
import pytest
from backtest.directional_1dte.pricing import select_strikes, lookup_debit


class TestSelectStrikes:
    def test_bullish_atm_long_otm_call_short(self):
        long_k, short_k = select_strikes(spot=500.4, direction="BULLISH", width=2)
        assert long_k == 500.0
        assert short_k == 502.0

    def test_bearish_atm_long_otm_put_short(self):
        long_k, short_k = select_strikes(spot=500.4, direction="BEARISH", width=2)
        assert long_k == 500.0
        assert short_k == 498.0

    def test_atm_rounds_half_up(self):
        long_k, _ = select_strikes(spot=500.5, direction="BULLISH", width=2)
        assert long_k in (500.0, 501.0)  # banker's rounding ok either way

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError):
            select_strikes(500.0, "SIDEWAYS", 2)


@pytest.fixture
def synthetic_chain():
    """Chain indexed (expiration_date, strike) with 4 strikes around 500."""
    exp = dt.date(2024, 3, 15)
    rows = [
        # strike, call_bid, call_ask, call_mid, put_bid, put_ask, put_mid
        (498.0, 3.10, 3.20, 3.15, 0.50, 0.55, 0.52),
        (500.0, 1.80, 1.90, 1.85, 1.20, 1.30, 1.25),
        (502.0, 0.90, 1.00, 0.95, 2.40, 2.50, 2.45),
        (504.0, 0.40, 0.50, 0.45, 4.10, 4.20, 4.15),
    ]
    df = pd.DataFrame(
        [(exp, s, cb, ca, cm, pb, pa, pm) for s, cb, ca, cm, pb, pa, pm in rows],
        columns=["expiration_date", "strike", "call_bid", "call_ask", "call_mid",
                 "put_bid", "put_ask", "put_mid"],
    ).set_index(["expiration_date", "strike"])
    return df, exp


class TestLookupDebit:
    def test_bull_call_debit_is_long_call_mid_minus_short_call_mid(self, synthetic_chain):
        chain, exp = synthetic_chain
        result = lookup_debit(chain, exp, long_strike=500.0, short_strike=502.0,
                              spread_type="BULL_CALL")
        assert result is not None
        assert result["debit"] == pytest.approx(1.85 - 0.95)
        assert result["long_mid"] == 1.85
        assert result["short_mid"] == 0.95

    def test_bear_put_debit_is_long_put_mid_minus_short_put_mid(self, synthetic_chain):
        chain, exp = synthetic_chain
        result = lookup_debit(chain, exp, long_strike=500.0, short_strike=498.0,
                              spread_type="BEAR_PUT")
        assert result is not None
        assert result["debit"] == pytest.approx(1.25 - 0.52)

    def test_returns_none_when_long_strike_missing(self, synthetic_chain):
        chain, exp = synthetic_chain
        assert lookup_debit(chain, exp, 7777.0, 502.0, "BULL_CALL") is None

    def test_returns_none_when_short_strike_missing(self, synthetic_chain):
        chain, exp = synthetic_chain
        assert lookup_debit(chain, exp, 500.0, 9999.0, "BULL_CALL") is None

    def test_returns_none_when_bid_greater_than_ask(self, synthetic_chain):
        chain, exp = synthetic_chain
        # Corrupt one row
        chain.loc[(exp, 500.0), "call_bid"] = 5.0
        chain.loc[(exp, 500.0), "call_ask"] = 1.0
        assert lookup_debit(chain, exp, 500.0, 502.0, "BULL_CALL") is None
