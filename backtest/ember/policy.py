# backtest/ember/policy.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    profit_target_pct: Optional[float]   # % of entry credit captured; None disables
    stop_loss_mult: Optional[float]      # loss threshold = mult * credit; None disables
    time_stop_minute: Optional[int]      # minutes since 09:30 ET; None = EOD only
    trail_activation_pct: Optional[float] = None   # % of credit before trail arms
    trail_giveback_pct: Optional[float] = None     # % of credit given back from peak
    min_hold_minutes: int = 5


# SPARK's current live exit config (see project_spark_config_locks): PT 30%, SL 0.5x credit, EOD.
SPARK_BASELINE = ExitPolicy(
    name="spark_live",
    profit_target_pct=30.0,
    stop_loss_mult=0.5,
    time_stop_minute=None,
    min_hold_minutes=5,
)


def default_grid() -> List[ExitPolicy]:
    """The PT x SL x time-stop sweep, plus the SPARK baseline."""
    pts = [20.0, 30.0, 40.0, 50.0, 60.0]
    sls = [0.5, 1.0, 1.5, 2.0, 2.5]
    # minute index is minutes-since-09:30 ET: 180=12:30, 300=14:30, 385=15:55
    time_stops = [None, 180, 300, 385]
    grid: List[ExitPolicy] = [SPARK_BASELINE]
    for pt in pts:
        for sl in sls:
            for ts in time_stops:
                ts_label = "eod" if ts is None else f"t{ts}"
                grid.append(
                    ExitPolicy(
                        name=f"pt{int(pt)}_sl{sl}_{ts_label}",
                        profit_target_pct=pt,
                        stop_loss_mult=sl,
                        time_stop_minute=ts,
                        min_hold_minutes=5,
                    )
                )
    return grid
