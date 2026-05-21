# backtest/ember/cli.py
from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import Dict, List, Tuple

from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.adapters.spark import SparkRepresentativeIC
from backtest.ember.data import list_trade_dates, load_day
from backtest.ember.engine import TradeResult, evaluate_exit
from backtest.ember.fills import FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP
from backtest.ember.policy import ExitPolicy, default_grid
from backtest.ember.report import (summarize, write_report_md, write_summary_csv, write_trades_csv)
from backtest.ember.walkforward import split


def run_policies_for_day(day, adapter, cfg: AdapterConfig, grid: List[ExitPolicy], fill: str) -> Dict[str, TradeResult]:
    """Build the day's entry once, evaluate every policy against it."""
    out: Dict[str, TradeResult] = {}
    pos = adapter.build_entry(day, cfg)
    if pos is None:
        return out
    for policy in grid:
        tr = evaluate_exit(day, pos, policy, fill=fill)
        if tr is not None:
            out[policy.name] = tr
    return out


def pick_best(results: Dict[str, List[TradeResult]]) -> Tuple[str, dict]:
    """Choose the policy with the highest EV/contract, tie-broken by Sharpe."""
    best_name, best_summary, best_key = None, None, (float("-inf"), float("-inf"))
    for name, trades in results.items():
        s = summarize(trades)
        key = (s["ev_per_contract"], s["sharpe"])
        if key > best_key:
            best_key, best_name, best_summary = key, name, dict(s, policy=name)
    return best_name, best_summary


def run(start: dt.date, end: dt.date, fill: str, out_dir: str, db_url: str,
        entry_minute: int, short_delta: float, wing_width: float) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    adapter = SparkRepresentativeIC()
    cfg = AdapterConfig(entry_minute=entry_minute, short_delta=short_delta, wing_width=wing_width)
    grid = default_grid()

    dates = list_trade_dates(db_url, start, end)
    train_dates, oos_dates = split(dates)

    train_results: Dict[str, List[TradeResult]] = {}
    oos_results: Dict[str, List[TradeResult]] = {}
    all_trades: List[TradeResult] = []

    for d in dates:
        day = load_day(d, db_url)
        per_day = run_policies_for_day(day, adapter, cfg, grid, fill=fill)
        bucket = train_results if d in set(train_dates) else oos_results
        for name, tr in per_day.items():
            bucket.setdefault(name, []).append(tr)
            all_trades.append(tr)

    best_name, best_summary = pick_best(train_results)
    baseline_summary = dict(summarize(train_results.get("spark_live", [])), policy="spark_live")
    oos_best_summary = dict(summarize(oos_results.get(best_name, [])), policy=best_name)

    # artifacts
    write_trades_csv(all_trades, os.path.join(out_dir, "trades.csv"))
    summary_rows = [dict(summarize(v), policy=k) for k, v in sorted(train_results.items())]
    write_summary_csv(summary_rows, os.path.join(out_dir, "summary.csv"))
    write_report_md(
        os.path.join(out_dir, "report.md"),
        fill=fill, best=best_summary, baseline=baseline_summary,
        oos_best=oos_best_summary, n_days=len(dates),
    )
    return {"best": best_summary, "baseline": baseline_summary, "oos_best": oos_best_summary,
            "n_days": len(dates), "out_dir": out_dir}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m backtest.ember", description="EMBER Phase 1 SPARK exit study")
    p.add_argument("--start", default="2023-01-03", type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--end", default="2025-12-05", type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--fill", default=FILL_ASK_CROSS, choices=[FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP])
    p.add_argument("--out", default="backtest/ember/out/latest")
    p.add_argument("--entry-minute", default=30, type=int, help="minutes since 09:30 ET (default 30 = 10:00 ET)")
    p.add_argument("--short-delta", default=0.16, type=float)
    p.add_argument("--wing-width", default=5.0, type=float)
    args = p.parse_args(argv)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    res = run(args.start, args.end, args.fill, args.out, db_url,
              args.entry_minute, args.short_delta, args.wing_width)
    b, base, oos = res["best"], res["baseline"], res["oos_best"]
    print(f"Days: {res['n_days']}  ->  artifacts in {res['out_dir']}")
    print(f"BEST  (in-sample): {b['policy']:>18}  EV/ct ${b['ev_per_contract']:>8}  WR {b['win_rate']}%  total ${b['total_pnl']}")
    print(f"SPARK baseline   : {base['policy']:>18}  EV/ct ${base['ev_per_contract']:>8}  WR {base['win_rate']}%  total ${base['total_pnl']}")
    print(f"BEST  (OOS 2025) : {oos['policy']:>18}  EV/ct ${oos['ev_per_contract']:>8}  WR {oos['win_rate']}%  total ${oos['total_pnl']}")
    return 0
