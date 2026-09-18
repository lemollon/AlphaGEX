"""Unit tests for speculative contract scoring helpers."""
from backend import speculative_contracts as sc


def _contract(strike, delta, bid=1.0, ask=1.10, oi=500, volume=100, right="C"):
    return {
        "strike": strike,
        "delta": delta,
        "bid": bid,
        "ask": ask,
        "open_interest": oi,
        "volume": volume,
        "right": right,
        "iv": 0.40,
        "gamma": 0.01,
        "theta": -0.10,
        "vega": 0.08,
    }


def test_direction_maps_bullish_to_calls_and_bearish_to_puts():
    assert sc._direction({"direction": "long"}) == ("long", "C")
    assert sc._direction({"trade_bias": "short_breakdown"}) == ("short", "P")


def test_expected_move_reads_one_sigma_levels():
    result = sc._expected_move({
        "data": {"levels": [
            {"name": "plus_1s_1d", "price": 110},
            {"name": "minus_1s_1d", "price": 90},
        ]}
    })
    assert result["preferred_horizon"] == "1d"
    assert result["dollars"] == 10.0
    assert result["one_day"] == {"lower": 90.0, "upper": 110.0, "dollars": 10.0}


def test_choose_candidate_requires_otm_delta_and_liquidity():
    contracts = [
        _contract(105, 0.28, oi=1000, volume=500),
        _contract(110, 0.24, bid=0.50, ask=1.00, oi=1000, volume=500),
        _contract(103, 0.45, oi=1000, volume=500),
        _contract(106, 0.27, oi=10, volume=500),
    ]
    result = sc._choose_candidate(
        contracts,
        right="C",
        spot=100,
        band=(0.20, 0.35),
        opportunity_score=8.0,
        iv_rank=30,
        expected_move=8,
        today=__import__("datetime").date(2026, 9, 18),
    )
    assert result["strike"] == 105
    assert result["speculative_contract_score"] > 0
    assert result["relative_spread"] < 0.25


def test_gamma_expiration_context_identifies_dominant_bucket():
    result = sc._gamma_expiration_context({
        "data": {"points": [
            {"nearest": 10, "first_weekly": 20, "first_monthly": 2, "all_other_expiries": 1},
            {"nearest": -5, "first_weekly": 30, "first_monthly": 3, "all_other_expiries": 1},
        ]}
    })
    assert result["available"] is True
    assert result["dominant_bucket"] == "first_weekly"


def test_expected_move_prefers_one_week_market_structure():
    result = sc._expected_move(
        {"data": {"levels": [
            {"name": "plus_1s_1d", "price": 102},
            {"name": "minus_1s_1d", "price": 98},
        ]}},
        {"data": {"key_levels": {
            "plus_1sigma_1w": 108,
            "minus_1sigma_1w": 92,
        }}},
    )
    assert result["preferred_horizon"] == "1w"
    assert result["dollars"] == 8.0
    assert result["one_week"]["upper"] == 108.0
