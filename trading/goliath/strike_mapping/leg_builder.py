"""Leg builder -- assembles the 3-leg LETF structure.

Per master spec section 1.5, every GOLIATH trade is exactly:
    Leg 1: SELL short put on LETF, ~25-30 delta, below central target
    Leg 2: BUY  long put  on LETF, 1 strike below short put
    Leg 3: BUY  long call on LETF, 15-25% OTM (above central target)

This module takes the LETFTarget from letf_mapper (Step 2) plus the
available LETF strike grid and returns a ThreeLegStructure or None.

Selection rules:
    short_put  = highest available strike <= target_strike AND >= band_low
                 (must lie within the lower half of the tracking-error band)
    long_put   = the next-lowest strike on the chain below short_put
    long_call  = the strike closest to 20% OTM (midpoint of 15-25% range)
                 from letf_spot, bounded to that range

Returns None when:
    - no available strike falls in [band_low, target_strike]
    - short_put has no strike below it on the chain (edge case)
    - no strike falls in the 15-25% OTM band for the long call
    - long_call would not be strictly above target_strike (sanity)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from trading.goliath.models import GoliathConfig
from trading.goliath.strike_mapping.letf_mapper import LETFTarget

# Spec section 1.5 constants. Configurable in v0.3 if calibration suggests.
LONG_CALL_OTM_LOW = 0.15
LONG_CALL_OTM_HIGH = 0.25
LONG_CALL_OTM_TARGET = 0.20  # midpoint of the OTM range


@dataclass(frozen=True)
class ThreeLegStructure:
    """The 3-leg LETF structure produced by build_legs.

    Attributes:
        short_put_strike: short put strike (LEG 1, sold)
        long_put_strike: long put strike (LEG 2, bought, below short put)
        long_call_strike: long call strike (LEG 3, bought, OTM)
        put_spread_width: short_put_strike - long_put_strike (always > 0)
    """

    short_put_strike: float
    long_put_strike: float
    long_call_strike: float
    put_spread_width: float


def build_legs(
    letf_target: LETFTarget,
    available_strikes: Sequence[float],
    letf_spot: float,
    config: GoliathConfig,
) -> Optional[ThreeLegStructure]:
    """Build a ThreeLegStructure from an LETFTarget and available strikes.

    Args:
        letf_target: output of map_to_letf (Step 2)
        available_strikes: LETF option-chain strike grid (any iterable)
        letf_spot: current LETF spot price (for OTM call placement)
        config: GoliathConfig (currently unused; reserved for v0.3 hooks)

    Returns:
        ThreeLegStructure on success, None if any leg cannot be selected.
    """
    if not available_strikes or letf_spot <= 0:
        return None

    sorted_strikes = sorted({float(s) for s in available_strikes})

    short_put = _select_short_put(sorted_strikes, letf_target)
    if short_put is None:
        return None

    long_put = _select_long_put(sorted_strikes, short_put)
    if long_put is None:
        # Edge case (spec section 3.1 test 12): short put has no strike below it.
        return None

    long_call = _select_long_call(sorted_strikes, letf_spot, letf_target.target_strike)
    if long_call is None:
        return None

    return ThreeLegStructure(
        short_put_strike=short_put,
        long_put_strike=long_put,
        long_call_strike=long_call,
        put_spread_width=short_put - long_put,
    )


def _select_short_put(
    sorted_strikes: list[float],
    letf_target: LETFTarget,
) -> Optional[float]:
    """Highest strike at or below target_strike AND >= band_low.

    Spec section 3.1 test 9: respects "below central target" rule.
    """
    candidates = [
        s
        for s in sorted_strikes
        if s <= letf_target.target_strike and s >= letf_target.band_low
    ]
    return max(candidates) if candidates else None


def _select_long_put(
    sorted_strikes: list[float],
    short_put: float,
) -> Optional[float]:
    """The next strike below short_put on the chain.

    Spec section 3.1 test 11: long put is correctly 1 strike below short put.
    Test 12 edge case: short put is lowest -> returns None.
    """
    idx = sorted_strikes.index(short_put)
    if idx == 0:
        return None
    return sorted_strikes[idx - 1]


def _select_long_call(
    sorted_strikes: list[float],
    letf_spot: float,
    target_strike: float,
) -> Optional[float]:
    """Strike closest to 20% OTM, bounded to [15%, 25%] OTM range.

    Spec section 3.1 test 10: respects "above central target" rule.
    """
    otm_low = letf_spot * (1.0 + LONG_CALL_OTM_LOW)
    otm_high = letf_spot * (1.0 + LONG_CALL_OTM_HIGH)
    candidates = [s for s in sorted_strikes if otm_low <= s <= otm_high]
    if not candidates:
        return None

    otm_target = letf_spot * (1.0 + LONG_CALL_OTM_TARGET)
    chosen = min(candidates, key=lambda s: abs(s - otm_target))

    # Sanity: the long call must be strictly above the central target.
    # In practice this always holds (target is below LETF spot from the wall
    # mapping, call is 15%+ above LETF spot), but enforce for clarity.
    if chosen <= target_strike:
        return None
    return chosen
