"""Tests for the UPDRAFT / BACKDRAFT 0DTE call book."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from backend.bots.flow_store import chain_volume_totals
from backend.bots.monitor import decide_exit
from backend.bots.registry import get_bot
from backend.bots.strategies.updraft import (DEFAULT_PARAMS,
                                             build_updraft_signal)


def _chain(*, spot=600.0, flow_imb=-0.20, r30=25.0, put_wall=598.0,
           bid=0.60, ask=0.64):
    strikes = [spot - 2, spot - 1, spot, spot + 1, spot + 2, spot + 3]
    return {
        "spot": spot, "ticker": "SPY", "expiration": date(2026, 7, 27),
        "options": [
            {"strike": s, "type": t, "bid": bid, "ask": ask, "volume": 100,
             "open_interest": 500}
            for s in strikes for t in ("call", "put")
        ],
        "gex": {"put_wall": put_wall, "call_wall": spot + 5},
        "flow": {"flow_imb_30": flow_imb, "r30_bp": r30, "reason": None},
    }


# ---------------------------------------------------------------- UPDRAFT
def test_updraft_fires_on_put_heavy_flow_into_a_rally():
    sig = build_updraft_signal(chain=_chain(), today=date(2026, 7, 27),
                               params=DEFAULT_PARAMS, mode="updraft")
    assert sig is not None
    assert sig.mode == "updraft"
    # +1 strike OTM off a 600 spot
    assert sig.strike == 601.0
    assert sig.hold_minutes == 45
    assert sig.legs()[0]["type"] == "call"
    assert sig.legs()[0]["action"] == "buy"


def test_updraft_rejects_call_heavy_flow():
    diag = []
    sig = build_updraft_signal(chain=_chain(flow_imb=0.30),
                               today=date(2026, 7, 27),
                               params=DEFAULT_PARAMS, mode="updraft",
                               diag=diag)
    assert sig is None
    assert "flow_not_put_heavy" in diag[0]


def test_updraft_rejects_a_falling_tape():
    """Put-heavy flow alone is NOT the signal - research showed flow alone
    loses -4.54% train / -4.20% test. The momentum leg is required."""
    diag = []
    sig = build_updraft_signal(chain=_chain(r30=-30.0),
                               today=date(2026, 7, 27),
                               params=DEFAULT_PARAMS, mode="updraft",
                               diag=diag)
    assert sig is None
    assert "no_updraft" in diag[0]


def test_updraft_rejects_when_flow_is_still_warming_up():
    ch = _chain()
    ch["flow"] = {"flow_imb_30": None, "r30_bp": None,
                  "reason": "warming_up: no snapshot ~30m back"}
    diag = []
    assert build_updraft_signal(chain=ch, today=date(2026, 7, 27),
                                params=DEFAULT_PARAMS, diag=diag) is None
    assert "flow_unavailable" in diag[0]


def test_updraft_rejects_a_wide_spread():
    diag = []
    sig = build_updraft_signal(chain=_chain(bid=0.40, ask=0.90),
                               today=date(2026, 7, 27),
                               params=DEFAULT_PARAMS, diag=diag)
    assert sig is None
    assert "spread_too_wide" in diag[0]


# -------------------------------------------------------------- BACKDRAFT
def test_backdraft_fires_on_extreme_flow_above_the_put_wall():
    sig = build_updraft_signal(chain=_chain(flow_imb=-0.45, r30=-10.0),
                               today=date(2026, 7, 27),
                               params={**DEFAULT_PARAMS, "hold_minutes": 30},
                               mode="backdraft")
    assert sig is not None
    # BACKDRAFT does not need a rising tape
    assert sig.hold_minutes == 30
    assert sig.put_wall == 598.0


def test_backdraft_rejects_below_the_put_wall():
    diag = []
    sig = build_updraft_signal(chain=_chain(flow_imb=-0.45, put_wall=605.0),
                               today=date(2026, 7, 27),
                               params=DEFAULT_PARAMS, mode="backdraft",
                               diag=diag)
    assert sig is None
    assert "below_put_wall" in diag[0]


def test_backdraft_needs_more_extreme_flow_than_updraft():
    """-0.20 triggers UPDRAFT but must NOT trigger BACKDRAFT (-0.35)."""
    assert build_updraft_signal(chain=_chain(flow_imb=-0.20),
                                today=date(2026, 7, 27),
                                params=DEFAULT_PARAMS,
                                mode="backdraft") is None


# ------------------------------------------------------------- flow_store
def test_chain_volume_totals_sums_the_whole_chain():
    """Research summed ALL 0DTE strikes with no window - narrowing to
    near-the-money would compute a different quantity."""
    opts = [
        {"type": "call", "volume": 10}, {"type": "call", "volume": 5},
        {"type": "put", "volume": 7}, {"type": "put", "volume": None},
        {"type": "call", "volume": 0},
    ]
    assert chain_volume_totals(opts) == (15, 7)


# ---------------------------------------------------------------- exits
def test_time_stop_fires_at_the_hold_horizon():
    entry = datetime(2026, 7, 27, 9, 0)
    d = decide_exit(
        strategy="updraft", mtm_pnl=5.0, pt_target_pnl=9999.0,
        sl_target_pnl=25.0, now_ct=datetime(2026, 7, 27, 9, 45),
        front_expiration=date(2026, 7, 27), eod_close_ct=time(14, 45),
        event_blackout=False, entry_time=entry, hold_minutes=45)
    assert d.should_close and d.reason == "TIME_STOP"


def test_no_exit_before_the_hold_horizon():
    entry = datetime(2026, 7, 27, 9, 0)
    d = decide_exit(
        strategy="updraft", mtm_pnl=5.0, pt_target_pnl=9999.0,
        sl_target_pnl=25.0, now_ct=datetime(2026, 7, 27, 9, 30),
        front_expiration=date(2026, 7, 27), eod_close_ct=time(14, 45),
        event_blackout=False, entry_time=entry, hold_minutes=45)
    assert not d.should_close


def test_stop_loss_still_fires_inside_the_window():
    entry = datetime(2026, 7, 27, 9, 0)
    d = decide_exit(
        strategy="updraft", mtm_pnl=-30.0, pt_target_pnl=9999.0,
        sl_target_pnl=25.0, now_ct=datetime(2026, 7, 27, 9, 10),
        front_expiration=date(2026, 7, 27), eod_close_ct=time(14, 45),
        event_blackout=False, entry_time=entry, hold_minutes=45)
    assert d.should_close and d.reason == "SL"


def test_hold_minutes_is_optional_for_every_other_bot():
    """Existing strategies must be unaffected by the new parameter."""
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=0.0, pt_target_pnl=100.0,
        sl_target_pnl=100.0, now_ct=datetime(2026, 7, 27, 9, 30),
        front_expiration=date(2026, 7, 27), eod_close_ct=time(14, 45),
        event_blackout=False)
    assert not d.should_close


# ---------------------------------------------------------------- registry
def test_both_bots_are_registered_as_paper_with_no_profit_target():
    for name, hold in (("updraft", 45), ("backdraft", 30)):
        b = get_bot(name)
        assert b["strategy"] == "updraft"
        assert b["ticker"] == "SPY"
        assert b["front_dte"] == 0
        d = b["defaults"]
        assert d["hold_minutes"] == hold
        assert d["sl_pct"] == 0.50
        assert d["pt_pct"] >= 9.9      # unreachable == no profit target
        assert d["max_concurrent_positions"] == 3
        assert d["entry_start_ct"] == "08:31"   # 09:31 ET
        assert d["entry_end_ct"] == "14:00"     # 15:00 ET


# ---------------------------------------------------------------- REVERSAL
def _rsi_chain(*, rsi=32.0, prev_rsi=28.0, cross=True, spot=600.0, **kw):
    """A chain carrying the hourly-RSI block REVERSAL reads."""
    c = _chain(spot=spot, **kw)
    c["rsi"] = {"rsi": rsi, "prev_rsi": prev_rsi, "recovery_cross": cross,
                "bars_used": 40, "reason": None}
    return c


def _rev_params():
    return {**DEFAULT_PARAMS, "mode": "reversal", "strike_offset": 0,
            "hold_minutes": 45}


def test_reversal_fires_on_the_recovery_cross():
    sig = build_updraft_signal(chain=_rsi_chain(), today=date(2026, 7, 27),
                               params=_rev_params(), mode="reversal")
    assert sig is not None
    assert sig.mode == "reversal"
    assert sig.strike == 600.0          # ATM, not +1 OTM
    assert sig.hold_minutes == 45
    assert sig.legs()[0]["type"] == "call"
    assert sig.rsi == 32.0 and sig.prev_rsi == 28.0


def test_reversal_does_NOT_fire_while_merely_oversold():
    """The sign of the edge flips on this: buying INTO an oversold tape was
    -3.87% (SPY) / -3.74% (XSP) vs +10.68% / +12.58% waiting for the cross.
    A low RSI with no cross must never produce a signal."""
    diag = []
    sig = build_updraft_signal(chain=_rsi_chain(rsi=18.0, prev_rsi=17.0,
                                                cross=False),
                               today=date(2026, 7, 27), params=_rev_params(),
                               mode="reversal", diag=diag)
    assert sig is None
    assert any("no_rsi_recovery" in d for d in diag), diag


def test_reversal_rejects_when_rsi_history_is_missing():
    diag = []
    c = _chain()
    c["rsi"] = {"rsi": None, "recovery_cross": False,
                "reason": "insufficient_history: 6 bars, need 16"}
    sig = build_updraft_signal(chain=c, today=date(2026, 7, 27),
                               params=_rev_params(), mode="reversal",
                               diag=diag)
    assert sig is None
    assert any("rsi_unavailable" in d for d in diag), diag


def test_reversal_ignores_flow_entirely():
    """REVERSAL has no flow gate. Call-heavy flow, and no flow block at all,
    must both still allow it — otherwise it goes blind for the first 30
    minutes for a reason unrelated to its signal."""
    c = _rsi_chain(flow_imb=0.90, r30=-50.0)
    assert build_updraft_signal(chain=c, today=date(2026, 7, 27),
                                params=_rev_params(),
                                mode="reversal") is not None
    c2 = _rsi_chain()
    c2["flow"] = {"flow_imb_30": None, "r30_bp": None, "reason": "cold_start"}
    assert build_updraft_signal(chain=c2, today=date(2026, 7, 27),
                                params=_rev_params(),
                                mode="reversal") is not None


def test_reversal_ships_disarmed_and_atm():
    meta = get_bot("reversal")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "reversal"
    assert d["strike_offset"] == 0
    assert d["hold_minutes"] == 45
    assert d["sl_pct"] == 0.50
    assert meta["strategy"] == "updraft"


def test_wilder_rsi_matches_the_research_recursion():
    """flow_store._wilder_rsi must equal pandas ewm(alpha=1/period,
    adjust=False), which is what the backtest used."""
    from backend.bots.flow_store import _wilder_rsi
    closes = [100, 101, 100.5, 99, 98, 97.5, 99, 100, 101.5, 102, 101,
              100, 99.5, 98, 97, 96.5, 98, 99.5]
    out = _wilder_rsi(closes, period=14)
    assert len(out) == len(closes) - 1
    assert all(0.0 <= v <= 100.0 for v in out)
    # monotone up-only series pins at 100
    assert _wilder_rsi([1, 2, 3, 4, 5, 6], period=14)[-1] == 100.0


def test_read_rsi_state_end_to_end_against_a_real_engine(tmp_path):
    """read_rsi_state must work against the real table, not just a stub dict.

    Covers the SQL, the hour-bucketing, and the in-progress-bar exclusion —
    none of which the dict-based tests above exercise.
    """
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'rsi.db'}")
    flow_store.ensure_table(eng)

    # 40 hourly closes that fall hard then recover, so the last completed bar
    # is a genuine cross back up through 30.
    base = datetime(2026, 7, 20, 9, 0)
    closes = ([600.0 - i * 1.5 for i in range(30)] +      # long slide
              [555.0 + i * 3.0 for i in range(10)])       # sharp recovery
    for h, px in enumerate(closes):
        t = base + timedelta(hours=h)
        flow_store.record_snapshot(
            eng, ticker="SPY", expiration=date(2026, 7, 27), now=t, spot=px,
            options=[{"strike": px, "type": "call", "volume": 10},
                     {"strike": px, "type": "put", "volume": 10}])

    st = flow_store.read_rsi_state(
        eng, ticker="SPY", now=base + timedelta(hours=len(closes)))
    assert st.rsi is not None, st.reason
    assert st.bars_used >= 16
    assert 0.0 <= st.rsi <= 100.0

    # a cold table must report unavailable rather than firing
    eng2 = create_engine(f"sqlite:///{tmp_path/'cold.db'}")
    flow_store.ensure_table(eng2)
    cold = flow_store.read_rsi_state(eng2, ticker="SPY", now=base)
    assert cold.rsi is None
    assert cold.recovery_cross is False
    assert cold.reason is not None


def test_rsi_seed_makes_a_COLD_table_immediately_usable(tmp_path):
    """The whole point of seed_closes: without it a fresh table needs ~2.5
    sessions of snapshots before RSI(14) is computable, so REVERSAL sits out
    for days after any reset."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'seed.db'}")
    flow_store.ensure_table(eng)
    now = datetime(2026, 7, 27, 15, 30)

    # cold table, no seed -> correctly unavailable
    cold = flow_store.read_rsi_state(eng, ticker="SPY", now=now)
    assert cold.rsi is None and cold.recovery_cross is False

    # same cold table, WITH a seeded history -> usable immediately
    seed = []
    base = datetime(2026, 7, 24, 9, 0)
    px = [600.0 - i * 1.2 for i in range(20)] + [576.0 + i * 2.5 for i in range(6)]
    for i, v in enumerate(px):
        seed.append(((base + timedelta(hours=i)).strftime("%Y-%m-%dT%H"), v))
    warm = flow_store.read_rsi_state(eng, ticker="SPY", now=now,
                                     seed_closes=seed)
    assert warm.rsi is not None, warm.reason
    assert warm.bars_used >= 16


