"""Shared types for GOLIATH entry gates G01-G10.

Each gate exposes a module-level ``evaluate(...) -> GateResult``. The
orchestrator runs gates in order; first non-PASS stops the chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateOutcome(str, Enum):
    """Outcome of a single gate evaluation.

    PASS                 -> gate cleared
    FAIL                 -> gate's condition not met (data was sufficient)
    INSUFFICIENT_HISTORY -> gate could not be evaluated due to data gap
                            (spec Q6: fail-closed; treat as FAIL upstream)
    """

    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


@dataclass(frozen=True)
class GateResult:
    """Single gate's evaluation output.

    Attributes:
        gate: gate identifier, e.g. "G01"
        outcome: GateOutcome enum value
        reason: human-readable explanation (also stored in DB on failure)
        context: snapshot of inputs that drove the decision
    """

    gate: str
    outcome: GateOutcome
    reason: str
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.outcome == GateOutcome.PASS

    @property
    def is_terminal_fail(self) -> bool:
        """True if the orchestrator should stop the chain on this result."""
        return self.outcome != GateOutcome.PASS
