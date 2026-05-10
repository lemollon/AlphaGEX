"""Markdown report writer + per-trade CSV dump."""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import List

from backtest.skew_signal.engine import TradeRow
from backtest.skew_signal.binning import BinSummary


def write_trades_csv(trades: List[TradeRow], path: Path) -> None:
    if not trades:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(trades[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            row = asdict(t)
            for k, v in row.items():
                if isinstance(v, dt.date):
                    row[k] = v.isoformat()
            w.writerow(row)


def write_markdown_report(
    trades: List[TradeRow], bins: List[BinSummary],
    path: Path, start: dt.date, end: dt.date,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(trades)
    pnls = [t.pnl_net for t in trades]
    overall_wr = sum(1 for p in pnls if p > 0) / n if n else 0.0
    overall_mean = sum(pnls) / n if n else 0.0

    lines = []
    lines.append("# Skew + Charm (Phase 2) Backtest Report")
    lines.append("")
    lines.append(f"**Period:** {start.isoformat()} to {end.isoformat()}")
    lines.append(f"**Total trades:** {n}")
    lines.append(f"**Overall WR:** {overall_wr:.1%}")
    lines.append(f"**Overall mean PnL/trade:** ${overall_mean:.2f}")
    if n:
        lines.append(f"**Total PnL:** ${sum(pnls):.0f}")
        bull = [t for t in trades if t.action == "BULL"]
        bear = [t for t in trades if t.action == "BEAR"]
        lines.append(f"**BULL:** n={len(bull)}, WR={(sum(1 for t in bull if t.pnl_net>0)/len(bull) if bull else 0):.1%}")
        lines.append(f"**BEAR:** n={len(bear)}, WR={(sum(1 for t in bear if t.pnl_net>0)/len(bear) if bear else 0):.1%}")
        timestop = sum(1 for t in trades if t.exit_reason == "EOD") / n
        lines.append(f"**Time-stop %:** {timestop:.1%}")
    lines.append("")
    lines.append("## Bin Summary (by composite z bucket)")
    lines.append("")
    lines.append("| Action | Z-bucket | n | WR | Mean | Median | Std | Sharpe | RealPct |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for b in bins:
        lines.append(
            f"| {b.action} | {b.composite_z_bucket} | {b.n} | {b.win_rate:.1%} | "
            f"${b.mean_pnl:.2f} | ${b.median_pnl:.2f} | ${b.std_pnl:.2f} | "
            f"{b.sharpe_per_trade:.2f} | {b.mean_realized_pct:.1f}% |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
