"""GOLIATH position sizing package -- two-level cap algorithm.

Public API:
    calculate_contracts(letf_ticker, max_loss_per_contract, ...) -> SizingResult
    per_trade_risk_dollars() -> float  ($75 by default)
    instance_cap(letf_ticker) -> float
    PLATFORM_TOTAL_CAP, HARD_CAP_PER_TRADE constants
"""
from .calculator import SizingResult, calculate_contracts
from .limits import (
    HARD_CAP_PER_TRADE,
    INSTANCE_ALLOCATIONS,
    PLATFORM_TOTAL_CAP,
    instance_cap,
    per_trade_risk_dollars,
)

__all__ = [
    "SizingResult",
    "calculate_contracts",
    "HARD_CAP_PER_TRADE",
    "INSTANCE_ALLOCATIONS",
    "PLATFORM_TOTAL_CAP",
    "instance_cap",
    "per_trade_risk_dollars",
]
