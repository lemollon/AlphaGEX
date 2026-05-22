import datetime as dt
import os
import pytest
from backtest.ember.build import DayPath
from backtest.ember.cache import (
    build_key, ensure_tables, create_pending, set_progress,
    set_completed, set_failed, get_build, load_paths,
)

PARAMS = {"start": "2024-01-02", "end": "2024-01-31", "entry_minute": 30,
          "short_delta": 0.16, "wing_width": 5.0, "fill": "ask_cross"}


def test_build_key_is_deterministic_and_order_insensitive():
    a = build_key({"a": 1, "b": 2})
    b = build_key({"b": 2, "a": 1})   # different insertion order, same content
    assert a == b
    assert build_key({"a": 1}) != build_key({"a": 2})
    assert isinstance(a, str) and len(a) == 16


def _dp(date_str, gross):
    return DayPath(trade_date=dt.date.fromisoformat(date_str), entry_minute=30, entry_credit=0.5,
                   contracts=1, commission_dollars=5.2, is_oos=False, path=[(0, 0.0), (10, gross)])


@pytest.mark.integration
def test_cache_lifecycle_roundtrip():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    db = os.environ["DATABASE_URL"]
    ensure_tables(db)
    params = dict(PARAMS, _test_marker="ember_cache_test")  # unique-ish so we can clean up
    bid = build_key(params)
    try:
        create_pending(db, bid, params)
        row = get_build(db, bid)
        assert row["status"] == "pending" and row["progress"] == 0
        assert row["params"]["entry_minute"] == 30

        set_progress(db, bid, 50, "halfway")
        row = get_build(db, bid)
        assert row["status"] == "running" and row["progress"] == 50 and row["progress_message"] == "halfway"

        paths = [_dp("2024-01-03", 30.0), _dp("2024-01-04", -20.0)]
        set_completed(db, bid, paths)
        row = get_build(db, bid)
        assert row["status"] == "completed" and row["progress"] == 100 and row["n_days"] == 2
        # get_build does not return the heavy paths blob by default
        assert "paths" not in row or row.get("paths") in (None, [])

        loaded = load_paths(db, bid)
        assert len(loaded) == 2
        assert loaded[0].trade_date == dt.date(2024, 1, 3)
        assert loaded[0].path == [(0, 0.0), (10, 30.0)]

        set_failed(db, bid, "boom")
        assert get_build(db, bid)["status"] == "failed"
        assert get_build(db, bid)["error"] == "boom"
    finally:
        # cleanup the test row
        import psycopg2
        with psycopg2.connect(db) as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM ember_builds WHERE build_id = %s", (bid,))


@pytest.mark.integration
def test_get_build_missing_returns_none():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    ensure_tables(os.environ["DATABASE_URL"])
    assert get_build(os.environ["DATABASE_URL"], "nonexistent_build_xyz") is None
