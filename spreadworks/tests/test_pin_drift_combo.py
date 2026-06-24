"""Unit tests for SURGE — the pin+drift combo (long butterfly + two
0DTE/1DTE calendars). Front chain = the shared 0DTE fixture; back chain is
derived from it (same strikes, every price bumped +$0.50 for time value) so the
calendars find their strikes and carry a positive debit."""
import pytest

from backend.bots.strategies.pin_drift_combo import (
    build_pin_drift_combo_signal,
    PinDriftComboSignal,
)


def _config(**overrides):
    base = {
        "max_contracts": 2, "bp_pct": 0.10, "sd_mult": 1.0,
        "pt_pct": 0.30, "sl_pct": 0.50, "drift_offset": 2,
        "use_gex_walls": False,
    }
    base.update(overrides)
    return base


def _back_from_front(front, bump=0.50):
    """1DTE back chain: same strikes, prices +bump (time value), new expiration."""
    return {
        **front,
        "expiration": "2026-05-21",
        "options": [{**o, "bid": o["bid"] + bump, "ask": o["ask"] + bump}
                    for o in front["options"]],
    }


def test_builds_full_combo(fake_chain_0dte):
    front = fake_chain_0dte
    back = _back_from_front(front)
    sig = build_pin_drift_combo_signal(
        front_chain=front, back_chain=back, config=_config(), equity=10000.0
    )
    assert isinstance(sig, PinDriftComboSignal)
    # Body = pin 501; wings = round(1.0*4.0*0.85)=3 -> 498/504; drift 2 -> 503/499.
    assert sig.body_strike == 501
    assert sig.lower_strike == 498 and sig.upper_strike == 504
    assert sig.call_cal_strike == 503 and sig.put_cal_strike == 499
    # Cheaper fly side is the call fly at 0.75 (symmetric fixture, tie -> call).
    assert sig.option_type == "call"
    assert sig.fly_debit == pytest.approx(0.75)
    # Each calendar debit = back_mid - front_mid = the +0.50 bump.
    assert sig.call_cal_debit == pytest.approx(0.50)
    assert sig.put_cal_debit == pytest.approx(0.50)
    assert sig.debit == pytest.approx(0.75 + 0.50 + 0.50)
    # max_profit references the butterfly pin payoff: (wing - fly_debit)*100.
    assert sig.max_profit == pytest.approx(225.0)
    assert sig.max_loss == pytest.approx(175.0)   # total debit * 100


def test_emits_eight_legs_across_two_expirations(fake_chain_0dte):
    front = fake_chain_0dte
    back = _back_from_front(front)
    sig = build_pin_drift_combo_signal(
        front_chain=front, back_chain=back, config=_config(), equity=10000.0
    )
    legs = sig.legs()
    assert len(legs) == 8
    front_exp, back_exp = front["expiration"], back["expiration"]
    # Butterfly: 4 legs, single type, all on the FRONT expiration.
    fly = [l for l in legs if l["strike"] in (498, 501, 504)]
    assert len(fly) == 4
    assert all(l["expiration"] == front_exp for l in fly)
    assert {l["type"] for l in fly} == {"call"}
    # Body sold twice.
    assert sum(1 for l in fly if l["strike"] == 501 and l["side"] == "short") == 2
    # Call calendar @503: short front call + long back call.
    cc = [l for l in legs if l["strike"] == 503]
    assert {(l["side"], l["expiration"]) for l in cc} == {
        ("short", front_exp), ("long", back_exp)}
    assert {l["type"] for l in cc} == {"call"}
    # Put calendar @499: short front put + long back put.
    pc = [l for l in legs if l["strike"] == 499]
    assert {(l["side"], l["expiration"]) for l in pc} == {
        ("short", front_exp), ("long", back_exp)}
    assert {l["type"] for l in pc} == {"put"}


def test_pt_and_sl_targets(fake_chain_0dte):
    sig = build_pin_drift_combo_signal(
        front_chain=fake_chain_0dte, back_chain=_back_from_front(fake_chain_0dte),
        config=_config(), equity=10000.0,
    )
    # budget = 10000*0.10 = 1000; 1000 // 175 = 5, capped to 2.
    assert sig.contracts == 2
    assert sig.pt_target_pnl == pytest.approx(0.30 * 225.0 * 2)
    assert sig.sl_target_pnl == pytest.approx(0.50 * 175.0 * 2)


def test_skips_when_vix_too_high(fake_chain_0dte):
    front = {**fake_chain_0dte, "vix": 30.0}
    sig = build_pin_drift_combo_signal(
        front_chain=front, back_chain=_back_from_front(front),
        config=_config(), equity=10000.0,
    )
    assert sig is None


def test_rejects_when_calendar_strike_missing_in_back(fake_chain_0dte):
    front = fake_chain_0dte
    back = _back_from_front(front)
    # Drop the 503 call from the back chain -> the call calendar can't be built.
    back = {**back, "options": [o for o in back["options"]
                                if not (o["strike"] == 503 and o["type"] == "call")]}
    diag = []
    sig = build_pin_drift_combo_signal(
        front_chain=front, back_chain=back, config=_config(), equity=10000.0, diag=diag
    )
    assert sig is None
    assert diag and "cal_strike_missing" in diag[0]


def test_drift_offset_moves_calendar_strikes(fake_chain_0dte):
    front = fake_chain_0dte
    back = _back_from_front(front)
    sig = build_pin_drift_combo_signal(
        front_chain=front, back_chain=back, config=_config(drift_offset=4),
        equity=10000.0,
    )
    # body 501 +/- 4 -> calendars at 505 / 497.
    assert sig.call_cal_strike == 505 and sig.put_cal_strike == 497
