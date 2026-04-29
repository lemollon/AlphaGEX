"""GOLIATH Phase 1.5 Metric 3 -- volatility drag coefficient.

Spec:
    For each pair (underlying, LETF), compute weekly returns over 90 days.
    Compare actual LETF return vs theoretical leveraged return after drag:
        observed_drag_t   = l_t - leverage * u_t
        theoretical_drag  = -0.5 * leverage * (leverage-1) * sigma^2 * t
    Per-week ratio = observed_drag_t / theoretical_drag.
    Report per-pair mean / median / SE of ratios.

Acceptance criteria (recovery doc, accepted by Leron):
    Universe mean ratio in [0.90, 1.10] -> CALIB-OK, theoretical formula holds.
    Outside [0.90, 1.10]                -> CALIB-ADJUST, recommend k = universe
                                           median (robust, used as multiplier).
    Standard error > 0.15               -> CALIB-BLOCK with recommendation to
                                           extend window to 180d (calibration
                                           too noisy to act on).
    Per-pair > 25% from universe mean   -> outlier flagged in result.

Math:
    sigma = annualized realized vol from N-day window of underlying daily
            log returns (config.realized_vol_window_days, default 30).
            Single sigma per pair (slow-moving over 90d).
    theoretical_drag (constant per pair given single sigma) =
            -0.5 * L * (L-1) * sigma^2 * (1/52)
    observed_drag_t = l_t - L * u_t for each weekly observation
    ratio_t = observed_drag_t / theoretical_drag

    If theory perfectly explains LETF behavior: ratio_t == 1.0 on average.
    If observed drag is 20% worse than theory: mean ratio == 1.2.
    If observed drag is 20% less than theory: mean ratio == 0.8.
    Recommended k = universe median ratio (k applied as multiplier on
    theoretical formula in production drag calculation).

Inputs (per v2 module contract):
    price_history: dict[ticker, DataFrame] keyed by BOTH underlyings AND
        LETFs. 'Close' column required.
    config: GoliathConfig (uses leverage, drag_coefficient,
        realized_vol_window_days).
    client: TradingVolatilityAPI | None  -- accepted for symmetry; unused.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..models import GoliathConfig
from .data_fetch import LETF_PAIRS


@dataclass
class VolDragResult:
    parameter: str = "drag_coefficient"
    spec_default: float = 1.0
    per_pair: Dict[str, dict] = field(default_factory=dict)
    universe_count: int = 0
    universe_mean_ratio: Optional[float] = None
    universe_median_ratio: Optional[float] = None
    universe_se: Optional[float] = None
    outliers: List[Tuple[str, float]] = field(default_factory=list)
    tag: str = "CALIB-BLOCK"
    recommended_value: Optional[float] = None
    notes: str = ""


_OUTLIER_PCT_FROM_MEAN = 0.25  # >25% from universe mean = outlier
_NOISE_BLOCK_SE = 0.15         # SE >0.15 => too noisy to act on


def _compute_pair_drag(
    underlying_close: pd.Series,
    letf_close: pd.Series,
    leverage: float,
    vol_window_days: int,
) -> Optional[dict]:
    """Per-pair observed vs theoretical drag ratio.

    Returns dict with mean_ratio / median_ratio / se_mean / theoretical_drag /
    weeks / sigma, or None if data insufficient (not enough weeks, sigma=0,
    theoretical_drag too small to ratio against, etc).
    """
    common = underlying_close.index.intersection(letf_close.index)
    if len(common) < vol_window_days + 14:
        return None

    u = underlying_close.loc[common].sort_index()
    l = letf_close.loc[common].sort_index()

    u_weekly = u.resample("W-FRI").last().dropna()
    l_weekly = l.resample("W-FRI").last().dropna()
    common_w = u_weekly.index.intersection(l_weekly.index)
    if len(common_w) < 5:
        return None

    u_returns = u_weekly.loc[common_w].pct_change().dropna()
    l_returns = l_weekly.loc[common_w].pct_change().dropna()
    common_r = u_returns.index.intersection(l_returns.index)
    if len(common_r) < 4:
        return None
    u_returns = u_returns.loc[common_r]
    l_returns = l_returns.loc[common_r]

    u_log = np.log(u / u.shift(1)).dropna()
    if len(u_log) < vol_window_days:
        return None
    sigma = float(u_log.tail(vol_window_days).std() * math.sqrt(252))
    if not (0 < sigma < 5.0):
        return None

    t_weekly = 1.0 / 52.0
    theoretical_drag = -0.5 * leverage * (leverage - 1) * sigma**2 * t_weekly
    # theoretical_drag should be negative (volatility decay). If sigma is
    # tiny, theoretical_drag may be too small to form a meaningful ratio.
    if theoretical_drag >= 0 or abs(theoretical_drag) < 1e-7:
        return None

    observed_drag = l_returns - leverage * u_returns
    ratios = observed_drag / theoretical_drag

    if len(ratios) < 4:
        return None

    se_mean = float(ratios.std(ddof=1) / math.sqrt(len(ratios)))

    return {
        "mean_ratio": float(ratios.mean()),
        "median_ratio": float(ratios.median()),
        "se_mean": se_mean,
        "theoretical_drag": float(theoretical_drag),
        "weeks": int(len(ratios)),
        "sigma": sigma,
    }


def calibrate(
    price_history: Dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client=None,
) -> VolDragResult:
    """Validate spec drag coefficient (theoretical formula multiplier) against
    observed weekly LETF/underlying drag residuals.

    The ``client`` kwarg is accepted for symmetry with other metric modules
    per the v2 recovery doc Module Contracts; this metric does not use TV.
    """
    spec = float(config.drag_coefficient)
    result = VolDragResult(spec_default=spec)

    valid: List[Tuple[str, float, float]] = []  # (letf, mean_ratio, se)
    for letf, underlying in LETF_PAIRS.items():
        u_df = price_history.get(underlying, pd.DataFrame())
        l_df = price_history.get(letf, pd.DataFrame())
        if u_df is None or u_df.empty or l_df is None or l_df.empty:
            result.per_pair[letf] = {"error": "missing price data"}
            continue
        if "Close" not in u_df.columns or "Close" not in l_df.columns:
            result.per_pair[letf] = {"error": "Close column missing"}
            continue

        try:
            metrics = _compute_pair_drag(
                u_df["Close"],
                l_df["Close"],
                leverage=float(config.leverage),
                vol_window_days=int(config.realized_vol_window_days),
            )
        except Exception as exc:
            result.per_pair[letf] = {"error": f"{exc!r}"}
            continue

        if metrics is None:
            result.per_pair[letf] = {"error": "insufficient data"}
            continue

        result.per_pair[letf] = metrics
        valid.append((letf, float(metrics["mean_ratio"]), float(metrics["se_mean"])))

    if not valid:
        result.tag = "CALIB-BLOCK"
        result.notes = "no pair produced a usable drag ratio"
        return result

    pair_means = np.array([m for _, m, _ in valid])
    pair_ses = np.array([s for _, _, s in valid])
    result.universe_count = len(valid)
    result.universe_mean_ratio = float(pair_means.mean())
    result.universe_median_ratio = float(np.median(pair_means))
    # Pooled-style SE: RMS of per-pair SEs (rough but defensible for n=5)
    result.universe_se = float(np.sqrt(np.mean(pair_ses**2)))

    # Per-pair outlier detection: >25% from universe mean
    universe_mean = result.universe_mean_ratio
    if universe_mean != 0:
        for letf, mean_r, _ in valid:
            if abs(mean_r - universe_mean) / abs(universe_mean) > _OUTLIER_PCT_FROM_MEAN:
                result.outliers.append((letf, float(mean_r)))

    # Decision: SE check first (block on excess noise)
    if result.universe_se > _NOISE_BLOCK_SE:
        result.tag = "CALIB-BLOCK"
        result.notes = (
            f"universe SE {result.universe_se:.3f} > {_NOISE_BLOCK_SE} -- "
            f"calibration too noisy to act on. Recommend extending window "
            f"to 180d before re-running. Universe mean ratio "
            f"{universe_mean:.3f} (median {result.universe_median_ratio:.3f}), "
            f"n={result.universe_count}."
        )
        return result

    if 0.90 <= universe_mean <= 1.10:
        result.tag = "CALIB-OK"
        result.notes = (
            f"universe mean ratio {universe_mean:.3f} in [0.90, 1.10]; "
            f"theoretical drag formula validated. n={result.universe_count}, "
            f"SE={result.universe_se:.3f}, median={result.universe_median_ratio:.3f}."
        )
    else:
        result.recommended_value = float(result.universe_median_ratio)
        result.tag = "CALIB-ADJUST"
        direction = "weaker than theory" if universe_mean < 0.90 else "stronger than theory"
        result.notes = (
            f"universe mean ratio {universe_mean:.3f} outside [0.90, 1.10] -- "
            f"observed drag is {direction}. Recommend k={result.universe_median_ratio:.3f} "
            f"(median for robustness). Apply as multiplier on theoretical_drag "
            f"in strike-mapping. n={result.universe_count}, SE={result.universe_se:.3f}."
        )

    if result.outliers:
        outlier_summary = ", ".join(f"{t}={r:.3f}" for t, r in result.outliers)
        result.notes += (
            f" Per-pair outliers (>{int(_OUTLIER_PCT_FROM_MEAN * 100)}% from "
            f"universe mean): {outlier_summary}"
        )
        # MSTU note per spec: known structural concern
        if any(t == "MSTU" for t, _ in result.outliers):
            result.notes += (
                " (MSTU outlier expected per spec -- LETF may not behave as "
                "clean leveraged proxy due to known structural issues)"
            )

    return result
