"""Unit tests for the /recipe manual-ticket endpoint plumbing (registry
#23b AM + #41 PM)."""
from datetime import datetime

from backend.routes_risk import _recipe_phase, _recipe_strikes, _recipe_windows


def test_recipe_strikes_spy_dollar_grid():
    # round(777.7 - 2) = round(775.7) = 776; wing sits 5 points lower.
    short_strike, long_strike = _recipe_strikes(777.7)
    assert short_strike == 776
    assert long_strike == 771


def test_recipe_windows_match_ebb_registry():
    am_start, am_end, pm_start, pm_end = _recipe_windows()
    assert (am_start, am_end) == ((10, 5), (10, 20))
    assert (pm_start, pm_end) == ((13, 5), (13, 10))


def test_recipe_phase_before_am_counts_minutes_to_open():
    w = _recipe_windows()
    phase, minutes = _recipe_phase(datetime(2026, 8, 13, 9, 0), *w)
    assert phase == "before_am"
    assert minutes == 65


def test_recipe_phase_am_open_has_no_countdown():
    w = _recipe_windows()
    phase, minutes = _recipe_phase(datetime(2026, 8, 13, 10, 10), *w)
    assert phase == "am_open"
    assert minutes is None


def test_recipe_phase_between_counts_minutes_to_pm():
    w = _recipe_windows()
    phase, minutes = _recipe_phase(datetime(2026, 8, 13, 11, 30), *w)
    assert phase == "between"
    assert minutes == 95


def test_recipe_phase_pm_open_and_done():
    w = _recipe_windows()
    assert _recipe_phase(datetime(2026, 8, 13, 13, 7), *w) == ("pm_open", None)
    assert _recipe_phase(datetime(2026, 8, 13, 15, 0), *w) == ("done", None)


def test_recipe_phase_weekend():
    w = _recipe_windows()
    # 2026-08-15 is a Saturday.
    assert _recipe_phase(datetime(2026, 8, 15, 10, 0), *w) == ("weekend", None)
