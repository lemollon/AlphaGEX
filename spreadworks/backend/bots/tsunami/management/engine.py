"""Management engine -- evaluates triggers in priority order, returns first action.

Per master spec section 4: 8 triggers (T1..T8) on every open position.
The engine runs them in this order:

    1. T7  Thursday 3pm ET mandatory close   (hard temporal cutoff)
    2. T6  Material news flag                (manual override)
    3. T5  Short strike breach + 3 DTE       (risk: ITM near expiry)
    4. T4  Total loss > 80%% of defined max   (risk: drawdown cap)
    5. T8  Adverse underlying GEX flip       (risk: regime change)
    6. T2  Call leg 5x of cost               (profit -- closes everything)
    7. T1  Call leg 3x of cost               (profit -- close call only)
    8. T3  Put spread at 50%% of max profit   (profit -- close spread only)

Rationale: hard cutoffs and risk triggers preempt profit-taking, so a
position that hits both T4 and T1 in the same cycle gets closed
entirely (T4) instead of being partially trimmed (T1). T2 precedes
T1 because T2 closes everything; if call has gone straight to >=5x
between cycles we don't want to leave the spread open.

NO ROLLING. Per spec section 4 -- engine never emits a roll action.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from .state import ManagementAction, Position
from .triggers import (
    t1_call_3x,
    t2_call_5x,
    t3_spread_50pct,
    t4_total_loss_80pct,
    t5_short_strike_breach_3dte,
    t6_material_news_flag,
    t7_thursday_3pm_close,
    t8_underlying_gex_flip,
)


def evaluate_all(
    position: Position,
    *,
    now: Optional[datetime] = None,
    is_flagged: Optional[Callable[[str], bool]] = None,
) -> Optional[ManagementAction]:
    """Run triggers in priority order; return first firing action or None.

    Args:
        position: open position to evaluate
        now: tz-aware clock (default: datetime.now in T5/T7 internals)
        is_flagged: callable for T6 news-flag lookup (default: Postgres store)
    """
    # 1. T7 -- mandatory Thursday 3pm ET close (hardest cutoff)
    a = t7_thursday_3pm_close.evaluate(position, now=now)
    if a is not None:
        return a

    # 2. T6 -- material-news manual override
    a = t6_material_news_flag.evaluate(position, is_flagged=is_flagged)
    if a is not None:
        return a

    # 3. T5 -- short strike breach + <= 3 DTE
    a = t5_short_strike_breach_3dte.evaluate(position, now=now)
    if a is not None:
        return a

    # 4. T4 -- > 80%% of defined max loss
    a = t4_total_loss_80pct.evaluate(position)
    if a is not None:
        return a

    # 5. T8 -- adverse underlying GEX regime flip
    a = t8_underlying_gex_flip.evaluate(position)
    if a is not None:
        return a

    # 6. T2 -- call 5x (close everything; preempts T1)
    a = t2_call_5x.evaluate(position)
    if a is not None:
        return a

    # 7. T1 -- call 3x (close call leg only)
    a = t1_call_3x.evaluate(position)
    if a is not None:
        return a

    # 8. T3 -- put spread at 50%% PT (close spread only)
    a = t3_spread_50pct.evaluate(position)
    if a is not None:
        return a

    return None
