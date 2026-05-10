"""Build PIN-CALL / PIN-PUT debit-vertical specs at the GEX walls.

PIN-CALL: long call @ call_wall, short call @ call_wall + strike_step
PIN-PUT:  long put  @ put_support, short put  @ put_support - strike_step
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from backtest.touch_pin.loader import ChainEntry


@dataclass(frozen=True)
class VerticalSpec:
    side: str  # "PIN-CALL" or "PIN-PUT"
    long_K: float
    short_K: float
    width: float
    entry_mid: float
    long_bid: float
    long_ask: float
    short_bid: float
    short_ask: float


def build_verticals(
    chain: Dict[float, ChainEntry],
    walls: Dict[str, float],
    spot: float,
    strike_step: float = 1.0,
) -> Tuple[Optional[VerticalSpec], Optional[VerticalSpec]]:
    """Build both PIN-CALL and PIN-PUT specs (either may be None)."""
    pin_call = _build_call_vertical(chain, walls.get("call_wall"), strike_step)
    pin_put = _build_put_vertical(chain, walls.get("put_support"), strike_step)
    return pin_call, pin_put


def _build_call_vertical(chain, call_wall, step):
    if call_wall is None:
        return None
    long_K = float(call_wall)
    short_K = long_K + step
    long_e = chain.get(long_K)
    short_e = chain.get(short_K)
    if long_e is None or short_e is None:
        return None
    if not long_e.call_valid() or not short_e.call_valid():
        return None
    entry_mid = long_e.call_mid - short_e.call_mid
    if entry_mid <= 0:
        return None
    return VerticalSpec(
        side="PIN-CALL",
        long_K=long_K, short_K=short_K, width=step,
        entry_mid=entry_mid,
        long_bid=long_e.call_bid, long_ask=long_e.call_ask,
        short_bid=short_e.call_bid, short_ask=short_e.call_ask,
    )


def _build_put_vertical(chain, put_support, step):
    if put_support is None:
        return None
    long_K = float(put_support)
    short_K = long_K - step
    long_e = chain.get(long_K)
    short_e = chain.get(short_K)
    if long_e is None or short_e is None:
        return None
    if not long_e.put_valid() or not short_e.put_valid():
        return None
    entry_mid = long_e.put_mid - short_e.put_mid
    if entry_mid <= 0:
        return None
    return VerticalSpec(
        side="PIN-PUT",
        long_K=long_K, short_K=short_K, width=step,
        entry_mid=entry_mid,
        long_bid=long_e.put_bid, long_ask=long_e.put_ask,
        short_bid=short_e.put_bid, short_ask=short_e.put_ask,
    )
