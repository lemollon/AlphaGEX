# backtest/ember/engine.py
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Tuple

from backtest.ember.fills import CONTRACT_MULTIPLIER, commission, signed_cashflow
from backtest.ember.models import DayChain, Position
from backtest.ember.policy import ExitPolicy


@dataclass
class TradeResult:
    trade_date: dt.date
    policy: str
    entry_minute: int
    exit_minute: int
    exit_reason: str            # "PT" | "SL" | "TRAIL" | "TIME" | "EOD"
    entry_credit: float         # price units, per spread
    exit_cost: float            # price units paid to close, per spread (>=0 typical)
    pnl: float                  # dollars, net of commission, for position.contracts
    max_favorable: float        # best gross dollars seen
    max_adverse: float          # worst gross dollars seen


def _all_legs_quotable(chain: DayChain, position: Position, minute: int) -> bool:
    for leg in position.legs:
        if chain.quote(minute, leg.strike, leg.right) is None:
            return False
    return True


def price_path(
    chain: DayChain,
    position: Position,
    fill: str,
    slippage: float = 0.03,
) -> List[Tuple[int, float]]:
    """[(minute, gross_pnl_dollars)] for each minute >= entry where all legs quote.

    gross_pnl = (open_cashflow + close_cashflow_now) * multiplier * contracts.
    open_cashflow is fixed at entry (= +entry_credit by construction)."""
    open_cf = position.entry_credit
    out: List[Tuple[int, float]] = []
    for minute in chain.sorted_minutes:
        if minute < position.entry_minute:
            continue
        if not _all_legs_quotable(chain, position, minute):
            continue
        quotes = chain.minutes[minute].quotes
        close_cf = signed_cashflow(position.legs, quotes, action="close", fill=fill, slippage=slippage)
        gross = (open_cf + close_cf) * CONTRACT_MULTIPLIER * position.contracts
        out.append((minute, gross))
    return out


def evaluate_exit(
    chain: DayChain,
    position: Position,
    policy: ExitPolicy,
    fill: str,
    slippage: float = 0.03,
) -> Optional[TradeResult]:
    """Replay the position under one policy. Returns None if it never quotes."""
    path = price_path(chain, position, fill, slippage)
    if not path:
        return None

    credit_dollars = position.entry_credit * CONTRACT_MULTIPLIER * position.contracts
    pt_target = (policy.profit_target_pct / 100.0) * credit_dollars if policy.profit_target_pct else None
    sl_thresh = (policy.stop_loss_mult * credit_dollars) if policy.stop_loss_mult else None
    trail_arm = (policy.trail_activation_pct / 100.0) * credit_dollars if policy.trail_activation_pct else None
    trail_give = (policy.trail_giveback_pct / 100.0) * credit_dollars if policy.trail_giveback_pct else None

    peak = float("-inf")
    max_fav = float("-inf")
    max_adv = float("inf")
    last_minute, last_gross = path[-1]

    chosen_minute: Optional[int] = None
    chosen_reason: Optional[str] = None
    chosen_gross: Optional[float] = None

    for minute, gross in path:
        max_fav = max(max_fav, gross)
        max_adv = min(max_adv, gross)
        peak = max(peak, gross)
        if minute - position.entry_minute < policy.min_hold_minutes:
            continue
        # Precedence: SL -> PT -> TRAIL -> TIME
        if sl_thresh is not None and gross <= -sl_thresh:
            chosen_minute, chosen_reason, chosen_gross = minute, "SL", gross
            break
        if pt_target is not None and gross >= pt_target:
            chosen_minute, chosen_reason, chosen_gross = minute, "PT", gross
            break
        if trail_arm is not None and trail_give is not None and peak >= trail_arm and gross <= peak - trail_give:
            chosen_minute, chosen_reason, chosen_gross = minute, "TRAIL", gross
            break
        if policy.time_stop_minute is not None and minute >= policy.time_stop_minute:
            chosen_minute, chosen_reason, chosen_gross = minute, "TIME", gross
            break

    if chosen_minute is None:
        chosen_minute, chosen_reason, chosen_gross = last_minute, "EOD", last_gross

    comm = commission(position.legs, position.contracts)
    net_pnl = chosen_gross - comm
    # exit_cost (price units, per spread) implied by gross: gross = (credit - exit_cost)*mult*contracts
    exit_cost = position.entry_credit - chosen_gross / (CONTRACT_MULTIPLIER * position.contracts)

    return TradeResult(
        trade_date=chain.trade_date,
        policy=policy.name,
        entry_minute=position.entry_minute,
        exit_minute=chosen_minute,
        exit_reason=chosen_reason,
        entry_credit=position.entry_credit,
        exit_cost=exit_cost,
        pnl=net_pnl,
        max_favorable=max_fav,
        max_adverse=max_adv,
    )
