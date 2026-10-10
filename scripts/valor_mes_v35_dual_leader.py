"""Test the frozen MNQ+M2K same-minute breakout transfer to MES.

Research only. This command reads existing checksummed cache rows in a
read-only transaction, never calls a vendor or broker, and never reads 2026.
Reported fills are trade-print planning proxies, not executable quotes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import os
from typing import Callable, Iterable

import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33


SCHEMA_VERSION = "valor-mes-v35-result/1.0.0"
STRATEGY_VERSION = "v35"
STUDY_ID = "valor-mes-v35-dual-leader-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
SYMBOLS = ("MES", "MNQ", "M2K")
TICK_SIZES = {"MES": 0.25, "MNQ": 0.25, "M2K": 0.10}
LOOKBACK_MINUTES = 30
MAX_HOLD_MINUTES = 240
BOOTSTRAP_SEED = 350035
BOOTSTRAP_RESAMPLES = 10_000
LEDGER_FIELDS = (
    "year", "date", "lookback_minutes", "max_hold_minutes",
    "actual_hold_minutes", "side", "prior_mnq_high", "prior_mnq_low",
    "mnq_signal_close", "prior_m2k_high", "prior_m2k_low",
    "m2k_signal_close", "signal_bar_start", "decision_time", "entry_time",
    "exit_time", "exit_reason", "mes_instrument_id", "mnq_instrument_id",
    "m2k_instrument_id", "entry_price", "exit_price", "gross_dollars",
    "fee_0t", "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class TripleSession:
    date: str
    mes: pd.DataFrame
    mnq: pd.DataFrame
    m2k: pd.DataFrame


def _complete(frame: pd.DataFrame, symbol: str) -> dict[str, pd.DataFrame]:
    prepared = v33.cash.prepare(frame, TICK_SIZES[symbol])
    return v33._complete_sessions(prepared)


def build_triple_sessions(mes_frames: Iterable[pd.DataFrame],
                          mnq_frames: Iterable[pd.DataFrame],
                          m2k_frames: Iterable[pd.DataFrame]) -> list[TripleSession]:
    """Return only exact, complete, synchronized three-market cash sessions."""
    groups = {
        "MES": _complete(pd.concat(list(mes_frames), ignore_index=True), "MES"),
        "MNQ": _complete(pd.concat(list(mnq_frames), ignore_index=True), "MNQ"),
        "M2K": _complete(pd.concat(list(m2k_frames), ignore_index=True), "M2K"),
    }
    common = set(groups["MES"]).intersection(groups["MNQ"], groups["M2K"])
    sessions: list[TripleSession] = []
    for day in sorted(common):
        mes, mnq, m2k = (groups[symbol][day] for symbol in SYMBOLS)
        timestamps = pd.DatetimeIndex(mes.timestamp)
        if not (timestamps.equals(pd.DatetimeIndex(mnq.timestamp))
                and timestamps.equals(pd.DatetimeIndex(m2k.timestamp))):
            continue
        sessions.append(TripleSession(day, mes, mnq, m2k))
    return sessions


def _expected_path(frame: pd.DataFrame, start: int, length: int) -> bool:
    path = frame.iloc[start:start + length]
    if len(path) != length or path.instrument_id.nunique(dropna=False) != 1:
        return False
    expected = pd.date_range(pd.Timestamp(path.timestamp.iloc[0]), periods=length, freq="1min")
    return pd.DatetimeIndex(path.timestamp).equals(expected)


def _breakout(frame: pd.DataFrame, position: int) -> tuple[int, float, float, float]:
    prior = frame.iloc[position - LOOKBACK_MINUTES:position]
    close = float(frame.close.iloc[position])
    high, low = float(prior.high.max()), float(prior.low.min())
    side = 1 if close > high else -1 if close < low else 0
    return side, high, low, close


def generate_trades(sessions: list[TripleSession], year: int) -> list[dict]:
    """Apply the single dual-leader cell with strict execution paths."""
    if year not in ALLOWED_YEARS:
        raise ValueError("v35 may evaluate only 2023-2025")
    trades: list[dict] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    for session in sessions:
        if int(session.date[:4]) != year:
            continue
        mes, mnq, m2k = session.mes, session.mnq, session.m2k
        timestamps = pd.DatetimeIndex(mes.timestamp)
        if not (len(mes) == len(mnq) == len(m2k)
                and timestamps.equals(pd.DatetimeIndex(mnq.timestamp))
                and timestamps.equals(pd.DatetimeIndex(m2k.timestamp))):
            continue
        policy = v33.cash.session(session.date)
        if policy is None:
            continue
        flat_time = pd.Timestamp(policy[2]).tz_convert("UTC")
        for position in range(LOOKBACK_MINUTES, len(mes)):
            start = position - LOOKBACK_MINUTES
            if not (_expected_path(mnq, start, LOOKBACK_MINUTES + 1)
                    and _expected_path(m2k, start, LOOKBACK_MINUTES + 1)):
                continue
            mnq_side, mnq_high, mnq_low, mnq_close = _breakout(mnq, position)
            m2k_side, m2k_high, m2k_low, m2k_close = _breakout(m2k, position)
            if mnq_side == 0 or mnq_side != m2k_side:
                continue
            side = mnq_side

            entry_position = position + 1
            if entry_position >= len(mes):
                continue
            entry_time = pd.Timestamp(mes.timestamp.iloc[entry_position])
            decision_time = pd.Timestamp(mes.timestamp.iloc[position]) + pd.Timedelta(minutes=1)
            if entry_time != decision_time or entry_time < last_exit or entry_time >= flat_time:
                continue
            exit_boundary = min(
                entry_time + pd.Timedelta(minutes=MAX_HOLD_MINUTES), flat_time,
            )
            actual_hold = int((exit_boundary - entry_time) / pd.Timedelta(minutes=1))
            if actual_hold <= 0 or not _expected_path(mes, entry_position, actual_hold):
                continue
            exit_position = entry_position + actual_hold - 1
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
                "prior_mnq_high": mnq_high,
                "prior_mnq_low": mnq_low,
                "mnq_signal_close": mnq_close,
                "prior_m2k_high": m2k_high,
                "prior_m2k_low": m2k_low,
                "m2k_signal_close": m2k_close,
                "signal_bar_start": pd.Timestamp(mes.timestamp.iloc[position]).isoformat(),
                "decision_time": decision_time.isoformat(),
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "exit_reason": "fixed_240m" if actual_hold == MAX_HOLD_MINUTES else "v8_preclose",
                "mes_instrument_id": int(mes_path.instrument_id.iloc[0]),
                "mnq_instrument_id": int(mnq.instrument_id.iloc[position]),
                "m2k_instrument_id": int(m2k.instrument_id.iloc[position]),
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
    two = summary["cost_views"]["selection_2t"]
    four = summary["cost_views"]["stress_4t"]
    return (
        two["trade_count"] >= 60
        and two["net_dollars"] > 0
        and v33._profit_factor_value(two) >= 1.10
        and two["average_trade"] is not None
        and two["average_trade"] >= 8
        and four["net_dollars"] > 0
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
            "leaders": ["MNQ", "M2K"],
            "lookback_minutes": LOOKBACK_MINUTES,
            "direction": "same_minute_same_direction",
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
    """Open each year only after the unchanged rule passes the prior year."""
    frames = {symbol: {} for symbol in SYMBOLS}
    result = _result_base()
    ledger: list[dict] = []
    yearly_trades: dict[int, list[dict]] = {}
    sessions: list[TripleSession] = []
    for year in ALLOWED_YEARS:
        for symbol in SYMBOLS:
            frames[symbol][year] = loader(symbol, year)
        result["years_loaded"].append(year)
        years = sorted(frames["MES"])
        sessions = build_triple_sessions(
            [frames["MES"][item] for item in years],
            [frames["MNQ"][item] for item in years],
            [frames["M2K"][item] for item in years],
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
        yearly_trades[2024] + yearly_trades[2025], validation_dates,
        resamples=bootstrap_resamples, seed=BOOTSTRAP_SEED,
    )
    result["bootstrap"] = bootstrap
    if bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0:
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = "requires executable MES bid/ask calibration and forward paper fills"
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "historical family rejected by combined 2024-2025 daily bootstrap"
    return result, ledger


def postgres_loader(database_url: str) -> tuple[Callable[[str, int], pd.DataFrame], Callable[[], None]]:
    """Create a checksum-validating three-symbol loader in a read-only transaction."""
    import psycopg2

    connection = psycopg2.connect(database_url, connect_timeout=15)
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor()

    def load(symbol: str, year: int) -> pd.DataFrame:
        if symbol not in SYMBOLS or year not in ALLOWED_YEARS:
            raise ValueError("only MES/MNQ/M2K 2023-2025 cache rows are permitted")
        key = f"GLBX.MDP3:ohlcv-1m:{symbol}.v.0:{year}"
        cursor.execute(
            "SELECT sha256, parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"missing cache row {key}")
        body = bytes(row[1])
        if hashlib.sha256(body).hexdigest() != str(row[0]):
            raise ValueError(f"cache checksum mismatch {key}")
        return pd.read_parquet(io.BytesIO(body))

    def close() -> None:
        try:
            connection.rollback()
        finally:
            cursor.close()
            connection.close()

    return load, close


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
    loader, close = postgres_loader(args.database_url)
    try:
        result, ledger = run_study(loader)
        write_outputs(result, ledger, args.json_out, args.ledger_out)
    finally:
        close()
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
