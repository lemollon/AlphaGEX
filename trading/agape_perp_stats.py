"""Shared stats helpers for the AGAPE perpetual bots.

Trades opened while CoinGlass funding data was unavailable (the
DEGRADED_NO_COINGLASS paper override in each bot's signals.py) are recorded
with funding_regime_at_entry of None / "" / "UNKNOWN". They are real P&L, but
they were taken on a backup signal, so they are excluded from win rate.
"""

from typing import Dict, Iterable, Optional, Tuple

DEGRADED_FUNDING_REGIMES = (None, "", "UNKNOWN")


def is_degraded_trade(trade: Dict) -> bool:
    return trade.get("funding_regime_at_entry") in DEGRADED_FUNDING_REGIMES


def scored_win_rate(closed_trades: Optional[Iterable[Dict]]) -> Tuple[Optional[float], int, int]:
    """Win rate (percent, 1dp) over non-degraded closed trades.

    Returns (win_rate, scored_count, degraded_count). win_rate is None when
    no non-degraded trades have closed yet.
    """
    scored = 0
    degraded = 0
    wins = 0
    for t in closed_trades or []:
        if is_degraded_trade(t):
            degraded += 1
            continue
        scored += 1
        if (t.get("realized_pnl") or 0) > 0:
            wins += 1
    win_rate = round(wins / scored * 100, 1) if scored else None
    return win_rate, scored, degraded
