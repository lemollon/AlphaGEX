import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.bots.executor import (
    open_position, close_position, compute_mtm, list_open_positions,
    account_equity, configured_slippage_per_leg, DEFAULT_SLIPPAGE_PER_LEG,
    configured_fill_mode, DEFAULT_FILL_MODE,
)
from backend.bots.strategies.iron_butterfly import build_iron_butterfly_signal

CT = ZoneInfo("America/Chicago")


def test_open_and_list_position(db_session, fake_chain_0dte):
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 2, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    assert sig is not None
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    pid = open_position(engine, bot="surge", strategy="iron_butterfly",
                        signal=sig, now=now)
    assert pid.startswith("surge-2026-05-20-")
    opens = list_open_positions(engine, "surge")
    assert len(opens) == 1
    assert opens[0]["position_id"] == pid
    legs = json.loads(opens[0]["legs"])
    assert len(legs) == 4


def test_close_writes_to_closed_trades(db_session, fake_chain_0dte):
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    pid = open_position(engine, "surge", "iron_butterfly", sig, now)
    later = datetime(2026, 5, 20, 11, 0, tzinfo=CT)
    close_position(engine, bot="surge", position_id=pid,
                   close_value=sig.credit * 0.7, close_reason="PT", now=later)
    with engine.begin() as conn:
        ct = conn.execute(text(
            "SELECT * FROM surge_closed_trades WHERE position_id=:p"
        ), {"p": pid}).mappings().first()
    assert ct is not None
    assert ct["close_reason"] == "PT"
    assert float(ct["realized_pnl"]) > 0  # we received credit, bought back cheaper
    # original position now CLOSED
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT status FROM surge_positions WHERE position_id=:p"
        ), {"p": pid}).mappings().first()
    assert row["status"] == "CLOSED"


def test_compute_mtm_credit_strategy(fake_chain_0dte):
    """For an IBF (credit), MTM PnL = (entry_credit - cost_to_close) * contracts * 100."""
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    legs = sig.legs()
    cost_to_close = sig.credit * 0.5  # halved
    mtm_value, mtm_pnl = compute_mtm(
        strategy="iron_butterfly",
        legs=legs,
        entry_price=sig.credit,
        contracts=sig.contracts,
        leg_mids=[l["entry_price"] for l in legs],  # unused for this test path
        cost_to_close_override=cost_to_close,
    )
    expected = (sig.credit - cost_to_close) * sig.contracts * 100
    assert abs(mtm_pnl - expected) < 0.01


def test_account_equity_starts_at_config(db_session):
    engine = db_session.bind
    eq = account_equity(engine, "surge")
    assert eq == 10000.0


def test_compute_mtm_clamps_negative_long_fly_mark():
    """A long fly can never be worth less than zero. When stale/one-sided leg
    mids compute a negative unwind value, the mark must clamp to 0 so the loss
    can never exceed the debit (2026-07-06..08: negative combo marks realized
    -$175.50 on a $165 max-loss position and tripped phantom SLs)."""
    legs = [
        {"side": "long",  "type": "call", "strike": 498, "expiration": "2026-05-20", "entry_price": 3.25},
        {"side": "short", "type": "call", "strike": 501, "expiration": "2026-05-20", "entry_price": 1.60},
        {"side": "short", "type": "call", "strike": 501, "expiration": "2026-05-20", "entry_price": 1.60},
        {"side": "long",  "type": "call", "strike": 504, "expiration": "2026-05-20", "entry_price": 0.70},
    ]
    # Shorts marked richer than longs -> raw unwind value would be -0.85.
    mtm_value, mtm_pnl = compute_mtm(
        strategy="long_butterfly", legs=legs, entry_price=0.75, contracts=1,
        leg_mids=[0.10, 0.50, 0.50, 0.05],
    )
    assert mtm_value == 0.0
    assert mtm_pnl == -75.0  # exactly -debit, never deeper


# ---------------------------------------------------------------------------
# Slippage model: a real multi-leg fill crosses the spread on every leg, on
# entry AND exit. slip=0 must reproduce the old mid-fill numbers exactly.
# ---------------------------------------------------------------------------

_IC_LEGS = [
    {"side": "short", "type": "put",  "strike": 498, "expiration": "2026-05-20"},
    {"side": "short", "type": "call", "strike": 502, "expiration": "2026-05-20"},
    {"side": "long",  "type": "put",  "strike": 493, "expiration": "2026-05-20"},
    {"side": "long",  "type": "call", "strike": 507, "expiration": "2026-05-20"},
]
_IC_MIDS = [0.30, 0.25, 0.10, 0.05]  # cost to buy back = 0.55 - 0.15 = 0.40


def test_compute_mtm_slippage_zero_is_noop():
    """slip=0 (the default) must byte-match the pre-slippage mid-fill mark."""
    base = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                       entry_price=0.71, contracts=10, leg_mids=_IC_MIDS)
    explicit0 = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                            entry_price=0.71, contracts=10, leg_mids=_IC_MIDS,
                            slippage_per_leg=0.0)
    assert base == explicit0
    assert base[0] == 0.40  # unchanged cost-to-close


