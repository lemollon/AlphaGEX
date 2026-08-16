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


# --------------------------------------------------------------------------
# capture_health — the dedup ledger records a CLAIM, not a SUCCESS
# --------------------------------------------------------------------------
def test_never_run_is_its_own_state():
    from backend.bots.gamma_regime import capture_health
    h = capture_health({"last_capture_date": None}, {"last": {}, "reason": None})
    assert h["state"] == "never_run"


def test_claimed_but_nothing_stored_is_caught():
    """capture_gamma calls _dedup_ok BEFORE it pulls the chain, so a capture
    that claims the slot and then dies leaves a ledger entry and no row. A
    naive 'last fired' readout would call that healthy."""
    from backend.bots.gamma_regime import capture_health
    h = capture_health({"last_capture_date": None},
                       {"last": {"gamma_capture": date(2026, 8, 17)}, "reason": None})
    assert h["state"] == "claimed_but_not_stored"
    assert "wrote nothing." in h["detail"]

    # stored, but older than the claim -> today's run still failed
    h = capture_health({"last_capture_date": date(2026, 8, 14)},
                       {"last": {"gamma_capture": date(2026, 8, 17)}, "reason": None})
    assert h["state"] == "claimed_but_not_stored"


def test_claim_matched_by_a_stored_row_is_ok():
    from backend.bots.gamma_regime import capture_health
    h = capture_health({"last_capture_date": date(2026, 8, 17)},
                       {"last": {"gamma_capture": date(2026, 8, 17)}, "reason": None})
    assert h["state"] == "ok"


def test_a_failed_lookup_is_unknown_not_ok():
    from backend.bots.gamma_regime import capture_health
    h = capture_health({"last_capture_date": None},
                       {"last": {}, "reason": "table missing"})
    assert h["state"] == "unknown"


# --------------------------------------------------------------------------
# /state must always answer
# --------------------------------------------------------------------------
def test_state_never_422s_on_a_bad_sessions_param(engine, monkeypatch):
    """Declared as `int`, FastAPI rejects ?sessions=abc with a 422 before any
    clamp can run — which blanks the page, the exact failure this endpoint's
    contract exists to prevent."""
    import asyncio
    import backend.routes_squeeze as rs
    from backend.db import Base
    from backend import models  # noqa: F401
    Base.metadata.create_all(engine)
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 30)
    _seed(engine, days, lambda d: float(days.index(d)) * 1e8, lambda d: 15.0)
    monkeypatch.setattr(rs, "ENGINE", engine)

    for bad in ("abc", "", "1e9", None, "12.5"):
        out = asyncio.run(rs.state(sessions=bad))
        assert out["verdict"] is not None
        assert len(out["history"]) >= 1, f"blanked on sessions={bad!r}"

    assert len(asyncio.run(rs.state(sessions="30"))["history"]) == 30
    assert len(asyncio.run(rs.state(sessions="-5"))["history"]) == 1
    assert len(asyncio.run(rs.state(sessions="99999"))["history"]) <= rs.MAX_HISTORY_ROWS


def test_intraday_does_not_pull_the_chain_when_the_market_is_shut(monkeypatch):
    """~40 chain requests, cached 60s, for a number that cannot change — and
    out of hours Tradier serves stale quotes that the strip rendered as a
    live move."""
    import asyncio
    import backend.routes_squeeze as rs

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("fetch_net_gex must not run while the market is shut")

    monkeypatch.setattr(rs, "_INTRADAY_CACHE", {"ts": 0.0, "payload": None})
    monkeypatch.setattr("backend.bots.gamma_regime.fetch_net_gex", _boom)

    class _Sat(rs.datetime):
        @classmethod
        def now(cls, tz=None):
            return rs.datetime(2026, 8, 15, 12, 0, tzinfo=rs.CT)   # Saturday
    monkeypatch.setattr(rs, "datetime", _Sat)

    out = asyncio.run(rs.intraday())
    assert called["n"] == 0
    assert out["stale"] is True
    assert out["net_gex_b"] is None
    assert out["reason"] == "market_closed"


