"""LETF mapper -- Step 2 of GOLIATH strike mapping (master spec section 3).

Translates an underlying-side wall price into an LETF-side target
strike using the vol-drag-adjusted predicted-return formula. The
mapping is the central target around which leg_builder selects the
short put / long put / long call strikes.

Math (master spec section 3 + Phase 1.5 metric definitions):

  Underlying relative move:
      r_u = (wall_price - underlying_spot) / underlying_spot

  Vol drag over t years (annualized sigma, leverage L):
      drag = -0.5 * L * (L-1) * sigma^2 * t * drag_coefficient

  Predicted LETF return over the same horizon:
      r_l = L * r_u + drag

  LETF target price:
      target = letf_spot * (1 + r_l)

  Tracking-error half-width (Phase 1.5 metric 2 formula):
      te_band = L * sigma * sqrt(t) * sqrt(2/3) * tracking_error_fudge

  Confidence band on the LETF target:
      [target * (1 - te_band), target * (1 + te_band)]

Caller supplies the annualized realized-vol sigma; this module does not
fetch price history. Decoupling the math from data acquisition keeps
this unit-testable with synthetic inputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from trading.goliath.models import GoliathConfig

# Phase 1.5 metric 2 definition: the constant inside the tracking-error
# formula equals sqrt(2/3) per spec section 3.
_TE_GEOMETRIC = math.sqrt(2.0 / 3.0)


def compute_vol_drag(
    leverage: float,
    sigma_annualized: float,
    t_years: float,
    drag_coefficient: float = 1.0,
) -> float:
    """Theoretical vol drag of a daily-rebalanced LETF over t years.

    Returns negative for L > 1 (drag reduces LETF return below pure leverage).
    drag_coefficient (default 1.0 = theoretical formula) is the Phase 1.5
    calibration multiplier; values > 1 increase drag, < 1 reduce it.
    """
    return -0.5 * leverage * (leverage - 1.0) * (sigma_annualized ** 2) * t_years * drag_coefficient


def compute_tracking_error_band(
    leverage: float,
    sigma_annualized: float,
    t_years: float,
    fudge_factor: float,
) -> float:
    """Tracking-error half-width as a fraction of target.

    Returns a non-negative number representing the +/- band fraction
    around the LETF target. Multiply by target price to get a price band.
    """
    if t_years <= 0 or sigma_annualized <= 0:
        return 0.0
    return leverage * sigma_annualized * math.sqrt(t_years) * _TE_GEOMETRIC * fudge_factor


@dataclass(frozen=True)
class LETFTarget:
    """Output of the underlying-to-LETF strike mapping.

    Attributes:
        target_strike: central target LETF price (LETF spot times 1+predicted_return)
        band_low: lower edge of the tracking-error confidence band
        band_high: upper edge of the tracking-error confidence band
        predicted_letf_return: r_l = L*r_u + drag (over t_years)
        vol_drag: drag component of the predicted return
        te_band: tracking-error half-width as a fraction (band_high - target / target)
    """

    target_strike: float
    band_low: float
    band_high: float
    predicted_letf_return: float
    vol_drag: float
    te_band: float


def map_to_letf(
    underlying_wall_price: float,
    underlying_spot: float,
    letf_spot: float,
    sigma_annualized: float,
    t_years: float,
    config: GoliathConfig,
) -> LETFTarget:
    """Translate an underlying wall to an LETF target strike + band.

    Args:
        underlying_wall_price: wall price found by wall_finder (Step 1)
        underlying_spot: current spot of the underlying
        letf_spot: current spot of the LETF
        sigma_annualized: annualized realized vol of the underlying
        t_years: time horizon in years (e.g. 7/365 for 1-week DTE)
        config: GoliathConfig (provides leverage, drag_coefficient, fudge)

    Returns:
        LETFTarget with central target, confidence band, and components.

    Raises:
        ValueError on non-positive prices or sigma; the caller is expected
        to validate inputs before invoking this function.
    """
    if underlying_spot <= 0 or letf_spot <= 0:
        raise ValueError("Spot prices must be positive")
    if sigma_annualized < 0:
        raise ValueError("sigma_annualized must be non-negative")
    if t_years < 0:
        raise ValueError("t_years must be non-negative")

    r_u = (underlying_wall_price - underlying_spot) / underlying_spot

    drag = compute_vol_drag(
        leverage=config.leverage,
        sigma_annualized=sigma_annualized,
        t_years=t_years,
        drag_coefficient=config.drag_coefficient,
    )
    r_l = config.leverage * r_u + drag

    target = letf_spot * (1.0 + r_l)

    te_band = compute_tracking_error_band(
        leverage=config.leverage,
        sigma_annualized=sigma_annualized,
        t_years=t_years,
        fudge_factor=config.tracking_error_fudge,
    )

    return LETFTarget(
        target_strike=float(target),
        band_low=float(target * (1.0 - te_band)),
        band_high=float(target * (1.0 + te_band)),
        predicted_letf_return=float(r_l),
        vol_drag=float(drag),
        te_band=float(te_band),
    )
