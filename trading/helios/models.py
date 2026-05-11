from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SpreadType(str, Enum):
    BULL_CALL = "BULL_CALL"
    BEAR_PUT = "BEAR_PUT"


class SkipReason(str, Enum):
    NO_LOCAL_GAMMA = "NO_LOCAL_GAMMA"
    NO_MAJOR_WALL = "NO_MAJOR_WALL"
    VIX_OUT_OF_RANGE = "VIX_OUT_OF_RANGE"
    NOT_NEAR_WALL = "NOT_NEAR_WALL"
    PROPHET_VETO = "PROPHET_VETO"
    ALREADY_OPEN = "ALREADY_OPEN"
    MAX_TRADES_TODAY = "MAX_TRADES_TODAY"
    NO_NEAR_EXPIRATION = "NO_NEAR_EXPIRATION"
    DEBIT_INVALID = "DEBIT_INVALID"
    SIZE_BELOW_1_CONTRACT = "SIZE_BELOW_1_CONTRACT"
    QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
    DATA_GAP = "DATA_GAP"


@dataclass(frozen=True)
class HeliosConfig:
    ticker: str = "SPY"
    wall_filter_pct: float = 1.0
    wall_concentration_threshold: float = 2.0
    wall_top_n: int = 3
    spread_width: int = 2
    min_vix: float = 15.0
    max_vix: float = 35.0
    risk_per_trade: float = 1000.0
    starting_capital: float = 10000.0
    profit_target_pct: float = 20.0
    stop_loss_pct: float = 50.0
    stop_loss_grace_minutes: int = 30
    eod_close_time_ct: str = "14:50"
    max_trades_per_day: int = 1
    monitor_poll_seconds: int = 15


@dataclass(frozen=True)
class HeliosTradeSignal:
    action: str  # "TRADE" or "SKIP"
    spread_type: Optional[SpreadType] = None
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    skip_reason: Optional[SkipReason] = None
    detail: Optional[str] = None

    @classmethod
    def trade(cls, spread_type: SpreadType, long_strike: float, short_strike: float) -> "HeliosTradeSignal":
        return cls(action="TRADE", spread_type=spread_type, long_strike=long_strike, short_strike=short_strike)

    @classmethod
    def skip(cls, reason: SkipReason, detail: str = "") -> "HeliosTradeSignal":
        return cls(action="SKIP", skip_reason=reason, detail=detail)
