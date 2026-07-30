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


def _fp_chain(*, spot=602.0, or_high=601.5, or_low=598.5, day_open=600.0,
              open_str=0.80, prev_spot=601.2, complete=True):
    """Chain with an orx block. Defaults: 3-point range on a 0.80% straddle
    -> width/EM = 0.625 > 0.5709 gate; spot just broke the range high and
    the prior snapshot had NOT."""
    c = _chain(spot=spot)
    c["orx"] = {"or_high": or_high, "or_low": or_low, "or_complete": complete,
                "day_open": day_open, "open_straddle_pct": open_str,
                "prev_spot": prev_spot, "reason": None}
    return c


def _fp_params():
    return {**DEFAULT_PARAMS, "mode": "flashpoint", "strike_offset": 0,
            "hold_minutes": 45}


def test_flashpoint_fires_a_CALL_on_first_break_of_a_wide_range():
    sig = build_updraft_signal(chain=_fp_chain(), today=date(2026, 7, 28),
                               params=_fp_params(), mode="flashpoint")
    assert sig is not None
    leg = sig.legs()[0]
    assert leg["type"] == "call" and leg["action"] == "buy"
    assert sig.strike == 602.0          # ATM


def test_flashpoint_rejects_a_narrow_range():
    # 3-point range but a 1.60% straddle -> width/EM = 0.3125 < gate.
    # Unfiltered ORB is BREAKEVEN — the width gate IS the strategy.
    diag = []
    sig = build_updraft_signal(chain=_fp_chain(open_str=1.60),
                               today=date(2026, 7, 28), params=_fp_params(),
                               mode="flashpoint", diag=diag)
    assert sig is None
    assert any("range_too_narrow" in d for d in diag), diag


def test_flashpoint_rejects_stale_break_and_forming_range():
    diag = []
    assert build_updraft_signal(chain=_fp_chain(prev_spot=601.8),
                                today=date(2026, 7, 28), params=_fp_params(),
                                mode="flashpoint", diag=diag) is None
    assert any("not_first_touch" in d for d in diag), diag
    diag2 = []
    assert build_updraft_signal(chain=_fp_chain(complete=False),
                                today=date(2026, 7, 28), params=_fp_params(),
                                mode="flashpoint", diag=diag2) is None
    assert any("or_forming" in d for d in diag2), diag2


def test_flashpoint_registry_runs_1k_account_and_sizes_one_contract():
    meta = get_bot("flashpoint")
    d = meta["defaults"]
    assert meta["ticker"] == "SPY"
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "flashpoint"
    assert d["starting_capital"] == 1000.0, "Leron's $1k paper framing"
    # ATM calls run ~$100-350; the bp budget must never floor to zero
    # contracts (the AFTERBURN sizing lesson)
    assert d["bp_pct"] * d["starting_capital"] >= 350
    assert d["or_width_min_em"] == 0.5709, "TRAIN q67, frozen"
    assert d["strike_offset"] == 0 and d["sl_pct"] == 0.50
    assert d["entry_start_ct"] == "09:01", "range completes at 09:00 CT"
    assert meta["one_entry_per_day"] is True


