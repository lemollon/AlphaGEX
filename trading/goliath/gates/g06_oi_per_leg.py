"""Gate G06 -- All 3 LETF strikes have OI >= 200.

Master spec section 2:
    "All 3 LETF strikes have OI >= 200 -- Liquidity check on each leg"

Thin wrapper over the engine's MIN_OI_PER_LEG predicate. The engine
already enforces this inline; this gate exists as a separate module so
the orchestrator's per-gate logging surfaces it explicitly and so the
gate can be evaluated standalone (e.g., post-quote-refresh re-check).

Wraps trading.goliath.strike_mapping.engine.MIN_OI_PER_LEG to keep
the threshold single-sourced.
"""
from __future__ import annotations

from trading.goliath.strike_mapping.engine import MIN_OI_PER_LEG, OptionLeg

from .base import GateOutcome, GateResult


def evaluate(
    short_put: OptionLeg,
    long_put: OptionLeg,
    long_call: OptionLeg,
) -> GateResult:
    """Pass when every leg has OI >= MIN_OI_PER_LEG (200 per spec)."""
    legs = {
        "short_put": short_put,
        "long_put": long_put,
        "long_call": long_call,
    }
    failures = [
        f"{name}@{leg.strike} OI={leg.open_interest}"
        for name, leg in legs.items()
        if leg.open_interest < MIN_OI_PER_LEG
    ]

    context = {
        "min_oi": MIN_OI_PER_LEG,
        "short_put_oi": short_put.open_interest,
        "long_put_oi": long_put.open_interest,
        "long_call_oi": long_call.open_interest,
    }

    if failures:
        return GateResult(
            gate="G06",
            outcome=GateOutcome.FAIL,
            reason=f"OI below {MIN_OI_PER_LEG}: {', '.join(failures)}",
            context=context,
        )

    return GateResult(
        gate="G06",
        outcome=GateOutcome.PASS,
        reason=f"All legs OI >= {MIN_OI_PER_LEG}",
        context=context,
    )
