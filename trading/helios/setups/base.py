"""Base types for JOSHUA setups.

A SetupAction is the output of a setup's `evaluate(...)` method:
  - direction "call" -> buy ATM call, sell ATM+spread_width call (BULL_CALL debit)
  - direction "put"  -> buy ATM put, sell ATM-spread_width put (BEAR_PUT debit)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trading.helios.models import SetupType


@dataclass(frozen=True)
class SetupAction:
    setup: SetupType
    direction: Literal["call", "put"]
    long_strike: float
    short_strike: float
    reason: str

    def __post_init__(self):
        if self.direction not in ("call", "put"):
            raise ValueError(f"direction must be 'call' or 'put', got {self.direction!r}")