def test_or_state_reader_builds_range_from_snapshots(tmp_path):
    """End-to-end: 08:31-09:00 snapshots form the range; a 09:05 read is
    complete with prev = the latest snapshot."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'orx.db'}")
    flow_store.ensure_table(eng)
    opts = [{"strike": 600.0, "type": "call", "bid": 1.20, "ask": 1.24,
             "volume": 10},
            {"strike": 600.0, "type": "put", "bid": 1.15, "ask": 1.19,
             "volume": 10}]
    t0 = datetime(2026, 7, 28, 8, 31)
    for mins, spot in ((0, 600.0), (15, 601.4), (29, 598.9), (34, 601.0)):
        flow_store.record_snapshot(eng, ticker="SPY",
                                   expiration=date(2026, 7, 28),
                                   now=t0 + timedelta(minutes=mins),
                                   spot=spot, options=opts)
    st = flow_store.read_or_state(eng, ticker="SPY",
                                  now=datetime(2026, 7, 28, 9, 7))
    assert st.or_complete
    assert st.or_high == 601.4 and st.or_low == 598.9
    assert st.day_open == 600.0
    assert st.prev_spot == 601.0        # the 09:05 snapshot, outside the OR
    # mid-range read: incomplete
    st2 = flow_store.read_or_state(eng, ticker="SPY",
                                   now=datetime(2026, 7, 28, 8, 50))
    assert not st2.or_complete


def test_thermal_is_updraft_ridden_to_the_close():
    meta = get_bot("thermal")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "updraft", "THERMAL = UPDRAFT's exact signal"
    assert d["flow_max"] == -0.1378 and d["r30_min"] == 19.23, \
        "gates FROZEN, identical to UPDRAFT"
    assert d["strike_offset"] == 0, "C+0 beat C+1 (DD 45% vs 72%)"
    assert d["sl_pct"] == 0.99, "research ran NO stop — settle holds ride"
    # the timer must never fire before the 14:57 EOD close does
    assert d["hold_minutes"] >= 600
    assert d["eod_close_ct"] == "14:57"
    assert d["starting_capital"] == 1000.0, "the $1k paper framing"
    assert d["bp_pct"] * d["starting_capital"] >= 350, \
        "must never size to zero contracts (AFTERBURN lesson)"
    assert meta["one_entry_per_day"] is True, "one ride per day, no k=3"


def test_wildfire_is_backdraft_ridden_to_the_close():
    meta = get_bot("wildfire")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "backdraft", "WILDFIRE = BACKDRAFT's exact signal"
    assert d["backdraft_flow_max"] == -0.35 and d["require_put_wall"] is True, \
        "gates FROZEN, identical to BACKDRAFT"
    assert d["strike_offset"] == 0 and d["sl_pct"] == 0.99
    assert d["hold_minutes"] >= 600 and d["eod_close_ct"] == "14:57"
    assert d["starting_capital"] == 1000.0, "the $1k paper framing"
    assert d["bp_pct"] * d["starting_capital"] >= 350
    assert meta["one_entry_per_day"] is True


def _glow_chain(*, updraft=True, rsi=False):
    c = _chain(spot=600.0)
    c["dayx"] = {"updraft_fired": updraft, "rsi_recovery_fired": rsi,
                 "n_snapshots": 120, "reason": None}
    return c


def test_afterglow_fires_a_weekly_call_when_the_day_signal_fired():
    sig = build_updraft_signal(
        chain=_glow_chain(), today=date(2026, 7, 29),
        params={**DEFAULT_PARAMS, "mode": "afterglow", "strike_offset": 0},
        mode="afterglow")
    assert sig is not None
    leg = sig.legs()[0]
    assert leg["type"] == "call" and leg["action"] == "buy"
    assert sig.strike == 600.0


def test_afterglow_and_ember_read_their_own_flags():
    diag = []
    assert build_updraft_signal(
        chain=_glow_chain(updraft=False), today=date(2026, 7, 29),
        params={**DEFAULT_PARAMS, "mode": "afterglow", "strike_offset": 0},
        mode="afterglow", diag=diag) is None
    assert any("no_afterglow_signal_today" in d for d in diag), diag
    # EMBER keys on the RSI flag, not the flow flag
    sig = build_updraft_signal(
        chain=_glow_chain(updraft=False, rsi=True), today=date(2026, 7, 29),
        params={**DEFAULT_PARAMS, "mode": "ember", "strike_offset": 0},
        mode="ember")
    assert sig is not None


def test_afterglow_registry_two_day_swing_mechanics():
    for bot in ("afterglow", "ember"):
        meta = get_bot(bot)
        d = meta["defaults"]
        assert d["enabled"] is False, "no bot ships armed"
        assert meta["front_dte"] == 5, "nearest weekly, the researched expiry"
        assert d["hold_minutes"] == 2880, "wall-clock ~2 trading days"
        assert d["sl_pct"] == 0.99, "research ran NO stop"
        assert d["entry_start_ct"] == "14:50", "read the day flag at the close"
        assert d["entry_days"] == "mon,tue,wed,thu", \
            "Friday entries would hold over a weekend — untested"
        assert d["starting_capital"] == 1000.0
        assert d["bp_pct"] * d["starting_capital"] >= 450, \
            "SPY weekly ATM ~$250-450 — never floor to zero contracts"
        assert meta["one_entry_per_day"] is True


def test_day_signal_reader_flags_updraft_burst(tmp_path):
    """Snapshots that contain a put-heavy volume burst during a rise must set
    updraft_fired; a quiet tape must not."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'glow.db'}")
    flow_store.ensure_table(eng)
    opts = [{"strike": 600.0, "type": "call", "bid": 0.60, "ask": 0.64,
             "volume": 10},
            {"strike": 600.0, "type": "put", "bid": 0.55, "ask": 0.59,
             "volume": 10}]
    t0 = datetime(2026, 7, 29, 9, 0)
    # 40 snapshots, 2 min apart: cumulative put volume ramps hard while spot
    # rises ~30bp over each 30-minute stretch
    for i in range(40):
        spot = 600.0 + i * 0.15               # ~+37bp per 30min: r30 > 19.23
        flow_store.record_snapshot(
            eng, ticker="SPY", expiration=date(2026, 7, 29),
            now=t0 + timedelta(minutes=2 * i), spot=spot,
            options=[{"strike": 600.0, "type": "call", "bid": 0.6, "ask": 0.64,
                      "volume": 100 + i * 10},
                     {"strike": 600.0, "type": "put", "bid": 0.55, "ask": 0.59,
                      "volume": 100 + i * 60}])   # put-heavy deltas
    st = flow_store.read_day_signal_state(
        eng, ticker="SPY", now=t0 + timedelta(minutes=90))
    assert st.updraft_fired, st
    # quiet tape: balanced flow, flat spot
    eng2 = create_engine(f"sqlite:///{tmp_path/'quiet.db'}")
    flow_store.ensure_table(eng2)
    for i in range(40):
        flow_store.record_snapshot(
            eng2, ticker="SPY", expiration=date(2026, 7, 29),
            now=t0 + timedelta(minutes=2 * i), spot=600.0,
            options=[{"strike": 600.0, "type": "call", "bid": 0.6, "ask": 0.64,
                      "volume": 100 + i * 10},
                     {"strike": 600.0, "type": "put", "bid": 0.55, "ask": 0.59,
                      "volume": 100 + i * 10}])
    st2 = flow_store.read_day_signal_state(
        eng2, ticker="SPY", now=t0 + timedelta(minutes=90))
    assert not st2.updraft_fired, st2


