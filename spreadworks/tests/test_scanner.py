from datetime import date, datetime, timedelta
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
                 chain_6dte=None, chain_9dte=None, daily_history=None,
                 chains_by_ticker=None):
        self.c0 = chain_0dte; self.c1 = chain_1dte; self.c14 = chain_14dte
        self.c6 = chain_6dte; self.c9 = chain_9dte
        self.calls = 0
        self.leg_mid_overrides = None  # if set, get_leg_mids returns this
        self.daily_history = daily_history or {}        # ticker -> list[bar]
        self.chains_by_ticker = chains_by_ticker or {}  # ticker -> chain dict

    def get_chain(self, *, ticker, dte, today):
        self.calls += 1
        if self.chains_by_ticker:
            return self.chains_by_ticker.get(ticker)
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

    def get_daily_history(self, *, ticker, days):
        return list(self.daily_history.get(ticker, []))


def test_fake_provider_returns_daily_history():
    p = FakeChainProvider(daily_history={"NVDA": [{"date": "2026-06-09",
        "open": 1, "high": 2, "low": 1, "close": 2}]})
    bars = p.get_daily_history(ticker="NVDA", days=40)
    assert len(bars) == 1 and bars[0]["date"] == "2026-06-09"
    assert p.get_daily_history(ticker="MSFT", days=40) == []


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


def test_river_pt_rederived_on_decreasing_ladder(db_session, fake_chain_0dte):
    """RIVER (long_butterfly) must re-derive PT from the DECREASING time-of-day
    ladder, not sit at the static 30%-of-max-profit target it was opened with.

    A gain of +$100 = 22.2% of the $450 max profit is below the 30% morning bar
    ($135) but above the 20% afternoon tier ($90). Pre-fix (no re-derivation for
    long_butterfly) it would never close; post-fix it closes in the afternoon.
    """
    from backend.bots.strategies.long_butterfly import build_long_butterfly_signal
    from backend.bots.executor import open_position
    engine = db_session.bind
    _enable_bot(engine, "river")
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 2, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 0.50, "use_gex_walls": False,
                "starting_capital": 10000},
        equity=10000.0,
    )
    assert sig is not None
    # debit 0.75, 2 contracts, max_profit total = 225 * 2 = 450, stored PT = 135.
    open_position(engine, "river", "long_butterfly", sig,
                  datetime(2026, 5, 20, 9, 0, tzinfo=CT))

    # Drive the fly's current value to 1.25 -> pnl = (1.25 - 0.75) * 2 * 100 = +$100.
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    provider.leg_mid_overrides = [1.25, 0.0, 0.0, 0.0]

    # MORNING: 30% tier ($135) not met -> still just monitoring.
    res_am = run_scan_cycle(engine=engine, bot="river",
                            now_ct=datetime(2026, 5, 20, 9, 30, tzinfo=CT),
                            chain_provider=provider, event_blackout=False)
    assert res_am["outcome"] == "MONITOR"

    # AFTERNOON: 20% tier ($90) met -> take profit.
    res_pm = run_scan_cycle(engine=engine, bot="river",
                            now_ct=datetime(2026, 5, 20, 13, 30, tzinfo=CT),
                            chain_provider=provider, event_blackout=False)
    assert res_pm["outcome"] == "TRADE"
    assert res_pm["reason"] == "CLOSE_PT"
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) c FROM river_positions WHERE status='OPEN'"
        )).mappings().first()["c"]
    assert n == 0


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


