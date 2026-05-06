"""CLI: python -m backtest.directional_1dte --bot {solomon,gideon,both} --start ... --end ..."""
import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path

from backtest.directional_1dte.config import BOT_CONFIGS
from backtest.directional_1dte.engine import run
from backtest.directional_1dte.report import write_results, write_comparison


def parse_args():
    p = argparse.ArgumentParser(description="SOLOMON/GIDEON 1DTE directional backtest")
    p.add_argument("--bot", choices=["solomon", "gideon", "both"], default="both")
    p.add_argument("--start", default="2020-01-02", help="YYYY-MM-DD")
    p.add_argument("--end", default="2025-12-05", help="YYYY-MM-DD")
    p.add_argument("--output-dir", default=None,
                   help="Output dir; default backtest/results/<today>-solomon-gideon-1dte/")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.environ.get("ORAT_DATABASE_URL"):
        sys.exit("ORAT_DATABASE_URL not set in environment")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    out_root = Path(args.output_dir or
                    f"backtest/results/{dt.date.today().isoformat()}-solomon-gideon-1dte")
    out_root.mkdir(parents=True, exist_ok=True)

    bot_names = ["solomon", "gideon"] if args.bot == "both" else [args.bot]
    results = {}
    for name in bot_names:
        cfg = BOT_CONFIGS[name]
        print(f"[{name}] running {start} -> {end} ...", flush=True)
        res = run(cfg, start, end)
        write_results(res, out_root / name)
        results[name] = res
        print(f"[{name}] {len(res.trades)} trades, {len(res.skips)} skips, "
              f"P&L ${sum(t.realized_pnl for t in res.trades):,.2f}", flush=True)

    if len(results) > 1:
        write_comparison(results, out_root)
        print(f"Comparison written to {out_root}/comparison.md", flush=True)


if __name__ == "__main__":
    main()
