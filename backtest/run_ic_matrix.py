#!/usr/bin/env python3
"""
Iron Condor Backtest Matrix Runner

Runs the monthly_iron_condor.py backtest across all combinations of:
  - DTE modes: 0DTE, 1DTE, 2DTE, 3DTE, Monthly (30-45 DTE)
  - Capital utilization: 20%, 30%, 50%, 70%
  - Capital levels: $5,000 and $100,000

Total: 5 DTE modes × 4 utilizations × 2 capital levels = 40 backtests

Results are saved to backtest/results/ and a summary CSV is generated.

Usage:
    python backtest/run_ic_matrix.py
    python backtest/run_ic_matrix.py --capital 100000      # Single capital level
    python backtest/run_ic_matrix.py --dte 0               # Single DTE only
    python backtest/run_ic_matrix.py --utilization 50      # Single utilization only
"""

import os
import sys
import json
import csv
import subprocess
import time
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BACKTEST_SCRIPT = PROJECT_ROOT / "backtest" / "monthly_iron_condor.py"
RESULTS_DIR = PROJECT_ROOT / "backtest" / "results"

# Test matrix
DTE_MODES = [
    {"dte_mode": "short", "short_dte": 0, "label": "0DTE"},
    {"dte_mode": "short", "short_dte": 1, "label": "1DTE"},
    {"dte_mode": "short", "short_dte": 2, "label": "2DTE"},
    {"dte_mode": "short", "short_dte": 3, "label": "3DTE"},
    {"dte_mode": "monthly", "short_dte": 0, "label": "Monthly"},
]

UTILIZATIONS = [20, 30, 50, 70]
CAPITALS = [5_000, 100_000]


def run_single_backtest(dte_config: dict, utilization: int, capital: float,
                         ticker: str = "SPX", start: str = "2021-01-01",
                         end: str = "2025-12-31") -> dict:
    """Run a single backtest and return parsed results."""

    label = dte_config["label"]
    capital_label = f"{int(capital/1000)}k"
    print(f"\n{'='*60}")
    print(f"  Running: {label} | {utilization}% util | ${capital:,.0f} capital")
    print(f"{'='*60}")

    cmd = [
        sys.executable, str(BACKTEST_SCRIPT),
        "--ticker", ticker,
        "--start", start,
        "--end", end,
        "--capital", str(capital),
        "--max-utilization", str(utilization),
        "--dte-mode", dte_config["dte_mode"],
        "--short-dte", str(dte_config["short_dte"]),
        "--dynamic-sizing",
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(PROJECT_ROOT)
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"  FAILED ({elapsed:.1f}s): {result.stderr[:200]}")
            return {
                "dte_mode": label,
                "utilization_pct": utilization,
                "capital": capital,
                "status": "FAILED",
                "error": result.stderr[:200],
            }

        print(f"  Completed in {elapsed:.1f}s")

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 600s")
        return {
            "dte_mode": label,
            "utilization_pct": utilization,
            "capital": capital,
            "status": "TIMEOUT",
        }

    # Parse results JSON
    dte_file_label = f"{dte_config['short_dte']}dte" if dte_config["dte_mode"] == "short" else "monthly"
    util_label = f"util{utilization}"
    results_file = RESULTS_DIR / f"{ticker}_{dte_file_label}_ic_results_{capital_label}_{util_label}_{start}_{end}.json"

    if results_file.exists():
        with open(results_file) as f:
            data = json.load(f)

        s = data.get("summary", {})
        r = data.get("risk", {})
        col = data.get("collateral", {})

        return {
            "dte_mode": label,
            "utilization_pct": utilization,
            "capital": capital,
            "status": "OK",
            "total_trades": s.get("total_trades", 0),
            "win_rate": s.get("win_rate", 0),
            "total_pnl": s.get("total_pnl", 0),
            "total_return_pct": s.get("total_return_pct", 0),
            "avg_pnl_per_trade": s.get("avg_pnl_per_trade", 0),
            "profit_factor": s.get("profit_factor", 0),
            "max_drawdown_pct": r.get("max_drawdown_pct", 0),
            "sharpe_ratio": r.get("sharpe_ratio", 0),
            "sortino_ratio": r.get("sortino_ratio", 0),
            "final_equity": s.get("final_equity", 0),
            "trades_skipped": col.get("trades_skipped_no_capital", 0),
            "peak_concurrent": col.get("peak_concurrent_positions", 0),
            "peak_margin_pct": col.get("peak_margin_pct_of_capital", 0),
            "avg_contracts": col.get("avg_contracts_per_trade", 0),
            "elapsed_s": round(elapsed, 1),
        }
    else:
        print(f"  WARNING: Results file not found: {results_file}")
        return {
            "dte_mode": label,
            "utilization_pct": utilization,
            "capital": capital,
            "status": "NO_RESULTS",
        }


