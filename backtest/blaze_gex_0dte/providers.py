"""Debit + mark providers for the 0DTE ATM debit vertical, fed to replay_day."""
from __future__ import annotations
from typing import Callable, Tuple
from .loader import DayChain

def _right_for(direction: str) -> str:
    return "C" if direction == "call" else "P"

def make_providers(day: DayChain) -> Tuple[Callable, Callable]:
    def debit_estimator(snap, action) -> float:
        r = _right_for(action.direction)
        long_q = day.quote(0, float(action.long_strike), r)
        short_q = day.quote(0, float(action.short_strike), r)
        if long_q is None or short_q is None:
            return 0.0
        long_ask = long_q[1]
        short_bid = short_q[0]
        if long_ask is None or short_bid is None:
            return 0.0
        return max(0.0, long_ask - short_bid)

    def mark_provider(*, snapshot, action, minute, entry_minute, debit) -> float:
        r = _right_for(action.direction)
        lm = day.mid(minute, float(action.long_strike), r)
        sm = day.mid(minute, float(action.short_strike), r)
        if lm is None or sm is None:
            return debit
        return max(0.0, lm - sm)

    return debit_estimator, mark_provider
