"""Tests for the UPDRAFT / BACKDRAFT 0DTE call book."""
from __future__ import annotations

from datetime import date, datetime, time

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
        assert d["pt_pct"] > 10       # unreachable == no profit target
        assert d["max_concurrent_positions"] == 3
        assert d["entry_start_ct"] == "08:31"   # 09:31 ET
        assert d["entry_end_ct"] == "14:00"     # 15:00 ET
