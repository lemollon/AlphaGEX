"""Gate G07 -- Bid-ask spread on each leg <= 20% of mid.

Master spec section 2:
    "Bid-ask spread on each leg <= 20% of mid -- Slippage protection"

Thin wrapper over engine.passes_bid_ask, which uses
engine.MAX_BID_ASK_RATIO (0.20) as the universal threshold. Any leg
with non-positive mid or spread > 20% of mid causes a FAIL.
"""
from __future__ import annotations

from trading.goliath.strike_mapping.engine import (
    MAX_BID_ASK_RATIO,
    OptionLeg,
    compute_mid,
    passes_bid_ask,
)

from .base import GateOutcome, GateResult


def _leg_ratio(leg: OptionLeg) -> float:
    """Spread-to-mid ratio for diagnostic logging.

    Returns infinity for non-positive mids so the audit log clearly
    flags degenerate quotes (rather than dividing by zero).
    """
    mid = compute_mid(leg)
    if mid <= 0:
        return float("inf")
    return (leg.ask - leg.bid) / mid


def evaluate(
    short_put: OptionLeg,
    long_put: OptionLeg,
    long_call: OptionLeg,
) -> GateResult:
    """Pass when every leg's bid-ask <= MAX_BID_ASK_RATIO of mid (20%)."""
    legs = {
        "short_put": short_put,
        "long_put": long_put,
        "long_call": long_call,
    }
    failures = [
        f"{name}@{leg.strike} ratio={_leg_ratio(leg):.3f}"
        for name, leg in legs.items()
        if not passes_bid_ask(leg)
    ]

    context = {
        "max_bid_ask_ratio": MAX_BID_ASK_RATIO,
        "short_put_ratio": _leg_ratio(short_put),
        "long_put_ratio": _leg_ratio(long_put),
        "long_call_ratio": _leg_ratio(long_call),
    }

    if failures:
        return GateResult(
            gate="G07",
            outcome=GateOutcome.FAIL,
            reason=f"Bid-ask above {MAX_BID_ASK_RATIO}: {', '.join(failures)}",
            context=context,
        )

    return GateResult(
        gate="G07",
        outcome=GateOutcome.PASS,
        reason=f"All legs bid-ask <= {MAX_BID_ASK_RATIO} of mid",
        context=context,
    )
