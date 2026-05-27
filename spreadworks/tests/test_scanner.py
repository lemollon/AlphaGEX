from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.bots.scanner import run_scan_cycle, should_run_scan_loop, ChainProvider

CT = ZoneInfo("America/Chicago")


# 2026-05-20 = Wed, 05-23 = Sat, 05-24 = Sun, 05-25 = Mon (Memorial Day holiday)
@pytest.mark.parametrize("dt,is_holiday,expected", [
    (datetime(2026, 5, 20, 9, 0, tzinfo=CT),  False, True),   # Wed, RTH, normal day
    (datetime(2026, 5, 20, 8, 0, tzinfo=CT),  False, True),   # 08:00 boundary — open
    (datetime(2026, 5, 20, 14, 59, tzinfo=CT), False, True),  # 14:59 — last minute
    (datetime(2026, 5, 20, 7, 59, tzinfo=CT), False, False),  # before 08:00
    (datetime(2026, 5, 20, 15, 0, tzinfo=CT), False, False),  # 15:00 — closed
    (datetime(2026, 5, 23, 9, 0, tzinfo=CT),  False, False),  # Saturday
    (datetime(2026, 5, 24, 9, 0, tzinfo=CT),  False, False),  # Sunday
    (datetime(2026, 5, 25, 9, 0, tzinfo=CT),  True,  False),  # Memorial Day holiday
])
def test_should_run_scan_loop(dt, is_holiday, expected):
    assert should_run_scan_loop(dt, is_holiday=is_holiday) is expected


class FakeChainProvider(ChainProvider):
    def __init__(self, *, chain_0dte=None, chain_1dte=None, chain_14dte=None,
                 chain_6dte=None, chain_9dte=None):
        self.c0 = chain_0dte; self.c1 = chain_1dte; self.c14 = chain_14dte
        self.c6 = chain_6dte; self.c9 = chain_9dte
        self.calls = 0
        self.leg_mid_overrides = None  # if set, get_leg_mids returns this

    def get_chain(self, *, ticker, dte, today):
        self.calls += 1
        if dte == 0: return self.c0
        if dte == 1: return self.c1
        if dte == 6: return self.c6
        if dte == 9: return self.c9
        if dte == 14: return self.c14
        return None

    def get_leg_mids(self, *, ticker, legs):
        if self.leg_mid_overrides is not None:
            return self.leg_mid_overrides
        return [leg["entry_price"] for leg in legs]


def _enable_bot(engine, bot):
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {bot}_config SET enabled = 1 WHERE id = 1"))


def _set_stacking(engine, bot, on):
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {bot}_config SET allow_stacking = :v WHERE id = 1"),
                     {"v": 1 if on else 0})


def _open_meadow_at(engine, when, c6, c9):
    """Open a real MEADOW credit-double-diagonal position dated `when`."""
    from backend.bots.strategies.double_diagonal_credit import (
        build_double_diagonal_credit_signal,
    )
    from backend.bots.executor import open_position
    from backend.bots.db import load_config
    sig = build_double_diagonal_credit_signal(
        front_chain=c6, back_chain=c9, config=dict(load_config(engine, "meadow")),
        equity=10000.0,
    )
    assert sig is not None
    return open_position(engine, "meadow", "double_diagonal_credit", sig, when)


# 2026-05-18 = Monday, 2026-05-22 = Friday (both before the fixture's
# front expiration 2026-05-27, so a held position is not force-closed).
MONDAY = datetime(2026, 5, 18, 9, 0, tzinfo=CT)
FRIDAY = datetime(2026, 5, 22, 9, 0, tzinfo=CT)
MONDAY2 = datetime(2026, 5, 25, 9, 0, tzinfo=CT)  # next Mon, still < exp 2026-05-27


def test_breeze_opens_position_in_entry_window(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] in ("TRADE", "NO_TRADE")  # not blocked
    # If TRADE, position should exist
    if res["outcome"] == "TRADE":
        with engine.begin() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) c FROM breeze_positions WHERE status='OPEN'"
            )).mappings().first()["c"]
        assert n == 1


def test_breeze_disabled_blocks_trading(db_session, fake_chain_0dte):
    engine = db_session.bind  # NOT enabling
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "BLOCKED_DISABLED"


