import pytest

from backend.bots.strategies.iron_butterfly import (
    build_iron_butterfly_signal,
    IronButterflySignal,
)


def _config(**overrides):
    base = {
        "starting_capital": 10000,
        "max_contracts": 2,
        "bp_pct": 0.10,
        "sd_mult": 1.0,
        "pt_pct": 0.30,
        "sl_pct": 2.0,
        "use_gex_walls": False,
    }
    base.update(overrides)
    return base


def test_picks_atm_body_and_symmetric_wings(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 500
    # Wing distance = 1.0 * 4.0 * 0.85 ~= 3.4 -> round to 3 -> wings at 497/503
    assert sig.long_put_strike == 497
    assert sig.long_call_strike == 503


def test_skips_when_vix_too_high(fake_chain_0dte):
    chain = {**fake_chain_0dte, "vix": 30.0}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_skips_when_flip_too_close(fake_chain_0dte):
    chain = {**fake_chain_0dte, "gex": {"flip_point": 500.5, "call_wall": 505, "put_wall": 496}}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_skips_when_credit_below_floor(fake_chain_0dte):
    # Squeeze all premiums to ~zero to force credit < 0.30
    chain = {
        **fake_chain_0dte,
        "options": [
            {**o, "bid": 0.01, "ask": 0.02} for o in fake_chain_0dte["options"]
        ],
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_credit_sizing(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    # Body credit = (2.05 + 2.05) - (0.55 + 0.55) but with 1c slippage either side.
    # We expect a positive credit and contracts >= 1.
    assert sig.credit > 0.30
    assert sig.contracts >= 1
    assert sig.contracts <= 2  # bounded by max_contracts


def test_gex_walls_clip_wings(fake_chain_0dte):
    # call_wall=505 sits OUTSIDE the computed wing (503) so clipping should
    # not change call wing, but put_wall=496 also outside put wing (497).
    # Move put_wall inside to verify clipping.
    chain = {
        **fake_chain_0dte,
        "gex": {"flip_point": 502.0, "call_wall": 505.0, "put_wall": 498.0},
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    # Put wing clipped UP to put_wall (closer to body)
    assert sig.long_put_strike == 498


def test_returns_legs_in_signal(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    legs = sig.legs()
    assert len(legs) == 4
    sides = {(l["side"], l["type"]) for l in legs}
    assert sides == {("short", "call"), ("short", "put"),
                     ("long", "call"), ("long", "put")}