def test_river_opens_and_pt_closes_with_positive_pnl(db_session, fake_chain_0dte):
    """End-to-end RIVER (long debit butterfly): the scanner opens a position,
    and once the fly gains value the debit-aware MTM yields a positive P&L that
    trips the profit target — exercising the 4-leg (body sold twice) path."""
    engine = db_session.bind
    _enable_bot(engine, "river")  # enabled by default, but be explicit
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)

    # 1) Open in the entry window (fixture expiration 2026-05-20 == scan day).
    opened = run_scan_cycle(engine=engine, bot="river",
                            now_ct=datetime(2026, 5, 20, 9, 0, tzinfo=CT),
                            chain_provider=provider, event_blackout=False)
    assert opened["outcome"] == "TRADE" and opened["reason"] == "OPENED"
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT entry_price, contracts FROM river_positions WHERE status='OPEN'"
        )).mappings().first()
    assert float(row["entry_price"]) == pytest.approx(0.75)  # the net debit

    # 2) Drive the legs so the fly is worth ~3.0 (price pinned at the body):
    #    legs order = [long lower, short body, short body, long upper];
    #    mtm_value = lower - 2*body + upper = 3.0 - 0 + 0 = 3.0 >> 0.75 debit.
    provider.leg_mid_overrides = [3.0, 0.0, 0.0, 0.0]
    closed = run_scan_cycle(engine=engine, bot="river",
                            now_ct=datetime(2026, 5, 20, 9, 30, tzinfo=CT),
                            chain_provider=provider, event_blackout=False)
    assert closed["outcome"] == "TRADE"
    assert closed["reason"] == "CLOSE_PT"
    with engine.begin() as conn:
        r = conn.execute(text(
            "SELECT realized_pnl FROM river_closed_trades"
        )).mappings().first()
    assert float(r["realized_pnl"]) > 0  # debit trade gains as fly value rises


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


def _undertow_history():
    # rising trend, spike high to 150, then 3 down days so RSI(2) is oversold
    # and SMA(20) ~= 131.
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        price = 101 + i
        d = base + timedelta(days=i)
        bars.append({"date": d.isoformat(), "open": price, "high": price,
                     "low": price, "close": price})
    bars.append({"date": (base + timedelta(days=36)).isoformat(),
                 "open": 144, "high": 150, "low": 143, "close": 145})
    bars.append({"date": (base + timedelta(days=37)).isoformat(),
                 "open": 145, "high": 146, "low": 142, "close": 143})
    bars.append({"date": (base + timedelta(days=38)).isoformat(),
                 "open": 143, "high": 143, "low": 140, "close": 141})
    bars.append({"date": (base + timedelta(days=39)).isoformat(),
                 "open": 141, "high": 141, "low": 139, "close": 140})
    return bars


def _undertow_chain(ticker, spot):
    opts = []
    for s in range(120, 161, 5):
        opts.append({"strike": s, "type": "call", "bid": 4.8, "ask": 5.2})
        opts.append({"strike": s, "type": "put", "bid": 4.8, "ask": 5.2})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker,
            "options": opts}


def _spread_chain(ticker, spot):
    opts = []
    for s in range(100, 201, 5):
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.05, 2), "ask": round(call_mid + 0.05, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.05, 2), "ask": round(put_mid + 0.05, 2)})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def _enable_undertow(engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("UPDATE undertow_config SET enabled=1"))


def test_undertow_opens_deepest_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    eng = db_session.get_bind()
    _enable_undertow(eng)
    # NVDA dips to 140 (6.7%), AAPL to 145 (3.3%) — NVDA is deeper.
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0),
                          "AAPL": _spread_chain("AAPL", 145.0)},
        daily_history={"NVDA": _undertow_history(), "AAPL": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    from backend.bots.executor import list_open_positions
    opens = list_open_positions(eng, "undertow")
    assert len(opens) == 1
    assert opens[0]["ticker"] == "NVDA"


def test_undertow_skips_held_ticker_and_respects_concurrent_cap(db_session):
    from backend.bots.scanner import run_scan_cycle
    eng = db_session.get_bind()
    _enable_undertow(eng)
    from sqlalchemy import text
    with eng.begin() as conn:
        conn.execute(text("UPDATE undertow_config SET max_concurrent_positions=1"))
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    res2 = run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                          chain_provider=provider, event_blackout=False)
    from backend.bots.executor import list_open_positions
    assert len(list_open_positions(eng, "undertow")) == 1
    assert res2["outcome"] in ("BLOCKED_MAX_CONCURRENT", "MONITOR")


