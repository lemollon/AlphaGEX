from backend.bots.strategies.delta_butterfly import (
    build_delta_butterfly_signal,
    DeltaButterflySignal,
    MONARCH_VIX_Q1,
    MONARCH_VIX_Q2,
)


def _config(**overrides):
    base = {
        "wing_delta_target": 0.25,
        "max_contracts": 1,
        "bp_pct": 0.20,
        "pt_pct": 1.0,
        "sl_pct": 3.0,
    }
    base.update(overrides)
    return base


def test_body_is_nearest_strike_to_spot_not_a_magnet(fake_chain_0dte, market_open_ct):
    # Fixture spot=500, vix=17.0 (inside the frozen mid-tercile band) and
    # carries a pin_strike=501/magnets — MONARCH must ignore both and use
    # spot's nearest listed strike, unlike long_butterfly.
    sig = build_delta_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0, now_ct=market_open_ct,
    )
    assert sig is not None
    assert sig.body_strike == 500


def test_025_delta_wing_matches_known_fixture_numbers(fake_chain_0dte, market_open_ct):
    # Verified directly against the fixture's real bid/ask (09:00 CT ->
    # ~6h-to-close BS-implied delta, no Tradier greeks on this fixture so
    # the BS fallback path is exercised): upper=504, delta~0.228, debit=1.50.
    sig = build_delta_butterfly_signal(
        chain=fake_chain_0dte, config=_config(wing_delta_target=0.25),
        equity=10000.0, now_ct=market_open_ct,
    )
    assert sig is not None
    assert isinstance(sig, DeltaButterflySignal)
    assert sig.upper_strike == 504
    assert sig.lower_strike == 496
    assert 0.20 < sig.realized_delta < 0.25
    assert sig.debit == 1.5
    assert sig.wing_width == 4
    assert sig.max_loss == 150.0
    assert sig.contracts == 1


def test_005_delta_wing_unreachable_on_narrow_fixture_chain(fake_chain_0dte, market_open_ct):
    # The fixture only lists strikes out to spot+6; a genuine 0.05-delta SPY
    # 0DTE wing sits much further OTM. No candidate should fall inside the
    # +/-0.05 tolerance band, and the rejection reason must say so (not a
    # silent None).
    diag = []
    sig = build_delta_butterfly_signal(
        chain=fake_chain_0dte, config=_config(wing_delta_target=0.05),
        equity=10000.0, now_ct=market_open_ct, diag=diag,
    )
    assert sig is None
    assert diag and "no_wing_within_tolerance" in diag[0]


def test_vix_outside_mid_tercile_rejects(fake_chain_0dte, market_open_ct):
    chain = {**fake_chain_0dte, "vix": MONARCH_VIX_Q2 + 1.0}
    diag = []
    sig = build_delta_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, now_ct=market_open_ct, diag=diag,
    )
    assert sig is None
    assert diag and "vix_outside_mid_tercile" in diag[0]

    chain = {**fake_chain_0dte, "vix": MONARCH_VIX_Q1}  # boundary is exclusive
    diag = []
    sig = build_delta_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0, now_ct=market_open_ct, diag=diag,
    )
    assert sig is None
    assert diag and "vix_outside_mid_tercile" in diag[0]


def test_real_tradier_delta_preferred_over_bs_fallback(fake_chain_0dte, market_open_ct):
    # When Tradier's own greeks are present on a strike, MONARCH must use
    # them rather than re-deriving a delta from the mid price.
    opts = []
    for o in fake_chain_0dte["options"]:
        if o["strike"] == 503 and o["type"] == "call":
            o = {**o, "delta": 0.25}
        opts.append(o)
    chain = {**fake_chain_0dte, "options": opts}
    sig = build_delta_butterfly_signal(
        chain=chain, config=_config(wing_delta_target=0.25),
        equity=10000.0, now_ct=market_open_ct,
    )
    assert sig is not None
    assert sig.upper_strike == 503
    assert sig.realized_delta == 0.25


def test_fill_is_real_nbbo_not_mid(fake_chain_0dte, market_open_ct):
    # debit = ask_low + ask_high - 2*bid_mid, i.e. wings bought at ASK and
    # body sold at BID — never a mid-price fill.
    sig = build_delta_butterfly_signal(
        chain=fake_chain_0dte, config=_config(wing_delta_target=0.25),
        equity=10000.0, now_ct=market_open_ct,
    )
    assert sig is not None
    legs = sig.legs()
    lower = next(l for l in legs if l["strike"] == sig.lower_strike)
    upper = next(l for l in legs if l["strike"] == sig.upper_strike)
    body_legs = [l for l in legs if l["strike"] == sig.body_strike]
    assert len(body_legs) == 2  # body sold twice
    assert lower["entry_price"] == sig.lower_ask
    assert upper["entry_price"] == sig.upper_ask
    assert all(l["entry_price"] == sig.body_bid for l in body_legs)
    assert round(sig.lower_ask + sig.upper_ask - 2 * sig.body_bid, 4) == sig.debit


def test_sizing_below_one_rejects_on_tiny_equity(fake_chain_0dte, market_open_ct):
    diag = []
    sig = build_delta_butterfly_signal(
        chain=fake_chain_0dte, config=_config(wing_delta_target=0.25, max_contracts=1),
        equity=10.0, now_ct=market_open_ct, diag=diag,
    )
    assert sig is None
    assert diag and "sizing_below_one" in diag[0]
