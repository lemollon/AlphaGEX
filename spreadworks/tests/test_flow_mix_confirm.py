"""The two-stage flow signal added 2026-08-18, after the 2026-08-17 miss.

On 2026-08-17 SPY slid 775.50 -> 772.51 between 11:15 and 12:35 CT and every
advisory surface stayed silent while the bots kept selling put spreads. The
post-mortem found two separate failures, and these tests pin both:

STAGE 1 — WE MEASURED LEVEL, NEVER MIX.
    The shipped legs grade put volume and total volume as levels. That morning
    both were correctly quiet (put z +0.58, total z -0.45; the trigger is >2)
    because there genuinely was no put spike. What was extreme was the
    COMPOSITION: puts ordinary, call buying absent, ratio 1.487 = z +2.72, the
    highest of the trailing 63 sessions. Both numbers were already in every
    snapshot row; nobody divided them.

STAGE 2 — WE PREDICTED DIRECTION FROM A SNAPSHOT, THEN STOPPED WATCHING.
    Stage 1 cannot call direction: over 896 sessions P(down) on a flagged day
    is 45.8% against a 45.4% base, and the UP tail is the bigger one (32.4% vs
    24.3%). Asking "at 10:00, which way does the day end" is the wrong
    question. The right one is "the mix is extreme AND the market has now
    picked a side — does that side hold?" Measured over 904 sessions:

        price break alone, unflagged day     n=916    49.8% continue
        FLAGGED day, then the same break     n= 95    63.2% continue, z=+2.61

    Neither leg works alone — which is why this survives the book's standing
    "intraday continuation is dead" finding: that finding reproduces exactly
    (49.8%) and only breaks when the flow flag is present.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

CT = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# STAGE 1 — the ratio leg
# ---------------------------------------------------------------------------

def test_pc_derives_call_volume_without_a_new_capture():
    """Call volume is totv - putv. The whole point of this leg is that it
    needed NO new data collection — both numbers have been stored side by
    side in every snapshot and baseline row since the first one."""
    from backend.routes_risk import _pc
    assert _pc({"putv": 1_558_764, "totv": 2_606_761}) == pytest.approx(
        1_558_764 / 1_047_997)


def test_pc_is_none_when_call_volume_is_impossible():
    """Degenerate rows must yield None, not a divide-by-zero or a negative
    ratio that would poison the trailing baseline for 63 sessions."""
    from backend.routes_risk import _pc
    assert _pc({"putv": 100, "totv": 100}) is None      # zero calls
    assert _pc({"putv": 200, "totv": 100}) is None      # totv < putv
    assert _pc({"putv": None, "totv": 100}) is None


def test_the_2026_08_17_morning_is_flagged_by_mix_and_missed_by_level():
    """THE REGRESSION. Real captured numbers from that session against a
    synthetic-but-representative baseline: the level legs stay quiet and the
    mix leg clears 2. If this ever inverts, the alert has gone blind again in
    exactly the way it was blind on the day."""
    from backend.routes_risk import _pc_z, _z
    # 63 ordinary sessions: ~balanced flow, put/call near 1.0
    prior = [{"d": date(2026, 1, 1) + timedelta(days=i),
              "putv": 1_400_000 + (i % 7) * 40_000,
              "totv": 2_800_000 + (i % 5) * 60_000}
             for i in range(63)]
    today = {"putv": 1_558_764, "totv": 2_606_761}      # actual 10:00 CT capture

    putv_z = _z(today["putv"], [r["putv"] for r in prior])
    totv_z = _z(today["totv"], [r["totv"] for r in prior])
    mix_z = _pc_z(today, prior)

    assert putv_z < 2, "put LEVEL was not a spike — that was never the tell"
    assert totv_z < 2, "total LEVEL was below average that morning"
    assert mix_z > 2, "the MIX is the leg that should have fired"


def test_pc_z_needs_enough_history_before_it_speaks():
    """Under 40 usable prior sessions the z is undefined and must be None —
    never 0.0, which would read as 'perfectly normal' and silently disarm the
    watcher."""
    from backend.routes_risk import _pc_z
    prior = [{"d": date(2026, 1, 1) + timedelta(days=i),
              "putv": 1_000_000, "totv": 2_000_000} for i in range(20)]
    assert _pc_z({"putv": 1_500_000, "totv": 2_000_001}, prior) is None


# ---------------------------------------------------------------------------
# STAGE 2 — the confirmation watcher
# ---------------------------------------------------------------------------

@pytest.fixture
def confirm_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db import Base
    import backend.routes_risk as rr
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(rr, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    return rr


def _t(h, m):
    return datetime(2026, 8, 17, h, m, tzinfo=CT)


def test_unflagged_day_never_fires_however_far_price_moves(confirm_db):
    """Stage 2 is not a momentum signal. Without the morning mix flag the same
    break continues only 49.8% of the time — a coin flip — so it must stay
    silent no matter how big the move is."""
    rr = confirm_db
    d = date(2026, 8, 17)
    assert rr.confirm_step(d, _t(10, 10), 775.50, armed=False, pcz=0.4) is None
    for spot in (774.0, 772.0, 768.0):
        assert rr.confirm_step(d, _t(11, 0), spot, armed=False, pcz=0.4) is None


def test_flagged_day_confirms_down_and_fires_once(confirm_db):
    """The 2026-08-17 replay. Reference 775.50 at 10:00; the first poll that is
    0.10% lower AND at a session low fires DOWN — and only the first one."""
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.confirm_step(d, _t(10, 10), 775.50, armed=True, pcz=2.72)
    # drifting but not yet 0.10% through -> silent
    assert rr.confirm_step(d, _t(11, 30), 775.11, armed=True, pcz=2.72) is None
    hit = rr.confirm_step(d, _t(11, 55), 774.68, armed=True, pcz=2.72)
    assert hit is not None and hit["dir"] == "DOWN"
    assert hit["spot"] == 774.68
    # a second, lower poll must NOT re-fire — one call per session
    assert rr.confirm_step(d, _t(12, 30), 773.44, armed=True, pcz=2.72) is None


def test_a_bounce_off_the_low_does_not_confirm(confirm_db):
    """'At a session extreme' is load-bearing. A day that dips 0.10% and then
    recovers must not fire on the recovery poll — otherwise a single morning
    dip arms every subsequent poll for the rest of the day."""
    rr = confirm_db
    d = date(2026, 8, 18)
    rr.confirm_step(d, _t(10, 10), 800.00, armed=True, pcz=2.0)
    rr.confirm_step(d, _t(10, 40), 799.00, armed=True, pcz=2.0)   # sets the low
    # back up: still below the 10:00 reference by >0.10% but NOT at the low
    assert rr.confirm_step(d, _t(11, 10), 799.15, armed=True, pcz=2.0) is None


def test_up_breaks_confirm_too(confirm_db):
    """The effect is symmetric — 66.7% continuation on down breaks, 67.6% on
    up breaks, measured on disjoint samples. A down-only watcher would throw
    away half the evidence and read as a bearish tool, which it is not."""
    rr = confirm_db
    d = date(2026, 8, 19)
    rr.confirm_step(d, _t(10, 10), 700.00, armed=True, pcz=1.9)
    hit = rr.confirm_step(d, _t(11, 0), 701.00, armed=True, pcz=1.9)
    assert hit is not None and hit["dir"] == "UP"


def test_close_is_recorded_so_live_firings_carry_their_outcome(confirm_db):
    """The backtest is n=95. It only grows if every live firing is stored with
    what happened next — the 2026-08-17 post-mortem could not see the rolling
    z during the slide because that table overwrote itself all day."""
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.confirm_step(d, _t(10, 10), 775.50, armed=True, pcz=2.72)
    rr.confirm_step(d, _t(11, 55), 774.68, armed=True, pcz=2.72)
    rr.confirm_record_close(d, 772.67)
    db = rr.SessionLocal()
    row = db.get(rr.RiskConfirmState, d)
    assert row.fired_dir == "DOWN"
    assert row.fired_spot == 774.68
    assert row.close_spot == 772.67
    assert row.putcall_z == pytest.approx(2.72)
    # the outcome the row now proves: it kept going, by $2.01
    assert row.close_spot < row.fired_spot
    db.close()


# ---------------------------------------------------------------------------
# THE SESSION TAPE — append-only intraday history.
#
# risk_flow_rolling_state keeps ONE row per session and overwrites it on every
# poll, so the only surviving trace of what the watcher saw during the
# 2026-08-17 slide was its 14:00 CT reading — an hour and a half after the move
# ended. A signal you cannot replay is one you cannot improve or draw.
# ---------------------------------------------------------------------------

def test_tape_appends_one_row_per_ten_minute_slot(confirm_db):
    rr = confirm_db
    d = date(2026, 8, 17)
    for h, m, spot in ((10, 10, 775.50), (10, 22, 775.30), (10, 37, 775.10)):
        rr.session_log_write(d, _t(h, m), spot=spot)
    tape = rr.session_log_read(d)
    assert [r["minute_ct"] for r in tape] == [610, 620, 630]
    assert [r["spot"] for r in tape] == [775.50, 775.30, 775.10]


def test_two_writers_share_a_slot_without_clobbering(confirm_db):
    """The confirmation watcher has spot; the rolling watcher has the z-scores.
    They poll on the same */10 cron and must land in one row."""
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.session_log_write(d, _t(11, 0), spot=775.11)
    rr.session_log_write(d, _t(11, 3), roll_putv_z=0.57, roll_totv_z=0.06)
    tape = rr.session_log_read(d)
    assert len(tape) == 1
    assert tape[0]["spot"] == 775.11
    assert tape[0]["roll_putv_z"] == 0.57


def test_a_slot_is_never_rewritten(confirm_db):
    """Within one slot the FIRST reading is the one the alert fired from.
    Letting a later poll overwrite it desyncs the tape from the push that
    went to Discord."""
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.session_log_write(d, _t(11, 0), spot=775.11)
    rr.session_log_write(d, _t(11, 9), spot=999.99)
    assert rr.session_log_read(d)[0]["spot"] == 775.11


def test_tape_is_empty_not_broken_for_a_day_that_never_ran(confirm_db):
    """A page that cannot draw a chart still has to render its state cards."""
    assert confirm_db.session_log_read(date(2026, 8, 15)) == []

# THE PIVOT — EBB's one sanctioned early exit.
#
# Measured on 892 sessions of real expiry-day NBBO (sell bid / buy ask both
# ways). The CONTROL is the point: the identical 0.10% down-break exit applied
# WITHOUT the morning flow gate fires on 45.7% of days and loses $1,050 —
# which is exactly why "no stop by design" was right. Gated on the flow mix it
# fires on 3.7% and adds +$952 (t=+1.95), $3.13 -> $4.20/trade, ret/DD
# 2.98 -> 5.55, worst month -$581 -> -$350. Positive 4/4 years and in every
# offset/wing variant (+$778 .. +$1,517).
# ---------------------------------------------------------------------------

from datetime import date as _date, time as _time


def _exit(**kw):
    from backend.bots.monitor import decide_exit
    base = dict(strategy="bull_put_spread", mtm_pnl=-500.0,
                pt_target_pnl=14.0, sl_target_pnl=140.0,
                now_ct=datetime(2026, 8, 17, 12, 0, tzinfo=CT),
                front_expiration=_date(2026, 8, 17),
                eod_close_ct=_time(14, 45), event_blackout=False,
                settle_at_expiry=True)
    base.update(kw)
    return decide_exit(**base)


def test_settle_at_expiry_still_ignores_a_catastrophic_mark():
    """The default must be unchanged: no stop, whatever the mark says."""
    d = _exit(mtm_pnl=-9999.0)
    assert d.should_close is False and d.reason is None


def test_pivot_closes_and_is_labelled_pivot_not_sl():
    """A confirmed adverse move is the ONE thing that may buy this back — and
    it must be auditable as a PIVOT, never mixed in with SL."""
    d = _exit(pivot_confirmed=True)
    assert d.should_close is True and d.reason == "PIVOT"


def test_pivot_does_not_need_a_losing_mark():
    """It exits on the SIGNAL, not on P&L. A position still green when the
    watcher confirms against it is exactly the case a price stop misses."""
    d = _exit(mtm_pnl=+5.0, pivot_confirmed=True)
    assert d.should_close is True and d.reason == "PIVOT"


def test_pivot_direction_must_oppose_the_structure(confirm_db):
    """An UP confirmation is GOOD for a bull put spread. Treating the fire as
    bidirectional would close winners — the fastest way to turn this from an
    edge into a leak."""
    from backend.bots.scanner import _pivot_against
    rr = confirm_db
    d = _date(2026, 8, 17)
    now = datetime(2026, 8, 17, 12, 0, tzinfo=CT)
    cfg = {"pivot_on_confirm": 1}
    rr.confirm_step(d, _t(10, 10), 700.00, armed=True, pcz=2.0)
    rr.confirm_step(d, _t(11, 0), 701.00, armed=True, pcz=2.0)      # UP
    assert _pivot_against(cfg, {"strategy": "bull_put_spread"}, now) is False
    assert _pivot_against(cfg, {"strategy": "bear_call_spread"}, now) is True


def test_pivot_is_off_unless_configured(confirm_db):
    """NULL/0 means off. The fleet must never be silently armed."""
    from backend.bots.scanner import _pivot_against
    rr = confirm_db
    d = _date(2026, 8, 17)
    now = datetime(2026, 8, 17, 12, 0, tzinfo=CT)
    rr.confirm_step(d, _t(10, 10), 775.50, armed=True, pcz=2.72)
    rr.confirm_step(d, _t(11, 55), 774.68, armed=True, pcz=2.72)    # DOWN
    pos = {"strategy": "bull_put_spread"}
    assert _pivot_against({"pivot_on_confirm": 0}, pos, now) is False
    assert _pivot_against({}, pos, now) is False
    assert _pivot_against({"pivot_on_confirm": 1}, pos, now) is True


def test_pivot_holds_when_the_signal_lookup_breaks():
    """A DB hiccup must leave the position on its validated hold path, not
    close it on an exception."""
    from backend.bots.scanner import _pivot_against
    now = datetime(2026, 8, 17, 12, 0, tzinfo=CT)
    assert _pivot_against({"pivot_on_confirm": "boom"},
                          {"strategy": "bull_put_spread"}, now) is False


# ---------------------------------------------------------------------------
# SESSION CLOCK — freshness must come from the DATA, not from market hours.
#
# The first version of /session derived "LIVE" from 08:30-15:00 CT while the
# watchers only run 10:10-14:00. Between 14:00 and the close it therefore sat
# with a green LIVE badge over a tape that had stopped half an hour earlier —
# the exact defect the page was built to catch, shipped inside the fix for it.
# ---------------------------------------------------------------------------

def _clock(monkeypatch, now_ct, tape_minutes):
    """Drive session_tape()'s clock branch with a controlled now + tape."""
    import backend.routes_risk as rr
    monkeypatch.setattr(rr, "session_log_read",
                        lambda d: [{"minute_ct": m, "spot": 700.0,
                                    "roll_putv_z": None, "roll_totv_z": None}
                                   for m in tape_minutes])
    monkeypatch.setattr(rr, "_latest_snapshot", lambda d: None)
    monkeypatch.setattr(rr, "_flow_history", lambda: [])
    monkeypatch.setattr(rr, "_pm_flow_history", lambda ck: [])
    monkeypatch.setattr(rr, "_posted_today", lambda k, d: False)

    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now_ct
    monkeypatch.setattr(rr, "datetime", _FakeDT)
    import asyncio
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        rr.session_tape(None))["clock"]


