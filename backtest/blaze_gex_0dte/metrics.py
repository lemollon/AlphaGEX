"""Aggregate TradeOutcomes into per-setup summaries + GO/NO-GO verdict."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from backtest.joshua_replay.engine import TradeOutcome

@dataclass
class Summary:
    setup: str
    trades: int
    win_rate: float
    ev_per_contract: float
    total_pnl: float
    max_drawdown: float
    profit_factor: float
    pnl_by_year: Dict[int, float] = field(default_factory=dict)

def _pnl(oc: TradeOutcome) -> float:
    return (oc.realized_pct / 100.0) * oc.debit

def summarize(outcomes: List[TradeOutcome]) -> Dict[str, Summary]:
    by_setup: Dict[str, List[TradeOutcome]] = {}
    for oc in outcomes:
        by_setup.setdefault(oc.setup, []).append(oc)
    result: Dict[str, Summary] = {}
    for setup, ocs in by_setup.items():
        pnls = [_pnl(o) for o in ocs]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = sum(wins)
        gross_loss = -sum(losses)
        cum, peak, mdd = 0.0, 0.0, 0.0
        for p in pnls:
            cum += p
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        by_year: Dict[int, float] = {}
        for o, p in zip(ocs, pnls):
            by_year[o.trade_date.year] = by_year.get(o.trade_date.year, 0.0) + p
        result[setup] = Summary(
            setup=setup,
            trades=len(ocs),
            win_rate=(len(wins) / len(ocs)) if ocs else 0.0,
            ev_per_contract=(sum(pnls) / len(ocs)) if ocs else 0.0,
            total_pnl=sum(pnls),
            max_drawdown=mdd,
            profit_factor=(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            pnl_by_year=by_year,
        )
    return result

def go_no_go(s: Summary, *, min_profit_factor: float = 1.2) -> str:
    if s.ev_per_contract <= 0:
        return "NO-GO"
    if s.profit_factor < min_profit_factor:
        return "NO-GO"
    if s.pnl_by_year and any(v <= 0 for v in s.pnl_by_year.values()):
        return "NO-GO"
    return "GO"
