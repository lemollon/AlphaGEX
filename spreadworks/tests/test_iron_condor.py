"""Tests for FLOW (Iron Condor 1DTE) signal builder."""
from __future__ import annotations

import pytest

from backend.bots.strategies.iron_condor import (
    IronCondorSignal,
    build_iron_condor_signal,
)


def _chain(
    *,
    spot: float = 500.0,
    vix: float = 17.0,
    atm_straddle_mid: float = 5.0,
    flip_point: float | None = None,
    expiration: str = "2026-05-20",
) -> dict:
    """Build an IC-friendly SPY 1DTE chain with strikes wide enough for $5 wings."""
    strikes = list(range(int(spot) - 12, int(spot) + 13))  # spot ± 12
    options = []
    for s in strikes:
        # Cheap symmetric premiums — far OTM thinner, ATM thicker. Intrinsic
        # for a put is max(0, K - spot); for a call max(0, spot - K).
        d = abs(s - spot)
        intrinsic_put = max(0, s - spot)
        intrinsic_call = max(0, spot - s)
        extrinsic = max(0.2, 3.0 - 0.25 * d)
        put_mid = intrinsic_put + extrinsic
        call_mid = intrinsic_call + extrinsic
        options.append({"strike": s, "type": "put", "bid": put_mid - 0.05, "ask": put_mid + 0.05})
        options.append({"strike": s, "type": "call", "bid": call_mid - 0.05, "ask": call_mid + 0.05})
    chain = {
        "spot": spot,
        "vix": vix,
        "atm_straddle_mid": atm_straddle_mid,
        "expiration": expiration,
        "ticker": "SPY",
        "options": options,
        "gex": {"flip_point": flip_point} if flip_point is not None else {},
    }
    return chain


def _config(**overrides) -> dict:
    base = {
        "starting_capital": 10000,
        "max_contracts": 0,  # 0 = unlimited (size by BP)
        "bp_pct": 0.50,
        "sd_mult": 1.2,
        "spread_width": 5,
        "pt_pct": 0.30,
        "sl_pct": 0.50,
        "use_gex_walls": False,
    }
    base.update(overrides)
    return base


def test_builds_symmetric_iron_condor():
    sig = build_iron_condor_signal(chain=_chain(), config=_config(), equity=10000.0)
    assert sig is not None
    # sd_distance = 1.2 * 5.0 = 6.0; shorts at 494/506
    assert sig.short_put_strike == 494
    assert sig.short_call_strike == 506
    # Wings $5 outside the shorts
    assert sig.long_put_strike == 489
    assert sig.long_call_strike == 511
    # Credit must clear MIN_CREDIT
    assert sig.credit >= 0.25
    # Sizing should produce at least 1 contract on $10k equity
    assert sig.contracts >= 1


def test_legs_have_correct_shape():
    sig = build_iron_condor_signal(chain=_chain(), config=_config(), equity=10000.0)
    legs = sig.legs()
    assert len(legs) == 4
    sides = {(l["side"], l["type"]) for l in legs}
    assert sides == {("short", "put"), ("short", "call"),
                     ("long", "put"), ("long", "call")}
    # All legs share the same expiration (IC is single-expiry)
    assert {l["expiration"] for l in legs} == {"2026-05-20"}


def test_skipped_when_vix_too_high():
    sig = build_iron_condor_signal(
        chain=_chain(vix=33.0), config=_config(), equity=10000.0
    )
    assert sig is None


def test_skipped_when_credit_below_min():
    # Crush all bid/ask to ~zero so credit < $0.25
    chain = _chain()
    chain["options"] = [{**o, "bid": 0.01, "ask": 0.02} for o in chain["options"]]
    sig = build_iron_condor_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is None


def test_skipped_when_too_close_to_flip():
    sig = build_iron_condor_signal(
        chain=_chain(flip_point=500.4),
        config=_config(),
        equity=10000.0,
    )
    assert sig is None


def test_pt_sl_targets_match_config():
    """SPARK-style: PT=30% of max profit, SL=50% of max profit (1.5x cost-to-close)."""
    sig = build_iron_condor_signal(chain=_chain(), config=_config(), equity=10000.0)
    expected_max_profit = sig.credit * 100.0 * sig.contracts
    assert sig.pt_target_pnl == pytest.approx(0.30 * expected_max_profit)
    assert sig.sl_target_pnl == pytest.approx(0.50 * expected_max_profit)


def test_max_contracts_zero_means_unlimited():
    """max_contracts=0 (SPARK default) should size purely by BP, not return 0."""
    sig = build_iron_condor_signal(
        chain=_chain(), config=_config(max_contracts=0), equity=10000.0
    )
    assert sig is not None
    assert sig.contracts >= 1


def test_max_contracts_ceiling_clamps():
    """When max_contracts > 0, it should cap the BP-derived contracts."""
    sig = build_iron_condor_signal(
        chain=_chain(), config=_config(max_contracts=1, bp_pct=0.95), equity=100000.0
    )
    assert sig is not None
    assert sig.contracts == 1


def test_missing_atm_straddle_rejected():
    chain = _chain(atm_straddle_mid=0)
    sig = build_iron_condor_signal(chain=chain, config=_config(), equity=10000.0)
    assert sig is None
