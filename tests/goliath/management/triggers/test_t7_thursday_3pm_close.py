"""Tests for trading.goliath.management.triggers.t7_thursday_3pm_close."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t7_thursday_3pm_close import (  # noqa: E402
    THURSDAY_CUTOFF_TIME,
    evaluate,
)

_ET = ZoneInfo("America/New_York")
_FRIDAY = date(2026, 5, 8)
_THURSDAY = date(2026, 5, 7)


def _position(exp: date = _FRIDAY) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=exp,
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )


def _et(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=_ET)


class T7Fire(unittest.TestCase):
    def test_fires_at_exact_thursday_3pm_et(self):
        action = evaluate(_position(), now=_et(_THURSDAY, 15, 0))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T7")
        self.assertTrue(action.closes_everything)

    def test_fires_after_thursday_3pm_et(self):
        action = evaluate(_position(), now=_et(_THURSDAY, 15, 30))
        self.assertIsNotNone(action)

    def test_fires_friday_morning(self):
        action = evaluate(_position(), now=_et(_FRIDAY, 9, 30))
        self.assertIsNotNone(action)


class T7NoFire(unittest.TestCase):
    def test_does_not_fire_thursday_2_59pm_et(self):
        action = evaluate(_position(), now=_et(_THURSDAY, 14, 59))
        self.assertIsNone(action)

    def test_does_not_fire_wednesday_afternoon(self):
        action = evaluate(_position(), now=_et(date(2026, 5, 6), 15, 30))
        self.assertIsNone(action)

    def test_does_not_fire_monday(self):
        action = evaluate(_position(), now=_et(date(2026, 5, 4), 10, 0))
        self.assertIsNone(action)


class T7TimezoneEdgeCases(unittest.TestCase):
    def test_utc_input_normalized_to_et(self):
        # 19:00 UTC = 15:00 EDT (May = DST). Should fire.
        utc_now = datetime(2026, 5, 7, 19, 0, tzinfo=timezone.utc)
        action = evaluate(_position(), now=utc_now)
        self.assertIsNotNone(action)

    def test_utc_input_just_before_cutoff_no_fire(self):
        # 18:59 UTC = 14:59 EDT -> below cutoff.
        utc_now = datetime(2026, 5, 7, 18, 59, tzinfo=timezone.utc)
        action = evaluate(_position(), now=utc_now)
        self.assertIsNone(action)

    def test_pacific_tz_input_normalized(self):
        # 12:00 noon Pacific = 15:00 ET on the same date.
        pacific = ZoneInfo("America/Los_Angeles")
        action = evaluate(_position(), now=_et(_THURSDAY, 15, 0).astimezone(pacific))
        self.assertIsNotNone(action)

    def test_naive_datetime_returns_none(self):
        # Defensive: naive datetimes are ambiguous; reject.
        naive = datetime(2026, 5, 7, 15, 0)
        action = evaluate(_position(), now=naive)
        self.assertIsNone(action)


class T7NonStandardExpiration(unittest.TestCase):
    def test_works_for_arbitrary_expiration_dates(self):
        # If expiration moves to a non-Friday (e.g., holiday-shifted),
        # T7 still uses expiration_date - 1 calendar day at 3pm ET.
        wed_exp = date(2026, 5, 6)  # Wednesday
        # Tuesday 3pm ET should fire.
        tuesday_3pm = _et(date(2026, 5, 5), 15, 0)
        action = evaluate(_position(exp=wed_exp), now=tuesday_3pm)
        self.assertIsNotNone(action)


class T7ConstantsAndContext(unittest.TestCase):
    def test_cutoff_time_is_3pm(self):
        self.assertEqual(THURSDAY_CUTOFF_TIME, time(15, 0))

    def test_context_includes_cutoff_and_now(self):
        action = evaluate(_position(), now=_et(_THURSDAY, 15, 30))
        self.assertIn("now_et", action.context)
        self.assertIn("cutoff_et", action.context)
        self.assertEqual(action.context["expiration_date"], _FRIDAY.isoformat())


if __name__ == "__main__":
    unittest.main()