def test_undertow_time_stop_closes_position_end_to_end(db_session):
    """End-to-end: a position opened 2 days ago is force-closed by TIME_STOP
    through the scanner's decide_exit wiring (entry_time + hold_days)."""
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    from sqlalchemy import text
    eng = db_session.get_bind()
    _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    # Open on day 0
    open_now = datetime(2026, 6, 8, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=open_now,
                   chain_provider=provider, event_blackout=False)
    assert len(list_open_positions(eng, "undertow")) == 1
    # Two calendar days later -> hold_days=2 reached -> TIME_STOP.
    # Keep the same provider so get_leg_mids can price the (single) leg.
    later = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=eng, bot="undertow", now_ct=later,
                         chain_provider=provider, event_blackout=False)
    assert len(list_open_positions(eng, "undertow")) == 0  # closed
    # closed_trades has a TIME_STOP row
    row = eng.connect().execute(text(
        "SELECT close_reason FROM undertow_closed_trades ORDER BY close_time DESC")
    ).mappings().first()
    assert row["close_reason"] == "TIME_STOP"


def test_undertow_journals_dip_context(db_session):
    from backend.bots.scanner import run_scan_cycle
    import json as _json
    eng = db_session.get_bind()
    _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    from backend.bots.executor import list_open_positions
    pos = list_open_positions(eng, "undertow")[0]
    notes = _json.loads(pos["notes"])
    assert notes["ticker"] == "NVDA"
    assert notes["kind"] == "bull_call_spread"
    assert notes["magnitude_pct"] > 0.03
    assert notes["reference_level"] == 150.0


def test_undertow_earnings_window_excludes_ticker(db_session, monkeypatch):
    """A universe ticker inside its earnings window is skipped (no open),
    even though it has a qualifying dip. Companion to test_undertow_opens_deepest_dip
    which proves NVDA DOES open when not in an earnings window."""
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import backend.earnings_calendar as ec
    eng = db_session.get_bind()
    _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    # Stub the calendar so NVDA is reported as having upcoming earnings.
    monkeypatch.setattr(ec, "get_upcoming_earnings",
                        lambda from_date=None, days=30: [
                            {"name": "📊 NVDA Earnings (Q1)", "datetime": None}])
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    # NVDA was the only ticker with a chain, and it's earnings-excluded -> nothing opened.
    assert len(list_open_positions(eng, "undertow")) == 0


def test_undertow_opens_bull_call_spread_on_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})
    res = run_scan_cycle(engine=eng, bot="undertow",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "undertow")[0]
    assert pos["strategy"] == "bull_call_spread"
    legs = _j.loads(pos["legs"])
    assert len(legs) == 2 and all(l["type"] == "call" for l in legs)


def test_undertow_writes_ai_rationale(db_session, monkeypatch):
    import backend.bots.ai_rationale as air
    monkeypatch.setattr(air, "generate_entry_rationale",
                        lambda *, bot, signal_context: "Test rationale.")
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})
    run_scan_cycle(engine=eng, bot="undertow",
                   now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                   chain_provider=provider, event_blackout=False)
    notes = _j.loads(list_open_positions(eng, "undertow")[0]["notes"])
    assert notes["rationale"] == "Test rationale."


def _rip_history_scanner():
    """Downtrend then a sharp bounce. Pre-computed so the DIP branch does NOT
    pre-empt: last-5 highs max ~112 (spot 110 -> dip<3%), ref_low ~92
    (rip ~19%), RSI(2)=100 overbought, SMA(20) ~125 > spot (bearish)."""
    bars, base = [], date(2026, 4, 1)
    for i in range(35):                       # 35-bar downtrend 160 -> 126
        c = 160 - i
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": c, "high": c, "low": c, "close": c})
    tail = [(100, 102, 98), (95, 98, 92), (103, 105, 100), (108, 110, 104), (110, 112, 107)]
    for j, (c, h, l) in enumerate(tail):
        bars.append({"date": (base + timedelta(days=35 + j)).isoformat(),
                     "open": c, "high": h, "low": l, "close": c})
    return bars


def _enable_bot(eng, bot):
    from sqlalchemy import text
    with eng.begin() as c:
        c.execute(text(f"UPDATE {bot}_config SET enabled=1"))


