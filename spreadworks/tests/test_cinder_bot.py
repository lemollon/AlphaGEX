"""CINDER — the $500 PAPER bot (backend/bots/registry.py), NOT to be confused
with `backend/cinder_signal.py`'s already-live signal module of the same
name (see registry.py's "NAMING COLLISION" comment). This file only exercises
the paper bot's own registry/config rows and its scanner._evaluate_entry
macro gates; it never imports cinder_signal.py.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text

from backend.bots.db import bot_table, create_bot_tables, load_config
from backend.bots.registry import BOT_REGISTRY, get_bot
from backend.bots.scanner import ChainProvider, _evaluate_entry
from backend.bots.strategies.vertical_spread import (
    DEFAULT_VERTICAL_PARAMS, build_vertical_signal,
)

CT = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_cinder_registered():
    assert "cinder" in BOT_REGISTRY
    b = get_bot("cinder")
    assert b["display"] == "CINDER"
    assert b["strategy"] == "bull_call_spread"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 1
    assert b["back_dte"] is None
    assert b["one_entry_per_day"] is True
    assert b["params"]["spread_abs"] == 10.0


def test_cinder_defaults_are_500_paper_armed():
    d = get_bot("cinder")["defaults"]
    assert d["starting_capital"] == 500.0
    assert d["enabled"] is True
    assert d["max_contracts"] == 1
    # pt_pct=1.0 against a debit-spread's max_loss_per base means the exit
    # target is "spread value = 2x entry debit" — cinder_signal.py's own
    # TARGET_MULTIPLE. sl_pct=1.0 is unreachable by construction (a debit
    # spread cannot lose more than the debit paid).
    assert d["pt_pct"] == 1.0
    assert d["sl_pct"] == 1.0
    assert d["entry_start_ct"] == "10:25"
    assert d["entry_end_ct"] == "10:35"


def test_cinder_macro_gate_defaults_mirror_the_live_signal():
    d = get_bot("cinder")["defaults"]
    assert d["gex_ceiling_b"] == -10.0
    assert d["live_vix_ratio_max"] == 0.90
    assert d["require_vix_contango"] == 1
    assert d["entry_cooldown_days"] == 5


def test_only_cinder_carries_the_macro_gates():
    gated = sorted(b for b, d in BOT_REGISTRY.items()
                   if (d.get("defaults") or {}).get("gex_ceiling_b") is not None)
    assert gated == ["cinder"]


# ---------------------------------------------------------------------------
# Strike construction — ATM long call / $10-wide short call, 2x-debit target
# ---------------------------------------------------------------------------

def _chain(spot=670.0):
    # Gentle slope + a $0.30 floor so the SHORT leg (the far-OTM $680 call —
    # _spread_ok's quality checks apply to the SOLD leg on a debit spread,
    # never the bought one) clears min_option_price=0.10 / max_spread_pct=0.15.
    opts = []
    base = int(spot)
    for s in range(base - 30, base + 31, 1):
        call_mid = max(0.30, (spot - s) * 0.05 + 1.0)
        opts.append({"strike": s, "type": "call",
                     "bid": round(call_mid - 0.02, 2), "ask": round(call_mid + 0.02, 2)})
    return {"spot": spot, "expiration": "2026-10-07", "ticker": "SPY", "options": opts}


def test_cinder_strike_construction_is_atm_plus_10():
    params = {**DEFAULT_VERTICAL_PARAMS, **get_bot("cinder")["params"]}
    cfg = {"bp_pct": 0.80, "pt_pct": 1.0, "sl_pct": 1.0, "max_contracts": 1}
    sig = build_vertical_signal(kind="bull_call_spread", chain=_chain(670.0),
                                config=cfg, equity=500.0, params=params)
    assert sig is not None
    legs = sig.legs()
    long_leg = [l for l in legs if l["side"] == "long"][0]
    short_leg = [l for l in legs if l["side"] == "short"][0]
    assert long_leg["strike"] == 670   # ATM
    assert short_leg["strike"] == 680  # ATM + $10
    assert sig.width == 10
    assert sig.debit > 0
    # max_loss is exactly the debit paid (a debit spread's structural floor)
    assert sig.max_loss == round(sig.debit * 100, 2)
    # pt_pct=1.0 * max_loss_per (the sizing engine's debit base) == the debit
    # itself — i.e. the PROFIT needed is 100% of the debit, which means the
    # spread's mark must reach 2x the debit. This IS cinder_signal.py's
    # TARGET_MULTIPLE = 2.0, reached through the generic pt_pct machinery.
    pt_target = cfg["pt_pct"] * sig.max_loss * sig.contracts
    assert pt_target == pytest.approx(sig.debit * 100 * sig.contracts)


# ---------------------------------------------------------------------------
# Config seeding / backfill — same discipline as vix_decay_max/pivot_on_confirm
# ---------------------------------------------------------------------------

def test_cinder_config_seeds_the_macro_gate_columns():
    engine = create_engine("sqlite://")
    create_bot_tables(engine)
    cfg = load_config(engine, "cinder")
    assert float(cfg["gex_ceiling_b"]) == -10.0
    assert float(cfg["live_vix_ratio_max"]) == 0.90
    assert int(cfg["require_vix_contango"]) == 1
    assert int(cfg["entry_cooldown_days"]) == 5
    assert bool(cfg["enabled"]) is True
    assert float(cfg["starting_capital"]) == 500.0


def test_cinder_backfill_reaches_a_row_that_predates_the_default():
    engine = create_engine("sqlite://")
    create_bot_tables(engine)
    t = bot_table("cinder", "config")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {t} SET gex_ceiling_b = NULL WHERE id = 1"))
    assert load_config(engine, "cinder")["gex_ceiling_b"] is None
    create_bot_tables(engine)          # next startup must repair it
    assert float(load_config(engine, "cinder")["gex_ceiling_b"]) == -10.0


def test_cinder_backfill_never_overwrites_an_operator_value():
    engine = create_engine("sqlite://")
    create_bot_tables(engine)
    t = bot_table("cinder", "config")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {t} SET live_vix_ratio_max = 0.5 WHERE id = 1"))
    create_bot_tables(engine)
    assert float(load_config(engine, "cinder")["live_vix_ratio_max"]) == 0.5


# ---------------------------------------------------------------------------
# scanner._evaluate_entry macro gates
# ---------------------------------------------------------------------------

class _NoChainProvider(ChainProvider):
    """Every gate passes through to the real signal builder, which then
    fails on a missing chain — proves the macro gates let a clean day
    through rather than blocking it."""
    def get_chain(self, *, ticker, dte, today):
        return None
    def get_leg_mids(self, *, ticker, legs):
        return [None for _ in legs]
    def get_daily_history(self, *, ticker, days):
        return []
    def get_leg_spreads(self, *, ticker, legs):
        return [None for _ in legs]
    def get_leg_exit_prices(self, *, ticker, legs):
        return [None for _ in legs]
    def get_leg_exit_quotes(self, *, ticker, legs):
        return [None for _ in legs]


NOW_CT = datetime(2026, 10, 6, 10, 30, tzinfo=CT)  # inside 10:25-10:35 CT


def _setup(monkeypatch, *, gex_b=-15.0, gex_reason=None, vix_ratio=0.5,
          vix_now=15.0, vix3m_now=20.0, vix_fresh=True):
    engine = create_engine("sqlite://")
    create_bot_tables(engine)
    meta = get_bot("cinder")
    cfg = load_config(engine, "cinder")

    monkeypatch.setattr("backend.bots.scanner.gamma_state",
                        lambda eng, asof: {"net_gex_b": gex_b, "reason": gex_reason})

    def fake_fetch_vol_indices(now=None):
        return {"available": True, "indices": {
            "VIX": {"price": vix_now, "fresh": vix_fresh},
            "VIX3M": {"price": vix3m_now, "fresh": vix_fresh},
        }}
    monkeypatch.setattr("backend.market_structure.fetch_vol_indices",
                        fake_fetch_vol_indices)
    monkeypatch.setattr("backend.routes_squeeze.live_vix_ratio",
                        lambda vix_now_: vix_ratio)
    return engine, meta, cfg


def _run(engine, meta, cfg):
    return _evaluate_entry(
        engine=engine, bot="cinder", meta=meta, cfg=cfg, now_ct=NOW_CT,
        chain_provider=_NoChainProvider(), event_blackout=False,
        allow_stacking=False, open_count=0, opens=[],
    )


def test_all_gates_clear_falls_through_to_signal_build(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch)
    out = _run(engine, meta, cfg)
    # Macro gates all passed; the only reason left to not trade is the fake
    # chain provider returning no chain.
    assert out["outcome"] == "NO_TRADE"
    assert "chain_unavailable" in out["reason"]


def test_gex_unknown_blocks(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch, gex_b=None, gex_reason="no_gamma_history")
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "BLOCKED_GEX_UNKNOWN"


def test_gex_above_ceiling_blocks(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch, gex_b=-2.0)  # not deep-short enough
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "BLOCKED_GEX_ABOVE_CEILING"


def test_live_vix_ratio_elevated_blocks(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch, vix_ratio=0.95)
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "BLOCKED_VIX_LIVE_ELEVATED"


def test_backwardation_blocks(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch, vix_now=28.0, vix3m_now=24.0)
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "BLOCKED_TERM_STRUCTURE_BACKWARDATED"


def test_stale_vol_reading_blocks_as_unknown_not_a_silent_pass(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch, vix_fresh=False)
    out = _run(engine, meta, cfg)
    assert out["outcome"] in ("BLOCKED_VIX_LIVE_UNKNOWN", "BLOCKED_TERM_STRUCTURE_UNKNOWN")


def test_cooldown_blocks_within_5_calendar_days(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch)
    t = bot_table("cinder", "positions")
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {t} (position_id, ticker, strategy, legs, entry_price,
                             contracts, entry_time, status, pt_target_pnl,
                             sl_target_pnl, max_profit, max_loss)
            VALUES ('p1', 'SPY', 'bull_call_spread', '[]', 3.50, 1, :et,
                    'OPEN', 350.0, 350.0, 650.0, 350.0)
        """), {"et": datetime(2026, 10, 4, 10, 30)})  # 2 calendar days before NOW_CT
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "BLOCKED_COOLDOWN_DAYS"


def test_cooldown_clears_after_5_calendar_days(monkeypatch):
    engine, meta, cfg = _setup(monkeypatch)
    t = bot_table("cinder", "positions")
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {t} (position_id, ticker, strategy, legs, entry_price,
                             contracts, entry_time, status, pt_target_pnl,
                             sl_target_pnl, max_profit, max_loss)
            VALUES ('p1', 'SPY', 'bull_call_spread', '[]', 3.50, 1, :et,
                    'OPEN', 350.0, 350.0, 650.0, 350.0)
        """), {"et": datetime(2026, 9, 30, 10, 30)})  # exactly 6 days before NOW_CT
    out = _run(engine, meta, cfg)
    assert out["outcome"] == "NO_TRADE"
    assert "chain_unavailable" in out["reason"]
