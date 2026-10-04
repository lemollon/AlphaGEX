"""End-to-end (mocked HTTP) test for the reactive-momentum squeeze scanner.

Drives `run_reactive_scan()` through two ticks against a SQLite engine with
every ThetaData call monkeypatched (`backend.squeeze_reactive_alerts._fetch_csv`)
to canned CSV-row data, proving the two-leg entry -> exit flow and its state
tracking work end to end without touching the real (private, Render-only)
ThetaData proxy:
  tick 1 (09:55 ET) -- entry trigger fires, a position opens.
  tick 2 (10:10 ET) -- the SAME position's money pace has faded; it closes.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine

from backend import squeeze_premarket_alerts as pm
from backend import squeeze_reactive_alerts as reactive

ET = ZoneInfo("America/New_York")
TODAY = date(2026, 10, 2)
SYMBOL = "SQZZ"


def _bar(minute_offset: int, close: float, volume: int) -> dict:
    ts = datetime(2026, 10, 2, 9, 30) + timedelta(minutes=minute_offset)
    return {"timestamp": ts.isoformat(sep=" "), "close": str(close), "volume": str(volume)}


# Bars 0-18: flat at $10.00 (no move at all). Bar 19: jumps to $11.50 (+15%
# vs the $10.00 prior close) on a huge volume spike -- the only bar in the
# first 20 minutes where BOTH the move floor and the acceleration floor are
# satisfied, so the entry trigger must land exactly here.
_ENTRY_BARS = [_bar(i, 10.0, 1_000) for i in range(19)] + [_bar(19, 11.5, 1_000_000)]

# Extend to 36 bars (through minute 35): bars 20-33 stay elevated at $11.50
# on ordinary volume (the spike is still inside the trailing 15-min window,
# so pace is still accelerating); by bar 34 the spike has rolled out of the
# trailing window entirely and pace collapses to well under the whole-
# session average -- comfortably under the 0.4x wide-fade floor.
_EXIT_BARS = _ENTRY_BARS + [_bar(i, 11.5, 1_000) for i in range(20, 36)]


def _fake_fetch_csv(url: str, params: dict):
    if url.endswith("/v3/stock/history/eod"):
        return ([{"last_trade": "2026-10-01 16:00:00", "close": "10.0"}], "ok", None)
    if url.endswith("/v3/stock/snapshot/ohlc"):
        # Stage-1 cheap screen: +15% from today's own open -- clears the 5%
        # prefilter floor easily.
        return ([{"symbol": SYMBOL, "open": "10.0", "close": "11.5"}], "ok", None)
    if url.endswith("/v3/stock/history/ohlc"):
        end_time = params["end_time"]
        if end_time <= "09:55:00":
            return (_ENTRY_BARS, "ok", None)
        return (_EXIT_BARS, "ok", None)
    if url.endswith("/v3/stock/history/quote"):
        start_time = params["start_time"]
        if start_time.startswith("09:50"):   # entry confirm window
            return ([{"timestamp": "2026-10-02 09:50:05", "ask": "11.60", "bid": "11.55"}],
                     "ok", None)
        if start_time.startswith("10:05"):   # exit confirm window (faded)
            return ([{"timestamp": "2026-10-02 10:05:10", "ask": "11.05", "bid": "11.00"}],
                     "ok", None)
        return ([], "no_data", None)
    raise AssertionError(f"unexpected URL in test: {url}")


def _seed_universe(engine):
    pm.ensure_tables(engine)
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text(
            "INSERT INTO squeeze_premarket_universe "
            "(symbol, shares_outstanding, median20_volume, as_of_date) "
            "VALUES (:s, :sh, :mv, :d)"
        ), {"s": SYMBOL, "sh": 10_000_000, "mv": 500_000, "d": TODAY})


def test_reactive_entry_then_wide_fade_exit(monkeypatch):
    engine = create_engine("sqlite://")
    _seed_universe(engine)
    monkeypatch.setattr(reactive, "_fetch_csv", _fake_fetch_csv)
    reactive._PRIOR_CLOSE_CACHE.clear()

    # ---- Tick 1: 09:55 ET -- entry should fire ----------------------------
    now1 = datetime(2026, 10, 2, 9, 55, tzinfo=ET)
    summary1 = reactive.run_reactive_scan(engine, now1)

    assert summary1["reason"] is None
    assert len(summary1["entries_opened"]) == 1
    hit = summary1["entries_opened"][0]
    assert hit["symbol"] == SYMBOL
    assert hit["entry_ask"] == 11.60
    assert abs(hit["entry_move"] - 0.15) < 1e-9
    assert hit["prior_close"] == 10.0
    assert summary1["exits_closed"] == []

    open_rows = reactive.load_open_positions(engine)
    assert SYMBOL in open_rows
    assert open_rows[SYMBOL]["entry_ask"] == 11.60

    # Discord copy renders cleanly off the real payload shape.
    alert_text = reactive._build_entry_alert(hit)
    assert "SQZZ" in alert_text and "+15%" in alert_text

    # ---- Tick 2: 10:10 ET -- the open position has faded, should exit -----
    now2 = datetime(2026, 10, 2, 10, 10, tzinfo=ET)
    summary2 = reactive.run_reactive_scan(engine, now2)

    assert summary2["reason"] is None
    assert summary2["entries_opened"] == []
    assert len(summary2["exits_closed"]) == 1
    exit_hit = summary2["exits_closed"][0]
    assert exit_hit["symbol"] == SYMBOL
    assert exit_hit["exit_reason"] == "faded"
    assert exit_hit["exit_bid"] == 11.00
    assert abs(exit_hit["raw_return"] - (11.00 / 11.60 - 1)) < 1e-9

    exit_alert_text = reactive._build_exit_alert(exit_hit)
    assert "SQZZ" in exit_alert_text and "FADED" in exit_alert_text

    # Position is now closed, no longer tracked as open, and the 30-day
    # dedupe blocks a same-day re-entry even though the universe/snapshot
    # pre-filter would still happily pass this symbol through stage 1.
    assert reactive.load_open_positions(engine) == {}
    assert reactive.already_signaled_recently(engine, SYMBOL, TODAY) is True

    summary3 = reactive.run_reactive_scan(engine, now2 + timedelta(minutes=5))
    assert summary3["entries_opened"] == []


def test_outside_regular_session_is_a_cheap_noop():
    engine = create_engine("sqlite://")
    _seed_universe(engine)
    before_hours = datetime(2026, 10, 2, 7, 0, tzinfo=ET)
    summary = reactive.run_reactive_scan(engine, before_hours)
    assert summary["reason"] == "outside the 09:30:00-16:00:00 ET regular session"
    assert summary["entries_opened"] == [] and summary["exits_closed"] == []


def test_empty_universe_reports_a_clear_reason():
    engine = create_engine("sqlite://")
    pm.ensure_tables(engine)
    during_hours = datetime(2026, 10, 2, 10, 0, tzinfo=ET)
    summary = reactive.run_reactive_scan(engine, during_hours)
    assert "squeeze_premarket_universe" in summary["reason"]
