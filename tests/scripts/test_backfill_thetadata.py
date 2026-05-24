"""Unit tests for scripts/backfill_thetadata.py — focused on the 0DTE/1DTE
expiration selection and the DTE-aware resume clause.

Loads the script by file path (it lives in scripts/, not an importable package)
so these tests don't depend on sys.path or package layout.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_thetadata.py"
_spec = importlib.util.spec_from_file_location("backfill_thetadata", _MOD_PATH)
backfill = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve its own module (Py3.14).
sys.modules["backfill_thetadata"] = backfill
_spec.loader.exec_module(backfill)


# 2024-03-15 is a Friday (trading day); next trading day is Mon 2024-03-18.
FRIDAY = dt.date(2024, 3, 15)
NEXT_TRADING_DAY = dt.date(2024, 3, 18)


def test_plan_pulls_1dte_uses_next_trading_day():
    pulls = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=2, dte=1)
    assert pulls, "expected pulls"
    assert all(p.expiration_date == NEXT_TRADING_DAY for p in pulls)
    assert all(p.trade_date == FRIDAY for p in pulls)


def test_plan_pulls_0dte_uses_same_trade_day():
    pulls = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=2, dte=0)
    assert pulls, "expected pulls"
    assert all(p.expiration_date == FRIDAY for p in pulls)
    assert all(p.trade_date == FRIDAY for p in pulls)


def test_plan_pulls_default_is_1dte():
    """Omitting dte must preserve the original (1DTE) behavior."""
    pulls = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=2)
    assert all(p.expiration_date == NEXT_TRADING_DAY for p in pulls)


def test_plan_pulls_strike_and_right_coverage():
    # half_width=2 -> 5 integer strikes, x2 rights (C/P) = 10 pulls.
    pulls = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=2, dte=0)
    assert len(pulls) == 10
    assert {p.strike for p in pulls} == {513, 514, 515, 516, 517}
    assert {p.right for p in pulls} == {"C", "P"}


def test_0dte_and_1dte_differ_for_same_trade_date():
    p0 = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=1, dte=0)
    p1 = backfill.plan_pulls(FRIDAY, spot=515.0, half_width=1, dte=1)
    assert p0[0].expiration_date != p1[0].expiration_date


# --- get_resume_point: verify the DTE filter clause -------------------------

class _FakeCursor:
    def __init__(self, result):
        self._result = result
        self.executed_sql = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args):
        self.executed_sql = sql

    def fetchone(self):
        return self._result


class _FakeConn:
    def __init__(self, result):
        self.cur = _FakeCursor(result)

    def cursor(self):
        return self.cur


def test_get_resume_point_0dte_filters_same_day():
    conn = _FakeConn((dt.date(2026, 5, 21),))
    out = backfill.get_resume_point(conn, dte=0)
    assert "expiration_date = trade_date" in conn.cur.executed_sql
    assert out == dt.date(2026, 5, 21)


def test_get_resume_point_1dte_filters_next_day():
    conn = _FakeConn((dt.date(2026, 5, 21),))
    out = backfill.get_resume_point(conn, dte=1)
    assert "expiration_date > trade_date" in conn.cur.executed_sql
    assert out == dt.date(2026, 5, 21)


def test_get_resume_point_empty_returns_none():
    conn = _FakeConn((None,))
    assert backfill.get_resume_point(conn, dte=0) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
