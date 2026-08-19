"""The "next update" a chart advertises has to be one that actually does work.

The charts now publish, per plot, when their data next moves. That number comes
from apscheduler's `next_run_time`, so the SCHEDULE — not the guard inside the
job — is what the user is shown.

🚨 THE BUG THESE PIN. `capture_gamma` returns immediately on a weekend, but the
cron had no `day_of_week`. So the schedule still contained Saturday 15:05, and
from Friday afternoon until Monday the page would have told the reader its data
refreshed the next day when in truth nothing would move until Monday. A guard
that stops the WORK does not stop the SCHEDULE, and only the schedule is
published.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("apscheduler")
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

CT = ZoneInfo("America/Chicago")

# 2026-08-21 is a Friday; 08-22/23 the weekend; 08-24 the Monday.
FRIDAY_PM = datetime(2026, 8, 21, 16, 0, tzinfo=CT)
MONDAY = datetime(2026, 8, 24, 15, 5, tzinfo=CT)


def _trigger(**kw):
    return CronTrigger(timezone=CT, **kw)


def test_a_weekday_cron_skips_the_weekend_it_would_have_advertised():
    """The regression itself: standing on Friday evening, the next firing must
    be Monday, not Saturday."""
    nxt = _trigger(day_of_week="mon-fri", hour=15, minute=5) \
        .get_next_fire_time(None, FRIDAY_PM)
    assert nxt == MONDAY, f"expected Monday's capture, got {nxt}"
    assert nxt.weekday() < 5


def test_without_day_of_week_it_advertises_a_saturday_that_does_nothing():
    """Proves the fix is load-bearing rather than decorative. If this ever
    stops holding, apscheduler changed and the guard above is redundant."""
    nxt = _trigger(hour=15, minute=5).get_next_fire_time(None, FRIDAY_PM)
    assert nxt.weekday() == 5, "the un-guarded cron is supposed to hit Saturday"


@pytest.mark.parametrize("hour,minute", [(15, 5), (10, 5), (8, 5)])
def test_every_gamma_clock_is_weekday_only(hour, minute):
    """capture / entry-credit / squeeze-alert all guard weekends internally,
    so all three must be weekday-scheduled or all three publish a phantom."""
    nxt = _trigger(day_of_week="mon-fri", hour=hour, minute=minute) \
        .get_next_fire_time(None, FRIDAY_PM)
    assert nxt.weekday() < 5


def test_the_registered_jobs_actually_carry_the_weekday_restriction():
    """Reads the real registration rather than a re-declared copy of it — a
    test that rebuilds the trigger by hand passes forever after someone edits
    gamma_alerts.py."""
    import inspect

    from backend import gamma_alerts

    src = inspect.getsource(gamma_alerts.register_gamma_alerts)
    # Each add_job(...) call for a gamma cron must name day_of_week.
    calls = [c for c in src.split("scheduler.add_job(")[1:]]
    assert calls, "no add_job calls found — did registration move?"
    for c in calls:
        head = c.split(")")[0]
        assert 'day_of_week' in head, (
            "a gamma cron is scheduled without day_of_week; it will advertise "
            f"a weekend firing that returns immediately:\n{head}")


def test_scheduled_jobs_reports_unarmed_rather_than_guessing():
    """⛔ With no scheduler attached the API must say so. The UI renders that
    as 'NOT SCHEDULED'; anything that looked like a time would be a guess at
    the cron, which is exactly what this feature exists to stop trusting."""
    from backend import gamma_alerts

    saved = gamma_alerts._SCHEDULER.get("ref")
    gamma_alerts._SCHEDULER["ref"] = None
    try:
        out = gamma_alerts.scheduled_jobs()
    finally:
        gamma_alerts._SCHEDULER["ref"] = saved
    assert out["registered"] is False
    assert out["jobs"] == {}
    assert "not armed" in out["reason"]


def test_risk_exposes_the_same_contract():
    """/risk's charts read the same shape; without this the risk page silently
    falls back to 'unknown' forever."""
    from backend import risk_alerts

    saved = risk_alerts._SCHEDULER.get("ref")
    risk_alerts._SCHEDULER["ref"] = None
    try:
        out = risk_alerts.scheduled_jobs()
    finally:
        risk_alerts._SCHEDULER["ref"] = saved
    assert out["registered"] is False
    assert "not armed" in out["reason"]


def test_risk_job_ids_are_real():
    """The ids in RISK_JOB_IDS are string literals matched against apscheduler
    at runtime, so a typo degrades silently to 'unknown' instead of erroring.
    One was wrong on the first pass (risk_rolling_flow vs risk_flow_rolling)."""
    import inspect

    from backend import risk_alerts

    src = inspect.getsource(risk_alerts.register_risk_alerts)
    for jid in risk_alerts.RISK_JOB_IDS:
        assert f'id="{jid}"' in src, (
            f"{jid} is not a job this module registers — scheduled_jobs() will "
            "report it as None forever")