def test_watch_window_over_is_not_live(monkeypatch):
    """14:32 CT with a tape ending 14:00. The market is open, the watchers are
    done. This must NOT say LIVE."""
    c = _clock(monkeypatch, datetime(2026, 8, 18, 14, 32, tzinfo=CT), [610, 780, 840])
    assert c["live"] is False
    assert c["state"] == "WATCHERS CLOSED"
    assert c["last_reading_ct"] == "14:00"
    assert c["age_min"] == 32


def test_a_stall_inside_the_window_is_a_fault(monkeypatch):
    """Polls are every 10 min. Nothing for 25 min while the watchers should be
    running is broken, and must read differently from the window being over."""
    c = _clock(monkeypatch, datetime(2026, 8, 18, 12, 30, tzinfo=CT), [610, 700, 725])
    assert c["live"] is False
    assert c["state"] == "STALLED"
    assert c["age_min"] == 25


def test_fresh_tape_inside_the_window_is_live(monkeypatch):
    c = _clock(monkeypatch, datetime(2026, 8, 18, 12, 30, tzinfo=CT), [610, 740, 750])
    assert c["live"] is True and c["state"] == "LIVE"
    assert c["age_min"] == 0


def test_open_but_before_the_watchers_start(monkeypatch):
    """08:30-10:10 the market is open and the watchers legitimately have not
    started. That is WAITING, not LIVE and not a fault."""
    c = _clock(monkeypatch, datetime(2026, 8, 18, 9, 30, tzinfo=CT), [])
    assert c["live"] is False and c["state"] == "WAITING"


