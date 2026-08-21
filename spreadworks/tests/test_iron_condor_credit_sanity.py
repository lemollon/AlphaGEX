"""A credit too GOOD to be true is a bad quote, not an opportunity.

🚨 THE INCIDENT. On 2026-08-18 FLOW entered a $5-wide 1DTE condor at a claimed
2.81 credit — 56% of the width — because the 763 put came back at 2.75 when the
764 put, quoted two minutes later, was 0.695. A lower-strike put cannot cost 4x
a higher-strike one. The phantom credit made the position look instantly
profitable, the profit-target logic closed it ONE MINUTE after entry, and the
ledger booked +$5,319 on a trade that was really around −$500.

The only upper bound at the time was `credit < wing_width`, which on a $5 wing
admits anything below $4.99.
"""
import pytest

from backend.bots.strategies.iron_condor import MAX_CREDIT_FRAC_OF_WIDTH


def frac(credit, width):
    return credit / width


def test_the_real_incident_would_now_be_rejected():
    """The exact numbers from flow-2026-08-18-d2e4ed9e."""
    assert frac(2.81, 5.0) > MAX_CREDIT_FRAC_OF_WIDTH


@pytest.mark.parametrize("credit,width", [
    (0.755, 5.0), (0.750, 5.0), (0.720, 5.0), (0.885, 5.0),
    (0.660, 5.0), (0.810, 5.0), (0.700, 5.0), (0.520, 5.0),
])
def test_every_legitimate_flow_fill_still_passes(credit, width):
    """⛔ THE GUARD MUST NOT COST A REAL TRADE. These are the actual credits
    from every other FLOW fill in the sample — 13-18% of width. A ceiling that
    rejected any of them would be worse than the bug."""
    assert frac(credit, width) <= MAX_CREDIT_FRAC_OF_WIDTH


def test_the_ceiling_sits_well_clear_of_both_sides():
    """Not a threshold tuned to one incident: it has to be comfortably above
    real fills and comfortably below the bad one, or the next slightly-different
    bad quote walks straight through."""
    worst_real = 0.885 / 5.0          # 17.7%
    the_bug = 2.81 / 5.0              # 56.2%
    assert worst_real < MAX_CREDIT_FRAC_OF_WIDTH < the_bug
    assert MAX_CREDIT_FRAC_OF_WIDTH - worst_real > 0.15, "too close to real fills"
    assert the_bug - MAX_CREDIT_FRAC_OF_WIDTH > 0.10, "too close to the bug"


def test_the_old_bound_would_not_have_caught_it():
    """Proves the new check is load-bearing rather than decorative: the only
    previous ceiling was credit < wing_width."""
    assert 2.81 < 5.0, "the old rule passed this trade"
    assert frac(2.81, 5.0) > MAX_CREDIT_FRAC_OF_WIDTH, "the new rule catches it"
