"""Bucket trades by (side, magnet_imb, vix, distance, regime) and aggregate."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List

from backtest.touch_pin.engine import TradeRow


@dataclass(frozen=True)
class BinSummary:
    side: str
    magnet_imb_bucket: str
    vix_bucket: str
    distance_bucket: str
    regime_label: str
    n: int
    n_winners: int
    win_rate: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float
    sharpe_per_trade: float
    mean_touched: float
    mean_implied_method1: float
    mean_implied_method2: float


def bin_trades(trades: List[TradeRow]) -> List[BinSummary]:
    groups: dict = {}
    for t in trades:
        key = (
            t.side,
            _magnet_bucket(t.magnet_imbalance),
            _vix_bucket(t.vix_close_prior or 0.0),
            _distance_bucket(t.distance_pct),
            t.regime_label or "unlabeled",
        )
        groups.setdefault(key, []).append(t)

    out: List[BinSummary] = []
    for key, items in groups.items():
        side, mb, vb, db, rb = key
        pnls = [t.pnl_net for t in items]
        n = len(pnls)
        winners = sum(1 for p in pnls if p > 0)
        mean_pnl = sum(pnls) / n if n else 0.0
        median_pnl = statistics.median(pnls) if n else 0.0
        std_pnl = statistics.pstdev(pnls) if n > 1 else 0.0
        sharpe = (mean_pnl / std_pnl) if std_pnl > 1e-9 else 0.0
        mean_touched = sum(t.touched_during_day for t in items) / n if n else 0.0
        m1 = sum(t.implied_method1 for t in items) / n if n else 0.0
        m2 = sum(t.implied_method2 for t in items) / n if n else 0.0
        out.append(BinSummary(
            side=side, magnet_imb_bucket=mb, vix_bucket=vb,
            distance_bucket=db, regime_label=rb,
            n=n, n_winners=winners, win_rate=winners / n if n else 0.0,
            mean_pnl=mean_pnl, median_pnl=median_pnl, std_pnl=std_pnl,
            sharpe_per_trade=sharpe, mean_touched=mean_touched,
            mean_implied_method1=m1, mean_implied_method2=m2,
        ))
    out.sort(key=lambda b: (b.side, b.magnet_imb_bucket, b.vix_bucket, b.distance_bucket, b.regime_label))
    return out


def _magnet_bucket(x: float) -> str:
    if x < 1.2: return "<1.2"
    if x < 1.5: return "1.2-1.5"
    if x < 2.0: return "1.5-2.0"
    return ">2.0"


def _vix_bucket(x: float) -> str:
    if x < 15: return "<15"
    if x < 20: return "15-20"
    if x < 30: return "20-30"
    return ">30"


def _distance_bucket(pct: float) -> str:
    if pct < 0.3: return "<0.3%"
    if pct < 0.6: return "0.3-0.6%"
    return ">0.6%"
