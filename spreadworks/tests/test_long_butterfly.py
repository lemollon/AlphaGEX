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


def test_rejects_junk_cheap_debit(fake_chain_0dte):
    # A debit far below the real-fill floor (~0.27x wing; gate at 0.10x) means
    # broken/one-sided quotes, not a bargain — 2026-07-08 the live scanner
    # bought a $0.065 combo on junk quotes. Cheapen the call fly to 0.25 on a
    # $3 wing (frac 0.083 < 0.10) — it becomes the cheaper side and must be
    # rejected, not traded.
    chain = _override(fake_chain_0dte, 498, "call", 2.70, 2.80)  # lower mid 2.75
    # call debit = 2.75 + 0.70 - 2*1.60 = 0.25 ; frac = 0.083
    diag = []
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "debit_too_cheap_junk_quotes" in diag[0]


def test_rejects_debit_above_breakeven(fake_chain_0dte):
    # Real-fill breakeven is ~0.38-0.45x wing. Paying MORE than 0.45x is a
    # -EV entry even on real quotes. Collapse both body mids so each fly
    # costs 1.45 on a $3 wing (frac 0.483) — must reject.
    chain = _override(fake_chain_0dte, 501, "call", 1.20, 1.30)  # body mid 1.25
    chain = _override(chain, 501, "put", 1.20, 1.30)
    # debit = 3.25 + 0.70 - 2*1.25 = 1.45 ; frac = 0.483 > 0.45
    diag = []
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "debit_above_breakeven" in diag[0]


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


def _spx_chain():
    """Synthetic SPX 0DTE chain: $5 strike grid, spot 5000, straddle 40.
    Raw wing = round(1.0 * 40 * 0.85) = 34 -> must snap to 35 (the grid)."""
    opts = []
    for strike in range(4900, 5105, 5):
        for t in ("call", "put"):
            # Flat placeholder quotes; the three legs that matter are
            # overridden below to give an in-band debit.
            opts.append({"strike": strike, "type": t, "bid": 1.0, "ask": 1.2})
    chain = {
        "ticker": "SPX", "spot": 5000.0, "vix": 17.0,
        "atm_straddle_mid": 40.0, "expiration": "2026-05-20",
        "gex": {}, "options": opts,
    }
    # body 5000, wings 4965/5035: debit = 40.0 + 4.0 - 2*18.0 = 8.0
    # -> frac 8/35 = 0.229, inside the 0.10-0.45 band.
    for o in chain["options"]:
        if o["type"] != "call":
            continue
        if o["strike"] == 4965:
            o["bid"], o["ask"] = 39.9, 40.1
        elif o["strike"] == 5000:
            o["bid"], o["ask"] = 17.9, 18.1
        elif o["strike"] == 5035:
            o["bid"], o["ask"] = 3.9, 4.1
    return chain


def test_spx_wing_snaps_to_5_point_grid():
    # Make the put fly expensive so the call side (with the crafted quotes)
    # deterministically wins.
    chain = _spx_chain()
    sig = build_long_butterfly_signal(
        chain=chain, config=_config(bp_pct=0.20, max_contracts=4),
        equity=10000.0,
    )
    assert sig is not None
    # Raw wing 34 doesn't exist on a $5 grid; snapped to 35.
    assert sig.wing_width == 35
    assert sig.lower_strike == 4965 and sig.upper_strike == 5035
    assert sig.debit == pytest.approx(8.0)
    # $10k * 0.20 = $2000 budget // $800 max loss = 2 lots.
    assert sig.contracts == 2


def test_spy_one_point_grid_snap_is_noop(fake_chain_0dte):
    sig = build_long_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.wing_width == 3  # unchanged from round(1.0 * 4.0 * 0.85)
