"""`/api/spreadworks/talon/*` — TALON paper-only $500 small-cap squeeze bot.

Same testing convention as `test_squeeze_hunt_premarket.py`: exercise the
route function directly against a fake `_query`, not a real DB. Postgres
(psycopg2) hands back real `date`/`datetime` objects for DATE/TIMESTAMP
columns, which is what the route's `.isoformat()` calls assume — a
sqlite-backed test would pass for the wrong reason.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException

import backend.routes_talon as rt


def _fake_query(rows, captured_sql: list[str] | None = None):
    def fn(sql: str):
        if captured_sql is not None:
            captured_sql.append(sql)
        if isinstance(rows, Exception):
            raise rows
        return rows

    return fn


def _fake_query_sequence(sequence):
    """Returns a different row-set on each successive `_query` call, in
    call order — `/status` makes three separate `_query` calls."""
    calls = {"i": 0}

    def fn(sql: str):
        rows = sequence[calls["i"]]
        calls["i"] += 1
        if isinstance(rows, Exception):
            raise rows
        return rows

    return fn


# --------------------------------------------------------------------------
# /status
# --------------------------------------------------------------------------
def test_status_computes_pnl_and_win_rate(monkeypatch):
    acct = [(500.0, 562.5, datetime(2026, 10, 6, 14, 55))]
    open_count = [(1,)]
    perf = [(3, 2)]
    monkeypatch.setattr(rt, "_query", _fake_query_sequence([acct, open_count, perf]))

    out = rt.talon_status()

    assert out["paper_only"] is True
    assert out["starting_balance"] == 500.0
    assert out["current_balance"] == 562.5
    assert out["total_pnl"] == pytest.approx(62.5)
    assert out["total_pnl_pct"] == pytest.approx(0.125)
    assert out["open_positions"] == 1
    assert out["closed_trades"] == 3
    assert out["wins"] == 2
    assert out["win_rate"] == pytest.approx(2 / 3)
    assert out["updated_at"] == "2026-10-06T14:55:00"


def test_status_no_account_row_reads_as_not_started(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query([]))

    out = rt.talon_status()

    assert out["paper_only"] is True
    assert out["starting_balance"] == rt.STARTING_BALANCE_FALLBACK
    assert out["current_balance"] == rt.STARTING_BALANCE_FALLBACK
    assert out["total_pnl"] == 0.0
    assert out["open_positions"] == 0
    assert out["closed_trades"] == 0
    assert out["win_rate"] is None


def test_status_zero_closed_trades_win_rate_is_none(monkeypatch):
    acct = [(500.0, 500.0, datetime(2026, 10, 6, 8, 33))]
    open_count = [(0,)]
    perf = [(0, 0)]
    monkeypatch.setattr(rt, "_query", _fake_query_sequence([acct, open_count, perf]))

    out = rt.talon_status()

    assert out["closed_trades"] == 0
    assert out["win_rate"] is None
    assert out["total_pnl"] == 0.0


def test_status_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(
        rt, "_query",
        _fake_query(RuntimeError('relation "sw_talon_account" does not exist')),
    )

    with pytest.raises(HTTPException) as exc_info:
        rt.talon_status()

    assert exc_info.value.status_code == 503
    assert "talon mirror unreachable" in exc_info.value.detail


# --------------------------------------------------------------------------
# /positions
# --------------------------------------------------------------------------
def test_positions_rows_have_expected_keys_and_types(monkeypatch):
    rows = [
        ("AIXI-2026-10-06", "AIXI", date(2026, 10, 6), datetime(2026, 10, 6, 9, 32),
         2.91, 100.0, 34.36, "paper"),
    ]
    monkeypatch.setattr(rt, "_query", _fake_query(rows))

    out = rt.talon_positions()

    assert out["count"] == 1
    row = out["positions"][0]
    assert row["position_id"] == "AIXI-2026-10-06"
    assert row["symbol"] == "AIXI"
    assert row["signal_date"] == "2026-10-06"
    assert row["entry_ts"] == "2026-10-06T09:32:00"
    assert row["entry_ask"] == 2.91
    assert row["position_size_usd"] == 100.0
    assert row["shares"] == 34.36
    assert row["account_type"] == "paper"
    assert set(row.keys()) == {
        "position_id", "symbol", "signal_date", "entry_ts", "entry_ask",
        "position_size_usd", "shares", "account_type",
    }


def test_positions_empty_yields_empty_payload(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query([]))

    out = rt.talon_positions()

    assert out == {"positions": [], "count": 0}


def test_positions_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query(RuntimeError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        rt.talon_positions()

    assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------
# /trades
# --------------------------------------------------------------------------
def test_trades_rows_have_expected_keys_and_types(monkeypatch):
    rows = [
        ("AIXI-2026-10-06", "AIXI", date(2026, 10, 6), datetime(2026, 10, 6, 9, 32),
         2.91, datetime(2026, 10, 6, 14, 55), 1.83, "eod", -37.11, 100.0,
         34.36, "paper"),
    ]
    captured: list[str] = []
    monkeypatch.setattr(rt, "_query", _fake_query(rows, captured))

    out = rt.talon_trades()

    assert out["count"] == 1
    row = out["trades"][0]
    assert row["symbol"] == "AIXI"
    assert row["exit_ts"] == "2026-10-06T14:55:00"
    assert row["exit_price"] == 1.83
    assert row["exit_reason"] == "eod"
    assert row["realized_pnl"] == -37.11
    assert "ORDER BY exit_ts DESC" in captured[0]
    assert "LIMIT 100" in captured[0]


def test_trades_limit_is_clamped(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(rt, "_query", _fake_query([], captured))

    rt.talon_trades(limit=10_000)
    assert "LIMIT 500" in captured[0]

    rt.talon_trades(limit=0)
    assert "LIMIT 1" in captured[1]


def test_trades_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query(RuntimeError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        rt.talon_trades()

    assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------
# /equity-curve
# --------------------------------------------------------------------------
def test_equity_curve_returns_oldest_first(monkeypatch):
    # _query itself returns newest-first (per the route's own ORDER BY) —
    # the route must reverse it back to oldest-first for the chart.
    rows = [
        (datetime(2026, 10, 6, 14, 55), 462.89),
        (datetime(2026, 10, 6, 9, 32), 500.0),
    ]
    monkeypatch.setattr(rt, "_query", _fake_query(rows))

    out = rt.talon_equity_curve()

    assert out["count"] == 2
    assert [p["equity"] for p in out["curve"]] == [500.0, 462.89]
    assert out["curve"][0]["time"] == "2026-10-06T09:32:00"
    assert out["curve"][1]["time"] == "2026-10-06T14:55:00"


def test_equity_curve_empty_yields_empty_payload(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query([]))

    out = rt.talon_equity_curve()

    assert out == {"curve": [], "count": 0}


def test_equity_curve_db_exception_raises_503(monkeypatch):
    monkeypatch.setattr(rt, "_query", _fake_query(RuntimeError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        rt.talon_equity_curve()

    assert exc_info.value.status_code == 503
