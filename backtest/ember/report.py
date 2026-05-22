# backtest/ember/report.py
from __future__ import annotations

import csv
import statistics
from dataclasses import asdict
from typing import Dict, List

from backtest.ember.engine import TradeResult


def summarize(trades: List[TradeResult]) -> Dict[str, float]:
    """Per-policy summary stats. Sharpe is per-trade (mean/std), not annualized."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "ev_per_contract": 0.0, "total_pnl": 0.0,
                "sharpe": 0.0, "max_drawdown": 0.0, "avg_hold_min": 0.0, "pct_eod": 0.0}
    pnls = [t.pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    mean = total / n
    std = statistics.pstdev(pnls) if n > 1 else 0.0
    sharpe = (mean / std) if std > 0 else 0.0
    # max drawdown of the cumulative equity curve (in dollars, positive number)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    avg_hold = sum(t.exit_minute - t.entry_minute for t in trades) / n
    pct_eod = 100.0 * sum(1 for t in trades if t.exit_reason == "EOD") / n
    return {
        "n": n,
        "win_rate": round(100.0 * wins / n, 2),
        "ev_per_contract": round(mean, 4),
        "total_pnl": round(total, 2),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 2),
        "avg_hold_min": round(avg_hold, 1),
        "pct_eod": round(pct_eod, 2),
    }


def write_trades_csv(trades: List[TradeResult], path: str) -> None:
    fields = list(asdict(trades[0]).keys()) if trades else [
        "trade_date", "policy", "entry_minute", "exit_minute", "exit_reason",
        "entry_credit", "exit_cost", "pnl", "max_favorable", "max_adverse",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow(asdict(t))


def write_summary_csv(rows: List[Dict], path: str) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_report_md(
    path: str,
    *,
    fill: str,
    best: Dict,
    baseline: Dict,
    oos_best: Dict,
    n_days: int,
) -> None:
    lines = [
        "# EMBER Phase 1 — SPARK 1DTE intraday exit study",
        "",
        f"- Trading days: {n_days}",
        f"- Headline fill model: `{fill}`",
        "",
        "## Best policy (in-sample)",
        f"- **{best.get('policy', '?')}** — EV/contract ${best.get('ev_per_contract', 0)}, "
        f"win rate {best.get('win_rate', 0)}%, total ${best.get('total_pnl', 0)}, "
        f"Sharpe {best.get('sharpe', 0)}, maxDD ${best.get('max_drawdown', 0)}",
        "",
        "## SPARK live baseline (PT 30 / SL 0.5x / EOD)",
        f"- EV/contract ${baseline.get('ev_per_contract', 0)}, win rate {baseline.get('win_rate', 0)}%, "
        f"total ${baseline.get('total_pnl', 0)}",
        "",
        "## Out-of-sample (2025) check of the chosen policy",
        f"- EV/contract ${oos_best.get('ev_per_contract', 0)}, win rate {oos_best.get('win_rate', 0)}%, "
        f"total ${oos_best.get('total_pnl', 0)}",
        "",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines))