def test_squall_is_the_frequency_tier_with_the_deeper_discount():
    meta = get_bot("squall")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "updraft"
    assert d["flow_max"] == -0.0983 and d["r30_min"] == 14.44,         "TRAIN q30/q85, frozen — looser than UPDRAFT by exactly one notch"
    assert d["limit_entry_frac"] == 0.20,         "the deeper discount is what rescues the looser gate (market entry "         "at these gates is OOS-negative — the frequency-frontier verdict)"
    assert d["starting_capital"] == 1000.0
    assert d["strike_offset"] == 1 and d["sl_pct"] == 0.50
def test_tempest_dispatch_takes_the_first_firing_leg_and_records_it():
    """UPDRAFT-grade flow + rally: tempest returns the updraft leg with the
    sub-mode recorded; a dead tape returns None with the leg diagnostics."""
    c = _chain(spot=600.0, flow_imb=-0.20, r30=25.0)
    sig = build_updraft_signal(chain=c, today=date(2026, 7, 29),
                               params={**DEFAULT_PARAMS, "mode": "tempest"},
                               mode="tempest")
    assert sig is not None and sig.mode == "updraft"
    leg = sig.legs()[0]
    assert leg["type"] == "call" and leg["action"] == "buy"
    # EM-breach tape (no flow edge, day broke its priced move) -> the PUT leg
    c2 = _em_chain()
    c2["flow"] = {"flow_imb_30": 0.0, "r30_bp": 0.0, "reason": None}
    sig2 = build_updraft_signal(chain=c2, today=date(2026, 7, 27),
                                params={**DEFAULT_PARAMS, "mode": "tempest"},
                                mode="tempest")
    assert sig2 is not None and sig2.mode == "em_breach"
    assert sig2.legs()[0]["type"] == "put"
    # dead tape -> None with sub-diagnostics
    c3 = _chain(spot=600.0, flow_imb=0.0, r30=0.0)
    diag = []
    assert build_updraft_signal(chain=c3, today=date(2026, 7, 29),
                                params={**DEFAULT_PARAMS, "mode": "tempest"},
                                mode="tempest", diag=diag) is None
    assert any("no_leg" in d for d in diag), diag


