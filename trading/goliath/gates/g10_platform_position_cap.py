"""Gate G10 -- Total open GOLIATH positions <= 3 across all instances.

Master spec section 2:
    "Total open GOLIATH positions <= 3 across all instances --
     Platform concentration cap"

Master spec section 5 reinforces with: "Max concurrent positions: 3
across the entire platform".

This gate is evaluated BEFORE opening a new position, so it passes
when the current open-count leaves room for one more (i.e.,
current < max_concurrent). At-or-above-cap fails.

Caller is responsible for counting open positions across all 5 LETF
instances (typically a single SQL aggregate).
"""
from __future__ import annotations

from .base import GateOutcome, GateResult

DEFAULT_MAX_CONCURRENT = 3


def evaluate(
    open_position_count: int,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> GateResult:
    """Pass when open_position_count < max_concurrent.

    Args:
        open_position_count: total open GOLIATH positions across all
            instances (MSTU + TSLL + NVDL + CONL + AMDL combined).
        max_concurrent: platform cap (default 3 per spec).
    """
    context = {
        "open_position_count": int(open_position_count),
        "max_concurrent": int(max_concurrent),
    }

    if open_position_count >= max_concurrent:
        return GateResult(
            gate="G10",
            outcome=GateOutcome.FAIL,
            reason=(
                f"Platform open-position count {open_position_count} "
                f">= cap {max_concurrent} (no room for new trade)"
            ),
            context=context,
        )

    return GateResult(
        gate="G10",
        outcome=GateOutcome.PASS,
        reason=(
            f"Platform open-position count {open_position_count} "
            f"< cap {max_concurrent}"
        ),
        context=context,
    )
