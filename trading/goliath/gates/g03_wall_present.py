"""Gate G03 -- Underlying has identifiable positive gamma wall below spot.

Master spec section 2:
    "Underlying has identifiable positive gamma wall below spot --
     If no wall, no trade"

Thin delegation to Phase 2 ``wall_finder.find_wall``. Pass when a
qualifying wall exists; fail otherwise. The Wall details are captured
in the context for downstream audit logging.
"""
from __future__ import annotations

from typing import Sequence

from trading.goliath.models import GoliathConfig
from trading.goliath.strike_mapping.wall_finder import GammaStrike, find_wall

from .base import GateOutcome, GateResult


def evaluate(
    underlying_strikes: Sequence[GammaStrike],
    underlying_spot: float,
    config: GoliathConfig,
) -> GateResult:
    """Pass when find_wall returns a qualifying wall, fail otherwise.

    Args:
        underlying_strikes: gamma-by-strike for the underlying
        underlying_spot: current underlying spot price
        config: GoliathConfig (provides wall_concentration_threshold)
    """
    wall = find_wall(underlying_strikes, underlying_spot, config)

    base_context = {
        "underlying_spot": float(underlying_spot),
        "wall_concentration_threshold": config.wall_concentration_threshold,
        "n_strikes": len(underlying_strikes),
    }

    if wall is None:
        return GateResult(
            gate="G03",
            outcome=GateOutcome.FAIL,
            reason=(
                f"No wall meeting {config.wall_concentration_threshold}x median "
                "concentration found below spot"
            ),
            context=base_context,
        )

    return GateResult(
        gate="G03",
        outcome=GateOutcome.PASS,
        reason=(
            f"Wall at {wall.strike:.2f} (gamma {wall.gamma:.2e}, "
            f"concentration {wall.concentration_ratio:.2f}x)"
        ),
        context={
            **base_context,
            "wall_strike": wall.strike,
            "wall_gamma": wall.gamma,
            "wall_concentration_ratio": wall.concentration_ratio,
            "median_local_gamma": wall.median_local_gamma,
        },
    )
