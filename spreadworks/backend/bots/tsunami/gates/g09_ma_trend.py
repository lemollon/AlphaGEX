"""Gate G09 -- Underlying not in active downtrend (above 50-day MA).

Master spec section 2:
    "Underlying not in active downtrend (above 50-day MA) -- Trend filter"

Data-only: caller computes the 50-day moving average from the
underlying's daily-close price history (yfinance is the canonical
source) and passes the float in. ``None`` means insufficient price
history (less than 50 daily closes available) -> INSUFFICIENT_HISTORY,
treated as a terminal stop per Leron Q6 fail-closed convention.
"""
from __future__ import annotations

from typing import Optional

from .base import GateOutcome, GateResult


def evaluate(
    underlying_ticker: str,
    underlying_spot: float,
    underlying_50d_ma: Optional[float],
) -> GateResult:
    """Pass when underlying spot is strictly above the 50-day MA.

    Args:
        underlying_ticker: e.g. "TSLA"
        underlying_spot: current spot price
        underlying_50d_ma: 50-day simple MA of daily closes, or None
            when fewer than 50 closes are available.
    """
    context = {
        "underlying_ticker": underlying_ticker,
        "underlying_spot": float(underlying_spot),
        "underlying_50d_ma": underlying_50d_ma,
    }

    if underlying_50d_ma is None:
        return GateResult(
            gate="G09",
            outcome=GateOutcome.INSUFFICIENT_HISTORY,
            reason=(
                f"{underlying_ticker} 50-day MA unavailable "
                "(< 50 daily closes); fail-closed"
            ),
            context=context,
        )

    gap = underlying_spot - underlying_50d_ma
    context["spot_minus_ma"] = gap
    context["spot_to_ma_pct"] = (
        gap / underlying_50d_ma if underlying_50d_ma else None
    )

    if underlying_spot <= underlying_50d_ma:
        return GateResult(
            gate="G09",
            outcome=GateOutcome.FAIL,
            reason=(
                f"{underlying_ticker} spot {underlying_spot:.2f} "
                f"<= 50d MA {underlying_50d_ma:.2f} (downtrend)"
            ),
            context=context,
        )

    return GateResult(
        gate="G09",
        outcome=GateOutcome.PASS,
        reason=(
            f"{underlying_ticker} spot {underlying_spot:.2f} "
            f"> 50d MA {underlying_50d_ma:.2f}"
        ),
        context=context,
    )
