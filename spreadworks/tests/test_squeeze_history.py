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
