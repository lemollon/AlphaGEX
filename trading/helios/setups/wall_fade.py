"""Setup 1 — wall_fade: positive-gamma mean-reversion.

Fires in positive-gamma regime when spot is within `wall_fade_em_threshold`
multiples of the 1-day expected-move band from either wall. Trades a debit
vertical that fades back toward the flip point.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction

POSITIVE_REGIMES = {"MODERATE_POSITIVE", "HIGH_POSITIVE", "EXTREME_POSITIVE"}


def evaluate(snapshot: GexSnapshot, *, config: JoshuaConfig) -> Optional[SetupAction]:
    if snapshot.regime not in POSITIVE_REGIMES:
        return None
    if snapshot.sigma_1d_band_width <= 0:
        return None

    spot = snapshot.spot
    cw = snapshot.call_wall
    pw = snapshot.put_wall
    sigma = snapshot.sigma_1d_band_width
    thr = config.wall_fade_em_threshold

    near_call = cw > 0 and spot < cw and (cw - spot) / sigma < thr
    near_put = pw > 0 and spot > pw and (spot - pw) / sigma < thr

    if not near_call and not near_put:
        return None

    if near_call and near_put:
        d_call = cw - spot
        d_put = spot - pw
        if d_call <= d_put:
            near_put = False
        else:
            near_call = False

    long_strike = float(round(spot))
    if near_call:
        short_strike = long_strike - config.spread_width
        return SetupAction(
            setup=SetupType.WALL_FADE,
            direction="put",
            long_strike=long_strike,
            short_strike=short_strike,
            reason=f"call_wall within {(cw - spot)/sigma:.2f}sigma overhead",
        )
    short_strike = long_strike + config.spread_width
    return SetupAction(
        setup=SetupType.WALL_FADE,
        direction="call",
        long_strike=long_strike,
        short_strike=short_strike,
        reason=f"put_wall within {(spot - pw)/sigma:.2f}sigma below",
    )
