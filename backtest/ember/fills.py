# backtest/ember/fills.py
from __future__ import annotations

from typing import Dict, List, Tuple

from backtest.ember.models import Leg, Quote

FILL_ASK_CROSS = "ask_cross"
FILL_MID = "mid"
FILL_MID_SLIP = "mid_slip"

COMMISSION_PER_LEG = 0.65   # $/contract/leg (one side)
CONTRACT_MULTIPLIER = 100   # options multiplier


def leg_price(quote: Quote, buying: bool, fill: str, slippage: float = 0.03) -> float:
    """Per-contract execution price for one leg under a fill model."""
    if fill == FILL_ASK_CROSS:
        return quote.ask if buying else quote.bid
    if fill == FILL_MID:
        return quote.mid
    if fill == FILL_MID_SLIP:
        return quote.mid + slippage if buying else quote.mid - slippage
    raise ValueError(f"unknown fill model: {fill!r}")


def signed_cashflow(
    legs: List[Leg],
    quotes: Dict[Tuple[float, str], Quote],
    action: str,                 # "open" or "close"
    fill: str,
    slippage: float = 0.03,
) -> float:
    """Net cash flow per 1 contract, price units. + = received, - = paid.

    A long leg is bought to open / sold to close; a short leg is sold to
    open / bought to close. Buying pays (cash out), selling receives (cash in).
    """
    total = 0.0
    for leg in legs:
        buying = (leg.qty > 0) == (action == "open")
        q = quotes[(leg.strike, leg.right)]
        px = leg_price(q, buying, fill, slippage)
        total += (-px if buying else px) * abs(leg.qty)
    return total


def commission(legs: List[Leg], contracts: int) -> float:
    """Round-trip (open + close) commission in dollars."""
    return COMMISSION_PER_LEG * len(legs) * 2 * contracts
