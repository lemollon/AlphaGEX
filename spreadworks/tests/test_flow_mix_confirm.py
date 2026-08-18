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
