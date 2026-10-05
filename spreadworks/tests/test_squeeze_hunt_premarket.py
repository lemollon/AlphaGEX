"""`/api/spreadworks/squeeze-hunt/premarket` — PREREG #2 premarket-turnover
scanner (`research/premarket_velocity_scan.py` in the squeeze repo, the
08:35 CT `SqueezePremarket0835` task), latest scan day only, sorted by
`premarket_move` descending — the only ranking signal this scan produces.

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
    def fn(sql: str):
        if captured_sql is not None:
            captured_sql.append(sql)
        if isinstance(rows, Exception):
            raise rows
        return rows

    return fn


# --------------------------------------------------------------------------
# rows come back with the right keys/types, in query order (the SQL already
# sorts by premarket_move DESC — the route must not re-sort or reverse it)
# --------------------------------------------------------------------------
def test_rows_have_expected_keys_and_types(monkeypatch):
    rows = [
        ("BIGM", datetime(2026, 10, 3, 8, 35), date(2026, 10, 3), 0.42, 0.55,
         8_200_000, 3.10, 2.00, 19_500_000, True, "0835", 3.05, 3.15, 3.2, True),
        ("SMLR", datetime(2026, 10, 3, 8, 35), date(2026, 10, 3), 0.19, 0.12,
         1_100_000, 1.85, 1.65, 5_800_000, False, "0835", None, None, None, False),
    ]
    monkeypatch.setattr(rsh, "_query", _fake_query(rows))

    out = rsh.squeeze_hunt_premarket()

    assert out["count"] == 2
    assert out["signal_date"] == "2026-10-03"
    # Order preserved exactly as returned by the (already-sorted) query —
    # biggest mover first, never re-sorted client-side.
    assert [r["symbol"] for r in out["rows"]] == ["BIGM", "SMLR"]

    row = out["rows"][0]
    assert row["symbol"] == "BIGM"
    assert row["signal_ts"] == "2026-10-03T08:35:00"
    assert row["signal_date"] == "2026-10-03"
    assert row["premarket_turnover"] == 0.42
    assert row["premarket_move"] == 0.55
    assert row["premarket_vol"] == 8_200_000
    assert row["premarket_last_px"] == 3.10
    assert row["prior_close"] == 2.00
    assert row["shares_outstanding"] == 19_500_000
    assert row["has_options"] is True
    assert row["sweep"] == "0835"
    assert row["entry_bid"] == 3.05
    assert row["entry_ask"] == 3.15
    assert row["spread_pct"] == 3.2
    assert row["tradeable"] is True
    assert set(row.keys()) == {
        "symbol", "signal_ts", "signal_date", "premarket_turnover",
        "premarket_move", "premarket_vol", "premarket_last_px", "prior_close",
        "shares_outstanding", "has_options", "sweep", "entry_bid",
        "entry_ask", "spread_pct", "tradeable",
    }

    row2 = out["rows"][1]
    assert row2["premarket_move"] == 0.12
    assert row2["entry_bid"] is None
    assert row2["tradeable"] is False


# --------------------------------------------------------------------------
# query sorts by premarket_move DESC off the latest signal_date on record
# --------------------------------------------------------------------------
def test_query_orders_by_premarket_move_desc_latest_day(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rsh, "_query", _fake_query([], captured))

    rsh.squeeze_hunt_premarket()

    sql = captured[0]
    assert "sw_hunt_premarket" in sql
    assert "SELECT MAX(signal_date) FROM sw_hunt_premarket" in sql
    assert "ORDER BY premarket_move DESC" in sql


# --------------------------------------------------------------------------
# DB exception -> 503, same pattern as the rest of this file
# --------------------------------------------------------------------------
def test_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(
        rsh, "_query",
        _fake_query(RuntimeError('relation "sw_hunt_premarket" does not exist')),
    )

    with pytest.raises(HTTPException) as exc_info:
        rsh.squeeze_hunt_premarket()

    assert exc_info.value.status_code == 503
    assert "squeeze mirror unreachable" in exc_info.value.detail


# --------------------------------------------------------------------------
# empty table -> empty payload, not an error
# --------------------------------------------------------------------------
def test_empty_table_yields_empty_payload(monkeypatch):
    monkeypatch.setattr(rsh, "_query", _fake_query([]))

    out = rsh.squeeze_hunt_premarket()

    assert out == {"rows": [], "count": 0, "signal_date": None}
