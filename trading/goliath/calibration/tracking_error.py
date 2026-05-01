"""GOLIATH Phase 1.5 Metric 2 -- tracking error fudge factor.

Spec:
    Compute residuals between observed weekly LETF return and predicted
    weekly return (after drag adjustment). Report observed standard
    deviation; compare to spec's
        leverage * sigma * sqrt(t) * sqrt(2/3) * fudge_factor (=0.1)
    formula. Report observed_te_stddev / spec_predicted_te ratio.

Acceptance criteria (recovery doc, accepted by Leron):
    universe median ratio in [0.75, 1.25] -> CALIB-OK, keep spec fudge 0.1
    universe median <  0.75               -> CALIB-ADJUST, recommend 0.1 * ratio
    universe median >  1.25               -> CALIB-ADJUST, recommend 0.1 * ratio
                                            (proportional in both directions)
    Per-pair: ratio > 1.5x universe median -> flag as outlier in result.

Math:
    For each (underlying, LETF) pair over 90d daily prices:
      1. Resample to weekly closes (Friday).
      2. Weekly simple returns u_t and l_t.
      3. Compute annualized realized vol sigma from N-day window of
         daily log returns (config.realized_vol_window_days, default 20
         per Phase 1.5 step 9 calibration; was 30 originally).
      4. Per-week predicted LETF return:
            predicted_l_t = leverage * u_t + drag
            drag         = -0.5 * leverage * (leverage-1) * sigma**2 * (1/52)
      5. Residuals: r_t = l_t - predicted_l_t
      6. observed_te  = stddev(r_t)
      7. predicted_te = leverage * sigma * sqrt(1/52) * sqrt(2/3) * config.tracking_error_fudge
      8. ratio = observed_te / predicted_te

Inputs (per v2 module contract):
    price_history: dict[ticker, DataFrame] keyed by BOTH underlyings AND
        LETFs. Each DataFrame has at least a 'Close' column, indexed by
        date (tz-naive).
    config: GoliathConfig (uses leverage, tracking_error_fudge,
        realized_vol_window_days).
    client: TradingVolatilityAPI | None  -- accepted for symmetry across
        all 4 metric module contracts; this metric does not use TV.
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
class TrackingErrorResult:
    parameter: str = "tracking_error_fudge"
    spec_default: float = 0.1
    per_pair: Dict[str, dict] = field(default_factory=dict)
    universe_count: int = 0
    universe_median_ratio: Optional[float] = None
    outliers: List[Tuple[str, float]] = field(default_factory=list)
    tag: str = "CALIB-BLOCK"
    recommended_value: Optional[float] = None
    notes: str = ""


_OUTLIER_MULTIPLIER = 1.5  # >1.5x universe median ratio = outlier


def _compute_pair_te(
    underlying_close: pd.Series,
    letf_close: pd.Series,
    leverage: float,
    vol_window_days: int,
) -> Optional[dict]:
    """Per-pair observed vs predicted tracking error.

    Returns dict with observed_te / predicted_te / ratio / weeks / sigma,
    or None if data is insufficient (not enough weeks, sigma=0, etc).
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

    # Annualized realized vol from daily log returns of underlying.
    u_log = np.log(u / u.shift(1)).dropna()
    if len(u_log) < vol_window_days:
        return None
    sigma = float(u_log.tail(vol_window_days).std() * math.sqrt(252))
    if not (0 < sigma < 5.0):  # 0 < sigma < 500% sanity bound
        return None

    t_weekly = 1.0 / 52.0
    drag = -0.5 * leverage * (leverage - 1) * sigma**2 * t_weekly
    predicted_l = leverage * u_returns + drag
    residuals = l_returns - predicted_l

    observed_te = float(residuals.std())
    predicted_te = leverage * sigma * math.sqrt(t_weekly) * math.sqrt(2.0 / 3.0) * 0.1
    if predicted_te <= 0:
        return None

    return {
        "observed_te": observed_te,
        "predicted_te": predicted_te,
        "ratio": observed_te / predicted_te,
        "weeks": int(len(common_r)),
        "sigma": sigma,
    }


def calibrate(
    price_history: Dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client=None,
) -> TrackingErrorResult:
    """Validate spec tracking-error fudge factor against observed weekly residuals.

    The ``client`` kwarg is accepted for symmetry with other metric modules
    per the v2 recovery doc Module Contracts; this metric does not use TV.
    """
    spec = float(config.tracking_error_fudge)
    result = TrackingErrorResult(spec_default=spec)

    valid: List[Tuple[str, float]] = []
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
            metrics = _compute_pair_te(
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
        valid.append((letf, float(metrics["ratio"])))

    if not valid:
        result.tag = "CALIB-BLOCK"
        result.notes = "no pair produced a usable tracking error ratio"
        return result

    sorted_ratios = sorted(r for _, r in valid)
    n = len(sorted_ratios)
    median = float(sorted_ratios[n // 2])
    result.universe_count = n
    result.universe_median_ratio = median

    for letf, ratio in valid:
        if ratio > _OUTLIER_MULTIPLIER * median:
            result.outliers.append((letf, ratio))

    if 0.75 <= median <= 1.25:
        result.tag = "CALIB-OK"
        result.notes = (
            f"universe median ratio {median:.3f} in [0.75, 1.25]; spec fudge "
            f"{spec:.3f} validated against {n} pair(s)."
        )
    else:
        recommended = spec * median
        result.recommended_value = float(recommended)
        result.tag = "CALIB-ADJUST"
        direction = "too conservative" if median < 0.75 else "too aggressive"
        result.notes = (
            f"universe median ratio {median:.3f} outside [0.75, 1.25] -- spec "
            f"fudge {spec:.3f} is {direction}. Recommend {recommended:.4f} "
            f"(spec * median, proportional). n={n} pair(s)."
        )

    if result.outliers:
        outlier_summary = ", ".join(f"{t}={r:.3f}" for t, r in result.outliers)
        result.notes += f" Outliers (>{_OUTLIER_MULTIPLIER}x universe median): {outlier_summary}"

    return result
