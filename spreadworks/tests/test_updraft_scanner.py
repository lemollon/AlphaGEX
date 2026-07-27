"""End-to-end scanner wiring for UPDRAFT / BACKDRAFT.

The unit tests in test_updraft.py cover the signal logic in isolation. These
drive the real `run_scan_cycle` so the parts that only exist in the scanner
are exercised: the flow-snapshot write, the cumulative-volume differencing
that produces flow_imb_30, and the minute-granularity TIME_STOP.

The 30-minute imbalance is the whole signal, so the critical case is the one
that cannot be faked from a single chain: two scans 30 minutes apart with
DIFFERENT cumulative volumes.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.bots.executor import list_open_positions
from backend.bots.scanner import ChainProvider, run_scan_cycle

CT = ZoneInfo("America/Chicago")


class FlowChainProvider(ChainProvider):
    """Serves a 0DTE SPY chain whose cumulative volume we control per scan."""

    def __init__(self, spot=600.0, call_vol=1000, put_vol=1000,
                 put_wall=598.0):
        self.spot = spot
        self.call_vol = call_vol
        self.put_vol = put_vol
        self.put_wall = put_wall

    def get_chain(self, *, ticker, dte, today):
        strikes = [self.spot + d for d in (-2, -1, 0, 1, 2, 3)]
        n = len(strikes)
        return {
            "spot": self.spot, "ticker": ticker, "expiration": today,
            "options": [
                {"strike": s, "type": t, "bid": 0.60, "ask": 0.64,
                 # split the session total evenly across strikes
                 "volume": (self.call_vol if t == "call" else self.put_vol) // n,
                 "open_interest": 100}
                for s in strikes for t in ("call", "put")
            ],
            "gex": {"put_wall": self.put_wall, "call_wall": self.spot + 5},
        }

    def get_leg_mids(self, *, ticker, legs):
        return [leg["entry_price"] for leg in legs]

    def get_daily_history(self, *, ticker, days):
        return []


def _enable(engine, bot):
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {bot}_config SET enabled=1"))


def test_first_scan_does_not_trade_while_flow_is_warming_up(db_session):
    """With no snapshot ~30 min back there is no imbalance, so no trade.

    This is the correct behaviour for the first half hour of a session and
    for the first scans after a deploy - not an error.
    """
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider()
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 0
    row = eng.connect().execute(text(
        "SELECT reason FROM updraft_scan_activity ORDER BY scan_time DESC"
    )).mappings().first()
    assert row is not None and "flow" in (row["reason"] or "").lower()


def test_snapshot_is_recorded_every_scan(db_session):
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider()
    for m in (0, 5, 10):
        run_scan_cycle(engine=eng, bot="updraft",
                       now_ct=datetime(2026, 7, 27, 9, m, tzinfo=CT),
                       chain_provider=p, event_blackout=False)
    n = eng.connect().execute(text(
        "SELECT COUNT(*) c FROM spreadworks_flow_snapshots"
    )).mappings().first()["c"]
    assert n == 3


def test_updraft_opens_on_put_heavy_flow_into_a_rally(db_session):
    """The signal that only a 30-minute difference can express.

    Scan 1 at 09:00 banks the baseline. Between then and 09:30 the tape
    prints far more puts than calls (imbalance well below -0.1378) while
    spot rises 60bp (above the +19.23bp gate). That must open a position.
    """
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=1200, put_vol=1200)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 0

    # +600 calls vs +3000 puts -> imb = (600-3000)/3600 = -0.667
    # spot 600.00 -> 603.60 = +60bp
    p.call_vol += 600
    p.put_vol += 3000
    p.spot = 603.60
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 30, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    pos = list_open_positions(eng, "updraft")
    assert len(pos) == 1, "put-heavy flow into a rally should open a call"


def test_updraft_does_not_open_when_the_tape_is_falling(db_session):
    """Put-heavy flow ALONE is not the signal - flow alone lost ~-4.5% in
    research. Same volumes as the passing case, but spot falls."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=1200, put_vol=1200)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    p.call_vol += 600
    p.put_vol += 3000
    p.spot = 597.0                       # tape DOWN
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 30, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 0


