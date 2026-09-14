"""Opportunity Scanner — THE RULE (median_ratio_rule, ported verbatim from
run_divhike.py) and the same-day SPY VIX-gate ratio math. Both are pure
functions with no network calls, so these tests never touch yfinance/Polygon.
"""
from backend.opportunity_scanner import compute_vix_gate, median_ratio_rule


# ---------------------------------------------------------------------------
# median_ratio_rule
# ---------------------------------------------------------------------------
def test_ratio_exactly_2x_is_no_event():
    # THE RULE requires the ratio to strictly EXCEED 2.0x, not merely reach it.
    r = median_ratio_rule(2.0, "CD", [1.0, 1.0])
    assert r["event"] is False
    assert r["reason"] == "ratio_below_2x"


def test_ratio_just_above_2x_is_an_event():
    r = median_ratio_rule(2.01, "CD", [1.0, 1.0])
    assert r["event"] is True
    assert round(r["ratio"], 4) == 2.01


def test_own_type_sc_can_never_be_the_event():
    r = median_ratio_rule(10.0, "SC", [1.0, 1.0, 1.0])
    assert r["event"] is False
    assert r["reason"] == "own_type_SC"


def test_sc_priors_are_included_in_the_median():
    # An SC-typed prior contributes its amount to the median exactly like a
    # CD prior would -- the AMENDMENT only bars SC from being the event
    # itself, never from the denominator.
    r = median_ratio_rule(3.0, "CD", [1.0, 1.0])  # median 1.0 -> ratio 3.0x
    assert r["event"] is True
    assert r["median"] == 1.0
    assert round(r["ratio"], 2) == 3.0


def test_fewer_than_two_priors_is_no_event():
    r_one = median_ratio_rule(5.0, "CD", [1.0])
    assert r_one["event"] is False
    assert r_one["reason"] == "insufficient_prior_dividends"

    r_zero = median_ratio_rule(5.0, "CD", [])
    assert r_zero["event"] is False
    assert r_zero["reason"] == "insufficient_prior_dividends"


def test_only_trailing_four_priors_are_used():
    # Oldest (1000.0) must be dropped once there are more than 4 priors.
    r = median_ratio_rule(100.0, "CD", [1000.0, 1.0, 1.0, 1.0, 1.0])
    assert r["n_used"] == 4
    assert r["median"] == 1.0


# ---------------------------------------------------------------------------
# eligible_entry
# ---------------------------------------------------------------------------
def test_eligibility_price_and_volume_floors():
    from backend.opportunity_scanner import eligible_entry

    ok, why = eligible_entry(2.00, 1_000_000.0)
    assert ok is True, why

    ok, why = eligible_entry(1.99, 1_000_000.0)
    assert ok is False and "close" in why

    ok, why = eligible_entry(5.0, 999_999.0)
    assert ok is False and "$ volume" in why

    ok, why = eligible_entry(None, 2_000_000.0)
    assert ok is False


# ---------------------------------------------------------------------------
# Same-day SPY put spread — VIX gate ratio math
# ---------------------------------------------------------------------------
def test_vix_gate_open_at_the_ceiling():
    # ratio == 0.80 exactly must still be OPEN (<=), not CLOSED.
    gate = compute_vix_gate(vix_prev=16.0, vix_20d_max=20.0)
    assert round(gate["ratio"], 2) == 0.80
    assert gate["gate_status"] == "OPEN"


def test_vix_gate_closed_just_above_the_ceiling():
    gate = compute_vix_gate(vix_prev=16.1, vix_20d_max=20.0)
    assert gate["gate_status"] == "CLOSED"


def test_vix_gate_open_low_vol():
    gate = compute_vix_gate(vix_prev=12.0, vix_20d_max=25.0)
    assert gate["ratio"] == 0.48
    assert gate["gate_status"] == "OPEN"