# --------------------------------------------------------------------------
# scheduled_jobs — "never run" is ambiguous without it
# --------------------------------------------------------------------------
def test_unarmed_scheduler_is_distinguishable_from_not_yet_fired():
    """A scheduler that failed to start and a job that simply has not reached
    its first firing are identical in the ledger. They are not the same
    problem: one needs a fix, the other needs patience."""
    import backend.gamma_alerts as ga
    old = ga._SCHEDULER.get("ref")
    ga._SCHEDULER["ref"] = None
    try:
        s = ga.scheduled_jobs()
        assert s["registered"] is False
        assert "not armed" in s["reason"] and s["reason"].endswith(".")
    finally:
        ga._SCHEDULER["ref"] = old


def test_armed_scheduler_reports_each_job_next_run():
    import backend.gamma_alerts as ga

    class _Job:
        def __init__(self, nxt): self.next_run_time = nxt

    class _Sched:
        def get_job(self, jid):
            return _Job(datetime(2026, 8, 17, 15, 5, tzinfo=ga.CT)) \
                if jid == "gamma_capture" else None

    from datetime import datetime
    old = ga._SCHEDULER.get("ref")
    ga._SCHEDULER["ref"] = _Sched()
    try:
        s = ga.scheduled_jobs()
        assert s["registered"] is True
        assert s["jobs"]["gamma_capture"].startswith("2026-08-17T15:05")
        assert s["jobs"]["gamma_squeeze_alert"] is None      # armed but no job
    finally:
        ga._SCHEDULER["ref"] = old


def test_scheduled_jobs_never_raises():
    import backend.gamma_alerts as ga

    class _Bad:
        def get_job(self, jid): raise RuntimeError("apscheduler internals moved")

    old = ga._SCHEDULER.get("ref")
    ga._SCHEDULER["ref"] = _Bad()
    try:
        s = ga.scheduled_jobs()
        assert s["registered"] is True
        assert s["reason"] is not None
    finally:
        ga._SCHEDULER["ref"] = old


# --------------------------------------------------------------------------
# the Discord alert must never post a trade off an unfit signal
# --------------------------------------------------------------------------
def _block_reason(fresh, cap, sched):
    """Mirror of the health gate's precedence in fire_squeeze_alert."""
    if sched.get("registered") is False:
        return "not scheduled"
    if cap.get("state") == "claimed_but_not_stored":
        return "stored nothing"
    if fresh.get("stale"):
        return "sessions behind"
    if fresh.get("window_complete") is False:
        return "missing session"
    return None


def test_the_2026_08_15_case_would_now_be_blocked_not_posted():
    """The real failure: gamma four sessions old still resolved to
    SELL_PREMIUM, so the 08:05 job would have posted a clean, confident trade
    recommendation off stale data with nothing marking it stale."""
    fresh = {"stale": True, "gamma_date": "2026-08-11", "gamma_stale_sessions": 3,
             "expected_date": "2026-08-14", "window_complete": True}
    cap = {"state": "never_run"}
    sched = {"registered": True}
    assert _block_reason(fresh, cap, sched) == "sessions behind"


def test_unarmed_scheduler_outranks_everything():
    assert _block_reason({"stale": False, "window_complete": True},
                         {"state": "ok"}, {"registered": False}) == "not scheduled"


def test_a_failed_capture_blocks_even_when_data_looks_fresh():
    """freshness alone cannot catch this on day one — the data is only one
    session old, so `stale` is False while the job is in fact dead."""
    assert _block_reason({"stale": False, "window_complete": True},
                         {"state": "claimed_but_not_stored"},
                         {"registered": True}) == "stored nothing"


def test_a_hole_in_the_window_blocks():
    assert _block_reason({"stale": False, "window_complete": False,
                          "window_missing": ["2026-08-13"]},
                         {"state": "ok"}, {"registered": True}) == "missing session"