# ---------------------------------------------------------------------------
# THE DECAY MONITOR.
#
# The signal fires on ~8.7% of sessions. Judging it on live alerts alone would
# take two years to say anything, so the evaluation re-scores the whole rule
# over an expanding window every night off data production already writes.
#
# The thresholds are pre-registered (2026-08-18, before any live firing) and
# graded against a CONTEMPORANEOUS base rate, not against the backtest's own
# 63.2% — so the bar moves if the whole market changes.
# ---------------------------------------------------------------------------

@pytest.fixture
def calib_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db import Base
    import backend.signal_calibration as sc
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(sc, "SessionLocal", sessionmaker(bind=eng, expire_on_commit=False))
    monkeypatch.setattr(sc, "engine", eng)
    return sc


def _fill(sc, *, n_armed_cont, n_armed_total, n_base_cont, n_base_total,
          big_armed=0.9, big_base=0.2, start=date(2026, 1, 5)):
    """Write a synthetic window with controlled continuation rates."""
    db = sc.SessionLocal()
    day = start
    def add(armed, cont, big):
        nonlocal day
        db.add(sc.SignalEval(
            d=day, pcz=2.0 if armed else 0.1, armed=1 if armed else 0,
            ref_spot=700.0, close_spot=700.0, fired_dir="DOWN",
            fired_spot=699.0, continued=cont,
            move_pct=-0.8 if big else -0.1, source="live"))
        day = day + timedelta(days=1)
    for i in range(n_armed_total):
        add(True, 1 if i < n_armed_cont else 0, i < int(big_armed * n_armed_total))
    for i in range(n_base_total):
        add(False, 1 if i < n_base_cont else 0, i < int(big_base * n_base_total))
    db.commit(); db.close()


