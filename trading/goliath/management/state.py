"""Position state machine and shared types for GOLIATH management.

Master spec section 4: every position transitions through
    OPEN -> MANAGING -> CLOSING -> CLOSED.

Triggers (T1..T8) consume a Position and return Optional[ManagementAction].
The management engine selects the first firing trigger and the bot's
broker layer executes the corresponding leg closes.

NO ROLLING. Per master spec section 4: "If a trade doesn't work, close
it. Rolling is how every short-vol strategy dies." There is no roll
action; close-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class PositionState(str, Enum):
    """Lifecycle state of a GOLIATH position."""

    OPEN = "OPEN"          # Filled at broker, no exit triggered
    MANAGING = "MANAGING"  # An exit trigger is being acted on (cancel-replace cycle)
    CLOSING = "CLOSING"    # Close orders submitted, awaiting fills
    CLOSED = "CLOSED"      # All legs closed (or expired), terminal state


@dataclass
class Position:
    """An open GOLIATH position with all data triggers need to evaluate.

    Strike + entry-economics fields are snapshotted at entry and never
    mutated. Current-quote fields are refreshed by the caller before each
    trigger evaluation cycle. Triggers do not fetch market data; the
    Position carries everything they need.
    """

    # Identity
    position_id: str
    instance_name: str         # e.g. "GOLIATH-MSTU"
    letf_ticker: str           # e.g. "MSTU"
    underlying_ticker: str     # e.g. "MSTR"

    # Lifecycle
    state: PositionState
    entered_at: datetime       # UTC; filled timestamp
    expiration_date: date      # Friday of entry week (7 DTE)

    # Structure (snapshot at entry)
    short_put_strike: float
    long_put_strike: float
    long_call_strike: float

    # Entry economics (snapshot)
    entry_long_call_cost: float       # mid of long-call leg at entry
    entry_put_spread_credit: float    # short_put_mid - long_put_mid at entry
    entry_net_cost: float             # long_call_cost - put_spread_credit
    defined_max_loss: float           # put_spread_width - entry_put_spread_credit

    # Regime context for T8 (snapshot of underlying GEX regime at entry)
    entry_underlying_gex_regime: str  # "POSITIVE" / "NEUTRAL" / "NEGATIVE"

    # Current market data (refreshed each cycle)
    current_short_put_mid: float
    current_long_put_mid: float
    current_long_call_mid: float
    current_underlying_spot: float
    current_underlying_gex_regime: str

    @property
    def current_put_spread_value(self) -> float:
        """Current debit to close the put spread = short - long mid (positive)."""
        return self.current_short_put_mid - self.current_long_put_mid

    @property
    def current_net_position_value(self) -> float:
        """Current marked-to-market value of the full structure."""
        # Long call value + (entry_credit - current_close_cost_of_spread)
        # = current_long_call_mid + (entry_put_spread_credit - current_put_spread_value)
        return (
            self.current_long_call_mid
            + (self.entry_put_spread_credit - self.current_put_spread_value)
        )

    @property
    def current_total_pnl(self) -> float:
        """Mark-to-market P&L vs entry net cost."""
        return self.current_net_position_value - self.entry_long_call_cost


@dataclass
class ManagementAction:
    """The action a trigger emits when it fires.

    Triggers either close the call leg, the put spread (both legs
    together), or the entire position. ``closes_everything`` is the
    convenience boolean for T2/T4/T5/T6/T7.
    """

    trigger_id: str          # e.g. "T1", "T7"
    close_call: bool         # close long-call leg
    close_put_spread: bool   # close short put + long put as a 2-leg combo
    reason: str
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def closes_everything(self) -> bool:
        return self.close_call and self.close_put_spread

    @property
    def closes_anything(self) -> bool:
        return self.close_call or self.close_put_spread


# Triggers return Optional[ManagementAction]. The engine picks the first
# fired action per a priority order (defined in management/engine.py).
TriggerResult = Optional[ManagementAction]
