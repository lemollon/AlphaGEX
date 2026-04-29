"""GOLIATH Phase 1.5 Metric 1 — wall concentration threshold.

Spec:
    For each of last 90 days of GEX snapshots, find the largest positive
    gamma below spot. Compute its ratio vs median gamma of strikes within
    ±5% of spot. Report distribution (median, P25, P75, P90).

Acceptance:
    Spec default 2.0×.  If 2.0× falls within universe [P25, P90] → CALIB-OK.
    If outside → CALIB-ADJUST recommending the universe median.

Data limitation [GOLIATH-FINDING] WARN:
    TV's v2 /series provides historical scalar metrics only — it does NOT
    expose strike-level historicals. /curves/gex_by_strike returns the
    current snapshot only. So a true 90-day per-underlying distribution is
    not constructible from current data.

    Workaround: we make one current-day /curves/gex_by_strike call per
    underlying via the public TradingVolatilityAPI.get_gex_profile() and
    report the distribution ACROSS the universe (5 single-day observations)
    rather than within each underlying's history. Honest and useful given
    the constraint; documented in the report.

    v0.3 enhancement: build a daily strike-snapshot collector that
    accumulates gex_by_strike data over time, then re-run for true
    per-underlying distributions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

from ..models import GoliathConfig


@dataclass
class WallConcentrationResult:
    parameter: str = "wall_concentration_threshold"
    spec_default: float = 2.0
    per_underlying: Dict[str, Optional[float]] = field(default_factory=dict)
    universe_p25: Optional[float] = None
    universe_p50: Optional[float] = None
    universe_p75: Optional[float] = None
    universe_p90: Optional[float] = None
    tag: str = "CALIB-BLOCK"
    recommended_value: Optional[float] = None
    notes: str = ""


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

    # Median absolute gamma in ±band_pct of spot
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

    # Largest absolute gamma at strikes BELOW spot (puts dominate below
    # spot; absolute value captures wall magnitude regardless of sign).
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


def _percentile(sorted_values, p: float) -> float:
    """Inclusive percentile (0-1) on a pre-sorted list. n=5 friendly."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = max(0, min(n - 1, int(round(p * (n - 1)))))
    return float(sorted_values[idx])


def calibrate(
    gex_history: Dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client=None,
) -> WallConcentrationResult:
    """Validate the spec wall concentration threshold against current snapshots.

    The ``gex_history`` dict is used solely for its keys (the universe of
    underlyings to evaluate). Strike-level data is fetched fresh per
    underlying via ``client.get_gex_profile()``. Pass a mocked ``client`` in
    tests to bypass the live API call.
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

    valid = sorted(v for v in result.per_underlying.values() if v is not None and v > 0)
    if not valid:
        result.tag = "CALIB-BLOCK"
        result.notes = "no underlyings produced a usable concentration ratio"
        return result

    result.universe_p25 = _percentile(valid, 0.25)
    result.universe_p50 = _percentile(valid, 0.50)
    result.universe_p75 = _percentile(valid, 0.75)
    result.universe_p90 = _percentile(valid, 0.90)

    spec = float(config.wall_concentration_threshold)
    if result.universe_p25 <= spec <= result.universe_p90:
        result.tag = "CALIB-OK"
        result.notes = (
            f"spec {spec:.2f}x within universe [P25={result.universe_p25:.2f}, "
            f"P90={result.universe_p90:.2f}] (n={len(valid)})"
        )
    else:
        result.tag = "CALIB-ADJUST"
        result.recommended_value = float(result.universe_p50)
        result.notes = (
            f"spec {spec:.2f}x outside universe [P25={result.universe_p25:.2f}, "
            f"P90={result.universe_p90:.2f}] -- recommend median "
            f"{result.universe_p50:.2f}x (n={len(valid)})"
        )

    return result
