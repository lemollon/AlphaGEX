"""Scorecard CSV/JSON writers for BacktestResult."""
import csv
import dataclasses
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev

from backtest.directional_1dte.engine import BacktestResult


VIX_BUCKETS = [
    ("low_lt_15", lambda v: v < 15),
    ("normal_15_22", lambda v: 15 <= v < 22),
    ("elevated_22_28", lambda v: 22 <= v < 28),
    ("high_gte_28", lambda v: v >= 28),
]


def _ann_sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mu = mean(daily_returns)
    sd = pstdev(daily_returns)
    if sd == 0:
        return 0.0
    return (mu / sd) * math.sqrt(252)


def _max_drawdown(equity_series: list[float]) -> float:
    if not equity_series:
        return 0.0
    peak = equity_series[0]
    max_dd = 0.0
    for v in equity_series:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def summary_stats(result: BacktestResult) -> dict:
    trades = result.trades
    n = len(trades)
    pnls = [t.realized_pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    equity_vals = [result.starting_capital] + [ep.equity for ep in result.equity]
    daily_pct = [p / result.starting_capital for p in pnls]

    pf_denom = abs(sum(losses)) if losses else 0
    profit_factor = (sum(wins) / pf_denom) if pf_denom > 0 else (float("inf") if wins else 0.0)

    return {
        "bot": result.bot,
        "start": str(result.start),
        "end": str(result.end),
        "starting_capital": result.starting_capital,
        "ending_equity": equity_vals[-1] if equity_vals else result.starting_capital,
        "total_trades": n,
        "total_skips": len(result.skips),
        "total_pnl": sum(pnls),
        "win_rate": (len(wins) / n) if n else 0.0,
        "avg_win": (mean(wins) if wins else 0.0),
        "avg_loss": (mean(losses) if losses else 0.0),
        "expectancy": (mean(pnls) if pnls else 0.0),
        "profit_factor": profit_factor,
        "annualized_sharpe": _ann_sharpe(daily_pct),
        "max_drawdown_pct": _max_drawdown(equity_vals),
    }


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _trade_to_row(t: 'Trade') -> dict:
    d = dataclasses.asdict(t)
    d["entry_date"] = str(d["entry_date"])
    d["expiration_date"] = str(d["expiration_date"])
    return d


def write_results(result: BacktestResult, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = summary_stats(result)

    # 1. summary.json
    (out_dir / "summary.json").write_text(json.dumps(s, indent=2, default=str))

    # 2. trades.csv
    if result.trades:
        rows = [_trade_to_row(t) for t in result.trades]
        _write_csv(out_dir / "trades.csv", rows, list(rows[0].keys()))
    else:
        (out_dir / "trades.csv").write_text("")

    # 3. skips.csv
    skip_rows = [{"entry_date": str(s.entry_date), "reason": s.reason, "detail": s.detail}
                 for s in result.skips]
    _write_csv(out_dir / "skips.csv", skip_rows, ["entry_date", "reason", "detail"])

    # 4. equity_curve.csv
    eq_rows = [{"date": str(p.date), "equity": p.equity} for p in result.equity]
    _write_csv(out_dir / "equity_curve.csv", eq_rows, ["date", "equity"])

    # 5. by_year.csv
    by_year: dict = {}
    for t in result.trades:
        y = t.entry_date.year
        by_year.setdefault(y, []).append(t)
    yr_rows = [{
        "year": y,
        "trades": len(ts),
        "pnl": sum(t.realized_pnl for t in ts),
        "win_rate": sum(1 for t in ts if t.realized_pnl > 0) / len(ts),
    } for y, ts in sorted(by_year.items())]
    _write_csv(out_dir / "by_year.csv", yr_rows, ["year", "trades", "pnl", "win_rate"])

    # 6. by_vix_bucket.csv
    buckets: dict = {name: [] for name, _ in VIX_BUCKETS}
    for t in result.trades:
        for name, pred in VIX_BUCKETS:
            if pred(t.vix_at_entry):
                buckets[name].append(t)
                break
    vb_rows = [{
        "bucket": name,
        "trades": len(ts),
        "pnl": sum(t.realized_pnl for t in ts),
        "win_rate": (sum(1 for t in ts if t.realized_pnl > 0) / len(ts)) if ts else 0,
    } for name, ts in buckets.items()]
    _write_csv(out_dir / "by_vix_bucket.csv", vb_rows, ["bucket", "trades", "pnl", "win_rate"])

    # 7. by_direction.csv
    dirs: dict = {"BULLISH": [], "BEARISH": []}
    for t in result.trades:
        dirs[t.direction].append(t)
    dir_rows = [{
        "direction": k,
        "trades": len(v),
        "pnl": sum(t.realized_pnl for t in v),
        "win_rate": (sum(1 for t in v if t.realized_pnl > 0) / len(v)) if v else 0,
    } for k, v in dirs.items()]
    _write_csv(out_dir / "by_direction.csv", dir_rows, ["direction", "trades", "pnl", "win_rate"])

    # 8. top_trades.csv & worst_trades.csv
    top = sorted(result.trades, key=lambda t: t.realized_pnl, reverse=True)[:10]
    worst = sorted(result.trades, key=lambda t: t.realized_pnl)[:10]
    if top:
        _write_csv(out_dir / "top_trades.csv", [_trade_to_row(t) for t in top],
                   list(_trade_to_row(top[0]).keys()))
    else:
        (out_dir / "top_trades.csv").write_text("")
    if worst:
        _write_csv(out_dir / "worst_trades.csv", [_trade_to_row(t) for t in worst],
                   list(_trade_to_row(worst[0]).keys()))
    else:
        (out_dir / "worst_trades.csv").write_text("")

    # 9. run.json (reproducibility metadata)
    skip_counts: dict = {}
    for sk in result.skips:
        skip_counts[sk.reason] = skip_counts.get(sk.reason, 0) + 1
    (out_dir / "run.json").write_text(json.dumps({
        "bot": result.bot,
        "config": dataclasses.asdict(result.config),
        "window": [str(result.start), str(result.end)],
        "trades": len(result.trades),
        "skips_by_reason": skip_counts,
        "ending_equity": s["ending_equity"],
        "written_at": datetime.utcnow().isoformat() + "Z",
    }, indent=2, default=str))


def write_comparison(results: dict, out_dir: Path) -> None:
    """Write top-level comparison.json + comparison.md across multiple bots."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = {name: summary_stats(r) for name, r in results.items()}
    (out_dir / "comparison.json").write_text(json.dumps(summaries, indent=2, default=str))

    lines = ["# SOLOMON / GIDEON 1DTE Backtest Comparison\n"]
    fields = ["total_trades", "total_pnl", "win_rate", "avg_win", "avg_loss",
              "expectancy", "profit_factor", "annualized_sharpe", "max_drawdown_pct"]
    lines.append("| Metric | " + " | ".join(summaries.keys()) + " |")
    lines.append("|" + "---|" * (len(summaries) + 1))
    for f in fields:
        row = [f]
        for name in summaries:
            val = summaries[name].get(f, 0)
            if isinstance(val, float):
                row.append(f"{val:.4f}" if abs(val) < 100 else f"{val:.2f}")
            else:
                row.append(str(val))
        lines.append("| " + " | ".join(row) + " |")
    (out_dir / "comparison.md").write_text("\n".join(lines))
