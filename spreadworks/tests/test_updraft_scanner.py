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