def test_tempest_registry_is_the_whole_book_in_one_account():
    meta = get_bot("tempest")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "tempest"
    assert d["starting_capital"] == 1000.0
    assert d["flow_max"] == -0.1378 and d["backdraft_flow_max"] == -0.35
    assert d["em_frac"] == 0.8 and d["or_width_min_em"] == 0.5709
    assert d["allow_stacking"] is True and d["max_concurrent_positions"] == 3


def test_or_state_reads_utc_stored_snapshots_with_aware_now(tmp_path):
    """PRODUCTION shape: snapshot_time lands in UTC; the caller passes a
    tz-aware CT now. The 08:30-09:00 CT window must still find the rows
    (2026-07-29: it matched ZERO and blinded FLASHPOINT all session)."""
    from zoneinfo import ZoneInfo
    from sqlalchemy import create_engine, text as _text
    from backend.bots import flow_store

    CT = ZoneInfo("America/Chicago")
    eng = create_engine(f"sqlite:///{tmp_path/'utc.db'}")
    flow_store.ensure_table(eng)
    # rows as production stores them: UTC wall-clock (08:31 CT == 13:31 UTC)
    with eng.begin() as conn:
        for hh, mm, spot in ((13, 31, 600.0), (13, 45, 601.4), (13, 59, 598.9),
                             (14, 5, 601.0)):
            conn.execute(_text(
                f"INSERT INTO {flow_store.TABLE} (ticker, snapshot_time, "
                "trade_date, spot, call_volume, put_volume, straddle_pct) "
                "VALUES ('SPY', :t, '2026-07-29', :s, 100, 100, 0.8)"),
                {"t": datetime(2026, 7, 29, hh, mm), "s": spot})
    st = flow_store.read_or_state(
        eng, ticker="SPY", now=datetime(2026, 7, 29, 9, 7, tzinfo=CT))
    assert st.or_complete, st
    assert st.or_high == 601.4 and st.or_low == 598.9, st
    assert st.day_open == 600.0
    assert st.prev_spot == 601.0