def test_a_healthy_window_passes_and_leaves_the_pivot_armed(calib_db):
    sc = calib_db
    _fill(sc, n_armed_cont=40, n_armed_total=60, n_base_cont=314, n_base_total=630)
    rep = sc.report(date(2027, 11, 1))
    assert rep["verdict"] == "PASS"
    assert sc.enforce(rep) == []          # nothing disarmed


def test_a_collapsed_gap_disarms_the_pivot(calib_db):
    """Continuation drifting down to the unflagged base means the gate no
    longer separates — the pivot would be acting on nothing."""
    sc = calib_db
    _fill(sc, n_armed_cont=31, n_armed_total=60, n_base_cont=314, n_base_total=630)
    rep = sc.report(date(2027, 11, 1))
    assert rep["verdict"] == "DISARM"
    assert "no longer separates" in " ".join(rep["reasons"])


def test_a_thin_window_says_underpowered_not_pass(calib_db):
    """🚨 The dangerous failure would be a small good-looking sample reading as
    PASS. Under MIN_N it must refuse to conclude in EITHER direction."""
    sc = calib_db
    _fill(sc, n_armed_cont=8, n_armed_total=10, n_base_cont=52, n_base_total=105)
    rep = sc.report(date(2027, 11, 1))
    assert rep["verdict"] == "UNDERPOWERED"
    assert sc.enforce(rep) == []


