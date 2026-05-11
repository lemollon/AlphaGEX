"""JOSHUA replay CLI.

Usage:
    python -m backtest.joshua_replay --start 2026-02-09 --end 2026-05-09

Writes:
    docs/superpowers/reports/2026-05-11-joshua-replay.md
    backtest/joshua_replay/output/trades.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import pathlib
from collections import defaultdict
from typing import Optional

from backtest.joshua_replay.data import load_snapshots, load_snapshots_from_gex_history
from backtest.joshua_replay.engine import replay_day, TradeOutcome
from backtest.joshua_replay.quotes import synthetic_vertical
from backtest.joshua_replay.report import build_report
from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig
from trading.helios.setups.base import SetupAction
from quant.bs import bs_price

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("joshua_replay")


def _t_years_to_expiration(snap_ct: dt.datetime, expiration: dt.date) -> float:
    expiration_close = dt.datetime.combine(expiration, dt.time(15, 0))
    delta_sec = (expiration_close - snap_ct).total_seconds()
    return max(delta_sec / (365.0 * 86400.0), 1e-6)


def _next_trading_day(d: dt.date) -> dt.date:
    nd = d + dt.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += dt.timedelta(days=1)
    return nd


def _build_debit_estimator():
    def estimator(snap: GexSnapshot, action: SetupAction) -> float:
        sigma = max(snap.vix / 100.0, 0.05)
        expiration = _next_trading_day(snap.snapshot_at.date())
        snap_ct = snap.snapshot_at.replace(tzinfo=None) - dt.timedelta(hours=5)
        t_years = _t_years_to_expiration(snap_ct, expiration)
        is_call = action.direction == "call"
        v = synthetic_vertical(
            spot=snap.spot,
            long_strike=action.long_strike,
            short_strike=action.short_strike,
            is_call=is_call,
            t_years=t_years,
            sigma=sigma,
        )
        return max(v.debit, 0.05)
    return estimator


def _build_spot_mark_provider():
    def provider(*, snapshot: GexSnapshot, action: SetupAction, minute: int, entry_minute: int, debit: float) -> float:
        sigma = max(snapshot.vix / 100.0, 0.05)
        expiration = _next_trading_day(snapshot.snapshot_at.date())
        snap_ct = snapshot.snapshot_at.replace(tzinfo=None) - dt.timedelta(hours=5)
        t_years = _t_years_to_expiration(snap_ct, expiration)
        is_call = action.direction == "call"
        long_p = bs_price(snapshot.spot, action.long_strike, t_years, sigma, is_call)
        short_p = bs_price(snapshot.spot, action.short_strike, t_years, sigma, is_call)
        return max(long_p - short_p, 0.0)
    return provider


def _group_by_day(snaps):
    by_day = defaultdict(list)
    for s in snaps:
        ct = s.snapshot_at - dt.timedelta(hours=5)
        by_day[ct.date()].append(s)
    return by_day


def run(start: dt.date, end: dt.date, *, out_dir: Optional[pathlib.Path] = None):
    out_dir = out_dir or pathlib.Path("backtest/joshua_replay/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = pathlib.Path("docs/superpowers/reports/2026-05-11-joshua-replay.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "trades.csv"

    config = JoshuaConfig()
    debit_estimator = _build_debit_estimator()
    spot_mark = _build_spot_mark_provider()

    logger.info("Loading snapshots %s -> %s (watchtower first, gex_history fallback)", start, end)
    all_snaps = load_snapshots(start, end, symbol="SPY")
    populated = [s for s in all_snaps if s.call_wall > 0 and s.flip_point > 0]
    if len(populated) < 10:
        logger.info("Watchtower has only %d wall-populated snaps — falling back to gex_history", len(populated))
        all_snaps = load_snapshots_from_gex_history(start, end, symbol="SPY")
    logger.info("Loaded %d snapshots", len(all_snaps))
    by_day = _group_by_day(all_snaps)

    all_trades: list = []
    for day in sorted(by_day):
        day_snaps = by_day[day]
        day_trades = replay_day(day_snaps, config=config,
                                spot_mark_provider=spot_mark,
                                debit_estimator=debit_estimator)
        all_trades.extend(day_trades)
        logger.info("  %s: %d snapshots -> %d trades", day, len(day_snaps), len(day_trades))

    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trade_date", "setup", "direction", "entry_minute", "exit_minute",
                    "debit", "exit_reason", "realized_pct"])
        for t in all_trades:
            w.writerow([t.trade_date, t.setup, t.direction, t.entry_minute, t.exit_minute,
                        f"{t.debit:.4f}", t.exit_reason, f"{t.realized_pct:.2f}"])
    logger.info("CSV: %s", csv_path)

    report = build_report(all_trades, start=start, end=end)
    report_path.write_text(report)
    logger.info("Report: %s", report_path)
    print(report)
    return all_trades


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    args = p.parse_args()
    run(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))


if __name__ == "__main__":
    main()
