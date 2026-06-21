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


def test_uses_pin_strike_when_no_magnets(fake_chain_0dte):
    # Fixture has pin_strike = 501 and NO magnets list -> body falls back to
    # the predicted pin (NOT spot 500, NOT flip 502).
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 501
    # Wing distance = 1.0 * 4.0 * 0.85 ~= 3.4 -> round to 3 -> wings at 498/504
    assert sig.long_put_strike == 498
    assert sig.long_call_strike == 504


def test_pins_between_two_large_magnets(fake_chain_0dte):
    # Two comparably-large magnets at 497 and 501 -> price pins BETWEEN them,
    # at the gamma-weighted midpoint (499). This must WIN over the single
    # pin_strike (502) and over spot (500), proving the multi-magnet rule.
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
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 499  # midpoint of 497 and 501
    assert sig.long_put_strike == 496
    assert sig.long_call_strike == 502


def test_pins_between_magnets_with_net_gamma_key(fake_chain_0dte):
    # Regression: the live WATCHTOWER engine emits magnets keyed by `net_gamma`
    # (core/watchtower_engine.identify_magnets), NOT `gamma`. The builder must
    # read that key, otherwise every magnet reads as 0 gamma, gets dropped, and
    # the body silently falls back to spot/pin instead of the magnet midpoint.
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
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 499  # midpoint of 497/501 — magnets honored


def test_single_dominant_magnet_centers_on_top_magnet(fake_chain_0dte):
    # One magnet far larger than the rest -> NOT a between-magnets case, so the
    # body centers on the dominant magnet (503), winning over pin_strike (500).
    chain = {
        **fake_chain_0dte,
        "gex": {
            "pin_strike": 500.0,
            "magnets": [
                {"strike": 503.0, "gamma": 1.0e9},
                {"strike": 498.0, "gamma": 1.0e8},  # 10x smaller -> not comparable
            ],
        },
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 503  # dominant magnet, not pin_strike 500


def test_falls_back_to_spot_when_no_pin(fake_chain_0dte):
    # No pin in the GEX block -> body centers on spot (500), neutral fallback.
    chain = {**fake_chain_0dte, "gex": {"flip_point": 502.0}}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 500
    assert sig.long_put_strike == 497
    assert sig.long_call_strike == 503


def test_skips_when_vix_too_high(fake_chain_0dte):
    chain = {**fake_chain_0dte, "vix": 30.0}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_no_credit_floor_allows_thin_credit(fake_chain_0dte):
    # Squeeze all premiums to ~zero so credit ~= 0. There is intentionally NO
    # minimum-credit gate, so the signal must still build (the only credit-side
    # guard is the structural max_loss > 0 check, which still passes here).
    chain = {
        **fake_chain_0dte,
        "options": [
            {**o, "bid": 0.01, "ask": 0.02} for o in fake_chain_0dte["options"]
        ],
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.credit < 0.30  # below the old floor — proves the gate is gone
    assert sig.contracts >= 1


def test_credit_sizing(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    # Body at pin (501): credit = (1.60 + 2.60) - (0.70 + 1.25) = 2.25.
    # We expect a positive credit and contracts in [1, max_contracts].
    assert sig.credit > 0.30
    assert sig.contracts >= 1
    assert sig.contracts <= 2  # bounded by max_contracts


def test_gex_walls_clip_wings(fake_chain_0dte):
    # Body at pin 501, wings at 498/504. Move BOTH walls inside the wings to
    # verify each gets clipped toward the body: put_wall 499 (498<499<501) and
    # call_wall 503 (501<503<504).
    chain = {
        **fake_chain_0dte,
        "gex": {"pin_strike": 501.0, "call_wall": 503.0, "put_wall": 499.0},
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    # Put wing clipped UP to put_wall, call wing clipped DOWN to call_wall.
    assert sig.long_put_strike == 499
    assert sig.long_call_strike == 503


def test_sl_is_pct_of_max_loss_not_max_profit(fake_chain_0dte):
    # The iron fly's stop must be a fraction of MAX LOSS (defined risk). Basing
    # it on max_profit (the rich ATM credit) made it unreachable. max_loss and
    # max_profit differ here, so this distinguishes the two bases.
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(sl_pct=1.0), equity=10000.0
    )
    assert sig is not None
    assert sig.max_loss != pytest.approx(sig.max_profit)
    assert sig.sl_target_pnl == pytest.approx(1.0 * sig.max_loss * sig.contracts)


def test_asymmetric_walls_keep_wings_symmetric(fake_chain_0dte):
    # A near call_wall (502) and a far put_wall (497) must NOT produce a
    # broken-wing fly. Both wings pull in to the nearer wall distance (1) so the
    # fly stays symmetric and the defined-risk math (max_loss = wing - credit)
    # holds. Base wings would be 498/504; the close call wall caps both to ±1.
    chain = {
        **fake_chain_0dte,
        "gex": {"pin_strike": 501.0, "call_wall": 502.0, "put_wall": 497.0},
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    assert sig.long_call_strike - sig.body_strike == sig.body_strike - sig.long_put_strike
    assert sig.long_call_strike == 502 and sig.long_put_strike == 500


def test_rejects_missing_atm_straddle(fake_chain_0dte):
    chain = {**fake_chain_0dte, "atm_straddle_mid": 0}
    diag = []
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "missing_atm_straddle" in diag[0]


def test_max_contracts_zero_means_uncapped(fake_chain_0dte):
    # Regression: max_contracts=0 must mean "no ceiling, size by BP alone",
    # NOT "clamp to zero". The old min(max_contracts, raw) rejected every
    # entry (sizing_below_one) once config flipped to 0, freezing the bot.
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(max_contracts=0, bp_pct=0.50),
        equity=10000.0,
    )
    assert sig is not None
    assert sig.contracts > 2  # uncapped 50% BP far exceeds the old 2-cap


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
