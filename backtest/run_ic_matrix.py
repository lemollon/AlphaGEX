#!/usr/bin/env python3
"""
Iron Condor Backtest Matrix Runner (Render Shell Friendly)

Runs monthly_iron_condor.py across all combinations of:
  - DTE modes: 0DTE, 1DTE, 2DTE, 3DTE, Weekly (5-7 DTE), Monthly (30-45 DTE)
  - Capital utilization: 20%, 30%, 50%, 70%
  - Capital + Risk-per-trade:
      $5k   @ 100% (forced — one SPX IC needs ~$2,500 margin)
      $100k @ 10%, 25%, 50%

Total: 6 DTE modes x 4 utilizations x 4 capital/risk combos = 96 backtests

OUTPUT: Prints a tab-separated table at the end that you can
        copy/paste directly into Google Sheets or Excel.

RELIABILITY:
  - Each run has a 10-min timeout (won't hang forever)
  - Failures are caught and reported (won't crash the whole matrix)
  - Progress printed after each run so you know it's alive
  - Final "ALL DONE" banner so you know when to copy/paste

Usage:
    python backtest/run_ic_matrix.py                       # Full 40-run matrix
    python backtest/run_ic_matrix.py --capital 100000      # Just $100k (20 runs)
    python backtest/run_ic_matrix.py --dte 0               # Just 0DTE (8 runs)
    python backtest/run_ic_matrix.py --utilization 50      # Just 50% util (10 runs)
    python backtest/run_ic_matrix.py --dte -1              # Just Monthly (8 runs)
"""

import gc
import os
import sys
import json
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
    {"dte_mode": "weekly", "short_dte": 0, "label": "Weekly", "weekly_dte_min": 5, "weekly_dte_max": 7},
    {"dte_mode": "monthly", "short_dte": 0, "label": "Monthly"},
]

UTILIZATIONS = [20, 30, 50, 70]

# (capital, risk_per_trade_pct)
# $5k must use 100% risk — a single SPX IC costs ~$2,500 margin
# $100k tests 10%, 25%, 50% risk per trade
CAPITAL_RISK_COMBOS = [
    (5_000, 100),
    (100_000, 10),
    (100_000, 25),
    (100_000, 50),
]

# Column headers for the copy/paste table
HEADERS = [
    "DTE", "Util%", "Risk%", "Capital", "Status", "Trades", "WR%", "TotalP&L",
    "Return%", "PF", "MaxDD%", "Sharpe", "Sortino", "Skipped",
    "VIXSkip", "PeakPos", "AvgCtx", "FinalEquity", "Seconds"
]


def _json_path_for(dte_config: dict, utilization: int, capital: float,
                    risk_pct: int, ticker: str, start: str, end: str) -> Path:
    """Build the expected JSON result path for a given parameter combo."""
    capital_k = f"{int(capital/1000)}k"
    if dte_config["dte_mode"] == "short":
        dte_file = f"{dte_config['short_dte']}dte"
    elif dte_config["dte_mode"] == "weekly":
        dte_file = "weekly"
    else:
        dte_file = "monthly"
    util_file = f"util{utilization}"
    risk_file = f"risk{risk_pct}"
    return RESULTS_DIR / f"{ticker}_{dte_file}_ic_results_{capital_k}_{util_file}_{risk_file}_{start}_{end}.json"


def _parse_json_result(json_path: Path, label: str, utilization: int,
                       risk_pct: int, capital: float, elapsed: float) -> dict:
    """Read a completed JSON result file into a row dict."""
    with open(json_path) as f:
        data = json.load(f)
    s = data.get("summary", {})
    r = data.get("risk", {})
    col = data.get("collateral", {})
    return _row(
        label, utilization, risk_pct, capital, "OK",
        trades=s.get("total_trades", 0),
        wr=s.get("win_rate", 0),
        pnl=s.get("total_pnl", 0),
        ret=s.get("total_return_pct", 0),
        pf=s.get("profit_factor", 0),
        dd=r.get("max_drawdown_pct", 0),
        sharpe=r.get("sharpe_ratio", 0),
        sortino=r.get("sortino_ratio", 0),
        skipped=col.get("trades_skipped_no_capital", 0),
        vix_skip=col.get("trades_skipped_vix", 0),
        peak_pos=col.get("peak_concurrent_positions", 0),
        avg_ctx=col.get("avg_contracts_per_trade", 0),
        final_eq=s.get("final_equity", 0),
        elapsed=elapsed,
    )


