import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.bots.executor import (
    open_position, close_position, compute_mtm, list_open_positions,
    account_equity,
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
