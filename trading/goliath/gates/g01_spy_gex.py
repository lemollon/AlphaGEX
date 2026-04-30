"""Gate G01 -- SPY GEX not in extreme negative regime.

Master spec section 2:
    "SPY GEX not in extreme negative regime -- Global market regime check"

Spec is silent on the numeric threshold; v0.2 uses -3B as a placeholder
(common AlphaGEX convention for "extreme negative" SPX/SPY regimes). This
constant is documented as v0.3-tunable; tracked in goliath-v0.3-todos.md.

The gate is data-only: caller fetches SPY net GEX (typically via TV's
get_net_gamma("SPY")) and passes the float in. Decoupling the fetch keeps
this unit-testable with synthetic inputs.
"""
from __future__ import annotations

from .base import GateOutcome, GateResult

# Threshold below which SPY net GEX is "extreme negative" -> reject.
# v0.3-tunable; current value matches existing AlphaGEX SPY regime
# classification used by FORTRESS / SOLOMON.
EXTREME_NEGATIVE_GEX_THRESHOLD = -3.0e9


def evaluate(spy_net_gex: float) -> GateResult:
    """Pass when SPY net GEX is at or above the extreme-negative threshold.

    Args:
        spy_net_gex: SPY net gamma exposure in dollars (per TV /api/gex/latest)

    Returns:
        GateResult with gate="G01" and outcome PASS or FAIL.
    """
    context = {
        "spy_net_gex": float(spy_net_gex),
        "threshold": EXTREME_NEGATIVE_GEX_THRESHOLD,
    }
    if spy_net_gex < EXTREME_NEGATIVE_GEX_THRESHOLD:
        return GateResult(
            gate="G01",
            outcome=GateOutcome.FAIL,
            reason=(
                f"SPY net GEX {spy_net_gex:.2e} below extreme-negative "
                f"threshold {EXTREME_NEGATIVE_GEX_THRESHOLD:.2e}"
            ),
            context=context,
        )
    return GateResult(
        gate="G01",
        outcome=GateOutcome.PASS,
        reason=f"SPY net GEX {spy_net_gex:.2e} above threshold",
        context=context,
    )
