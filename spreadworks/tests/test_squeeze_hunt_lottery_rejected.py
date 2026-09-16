"""`/api/spreadworks/squeeze-hunt/lottery/rejected` — candidates the
MECHANISM gate (research/mech_gate.py in the squeeze repo) turned away
before they could reach `sw_hunt_lottery`. Same shape as `/lottery` plus
`reject_reason` ('STALL' | 'UNKNOWN').

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
# rows come back with the right keys/types, in query order
# --------------------------------------------------------------------------
def test_rows_have_expected_keys_and_types(monkeypatch):
    rows = [
        ("STLL", datetime(2026, 9, 15, 20, 0), date(2026, 9, 15), 1.90, 0.31,
         22.4, 2_100_000.0, None, ">20", None, None, None, None, "STALL"),
        ("UNKN", datetime(2026, 9, 14, 14, 45), date(2026, 9, 14), 4.40, 0.18,
         11.0, 900_000.0, 3, "10-20", None, None, None, None, "UNKNOWN"),
    ]
    monkeypatch.setattr(rsh, "_query", _fake_query(rows))

    out = rsh.squeeze_hunt_lottery_rejected()

    assert out["count"] == 2
    assert [r["symbol"] for r in out["rows"]] == ["STLL", "UNKN"]

    row = out["rows"][0]
    assert row["symbol"] == "STLL"
    assert row["entry_ts"] == "2026-09-15T20:00:00"
    assert row["entry_date"] == "2026-09-15"
    assert row["entry_px"] == 1.90
    assert row["day_chg"] == 0.31
    assert row["si_pct"] == 22.4
    assert row["dollar_vol"] == 2_100_000.0
    assert row["sweep"] is None
    assert row["si_band"] == ">20"
    assert row["mech_class"] is None
    assert row["n_offering_docs_180d"] is None
    assert row["runway_quarters"] is None
    assert row["runway_basis"] is None
    assert row["reject_reason"] == "STALL"
    assert set(row.keys()) == {
        "symbol", "entry_ts", "entry_date", "entry_px", "day_chg",
        "si_pct", "dollar_vol", "sweep", "si_band", "mech_class",
        "n_offering_docs_180d", "runway_quarters", "runway_basis",
        "reject_reason",
    }

    assert out["rows"][1]["reject_reason"] == "UNKNOWN"


# --------------------------------------------------------------------------
# newest first, capped at 100 — assert the SQL text, not row count (the
# fake never actually returns >100 rows)
# --------------------------------------------------------------------------
def test_query_orders_newest_first_and_caps_at_100(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rsh, "_query", _fake_query([], captured))

    rsh.squeeze_hunt_lottery_rejected()

    sql = captured[0]
    assert "sw_hunt_lottery_shadow" in sql
    assert "ORDER BY entry_date DESC, entry_ts DESC" in sql
    assert "LIMIT 100" in sql


# --------------------------------------------------------------------------
# DB exception -> 503, same pattern as /lottery
# --------------------------------------------------------------------------
def test_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(
        rsh, "_query",
        _fake_query(RuntimeError('relation "sw_hunt_lottery_shadow" does not exist')),
    )

    with pytest.raises(HTTPException) as exc_info:
        rsh.squeeze_hunt_lottery_rejected()

    assert exc_info.value.status_code == 503
    assert "squeeze mirror unreachable" in exc_info.value.detail


# --------------------------------------------------------------------------
# empty table -> empty payload, not an error
# --------------------------------------------------------------------------
def test_empty_table_yields_empty_payload(monkeypatch):
    monkeypatch.setattr(rsh, "_query", _fake_query([]))

    out = rsh.squeeze_hunt_lottery_rejected()

    assert out == {"rows": [], "count": 0}
