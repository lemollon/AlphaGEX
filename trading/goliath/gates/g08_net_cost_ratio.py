"""Gate G08 -- Net cost on entry <= 30% of long-call cost.

Master spec section 2:
    "Net cost on entry <= 30% of long call cost --
     Spread must subsidize the call"

Thin wrapper over engine.MAX_NET_COST_TO_CALL_RATIO (0.30) and
engine.compute_mid. Computes the same net_cost / long_call_cost
ratio that build_trade_structure enforces inline; this module exists
so the orchestrator can log G08 outcomes explicitly.

Net credit (negative net_cost) trivially passes -- a credit means
the put spread fully funded the long call and then some. A
non-positive long-call mid is treated as a fail (degenerate quote).
"""
from __future__ import annotations

from trading.goliath.strike_mapping.engine import (
    MAX_NET_COST_TO_CALL_RATIO,
    OptionLeg,
    compute_mid,
)

from .base import GateOutcome, GateResult


def evaluate(
    short_put: OptionLeg,
    long_put: OptionLeg,
    long_call: OptionLeg,
) -> GateResult:
    """Pass when net_cost / long_call_mid <= MAX_NET_COST_TO_CALL_RATIO."""
    short_put_mid = compute_mid(short_put)
    long_put_mid = compute_mid(long_put)
    long_call_mid = compute_mid(long_call)

    put_spread_credit = short_put_mid - long_put_mid
    net_cost = long_call_mid - put_spread_credit

    context = {
        "max_net_cost_to_call_ratio": MAX_NET_COST_TO_CALL_RATIO,
        "short_put_mid": short_put_mid,
        "long_put_mid": long_put_mid,
        "long_call_mid": long_call_mid,
        "put_spread_credit": put_spread_credit,
        "net_cost": net_cost,
    }

    if long_call_mid <= 0:
        return GateResult(
            gate="G08",
            outcome=GateOutcome.FAIL,
            reason=(
                f"Long-call mid {long_call_mid:.4f} non-positive -- degenerate quote"
            ),
            context=context,
        )

    threshold = MAX_NET_COST_TO_CALL_RATIO * long_call_mid
    ratio = net_cost / long_call_mid
    context["net_cost_ratio"] = ratio

    if net_cost > threshold:
        return GateResult(
            gate="G08",
            outcome=GateOutcome.FAIL,
            reason=(
                f"Net cost {net_cost:.4f} > {MAX_NET_COST_TO_CALL_RATIO} "
                f"of long-call mid {long_call_mid:.4f} (ratio {ratio:.3f})"
            ),
            context=context,
        )

    return GateResult(
        gate="G08",
        outcome=GateOutcome.PASS,
        reason=(
            f"Net cost {net_cost:.4f} <= {MAX_NET_COST_TO_CALL_RATIO} "
            f"of long-call mid {long_call_mid:.4f} (ratio {ratio:.3f})"
        ),
        context=context,
    )
