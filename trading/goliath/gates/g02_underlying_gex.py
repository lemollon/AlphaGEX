"""Gate G02 -- Underlying GEX not in extreme negative regime.

Master spec section 2:
    "Underlying GEX not in extreme negative regime -- Per-LETF regime check"

Same shape as G01 but evaluates the underlying single-name (MSTR, TSLA,
NVDA, COIN, AMD) instead of SPY. Single-name underlyings carry far less
absolute GEX than SPY, so the threshold is smaller. -5e8 is a v0.2
placeholder; per-ticker tuning belongs in v0.3 once we accumulate enough
historical data to characterize each name's GEX distribution.
"""
from __future__ import annotations

from .base import GateOutcome, GateResult

# Default threshold across all 5 underlyings. v0.3-tunable per ticker.
EXTREME_NEGATIVE_GEX_THRESHOLD = -5.0e8


def evaluate(underlying_ticker: str, underlying_net_gex: float) -> GateResult:
    """Pass when underlying net GEX is at or above the threshold.

    Args:
        underlying_ticker: e.g. "MSTR", "TSLA", "NVDA", "COIN", "AMD"
        underlying_net_gex: net GEX in dollars from TV /api/gex/latest

    Returns:
        GateResult with gate="G02".
    """
    context = {
        "underlying_ticker": underlying_ticker,
        "underlying_net_gex": float(underlying_net_gex),
        "threshold": EXTREME_NEGATIVE_GEX_THRESHOLD,
    }
    if underlying_net_gex < EXTREME_NEGATIVE_GEX_THRESHOLD:
        return GateResult(
            gate="G02",
            outcome=GateOutcome.FAIL,
            reason=(
                f"{underlying_ticker} net GEX {underlying_net_gex:.2e} below "
                f"extreme-negative threshold {EXTREME_NEGATIVE_GEX_THRESHOLD:.2e}"
            ),
            context=context,
        )
    return GateResult(
        gate="G02",
        outcome=GateOutcome.PASS,
        reason=f"{underlying_ticker} net GEX {underlying_net_gex:.2e} above threshold",
        context=context,
    )
