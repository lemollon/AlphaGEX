"""`/api/spreadworks/squeeze-hunt/lottery` — confirmed lottery-setup entries.

These exercise the route function directly against a fake `_query`, not a
real DB: Postgres (psycopg2) hands back real `date`/`datetime` objects for
DATE/TIMESTAMP columns, which is what the route's `.isoformat()` calls
assume — SQLite via raw `text()` SQL hands back plain strings instead, so a
sqlite-backed test would pass for the wrong reason.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException

import backend.routes_squeeze_hunt as rsh


def _fake_query(rows, captured_sql: list[str] | None = None):
    """Route `_query(sql)` calls to canned rows (or raise if `rows` is an
    Exception), optionally recording the SQL text so a test can assert on
    the interpolated `days` clamp."""

    def fn(sql: str):
        if captured_sql is not None:
            captured_sql.append(sql)
        if isinstance(rows, Exception):
            raise rows
        return rows

    return fn


# --------------------------------------------------------------------------
# rows come back with the right keys/types, in query order
# --------------------------------------------------------------------------
def test_rows_have_expected_keys_and_types(monkeypatch):
    rows = [
        ("GPRO", datetime(2026, 9, 2, 14, 45), date(2026, 9, 2), 3.10, 0.42,
         14.2, 9_000_000.0, 3),
        ("AREN", datetime(2026, 9, 1, 14, 45), date(2026, 9, 1), 2.05, 0.55,
         18.0, 4_500_000.0, 2),
    ]
    monkeypatch.setattr(rsh, "_query", _fake_query(rows))

    out = rsh.squeeze_hunt_lottery(days=7)

    assert out["count"] == 2
    assert out["days"] == 7
    assert [r["symbol"] for r in out["rows"]] == ["GPRO", "AREN"]

    row = out["rows"][0]
    assert row["symbol"] == "GPRO"
    assert row["entry_ts"] == "2026-09-02T14:45:00"
    assert row["entry_date"] == "2026-09-02"
    assert row["entry_px"] == 3.10
    assert row["day_chg"] == 0.42
    assert row["si_pct"] == 14.2
    assert row["dollar_vol"] == 9_000_000.0
    assert row["sweep"] == 3
    assert set(row.keys()) == {
        "symbol", "entry_ts", "entry_date", "entry_px", "day_chg",
        "si_pct", "dollar_vol", "sweep",
    }


# --------------------------------------------------------------------------
# days clamps to [1, 60] and the clamped int is what lands in the SQL
# --------------------------------------------------------------------------
def test_days_clamps_low(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rsh, "_query", _fake_query([], captured))

    out = rsh.squeeze_hunt_lottery(days=0)

    assert out["days"] == 1
    assert "CURRENT_DATE - 1" in captured[0]


def test_days_clamps_high(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rsh, "_query", _fake_query([], captured))

    out = rsh.squeeze_hunt_lottery(days=999)

    assert out["days"] == 60
    assert "CURRENT_DATE - 60" in captured[0]


def test_days_within_range_passes_through(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rsh, "_query", _fake_query([], captured))

    out = rsh.squeeze_hunt_lottery(days=14)

    assert out["days"] == 14
    assert "CURRENT_DATE - 14" in captured[0]


# --------------------------------------------------------------------------
# DB exception -> 503, same pattern as /signals and /tape
# --------------------------------------------------------------------------
def test_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(
        rsh, "_query",
        _fake_query(RuntimeError('relation "sw_hunt_lottery" does not exist')),
    )

    with pytest.raises(HTTPException) as exc_info:
        rsh.squeeze_hunt_lottery(days=7)

    assert exc_info.value.status_code == 503
    assert "squeeze mirror unreachable" in exc_info.value.detail


# --------------------------------------------------------------------------
# empty table -> empty payload, not an error
# --------------------------------------------------------------------------
def test_empty_table_yields_empty_payload(monkeypatch):
    monkeypatch.setattr(rsh, "_query", _fake_query([]))

    out = rsh.squeeze_hunt_lottery(days=7)

    assert out == {"rows": [], "count": 0, "days": 7}
