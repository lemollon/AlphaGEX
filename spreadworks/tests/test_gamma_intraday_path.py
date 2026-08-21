"""The intraday gamma path — stored, so the session leaves a record.

🚨 THE LIVE READING WAS EPHEMERAL. /squeeze/intraday computed net gamma from
the live chain and the page polled it every 60s, but nothing was persisted: the
chart had one dot for "now", no path through the session, and nothing at all
once the market shut. The session you just traded left no trace.

⛔ AND IT IS CONTEXT, NOT THE SIGNAL. The verdict stays on the 15:05 capture.
An intraday sample lands in the wrong percentile zone 21.6% of the time against
its own session's close, and ~5% of sessions would flash a false "oversold" the
close then retracts.
"""
import inspect

from backend import gamma_alerts, routes_squeeze as R


def test_the_writer_is_a_scheduled_job_not_a_page_hook():
    """A store that only fills while somebody is looking makes the record a
    function of who was watching — the defect that left risk_flow_rolling_state
    unable to explain the 2026-08-17 slide."""
    src = inspect.getsource(gamma_alerts.register_gamma_alerts)
    assert "record_intraday_gamma" in src
    i = src.index('id="gamma_intraday"')
    seg = src[max(0, i - 400):i]
    assert 'minute="*/10"' in seg
    assert 'day_of_week="mon-fri"' in seg


def test_the_job_is_reported_by_scheduled_jobs():
    """Otherwise the chart cannot say when its next point lands."""
    assert "gamma_intraday" in gamma_alerts.GAMMA_JOB_IDS


def test_the_writer_refuses_outside_the_session():
    """⛔ Out of hours Tradier serves stale quotes, and a fresh pull of stale
    marks is not a reading — the trap /intraday already documents in prose."""
    src = inspect.getsource(gamma_alerts.register_gamma_alerts)
    i = src.index("async def record_intraday_gamma")
    seg = src[i:i + 1800]
    assert "weekday() >= 5" in seg
    assert "dtime(8, 30)" in seg and "dtime(15, 0)" in seg


def test_the_window_includes_the_1500_close():
    """⛔ `< 15:00` makes 14:50 the last */10 tick, leaving the closing ten
    minutes unrecorded — the most informative reading of the day and the one
    nearest the 15:05 capture. Same blind spot the /session tape had at
    14:00-15:00."""
    src = inspect.getsource(gamma_alerts.register_gamma_alerts)
    i = src.index("async def record_intraday_gamma")
    seg = src[i:i + 2200]
    assert "<= dtime(15, 0)" in seg, "the 15:00 close must be inside the window"
    assert "now.time() < dtime(15, 0)" not in seg


def test_points_are_bucketed_so_a_retry_updates_rather_than_duplicates():
    src = inspect.getsource(R.record_gamma_intraday)
    assert "// 10) * 10" in src, "must bucket to a 10-minute slot"
    assert "ON CONFLICT" in src, "a retry in the same slot must update, not insert"


def test_a_null_reading_is_never_stored():
    """A missing chain must leave a hole, not a zero — a zero would plot as a
    real gamma reading of nothing."""
    src = inspect.getsource(R.record_gamma_intraday)
    assert "if net_gex_b is None:" in src


def test_the_path_endpoint_never_pulls_a_chain():
    """It serves what the job recorded. If it pulled, every page load would
    cost ~40 Tradier requests and the 60s cache would be pointless."""
    src = inspect.getsource(R.intraday_path)
    for forbidden in ("fetch_net_gex", "build_live_chain_provider"):
        assert forbidden not in src


def test_the_path_endpoint_degrades_to_empty_not_an_error():
    src = inspect.getsource(R.intraday_path)
    assert '"rows": []' in src and "reason" in src
