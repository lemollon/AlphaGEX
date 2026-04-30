"""Gate G05 -- LETF IV Rank >= 60.

Master spec section 2:
    "LETF IV Rank >= 60 -- Premium must be elevated to fund the call"
    "Cold-start IV-rank case logs INSUFFICIENT_HISTORY and skips trade"

Leron-confirmed (2026-04-29, Q6):
    Cold-start fallback = fail-closed. Mark INSUFFICIENT_HISTORY,
    skip trade. Proper "Option C" handling deferred to v0.3.

The gate is data-only: caller fetches IV rank (typically TV /series
``iv_rank`` field for the LETF) and passes the float in. ``None``
represents the cold-start / data-unavailable case and produces the
``INSUFFICIENT_HISTORY`` outcome (a non-PASS result; orchestrator
treats it as a terminal stop).
"""
from __future__ import annotations

from typing import Optional

from .base import GateOutcome, GateResult

# Spec threshold (master spec section 2 G05).
DEFAULT_IV_RANK_THRESHOLD = 60.0


def evaluate(
    letf_ticker: str,
    iv_rank: Optional[float],
    threshold: float = DEFAULT_IV_RANK_THRESHOLD,
) -> GateResult:
    """Pass when IV rank is at or above the threshold.

    Args:
        letf_ticker: e.g. "TSLL"
        iv_rank: TV-style IV rank percentile in [0, 100], or None when
            the data source returned nothing (cold start / API gap).
        threshold: minimum IV rank required to pass (default 60).
    """
    context = {
        "letf_ticker": letf_ticker,
        "iv_rank": iv_rank,
        "threshold": threshold,
    }

    if iv_rank is None:
        return GateResult(
            gate="G05",
            outcome=GateOutcome.INSUFFICIENT_HISTORY,
            reason=(
                f"{letf_ticker} IV rank unavailable; cold-start fail-closed "
                "per spec Q6 (skip trade, add to v0.3 todos for proper handling)"
            ),
            context=context,
        )

    if iv_rank < threshold:
        return GateResult(
            gate="G05",
            outcome=GateOutcome.FAIL,
            reason=(
                f"{letf_ticker} IV rank {iv_rank:.1f} below threshold {threshold}"
            ),
            context=context,
        )

    return GateResult(
        gate="G05",
        outcome=GateOutcome.PASS,
        reason=f"{letf_ticker} IV rank {iv_rank:.1f} >= {threshold}",
        context=context,
    )