def run_matrix(dte_filter=None, util_filter=None, capital_filter=None,
               ticker="SPX", start="2021-01-01", end="2025-12-31"):
    """Run the full test matrix."""

    dtes = DTE_MODES if dte_filter is None else [d for d in DTE_MODES if d["short_dte"] == dte_filter or (dte_filter == -1 and d["dte_mode"] == "monthly")]
    utils = UTILIZATIONS if util_filter is None else [util_filter]
    caps = CAPITALS if capital_filter is None else [capital_filter]

    total = len(dtes) * len(utils) * len(caps)
    print(f"\nIRON CONDOR BACKTEST MATRIX")
    print(f"{'='*60}")
    print(f"DTE modes:     {', '.join(d['label'] for d in dtes)}")
    print(f"Utilizations:  {', '.join(str(u)+'%' for u in utils)}")
    print(f"Capitals:      {', '.join('$'+f'{c:,.0f}' for c in caps)}")
    print(f"Total runs:    {total}")
    print(f"{'='*60}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    completed = 0

    for dte_config in dtes:
        for util in utils:
            for cap in caps:
                completed += 1
                print(f"\n[{completed}/{total}]", end="")
                result = run_single_backtest(dte_config, util, cap, ticker, start, end)
                all_results.append(result)

    # Write summary CSV
    summary_file = RESULTS_DIR / f"ic_matrix_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if all_results:
        fieldnames = list(all_results[0].keys())
        with open(summary_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\n\nSummary CSV: {summary_file}")

    # Print summary table
    print_summary_table(all_results)

    return all_results


def print_summary_table(results):
    """Print a formatted summary table."""
    ok_results = [r for r in results if r.get("status") == "OK"]
    if not ok_results:
        print("\nNo successful results to display.")
        return

    print(f"\n\n{'='*120}")
    print(f"  IRON CONDOR BACKTEST MATRIX SUMMARY")
    print(f"{'='*120}")
    print(f"  {'DTE':<10} {'Util%':>6} {'Capital':>10} {'Trades':>7} {'WR%':>6} {'Total P&L':>12} {'Return%':>8} "
          f"{'PF':>6} {'MaxDD%':>7} {'Sharpe':>7} {'Skipped':>8} {'PeakPos':>8} {'AvgCtx':>7}")
    print(f"  {'─'*116}")

    for r in ok_results:
        print(f"  {r['dte_mode']:<10} {r['utilization_pct']:>5}% ${r['capital']:>9,.0f} "
              f"{r['total_trades']:>7} {r['win_rate']:>5.1f}% ${r['total_pnl']:>+11,.2f} "
              f"{r['total_return_pct']:>+7.1f}% {r['profit_factor']:>5.2f} "
              f"{r['max_drawdown_pct']:>6.1f}% {r['sharpe_ratio']:>6.2f} "
              f"{r['trades_skipped']:>8} {r['peak_concurrent']:>8} {r['avg_contracts']:>6.1f}")

    failed = [r for r in results if r.get("status") != "OK"]
    if failed:
        print(f"\n  FAILED/SKIPPED: {len(failed)} runs")
        for r in failed:
            print(f"    {r['dte_mode']} | {r['utilization_pct']}% | ${r['capital']:,.0f} → {r['status']}: {r.get('error', '')[:80]}")

    print(f"{'='*120}\n")


def main():
    parser = argparse.ArgumentParser(description="Run IC backtest matrix")
    parser.add_argument("--dte", type=int, default=None, choices=[0, 1, 2, 3, -1],
                        help="Filter: single DTE (0-3) or -1 for monthly only")
    parser.add_argument("--utilization", type=int, default=None, choices=[20, 30, 50, 70],
                        help="Filter: single utilization level")
    parser.add_argument("--capital", type=float, default=None,
                        help="Filter: single capital level (e.g. 5000 or 100000)")
    parser.add_argument("--ticker", default="SPX", help="Underlying (default: SPX)")
    parser.add_argument("--start", default="2021-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    args = parser.parse_args()

    run_matrix(
        dte_filter=args.dte,
        util_filter=args.utilization,
        capital_filter=args.capital,
        ticker=args.ticker,
        start=args.start,
        end=args.end,
    )


if __name__ == "__main__":
    main()