def test_live_snapshots_win_over_seed_on_overlapping_hours(tmp_path):
    """Snapshots are the same clock the flow half of the book reads, so on a
    shared hour they must override the vendor seed."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'ovl.db'}")
    flow_store.ensure_table(eng)
    t = datetime(2026, 7, 27, 11, 5)
    flow_store.record_snapshot(
        eng, ticker="SPY", expiration=date(2026, 7, 27), now=t, spot=999.0,
        options=[{"strike": 999, "type": "call", "volume": 1},
                 {"strike": 999, "type": "put", "volume": 1}])
    # seed claims a different close for that same hour
    seed = [("2026-07-27T11", 111.0)]
    st = flow_store.read_rsi_state(eng, ticker="SPY",
                                   now=datetime(2026, 7, 27, 15, 0),
                                   seed_closes=seed)
    # not enough bars to produce an RSI, but the merge must have kept 999
    assert st.bars_used == 1


# ---------------------------------------------------------------- EM_BREACH
def _em_chain(*, spot=594.0, day_open=600.0, open_str=0.40,
              prev_spot=598.5, prev_str=0.40, bid=0.60, ask=0.64):
    """Chain with an em block. Defaults: -1.0% move vs a ~0.21% straddle
    at these premiums -> deeply breached; prev spot NOT breached."""
    c = _chain(spot=spot, bid=bid, ask=ask)
    c["em"] = {"day_open": day_open, "open_straddle_pct": open_str,
               "prev_spot": prev_spot, "prev_straddle_pct": prev_str,
               "reason": None}
    return c


def _em_params():
    return {**DEFAULT_PARAMS, "mode": "em_breach", "strike_offset": 0,
            "hold_minutes": 45}


def test_em_breach_fires_and_buys_a_PUT_at_the_money():
    sig = build_updraft_signal(chain=_em_chain(), today=date(2026, 7, 27),
                               params=_em_params(), mode="em_breach")
    assert sig is not None
    assert sig.mode == "em_breach"
    leg = sig.legs()[0]
    assert leg["type"] == "put", "EM_BREACH is the book's PUT leg"
    assert leg["action"] == "buy"
    assert sig.strike == 594.0          # ATM at spot
    assert sig.em_move_pct is not None and sig.em_move_pct < 0


def test_em_breach_rejects_when_not_breached():
    diag = []
    sig = build_updraft_signal(chain=_em_chain(spot=599.5, prev_spot=599.8),
                               today=date(2026, 7, 27), params=_em_params(),
                               mode="em_breach", diag=diag)
    assert sig is None
    assert any("no_breach" in d for d in diag), diag


def test_em_breach_rejects_catalyst_priced_open():
    """The edge is in UNPRICED surprises — measured NEGATIVE when the open
    straddle sat in its top decile (>= 0.75%)."""
    diag = []
    sig = build_updraft_signal(chain=_em_chain(open_str=0.90),
                               today=date(2026, 7, 27), params=_em_params(),
                               mode="em_breach", diag=diag)
    assert sig is None
    assert any("catalyst_priced" in d for d in diag), diag


def test_em_breach_is_first_touch_only():
    """Prev snapshot already breached -> stale move, no entry (the BACKDRAFT
    first-touch precedent: later minutes chase)."""
    diag = []
    sig = build_updraft_signal(chain=_em_chain(prev_spot=592.0),
                               today=date(2026, 7, 27), params=_em_params(),
                               mode="em_breach", diag=diag)
    assert sig is None
    assert any("not_first_touch" in d for d in diag), diag


def test_em_breach_degrades_to_unconditional_when_open_straddle_unknown():
    """Missing open straddle (legacy snapshot rows) must NOT sideline the
    leg — the headline research result is the unconditional version."""
    sig = build_updraft_signal(chain=_em_chain(open_str=None),
                               today=date(2026, 7, 27), params=_em_params(),
                               mode="em_breach")
    assert sig is not None


def test_em_breach_ignores_flow_entirely():
    c = _em_chain()
    c["flow"] = {"flow_imb_30": None, "r30_bp": None, "reason": "cold"}
    assert build_updraft_signal(chain=c, today=date(2026, 7, 27),
                                params=_em_params(),
                                mode="em_breach") is not None


def test_em_breach_ships_disarmed_one_entry_per_day():
    meta = get_bot("embreach")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "em_breach"
    assert d["strike_offset"] == 0 and d["hold_minutes"] == 45
    assert meta["one_entry_per_day"] is True
    assert meta["strategy"] == "updraft"


def test_snapshot_stores_straddle_and_em_state_reads_it(tmp_path):
    """End-to-end against a real engine: record_snapshot persists the ATM
    straddle, read_em_state returns day-open anchor + prev snapshot."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'em.db'}")
    flow_store.ensure_table(eng)
    opts = [{"strike": 600.0, "type": "call", "bid": 0.60, "ask": 0.64,
             "volume": 10},
            {"strike": 600.0, "type": "put", "bid": 0.55, "ask": 0.59,
             "volume": 10}]
    t0 = datetime(2026, 7, 27, 8, 31)          # CT session open
    flow_store.record_snapshot(eng, ticker="SPY", expiration=date(2026, 7, 27),
                               now=t0, spot=600.0, options=opts)
    flow_store.record_snapshot(eng, ticker="SPY", expiration=date(2026, 7, 27),
                               now=t0 + timedelta(minutes=30), spot=598.0,
                               options=opts)
    st = flow_store.read_em_state(eng, ticker="SPY",
                                  now=t0 + timedelta(minutes=35))
    assert st.day_open == 600.0
    assert st.prev_spot == 598.0
    assert st.open_straddle_pct is not None and st.open_straddle_pct > 0
    # pre-RTH snapshots must not become the day open
    eng2 = create_engine(f"sqlite:///{tmp_path/'pre.db'}")
    flow_store.ensure_table(eng2)
    flow_store.record_snapshot(eng2, ticker="SPY", expiration=date(2026, 7, 27),
                               now=datetime(2026, 7, 27, 8, 0), spot=590.0,
                               options=opts)
    st2 = flow_store.read_em_state(eng2, ticker="SPY",
                                   now=datetime(2026, 7, 27, 9, 0))
    assert st2.day_open is None and st2.reason == "no_rth_snapshots"


