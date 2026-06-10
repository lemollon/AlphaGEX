"""UNDERTOW — single-leg long-call dip-buy entry signal builder.

Buys an ATM call when an underlying pulls back >= D% from its rolling
N-day reference high, confirmed oversold (RSI) and still in an uptrend
(above its SMA). Debit strategy: entry_price = the call mid (premium
paid); max loss = full premium. Mirrors the debit plumbing of RIVER
(long_butterfly) so the executor / MTM / close paths work unchanged.

All numeric defaults are STARTING HYPOTHESES to tune from the paper
track record — the entry edge is unproven and unbacktested (see spec §0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


def closed_bars(history: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Return daily bars strictly BEFORE `today`, sorted ascending by date.

    Drops today's partial/in-progress bar so the reference high and
    indicators are computed only from completed sessions.
    """
    bars = [b for b in history if str(b["date"]) < today.isoformat()]
    return sorted(bars, key=lambda b: str(b["date"]))


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values; None if too few."""
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(float(v) for v in window) / period


def rsi(values: list[float], period: int) -> float | None:
    """Wilder-style RSI over `period` using simple gain/loss averages.

    Needs at least `period + 1` values. Returns 0..100, or None if too few.
    All-gains -> 100, all-losses -> 0.
    """
    if len(values) < period + 1 or period <= 0:
        return None
    deltas = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    window = deltas[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 4)
