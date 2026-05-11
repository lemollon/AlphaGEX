"""DB tests for helios_daily_state — require DATABASE_URL."""
import datetime as dt
import os
import pytest

from trading.helios.db import HeliosDatabase
from trading.helios.models import SetupType


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB-backed test",
)


def _fresh_db():
    db = HeliosDatabase()
    today = dt.date.today()
    with db._connect() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM helios_daily_state WHERE trade_date = %s", (today,))
        conn.commit()
    return db, today


def test_load_daily_state_missing_returns_blank_state():
    db, today = _fresh_db()
    state = db.load_daily_state(today)
    assert state.trade_date == today
    assert not state.wall_fade_fired
    assert not state.wall_break_fired
    assert not state.flip_cross_fired


def test_upsert_daily_state_sets_setup_fired():
    db, today = _fresh_db()
    db.upsert_daily_state(today, fired=SetupType.WALL_FADE, signal_minute=120)
    state = db.load_daily_state(today)
    assert state.wall_fade_fired is True
    assert state.wall_break_fired is False
    assert state.last_signal_minute == 120


def test_upsert_daily_state_idempotent_multi_setup():
    db, today = _fresh_db()
    db.upsert_daily_state(today, fired=SetupType.WALL_FADE, signal_minute=60)
    db.upsert_daily_state(today, fired=SetupType.FLIP_CROSS, signal_minute=200)
    state = db.load_daily_state(today)
    assert state.wall_fade_fired is True
    assert state.flip_cross_fired is True
    assert state.last_signal_minute == 200