def test_enforce_only_ever_disarms(calib_db):
    """A recovered window must NOT auto-rearm — inside a rolling window that
    is more likely noise than resurrection, and auto-rearming would invert the
    fail-safe direction."""
    sc = calib_db
    _fill(sc, n_armed_cont=40, n_armed_total=60, n_base_cont=314, n_base_total=630)
    rep = sc.report(date(2027, 11, 1))
    assert rep["verdict"] == "PASS"
    assert not hasattr(sc, "rearm")       # no such affordance exists
    assert sc.enforce(rep) == []


def test_thresholds_are_recorded_in_the_payload(calib_db):
    """The pre-registered lines ship WITH the number, so a later reader cannot
    quietly re-interpret what 'passing' meant."""
    sc = calib_db
    _fill(sc, n_armed_cont=40, n_armed_total=60, n_base_cont=314, n_base_total=630)
    pr = sc.report(date(2027, 11, 1))["pre_registered"]
    assert pr["set_on"] == "2026-08-18"
    assert "LCB" in pr["disarm_if"]


# ---------------------------------------------------------------------------
# WHAT THE 08-18 PAGE LEFT OUT (added 2026-08-19)
#
# It shipped with the hit rate and nothing else: 63% continuation, two trigger
# lines on a chart, and no answer to "how much is left". A hit rate with no
# magnitude is not a tradeable statement, and the intraday tape carried only
# the two LEVEL z-scores — the pair that were both correctly quiet on 08-17
# while the MIX was the outlier of the trailing 63.
# ---------------------------------------------------------------------------

