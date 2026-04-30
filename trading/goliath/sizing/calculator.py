"""GOLIATH position sizing -- two-level cap algorithm (master spec section 5).

contracts = min(
    by_per_trade_risk      = floor($75 / max_loss_per_contract)
    by_instance_remaining  = floor((instance_cap - instance_open_dollars) / max_loss)
    by_platform_remaining  = floor((PLATFORM_CAP - platform_open_dollars) / max_loss)
    HARD_CAP_PER_TRADE     = 2
)

Returns 0 contracts when no allocation room (any remaining is < 1
contract's worth of risk). Caller treats 0 as a skip-trade signal.
"""
from __future__ import annotations

from dataclasses import dataclass

from .limits import (
    HARD_CAP_PER_TRADE,
    PLATFORM_TOTAL_CAP,
    instance_cap,
    per_trade_risk_dollars,
)

# Sentinel returned when input is invalid (e.g. non-positive max_loss).
_INVALID_MAX_LOSS = "invalid_max_loss"


@dataclass(frozen=True)
class SizingResult:
    """Outcome of calculate_contracts.

    Attributes:
        contracts: number of contracts to trade (0 = skip)
        binding_constraint: which limit bound the result -- one of
            "per_trade_risk", "instance_cap", "platform_cap", "hard_cap",
            or "invalid_max_loss" when input was non-positive.
        by_per_trade_risk: contracts allowed by the $75 per-trade limit
        by_instance_remaining: contracts allowed by remaining instance budget
        by_platform_remaining: contracts allowed by remaining platform budget
        hard_cap: HARD_CAP_PER_TRADE constant (always 2)
    """

    contracts: int
    binding_constraint: str
    by_per_trade_risk: int
    by_instance_remaining: int
    by_platform_remaining: int
    hard_cap: int


def calculate_contracts(
    letf_ticker: str,
    defined_max_loss_per_contract: float,
    instance_open_dollars: float = 0.0,
    platform_open_dollars: float = 0.0,
) -> SizingResult:
    """Return the SizingResult for a candidate trade.

    Args:
        letf_ticker: LETF being traded (drives instance cap lookup)
        defined_max_loss_per_contract: dollars at risk per single contract
            (e.g. $20 for a $0.50 width / $0.30 credit setup * 100 multiplier)
        instance_open_dollars: dollars currently at risk in open positions
            on this LETF instance (excluding the candidate trade)
        platform_open_dollars: dollars at risk across all 5 instances

    Returns:
        SizingResult with binding_constraint identifying which limit bound.
    """
    if defined_max_loss_per_contract <= 0:
        return SizingResult(
            contracts=0,
            binding_constraint=_INVALID_MAX_LOSS,
            by_per_trade_risk=0,
            by_instance_remaining=0,
            by_platform_remaining=0,
            hard_cap=HARD_CAP_PER_TRADE,
        )

    per_trade_n = int(per_trade_risk_dollars() // defined_max_loss_per_contract)

    inst_cap_dollars = instance_cap(letf_ticker)
    inst_remaining = max(0.0, inst_cap_dollars - instance_open_dollars)
    instance_n = int(inst_remaining // defined_max_loss_per_contract)

    platform_remaining = max(0.0, PLATFORM_TOTAL_CAP - platform_open_dollars)
    platform_n = int(platform_remaining // defined_max_loss_per_contract)

    candidates = {
        "per_trade_risk": per_trade_n,
        "instance_cap": instance_n,
        "platform_cap": platform_n,
        "hard_cap": HARD_CAP_PER_TRADE,
    }
    # Pick the smallest; ties broken by stable iteration order above
    # (so per_trade_risk wins ties over instance_cap, etc.).
    binding = min(candidates, key=lambda k: candidates[k])
    contracts = max(0, candidates[binding])

    return SizingResult(
        contracts=contracts,
        binding_constraint=binding,
        by_per_trade_risk=per_trade_n,
        by_instance_remaining=instance_n,
        by_platform_remaining=platform_n,
        hard_cap=HARD_CAP_PER_TRADE,
    )
