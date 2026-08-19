"""Unit tests for the rolling flow watcher (registry #39, validated
2026-08-13): a 10-minute poll across 10:36-14:00 CT that catches spikes the
fixed 10:00/12:00/13:30 CT clocks miss, without duplicating them.

Two layers are tested:
  * the pure baseline-lookup helpers in backend.routes_risk (module-level,
    directly callable — same style as test_pm_clocks.py)
  * the actual scheduler job's behavior (crossing/no-crossing/suppression/
    claim-after-fetch) via a fake scheduler that records add_job() calls,
    since the job itself is a closure inside register_risk_alerts() and not
    otherwise reachable — test_risk_alerts_new_jobs.py's docstring notes
    full job behavior is normally only "exercised live"; this fakes just
    enough of the scheduler/app surface to run it for real.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from freezegun import freeze_time

from backend import risk_alerts, routes_risk

BASELINE = {"put_mean": 1_000_000.0, "put_sd": 100_000.0,
           "tot_mean": 2_000_000.0, "tot_sd": 200_000.0}


# ─── baseline-minute lookup (pure functions, no fakes needed) ───────────────

def test_baseline_loads_and_covers_the_full_window():
    baseline = routes_risk._rolling_baseline()
    assert 696 in baseline and 900 in baseline
    for k in ("put_mean", "put_sd", "tot_mean", "tot_sd"):
        assert k in baseline[696]


def test_ct_to_et_minute_matches_documented_convention():
    # window doc: 696-900 = 10:36-14:00 CT; 571 = 09:31 ET
    assert routes_risk._ct_to_et_minute((10, 36)) == 696
    assert routes_risk._ct_to_et_minute((14, 0)) == 900


def test_rolling_baseline_at_lower_window_edge():
    row = routes_risk._rolling_baseline_at(datetime(2026, 8, 13, 10, 36))
    assert row == routes_risk._rolling_baseline()[696]


def test_rolling_baseline_at_upper_window_edge():
    row = routes_risk._rolling_baseline_at(datetime(2026, 8, 13, 14, 0))
    assert row == routes_risk._rolling_baseline()[900]


def test_rolling_baseline_at_picks_nearest_minute_at_or_before():
    # 10:41 CT -> ET minute 701; baseline has no gaps in this range so the
    # exact-match branch is what actually executes, but the assertion also
    # proves "at-or-before" semantics (never a later, unreached minute).
    now = datetime(2026, 8, 13, 10, 41)
    row = routes_risk._rolling_baseline_at(now)
    et_minute = routes_risk._ct_to_et_minute((10, 41))
    assert row == routes_risk._rolling_baseline()[et_minute]
    nearest_key = max(k for k in routes_risk._rolling_baseline() if k <= et_minute)
    assert row == routes_risk._rolling_baseline()[nearest_key]


def test_rolling_baseline_now_reaches_the_open_and_the_close():
    """CHANGED 2026-08-19. The baseline used to start at ET 696 (10:36 CT) and
    stop at 900 (14:00), so this returned None at 09:00 and the tape simply
    recorded nothing for 41% of the session — including the last hour, when
    0DTE gamma peaks and EBB settles at the close. That was never a data
    limit: bt_spy carries ~900 sessions at every minute 571-959.

    The poll returns early on a missing baseline row, so a short baseline is
    indistinguishable from a working one — it just quietly logs nothing."""
    for h, m in ((9, 0), (8, 40), (14, 30), (14, 55)):
        row = routes_risk._rolling_baseline_at(datetime(2026, 8, 13, h, m))
        assert row is not None, f"no baseline at {h:02d}:{m:02d} CT"
        assert row["pc_sd"], f"no MIX baseline at {h:02d}:{m:02d} CT"


def test_rolling_baseline_at_before_the_open_still_returns_none():
    """Pre-open there is genuinely nothing to grade against."""
    assert routes_risk._rolling_baseline_at(datetime(2026, 8, 13, 7, 0)) is None


def test_rolling_z_matches_manual_calc():
    assert routes_risk._rolling_z(1_300_000.0, 1_000_000.0, 100_000.0) == 3.0
    assert routes_risk._rolling_z(1_000_000.0, 1_000_000.0, 0.0) is None


# ─── job behavior (crossing / suppression / claim-after-fetch) ─────────────

class _FakeScheduler:
    """Records add_job() calls so a test can invoke a job's closure
    directly — mirrors what APScheduler would do at runtime, minus actually
    scheduling anything."""
    def __init__(self):
        self.jobs = {}

    def add_job(self, func, *_args, **kwargs):
        self.jobs[kwargs["id"]] = (func, kwargs.get("args") or [])


def _wire(monkeypatch, snap, baseline=BASELINE, already_posted_keys=()):
    """Registers the real risk_alerts jobs against a fake scheduler, with
    the DB-touching pieces swapped for in-memory fakes so the test exercises
    the actual decision logic (threshold, suppression, claim-after-fetch)
    without a database."""
    claimed: set[tuple[str, date]] = set()

    def fake_claim(key, fire_date):
        # mirrors the real INSERT..ON CONFLICT semantics: True only the
        # FIRST time a (key, date) slot is claimed.
        slot = (key, fire_date)
        if slot in claimed:
            return False
        claimed.add(slot)
        return True

    monkeypatch.setattr("backend._claim_post_slot_db", fake_claim)

    sched = _FakeScheduler()
    app = SimpleNamespace(state=SimpleNamespace(http=None))
    risk_alerts.register_risk_alerts(sched, app)
    func, args = sched.jobs["risk_flow_rolling"]

    async def fake_flow_now(_request):
        return snap

    monkeypatch.setattr(routes_risk, "_rolling_flow_now", fake_flow_now)
    monkeypatch.setattr(routes_risk, "_rolling_baseline_at",
                        lambda _now: baseline)

    saved = []
    monkeypatch.setattr(routes_risk, "_save_rolling_state",
                        lambda d, ts, pz, tz: saved.append((d, ts, pz, tz)))

    monkeypatch.setattr(risk_alerts, "_already_posted",
                        lambda key, _d: key in already_posted_keys)

    sent = []

    def fake_send(embed, ping=False):
        sent.append((embed, ping))
        return True

    monkeypatch.setattr(risk_alerts, "_send", fake_send)

    return func, args, claimed, saved, sent


SPIKE_SNAP = {"putv": 1_300_000, "totv": 2_100_000, "spot": 550.0}  # put z=3
CALM_SNAP = {"putv": 1_000_000, "totv": 2_000_000, "spot": 550.0}   # z=0


@freeze_time("2026-08-13 16:00:00")   # 11:00 CT (CDT, UTC-5), a Thursday
async def test_crossing_fires_once_and_only_once(monkeypatch):
    func, args, claimed, saved, sent = _wire(monkeypatch, SPIKE_SNAP)
    await func(*args)
    assert len(sent) == 1
    embed, ping = sent[0]
    assert ping is True
    assert "registry #39" in embed["description"] or "registry #39" in embed["footer"]["text"]
    assert ("risk_flow_rolling", date(2026, 8, 13)) in claimed

    # second poll in the same session, still a spike reading -> no 2nd push
    await func(*args)
    assert len(sent) == 1


@freeze_time("2026-08-13 16:00:00")
async def test_no_fire_when_both_z_below_2(monkeypatch):
    func, args, claimed, saved, sent = _wire(monkeypatch, CALM_SNAP)
    await func(*args)
    assert sent == []
    assert claimed == set()
    # the live reading is still persisted for /state even when it doesn't fire
    assert len(saved) == 1
    assert saved[0][2] == 0.0 and saved[0][3] == 0.0


@freeze_time("2026-08-13 16:00:00")
async def test_suppressed_when_fixed_clock_already_spiked(monkeypatch):
    func, args, claimed, saved, sent = _wire(
        monkeypatch, SPIKE_SNAP, already_posted_keys={"risk_flow_spike"})
    await func(*args)
    assert sent == []
    # suppression must not steal the slot either — a later real spike (if
    # the fixed clocks somehow didn't cover it) should still be postable
    assert claimed == set()


@freeze_time("2026-08-13 16:00:00")
async def test_suppressed_by_either_pm_clock(monkeypatch):
    func, args, claimed, saved, sent = _wire(
        monkeypatch, SPIKE_SNAP, already_posted_keys={"risk_pm_1200"})
    await func(*args)
    assert sent == []
    func2, args2, claimed2, saved2, sent2 = _wire(
        monkeypatch, SPIKE_SNAP, already_posted_keys={"risk_pm_1330"})
    await func2(*args2)
    assert sent2 == []


@freeze_time("2026-08-13 16:00:00")
async def test_slot_claimed_only_after_successful_fetch(monkeypatch):
    # fetch fails (Tradier hiccup) -> no claim, no save, no post
    func, args, claimed, saved, sent = _wire(monkeypatch, None)
    await func(*args)
    assert sent == []
    assert saved == []
    assert claimed == set()


@freeze_time("2026-08-13 15:00:00")   # 10:00 CT — inside the tape window,
                                      # outside the 10:36 ALERT window
async def test_outside_the_alert_window_records_but_never_pushes(monkeypatch):
    """🚨 THE SPLIT, pinned. Registry #39's 1.53x lift was measured on
    10:36-14:00, so a spike at 10:00 must NOT push — nobody has measured what
    an early crossing is worth. But it must still be RECORDED, because a
    session you cannot replay is one you cannot improve, and that is the whole
    reason risk_session_log exists.

    Before 2026-08-19 this asserted `saved == []` — the tape was as blind as
    the alert."""
    func, args, claimed, saved, sent = _wire(monkeypatch, SPIKE_SNAP)
    await func(*args)
    assert sent == [], "a spike outside the measured window must not push"
    assert saved != [], "…but it must still land on the tape"
    assert claimed == set(), "and must not burn the day's alert slot"


@freeze_time("2026-08-15 16:00:00")   # a Saturday
async def test_weekend_does_nothing(monkeypatch):
    func, args, claimed, saved, sent = _wire(monkeypatch, SPIKE_SNAP)
    await func(*args)
    assert sent == []
    assert saved == []
