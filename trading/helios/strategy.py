"""Pure exit decision tree. No I/O.

Order of precedence at every check:
  1. PT (always armed)
  2. SL (only if minutes_since_entry >= grace)
  3. EOD (only if now_ct >= eod_close_time_ct)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading.helios.models import HeliosConfig


class ExitReason(str, Enum):
    PT = "PT"
    PT_GRACE = "PT_GRACE"
    SL = "SL"
    EOD = "EOD"


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: Optional[ExitReason] = None


def decide_exit(
    *,
    debit: float,
    mark_to_close: float,
    minutes_since_entry: int,
    now_ct: dt.datetime,
    config: HeliosConfig,
) -> ExitDecision:
    pt_threshold = debit * (1.0 + config.profit_target_pct / 100.0)
    sl_threshold = debit * (1.0 - config.stop_loss_pct / 100.0)
    in_grace = minutes_since_entry < config.stop_loss_grace_minutes

    if mark_to_close >= pt_threshold:
        return ExitDecision(True, ExitReason.PT_GRACE if in_grace else ExitReason.PT)

    if not in_grace and mark_to_close <= sl_threshold:
        return ExitDecision(True, ExitReason.SL)

    eod_h, eod_m = (int(x) for x in config.eod_close_time_ct.split(":"))
    if now_ct.hour > eod_h or (now_ct.hour == eod_h and now_ct.minute >= eod_m):
        return ExitDecision(True, ExitReason.EOD)

    return ExitDecision(False, None)
