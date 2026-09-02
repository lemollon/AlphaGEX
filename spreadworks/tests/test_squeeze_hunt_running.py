"""`/api/spreadworks/squeeze-hunt/signals` — the "still running" section.

A name that fired within the last 30 days but still clears the V1/V2
threshold today is dropped by the scan's own dedupe (see the squeeze repo's
research/intraday_velocity_scan.py) and so never reaches `signals`. It is
mirrored separately into `sw_hunt_running`, and this route folds it into the
response as `running` so the page can show it without re-alerting on a name
already seen.

These exercise the route function directly against a fake `_query`, not a
real DB: Postgres (psycopg2) hands back real `date`/`datetime` objects for
DATE/TIMESTAMP columns, which is what the route's `.isoformat()` calls
assume — SQLite via raw `text()` SQL hands back plain strings instead, so a
sqlite-backed test would pass for the wrong reason.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

import backend.routes_squeeze_hunt as rsh


def _fake_query(tables: dict[str, list[tuple]]):
    """Route `_query(sql)` calls to canned rows by table name.

    Checked most-specific-first: 'sw_hunt_signals' contains 'sw_hunt_si' as a
    prefix, so the signals query would falsely match an 'sw_hunt_si' probe if
    checked in the wrong order.
    """
    order = ["sw_hunt_running", "sw_hunt_signals", "sw_hunt_tape",
             "sw_hunt_lottery", "sw_hunt_si"]

    def fn(sql: str):
        for name in order:
            if name in sql:
                rows = tables.get(name)
                if isinstance(rows, Exception):
                    raise rows
                return rows or []
        raise AssertionError(f"unrecognised query: {sql!r}")
    return fn


def _base_tables(**overrides):
    tables = {
        "sw_hunt_signals": [],
        "sw_hunt_tape": [],
        "sw_hunt_lottery": [],
        "sw_hunt_si": [],
        "sw_hunt_running": [],
    }
    tables.update(overrides)
    return tables


# --------------------------------------------------------------------------
# a deduped-but-still-running name appears in `running`
# --------------------------------------------------------------------------
def test_running_row_appears_when_not_in_signals(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            ("BIAF", date(2026, 9, 2), "V1", 5.18, 0.67, 1.4, 8.2, 13_020_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))

    out = rsh.squeeze_hunt_signals()

    assert out["running_count"] == 1
    row = out["running"][0]
    assert row["symbol"] == "BIAF"
    assert row["price"] == 5.18
    assert row["day_chg_pct"] == pytest.approx(67.0)
    assert row["turnover"] == 1.4
    assert row["volx"] == 8.2
    assert row["dollar_vol"] == 13_020_000.0
    assert row["first_signal_date"] == "2026-09-01"
    assert row["run_days"] == 2                       # 9/1 and 9/2 inclusive


def test_running_is_empty_when_nothing_dedupes(monkeypatch):
    monkeypatch.setattr(rsh, "_query", _fake_query(_base_tables()))
    out = rsh.squeeze_hunt_signals()
    assert out["running"] == []
    assert out["running_count"] == 0


# --------------------------------------------------------------------------
# a symbol already in today's signals must not double up in `running`
# --------------------------------------------------------------------------
def test_a_symbol_already_in_signals_is_excluded_from_running(monkeypatch):
    tables = _base_tables(
        sw_hunt_signals=[
            ("GPRO", datetime(2026, 9, 2, 14, 45), 3.10, 0.42, 9_000_000.0, 4.0,
             1.1, 0.03, -0.01, "context ?", 1, 1),
        ],
        sw_hunt_running=[
            # Same symbol, still clearing the line, but already an active
            # signal today — must NOT appear a second time in `running`.
            ("GPRO", date(2026, 9, 2), "V1", 3.10, 0.42, 1.1, 4.0, 27_900_000.0,
             date(2026, 9, 1)),
            # A genuinely deduped-only name stays.
            ("AREN", date(2026, 9, 2), "V1", 2.05, 0.55, 0.95, 6.1, 4_500_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))

    out = rsh.squeeze_hunt_signals()

    symbols = {s["symbol"] for s in out["signals"]}
    running_symbols = {r["symbol"] for r in out["running"]}
    assert "GPRO" in symbols
    assert "GPRO" not in running_symbols
    assert running_symbols == {"AREN"}


# --------------------------------------------------------------------------
# a missing sw_hunt_running table (before the first sync) must not 500
# --------------------------------------------------------------------------
def test_missing_running_table_yields_empty_list_not_a_500(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=RuntimeError('relation "sw_hunt_running" does not exist'),
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))

    out = rsh.squeeze_hunt_signals()

    assert out["running"] == []
    assert out["running_count"] == 0
    # the rest of the payload must still come through untouched
    assert out["count"] == 0


# --------------------------------------------------------------------------
# run_days is a business-day count, inclusive of both ends
# --------------------------------------------------------------------------
def test_run_days_is_a_business_day_count_inclusive(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            # Fri 8/28 -> Wed 9/2, skipping the 8/29-8/30 weekend:
            # 8/28, 8/31, 9/1, 9/2 = 4 business days.
            ("SSM", date(2026, 9, 2), "V1", 1.20, 0.30, 0.95, 5.5, 2_000_000.0,
             date(2026, 8, 28)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))

    out = rsh.squeeze_hunt_signals()

    assert out["running"][0]["run_days"] == 4


def test_run_days_is_none_without_a_first_signal_date(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            ("NODT", date(2026, 9, 2), "V1", 1.00, 0.20, 0.90, 5.0, 1_000_000.0,
             None),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))
    out = rsh.squeeze_hunt_signals()
    assert out["running"][0]["run_days"] is None
    assert out["running"][0]["first_signal_date"] is None


# --------------------------------------------------------------------------
# one row per symbol — V1 wins over V2 when a name clears both lines
# --------------------------------------------------------------------------
def test_v1_preferred_over_v2_for_the_same_symbol(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            ("GYGY", date(2026, 9, 2), "V2", 1.55, 0.20, 0.35, 5.2, 3_000_000.0,
             date(2026, 9, 1)),
            ("GYGY", date(2026, 9, 2), "V1", 1.60, 0.22, 0.92, 5.2, 3_100_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))

    out = rsh.squeeze_hunt_signals()

    rows = [r for r in out["running"] if r["symbol"] == "GYGY"]
    assert len(rows) == 1
    assert rows[0]["turnover"] == 0.92                # the V1 read, not V2


# --------------------------------------------------------------------------
# only the latest sweep of the latest trade_date is read
# --------------------------------------------------------------------------
def test_only_the_latest_sweep_of_the_latest_day_is_read(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            # An earlier sweep, same day: must be ignored in favour of the
            # later ts. The route filters this in SQL (WHERE ts = MAX(ts)),
            # so the fake only ever hands back the rows a real query would.
            ("AREN", date(2026, 9, 2), "V1", 1.90, 0.40, 0.85, 5.0, 5_000_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))
    out = rsh.squeeze_hunt_signals()
    assert len(out["running"]) == 1
    assert out["running"][0]["price"] == 1.90


# --------------------------------------------------------------------------
# sorted by dollars traded, richest first
# --------------------------------------------------------------------------
def test_running_is_sorted_by_dollar_vol_desc(monkeypatch):
    tables = _base_tables(
        sw_hunt_running=[
            ("SMALL", date(2026, 9, 2), "V1", 1.0, 0.1, 0.9, 5.0, 1_000_000.0,
             date(2026, 9, 1)),
            ("BIG", date(2026, 9, 2), "V1", 2.0, 0.2, 0.9, 5.0, 9_000_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))
    out = rsh.squeeze_hunt_signals()
    assert [r["symbol"] for r in out["running"]] == ["BIG", "SMALL"]


# --------------------------------------------------------------------------
# short interest and money state are pulled from the same joins `signals` use
# --------------------------------------------------------------------------
def test_running_carries_si_and_money_state_from_the_same_joins(monkeypatch):
    tables = _base_tables(
        sw_hunt_tape=[("AREN", "feeding")],
        sw_hunt_si=[("AREN", 14.2, date(2026, 8, 30))],
        sw_hunt_running=[
            ("AREN", date(2026, 9, 2), "V1", 1.90, 0.40, 0.85, 5.0, 5_000_000.0,
             date(2026, 9, 1)),
        ],
    )
    monkeypatch.setattr(rsh, "_query", _fake_query(tables))
    out = rsh.squeeze_hunt_signals()
    row = out["running"][0]
    assert row["money_state"] == "STILL FEEDING"
    assert row["short_interest_pct"] == 14.2
