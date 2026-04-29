"""GOLIATH Phase 1.5 Metric 1 — wall concentration sanity check.

Original spec:
    For each of last 90 days of GEX snapshots, find the largest positive
    gamma below spot. Compute its ratio vs median gamma of strikes within
    +/- 5% of spot. Report distribution (median, P25, P75, P90).

Validation downgraded to current-state SANITY CHECK (Phase 1.5 v2):
    TV's v2 API does not expose historical strike-level snapshots. Both
    /curves/gex_by_strike and /curves/gamma return current-day data only;
    /series carries scalar metrics only (per the metric_catalog). A true
    90-day per-underlying distribution is not constructible from current
    data sources. All TV endpoints checked (see [GOLIATH-BLOCKED] record
    in conversation transcript on this branch).

    What we CAN do today: one current-day /curves/gex_by_strike fetch per
    underlying, yielding 5 ratios across the universe. This is a
    cross-section, NOT a distribution -- 5 points is far too few to
    justify percentile language. We report it as a SANITY CHECK:
        - Are the universe ratios clustered in a reasonable range
          around the spec default 2.0x?
        - Is any single underlying a wild outlier (>3x deviation from
          universe median)?
    These checks won't catch a subtle calibration miscalibration but
    they will catch "spec default is structurally wrong for this universe."

v0.3 upgrade plan (queued in docs/goliath/goliath-v0.3-todos.md):
    A daily strike-snapshot collector accumulates /curves/gex_by_strike
    data per underlying into a goliath_strike_snapshots table. After
    30+ days of accumulation, re-run wall calibration with real
    per-underlying time-series, producing the proper P25/P75/P90
    distribution the spec originally called for.

Tags emitted:
    CALIB-SANITY-OK   Universe ratios cluster in [median/3, median*3]
                      AND median is in plausible range (0.5, 10.0)
    CALIB-FINDING     Usable data but at least one outlier flagged
    CALIB-BLOCK       No usable data fetched

This metric does NOT emit CALIB-OK or CALIB-ADJUST. With 5 cross-sectional
points, recommending a numerical adjustment to the spec default would be
statistically unjustified. The proper adjustment lives in v0.3 once the
snapshot collector has accumulated time-series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..models import GoliathConfig


@dataclass
class WallConcentrationResult:
    parameter: str = "wall_concentration_threshold"
    spec_default: float = 2.0
    per_underlying: Dict[str, Optional[float]] = field(default_factory=dict)
    universe_count: int = 0
    universe_min: Optional[float] = None
    universe_median: Optional[float] = None
    universe_max: Optional[float] = None
    outliers: List[Tuple[str, float]] = field(default_factory=list)
    tag: str = "CALIB-BLOCK"
    notes: str = ""
    # NOTE: deliberately no recommended_value or P25/P75/P90 fields.
    # See module docstring -- 5 cross-sectional points doesn't justify
    # percentile language or numerical adjustment recommendations.


# Sanity-check thresholds. Tuned for "this would catch a structurally wrong
# spec default" rather than "this is a precision instrument."
_PLAUSIBLE_MEDIAN_RANGE = (0.5, 10.0)
_OUTLIER_MULTIPLIER = 3.0  # flag ratio > median*3 or < median/3


def _compute_concentration(profile: dict, band_pct: float = 0.05) -> Optional[float]:
    """Single-snapshot wall concentration ratio.

    Returns ``max_abs_gamma_below_spot / median_abs_gamma_in_pct_band``,
    or None if the profile lacks usable data (no strikes, no spot, no
    strikes in band, no positive gamma below spot, etc.).
    """
    if not profile or "strikes" not in profile:
        return None

    strikes_data = profile.get("strikes") or []
    spot = float(profile.get("spot_price", 0) or 0)
    if not strikes_data or spot <= 0:
        return None

    in_band = []
    for s in strikes_data:
        strike = float(s.get("strike", 0) or 0)
        if not strike:
            continue
        if abs(strike - spot) / spot <= band_pct:
            gamma = abs(float(s.get("total_gamma", 0) or 0))
            if gamma > 0:
                in_band.append(gamma)
    if not in_band:
        return None
    in_band.sort()
    median_gamma = in_band[len(in_band) // 2]
    if median_gamma <= 0:
        return None

    max_below = 0.0
    for s in strikes_data:
        strike = float(s.get("strike", 0) or 0)
        if not strike or strike >= spot:
            continue
        gamma = abs(float(s.get("total_gamma", 0) or 0))
        if gamma > max_below:
            max_below = gamma

    if max_below <= 0:
        return None

    return max_below / median_gamma


def calibrate(
    gex_history: Dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client=None,
) -> WallConcentrationResult:
    """Wall concentration sanity check across the universe.

    Per-bot CLAUDE.md says module contracts are fixed. Recovery doc v2 (post
    [GOLIATH-DELTA] approval) defines this signature with keyword-only
    ``client`` for dependency injection. All 4 metric modules share this
    pattern for symmetry.

    The ``gex_history`` dict is used solely for its keys (the universe of
    underlyings to evaluate). Strike-level data is fetched fresh per
    underlying via ``client.get_gex_profile()``. Pass a mocked ``client``
    in tests; production code passes ``client=None`` and lets calibrate()
    construct ``TradingVolatilityAPI()`` lazily.
    """
    result = WallConcentrationResult(spec_default=float(config.wall_concentration_threshold))
    underlyings = list(gex_history.keys())
    if not underlyings:
        result.notes = "no underlyings in gex_history"
        return result

    if client is None:
        try:
            from core_classes_and_engines import TradingVolatilityAPI  # type: ignore
            client = TradingVolatilityAPI()
        except ImportError as exc:
            result.notes = f"cannot import TradingVolatilityAPI: {exc!r}"
            return result

    for underlying in underlyings:
        try:
            profile = client.get_gex_profile(underlying, expiration="combined")
            ratio = _compute_concentration(profile)
            result.per_underlying[underlying] = ratio
        except Exception as exc:
            print(f"  [wall_concentration] {underlying} fetch failed: {exc!r}")
            result.per_underlying[underlying] = None

    valid = [(t, v) for t, v in result.per_underlying.items() if v is not None and v > 0]
    if not valid:
        result.tag = "CALIB-BLOCK"
        result.notes = "no underlyings produced a usable concentration ratio"
        return result

    sorted_values = sorted(v for _, v in valid)
    result.universe_count = len(sorted_values)
    result.universe_min = float(sorted_values[0])
    result.universe_max = float(sorted_values[-1])
    result.universe_median = float(sorted_values[len(sorted_values) // 2])

    # Outlier detection: > median*3x or < median/3x
    median = result.universe_median
    upper_bound = median * _OUTLIER_MULTIPLIER
    lower_bound = median / _OUTLIER_MULTIPLIER
    for ticker, ratio in valid:
        if ratio > upper_bound or ratio < lower_bound:
            result.outliers.append((ticker, float(ratio)))

    median_in_plausible = _PLAUSIBLE_MEDIAN_RANGE[0] <= median <= _PLAUSIBLE_MEDIAN_RANGE[1]
    spec = float(config.wall_concentration_threshold)

    if not median_in_plausible:
        result.tag = "CALIB-FINDING"
        result.notes = (
            f"universe median {median:.2f}x is outside plausible sanity range "
            f"{_PLAUSIBLE_MEDIAN_RANGE} -- spec default {spec:.2f}x may be "
            f"structurally wrong for this universe; investigate before v0.3 "
            f"recalibration. Per-underlying: {dict(valid)}"
        )
    elif result.outliers:
        outlier_summary = ", ".join(f"{t}={r:.2f}x" for t, r in result.outliers)
        result.tag = "CALIB-FINDING"
        result.notes = (
            f"universe median {median:.2f}x in plausible range; "
            f"{len(result.outliers)} outlier(s) deviate >{_OUTLIER_MULTIPLIER}x "
            f"from median: {outlier_summary}. Spec default {spec:.2f}x not "
            f"adjusted (5-point cross-section can't justify recommendation; "
            f"see v0.3 wall recalibration TODO)."
        )
    else:
        result.tag = "CALIB-SANITY-OK"
        result.notes = (
            f"universe n={result.universe_count}, median {median:.2f}x, "
            f"range [{result.universe_min:.2f}, {result.universe_max:.2f}], "
            f"no outliers >{_OUTLIER_MULTIPLIER}x from median. Spec default "
            f"{spec:.2f}x is consistent with current-state cross-section. "
            f"True distribution validation deferred to v0.3 (see "
            f"goliath-v0.3-todos.md V03-WALL-RECAL)."
        )

    return result