def test_compute_mtm_exit_slippage_credit():
    """Buying a 4-leg credit structure back costs n_legs*slip MORE, so the
    booked pnl drops by exactly n_legs*slip*contracts*100."""
    v0, p0 = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                         entry_price=0.71, contracts=10, leg_mids=_IC_MIDS)
    v2, p2 = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                         entry_price=0.71, contracts=10, leg_mids=_IC_MIDS,
                         slippage_per_leg=0.02)
    assert abs(v2 - (v0 + 4 * 0.02)) < 1e-9         # 0.40 -> 0.48
    assert abs((p0 - p2) - (4 * 0.02 * 10 * 100)) < 1e-6  # -$80


def test_compute_mtm_exit_slippage_debit_and_floor():
    """Debit unwind fetches n_legs*slip LESS; the net-long floor still holds."""
    p0 = compute_mtm(strategy="double_diagonal", legs=_IC_LEGS,
                     entry_price=0.50, contracts=10, leg_mids=_IC_MIDS)[1]
    p2 = compute_mtm(strategy="double_diagonal", legs=_IC_LEGS,
                     entry_price=0.50, contracts=10, leg_mids=_IC_MIDS,
                     slippage_per_leg=0.02)[1]
    assert abs((p0 - p2) - (4 * 0.02 * 10 * 100)) < 1e-6
    # long fly floored at 0 even with slippage pushing further negative
    fv = compute_mtm(strategy="long_butterfly", legs=_IC_LEGS,
                     entry_price=1.0, contracts=1, leg_mids=[0, 0, 0, 0],
                     slippage_per_leg=0.02)[0]
    assert fv == 0.0


def test_open_position_entry_slippage(db_session, fake_chain_0dte):
    """A mid-fill entry credit is reduced by n_legs*slip; an already-crossed
    fill (mid_fill=False, e.g. UPDRAFT's limit) is NOT re-charged."""
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    n_legs = len(sig.legs())
    pid = open_position(engine, "surge", "iron_butterfly", sig, now,
                        slippage_per_leg=0.02)
    stored = {p["position_id"]: p for p in list_open_positions(engine, "surge")}[pid]
    assert abs(float(stored["entry_price"]) - (sig.credit - n_legs * 0.02)) < 1e-9
    assert "slip" in (stored["notes"] or "")
    # mid_fill=False keeps the fill exactly as passed (no double charge)
    pid2 = open_position(engine, "surge", "iron_butterfly", sig, now,
                         slippage_per_leg=0.02, mid_fill=False)
    stored2 = {p["position_id"]: p for p in list_open_positions(engine, "surge")}[pid2]
    assert abs(float(stored2["entry_price"]) - sig.credit) < 1e-9


def test_configured_slippage_precedence(monkeypatch):
    """bot-config column > env SPREADWORKS_SLIP_PER_LEG > DEFAULT."""
    monkeypatch.delenv("SPREADWORKS_SLIP_PER_LEG", raising=False)
    assert configured_slippage_per_leg(None) == DEFAULT_SLIPPAGE_PER_LEG
    assert configured_slippage_per_leg({"slippage_per_leg": 0}) == 0.0
    assert configured_slippage_per_leg({"slippage_per_leg": 0.05}) == 0.05
    monkeypatch.setenv("SPREADWORKS_SLIP_PER_LEG", "0.03")
    assert configured_slippage_per_leg(None) == 0.03
    # explicit config still wins over env
    assert configured_slippage_per_leg({"slippage_per_leg": 0.01}) == 0.01


def test_slippage_total_overrides_per_leg_on_exit():
    """slippage_total (measured taker cost) wins over the flat per-leg path."""
    # measured spreads: 0.005+0.005+0.02+0.03 = 0.06 total, NOT 4*0.02
    v0, p0 = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                         entry_price=0.71, contracts=10, leg_mids=_IC_MIDS)
    vt, pt = compute_mtm(strategy="iron_condor", legs=_IC_LEGS,
                         entry_price=0.71, contracts=10, leg_mids=_IC_MIDS,
                         slippage_per_leg=0.02, slippage_total=0.06)
    assert abs(vt - (v0 + 0.06)) < 1e-9              # total used, not 4*0.02=0.08
    assert abs((p0 - pt) - (0.06 * 10 * 100)) < 1e-6  # -$60, not -$80


def test_open_position_slippage_total(db_session, fake_chain_0dte):
    """A measured taker total reduces the entry credit by exactly that total."""
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    pid = open_position(engine, "surge", "iron_butterfly", sig, now,
                        slippage_total=0.055)
    stored = {p["position_id"]: p for p in list_open_positions(engine, "surge")}[pid]
    assert abs(float(stored["entry_price"]) - (sig.credit - 0.055)) < 1e-9


def test_configured_fill_mode_precedence(monkeypatch):
    """fill mode: bot config > env SPREADWORKS_FILL_MODE > taker default."""
    monkeypatch.delenv("SPREADWORKS_FILL_MODE", raising=False)
    assert configured_fill_mode(None) == DEFAULT_FILL_MODE == "taker"
    assert configured_fill_mode({"fill_mode": "half"}) == "half"
    assert configured_fill_mode({"fill_mode": "MID"}) == "mid"      # case-insensitive
    assert configured_fill_mode({"fill_mode": "bogus"}) == "taker"  # invalid ignored
    monkeypatch.setenv("SPREADWORKS_FILL_MODE", "mid")
    assert configured_fill_mode(None) == "mid"
    assert configured_fill_mode({"fill_mode": "taker"}) == "taker"  # config wins