def test_a_healthy_signal_is_not_blocked():
    assert _block_reason({"stale": False, "window_complete": True},
                         {"state": "ok"}, {"registered": True}) is None


# --------------------------------------------------------------------------
# source mixing — a percentile must not rank two different measurements
# --------------------------------------------------------------------------
def test_an_all_seeded_window_is_not_mixed(engine):
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 5)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["window_captured"] == 0
    assert f["window_source_mixed"] is False


def test_one_captured_row_makes_the_window_mixed(engine):
    """The moment the 15:05 capture writes its first Tradier-derived reading
    into an ORATS-derived baseline, the percentile is ranking one kind of
    measurement inside a window of another."""
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW + 5)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {GAMMA_DAILY_TABLE} SET n_contracts = 4821 "
            "WHERE trade_date = :d"), {"d": days[-1].isoformat()})
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["window_captured"] == 1
    assert f["window_source_mixed"] is True


def test_a_fully_captured_window_is_homogeneous_again(engine):
    """Once every row in the window came from the capture, it is internally
    consistent again — mixing is a transitional state, not a permanent one."""
    days = _weekdays(date(2026, 8, 14), PCT_WINDOW)
    _seed(engine, days, lambda d: 1e9, lambda d: 15.0)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {GAMMA_DAILY_TABLE} SET n_contracts = 4821"))
    f = data_freshness(engine, date(2026, 8, 17))
    assert f["window_source_mixed"] is False


# --------------------------------------------------------------------------
# trade_ticket — actual strikes, not a formula
# --------------------------------------------------------------------------
def test_strikes_resolve_to_numbers(engine):
    """round(776.34) = 776, short 774, long 772 at $2 wide."""
    from backend.bots.gamma_regime import trade_ticket
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {GAMMA_DAILY_TABLE} "
            "(trade_date, net_gex, spot, updated_at) "
            "VALUES ('2026-08-14', 3.5e9, 776.34, '2026-01-01')"))
    t = trade_ticket(engine, date(2026, 8, 17))
    assert t["spot"] == 776.34
    assert t["spot_source"] == "2026-08-14 close"
    assert t["sell"]["short_put"] == 774
    assert t["sell"]["long_put"] == 772
    assert t["sell"]["width"] == 2


def test_a_live_spot_overrides_the_stored_close(engine):
    from backend.bots.gamma_regime import trade_ticket
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {GAMMA_DAILY_TABLE} "
            "(trade_date, net_gex, spot, updated_at) "
            "VALUES ('2026-08-14', 3.5e9, 776.34, '2026-01-01')"))
    t = trade_ticket(engine, date(2026, 8, 17), live_spot=781.90)
    assert t["spot_source"] == "live"
    assert t["sell"]["short_put"] == 780      # round(781.90)=782, -2
    assert t["sell"]["long_put"] == 778


def test_buy_side_expiries_skip_weekends(engine):
    from backend.bots.gamma_regime import trade_ticket
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {GAMMA_DAILY_TABLE} "
            "(trade_date, net_gex, spot, updated_at) "
            "VALUES ('2026-08-14', 3.5e9, 776.34, '2026-01-01')"))
    t = trade_ticket(engine, date(2026, 8, 17))     # Monday
    exp = t["buy"]["expiries"]
    assert exp, "should offer candidate expiries"
    for e in exp:
        assert date.fromisoformat(e).weekday() < 5
    assert t["buy"]["target_delta"] == 0.25


def test_no_spot_yields_nulls_not_a_plausible_strike(engine):
    """A strike invented from a missing spot is worse than no strike."""
    from backend.bots.gamma_regime import trade_ticket
    t = trade_ticket(engine, date(2026, 8, 17))
    assert t["sell"] is None and t["spot"] is None
    assert t["reason"]


