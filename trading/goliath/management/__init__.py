"""GOLIATH position management -- 8 exit triggers + state machine.

Master spec section 4: every open position is evaluated each
management cycle against 8 deterministic exit triggers (T1..T8).
The management engine returns the first fired action; the bot's
broker layer executes the close legs.

NO ROLLING. Close-only on every trigger.

Public API exports the shared state types here. Trigger modules
live under ``triggers/``; the engine entry point is ``engine.py``.
"""
from .state import (
    ManagementAction,
    Position,
    PositionState,
    TriggerResult,
)

__all__ = [
    "ManagementAction",
    "Position",
    "PositionState",
    "TriggerResult",
]
