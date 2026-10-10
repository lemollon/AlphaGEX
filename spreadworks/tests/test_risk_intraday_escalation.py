"""/risk must be able to change its mind during the session — and must not
change it for the wrong reasons.

🚨 THE BUG THIS PINS. `action` was computed once from prior closes plus the
single 10:00 CT snapshot and then frozen. The 12:00 and 13:30 re-checks and the
*/10 rolling watcher fired Discord alerts all afternoon and could never move the
page: a 13:30 spike pushed a phone alert while /risk still read NORMAL.

⛔ THE FIRST VERSION OF THIS FILE WAS NOT A TEST SUITE. It parsed the source and
asserted the code *mentioned* `intraday_flags`. That passes on wrong behaviour
and fails on a rename — the worst of both. The logic is now a pure function and
these call it with real inputs.
"""
import pytest

from backend.routes_risk import intraday_escalation

QUIET = {"backwardation": False, "flag_vix1d": False}
SPIKE = {"spike": True}
NOSPIKE = {"spike": False}
UNCAPTURED = {"spike": None}          # before the clock's window lands


def esc(flow=None, pm=None, roll=None, **kw):
    return intraday_escalation(flow, pm, roll, **{**QUIET, **kw})


# ── nothing fired ────────────────────────────────────────────────────────────

def test_a_quiet_day_escalates_nothing():
    assert esc(NOSPIKE, {"12:00": NOSPIKE, "13:30": NOSPIKE}, {"fired_today": False}) == ([], None)


@pytest.mark.parametrize("flow,pm,roll", [
    (None, None, None),
    ({}, {}, {}),
    (NOSPIKE, None, None),
    (None, {"12:00": None}, None),          # entry present but null
    (None, {}, {"fired_today": None}),
])
def test_missing_or_null_inputs_never_crash_and_never_escalate(flow, pm, roll):
    """⛔ Every one of these is a real state: pre-market, a failed capture, a
    weekend, a DB read that returned nothing. None may escalate, and none may
    raise — this function decides whether the page says stand down."""
    assert esc(flow, pm, roll) == ([], None)


def test_an_uncaptured_clock_has_not_fired():
    """`spike` is None until the clock's window lands. Falsy is correct: an
    uncaptured clock is not a quiet clock, but it is certainly not a firing."""
    assert esc(NOSPIKE, {"12:00": UNCAPTURED, "13:30": UNCAPTURED},
               {"fired_today": False}) == ([], None)


# ── something fired ──────────────────────────────────────────────────────────

def test_a_pm_clock_alone_escalates_and_is_named():
    flags, by = esc(NOSPIKE, {"12:00": SPIKE, "13:30": NOSPIKE}, {"fired_today": False})
    assert flags == ["12:00"]
    assert by == ["12:00"], "a quiet-open day escalated by 12:00 must say so"


def test_the_rolling_watcher_alone_escalates():
    flags, by = esc(NOSPIKE, {"12:00": NOSPIKE}, {"fired_today": True})
    assert flags == ["rolling"] and by == ["rolling"]


def test_both_clocks_and_the_watcher_are_all_listed():
    flags, by = esc(NOSPIKE, {"12:00": SPIKE, "13:30": SPIKE}, {"fired_today": True})
    assert flags == ["12:00", "13:30", "rolling"] and by == flags


def test_flag_order_is_stable_regardless_of_dict_order():
    """A headline that reads '13:30, 12:00' on one request and '12:00, 13:30'
    on the next looks like the verdict moved when nothing did."""
    a, _ = esc(NOSPIKE, {"13:30": SPIKE, "12:00": SPIKE}, {"fired_today": False})
    b, _ = esc(NOSPIKE, {"12:00": SPIKE, "13:30": SPIKE}, {"fired_today": False})
    assert a == b == ["12:00", "13:30"]


# ── the guard: don't relabel a day that already opened risk-off ──────────────

@pytest.mark.parametrize("kw", [
    {"backwardation": True},
    {"flag_vix1d": True},
    {"backwardation": True, "flag_vix1d": True},
])
def test_a_day_already_riskoff_from_the_close_is_not_relabelled(kw):
    """⛔ The flags still show — the reader should see the clock fired — but
    `escalated_by` stays None, because the verdict did not change today. Saying
    'escalated intraday' about a standing call is a lie about what happened."""
    flags, by = esc(NOSPIKE, {"12:00": SPIKE}, {"fired_today": True}, **kw)
    assert flags == ["12:00", "rolling"]
    assert by is None


def test_a_1000_spike_also_suppresses_the_escalation_label():
    """The 10:00 snapshot is itself a prior leg of the same verdict. If it
    already fired, an afternoon clock is confirmation, not escalation."""
    flags, by = esc(SPIKE, {"13:30": SPIKE}, {"fired_today": False})
    assert flags == ["13:30"] and by is None


# ── the invariant that matters most ──────────────────────────────────────────

@pytest.mark.parametrize("pm,roll", [
    ({"12:00": SPIKE}, {"fired_today": False}),
    ({}, {"fired_today": True}),
    ({"12:00": SPIKE, "13:30": SPIKE}, {"fired_today": True}),
])
def test_escalation_can_only_add_risk_never_remove_it(pm, roll):
    """RATCHET. risk_off is an OR, so firing a clock can only push the verdict
    toward caution. A page that reads RISK-OFF at 12:06 and NORMAL at 12:16 is
    worse than one that never moved — the alert has already gone out."""
    quiet_flags, _ = esc(NOSPIKE, {}, {"fired_today": False})
    fired_flags, _ = esc(NOSPIKE, pm, roll)
    assert quiet_flags == []
    assert len(fired_flags) > 0, "firing a clock must never produce fewer flags"


def test_adding_a_clock_never_shrinks_the_flag_list():
    one, _ = esc(NOSPIKE, {"12:00": SPIKE, "13:30": NOSPIKE}, {"fired_today": False})
    two, _ = esc(NOSPIKE, {"12:00": SPIKE, "13:30": SPIKE}, {"fired_today": False})
    assert set(one).issubset(set(two)) and len(two) > len(one)
