"""GOLIATH kill-switch package -- per master spec section 6.

Per-instance triggers (I-K1, I-K2, I-K3) and platform triggers
(P-K1..P-K4). State is persisted in goliath_kill_state (migration 030)
so kills survive process restarts.

Public API exposed here:
    KillScope             enum (INSTANCE | PLATFORM)
    KillEvent             dataclass for one kill
    is_killed             check whether scope is currently killed
    record_kill           insert active kill row
    clear_kill            manual override (requires cleared_by)
    list_active_kills     audit query
"""
from .state import (
    KillEvent,
    KillScope,
    clear_kill,
    is_killed,
    list_active_kills,
    record_kill,
)

__all__ = [
    "KillEvent", "KillScope",
    "clear_kill", "is_killed", "list_active_kills", "record_kill",
]