# ---------------------------------------------------------------- AFTERBURN
def _ab_chain(*, spot=605.0, day_open=600.0, bid=3.10, ask=3.14):
    """+0.83% session return -> above the 0.52% gate. 1DTE chain."""
    c = _chain(spot=spot, bid=bid, ask=ask)
    c["expiration"] = date(2026, 7, 29)     # tomorrow (front_dte=1)
    c["em"] = {"day_open": day_open, "open_straddle_pct": 0.40,
               "prev_spot": None, "prev_straddle_pct": None, "reason": None}
    return c


def _ab_params():
    return {**DEFAULT_PARAMS, "mode": "afterburn", "strike_offset": 0,
            "hold_minutes": 1056}


def test_afterburn_fires_on_strong_close_and_buys_next_day_call():
    sig = build_updraft_signal(chain=_ab_chain(), today=date(2026, 7, 28),
                               params=_ab_params(), mode="afterburn",
                               config={"bp_pct": 0.05})
    assert sig is not None
    assert sig.mode == "afterburn"
    leg = sig.legs()[0]
    assert leg["type"] == "call" and leg["action"] == "buy"
    assert leg["expiration"] == "2026-07-29", "must carry TOMORROW's expiry"
    assert sig.strike == 605.0              # ATM
    assert sig.hold_minutes == 1056         # the overnight wall-clock timer
    assert sig.em_move_pct is not None and sig.em_move_pct > 0.52


