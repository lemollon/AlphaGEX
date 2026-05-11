"""Bucket trades by composite_z and direction."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List

from backtest.skew_signal.engine import TradeRow


@dataclass(frozen=True)
class BinSummary:
    action: str
    composite_z_bucket: str
    n: int
    n_winners: int
    win_rate: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float
    sharpe_per_trade: float
    mean_realized_pct: float


def _z_bucket(z: float) -> str:
    az = abs(z)
    if az < 1.5: return "<1.5"
    if az < 3.0: return "1.5-3.0"
    if az < 6.0: return "3.0-6.0"
    return ">6.0"


def bin_trades(trades: List[TradeRow]) -> List[BinSummary]:
    groups: dict = {}
    for t in trades:
        key = (t.action, _z_bucket(t.composite_z))
        groups.setdefault(key, []).append(t)
    out: List[BinSummary] = []
    for (action, zb), items in groups.items():
        pnls = [t.pnl_net for t in items]
        n = len(pnls)
        winners = sum(1 for p in pnls if p > 0)
        mean_pnl = sum(pnls) / n if n else 0.0
        med = statistics.median(pnls) if n else 0.0
        std = statistics.pstdev(pnls) if n > 1 else 0.0
        sharpe = mean_pnl / std if std > 1e-9 else 0.0
        mean_real = sum(t.realized_pct for t in items) / n if n else 0.0
        out.append(BinSummary(
            action=action, composite_z_bucket=zb,
            n=n, n_winners=winners, win_rate=winners / n if n else 0.0,
            mean_pnl=mean_pnl, median_pnl=med, std_pnl=std,
            sharpe_per_trade=sharpe, mean_realized_pct=mean_real,
        ))
    out.sort(key=lambda b: (b.action, b.composite_z_bucket))
    return out
