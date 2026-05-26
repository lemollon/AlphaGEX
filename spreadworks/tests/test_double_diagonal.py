from backend.bots.strategies.double_diagonal import (
    build_double_diagonal_signal,
)


def _cfg(**o):
    base = {"max_contracts": 2, "bp_pct": 0.10, "pt_pct": 0.50,
            "sl_pct": 1.0, "starting_capital": 10000, "delta_skew": 0}
    base.update(o); return base


def test_max_contracts_zero_means_uncapped(fake_chain_1dte, fake_chain_14dte):
    # Regression: max_contracts=0 must size by BP, not clamp to zero.
    capped = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(max_contracts=1, bp_pct=0.50), equity=10000.0,
    )
    uncapped = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(max_contracts=0, bp_pct=0.50), equity=10000.0,
    )
    assert uncapped is not None
    assert uncapped.contracts >= 1
    assert uncapped.contracts >= capped.contracts


def test_back_strikes_shifted_one_otm(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # front call=505, back call should be 506
    assert sig.short_call_strike == 505
    assert sig.long_call_strike == 506
    # front put=495, back put should be 494
    assert sig.short_put_strike == 495
    assert sig.long_put_strike == 494


def test_delta_skew_propagates_to_signal(fake_chain_1dte, fake_chain_14dte):
    # Strategy now snaps targets to the nearest available strike instead
    # of returning None, so verify delta_skew is wired through by reading
    # it off the signal directly.
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(delta_skew=1), equity=10000.0,
    )
    assert sig is not None
    assert sig.delta_skew == 1


def test_skips_when_back_iv_not_higher(fake_chain_1dte, fake_chain_14dte):
    # Module default is now permissive (-10vp); test the strict-contango
    # path explicitly by overriding min_vega_edge in config.
    flat = {**fake_chain_14dte, "iv_atm": 0.16}
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=flat,
        config=_cfg(min_vega_edge=0.3), equity=10000.0,
    )
    assert sig is None