def test_outside_entry_window_blocks_open(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    # Before 08:35
    now = datetime(2026, 5, 20, 8, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "BLOCKED_OUTSIDE_WINDOW"


def test_event_blackout_blocks_open(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                        chain_provider=provider, event_blackout=True)
    assert res["outcome"] == "BLOCKED_EVENT"


def test_existing_open_position_monitors_instead_of_opens(db_session, fake_chain_0dte):
    """If an OPEN position exists, the scanner should MONITOR (not open another)."""
    from backend.bots.strategies.iron_butterfly import build_iron_butterfly_signal
    from backend.bots.executor import open_position
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    open_position(engine, "breeze", "iron_butterfly", sig,
                  datetime(2026, 5, 20, 9, 0, tzinfo=CT))
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "MONITOR"


def test_scan_activity_row_written(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT outcome FROM breeze_scan_activity"
        )).mappings().all()
    assert len(rows) >= 1


def test_meadow_blocked_on_non_entry_day(db_session, fake_chain_6dte, fake_chain_9dte):
    """MEADOW enters Mon/Fri only — a Wednesday scan must not open."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    wednesday = datetime(2026, 5, 20, 9, 0, tzinfo=CT)  # 2026-05-20 is a Wednesday
    res = run_scan_cycle(engine=engine, bot="meadow", now_ct=wednesday,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "BLOCKED_ENTRY_DAY"


def test_meadow_opens_on_entry_day(db_session, fake_chain_6dte, fake_chain_9dte):
    """On a Friday, the day gate allows MEADOW to open its credit DD."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    friday = datetime(2026, 5, 22, 9, 0, tzinfo=CT)  # 2026-05-22 is a Friday
    res = run_scan_cycle(engine=engine, bot="meadow", now_ct=friday,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM meadow_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 1


def test_meadow_stacks_on_next_entry_day_while_position_open(
    db_session, fake_chain_6dte, fake_chain_9dte
):
    """allow_stacking ON: a Monday position still open on Friday must NOT block
    the Friday entry — MEADOW opens a second concurrent position."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    _set_stacking(engine, "meadow", True)
    _open_meadow_at(engine, MONDAY, fake_chain_6dte, fake_chain_9dte)
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    res = run_scan_cycle(engine=engine, bot="meadow", now_ct=FRIDAY,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    assert res["reason"] == "OPENED"
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM meadow_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 2


def test_meadow_one_entry_per_day_cap(db_session, fake_chain_6dte, fake_chain_9dte):
    """Even with stacking, MEADOW opens at most ONE position per entry-day —
    a second scan the same Friday monitors instead of opening a third."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    _set_stacking(engine, "meadow", True)
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    first = run_scan_cycle(engine=engine, bot="meadow", now_ct=FRIDAY,
                           chain_provider=provider, event_blackout=False)
    assert first["outcome"] == "TRADE"
    second = run_scan_cycle(engine=engine, bot="meadow",
                            now_ct=FRIDAY.replace(minute=1),
                            chain_provider=provider, event_blackout=False)
    assert second["outcome"] == "MONITOR"
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM meadow_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 1


def test_meadow_max_concurrent_cap_blocks_third(
    db_session, fake_chain_6dte, fake_chain_9dte
):
    """With max_concurrent_positions=2, holding two positions blocks a third
    entry on a later entry-day — even though the per-day cap wouldn't (no
    position was opened on MONDAY2)."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    _set_stacking(engine, "meadow", True)  # MEADOW seeds max_concurrent=2
    _open_meadow_at(engine, MONDAY, fake_chain_6dte, fake_chain_9dte)
    _open_meadow_at(engine, FRIDAY, fake_chain_6dte, fake_chain_9dte)
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    res = run_scan_cycle(engine=engine, bot="meadow", now_ct=MONDAY2,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "MONITOR"  # managing the 2 held positions
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM meadow_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 2  # cap held — no third opened


def test_meadow_without_stacking_stays_one_at_a_time(
    db_session, fake_chain_6dte, fake_chain_9dte
):
    """allow_stacking OFF: a held position blocks new entries even on a Friday
    — preserves the legacy one-at-a-time behavior used by all other bots."""
    engine = db_session.bind
    _enable_bot(engine, "meadow")
    _set_stacking(engine, "meadow", False)  # MEADOW seeds ON; force legacy path
    _open_meadow_at(engine, MONDAY, fake_chain_6dte, fake_chain_9dte)
    provider = FakeChainProvider(chain_6dte=fake_chain_6dte, chain_9dte=fake_chain_9dte)
    res = run_scan_cycle(engine=engine, bot="meadow", now_ct=FRIDAY,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "MONITOR"
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM meadow_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 1


def test_equity_snapshot_written(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "breeze")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=engine, bot="breeze", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT equity FROM breeze_equity_snapshots"
        )).mappings().all()
    assert len(rows) == 1
    assert float(rows[0]["equity"]) >= 9000  # near starting capital