def test_updraft_time_stop_closes_at_45_minutes(db_session):
    """The timer IS the exit - there is deliberately no profit target."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=1200, put_vol=1200)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    p.call_vol += 600
    p.put_vol += 3000
    p.spot = 603.60
    open_at = datetime(2026, 7, 27, 9, 30, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="updraft", now_ct=open_at,
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 1

    # 45 minutes later the timer must fire
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 10, 15, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 0
    row = eng.connect().execute(text(
        "SELECT close_reason FROM updraft_closed_trades "
        "ORDER BY close_time DESC")).mappings().first()
    assert row["close_reason"] == "TIME_STOP"


def test_backdraft_needs_the_put_wall_underneath(db_session):
    """Same extreme flow, but spot BELOW the live put wall -> no trade."""
    eng = db_session.get_bind()
    _enable(eng, "backdraft")
    p = FlowChainProvider(spot=600.0, call_vol=1200, put_vol=1200,
                          put_wall=610.0)          # wall ABOVE spot
    run_scan_cycle(engine=eng, bot="backdraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    p.call_vol += 500
    p.put_vol += 4000                              # imb = -0.778
    run_scan_cycle(engine=eng, bot="backdraft",
                   now_ct=datetime(2026, 7, 27, 9, 30, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "backdraft")) == 0

    # Move the wall below spot and it should trade.
    p.put_wall = 595.0
    p.call_vol += 500
    p.put_vol += 4000
    run_scan_cycle(engine=eng, bot="backdraft",
                   now_ct=datetime(2026, 7, 27, 10, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "backdraft")) == 1


# ------------------------------------------------- the open (08:30 CT)
# Research builds the two halves of the signal with different SQL, and they
# truncate differently in the first half hour: flow_imb_30 is a ROWS-29-
# PRECEDING sum (defined from the first bar, 08:31 CT) while r30_bp is
# LAG(spot,30) (NULL until 09:00 CT). BACKDRAFT takes 12 of its 119
# backtested entries in that gap; UPDRAFT takes none. These pin both sides.

def _last_reason(eng, bot):
    return (eng.connect().execute(text(
        f"SELECT reason FROM {bot}_scan_activity ORDER BY scan_time DESC"
    )).mappings().first() or {}).get("reason") or ""


def test_snapshot_is_recorded_before_the_entry_window_opens(db_session):
    """The 08:00-08:30 CT scans are outside the entry window but must still
    bank a zero-volume baseline - that baseline is the whole reason the
    window can truncate at the open instead of warming up for 22 minutes."""
    eng = db_session.get_bind()
    _enable(eng, "backdraft")
    p = FlowChainProvider(spot=600.0, call_vol=0, put_vol=0)
    res = run_scan_cycle(engine=eng, bot="backdraft",
                         now_ct=datetime(2026, 7, 27, 8, 5, tzinfo=CT),
                         chain_provider=p, event_blackout=False)
    assert res["outcome"] == "BLOCKED_OUTSIDE_WINDOW"
    row = eng.connect().execute(text(
        "SELECT call_volume, put_volume FROM spreadworks_flow_snapshots"
    )).mappings().first()
    assert row is not None, "pre-open scan must still snapshot the tape"
    assert row["call_volume"] == 0 and row["put_volume"] == 0


def test_backdraft_trades_in_the_first_minutes_of_the_session(db_session):
    """08:35 CT, five minutes into the session, differencing against the
    pre-open zero baseline = volume since the open. That is exactly the
    truncated window research used, and BACKDRAFT is allowed to act on it."""
    eng = db_session.get_bind()
    _enable(eng, "backdraft")
    p = FlowChainProvider(spot=600.0, call_vol=0, put_vol=0, put_wall=595.0)
    run_scan_cycle(engine=eng, bot="backdraft",
                   now_ct=datetime(2026, 7, 27, 8, 5, tzinfo=CT),
                   chain_provider=p, event_blackout=False)

    p.call_vol, p.put_vol = 600, 3000        # imb = -0.667
    run_scan_cycle(engine=eng, bot="backdraft",
                   now_ct=datetime(2026, 7, 27, 8, 35, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "backdraft")) == 1


def test_updraft_stands_down_until_the_return_window_clears_the_open(db_session):
    """Same tape, same minute - but UPDRAFT also needs r30_bp, and a
    pre-open baseline would measure the overnight gap rather than a
    30-minute return. It must decline, and say why."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=0, put_vol=0)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 8, 5, tzinfo=CT),
                   chain_provider=p, event_blackout=False)

    p.call_vol, p.put_vol = 600, 3000
    p.spot = 604.0                            # a rally that would qualify
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 8, 35, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 0
    assert "pre_open_baseline" in _last_reason(eng, "updraft")


def test_updraft_trades_once_the_baseline_sits_inside_the_session(db_session):
    """09:05 CT: the ~30-minute-back snapshot is 08:35, after the open, so
    r30_bp is a real intraday return and UPDRAFT is live again."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=0, put_vol=0)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 8, 5, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    p.call_vol, p.put_vol = 600, 600
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 8, 35, tzinfo=CT),
                   chain_provider=p, event_blackout=False)

    p.call_vol += 600                         # imb = (600-3000)/3600 = -0.667
    p.put_vol += 3000
    p.spot = 603.60                           # +60bp over the 30 minutes
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 5, tzinfo=CT),
                   chain_provider=p, event_blackout=False)
    assert len(list_open_positions(eng, "updraft")) == 1


def test_one_minute_is_snapshotted_once_across_both_bots(db_session):
    """UPDRAFT and BACKDRAFT scan the same ticker in the same cycle. Two
    identical rows per minute would double the table for no signal."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    _enable(eng, "backdraft")
    p = FlowChainProvider(spot=600.0, call_vol=100, put_vol=100)
    now = datetime(2026, 7, 27, 9, 0, tzinfo=CT)
    for bot in ("updraft", "backdraft"):
        run_scan_cycle(engine=eng, bot=bot, now_ct=now,
                       chain_provider=p, event_blackout=False)
    n = eng.connect().execute(text(
        "SELECT COUNT(*) c FROM spreadworks_flow_snapshots"
    )).mappings().first()["c"]
    assert n == 1


def test_a_blocked_entry_still_records_the_tape(db_session):
    """A gate that stops the ENTRY must not stop the SNAPSHOT. A hole wider
    than WINDOW_TOL_MIN blinds the bot once the block clears - which is what
    a bot sitting on its 3-position cap for 45 minutes used to do."""
    eng = db_session.get_bind()
    _enable(eng, "updraft")
    p = FlowChainProvider(spot=600.0, call_vol=100, put_vol=100)
    run_scan_cycle(engine=eng, bot="updraft",
                   now_ct=datetime(2026, 7, 27, 9, 0, tzinfo=CT),
                   chain_provider=p, event_blackout=True)     # blackout gate
    n = eng.connect().execute(text(
        "SELECT COUNT(*) c FROM spreadworks_flow_snapshots"
    )).mappings().first()["c"]
    assert n == 1
