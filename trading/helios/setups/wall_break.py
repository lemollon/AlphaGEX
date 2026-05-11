"""Setup 2 — wall_break: negative-gamma momentum.

Fires in negative-gamma regime when spot has cleared a wall by
>= wall_break_em_threshold multiples of sigma_1d. Dealer hedging in
negative gamma amplifies the break — chase momentum with a debit vertical
in the direction of the break.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction

NEGATIVE_REGIMES = {"MODERATE_NEGATIVE", "HIGH_NEGATIVE", "EXTREME_NEGATIVE"}


def evaluate(snapshot: GexSnapshot, *, config: JoshuaConfig) -> Optional[SetupAction]:
    if snapshot.regime not in NEGATIVE_REGIMES:
        return None
    if snapshot.sigma_1d_band_width <= 0:
        return None

    spot = snapshot.spot
    cw = snapshot.call_wall
    pw = snapshot.put_wall
    sigma = snapshot.sigma_1d_band_width
    thr = config.wall_break_em_threshold

    broke_call = cw > 0 and spot > cw and (spot - cw) / sigma > thr
    broke_put = pw > 0 and spot < pw and (pw - spot) / sigma > thr

    if not broke_call and not broke_put:
        return None

    long_strike = float(round(spot))
    if broke_call:
        return SetupAction(
            setup=SetupType.WALL_BREAK,
            direction="call",
            long_strike=long_strike,
            short_strike=long_strike + config.spread_width,
            reason=f"spot {(spot - cw)/sigma:.2f}sigma above call_wall",
        )
    return SetupAction(
        setup=SetupType.WALL_BREAK,
        direction="put",
        long_strike=long_strike,
        short_strike=long_strike - config.spread_width,
        reason=f"spot {(pw - spot)/sigma:.2f}sigma below put_wall",
    )