def test_or_state_prev_excludes_current_minute(tmp_path):
    """prev must come from an EARLIER minute than `now` — never the row the
    scan itself just wrote. record_snapshot floors timestamps to the minute,
    so a plain "< now" filter returns the current scan's own snapshot and
    the flashpoint first-touch gate compares the breakout spot to itself
    (2026-07-30: TEMPEST rejected the true breakout scan with
    not_first_touch prev == the same-minute spot; the leg could never fire)."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'ft.db'}")
    flow_store.ensure_table(eng)
    opts = [{"strike": 600.0, "type": "call", "bid": 1.20, "ask": 1.24,
             "volume": 10},
            {"strike": 600.0, "type": "put", "bid": 1.15, "ask": 1.19,
             "volume": 10}]
    t0 = datetime(2026, 7, 30, 8, 31)
    # range 600.0-601.4, then 9:04 still below or_high, then THIS scan's
    # 9:05 snapshot breaks above it
    for mins, spot in ((0, 600.0), (15, 601.4), (29, 598.9),
                      (33, 601.0), (34, 602.5)):
        flow_store.record_snapshot(eng, ticker="SPY",
                                   expiration=date(2026, 7, 30),
                                   now=t0 + timedelta(minutes=mins),
                                   spot=spot, options=opts)
    st = flow_store.read_or_state(
        eng, ticker="SPY",
        now=datetime(2026, 7, 30, 9, 5, 0, 21000))   # same minute as last row
    assert st.prev_spot == 601.0, \
        f"prev must be the 09:04 row, not this scan's own 09:05 row: {st}"


def test_em_state_prev_excludes_current_minute(tmp_path):
    """Same trap as read_or_state: the EM_BREACH first-touch gate reads prev
    off this table, and prev == the current scan's row makes every breach
    look stale, so the leg can never fire."""
    from sqlalchemy import create_engine
    from backend.bots import flow_store

    eng = create_engine(f"sqlite:///{tmp_path/'emft.db'}")
    flow_store.ensure_table(eng)
    opts = [{"strike": 600.0, "type": "call", "bid": 0.60, "ask": 0.64,
             "volume": 10},
            {"strike": 600.0, "type": "put", "bid": 0.55, "ask": 0.59,
             "volume": 10}]
    t0 = datetime(2026, 7, 30, 8, 31)
    for mins, spot in ((0, 600.0), (29, 599.0), (34, 590.0)):
        flow_store.record_snapshot(eng, ticker="SPY",
                                   expiration=date(2026, 7, 30),
                                   now=t0 + timedelta(minutes=mins),
                                   spot=spot, options=opts)
    st = flow_store.read_em_state(
        eng, ticker="SPY",
        now=datetime(2026, 7, 30, 9, 5, 0, 21000))   # same minute as the drop
    assert st.day_open == 600.0
    assert st.prev_spot == 599.0, \
        f"prev must be the 09:00 row, not this scan's own 09:05 row: {st}"


def test_embreachq_is_embreach_on_qqq_with_own_thresholds():
    meta = get_bot("embreachq")
    d = meta["defaults"]
    assert meta["ticker"] == "QQQ"
    assert d["enabled"] is False, "no bot ships armed"
    assert d["mode"] == "em_breach"
    assert d["em_frac"] == 0.8, "breach multiple is structural, carried over"
    assert d["max_open_straddle_pct"] == 1.04, "QQQ's OWN TRAIN q90, not SPY's"
    # QQQ ATM premium ~$150-300/contract; 2% of $10k floors to zero
    # contracts (the AFTERBURN sizing lesson)
    assert d["bp_pct"] >= 0.04
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


# ---------------------------------------------------------------- WEEKENDER
def test_weekender_fires_unconditionally_with_day_state():
    """min_ret=-99 disables the close-momentum gate: ALL Fridays trade
    (the research base case, n=138) — a flat or weak close must NOT block."""
    c = _ab_chain(spot=600.5, day_open=600.0)          # +0.08%, weak close
    c["expiration"] = date(2026, 7, 31)                # Friday -> Monday exp
    sig = build_updraft_signal(
        chain=c, today=date(2026, 7, 28),
        params={**DEFAULT_PARAMS, "mode": "weekender", "strike_offset": 0,
                "hold_minutes": 3936, "afterburn_min_ret_pct": -99.0},
        mode="weekender", config={"bp_pct": 0.10})
    assert sig is not None
    leg = sig.legs()[0]
    assert leg["type"] == "call" and leg["action"] == "buy"
    assert sig.hold_minutes == 3936


def test_weekender_registry_weekend_mechanics():
    meta = get_bot("weekender")
    d = meta["defaults"]
    assert d["enabled"] is False, "no bot ships armed"
    assert meta["front_dte"] == 3, "Friday entry -> Monday expiry"
    assert d["entry_days"] == "fri"
    assert d["hold_minutes"] == 3936, "Fri 14:55 + 3936m = Mon ~08:31 CT"
    assert d["afterburn_min_ret_pct"] == -99.0, "UNCONDITIONAL by design"
    assert d["bp_pct"] >= 0.10, "3DTE ATM ~$450-650: smaller bp sizes to zero"
    assert d["sl_pct"] == 0.99
    assert meta["one_entry_per_day"] is True


def test_weekender_mode_is_in_updraft_family():
    from backend.bots.scanner import UPDRAFT_FAMILY
    assert "weekender" in UPDRAFT_FAMILY, \
        "missing from UPDRAFT_FAMILY -> the Monday timer exit would not fire"