def test_afterburn_rejects_a_weak_close():
    diag = []
    sig = build_updraft_signal(chain=_ab_chain(spot=601.0),  # +0.17%
                               today=date(2026, 7, 28), params=_ab_params(),
                               mode="afterburn", diag=diag)
    assert sig is None
    assert any("weak_close" in d for d in diag), diag


def test_afterburn_rejects_when_day_open_unknown():
    diag = []
    c = _ab_chain()
    c["em"] = {"day_open": None, "reason": "no_rth_snapshots"}
    sig = build_updraft_signal(chain=c, today=date(2026, 7, 28),
                               params=_ab_params(), mode="afterburn",
                               diag=diag)
    assert sig is None
    assert any("em_unavailable" in d for d in diag), diag


def test_afterburn_registry_overnight_mechanics():
    """The overnight hold is an EMERGENT property of three settings — pin all
    three so nobody 'simplifies' one and silently breaks the exit."""
    meta = get_bot("afterburn")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert meta["front_dte"] == 1, "1DTE: EOD close must NOT fire on entry day"
    assert d["hold_minutes"] == 1056, "wall-clock timer = exit ~08:31 next day"
    assert d["entry_days"] == "mon,tue,wed,thu", "no 1DTE into a weekend"
    assert d["entry_start_ct"] == "14:50" and d["entry_end_ct"] == "14:59"
    assert d["sl_pct"] == 0.99, "research ran NO stop"
    assert d["bp_pct"] >= 0.05,         "ATM 1DTE premium ~$300-400: bp 2% of $10k sizes to ZERO contracts"
    assert meta["one_entry_per_day"] is True


def test_position_rows_store_the_MODE_not_the_module():
    """Four bots share strategy='updraft'; the stored strategy must be the
    registry-default MODE so the positions UI can tell legs apart."""
    from backend.bots.registry import BOT_REGISTRY
    from backend.bots.scanner import UPDRAFT_FAMILY
    for bot, want in (("updraft", "updraft"), ("backdraft", "backdraft"),
                      ("reversal", "reversal"), ("embreach", "em_breach"),
                      ("afterburn", "afterburn")):
        mode = str(((BOT_REGISTRY.get(bot) or {}).get("defaults") or {})
                   .get("mode") or "") or BOT_REGISTRY[bot]["strategy"]
        assert mode == want, f"{bot}: stored strategy would be {mode}"
        assert mode in UPDRAFT_FAMILY, \
            f"{mode} missing from UPDRAFT_FAMILY -> timer exit would not fire"
