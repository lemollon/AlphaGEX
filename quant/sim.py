"""Simplified intraday simulator for debit-vertical PnL with PT/SL/trail/EOD.

Walks a minute-indexed mark-series from entry_minute to eod_minute, returning
the first triggered exit. Distilled from backtest/helios_intraday/_simulate_intraday
with HeliosConfig replaced by explicit threshold parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol


class _BarsLike(Protocol):
    def mark_at(self, minute: int) -> Optional[float]: ...


@dataclass(frozen=True)
class IntradayResult:
    exit_minute: int
    exit_reason: str   # "PT" | "PT_GRACE" | "SL" | "TRAIL" | "EOD"
    realized_pct: float


@dataclass(frozen=True)
class MarkSeries:
    marks: Dict[int, float]

    def mark_at(self, minute: int) -> Optional[float]:
        return self.marks.get(minute)


def simulate_intraday(
    *,
    debit: float,
    entry_minute: int,
    eod_minute: int,
    bars: _BarsLike,
    pt_pct: float,
    sl_pct: float,
    sl_grace_minutes: int = 0,
    trailing_activate_pct: Optional[float] = None,
    trailing_stop_pct: Optional[float] = None,
) -> IntradayResult:
    """First-trigger walk through bars[entry_minute..eod_minute]."""
    pt_threshold = debit * (1.0 + pt_pct / 100.0)
    sl_threshold = debit * (1.0 - sl_pct / 100.0)
    trailing_enabled = trailing_activate_pct is not None and trailing_stop_pct is not None
    activate_threshold = debit * (1.0 + (trailing_activate_pct or 0.0) / 100.0)
    peak = debit
    trail_armed = False

    for minute in range(entry_minute, eod_minute + 1):
        mark = bars.mark_at(minute)
        if mark is None:
            continue
        minutes_since_entry = minute - entry_minute
        if mark > peak:
            peak = mark
        if trailing_enabled and not trail_armed and peak >= activate_threshold:
            trail_armed = True

        if mark >= pt_threshold:
            in_grace = minutes_since_entry < sl_grace_minutes
            return IntradayResult(
                exit_minute=minute,
                exit_reason="PT_GRACE" if in_grace else "PT",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

        if trail_armed and trailing_stop_pct is not None:
            trail_floor = peak * (1.0 - trailing_stop_pct / 100.0)
            if mark <= trail_floor:
                return IntradayResult(
                    exit_minute=minute,
                    exit_reason="TRAIL",
                    realized_pct=(mark / debit - 1.0) * 100.0,
                )

        if not trail_armed and minutes_since_entry >= sl_grace_minutes and mark <= sl_threshold:
            return IntradayResult(
                exit_minute=minute,
                exit_reason="SL",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

        if minute >= eod_minute:
            return IntradayResult(
                exit_minute=minute,
                exit_reason="EOD",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

    return IntradayResult(exit_minute=eod_minute, exit_reason="EOD", realized_pct=0.0)
