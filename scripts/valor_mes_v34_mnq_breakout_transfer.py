"""Transfer the frozen MNQ 30-minute breakout direction to MES.

Research only. Existing checksummed MES/MNQ cache rows are read through the
v33 read-only loader. Calendar year 2026, vendors, brokers, and production are
outside this command's boundary. Reported fills are trade-print proxies.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import os
from typing import Callable

import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33


SCHEMA_VERSION = "valor-mes-v34-result/1.0.0"
STRATEGY_VERSION = "v34"
STUDY_ID = "valor-mes-v34-mnq-breakout-transfer-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
LOOKBACK_MINUTES = 30
MAX_HOLD_MINUTES = 240
BOOTSTRAP_SEED = 340034
BOOTSTRAP_RESAMPLES = 10_000
LEDGER_FIELDS = (
    "year", "date", "lookback_minutes", "max_hold_minutes",
    "actual_hold_minutes", "side", "prior_mnq_high", "prior_mnq_low",
    "mnq_signal_close", "signal_bar_start", "decision_time", "entry_time",
    "exit_time", "exit_reason", "mes_instrument_id", "mnq_instrument_id",
    "entry_price", "exit_price", "gross_dollars", "fee_0t", "planning_1t",
    "selection_2t", "stress_4t",
)


def _expected_path(frame: pd.DataFrame, start: int, length: int) -> bool:
    path = frame.iloc[start:start + length]
    if len(path) != length or path.instrument_id.nunique(dropna=False) != 1:
        return False
    first = pd.Timestamp(path.timestamp.iloc[0])
    expected = pd.date_range(first, periods=length, freq="1min")
    return pd.DatetimeIndex(path.timestamp).equals(expected)


def generate_trades(sessions: list[v33.PairSession], year: int) -> list[dict]:
    """Apply the one-cell breakout transfer with strict path validation."""
    if year not in ALLOWED_YEARS:
        raise ValueError("v34 may evaluate only 2023-2025")
    trades: list[dict] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    for session in sessions:
        if int(session.date[:4]) != year:
            continue
        mes, mnq = session.mes, session.mnq
        if len(mes) != len(mnq) or not pd.DatetimeIndex(mes.timestamp).equals(
                pd.DatetimeIndex(mnq.timestamp)):
            continue
        policy = v33.cash.session(session.date)
        if policy is None:
            continue
        flat_time = pd.Timestamp(policy[2]).tz_convert("UTC")
        for position in range(LOOKBACK_MINUTES, len(mnq)):
            if not (_expected_path(mnq, position - LOOKBACK_MINUTES,
                                   LOOKBACK_MINUTES + 1)
                    and _expected_path(mes, position - LOOKBACK_MINUTES,
                                       LOOKBACK_MINUTES + 1)):
                continue
            prior = mnq.iloc[position - LOOKBACK_MINUTES:position]
            signal_close = float(mnq.close.iloc[position])
            prior_high = float(prior.high.max())
            prior_low = float(prior.low.min())
            if signal_close > prior_high:
                side = 1
            elif signal_close < prior_low:
                side = -1
            else:
                continue

            entry_position = position + 1
            if entry_position >= len(mes):
                continue
            entry_time = pd.Timestamp(mes.timestamp.iloc[entry_position])
            decision_time = pd.Timestamp(mes.timestamp.iloc[position]) + pd.Timedelta(minutes=1)
            if entry_time != decision_time or entry_time < last_exit or entry_time >= flat_time:
                continue
            exit_boundary = min(
                entry_time + pd.Timedelta(minutes=MAX_HOLD_MINUTES),
                flat_time,
            )
            actual_hold = int((exit_boundary - entry_time) / pd.Timedelta(minutes=1))
            if actual_hold <= 0:
                continue
            exit_position = entry_position + actual_hold - 1
            if exit_position >= len(mes) or not _expected_path(mes, entry_position, actual_hold):
                continue
            exit_time = pd.Timestamp(mes.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
            if exit_time != exit_boundary:
                continue

            mes_path = mes.iloc[entry_position:exit_position + 1]
            entry_price = float(mes_path.open.iloc[0])
            exit_price = float(mes_path.close.iloc[-1])
            gross = round(side * (exit_price - entry_price) * v33.POINT_VALUE, 6)
            trade = {
                "year": year,
                "date": session.date,
                "lookback_minutes": LOOKBACK_MINUTES,
                "max_hold_minutes": MAX_HOLD_MINUTES,
                "actual_hold_minutes": actual_hold,
                "side": side,
                "prior_mnq_high": prior_high,
                "prior_mnq_low": prior_low,
                "mnq_signal_close": signal_close,
                "signal_bar_start": pd.Timestamp(mnq.timestamp.iloc[position]).isoformat(),
                "decision_time": decision_time.isoformat(),
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "exit_reason": "fixed_240m" if actual_hold == MAX_HOLD_MINUTES else "v8_preclose",
                "mes_instrument_id": int(mes_path.instrument_id.iloc[0]),
                "mnq_instrument_id": int(mnq.instrument_id.iloc[position]),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_dollars": gross,
            }
            for name, ticks in v33.COST_CASES[1:]:
                trade[name] = v33._cost(gross, ticks)
            trades.append(trade)
            last_exit = exit_time
    return trades


def annual_passes(summary: dict) -> bool:
    two_tick = summary["cost_views"]["selection_2t"]
    four_tick = summary["cost_views"]["stress_4t"]
    return (
        two_tick["trade_count"] >= 80
        and two_tick["net_dollars"] > 0
        and v33._profit_factor_value(two_tick) >= 1.10
        and two_tick["average_trade"] is not None
        and two_tick["average_trade"] >= 8
        and four_tick["net_dollars"] > 0
    )


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "calendar_year_2026_sealed": True,
        "cell": {
            "lookback_minutes": LOOKBACK_MINUTES,
            "direction": "same_direction_mnq_to_mes",
            "max_hold_minutes": MAX_HOLD_MINUTES,
            "cells": 1,
        },
        "execution": {
            "fill_convention": "next-minute MES open to last MES close before fixed horizon or v8 preclose",
            "evidence": "trade-print proxy; executable bid/ask and latency not verified",
            "round_trip_fee": v33.ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "years_loaded": [],
        "annual_results": {},
        "verdict": None,
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Open each calendar year only after the identical prior-year gate passes."""
    frames: dict[str, dict[int, pd.DataFrame]] = {"MES": {}, "MNQ": {}}
    result = _result_base()
    ledger: list[dict] = []
    sessions: list[v33.PairSession] = []
    yearly_trades: dict[int, list[dict]] = {}

    for year in ALLOWED_YEARS:
        for symbol in ("MES", "MNQ"):
            frames[symbol][year] = loader(symbol, year)
        result["years_loaded"].append(year)
        years = sorted(frames["MES"])
        sessions = v33.build_pair_sessions(
            [frames["MES"][item] for item in years],
            [frames["MNQ"][item] for item in years],
        )
        trades = generate_trades(sessions, year)
        summary = v33.summarize_cell(trades, year)
        passed = annual_passes(summary)
        result["annual_results"][str(year)] = {"passed": passed, "metrics": summary}
        yearly_trades[year] = trades
        ledger.extend(trades)
        if not passed:
            if year == 2023:
                result["verdict"] = "FAILED_2023_DISCOVERY"
                result["firewall"] = "2024 and 2025 unopened because the one cell failed 2023"
            elif year == 2024:
                result["verdict"] = "FAILED_2024_VALIDATION"
                result["firewall"] = "2025 unopened because the unchanged cell failed 2024"
            else:
                result["verdict"] = "FAILED_2025_VALIDATION"
                result["firewall"] = "historical family rejected by independent 2025 confirmation"
            return result, ledger

    validation_dates = [row.date for row in sessions if row.date[:4] in {"2024", "2025"}]
    bootstrap = v33.day_cluster_bootstrap(
        yearly_trades[2024] + yearly_trades[2025],
        validation_dates,
        resamples=bootstrap_resamples,
        seed=BOOTSTRAP_SEED,
    )
    result["bootstrap"] = bootstrap
    if bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0:
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = "requires executable MES bid/ask calibration and forward paper fills"
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "historical family rejected by combined 2024-2025 daily bootstrap"
    return result, ledger


def write_outputs(result: dict, ledger: list[dict], json_out: Path,
                  ledger_out: Path) -> None:
    json_out, ledger_out = Path(json_out), Path(ledger_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    ledger_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with ledger_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ledger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--ledger-out", type=Path, required=True)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    loader, close = v33.postgres_loader(args.database_url)
    try:
        result, ledger = run_study(loader)
        write_outputs(result, ledger, args.json_out, args.ledger_out)
    finally:
        close()
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
