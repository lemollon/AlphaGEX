"""The ticket alert — the one Discord push that carries an ORDER.

Every other risk alert reports market state. This one hands over a strike
pair and an expiration at the moment the entry window opens, so these tests
guard the things that would make it useless: a missing strike, a silent
failure at an open window, a duplicate ping, and clocks drifting away from
the registry the strategy is actually defined by.
"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

from backend import risk_alerts as ra


class _Scheduler:
    """Records add_job calls so the registered crons can be asserted on."""

    def __init__(self):
        self.jobs = {}

    def add_job(self, fn, trigger, **kw):
        self.jobs[kw.get("id")] = {"fn": fn, "trigger": trigger, **kw}


@pytest.fixture
def harness(monkeypatch):
    """Register the alerts with Discord and the dedupe log stubbed out."""
    sent: list[dict] = []
    claimed: set = set()

    monkeypatch.setattr(ra, "_send",
                        lambda embed, ping=False: sent.append({"embed": embed, "ping": ping}) or True)

    def _claim(key, fire_date):
        if (key, fire_date) in claimed:
            return False
        claimed.add((key, fire_date))
        return True

    import backend as _b
    monkeypatch.setattr(_b, "_claim_post_slot_db", _claim, raising=False)

    sched = _Scheduler()
    ra.register_risk_alerts(sched, object())
    return sched, sent, claimed


def _fire(sched, job_id):
    j = sched.jobs[job_id]
    asyncio.run(j["fn"](*j.get("args", [])))


def _stub_recipe(monkeypatch, payload):
    import backend.routes_risk as rr

    async def _fake(_request):
        return payload
    monkeypatch.setattr(rr, "recipe", _fake)


def _weekday(monkeypatch, hour=10, minute=5):
    """Pin 'now' to a Thursday inside the AM window."""
    import datetime as _dt

    class _Now(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 13, hour, minute, tzinfo=tz)
    monkeypatch.setattr(ra, "datetime", _Now)


OK = {"status": "ok", "spot": 641.37, "expiration": "2026-08-13",
      "short_strike": 639, "long_strike": 634, "credit_now": 0.18,
      "meets_floor": True, "floor": 0.10}


def test_both_entry_windows_get_a_ticket_job(harness):
    sched, _, _ = harness
    assert "risk_recipe_am" in sched.jobs
    assert "risk_recipe_pm" in sched.jobs


def test_ticket_clocks_come_from_the_registry_not_a_hardcoded_copy(harness):
    """A registry edit to ebb/ebb_pm entry_start_ct must move the alert.

    A hardcoded 10:05 would silently keep firing at the old time after the
    strategy's window moved — the alert would then be advertising a ticket
    outside its validated window.
    """
    from backend.routes_risk import _recipe_windows
    (am_h, am_m), _, (pm_h, pm_m), _ = _recipe_windows()

    sched, _, _ = harness
    assert (sched.jobs["risk_recipe_am"]["hour"],
            sched.jobs["risk_recipe_am"]["minute"]) == (am_h, am_m)
    assert (sched.jobs["risk_recipe_pm"]["hour"],
            sched.jobs["risk_recipe_pm"]["minute"]) == (pm_h, pm_m)


def test_ticket_carries_the_strike_pair_and_the_expiration(harness, monkeypatch):
    """The entire point of the alert. Without these it is just noise."""
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")

    assert len(sent) == 1
    body = sent[0]["embed"]["description"]
    assert "SELL SPY 639P" in body
    assert "BUY SPY 634P" in body
    assert "2026-08-13" in body
    assert sent[0]["ping"] is True


def test_a_credit_below_the_validated_floor_says_skip(harness, monkeypatch):
    """The floor is the difference between the edge and no edge — a ticket
    that quietly showed a sub-floor credit would get sent anyway."""
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, {**OK, "credit_now": 0.04, "meets_floor": False})

    _fire(sched, "risk_recipe_am")

    body = sent[0]["embed"]["description"]
    assert "BELOW" in body and "SKIP" in body
    assert sent[0]["embed"]["color"] == ra.RED


def test_an_unpriceable_window_still_says_something(harness, monkeypatch):
    """Silence at an open window reads as 'no trade today'.

    That is a different and wrong message — the trade exists, we just could
    not price it. It posts without a ping.
    """
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, {"status": "no quote"})

    _fire(sched, "risk_recipe_am")

    assert len(sent) == 1
    assert "unavailable" in sent[0]["embed"]["title"]
    assert sent[0]["ping"] is False


def test_the_ticket_cannot_double_ping_on_a_redeploy(harness, monkeypatch):
    """Replicas and restarts re-run the job; the dedupe log must hold."""
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")
    _fire(sched, "risk_recipe_am")

    assert len(sent) == 1


def test_am_and_pm_dedupe_independently(harness, monkeypatch):
    """Two windows, two tickets — the PM push must not be swallowed by the
    AM slot already being claimed for the same date."""
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")
    _fire(sched, "risk_recipe_pm")

    assert len(sent) == 2
    assert sent[0]["embed"]["title"].startswith("\U0001f4c4 AM")
    assert sent[1]["embed"]["title"].startswith("\U0001f4c4 PM")


def test_both_tickets_ping_here(harness, monkeypatch):
    """The @here on the ticket is a confirmed decision, not an accident.

    It is a deliberate exception to this module's scarcity rule — Leron was
    offered the quiet unpinged variant on 2026-08-14 and chose to keep the
    ping, because the strike and expiration were previously invisible unless
    you went and opened the page. This test exists so a future tidy-up of
    "too many pings" fails here and has to be a decision rather than a drive-by.
    """
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")
    _fire(sched, "risk_recipe_pm")

    assert [s["ping"] for s in sent] == [True, True]


def test_no_ticket_on_a_weekend(harness, monkeypatch):
    sched, sent, _ = harness
    import datetime as _dt

    class _Sat(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 15, 10, 5, tzinfo=tz)   # Saturday
    monkeypatch.setattr(ra, "datetime", _Sat)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")
    assert sent == []


def test_the_no_stop_no_target_rule_rides_along_with_every_ticket(harness, monkeypatch):
    """Every tested exit collapses this edge to ~$0, so the rule travels with
    the order rather than living only on a page the reader may not open."""
    sched, sent, _ = harness
    _weekday(monkeypatch)
    _stub_recipe(monkeypatch, OK)

    _fire(sched, "risk_recipe_am")

    body = sent[0]["embed"]["description"]
    assert "NO stop-loss" in body and "NO profit-target" in body
    assert "Do NOT skip flagged days" in body