def run_single(dte_config: dict, utilization: int, capital: float,
               risk_pct: int, ticker: str, start: str, end: str,
               resume: bool = False) -> dict:
    """Run one backtest. Returns a flat dict of results."""

    label = dte_config["label"]

    json_path = _json_path_for(dte_config, utilization, capital, risk_pct, ticker, start, end)

    # Resume: if JSON already exists from a previous run, skip re-running
    if resume and json_path.exists():
        try:
            return _parse_json_result(json_path, label, utilization, risk_pct, capital, elapsed=0)
        except Exception:
            pass  # Re-run if JSON is corrupted

    cmd = [
        sys.executable, str(BACKTEST_SCRIPT),
        "--ticker", ticker,
        "--start", start,
        "--end", end,
        "--capital", str(capital),
        "--max-utilization", str(utilization),
        "--max-risk-per-trade", str(risk_pct),
        "--dte-mode", dte_config["dte_mode"],
        "--short-dte", str(dte_config["short_dte"]),
        "--dynamic-sizing",
        "--export",
    ]

    # Add weekly DTE range args if in weekly mode
    if dte_config["dte_mode"] == "weekly":
        cmd.extend(["--weekly-dte-min", str(dte_config["weekly_dte_min"])])
        cmd.extend(["--weekly-dte-max", str(dte_config["weekly_dte_max"])])

    t0 = time.time()
    try:
        # Don't capture output — it eats memory across 96 runs.
        # We only need the JSON result file that --export writes.
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, timeout=900, cwd=str(PROJECT_ROOT)
        )
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        return _row(label, utilization, risk_pct, capital, "TIMEOUT", elapsed=900)

    if proc.returncode != 0:
        # Detect OOM kill (SIGKILL = -9 on Linux)
        if proc.returncode == -9:
            return _row(label, utilization, risk_pct, capital, "OOM_KILLED", elapsed=time.time() - t0)
        # Other failure — grab last line of stderr only (not full output)
        err = proc.stderr.strip().split("\n")[-1][:80] if proc.stderr else "unknown"
        return _row(label, utilization, risk_pct, capital, f"FAIL:{err}", elapsed=time.time() - t0)

    # Free stderr string immediately
    del proc
    gc.collect()

    # Parse results JSON
    if json_path.exists():
        try:
            return _parse_json_result(json_path, label, utilization, risk_pct, capital, elapsed)
        except Exception as e:
            return _row(label, utilization, risk_pct, capital, f"JSON_ERR:{e}", elapsed=elapsed)

    # Fallback: no JSON found
    return _row(label, utilization, risk_pct, capital, "NO_OUTPUT", elapsed=elapsed)


def _row(label, util, risk_pct, capital, status, trades=0, wr=0, pnl=0, ret=0, pf=0,
         dd=0, sharpe=0, sortino=0, skipped=0, vix_skip=0, peak_pos=0,
         avg_ctx=0, final_eq=0, elapsed=0):
    """Build a result row dict."""
    return {
        "DTE": label,
        "Util%": util,
        "Risk%": risk_pct,
        "Capital": int(capital),
        "Status": status,
        "Trades": trades,
        "WR%": round(wr, 1),
        "TotalP&L": round(pnl, 2),
        "Return%": round(ret, 2),
        "PF": round(pf, 2),
        "MaxDD%": round(dd, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),
        "Skipped": skipped,
        "VIXSkip": vix_skip,
        "PeakPos": peak_pos,
        "AvgCtx": round(avg_ctx, 1),
        "FinalEquity": round(final_eq, 2),
        "Seconds": round(elapsed, 1),
    }


