"""The call log and its scoring.

These are about the two things that make a history worth keeping: that it
records what was ACTUALLY SHOWN rather than what today's code would say, and
that the numbers attached to it cannot flatter a signal.
"""

from datetime import datetime

import pytest

from backend.call_scoring import attach_outcomes, disagreements, score

SPY = {
    "2026-08-17": {"open": 100.0, "close": 100.5, "prev_close": 100.0,
                   "next_open": 100.6},
    "2026-08-18": {"open": 100.6, "close": 102.0, "prev_close": 100.5,
                   "next_open": 101.0},
    "2026-08-19": {"open": 101.0, "close": 101.0, "prev_close": 102.0,
                   "next_open": None},
}


def _call(i, surface, d, hh, verdict):
    return {"id": i, "surface": surface, "trade_date": d,
            "call_ts": f"{d}T{hh:02d}:00", "verdict": verdict}


# --- outcomes ----------------------------------------------------------------

def test_the_days_move_is_close_over_previous_close():
    """"SPY that day" is the number Leron reads off the row."""
    out = attach_outcomes([_call(1, "risk", "2026-08-18", 9, "normal")], SPY)
    assert out[0]["spy_day_pct"] == pytest.approx((102.0 / 100.5 - 1) * 100, abs=1e-6)
    assert out[0]["spy_close"] == 102.0


def test_the_overnight_gap_is_close_to_the_NEXT_open():
    out = attach_outcomes([_call(1, "risk", "2026-08-18", 14, "normal")], SPY)
    assert out[0]["spy_next_open"] == 101.0
    assert out[0]["spy_overnight_pct"] == pytest.approx((101.0 / 102.0 - 1) * 100,
                                                        abs=1e-6)


def test_the_next_open_is_the_next_SESSION_not_the_next_calendar_day():
    """🚨 Walking the stored bars gives this for free; calendar arithmetic
    would score a Friday call against a market holiday."""
    out = attach_outcomes([_call(1, "risk", "2026-08-19", 9, "normal")], SPY)
    assert out[0]["spy_next_open"] is None      # nothing after the last bar
    assert out[0]["spy_overnight_pct"] is None


def test_a_missing_bar_never_raises():
    out = attach_outcomes([_call(1, "risk", "1999-01-04", 9, "normal")], SPY)
    assert out[0]["spy_day_pct"] is None


# --- multiple calls in one day -----------------------------------------------

def test_every_call_is_kept_including_same_day_changes():
    """🚨 The whole point of the ask. `risk_confirm_state` is keyed on the date
    alone, so a second call the same day overwrote the first and this was
    unanswerable from the existing tables."""
    calls = [_call(1, "risk", "2026-08-18", 9, "normal"),
             _call(2, "risk", "2026-08-18", 11, "skip_entry"),
             _call(3, "risk", "2026-08-18", 14, "stand_down")]
    out = attach_outcomes(calls, SPY)
    assert len(out) == 3
    assert {c["verdict"] for c in out} == {"normal", "skip_entry", "stand_down"}


def test_only_the_last_call_of_the_day_owns_the_overnight_gap():
    """🚨 Otherwise a signal that flips three times looks brilliant - one of
    its calls is always right about the same overnight move."""
    calls = [_call(1, "risk", "2026-08-18", 9, "normal"),
             _call(2, "risk", "2026-08-18", 14, "stand_down")]
    out = attach_outcomes(calls, SPY)
    flags = {c["verdict"]: c["last_of_day"] for c in out}
    assert flags == {"normal": False, "stand_down": True}


def test_a_call_stands_until_the_surface_says_otherwise():
    calls = [_call(1, "risk", "2026-08-18", 9, "normal"),
             _call(2, "risk", "2026-08-18", 14, "stand_down")]
    out = attach_outcomes(calls, SPY)
    by = {c["verdict"]: c for c in out}
    assert by["normal"]["superseded_by"] == "stand_down"
    assert by["stand_down"]["superseded_by"] is None


def test_surfaces_do_not_supersede_each_other():
    """Squeeze saying something does not replace Risk's standing call."""
    calls = [_call(1, "risk", "2026-08-18", 9, "normal"),
             _call(2, "squeeze", "2026-08-18", 10, "SELL_PREMIUM")]
    out = attach_outcomes(calls, SPY)
    by = {c["surface"]: c for c in out}
    assert by["risk"]["superseded_by"] is None


# --- scoring -----------------------------------------------------------------

def test_a_hit_rate_never_ships_without_its_base_rate():
    """🚨 THE RULE. 55% right in a market that rises 55% of the time is zero
    information, and on its own it reads like a win."""
    calls = [_call(i, "session", f"2026-08-{17 + (i % 3)}", 14, "DOWN CONFIRMED")
             for i in range(12)]
    s = score(attach_outcomes(calls, SPY))
    v = s["verdicts"][0]
    assert v["hit_rate"] is not None
    assert v["base_rate"] is not None, "a hit rate alone is not reportable"
    assert v["edge"] == pytest.approx(v["hit_rate"] - v["base_rate"])
    assert s["base_rate_up"] is not None


def test_a_thin_sample_says_so():
    calls = [_call(1, "session", "2026-08-18", 14, "DOWN CONFIRMED")]
    s = score(attach_outcomes(calls, SPY))
    assert s["verdicts"][0]["thin"] is True
    assert s["verdicts"][0]["n"] == 1


def test_a_verdict_with_no_directional_claim_is_not_scored_for_direction():
    """NOT ARMED is not a forecast. Scoring it would manufacture an edge."""
    calls = [_call(i, "session", "2026-08-18", 14, "NOT ARMED") for i in range(12)]
    s = score(attach_outcomes(calls, SPY))
    v = s["verdicts"][0]
    assert v["hit_rate"] is None and v["kind"] is None


def test_scoring_an_empty_window_returns_nothing_not_a_fake_number():
    assert score([]) == {}


def test_big_is_defined_from_the_sample_not_a_constant():
    """"Big" must mean big for THIS market, not big in 2019."""
    calls = [_call(i, "risk", f"2026-08-{17 + (i % 3)}", 14, "stand_down")
             for i in range(12)]
    s = score(attach_outcomes(calls, SPY))
    assert s["big_move_cut_pct"] is not None


# --- disagreement -------------------------------------------------------------

def test_the_days_the_surfaces_split_are_surfaced():
    """🚨 Squeeze and Risk are the same trade - same underlying, same short
    strike, same entry minute. Two signals that always agree add nothing by
    being stacked; the split days are where the second earns its place."""
    calls = [_call(1, "risk", "2026-08-18", 14, "stand_down"),
             _call(2, "squeeze", "2026-08-18", 15, "SELL_PREMIUM")]
    d = disagreements(attach_outcomes(calls, SPY))
    assert [x["trade_date"] for x in d] == ["2026-08-18"]


def test_agreement_is_not_reported_as_disagreement():
    calls = [_call(1, "risk", "2026-08-18", 14, "stand_down"),
             _call(2, "squeeze", "2026-08-18", 15, "NO_SELL")]
    assert disagreements(attach_outcomes(calls, SPY)) == []


def test_the_last_call_of_the_day_is_the_one_compared():
    """A surface that flipped INTO agreement by the close has not disagreed."""
    calls = [_call(1, "risk", "2026-08-18", 9, "stand_down"),
             _call(2, "risk", "2026-08-18", 14, "normal"),
             _call(3, "squeeze", "2026-08-18", 15, "SELL_PREMIUM")]
    assert disagreements(attach_outcomes(calls, SPY)) == []