# --------------------------------------------------------------------------
# the forward ledger — every other number on the page is a backtest
# --------------------------------------------------------------------------
def _ledger_engine():
    from sqlalchemy import create_engine as ce
    from backend.bots.squeeze_ledger import ensure_ledger_table
    e = ce("sqlite:///:memory:", future=True)
    ensure_gamma_table(e)
    ensure_ledger_table(e)
    return e


def _tk(spot, short, long_):
    return {"spot": spot, "sell": {"short_put": short, "long_put": long_, "width": 2}}


def test_a_stand_down_day_is_still_recorded():
    """A signal that stands down on the day of a large move is doing its job;
    a record containing only the days it traded cannot show that."""
    from backend.bots.squeeze_ledger import ledger_summary, record_decision
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NO_SELL", _tk(776.34, 774, 772),
                    traded=False, note="net gamma below -$10B")
    s = ledger_summary(e)
    assert s["n_decisions"] == 1 and s["n_traded"] == 0


def test_close_above_the_short_strike_is_a_win():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 778.10, '2026-01-01')"))
    assert settle_open(e) == 1
    s = ledger_summary(e)
    assert s["wins"] == 1 and s["win_rate"] == 1.0 and s["worst_breach"] == 0.0


def test_a_full_breach_is_a_loss_capped_at_the_width():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:                       # closes far below the long strike
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 760.00, '2026-01-01')"))
    settle_open(e)
    s = ledger_summary(e)
    assert s["losses"] == 1
    assert s["worst_breach"] == 2.0            # capped at the width, not 14


def test_a_close_between_the_strikes_is_partial():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 773.00, '2026-01-01')"))
    settle_open(e)
    s = ledger_summary(e)
    assert s["partials"] == 1 and s["worst_breach"] == 1.0


def test_settling_never_rewrites_a_settled_row():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 778.10, '2026-01-01')"))
    settle_open(e)
    record_decision(e, date(2026, 8, 17), "NO_SELL", _tk(999, 990, 988), traded=False)
    s = ledger_summary(e)
    assert s["rows"][0]["verdict"] == "NEUTRAL"     # settled row is immutable
    assert s["wins"] == 1


def test_an_unpriced_entry_leaves_pnl_null_not_zero():
    """An assumed credit would turn "we did not measure this" into a number
    someone could average. Unpriced stays unpriced."""
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 778.10, '2026-01-01')"))
    settle_open(e)                       # settled, but never priced
    s = ledger_summary(e)
    assert s["wins"] == 1                # outcome still measured
    assert s["n_priced"] == 0
    assert s["pnl_total"] is None        # NOT 0.0


def test_a_priced_win_keeps_the_whole_credit():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open, LEDGER_TABLE)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"UPDATE {LEDGER_TABLE} SET credit = 0.42 "
                       "WHERE trade_date = '2026-08-17'"))
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 778.10, '2026-01-01')"))
    settle_open(e)
    s = ledger_summary(e)
    assert s["n_priced"] == 1
    assert s["pnl_total"] == 42.0        # (0.42 - 0) * 100
    assert s["pnl_per_trade"] == 42.0


def test_a_priced_full_breach_loses_width_minus_credit():
    from backend.bots.squeeze_ledger import (ledger_summary, record_decision,
                                             settle_open, LEDGER_TABLE)
    e = _ledger_engine()
    record_decision(e, date(2026, 8, 17), "NEUTRAL", _tk(776.34, 774, 772), traded=True)
    with e.begin() as c:
        c.execute(text(f"UPDATE {LEDGER_TABLE} SET credit = 0.42 "
                       "WHERE trade_date = '2026-08-17'"))
        c.execute(text(f"INSERT INTO {GAMMA_DAILY_TABLE} "
                       "(trade_date, net_gex, spot, updated_at) "
                       "VALUES ('2026-08-17', 1e9, 760.00, '2026-01-01')"))
    settle_open(e)
    s = ledger_summary(e)
    assert s["pnl_total"] == -158.0      # (0.42 - 2.00) * 100
    assert s["worst_day"] == -158.0
