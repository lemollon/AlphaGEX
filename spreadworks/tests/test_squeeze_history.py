"""Freshness, per-session verdicts, and the VIX leg's own series.

The squeeze page shipped able to print a confident SELL_PREMIUM off a reading
four sessions old, because `asof` was `date.today()` and nothing ever compared
it to the newest stored row. These cover the three additions that close that:
data_freshness (how old, and do the two legs agree), signal_history (the
verdict each stored session produced), and vix_history (the leg that had no
history at all).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from backend.bots.gamma_regime import (DEEP_SHORT_B, PCT_WINDOW, data_freshness,
                                       sessions_between, signal_history,
                                       signal_summary, vix_history)
from backend.bots.vix_regime import VIX_DAILY_TABLE, ensure_vix_table
from backend.bots.gamma_regime import GAMMA_DAILY_TABLE, ensure_gamma_table


def _weekdays(end: date, n: int) -> list[date]:
    """`n` weekdays ending at `end`, ascending."""
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    ensure_gamma_table(eng)
    ensure_vix_table(eng)
    return eng


def _seed(engine, dates, gex_of, vix_of=None):
    with engine.begin() as conn:
        for d in dates:
            conn.execute(text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, updated_at) "
                "VALUES (:d, :g, :s, :u)"),
                {"d": d.isoformat(), "g": gex_of(d), "s": 700.0,
                 "u": "2026-01-01 00:00:00"})
            if vix_of is not None:
                conn.execute(text(
                    f"INSERT INTO {VIX_DAILY_TABLE} "
                    "(trade_date, vix, updated_at) VALUES (:d, :v, :u)"),
                    {"d": d.isoformat(), "v": vix_of(d), "u": "2026-01-01 00:00:00"})


# --------------------------------------------------------------------------
# sessions_between / data_freshness
# --------------------------------------------------------------------------
def test_sessions_between_skips_the_weekend():
    # Fri 2026-08-14 -> Mon 2026-08-17 is ONE session, not three days.
    assert sessions_between(date(2026, 8, 14), date(2026, 8, 17)) == 1
    assert sessions_between(date(2026, 8, 11), date(2026, 8, 14)) == 3
    assert sessions_between(date(2026, 8, 14), date(2026, 8, 14)) == 0
    assert sessions_between(date(2026, 8, 14), date(2026, 8, 10)) == 0


def test_prior_session_is_not_stale(engine):
    days = _weekdays(date(2026, 8, 14), 5)          # ends Fri, asof Mon
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["gamma_date"] == date(2026, 8, 14)
    assert f["gamma_stale_sessions"] == 0
    assert f["stale"] is False
    assert f["legs_mismatch"] is False


def test_the_shipped_condition_reads_as_stale(engine):
    """The live defect: gamma to 08-11, VIX to 08-14, page claims 08-15."""
    gdays = _weekdays(date(2026, 8, 11), 5)
    vdays = _weekdays(date(2026, 8, 14), 5)
    _seed(engine, gdays, lambda d: 1e9)
    with engine.begin() as conn:
        for d in vdays:
            conn.execute(text(
                f"INSERT INTO {VIX_DAILY_TABLE} "
                "(trade_date, vix, updated_at) VALUES (:d, :v, :u)"),
                {"d": d.isoformat(), "v": 15.0, "u": "2026-01-01 00:00:00"})

    f = data_freshness(engine, date(2026, 8, 15))
    assert f["expected_date"] == date(2026, 8, 14)
    assert f["gamma_stale_sessions"] == 3      # 08-12, 08-13, 08-14 missing
    assert f["vix_stale_sessions"] == 0
    assert f["stale"] is True
    assert f["legs_mismatch"] is True          # the two legs are 3 sessions apart


def test_freshness_never_raises_on_a_missing_table():
    eng = create_engine("sqlite:///:memory:", future=True)
    f = data_freshness(eng, date(2026, 8, 17))
    assert f["reason"] is not None
    assert f["stale"] is not True              # unknown is not "fresh"


# --------------------------------------------------------------------------
# signal_history
# --------------------------------------------------------------------------
def test_history_is_silent_until_the_percentile_window_fills(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW - 1)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    assert signal_history(engine) == []


def test_overbought_session_prints_sell_premium(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 25)
    # a rising ramp: the last session is the highest in its own window
    _seed(engine, days, lambda d: float(days.index(d)) * 1e8, lambda d: 15.0)
    rows = signal_history(engine)
    assert rows[-1]["verdict"] == "SELL_PREMIUM"
    assert rows[-1]["pct"] > 0.80


def test_deep_short_gamma_prints_no_sell(engine):
    """NO_SELL only reachable with the VIX leg DOWN — SQUEEZE_WATCH is checked
    first in the ladder, and deep short gamma is also the most oversold reading
    in its own window, so a flat VIX (ratio == 1.0, i.e. "at its highs") would
    correctly take the SQUEEZE_WATCH branch instead."""
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 25)
    last = days[-1]
    # flat mid-range history, then one session far below the veto level
    _seed(engine, days,
          lambda d: (DEEP_SHORT_B - 5.0) * 1e9 if d == last else 0.0,
          lambda d: 15.0 if d == last else 40.0)     # VIX decaying, leg 2 fails
    rows = signal_history(engine)
    assert rows[-1]["verdict"] == "NO_SELL"
    assert rows[-1]["net_gex_b"] <= DEEP_SHORT_B


def test_squeeze_watch_needs_both_legs(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 25)
    last = days[-1]
    # oversold gamma on the last session
    gex = lambda d: -20e9 if d == last else 5e9        # noqa: E731

    # leg 2 missing: VIX flat, so ratio == 1.0 only if the window max equals
    # today; make VIX DECAYING (high past, low now) -> ratio well under 0.95
    _seed(engine, days, gex, lambda d: 40.0 if d != last else 15.0)
    assert signal_history(engine)[-1]["verdict"] != "SQUEEZE_WATCH"

    # both legs: VIX at its own 20-session high on the same session
    eng2 = create_engine("sqlite:///:memory:", future=True)
    ensure_gamma_table(eng2)
    ensure_vix_table(eng2)
    _seed(eng2, days, gex, lambda d: 15.0 if d != last else 40.0)
    assert signal_history(eng2)[-1]["verdict"] == "SQUEEZE_WATCH"


def test_unknown_when_the_vix_leg_has_no_row(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 25)
    _seed(engine, days, lambda d: 1e9)                 # no VIX at all
    rows = signal_history(engine)
    assert rows and all(r["verdict"] == "UNKNOWN" for r in rows)


def test_history_is_capped_and_ordered(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 120)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    rows = signal_history(engine, n=90)
    assert len(rows) == 90
    assert [r["trade_date"] for r in rows] == sorted(r["trade_date"] for r in rows)


# --------------------------------------------------------------------------
# signal_summary
# --------------------------------------------------------------------------
def test_summary_counts_the_current_run_not_the_total(engine):
    rows = [
        {"trade_date": date(2026, 8, 3), "verdict": "SELL_PREMIUM"},
        {"trade_date": date(2026, 8, 4), "verdict": "NEUTRAL"},
        {"trade_date": date(2026, 8, 5), "verdict": "SQUEEZE_WATCH"},
        {"trade_date": date(2026, 8, 6), "verdict": "SELL_PREMIUM"},
        {"trade_date": date(2026, 8, 7), "verdict": "SELL_PREMIUM"},
    ]
    s = signal_summary(rows)
    assert s["current"] == "SELL_PREMIUM"
    assert s["sessions_in_state"] == 2          # the run, not the 3 total
    assert s["counts"]["SELL_PREMIUM"] == 3
    assert s["last_squeeze_watch"] == date(2026, 8, 5)
    assert s["last_no_sell"] is None


def test_summary_of_nothing_is_empty_not_a_crash():
    s = signal_summary([])
    assert s["n"] == 0 and s["current"] is None


# --------------------------------------------------------------------------
# vix_history
# --------------------------------------------------------------------------
def test_vix_ratio_is_one_at_a_new_high(engine):
    days = _weekdays(date(2026, 8, 14), 40)
    last = days[-1]
    _seed(engine, days, lambda d: 1e9, lambda d: 40.0 if d == last else 20.0)
    rows = vix_history(engine)
    assert rows[-1]["ratio"] == pytest.approx(2.0)     # 40 / 20
    assert rows[0]["ratio"] is None                    # window not yet filled


# --------------------------------------------------------------------------
# provenance + window completeness + job status
# --------------------------------------------------------------------------
def test_seeded_rows_do_not_count_as_captures(engine):
    """The CSV seed leaves n_contracts NULL; only a real 15:05 capture sets
    it. That column is the ONLY way to answer 'has the capture ever run?',
    which the page was asserting an answer to without one."""
    days = _weekdays(date(2026, 8, 14), 5)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)      # seed-shaped rows
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["captured_sessions"] == 0
    assert f["last_capture_date"] is None
    assert f["latest_is_capture"] is False


def test_a_captured_row_is_recognised(engine):
    days = _weekdays(date(2026, 8, 14), 5)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {GAMMA_DAILY_TABLE} SET n_contracts = 4821 "
            "WHERE trade_date = :d"), {"d": days[-1].isoformat()})
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["captured_sessions"] == 1
    assert f["last_capture_date"] == date(2026, 8, 14)
    assert f["latest_is_capture"] is True


def test_a_hole_in_the_window_is_found_via_the_vix_calendar(engine):
    """Gaps are differenced against sw_vix_daily, not counted as weekdays, so
    a market holiday cannot masquerade as a missing session."""
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 5)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    hole = days[-3]
    with engine.begin() as conn:                    # gamma loses a day, VIX keeps it
        conn.execute(text(f"DELETE FROM {GAMMA_DAILY_TABLE} WHERE trade_date = :d"),
                     {"d": hole.isoformat()})
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["window_complete"] is False
    assert hole in f["window_missing"]


def test_a_holiday_is_not_a_hole(engine):
    """A day absent from BOTH series is a market holiday, not a gap."""
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 5)
    holiday = days[-4]
    kept = [d for d in days if d != holiday]
    _seed(engine, kept, lambda d: 1e9, lambda d: 15.0)
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["window_missing"] == []
    assert f["window_complete"] is True


def test_job_status_reports_never_ran_rather_than_ran_fine(engine):
    from backend.db import Base
    from backend import models  # noqa: F401
    from backend.bots.gamma_regime import job_status
    Base.metadata.create_all(engine)
    s = job_status(engine)
    assert s["reason"] is None
    assert s["last"] == {}                       # empty = never fired, not "ok"

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO discord_post_log (message_key, fire_date, posted_at) "
            "VALUES ('gamma_capture', :d, CURRENT_TIMESTAMP)"),
            {"d": date(2026, 8, 17).isoformat()})
    s = job_status(engine)
    assert s["last"]["gamma_capture"] == date(2026, 8, 17)
    assert "squeeze_signal" not in s["last"]


def test_job_status_on_a_missing_table_is_unknown_not_healthy():
    from sqlalchemy import create_engine as ce
    from backend.bots.gamma_regime import job_status
    s = job_status(ce("sqlite:///:memory:", future=True))
    assert s["reason"] is not None
    assert s["last"] == {}


# --------------------------------------------------------------------------
# phantom-session prune in the VIX seed
# --------------------------------------------------------------------------
def _run_vix_seed(engine, tmp_path, csv_rows):
    """Point the seed at a scratch CSV and run it against `engine`."""
    import backend.gamma_alerts as ga
    p = tmp_path / "vix_baseline.csv"
    p.write_text("d,vix\n" + "\n".join(f"{d},{v}" for d, v in csv_rows) + "\n")
    old = ga.VIX_BASELINE_CSV
    ga.VIX_BASELINE_CSV = p
    try:
        ga._auto_seed_vix_from_csv(engine)
    finally:
        ga.VIX_BASELINE_CSV = old


def test_a_holiday_row_with_no_trading_session_is_pruned(engine, tmp_path):
    """The real case: ThetaData's index feed published VIX on Memorial Day
    2026-05-25, a date SPY has no session for. ON CONFLICT DO NOTHING can add
    a row and never remove one, so the bad date survived every re-seed."""
    from backend.bots.vix_regime import VIX_DAILY_TABLE
    days = [date(2026, 5, 22), date(2026, 5, 26)]
    _seed(engine, days, lambda d: 1e9)                    # gamma: no 05-25
    with engine.begin() as conn:                          # phantom already live
        conn.execute(text(
            f"INSERT INTO {VIX_DAILY_TABLE} (trade_date, vix, updated_at) "
            "VALUES ('2026-05-25', 16.59, CURRENT_TIMESTAMP)"))

    _run_vix_seed(engine, tmp_path, [("2026-05-22", "16.7"), ("2026-05-26", "17.01")])

    with engine.begin() as conn:
        left = [r[0] for r in conn.execute(text(
            f"SELECT trade_date FROM {VIX_DAILY_TABLE} ORDER BY trade_date")).fetchall()]
    assert "2026-05-25" not in [str(x) for x in left]
    assert len(left) == 2


def test_prune_cannot_delete_a_real_session(engine, tmp_path):
    """A date missing from the VIX CSV but PRESENT in sw_gamma_daily is a real
    trading day the CSV simply lacks. Deleting it would be the destructive
    failure this guard exists to prevent."""
    from backend.bots.vix_regime import VIX_DAILY_TABLE
    days = [date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)]
    _seed(engine, days, lambda d: 1e9)                    # gamma HAS all three
    with engine.begin() as conn:
        for d, v in (("2026-07-20", 18.65), ("2026-07-21", 17.05), ("2026-07-22", 16.64)):
            conn.execute(text(
                f"INSERT INTO {VIX_DAILY_TABLE} (trade_date, vix, updated_at) "
                "VALUES (:d, :v, CURRENT_TIMESTAMP)"), {"d": d, "v": v})

    # CSV omits 07-21 and 07-22 entirely
    _run_vix_seed(engine, tmp_path, [("2026-07-20", "18.65")])

    with engine.begin() as conn:
        left = {str(r[0]) for r in conn.execute(text(
            f"SELECT trade_date FROM {VIX_DAILY_TABLE}")).fetchall()}
    assert left == {"2026-07-20", "2026-07-21", "2026-07-22"}


def test_prune_never_touches_rows_beyond_the_csv_span(engine, tmp_path):
    """Captures written after the baseline's last date must survive."""
    from backend.bots.vix_regime import VIX_DAILY_TABLE
    _seed(engine, [date(2026, 8, 14)], lambda d: 1e9)
    with engine.begin() as conn:
        for d, v in (("2026-08-14", 14.25), ("2026-08-17", 14.10)):
            conn.execute(text(
                f"INSERT INTO {VIX_DAILY_TABLE} (trade_date, vix, updated_at) "
                "VALUES (:d, :v, CURRENT_TIMESTAMP)"), {"d": d, "v": v})

    _run_vix_seed(engine, tmp_path, [("2026-08-14", "14.25")])   # span ends 08-14

    with engine.begin() as conn:
        left = {str(r[0]) for r in conn.execute(text(
            f"SELECT trade_date FROM {VIX_DAILY_TABLE}")).fetchall()}
    assert "2026-08-17" in left       # beyond the span, untouched


def test_committed_vix_baseline_has_no_phantom_sessions():
    """Regression on the shipped data itself: every date in vix_baseline.csv
    that falls inside gamma_baseline.csv's span must be a real session."""
    import csv as _csv
    from pathlib import Path
    D = Path(__file__).resolve().parent.parent / "backend" / "data"

    def load(name):
        out = set()
        with open(D / name, newline="") as f:
            for r in _csv.reader(f):
                if r and r[0] != "d":
                    out.add(date.fromisoformat(r[0]))
        return out

    g, v = load("gamma_baseline.csv"), load("vix_baseline.csv")
    lo, hi = max(min(g), min(v)), min(max(g), max(v))
    phantom = sorted(d for d in v if lo <= d <= hi and d not in g)
    missing = sorted(d for d in g if lo <= d <= hi and d not in v)
    assert phantom == [], f"VIX rows on non-trading days: {phantom}"
    assert missing == [], f"trading days with no VIX row: {missing}"
