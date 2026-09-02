"""record_call's dedupe — per SESSION, not per all-time.

🚨 THE BUG THIS GUARDS. The dedupe used to skip a write whenever the last row
EVER carried the same verdict, so a steady NORMAL never wrote again once it
had written once — one row since 8/19. A call log that cannot show "still
NORMAL as of today" is not a log of what was shown, it is a log of the last
time it changed. The fix: skip only when the previous row is the SAME
verdict AND the SAME trade_date as the new call — one row per session, plus
every same-day flip.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import call_log as cl


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    cl.Base.metadata.create_all(engine, tables=[cl.CallLog.__table__])
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(cl, "SessionLocal", Session)
    return Session


def test_the_first_call_of_a_session_always_writes(db):
    assert cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 9, 0)) is True


def test_a_steady_verdict_does_not_write_again_the_same_day(db):
    cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 9, 0))
    again = cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 14, 30))
    assert again is False


def test_a_steady_verdict_writes_once_more_on_the_NEXT_session(db):
    """🚨 THE REGRESSION. This is exactly the case that stopped writing: same
    verdict, new day. Without the trade_date check this stays False forever."""
    cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 9, 0))
    next_day = cl.record_call("risk", "normal", now=datetime(2026, 8, 20, 9, 0))
    assert next_day is True


def test_a_same_day_flip_still_writes(db):
    cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 9, 0))
    flip = cl.record_call("risk", "stand_down", now=datetime(2026, 8, 19, 11, 0))
    assert flip is True


def test_flipping_back_within_the_same_day_writes_too(db):
    cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 9, 0))
    cl.record_call("risk", "stand_down", now=datetime(2026, 8, 19, 11, 0))
    back = cl.record_call("risk", "normal", now=datetime(2026, 8, 19, 14, 0))
    assert back is True


def test_one_row_per_session_over_a_multi_day_steady_run(db):
    """Three sessions, same verdict every time -> three rows, not one."""
    for d in (19, 20, 21):
        cl.record_call("risk", "normal", now=datetime(2026, 8, d, 9, 0))
    rows = cl.read_calls(surface="risk", days=30,
                         now=datetime(2026, 8, 21, 16, 0))
    assert len(rows) == 3
