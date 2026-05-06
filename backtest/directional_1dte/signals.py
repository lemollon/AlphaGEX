"""Wall-proximity entry signal for SOLOMON / GIDEON 1DTE backtest.

Mirrors trading/solomon_v2/signals.py:check_wall_proximity exactly.
Returns (Signal, None) on entry, (None, skip_reason_str) on skip.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Signal:
    direction: str   # "BULLISH" or "BEARISH"
    spread_type: str # "BULL_CALL" or "BEAR_PUT"
    reason: str      # human-readable rationale


def generate_signal(walls, spot: float, vix: Optional[float], config):
    """Return (Signal, None) on entry, (None, skip_reason) on skip."""
    if vix is None:
        return None, "NO_VIX_DATA"
    if vix < config.min_vix or vix > config.max_vix:
        return None, "VIX_OUT_OF_RANGE"
    if not walls or walls.get("call_wall") is None or walls.get("put_wall") is None:
        return None, "NO_WALLS_FOUND"

    call_wall = float(walls["call_wall"])
    put_wall = float(walls["put_wall"])
    if spot <= 0:
        return None, "NO_WALLS_FOUND"

    dist_to_put_pct = abs(spot - put_wall) / spot * 100
    dist_to_call_pct = abs(call_wall - spot) / spot * 100

    near_put = dist_to_put_pct <= config.wall_filter_pct
    near_call = dist_to_call_pct <= config.wall_filter_pct

    if near_put and near_call:
        d_put = abs(spot - put_wall)
        d_call = abs(call_wall - spot)
        if d_put <= d_call:  # bullish wins exact ties
            return (
                Signal("BULLISH", "BULL_CALL",
                       f"Tie-break to put wall (${d_put:.2f} vs ${d_call:.2f})"),
                None,
            )
        return (
            Signal("BEARISH", "BEAR_PUT",
                   f"Tie-break to call wall (${d_call:.2f} vs ${d_put:.2f})"),
            None,
        )

    if near_put:
        return Signal("BULLISH", "BULL_CALL", f"Within {dist_to_put_pct:.2f}% of put wall"), None
    if near_call:
        return Signal("BEARISH", "BEAR_PUT", f"Within {dist_to_call_pct:.2f}% of call wall"), None
    return None, "NOT_NEAR_WALL"
