"""Markdown report writer + CSV dump for the touch_pin harness."""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import BinSummary


def write_trades_csv(trades: List[TradeRow], path: Path) -> None:
    if not trades:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(trades[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in trades:
            row = asdict(t)
            for k, v in row.items():
                if isinstance(v, dt.date):
                    row[k] = v.isoformat()
            w.writerow(row)


def write_markdown_report(
    trades: List[TradeRow],
    bins: List[BinSummary],
    path: Path,
    start: dt.date,
    end: dt.date,
    sensitivity_results: Optional[dict] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(trades)
    pnls = [t.pnl_net for t in trades]
    overall_mean = sum(pnls) / n if n else 0.0
    overall_wr = sum(1 for p in pnls if p > 0) / n if n else 0.0

    lines: List[str] = []
    lines.append("# Touch-Pin (Phase 1) Backtest Report")
    lines.append("")
    lines.append(f"**Period:** {start.isoformat()} to {end.isoformat()}")
    lines.append(f"**Total trades:** {n}")
    lines.append(f"**Overall WR:** {overall_wr:.1%}")
    lines.append(f"**Overall mean PnL/trade:** ${overall_mean:.2f}")
    if n:
        lines.append(f"**Total PnL:** ${sum(pnls):.0f}")
    lines.append("")
    lines.append("## Bin Summary (top 30 by n)")
    lines.append("")
    lines.append("| Side | Magnet | VIX | Dist | Regime | n | WR | Mean | Median | Std | Sharpe | Touch | Imp1 | Imp2 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for b in sorted(bins, key=lambda x: -x.n)[:30]:
        lines.append(
            f"| {b.side} | {b.magnet_imb_bucket} | {b.vix_bucket} | {b.distance_bucket} | "
            f"{b.regime_label} | {b.n} | {b.win_rate:.1%} | ${b.mean_pnl:.2f} | "
            f"${b.median_pnl:.2f} | ${b.std_pnl:.2f} | {b.sharpe_per_trade:.2f} | "
            f"{b.mean_touched:.1%} | {b.mean_implied_method1:.2%} | {b.mean_implied_method2:.2%} |"
        )
    lines.append("")
    lines.append("## GO Criteria (per spec)")
    lines.append("")
    lines.append("Bin qualifies if: n >= 30 train, n >= 15 OOS, mean_pnl >= +$5, sharpe >= 0.3, OOS sign+magnitude check.")
    lines.append("")
    qualifying = [b for b in bins if b.n >= 30 and b.mean_pnl >= 5.0 and b.sharpe_per_trade >= 0.3]
    lines.append(f"### In-sample qualifying bins (OOS check separate): {len(qualifying)}")
    for b in qualifying:
        lines.append(
            f"- {b.side} | mag={b.magnet_imb_bucket} | vix={b.vix_bucket} | "
            f"dist={b.distance_bucket} | reg={b.regime_label}: "
            f"n={b.n} WR={b.win_rate:.1%} mean=${b.mean_pnl:.2f} sharpe={b.sharpe_per_trade:.2f}"
        )
    lines.append("")

    if sensitivity_results:
        lines.append("## Sensitivity Battery")
        lines.append("")
        lines.append("| Variant | n | WR | Mean PnL |")
        lines.append("|---|---|---|---|")
        for label, res in sensitivity_results.items():
            lines.append(f"| {label} | {res['n']} | {res['wr']:.1%} | ${res['mean']:.2f} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
