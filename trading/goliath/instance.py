"""GoliathInstance -- stateful per-LETF wrapper.

Per master spec section 9.2:
    "GoliathInstance: Stateful per-LETF wrapper. Holds config +
     open positions + kill state."

The instance does not own broker logic or market-data fetching; it is
a pure container that the engine reads from. Persistence of
open_positions to a database is left to the runner (main.py) so this
class stays unit-testable with synthetic inputs.

Aggregate dollar-at-risk uses an option multiplier of 100 by default
(US equity option contracts). Pass ``multiplier=1`` for raw test
dollars (i.e. when defined_max_loss is already total dollars).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from trading.goliath.kill_switch import KillScope, is_killed
from trading.goliath.management.state import Position

from .configs import InstanceConfig

# Standard equity-option multiplier; LETFs trade $100/contract by default.
_OPTION_MULTIPLIER = 100


@dataclass
class GoliathInstance:
    """Stateful container for one LETF instance (config + open positions).

    Attributes:
        config: per-LETF InstanceConfig (cap, paper_only, ticker, etc.)
        open_positions: list of currently open Positions for this LETF
    """

    config: InstanceConfig
    open_positions: list[Position] = field(default_factory=list)

    # ---- Identity ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Bot-guard tag, e.g. 'GOLIATH-MSTU'."""
        return self.config.bot_guard_tag

    @property
    def letf_ticker(self) -> str:
        return self.config.letf_ticker

    @property
    def underlying_ticker(self) -> str:
        return self.config.underlying_ticker

    # ---- Position aggregates ----------------------------------------------

    @property
    def open_count(self) -> int:
        return len(self.open_positions)

    def open_dollars_at_risk(self, multiplier: int = _OPTION_MULTIPLIER) -> float:
        """Sum of (contracts * defined_max_loss * multiplier) across open positions.

        defined_max_loss is per-contract (master spec section 5 convention).
        Position.contracts may be missing on legacy instances; defaults to 1.
        """
        total = 0.0
        for p in self.open_positions:
            contracts = int(getattr(p, "contracts", 1))
            total += contracts * float(p.defined_max_loss) * multiplier
        return total

    # ---- Lifecycle / kill state -------------------------------------------

    @property
    def is_killed(self) -> bool:
        """True when this instance has an active kill row."""
        return is_killed(KillScope.INSTANCE, self.name)

    def has_capacity_for_new_trade(self) -> bool:
        """Quick local check: kill clear AND below per-instance cap.

        Does not invoke the gate orchestrator -- caller still runs G10
        for the platform-cap check separately.

        Unit note: open_dollars_at_risk() returns dollars (multiplier=100
        is applied internally). allocation_cap is also in dollars (e.g.
        $200 for MSTU per master spec section 5). Compare dollars-to-
        dollars; do NOT multiply allocation_cap by the option multiplier
        (prior bug fixed 2026-05-01 audit; reproduced in
        test_instance.py::CapacityCheck::test_no_capacity_at_or_above_allocation_cap).

        NOTE: this method is currently a test-only utility. Production
        sizing goes through engine.evaluate_entry -> sizing.calculator,
        which reads instance.open_dollars_at_risk() directly without
        going through this helper. Kept here for runner-level code that
        might want a quick pre-flight check before assembling a snapshot.
        """
        if self.is_killed:
            return False
        return self.open_dollars_at_risk() < self.config.allocation_cap

    # ---- Convenience -------------------------------------------------------

    def add_position(self, position: Position) -> None:
        self.open_positions.append(position)

    def remove_position(self, position_id: str) -> bool:
        """Remove a position by id; returns True if found and removed."""
        for i, p in enumerate(self.open_positions):
            if p.position_id == position_id:
                del self.open_positions[i]
                return True
        return False

    def find_position(self, position_id: str) -> Position | None:
        for p in self.open_positions:
            if p.position_id == position_id:
                return p
        return None


def build_all_instances(
    configs: Sequence[InstanceConfig],
) -> dict[str, GoliathInstance]:
    """Construct empty GoliathInstance objects for each config (no open positions)."""
    return {cfg.bot_guard_tag: GoliathInstance(config=cfg) for cfg in configs}