def run_matrix(dte_filter=None, util_filter=None, capital_filter=None,
               risk_filter=None, ticker="SPX", start="2021-01-01", end="2025-12-31",
               resume=False):
    """Run the full test matrix and print copy/paste results."""

    dtes = DTE_MODES
    if dte_filter is not None:
        if dte_filter == -1:
            dtes = [d for d in DTE_MODES if d["dte_mode"] == "monthly"]
        elif dte_filter == -2:
            dtes = [d for d in DTE_MODES if d["dte_mode"] == "weekly"]
        else:
            dtes = [d for d in DTE_MODES if d["short_dte"] == dte_filter and d["dte_mode"] == "short"]
    utils = UTILIZATIONS if util_filter is None else [util_filter]
    combos = CAPITAL_RISK_COMBOS
    if capital_filter is not None:
        combos = [(c, r) for c, r in combos if c == capital_filter]
    if risk_filter is not None:
        combos = [(c, r) for c, r in combos if r == risk_filter]

    total = len(dtes) * len(utils) * len(combos)
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'#'*60}")
    print(f"# IRON CONDOR BACKTEST MATRIX")
    print(f"# Started:      {started}")
    print(f"# DTE modes:    {', '.join(d['label'] for d in dtes)}")
    print(f"# Utilizations: {', '.join(str(u)+'%' for u in utils)}")
    print(f"# Cap/Risk:     {', '.join(f'${c:,.0f}@{r}%' for c,r in combos)}")
    print(f"# Total runs:   {total}")
    print(f"# Resume mode:  {'ON' if resume else 'OFF'}")
    print(f"# Timeout:      15 min per run")
    print(f"{'#'*60}")
    sys.stdout.flush()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    partial_results_path = RESULTS_DIR / "_matrix_partial_results.json"

    all_results = []
    completed = 0
    skipped = 0
    matrix_start = time.time()

    for dte_config in dtes:
        for util in utils:
            for cap, risk_pct in combos:
                completed += 1
                label = dte_config["label"]
                cap_k = f"${int(cap/1000)}k"
                print(f"\n>>> [{completed}/{total}] {label} | {util}% util | {risk_pct}% risk | {cap_k} ...", end=" ", flush=True)

                result = run_single(dte_config, util, cap, risk_pct, ticker, start, end, resume=resume)
                all_results.append(result)

                # Instant feedback
                if result["Status"] == "OK" and result["Seconds"] == 0:
                    skipped += 1
                    print(f"CACHED | {result['Trades']} trades | "
                          f"WR {result['WR%']}% | P&L ${result['TotalP&L']:+,.2f} | "
                          f"Return {result['Return%']:+.1f}%")
                elif result["Status"] == "OK":
                    print(f"OK ({result['Seconds']:.0f}s) | {result['Trades']} trades | "
                          f"WR {result['WR%']}% | P&L ${result['TotalP&L']:+,.2f} | "
                          f"Return {result['Return%']:+.1f}%")
                else:
                    print(f"{result['Status']} ({result['Seconds']:.0f}s)")
                sys.stdout.flush()

                # Save partial results after each run so nothing is lost
                try:
                    with open(partial_results_path, 'w') as f:
                        json.dump(all_results, f, indent=2)
                except Exception:
                    pass

                # Free memory between runs
                gc.collect()

    total_elapsed = time.time() - matrix_start
    finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Print the copy/paste table ───────────────────────────────────
    print(f"\n\n{'#'*60}")
    print(f"# ALL DONE")
    print(f"# Finished:     {finished}")
    print(f"# Total time:   {total_elapsed/60:.1f} minutes")
    print(f"# Successful:   {sum(1 for r in all_results if r['Status']=='OK')}/{total}")
    if skipped:
        print(f"# Cached:       {skipped} (from previous run)")
    print(f"{'#'*60}")

    # TSV table — copy everything between the START/END markers
    print(f"\n{'='*60}")
    print("COPY-PASTE START (tab-separated, paste into Google Sheets)")
    print(f"{'='*60}")

    # Header row
    print("\t".join(HEADERS))

    # Data rows
    for r in all_results:
        vals = [str(r[h]) for h in HEADERS]
        print("\t".join(vals))

    print(f"{'='*60}")
    print("COPY-PASTE END")
    print(f"{'='*60}")

    # Also print a human-readable summary for quick scanning
    print(f"\n{'─'*90}")
    print("QUICK SUMMARY (best result per DTE mode):")
    print(f"{'─'*90}")
    ok = [r for r in all_results if r["Status"] == "OK"]
    if ok:
        # Group by DTE and find best return
        by_dte = {}
        for r in ok:
            key = r["DTE"]
            if key not in by_dte or r["Return%"] > by_dte[key]["Return%"]:
                by_dte[key] = r
        print(f"  {'DTE':<10} {'Util':>5} {'Risk':>5} {'Capital':>10} {'Return%':>9} {'WR%':>6} {'MaxDD%':>8} {'Sharpe':>7} {'Trades':>7}")
        for dte_label in ["0DTE", "1DTE", "2DTE", "3DTE", "Weekly", "Monthly"]:
            if dte_label in by_dte:
                r = by_dte[dte_label]
                print(f"  {r['DTE']:<10} {r['Util%']:>4}% {r['Risk%']:>4}% ${r['Capital']:>9,} {r['Return%']:>+8.1f}% "
                      f"{r['WR%']:>5.1f}% {r['MaxDD%']:>7.1f}% {r['Sharpe']:>6.2f} {r['Trades']:>7}")
    else:
        print("  No successful runs.")

    failed = [r for r in all_results if r["Status"] != "OK"]
    if failed:
        print(f"\nFAILED RUNS ({len(failed)}):")
        for r in failed:
            print(f"  {r['DTE']} | {r['Util%']}% util | {r['Risk%']}% risk | ${r['Capital']:,} -> {r['Status']}")

    print(f"\n{'#'*60}")
    print(f"# MATRIX COMPLETE - {finished}")
    print(f"{'#'*60}\n")
    sys.stdout.flush()

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Run IC backtest matrix across DTE/utilization/capital combinations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backtest/run_ic_matrix.py                       # Full 96-run matrix
  python backtest/run_ic_matrix.py --capital 100000      # Just $100k (72 runs)
  python backtest/run_ic_matrix.py --capital 5000        # Just $5k (24 runs)
  python backtest/run_ic_matrix.py --dte 0               # Just 0DTE (16 runs)
  python backtest/run_ic_matrix.py --dte -1              # Just Monthly (16 runs)
  python backtest/run_ic_matrix.py --dte -2              # Just Weekly (16 runs)
  python backtest/run_ic_matrix.py --utilization 50      # Just 50% util (24 runs)
  python backtest/run_ic_matrix.py --risk 25             # Just 25% risk (24 runs)
  python backtest/run_ic_matrix.py --resume               # Resume after crash (skip completed)
        """
    )
    parser.add_argument("--dte", type=int, default=None, choices=[0, 1, 2, 3, -1, -2],
                        help="Single DTE (0-3), -1 for monthly, -2 for weekly")
    parser.add_argument("--utilization", type=int, default=None, choices=[20, 30, 50, 70],
                        help="Single utilization level")
    parser.add_argument("--capital", type=float, default=None,
                        help="Single capital level (e.g. 5000 or 100000)")
    parser.add_argument("--risk", type=int, default=None, choices=[10, 25, 50, 100],
                        help="Single risk-per-trade %% (10, 25, 50, or 100)")
    parser.add_argument("--ticker", default="SPX", help="Underlying (default: SPX)")
    parser.add_argument("--start", default="2021-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    parser.add_argument("--resume", action="store_true",
                        help="Skip runs that already have JSON results (resume after crash)")
    args = parser.parse_args()

    run_matrix(
        dte_filter=args.dte,
        util_filter=args.utilization,
        capital_filter=args.capital,
        risk_filter=args.risk,
        ticker=args.ticker,
        start=args.start,
        end=args.end,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
