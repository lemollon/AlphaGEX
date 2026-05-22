from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    close: float

    @property
    def mid(self) -> float:
        """Mid of a valid two-sided quote, else last trade (close)."""
        if self.bid is not None and self.ask is not None and self.ask >= self.bid > 0:
            return (self.bid + self.ask) / 2.0
        return self.close


@dataclass(frozen=True)
class Leg:
    strike: float
    right: str            # "C" or "P"
    qty: int              # +1 long (bought), -1 short (sold)


@dataclass
class Position:
    legs: List[Leg]
    entry_minute: int          # minutes since 09:30 ET
    entry_credit: float        # net credit per spread, price units (>0)
    contracts: int = 1


@dataclass(frozen=True)
class MinuteChain:
    minute: int
    spot: float
    quotes: Dict[Tuple[float, str], Quote]   # (strike, right) -> Quote


@dataclass
class DayChain:
    trade_date: dt.date
    expiration: dt.date
    minutes: Dict[int, MinuteChain] = field(default_factory=dict)

    def spot(self, minute: int) -> Optional[float]:
        mc = self.minutes.get(minute)
        return mc.spot if mc else None

    def quote(self, minute: int, strike: float, right: str) -> Optional[Quote]:
        mc = self.minutes.get(minute)
        if not mc:
            return None
        return mc.quotes.get((strike, right))

    @property
    def sorted_minutes(self) -> List[int]:
        return sorted(self.minutes.keys())
