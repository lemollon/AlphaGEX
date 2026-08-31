"""The /hunt page's one backend addition: a read-only list of every day the
two-stage confirmation watcher (risk_confirm_state) has recorded.

Everything else /hunt shows (today's flag, today's confirm state, the
playbook, the alert directory) already exists on /session and as static copy
— this is the only new query, so it is the only thing that needs new tests.
"""
import asyncio
from datetime import date, datetime

import pytest

from backend import routes_risk as R

CT = R.CT


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture
def confirm_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db import Base
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(R, "SessionLocal", Session)
    return Session


def _row(Session, **kw):
    db = Session()
    row = R.RiskConfirmState(**kw)
    db.add(row)
    db.commit()
    db.close()


def test_no_database_reports_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", None)
    out = _run(R.confirm_history())
    assert out["status"] == "unavailable"
    assert out["rows"] == []


def test_an_empty_table_is_an_empty_list_not_an_error(confirm_db):
    out = _run(R.confirm_history())
    assert out["status"] == "ok"
    assert out["rows"] == []


def test_a_fired_down_day_reports_a_positive_outcome_when_it_kept_falling(confirm_db):
    _row(confirm_db, d=date(2026, 8, 17), armed="yes", putcall_z=2.72,
         ref_spot=775.50, run_min=772.51, run_max=775.50,
         fired_dir="DOWN", fired_at=datetime(2026, 8, 17, 11, 55),
         fired_spot=774.68, close_spot=772.67)
    rows = _run(R.confirm_history())["rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["fired_dir"] == "DOWN"
    assert r["ref_spot"] == 775.50
    assert r["fired_at"] == "2026-08-17T11:55:00"
    # it kept moving DOWN after the fire (772.67 < 774.68), so the SIGNED
    # outcome — positive means "continued in the fired direction" — is > 0
    assert r["outcome_pct"] > 0
    assert r["outcome_pct"] == pytest.approx(
        (774.68 - 772.67) / 774.68 * 100, abs=1e-3)


def test_an_up_day_that_reversed_reports_a_negative_outcome(confirm_db):
    """Signed in the fired direction: an UP confirmation that gives it all
    back before the close must NOT read as a win."""
    _row(confirm_db, d=date(2026, 8, 19), armed="yes", putcall_z=1.9,
         ref_spot=700.00, run_min=700.00, run_max=701.00,
         fired_dir="UP", fired_at=datetime(2026, 8, 19, 11, 0),
         fired_spot=701.00, close_spot=699.50)
    r = _run(R.confirm_history())["rows"][0]
    assert r["outcome_pct"] < 0


def test_a_day_that_never_fired_still_appears_with_no_outcome(confirm_db):
    """Every session the watcher ran belongs on the reviewable list, not just
    the ones that fired — 'no confirm' is itself a fact worth reading."""
    _row(confirm_db, d=date(2026, 8, 21), armed="no", putcall_z=0.4,
         ref_spot=780.00, run_min=779.50, run_max=780.20)
    r = _run(R.confirm_history())["rows"][0]
    assert r["fired_dir"] is None
    assert r["outcome_pct"] is None


def test_a_row_missing_close_spot_does_not_crash_and_has_no_outcome(confirm_db):
    """The close is filled by a separate end-of-day job; a firing recorded
    mid-session and read before that job runs must degrade gracefully."""
    _row(confirm_db, d=date(2026, 8, 24), armed="yes", putcall_z=2.1,
         ref_spot=750.00, run_min=748.00, run_max=750.00,
         fired_dir="DOWN", fired_at=datetime(2026, 8, 24, 10, 40),
         fired_spot=748.50, close_spot=None)
    r = _run(R.confirm_history())["rows"][0]
    assert r["outcome_pct"] is None


def test_newest_first(confirm_db):
    _row(confirm_db, d=date(2026, 8, 10), armed="no")
    _row(confirm_db, d=date(2026, 8, 12), armed="no")
    _row(confirm_db, d=date(2026, 8, 11), armed="no")
    rows = _run(R.confirm_history())["rows"]
    assert [r["d"] for r in rows] == ["2026-08-12", "2026-08-11", "2026-08-10"]


def test_limit_is_respected_and_bounded(confirm_db):
    for i in range(5):
        _row(confirm_db, d=date(2026, 8, 1 + i), armed="no")
    assert len(_run(R.confirm_history(limit=2))["rows"]) == 2
    # an absurd limit must not blow past the module's hard cap of 500
    out = _run(R.confirm_history(limit=10_000))
    assert out["status"] == "ok"


def test_a_broken_query_degrades_to_unavailable_not_a_500(confirm_db, monkeypatch):
    class _BoomSession:
        def __call__(self):
            raise RuntimeError("db is down")
    monkeypatch.setattr(R, "SessionLocal", _BoomSession())
    out = _run(R.confirm_history())
    assert out["status"] == "unavailable"
    assert out["rows"] == []