def test_delta_opens_put_credit_spread_on_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_bot(eng, "delta")
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})  # dip -> bullish -> put credit
    res = run_scan_cycle(engine=eng, bot="delta",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "delta")[0]
    assert pos["strategy"] == "bull_put_spread"
    assert all(l["type"] == "put" for l in _j.loads(pos["legs"]))


def test_delta_opens_call_credit_spread_on_rip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_bot(eng, "delta")
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 110.0)},
        daily_history={"NVDA": _rip_history_scanner()})  # rip -> bearish -> call credit
    res = run_scan_cycle(engine=eng, bot="delta",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "delta")[0]
    assert pos["strategy"] == "bear_call_spread"
    assert all(l["type"] == "call" for l in _j.loads(pos["legs"]))


def test_evaluate_universe_watchlist_statuses(db_session):
    from datetime import datetime
    from backend.bots.scanner import (
        evaluate_universe_watchlist, ticker_eval_to_row, _evaluate_ticker,
    )
    from backend.bots.registry import get_bot
    from backend.bots.executor import open_position
    from backend.bots.strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS
    eng = db_session.get_bind()
    _enable_undertow(eng)
    meta = get_bot("undertow")
    cfg = dict(meta["defaults"])
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)

    # Open a real AAPL position so AAPL shows HELD.
    aapl_chain = _spread_chain("AAPL", 140.0)
    aapl_sig = build_vertical_signal(
        kind="bull_call_spread", chain=aapl_chain, config=cfg, equity=25000.0,
        params={**DEFAULT_VERTICAL_PARAMS, **(meta.get("params") or {})},
    )
    assert aapl_sig is not None
    open_position(eng, "undertow", "bull_call_spread", aapl_sig, now)

    # NVDA has a buildable dip -> SIGNAL. Other universe names: no chain -> WATCHING.
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0),
                          "AAPL": _spread_chain("AAPL", 140.0)},
        daily_history={"NVDA": _undertow_history(), "AAPL": _undertow_history()},
    )
    evals = evaluate_universe_watchlist(engine=eng, bot="undertow", meta=meta,
                                        cfg=cfg, now_ct=now, chain_provider=provider)
    rows = [ticker_eval_to_row(e) for e in evals]
    by_ticker = {r["ticker"]: r for r in rows}

    assert len(rows) == len(meta["universe"])
    assert by_ticker["AAPL"]["status"] == "HELD"
    assert by_ticker["NVDA"]["status"] == "SIGNAL"
    assert by_ticker["NVDA"]["candidate"]["kind"] == "bull_call_spread"
    assert by_ticker["NVDA"]["candidate"]["long_strike"] is not None
    assert by_ticker["NVDA"]["candidate"]["short_strike"] is not None
    assert by_ticker["NVDA"]["expiration"] == "2026-06-22"
    assert by_ticker["SPY"]["status"] == "WATCHING"
    assert by_ticker["SPY"]["candidate"] is None
    assert "chain_unavailable" in (by_ticker["SPY"]["reason"] or "")


def test_evaluate_ticker_signal_and_held_and_watching():
    from backend.bots.scanner import _evaluate_ticker
    from backend.bots.registry import get_bot
    meta = get_bot("undertow")
    cfg = dict(meta["defaults"])
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)

    # SIGNAL: NVDA dips to 140 from a 150 ref-high, oversold, above SMA(~131).
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    sig_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                now_ct=now, chain_provider=provider,
                                ticker="NVDA", held=False, equity=25000.0)
    assert sig_eval.signal is not None
    assert sig_eval.setup.direction == "bullish"
    assert sig_eval.indicators is not None and sig_eval.indicators["dip_pct"] > 0

    # HELD: short-circuits, no chain fetch, no signal.
    held_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                 now_ct=now, chain_provider=provider,
                                 ticker="NVDA", held=True, equity=25000.0)
    assert held_eval.held is True
    assert held_eval.signal is None and held_eval.setup is None

    # WATCHING: a name with no chain available -> reason, no signal.
    empty = FakeChainProvider(chains_by_ticker={}, daily_history={})
    watch_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                  now_ct=now, chain_provider=empty,
                                  ticker="SPY", held=False, equity=25000.0)
    assert watch_eval.signal is None
    assert "chain_unavailable" in (watch_eval.reason or "")
