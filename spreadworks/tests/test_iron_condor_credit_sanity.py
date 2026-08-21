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


@pytest.mark.parametrize("credit,pid", [
    (2.81, "flow-2026-08-18-d2e4ed9e"),   # 56% — the first one found
    (1.44, "flow-2026-08-12-58075fae"),   # 29% — flagged but under the old 40%
    (1.51, "flow-2026-08-21-7a00471b"),   # 30% — WALKED THROUGH the 40% ceiling
])
def test_every_known_phantom_is_rejected(credit, pid):
    """🚨 THE 40% CEILING WAS CALIBRATED TO THE WORST CASE AND MISSED TWO.
    Set from the 56% incident, it let a 29% and a 30% through — the 30% booked
    +$1,988 the session after the guard shipped. A threshold tuned to the
    loudest example is not a threshold."""
    assert frac(credit, 5.0) > MAX_CREDIT_FRAC_OF_WIDTH, pid


@pytest.mark.parametrize("credit,width", [
    (0.755, 5.0), (0.750, 5.0), (0.720, 5.0), (0.885, 5.0),
    (0.660, 5.0), (0.810, 5.0), (0.700, 5.0), (0.520, 5.0),
])
def test_every_legitimate_flow_fill_still_passes(credit, width):
    """⛔ THE GUARD MUST NOT COST A REAL TRADE. These are the actual credits
    from every other FLOW fill in the sample — 13-18% of width. A ceiling that
    rejected any of them would be worse than the bug."""
    assert frac(credit, width) <= MAX_CREDIT_FRAC_OF_WIDTH


def test_the_ceiling_separates_the_two_observed_populations():
    """🚨 SET FROM BOTH POPULATIONS, NOT FROM THE LOUDEST EXAMPLE. The first
    version was tuned to the 56% incident and a 30% walked straight through it
    the very next session. Measured:

        8 clean fills : 10.4% - 17.7%
        3 phantoms    : 28.8%, 30.2%, 56.2%

    The threshold must sit inside that gap, and nearer the clean side —
    rejecting a real trade costs an opportunity on a marginal paper bot;
    accepting a phantom corrupts the ledger, which is what this protects."""
    worst_real, nearest_bad = 0.885 / 5.0, 1.44 / 5.0
    assert worst_real < MAX_CREDIT_FRAC_OF_WIDTH < nearest_bad
    assert MAX_CREDIT_FRAC_OF_WIDTH - worst_real >= 0.03, "too close to real fills"
    assert nearest_bad - MAX_CREDIT_FRAC_OF_WIDTH >= 0.03, "too close to a phantom"


def test_the_old_bound_would_not_have_caught_it():
    """Proves the new check is load-bearing rather than decorative: the only
    previous ceiling was credit < wing_width."""
    assert 2.81 < 5.0, "the old rule passed this trade"
    assert frac(2.81, 5.0) > MAX_CREDIT_FRAC_OF_WIDTH, "the new rule catches it"


def test_the_opening_auction_is_skipped_entirely():
    """⛔ THE CEILING FILTERS THE SYMPTOM; THIS REMOVES THE CAUSE. All three
    phantom fills entered at exactly 13:30:00 UTC — the first scan of the
    session, on the opening auction print. No legitimate FLOW fill has ever
    come from that scan."""
    from datetime import datetime as _dt

    from backend.bots.strategies.iron_condor import (OPENING_BELL_SKIP_MIN,
                                                     build_iron_condor_signal)
    diag = []
    out = build_iron_condor_signal(
        chain={"spot": 766.0, "vix": 17.0}, config={}, equity=10_000.0,
        diag=diag, now_ct=_dt(2026, 8, 21, 8, 30))
    assert out is None
    assert diag and "opening_auction" in diag[0]
    assert OPENING_BELL_SKIP_MIN >= 3


def test_the_gate_reopens_after_the_skip_window():
    """It must not swallow the whole session — only the auction."""
    from datetime import datetime as _dt

    from backend.bots.strategies.iron_condor import (OPENING_BELL_SKIP_MIN,
                                                     build_iron_condor_signal)
    diag = []
    later = _dt(2026, 8, 21, 8, 30 + OPENING_BELL_SKIP_MIN)
    build_iron_condor_signal(chain={"spot": 766.0, "vix": 17.0}, config={},
                             equity=10_000.0, diag=diag, now_ct=later)
    assert not any("opening_auction" in d for d in diag)


def test_omitting_the_clock_leaves_behaviour_unchanged():
    """Preview and backtest callers pass no time; they must not be gated."""
    from backend.bots.strategies.iron_condor import build_iron_condor_signal
    diag = []
    build_iron_condor_signal(chain={"spot": 766.0, "vix": 17.0}, config={},
                             equity=10_000.0, diag=diag)
    assert not any("opening_auction" in d for d in diag)
