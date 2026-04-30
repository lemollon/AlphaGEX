"""Wall finder — Step 1 of GOLIATH strike mapping (master spec section 3).

Identifies the qualifying positive-gamma wall below spot on the
underlying. A wall is defined per spec as a strike whose gamma is
>= config.wall_concentration_threshold (default 2.0) times the median
gamma of strikes within +/- 5% of spot.

The wall's strike price is the input to letf_mapper (Step 2). If no
qualifying wall exists, find_wall returns None and the caller fails
Gate G03 (master spec section 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import List, Optional, Sequence

from trading.goliath.models import GoliathConfig

# Per spec section 3: median is computed across strikes within +/- 5% of spot.
LOCAL_BAND_FRACTION = 0.05


@dataclass(frozen=True)
class GammaStrike:
    """One strike's gamma data on the underlying option chain."""

    strike: float
    gamma: float


@dataclass(frozen=True)
class Wall:
    """A qualifying positive-gamma wall below spot.

    Attributes:
        strike: strike price of the wall on the underlying
        gamma: gamma at that strike
        median_local_gamma: median gamma across strikes within +/- 5% of spot
        concentration_ratio: gamma / median_local_gamma (>= threshold)
    """

    strike: float
    gamma: float
    median_local_gamma: float
    concentration_ratio: float


def find_wall(
    strikes: Sequence[GammaStrike],
    spot: float,
    config: GoliathConfig,
) -> Optional[Wall]:
    """Find the largest qualifying positive-gamma wall below spot.

    Algorithm (master spec section 3 step 1):
      1. Filter strikes to the +/- 5% band around spot
      2. Compute median gamma of those local strikes
      3. Threshold = config.wall_concentration_threshold * median_local
      4. Among strikes below spot with positive gamma, keep only those
         with gamma >= threshold
      5. Return the candidate with the largest gamma; None if none

    Returns None and triggers Gate G03 failure when:
      - strikes is empty
      - spot is non-positive
      - no strikes lie in the +/- 5% local band
      - median local gamma is non-positive (no meaningful baseline)
      - no below-spot strike meets the threshold

    Args:
        strikes: option-chain gamma data for the underlying
        spot: current spot price of the underlying
        config: GoliathConfig with wall_concentration_threshold

    Returns:
        Wall instance for the largest qualifying wall, or None.
    """
    if not strikes or spot <= 0:
        return None

    band_lo = spot * (1.0 - LOCAL_BAND_FRACTION)
    band_hi = spot * (1.0 + LOCAL_BAND_FRACTION)
    local = [s.gamma for s in strikes if band_lo <= s.strike <= band_hi]
    if not local:
        return None

    median_local = median(local)
    if median_local <= 0:
        # Spec "wall = N x median" loses meaning when median is non-positive.
        # Treat as no wall and fail Gate G03 upstream.
        return None

    threshold = config.wall_concentration_threshold * median_local

    candidates: List[GammaStrike] = [
        s
        for s in strikes
        if s.strike < spot and s.gamma > 0 and s.gamma >= threshold
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda s: s.gamma)
    return Wall(
        strike=float(best.strike),
        gamma=float(best.gamma),
        median_local_gamma=float(median_local),
        concentration_ratio=float(best.gamma) / float(median_local),
    )
