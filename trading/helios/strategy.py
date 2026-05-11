"""JOSHUA exit decision tree. Pure function. No I/O.

Order of precedence at every check:
  1. PT (always armed)
  2. SL (always armed — no grace period; 1DTE noise is the noise)
  3. TIME_STOP (now_ct >= eod_time_ct)
  4. DATA_FAILURE (quotes_unavail_streak >= max)

No trailing stop. Phase 2 showed it killed winners on 1DTE.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from trading.helios.models import ExitReason, JoshuaConfig


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: Optional[ExitReason] = None


def decide_exit(
    *,
    debit: float,
    mark_to_close: float,
    now_ct: dt.datetime,
    quotes_unavail_streak: int,
    config: JoshuaConfig,
) -> ExitDecision:
    pnl_pct = (mark_to_close / debit - 1.0) * 100.0 if debit > 0 else 0.0

    if pnl_pct >= config.profit_target_pct:
        return ExitDecision(True, ExitReason.PT)

    if pnl_pct <= -config.stop_loss_pct:
        return ExitDecision(True, ExitReason.SL)

    eod_h, eod_m = (int(x) for x in config.eod_time_ct.split(":"))
    if now_ct.hour > eod_h or (now_ct.hour == eod_h and now_ct.minute >= eod_m):
        return ExitDecision(True, ExitReason.TIME_STOP)

    if quotes_unavail_streak >= config.quotes_unavailable_max_cycles:
        return ExitDecision(True, ExitReason.DATA_FAILURE)

    return ExitDecision(False, None)
