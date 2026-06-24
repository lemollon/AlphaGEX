from backend.bots.strategies.double_calendar import (
    build_double_calendar_signal,
    DoubleCalendarSignal,
)


def _cfg(**o):
    base = {"max_contracts": 2, "bp_pct": 0.10, "pt_pct": 0.50,
            "sl_pct": 1.0, "starting_capital": 10000}
    base.update(o); return base


def test_picks_strikes_at_implied_move(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # implied_move from 1dte ATM straddle mid = 5.0; spot=500
    # call_strike = round(500 + 5) = 505; put_strike = round(500 - 5) = 495
    assert sig.call_strike == 505
    assert sig.put_strike == 495


def test_legs_use_same_strikes_different_expirations(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    legs = sig.legs()
    assert len(legs) == 4
    short_legs = [l for l in legs if l["side"] == "short"]
    long_legs = [l for l in legs if l["side"] == "long"]
    assert {l["expiration"] for l in short_legs} == {fake_chain_1dte["expiration"]}
    assert {l["expiration"] for l in long_legs} == {fake_chain_14dte["expiration"]}


def test_skips_when_back_iv_not_higher(fake_chain_1dte, fake_chain_14dte):
    # The module default now requires contango (0.3vp). Verify the gate rejects
    # flat/backwardated IV (here back == front, edge 0vp).
    flat = {**fake_chain_14dte, "iv_atm": 0.16}  # equal to front
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=flat,
        config=_cfg(min_vega_edge=0.3), equity=10000.0,
    )
    assert sig is None


def test_skips_when_vix_too_high(fake_chain_1dte, fake_chain_14dte):
    spiked = {**fake_chain_1dte, "vix": 32.0}
    sig = build_double_calendar_signal(
        front_chain=spiked, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is None


def test_debit_is_positive(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig.debit > 0.20
    assert sig.contracts >= 1


def test_max_contracts_zero_means_uncapped(fake_chain_1dte, fake_chain_14dte):
    # Regression: max_contracts=0 must size by BP, not clamp to zero.
    capped = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(max_contracts=1, bp_pct=0.50), equity=10000.0,
    )
    uncapped = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(max_contracts=0, bp_pct=0.50), equity=10000.0,
    )
    assert uncapped is not None
    assert uncapped.contracts >= 1
    assert uncapped.contracts >= capped.contracts
