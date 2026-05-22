from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.adapters.spark import SparkRepresentativeIC
from backtest.ember.data import build_day_chains_from_range, query_range_rows
from backtest.ember.engine import apply_policy, price_path
from backtest.ember.fills import commission
from backtest.ember.policy import ExitPolicy
from backtest.ember.report import summarize
from backtest.ember.walkforward import DEFAULT_TRAIN_END, split


@dataclass
class DayPath:
    """One day's cacheable backtest unit: the entry economics + the minute P&L path.

    Exit policies are evaluated against `path` without re-touching the DB."""
    trade_date: dt.date
    entry_minute: int
    entry_credit: float
    contracts: int
    commission_dollars: float
    is_oos: bool
    path: List[Tuple[int, float]]   # [(minute, gross_pnl_dollars)]

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "entry_minute": self.entry_minute,
            "entry_credit": self.entry_credit,
            "contracts": self.contracts,
            "commission_dollars": self.commission_dollars,
            "is_oos": self.is_oos,
            "path": [[int(m), float(g)] for m, g in self.path],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DayPath":
        return cls(
            trade_date=dt.date.fromisoformat(d["trade_date"]),
            entry_minute=int(d["entry_minute"]),
            entry_credit=float(d["entry_credit"]),
            contracts=int(d["contracts"]),
            commission_dollars=float(d["commission_dollars"]),
            is_oos=bool(d["is_oos"]),
            path=[(int(m), float(g)) for m, g in d["path"]],
        )


def build_paths(
    start: dt.date,
    end: dt.date,
    *,
    entry_minute: int,
    short_delta: float,
    wing_width: float,
    fill: str,
    db_url: str,
    slippage: float = 0.03,
    train_end: dt.date = DEFAULT_TRAIN_END,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[DayPath]:
    """Load the range in one query, build one IC per eligible day, compute its minute
    P&L path. The expensive, cache-once step. `progress_cb(done, total)` is called per day."""
    rows = query_range_rows(start, end, db_url)
    chains = build_day_chains_from_range(rows)
    dates = sorted(chains.keys())
    _, oos_dates = split(dates, train_end)
    oos_set = set(oos_dates)

    cfg = AdapterConfig(entry_minute=entry_minute, short_delta=short_delta, wing_width=wing_width)
    adapter = SparkRepresentativeIC()

    out: List[DayPath] = []
    total = len(dates)
    for i, d in enumerate(dates):
        chain = chains[d]
        pos = adapter.build_entry(chain, cfg)
        if pos is not None:
            path = price_path(chain, pos, fill, slippage)
            if path:
                out.append(DayPath(
                    trade_date=d,
                    entry_minute=pos.entry_minute,
                    entry_credit=pos.entry_credit,
                    contracts=pos.contracts,
                    commission_dollars=commission(pos.legs, pos.contracts),
                    is_oos=(d in oos_set),
                    path=path,
                ))
        if progress_cb is not None:
            progress_cb(i + 1, total)
    return out


def _trade_for(dp: DayPath, policy: ExitPolicy):
    return apply_policy(
        dp.path,
        trade_date=dp.trade_date,
        entry_minute=dp.entry_minute,
        entry_credit=dp.entry_credit,
        contracts=dp.contracts,
        commission_dollars=dp.commission_dollars,
        policy=policy,
    )


def evaluate_grid(paths: List[DayPath], grid: List[ExitPolicy]) -> List[dict]:
    """Fast: for each policy, summarize in-sample and OOS results over cached paths."""
    rows: List[dict] = []
    for policy in grid:
        in_trades, oos_trades = [], []
        for dp in paths:
            tr = _trade_for(dp, policy)
            if tr is None:
                continue
            (oos_trades if dp.is_oos else in_trades).append(tr)
        rows.append({
            "policy": policy.name,
            "in_sample": summarize(in_trades),
            "oos": summarize(oos_trades),
        })
    return rows


def evaluate_policy(paths: List[DayPath], policy: ExitPolicy) -> dict:
    """Fast: full detail for one policy — in-sample/OOS summaries, per-trade rows,
    and a date-sorted cumulative equity curve."""
    tagged = []  # (is_oos, TradeResult)
    for dp in paths:
        tr = _trade_for(dp, policy)
        if tr is None:
            continue
        tagged.append((dp.is_oos, tr))
    tagged.sort(key=lambda x: x[1].trade_date)

    in_trades = [t for oos, t in tagged if not oos]
    oos_trades = [t for oos, t in tagged if oos]

    equity = []
    cum = 0.0
    for is_oos, t in tagged:
        cum += t.pnl
        equity.append({
            "date": t.trade_date.isoformat(),
            "pnl": round(t.pnl, 2),
            "cum_pnl": round(cum, 2),
            "is_oos": is_oos,
        })

    trades = [{
        "trade_date": t.trade_date.isoformat(),
        "entry_minute": t.entry_minute,
        "exit_minute": t.exit_minute,
        "exit_reason": t.exit_reason,
        "entry_credit": round(t.entry_credit, 2),
        "exit_cost": round(t.exit_cost, 2),
        "pnl": round(t.pnl, 2),
        "max_favorable": round(t.max_favorable, 2),
        "max_adverse": round(t.max_adverse, 2),
        "is_oos": is_oos,
    } for is_oos, t in tagged]

    return {
        "policy": policy.name,
        "in_sample": summarize(in_trades),
        "oos": summarize(oos_trades),
        "equity_curve": equity,
        "trades": trades,
    }
