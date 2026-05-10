"""End-to-end runner: iterate days, collect trades, write CSV + report."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import List

from backtest.touch_pin.engine import run_one_day, TradeRow
from backtest.touch_pin.report import write_trades_csv, write_markdown_report
from backtest.touch_pin.binning import bin_trades
from backtest.touch_pin.walk_forward import split_trades, evaluate_go_no_go

logger = logging.getLogger("touch_pin")


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def trading_days_between(start: dt.date, end: dt.date) -> List[dt.date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def main(argv=None):
    p = argparse.ArgumentParser(prog="backtest.touch_pin")
    p.add_argument("--start", type=parse_date, required=True)
    p.add_argument("--end", type=parse_date, required=True)
    p.add_argument("--target-minute", type=int, default=5)
    p.add_argument("--exit-minute", type=int, default=385)
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--commission-leg", type=float, default=1.30)
    p.add_argument("--output-dir", type=Path, default=Path("backtest/touch_pin/output"))
    p.add_argument("--report-name", type=str, default="touch_pin")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-eval", action="store_true",
                   help="Skip walk-forward GO/NO-GO evaluation (just dump trades)")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    db_main = os.environ.get("DATABASE_URL")
    db_orat = os.environ.get("ORAT_DATABASE_URL", db_main)
    if not db_main:
        logger.error("DATABASE_URL must be set")
        return 1

    days = trading_days_between(args.start, args.end)
    logger.info("running %d trading days from %s to %s", len(days), args.start, args.end)

    all_trades: List[TradeRow] = []
    for i, d in enumerate(days):
        try:
            rows = run_one_day(
                db_main, db_orat, d,
                target_minute=args.target_minute,
                exit_minute=args.exit_minute,
                slippage_ticks_per_leg=args.slippage_ticks,
                commission_per_leg=args.commission_leg,
            )
            all_trades.extend(rows)
            if (i + 1) % 25 == 0:
                logger.info("%d/%d days done; %d trades so far", i + 1, len(days), len(all_trades))
        except Exception:
            logger.exception("day %s failed; continuing", d)

    logger.info("complete: %d trades from %d days", len(all_trades), len(days))

    out_csv = args.output_dir / f"{args.report_name}_trades_{args.start}_{args.end}.csv"
    out_md = args.output_dir / f"{args.report_name}_report_{args.start}_{args.end}.md"
    write_trades_csv(all_trades, out_csv)

    bins = bin_trades(all_trades)

    go_summary = None
    if not args.no_eval:
        train, val, oos = split_trades(all_trades)
        insample = train + val
        result = evaluate_go_no_go(insample, oos)
        go_summary = result.summary
        logger.info("GO/NO-GO: %s", result.summary)

    write_markdown_report(all_trades, bins, out_md, args.start, args.end, sensitivity_results=None)
    if go_summary:
        with out_md.open("a", encoding="utf-8") as f:
            f.write("\n\n## GO/NO-GO\n\n```\n")
            f.write(go_summary)
            f.write("\n```\n")

    logger.info("wrote %s and %s", out_csv, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
