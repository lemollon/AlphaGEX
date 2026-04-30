"""Gate G04 -- Underlying earnings not within 7 days.

Master spec section 2:
    "Underlying earnings not within 7 days -- Different volatility regime"
    "Earnings yfinance failure -> fail closed (no trade), do not assume safe"

The gate is data-only: caller fetches the next-earnings date (typically
via yfinance ``Ticker.calendar``) and passes it in. ``None`` represents
the data-unavailable case and is treated as FAIL per the spec rule.

V0.3 upgrade path: NASDAQ public earnings calendar fallback when
yfinance failure rate exceeds 5%% (tracked as V3-2 in goliath-v0.3-todos.md).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .base import GateOutcome, GateResult

# Spec: trade is rejected if earnings is within this many days.
DEFAULT_BLACKOUT_DAYS = 7


def evaluate(
    underlying_ticker: str,
    next_earnings_date: Optional[date],
    today: Optional[date] = None,
    blackout_days: int = DEFAULT_BLACKOUT_DAYS,
) -> GateResult:
    """Pass when next earnings is more than `blackout_days` away.

    Args:
        underlying_ticker: e.g. "TSLA"
        next_earnings_date: next scheduled earnings date, or None if
            the data source could not be reached / returned no answer.
        today: anchor date for testing; defaults to date.today()
        blackout_days: blackout window length in calendar days
    """
    today = today or date.today()
    context = {
        "underlying_ticker": underlying_ticker,
        "next_earnings_date": next_earnings_date.isoformat() if next_earnings_date else None,
        "today": today.isoformat(),
        "blackout_days": blackout_days,
    }

    # Spec: yfinance failure -> fail closed.
    if next_earnings_date is None:
        return GateResult(
            gate="G04",
            outcome=GateOutcome.FAIL,
            reason=(
                f"{underlying_ticker} earnings data unavailable; "
                "fail-closed per spec section 2 (do not assume safe)"
            ),
            context=context,
        )

    days_until = (next_earnings_date - today).days
    context["days_until_earnings"] = days_until

    # Past earnings dates (negative days_until) are not a blackout reason.
    if 0 <= days_until <= blackout_days:
        return GateResult(
            gate="G04",
            outcome=GateOutcome.FAIL,
            reason=(
                f"{underlying_ticker} earnings in {days_until} day(s) "
                f"<= {blackout_days}-day blackout window"
            ),
            context=context,
        )

    return GateResult(
        gate="G04",
        outcome=GateOutcome.PASS,
        reason=(
            f"{underlying_ticker} next earnings {next_earnings_date.isoformat()} "
            f"({days_until} day(s) away)"
        ),
        context=context,
    )
