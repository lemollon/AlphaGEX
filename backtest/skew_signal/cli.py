"""End-to-end runner."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import List

from backtest.skew_signal.engine import run_one_day, TradeRow
from backtest.skew_signal.report import write_trades_csv, write_markdown_report
from backtest.skew_signal.binning import bin_trades
from backtest.skew_signal.walk_forward import split_trades, evaluate_go_no_go

logger = logging.getLogger("skew_signal")


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
    p = argparse.ArgumentParser(prog="backtest.skew_signal")
    p.add_argument("--start", type=parse_date, required=True)
    p.add_argument("--end", type=parse_date, required=True)
    p.add_argument("--theta-skew", type=float, default=0.005)
    p.add_argument("--theta-charm", type=float, default=50.0)
    p.add_argument("--magnet-threshold", type=float, default=1.3)
    p.add_argument("--pt-pct", type=float, default=20.0)
    p.add_argument("--sl-pct", type=float, default=30.0)
    p.add_argument("--trail-activate-pct", type=float, default=5.0)
    p.add_argument("--trail-stop-pct", type=float, default=8.0)
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--commission-leg", type=float, default=1.30)
    p.add_argument("--output-dir", type=Path, default=Path("backtest/skew_signal/output"))
    p.add_argument("--report-name", type=str, default="skew_signal")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-eval", action="store_true")
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
                db_url_main=db_main, db_url_orat=db_orat, trade_date=d,
                theta_skew=args.theta_skew, theta_charm=args.theta_charm,
                magnet_threshold=args.magnet_threshold,
                pt_pct=args.pt_pct, sl_pct=args.sl_pct,
                trailing_activate_pct=args.trail_activate_pct,
                trailing_stop_pct=args.trail_stop_pct,
                slippage_ticks_per_leg=args.slippage_ticks,
                commission_per_leg=args.commission_leg,
            )
            all_trades.extend(rows)
            if (i + 1) % 25 == 0:
                logger.info("%d/%d days; %d trades so far", i + 1, len(days), len(all_trades))
        except Exception:
            logger.exception("day %s failed; continuing", d)

    logger.info("complete: %d trades from %d days", len(all_trades), len(days))
    out_csv = args.output_dir / f"{args.report_name}_trades_{args.start}_{args.end}.csv"
    out_md = args.output_dir / f"{args.report_name}_report_{args.start}_{args.end}.md"
    write_trades_csv(all_trades, out_csv)
    bins = bin_trades(all_trades)
    write_markdown_report(all_trades, bins, out_md, args.start, args.end)

    if not args.no_eval:
        train, val, oos = split_trades(all_trades)
        result = evaluate_go_no_go(train + val, oos)
        logger.info("GO/NO-GO:\n%s", result.summary)
        with out_md.open("a", encoding="utf-8") as f:
            f.write("\n\n## GO/NO-GO\n\n```\n")
            f.write(result.summary)
            f.write("\n```\n")

    logger.info("wrote %s and %s", out_csv, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
