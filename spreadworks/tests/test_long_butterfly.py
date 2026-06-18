import pytest

from backend.bots.strategies.long_butterfly import (
    build_long_butterfly_signal,
    LongButterflySignal,
)


def _config(**overrides):
    base = {
        "starting_capital": 10000,
        "max_contracts": 2,
        "bp_pct": 0.10,
        "sd_mult": 1.0,
        "pt_pct": 0.30,
        "sl_pct": 0.50,
        "use_gex_walls": False,
    }
    base.update(overrides)
    return base


def _override(chain, strike, opt_type, bid, ask):
    """Return a copy of `chain` with one option's bid/ask replaced."""
    opts = []
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            opts.append({**o, "bid": bid, "ask": ask})
        else:
            opts.append(o)
    return {**chain, "options": opts}


def test_uses_pin_strike_when_no_magnets(fake_chain_0dte):
    # Fixture has pin_strike = 501 and NO magnets -> body falls back to the
    # predicted pin (NOT spot 500, NOT flip 502) — identical to BREEZE.
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 501
    # Wing distance = round(1.0 * 4.0 * 0.85) = 3 -> wings at 498 / 504.
    assert sig.lower_strike == 498
    assert sig.upper_strike == 504


def test_pins_between_two_large_magnets(fake_chain_0dte):
    chain = {
        **fake_chain_0dte,
        "gex": {
            "pin_strike": 502.0,
            "magnets": [
                {"strike": 497.0, "gamma": 1.0e9},
                {"strike": 501.0, "gamma": 1.0e9},
            ],
        },
    }
    sig = build_long_butterfly_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is not None
    assert sig.body_strike == 499  # gamma-weighted midpoint of 497 and 501


def test_pins_between_magnets_with_net_gamma_key(fake_chain_0dte):
    # Regression: the live WATCHTOWER engine emits magnets keyed by `net_gamma`
    # (core/watchtower_engine.identify_magnets), NOT `gamma`. The builder must
    # honor that key so the body centers on the magnet midpoint, not spot/pin.
    chain = {
        **fake_chain_0dte,
        "gex": {
            "pin_strike": 502.0,
            "magnets": [
                {"strike": 497.0, "net_gamma": -1.0e9, "probability": 40},
                {"strike": 501.0, "net_gamma": 1.0e9, "probability": 42},
            ],
        },
    }
    sig = build_long_butterfly_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is not None
    assert sig.body_strike == 499  # gamma-weighted midpoint of 497 and 501


def test_falls_back_to_spot_when_no_pin(fake_chain_0dte):
    chain = {**fake_chain_0dte, "gex": {"flip_point": 502.0}}
    sig = build_long_butterfly_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is not None
    assert sig.body_strike == 500


def test_debit_and_risk_math(fake_chain_0dte):
    # Body 501, wings 498/504. Symmetric fixture -> call and put flies cost the
    # same debit (0.75); a tie resolves to the call fly.
    #   498c=3.25  501c=1.60  504c=0.70 -> debit = 3.25 + 0.70 - 2*1.60 = 0.75
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.option_type == "call"
    assert sig.debit == pytest.approx(0.75)
    assert sig.wing_width == 3
    # max loss = debit paid; max profit = (wing - debit) at the body.
    assert sig.max_loss == pytest.approx(75.0)
    assert sig.max_profit == pytest.approx(225.0)


def test_pt_is_pct_of_max_profit_sl_is_pct_of_debit(fake_chain_0dte):
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    # equity 10000 * bp 0.10 = 1000 budget; 1000 // 75 = 13, capped to 2.
    assert sig.contracts == 2
    # PT = 0.30 * 225 * 2 = 135 ; SL = 0.50 * 75 * 2 = 75.
    assert sig.pt_target_pnl == pytest.approx(135.0)
    assert sig.sl_target_pnl == pytest.approx(75.0)


def test_auto_picks_cheaper_side(fake_chain_0dte):
    # Make the CALL fly expensive by collapsing the 501 call body mid (a lower
    # body mid raises the net debit). The put fly stays at 0.75, so the put
    # side must win.
    chain = _override(fake_chain_0dte, 501, "call", 1.00, 1.10)  # body mid 1.05
    # call debit now = 3.25 + 0.70 - 2*1.05 = 1.85 ; put debit = 0.75
    sig = build_long_butterfly_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is not None
    assert sig.option_type == "put"
    assert sig.debit == pytest.approx(0.75)


def test_skips_when_vix_too_high(fake_chain_0dte):
    chain = {**fake_chain_0dte, "vix": 30.0}
    sig = build_long_butterfly_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is None


def test_rejects_non_positive_debit(fake_chain_0dte):
    # Make BOTH bodies extremely expensive so every candidate debit is <= 0
    # (a degenerate/credit fly) — must reject, never open.
    chain = _override(fake_chain_0dte, 501, "call", 5.00, 5.10)
    chain = _override(chain, 501, "put", 5.00, 5.10)
    diag = []
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "non_positive_debit" in diag[0]


def test_max_contracts_zero_means_uncapped(fake_chain_0dte):
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(max_contracts=0, bp_pct=0.50),
        equity=10000.0,
    )
    assert sig is not None
    assert sig.contracts > 2  # uncapped 50% BP far exceeds the old 2-cap


def test_gex_walls_clip_wings(fake_chain_0dte):
    # Body at pin 501, wings at 498/504. Walls inside the wings clip each
    # toward the body: put_wall 499 and call_wall 503.
    chain = {
        **fake_chain_0dte,
        "gex": {"pin_strike": 501.0, "call_wall": 503.0, "put_wall": 499.0},
    }
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    assert sig.lower_strike == 499
    assert sig.upper_strike == 503
    assert sig.wing_width == 2


def test_asymmetric_walls_keep_wings_symmetric(fake_chain_0dte):
    # A near call_wall (502) and a far put_wall (497) must NOT produce a
    # broken-wing 1-2-1 (whose max loss can exceed the debit). Both wings pull
    # in to the nearer wall distance (1) so the fly stays symmetric.
    chain = {
        **fake_chain_0dte,
        "gex": {"pin_strike": 501.0, "call_wall": 502.0, "put_wall": 497.0},
    }
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    assert sig.upper_strike - sig.body_strike == sig.body_strike - sig.lower_strike
    assert sig.upper_strike == 502 and sig.lower_strike == 500


def test_rejects_missing_atm_straddle(fake_chain_0dte):
    chain = {**fake_chain_0dte, "atm_straddle_mid": 0}
    diag = []
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "missing_atm_straddle" in diag[0]


def test_returns_four_legs_single_type(fake_chain_0dte):
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    legs = sig.legs()
    assert len(legs) == 4
    # All one option type.
    assert {l["type"] for l in legs} == {sig.option_type}
    # 1 long lower, 2 short body, 1 long upper.
    longs = [l for l in legs if l["side"] == "long"]
    shorts = [l for l in legs if l["side"] == "short"]
    assert len(longs) == 2 and len(shorts) == 2
    assert {l["strike"] for l in longs} == {sig.lower_strike, sig.upper_strike}
    assert all(l["strike"] == sig.body_strike for l in shorts)