def test_the_tape_carries_the_mix_not_just_the_levels(confirm_db):
    """🚨 The regression this pins: an intraday tape that grades put and total
    volume but never their ratio is the pre-08/18 metric wearing a new chart."""
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.session_log_write(d, _t(11, 0), spot=774.68,
                         roll_putv_z=0.58, roll_totv_z=-0.45, roll_pc_z=2.72)
    row = rr.session_log_read(d)[0]
    assert row["roll_pc_z"] == 2.72
    # and the levels alone would still have said "quiet"
    assert row["roll_putv_z"] < 2 and row["roll_totv_z"] < 2


def test_the_mix_shares_the_no_rewrite_rule(confirm_db):
    rr = confirm_db
    d = date(2026, 8, 17)
    rr.session_log_write(d, _t(11, 0), roll_pc_z=2.72)
    rr.session_log_write(d, _t(11, 8), roll_pc_z=0.10)
    assert rr.session_log_read(d)[0]["roll_pc_z"] == 2.72


def test_the_rolling_baseline_can_grade_the_mix():
    """The baseline file needs pc_mean/pc_sd at every minute it covers, or the
    watcher silently writes NULL mix all session and the chart stays empty."""
    from backend.routes_risk import _rolling_baseline
    b = _rolling_baseline()
    assert b, "baseline file missing"
    missing = [m for m, row in b.items() if not row.get("pc_sd")]
    assert not missing, f"{len(missing)} minutes have no mix baseline"
    # sanity: SPY's cumulative put/call ratio sits near 1, not near zero
    any_row = b[min(b)]
    assert 0.5 < any_row["pc_mean"] < 2.0


def test_runway_reports_magnitude_and_the_payoff_asymmetry(calib_db):
    """The finding is not the 63% — an unflagged break also wins sometimes.
    It is that a flagged break wins far more than it gives back."""
    sc = calib_db
    db = sc.SessionLocal()
    day = date(2026, 1, 5)
    for i in range(40):                       # armed: big wins, small losses
        won = i < 27
        db.add(sc.SignalEval(d=day, pcz=2.0, armed=1, ref_spot=700.0,
                             close_spot=700.0, fired_dir="UP", fired_spot=700.0,
                             continued=1 if won else 0, move_pct=0.5,
                             source="seed"))
        # close_spot carries the run; set it after so the sign is explicit
        db.query(sc.SignalEval).filter(sc.SignalEval.d == day).update(
            {"close_spot": 700.0 * (1 + (0.005 if won else -0.002))})
        day = day + timedelta(days=1)
    for i in range(40):                       # unflagged: symmetric coin flip
        won = i < 20
        db.add(sc.SignalEval(d=day, pcz=0.1, armed=0, ref_spot=700.0,
                             close_spot=700.0, fired_dir="UP", fired_spot=700.0,
                             continued=1 if won else 0, move_pct=0.1,
                             source="seed"))
        db.query(sc.SignalEval).filter(sc.SignalEval.d == day).update(
            {"close_spot": 700.0 * (1 + (0.003 if won else -0.003))})
        day = day + timedelta(days=1)
    db.commit(); db.close()

    sc._runway_cache = None
    rw = sc.runway(date(2026, 6, 1))
    assert rw["armed"]["n"] == 40 and rw["base"]["n"] == 40
    assert rw["armed"]["median_win"] > 0 > rw["armed"]["median_loss"]
    # the whole point: armed pays multiples of what it risks, base does not
    assert rw["payoff_ratio"] > 2
    assert rw["base_payoff_ratio"] == pytest.approx(1.0, abs=0.1)


def test_runway_stays_quiet_rather_than_quoting_a_number_from_nothing(calib_db):
    """Under ten firings there is no distribution to report. A page that
    invents one reads as authoritative and is wrong."""
    sc = calib_db
    sc._runway_cache = None
    assert sc.runway(date(2026, 6, 1))["armed"] is None
