from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from backtest.ember.models import DayChain, Position


@dataclass(frozen=True)
class AdapterConfig:
    entry_minute: int = 0          # minutes since 09:30 ET
    short_delta: float = 0.16      # target |delta| for short strikes
    wing_width: float = 5.0        # dollars between short and long strike


class StrategyAdapter(Protocol):
    def eligible(self, day: DayChain, cfg: AdapterConfig) -> bool: ...
    def build_entry(self, day: DayChain, cfg: AdapterConfig) -> Optional[Position]: ...
