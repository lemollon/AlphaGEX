"""GOLIATH Phase 1.5 Metric 4 -- realized volatility window sensitivity.

Spec:
    Compute 20-, 30-, 60-day realized vol on each underlying. Report which
    window minimizes drag-prediction residuals.

Acceptance criteria (recovery doc, accepted by Leron):
    If 30d window produces lowest residual SD across MAJORITY of underlyings
        (>= 3 of 5)             -> CALIB-OK, keep spec default of 30d
    Different window wins majority -> CALIB-ADJUST, recommend that window
    No clear majority           -> CALIB-FINDING, keep 30d default (do not
                                   change on ambiguous evidence)
    Per-underlying:
        Any single underlying with residual_sd at non-30d window > 30%
        lower than 30d -> flag as override candidate (per-underlying
        override rather than universe-wide change).

Math:
    For each (underlying, LETF) pair:
      For each candidate window N in {20, 30, 60}:
        sigma_N = annualized realized vol from N-day daily log returns
        predicted_drag_N = -0.5 * L * (L-1) * sigma_N^2 * (1/52)
        residuals_t = observed_drag_t - predicted_drag_N
                       where observed_drag_t = l_t - L * u_t (weekly)
        residual_sd_N = stddev(residuals_t)
      Best window for this pair = argmin(residual_sd over windows)
    Universe winner = window with most pair-level wins; majority threshold
    = floor(n/2) + 1 (so 3 of 5 = majority, 2 of 5 = no majority).

Inputs (per v2 module contract):
    price_history: dict[ticker, DataFrame] keyed by BOTH underlyings AND
        LETFs. 'Close' column required.
    config: GoliathConfig (uses leverage, realized_vol_window_days).
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


_CANDIDATE_WINDOWS = [20, 30, 60]
_OVERRIDE_IMPROVEMENT_THRESHOLD = 0.30  # >30% lower SD vs 30d -> per-underlying override candidate


@dataclass
class VolWindowResult:
    parameter: str = "realized_vol_window_days"
    spec_default: int = 30
    per_pair: Dict[str, dict] = field(default_factory=dict)
    universe_count: int = 0
    universe_winners: Dict[int, int] = field(default_factory=dict)  # window_days -> pair count
    universe_winner: Optional[int] = None  # majority winner; None if split
    per_underlying_overrides: List[Tuple[str, int, float]] = field(default_factory=list)
    # ^ (letf_ticker, better_window_days, fractional_improvement_vs_30d)
    tag: str = "CALIB-BLOCK"
    recommended_value: Optional[int] = None
    notes: str = ""


def _compute_pair_window_stats(
    underlying_close: pd.Series,
    letf_close: pd.Series,
    leverage: float,
    windows: List[int],
) -> Optional[dict]:
    """Per-pair residual SD for each candidate window.

    Returns dict with:
        window_stats: list of {window_days, sigma, residual_sd}
        winner: int        (window with smallest residual_sd)
        winner_residual_sd: float
    Or None if data insufficient for any window.
    """
    if not windows:
        return None
    common = underlying_close.index.intersection(letf_close.index)
    max_window = max(windows)
    if len(common) < max_window + 14:
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

    observed_drag = l_returns - leverage * u_returns
    u_log = np.log(u / u.shift(1)).dropna()

    t_weekly = 1.0 / 52.0
    stats: List[dict] = []
    for window_days in windows:
        if len(u_log) < window_days:
            continue
        sigma = float(u_log.tail(window_days).std() * math.sqrt(252))
        if not (0 < sigma < 5.0):
            continue
        predicted_drag = -0.5 * leverage * (leverage - 1) * sigma**2 * t_weekly
        residuals = observed_drag - predicted_drag
        residual_sd = float(residuals.std())
        stats.append({
            "window_days": int(window_days),
            "sigma": sigma,
            "residual_sd": residual_sd,
        })

    if not stats:
        return None

    winner = min(stats, key=lambda s: s["residual_sd"])
    return {
        "window_stats": stats,
        "winner": int(winner["window_days"]),
        "winner_residual_sd": float(winner["residual_sd"]),
    }


def calibrate(
    price_history: Dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client=None,
) -> VolWindowResult:
    """Pick the realized-vol window that minimizes drag-prediction residual SD.

    The ``client`` kwarg is accepted for symmetry with other metric modules
    per the v2 recovery doc Module Contracts; this metric does not use TV.
    """
    spec = int(config.realized_vol_window_days)
    result = VolWindowResult(spec_default=spec)

    valid: List[Tuple[str, dict]] = []
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
            metrics = _compute_pair_window_stats(
                u_df["Close"], l_df["Close"],
                leverage=float(config.leverage),
                windows=_CANDIDATE_WINDOWS,
            )
        except Exception as exc:
            result.per_pair[letf] = {"error": f"{exc!r}"}
            continue

        if metrics is None:
            result.per_pair[letf] = {"error": "insufficient data"}
            continue

        result.per_pair[letf] = metrics
        valid.append((letf, metrics))

    if not valid:
        result.tag = "CALIB-BLOCK"
        result.notes = "no pair produced usable window stats"
        return result

    # Count per-window pair-level wins
    winner_counts: Dict[int, int] = {}
    for _, metrics in valid:
        w = int(metrics["winner"])
        winner_counts[w] = winner_counts.get(w, 0) + 1
    result.universe_winners = winner_counts
    result.universe_count = len(valid)

    # Per-underlying override flag: any window beats 30d by >30% on residual_sd
    for letf, metrics in valid:
        stats_30d = next(
            (s for s in metrics["window_stats"] if s["window_days"] == spec), None
        )
        if stats_30d is None or stats_30d["residual_sd"] <= 0:
            continue
        sd_30d = stats_30d["residual_sd"]
        for s in metrics["window_stats"]:
            if s["window_days"] == spec:
                continue
            improvement = 1.0 - (s["residual_sd"] / sd_30d)
            if improvement > _OVERRIDE_IMPROVEMENT_THRESHOLD:
                result.per_underlying_overrides.append(
                    (letf, int(s["window_days"]), float(improvement))
                )

    # Universe winner: simple plurality + majority check
    n = len(valid)
    majority_threshold = (n // 2) + 1  # 3 of 5 = majority

    sorted_winners = sorted(winner_counts.items(), key=lambda x: (-x[1], x[0]))
    top_window, top_count = sorted_winners[0]

    if top_count >= majority_threshold:
        result.universe_winner = int(top_window)
        if top_window == spec:
            result.tag = "CALIB-OK"
            result.notes = (
                f"{spec}d window wins majority: {top_count} of {n} pair(s) prefer "
                f"{spec}d. Spec default validated. Per-pair winners: {dict(winner_counts)}."
            )
        else:
            result.tag = "CALIB-ADJUST"
            result.recommended_value = int(top_window)
            result.notes = (
                f"{top_window}d window wins majority: {top_count} of {n} pair(s) prefer "
                f"{top_window}d. Recommend changing spec from {spec}d to {top_window}d. "
                f"Per-pair winners: {dict(winner_counts)}."
            )
    else:
        result.tag = "CALIB-FINDING"
        result.notes = (
            f"No window wins majority (top: {top_window}d with {top_count} of {n} "
            f"pair(s)). Per-pair winners: {dict(winner_counts)}. Keeping spec "
            f"default {spec}d per recovery doc rule (do not change on ambiguous "
            f"evidence)."
        )

    if result.per_underlying_overrides:
        override_summary = ", ".join(
            f"{t}={w}d ({pct * 100:.0f}% lower SD vs {spec}d)"
            for t, w, pct in result.per_underlying_overrides
        )
        result.notes += (
            f" Per-underlying override candidates ({_OVERRIDE_IMPROVEMENT_THRESHOLD * 100:.0f}%+ "
            f"residual SD reduction at non-{spec}d window): {override_summary}"
        )

    return result
