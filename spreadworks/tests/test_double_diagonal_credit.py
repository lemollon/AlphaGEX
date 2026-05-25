"""MEADOW — credit double diagonal builder tests.

Front (6 DTE) short strangle close to the money, back (9 DTE) long strangle
$5 further OTM. Net CREDIT, short vega, positive theta — the inverse of DRIFT.
"""
from backend.bots.strategies.double_diagonal_credit import (
    build_double_diagonal_credit_signal,
)


def _cfg(**o):
    base = {"max_contracts": 2, "bp_pct": 0.10, "sd_mult": 1.0,
            "pt_pct": 0.50, "sl_pct": 1.0, "starting_capital": 10000}
    base.update(o)
    return base


def test_builds_a_net_credit_signal(fake_chain_6dte, fake_chain_9dte):
    sig = build_double_diagonal_credit_signal(
        front_chain=fake_chain_6dte, back_chain=fake_chain_9dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # Shorts at spot ± 1.0 * straddle(6) = 494 / 506, snapped to front strikes.
    assert sig.short_put_strike == 494
    assert sig.short_call_strike == 506
    # Longs $5 further OTM, snapped to back strikes.
    assert sig.long_put_strike == 489
    assert sig.long_call_strike == 511
    # Credit = (2.00 + 2.00) - (1.20 + 1.20) = 1.60  (a positive credit).
    assert sig.credit == 1.60
    assert hasattr(sig, "credit")


def test_risk_math_is_iron_condor_shaped(fake_chain_6dte, fake_chain_9dte):
    sig = build_double_diagonal_credit_signal(
        front_chain=fake_chain_6dte, back_chain=fake_chain_9dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # wing = max(494-489, 511-506) = 5
    assert sig.max_profit == 160.0           # credit * 100
    assert sig.max_loss == 340.0             # (5 - 1.60) * 100


def test_sizes_by_buying_power(fake_chain_6dte, fake_chain_9dte):
    # equity 10k * bp 0.10 = 1000 budget / 340 max_loss = 2 contracts.
    sig = build_double_diagonal_credit_signal(
        front_chain=fake_chain_6dte, back_chain=fake_chain_9dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    assert sig.contracts == 2
    # Targets use the credit (max_profit) reference, total $.
    assert sig.pt_target_pnl == 0.50 * 160.0 * 2   # 160
    assert sig.sl_target_pnl == 1.00 * 160.0 * 2   # 320


def test_legs_list_short_front_first(fake_chain_6dte, fake_chain_9dte):
    sig = build_double_diagonal_credit_signal(
        front_chain=fake_chain_6dte, back_chain=fake_chain_9dte,
        config=_cfg(), equity=10000.0,
    )
    legs = sig.legs()
    assert legs[0]["side"] == "short"
    assert legs[0]["expiration"] == "2026-05-27"   # front
    assert legs[2]["side"] == "long"
    assert legs[2]["expiration"] == "2026-05-30"   # back


def test_rejects_when_credit_below_minimum(fake_chain_6dte, fake_chain_9dte):
    # Demand more credit than this structure produces ($1.60).
    sig = build_double_diagonal_credit_signal(
        front_chain=fake_chain_6dte, back_chain=fake_chain_9dte,
        config=_cfg(min_credit=5.0), equity=10000.0,
    )
    assert sig is None


def test_rejects_when_vix_too_high(fake_chain_6dte, fake_chain_9dte):
    hot = {**fake_chain_6dte, "vix": 40.0}
    sig = build_double_diagonal_credit_signal(
        front_chain=hot, back_chain=fake_chain_9dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is None
