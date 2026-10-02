"""Frozen MES v43 intraday cross-asset risk-pulse research.

Research only. Reads checksummed MES/MCL/MGC one-minute cache rows through a
read-only transaction, scans a fixed all-day grid, and refuses calendar 2026.
Fills are one-minute trade-print proxies, not executable bid/ask evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v39_overnight_sweep as v39


SCHEMA_VERSION = "valor-mes-v43-result/1.0.0"
STRATEGY_VERSION = "v43"
STUDY_ID = "valor-mes-v43-crossasset-riskpulse-20260926"
ALLOWED_YEARS = (2023, 2024, 2025)
SYMBOLS = ("MES", "MCL", "MGC")
TICK_SIZES = {"MES": 0.25, "MCL": 0.01, "MGC": 0.10}
HOLDS = (15, 30, 60, 120)
LOOKBACK_MINUTES = 30
DECISION_MINUTES = tuple(range(9 * 60, 14 * 60 + 16, 15))
POINT_VALUE = 5.0
ROUND_TRIP_FEE = 3.0
MIN_TRADES = 120
MIN_ACTIVE_MONTHS = 9
BOOTSTRAP_SEED = 430043
BOOTSTRAP_RESAMPLES = 10_000
COST_CASES = (
    ("raw_gross", None),
    ("fee_0t", 0),
    ("planning_1t", 1),
    ("selection_2t", 2),
    ("stress_4t", 4),
)
LEDGER_FIELDS = (
    "year", "date", "hold_minutes", "side", "risk_state", "time_block",
    "dominant_leg", "oil_return_bps", "gold_return_bps", "signal_strength_bps",
    "decision_time", "entry_time", "exit_time", "mes_instrument_id",
    "mcl_instrument_id", "mgc_instrument_id", "entry_price", "exit_price",
    "gross_dollars", "fee_0t", "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class TripleSession:
    date: str
    mes: pd.DataFrame
    mcl: pd.DataFrame
    mgc: pd.DataFrame


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _prepare(frames: Iterable[pd.DataFrame], symbol: str) -> pd.DataFrame:
    if symbol not in SYMBOLS:
        raise ValueError("symbol outside frozen v43 inputs")
    items = []
    for frame in frames:
        item = frame
        if ("timestamp" not in item and "ts_event" not in item
                and item.index.name in {"timestamp", "ts_event"}):
            item = item.reset_index()
        items.append(item)
    if not items:
        raise ValueError(f"no {symbol} frames")
    return v33.cash.prepare(pd.concat(items, ignore_index=True), TICK_SIZES[symbol])


def build_sessions(frames: dict[str, list[pd.DataFrame]]) -> tuple[list[TripleSession], dict[int, dict[str, int]]]:
    """Return exact synchronized cash sessions and mutually exclusive skips."""
    if set(frames) != set(SYMBOLS):
        raise ValueError("v43 requires exactly MES, MCL, and MGC frames")
    complete = {
        symbol: v33._complete_sessions(_prepare(frames[symbol], symbol))
        for symbol in SYMBOLS
    }
    years = sorted({int(day[:4]) for symbol in SYMBOLS for day in complete[symbol]
                    if int(day[:4]) in ALLOWED_YEARS})
    exclusions = {year: Counter() for year in years}
    sessions: list[TripleSession] = []
    for year in years:
        union_days = sorted(set().union(*(
            {day for day in complete[symbol] if int(day[:4]) == year}
            for symbol in SYMBOLS
        )))
        for day in union_days:
            missing = [symbol for symbol in SYMBOLS if day not in complete[symbol]]
            if missing:
                exclusions[year]["missing_complete_" + "_".join(s.lower() for s in missing)] += 1
                continue
            mes, mcl, mgc = (complete[symbol][day] for symbol in SYMBOLS)
            timestamps = pd.DatetimeIndex(mes.timestamp)
            if (not timestamps.equals(pd.DatetimeIndex(mcl.timestamp))
                    or not timestamps.equals(pd.DatetimeIndex(mgc.timestamp))):
                exclusions[year]["unsynchronized_timestamps"] += 1
                continue
            sessions.append(TripleSession(day, mes, mcl, mgc))
            exclusions[year]["usable_synchronized_sessions"] += 1
    return sessions, {year: dict(counts) for year, counts in exclusions.items()}


def _cost(gross: float, ticks_each_side: int | None) -> float:
    if ticks_each_side is None:
        return round(float(gross), 6)
    cost = ROUND_TRIP_FEE + 2 * ticks_each_side * TICK_SIZES["MES"] * POINT_VALUE
    return round(float(gross) - cost, 6)


def _time_block(minute: int) -> str:
    if minute < 10 * 60 + 30:
        return "morning"
    if minute < 12 * 60:
        return "midday"
    return "afternoon"


def generate_trades(sessions: list[TripleSession], year: int, hold: int) -> tuple[list[dict], dict]:
    """Generate causal, non-overlapping MES fills for one frozen hold cell."""
    if year not in ALLOWED_YEARS or hold not in HOLDS:
        raise ValueError("year or hold outside frozen v43 family")
    trades: list[dict] = []
    counts = Counter()
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    for session in sessions:
        if int(session.date[:4]) != year:
            continue
        policy = v33.cash.session(session.date)
        if policy is None:
            counts["missing_calendar_policy"] += 1
            continue
        flat_time = pd.Timestamp(policy[2]).tz_convert("UTC")
        for minute in DECISION_MINUTES:
            entry_position = minute - 8 * 60 - 30
            start = entry_position - LOOKBACK_MINUTES
            if start < 0 or entry_position >= len(session.mes):
                counts["decision_outside_session"] += 1
                continue
            oil = session.mcl.iloc[start:entry_position]
            gold = session.mgc.iloc[start:entry_position]
            if len(oil) != LOOKBACK_MINUTES or len(gold) != LOOKBACK_MINUTES:
                counts["incomplete_signal_window"] += 1
                continue
            oil_return = (float(oil.close.iloc[-1]) / float(oil.open.iloc[0]) - 1.0) * 10_000
            gold_return = (float(gold.close.iloc[-1]) / float(gold.open.iloc[0]) - 1.0) * 10_000
            if not (_finite(oil_return) and _finite(gold_return)):
                counts["nonfinite_return"] += 1
                continue
            if oil_return == 0 or gold_return == 0:
                counts["zero_return"] += 1
                continue
            if oil_return * gold_return >= 0:
                counts["same_sign_no_signal"] += 1
                continue
            counts["opposed_sign_candidates"] += 1
            side = 1 if oil_return > 0 else -1
            exit_position = entry_position + hold - 1
            if exit_position >= len(session.mes):
                counts["exit_unavailable"] += 1
                continue
            entry_time = pd.Timestamp(session.mes.timestamp.iloc[entry_position])
            exit_time = pd.Timestamp(session.mes.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
            if exit_time > flat_time:
                counts["exit_after_flat_policy"] += 1
                continue
            if entry_time < last_exit:
                counts["overlap_blocked"] += 1
                continue
            mes_path = session.mes.iloc[entry_position:exit_position + 1]
            expected = pd.date_range(entry_time, periods=hold, freq="1min")
            if (len(mes_path) != hold
                    or not pd.DatetimeIndex(mes_path.timestamp).equals(expected)
                    or mes_path.instrument_id.nunique(dropna=False) != 1):
                counts["invalid_mes_execution_path"] += 1
                continue
            entry_price = float(mes_path.open.iloc[0])
            exit_price = float(mes_path.close.iloc[-1])
            gross = round(side * (exit_price - entry_price) * POINT_VALUE, 6)
            trade = {
                "year": year,
                "date": session.date,
                "hold_minutes": hold,
                "side": side,
                "risk_state": "risk_on" if side > 0 else "risk_off",
                "time_block": _time_block(minute),
                "dominant_leg": "oil" if abs(oil_return) > abs(gold_return) else "gold",
                "oil_return_bps": round(oil_return, 10),
                "gold_return_bps": round(gold_return, 10),
                "signal_strength_bps": round(min(abs(oil_return), abs(gold_return)), 10),
                "decision_time": entry_time.isoformat(),
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "mes_instrument_id": int(mes_path.instrument_id.iloc[0]),
                "mcl_instrument_id": int(oil.instrument_id.iloc[-1]),
                "mgc_instrument_id": int(gold.instrument_id.iloc[-1]),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_dollars": gross,
            }
            for name, ticks in COST_CASES[1:]:
                trade[name] = _cost(gross, ticks)
            trades.append(trade)
            last_exit = exit_time
            counts["completed_trades"] += 1
    return trades, dict(counts)


def _metrics(trades: list[dict], case: str, year: int) -> dict:
    values = np.asarray([
        trade["gross_dollars"] if case == "raw_gross" else trade[case]
        for trade in trades
    ], dtype=float)
    gross_profit = float(values[values > 0].sum()) if len(values) else 0.0
    gross_loss = float(-values[values < 0].sum()) if len(values) else 0.0
    equity = np.r_[0.0, values.cumsum()]
    drawdown = float((np.maximum.accumulate(equity) - equity).max())
    monthly = {f"{year}-{month:02}": 0.0 for month in range(1, 13)}
    for trade, pnl in zip(trades, values):
        monthly[trade["date"][:7]] += float(pnl)
    monthly = {month: round(value, 6) for month, value in monthly.items()}
    net = float(values.sum())
    best_month = max(monthly.values()) if monthly else 0.0
    return {
        "trade_count": len(trades),
        "net_dollars": round(net, 6),
        "average_trade": round(float(values.mean()), 6) if len(values) else None,
        "gross_profit": round(gross_profit, 6),
        "gross_loss": round(gross_loss, 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "profit_factor_infinite": bool(gross_profit > 0 and gross_loss == 0),
        "maximum_drawdown": round(drawdown, 6),
        "net_to_drawdown": round(net / drawdown, 10) if drawdown else None,
        "best_month_removed_net": round(net - best_month, 6),
        "monthly_pnl": monthly,
    }


def summarize_cell(trades: list[dict], year: int, session_dates: list[str],
                   skips: dict, resamples: int) -> dict:
    first_half = round(sum(float(t["selection_2t"]) for t in trades
                           if t["date"][5:7] <= "06"), 6)
    second_half = round(sum(float(t["selection_2t"]) for t in trades
                            if t["date"][5:7] >= "07"), 6)
    return {
        "year": year,
        "fill_convention": "decision-minute MES open to exact hold-minute MES close; trade-print proxy",
        "cost_views": {name: _metrics(trades, name, year) for name, _ in COST_CASES},
        "active_months": sorted({trade["date"][:7] for trade in trades}),
        "first_half_selection_2t_net": first_half,
        "second_half_selection_2t_net": second_half,
        "long_trades": sum(int(trade["side"]) > 0 for trade in trades),
        "short_trades": sum(int(trade["side"]) < 0 for trade in trades),
        "day_cluster_bootstrap": v33.day_cluster_bootstrap(
            trades, session_dates, resamples=resamples, seed=BOOTSTRAP_SEED,
        ),
        "execution_counts": skips,
    }


def annual_passes(summary: dict) -> bool:
    two = summary["cost_views"]["selection_2t"]
    four = summary["cost_views"]["stress_4t"]
    pf = math.inf if two["profit_factor_infinite"] else float(two["profit_factor"] or 0.0)
    boot = summary["day_cluster_bootstrap"]
    return bool(
        two["trade_count"] >= MIN_TRADES
        and len(summary["active_months"]) >= MIN_ACTIVE_MONTHS
        and two["net_dollars"] > 0
        and two["average_trade"] is not None and two["average_trade"] >= 8.0
        and pf >= 1.20
        and two["best_month_removed_net"] > 0
        and summary["first_half_selection_2t_net"] > 0
        and summary["second_half_selection_2t_net"] > 0
        and four["net_dollars"] > 0
        and boot["lower_95"] is not None and boot["lower_95"] > 0
    )


def _selection_ratio(summary: dict) -> float:
    two = summary["cost_views"]["selection_2t"]
    drawdown = float(two["maximum_drawdown"])
    return math.inf if drawdown == 0 and two["net_dollars"] > 0 else (
        float(two["net_dollars"]) / drawdown if drawdown else -math.inf
    )


def cluster_audit(trades: list[dict], resamples: int) -> dict:
    dimensions = (
        ("time_block", ("morning", "midday", "afternoon")),
        ("risk_state", ("risk_on", "risk_off")),
        ("dominant_leg", ("oil", "gold")),
    )
    cohorts = []
    seed_offset = 0
    for field, values in dimensions:
        for value in values:
            seed_offset += 1
            cohort = [trade for trade in trades if trade[field] == value]
            year = int(cohort[0]["year"]) if cohort else 2023
            two = _metrics(cohort, "selection_2t", year)
            four = _metrics(cohort, "stress_4t", year)
            bootstrap = v39._condition_bootstrap(
                cohort, "selection_2t", BOOTSTRAP_SEED + seed_offset, resamples,
            )
            avoid = bool(
                len(cohort) >= 30 and four["net_dollars"] < 0
                and bootstrap["upper_95"] is not None and bootstrap["upper_95"] < 0
            )
            size = bool(
                len(cohort) >= 30 and four["net_dollars"] > 0
                and bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0
            )
            cohorts.append({
                "dimension": field,
                "value": value,
                "selection_2t": two,
                "stress_4t": four,
                "mean_trade_bootstrap": bootstrap,
                "avoid_lead": avoid,
                "size_lead": size,
                "action_authorized": False,
            })
    return {
        "cohorts": cohorts,
        "avoid_leads": [{"dimension": c["dimension"], "value": c["value"]}
                        for c in cohorts if c["avoid_lead"]],
        "size_leads": [{"dimension": c["dimension"], "value": c["value"]}
                       for c in cohorts if c["size_lead"]],
        "largest_win_streak": v39._streaks(trades, "selection_2t")["largest_win_streak"],
        "largest_loss_streak": v39._streaks(trades, "selection_2t")["largest_loss_streak"],
        "five_active_session_windows": v39._five_session_windows(trades, "selection_2t"),
        "second_generation_filter_authorized": False,
        "size_authorized": False,
    }


def _result_base(resamples: int) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "family": "intraday_crossasset_riskpulse",
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "size_authorized": False,
        "calendar_year_2026_sealed": True,
        "years_loaded": [],
        "source_cache": {},
        "signal": {
            "inputs": ["MCL 30-minute return", "MGC 30-minute return"],
            "decision_grid_ct": [f"{minute // 60:02}:{minute % 60:02}" for minute in DECISION_MINUTES],
            "opposed_sign_only": True,
            "mes_price_in_signal": False,
        },
        "family_parameters": {"hold_minutes": list(HOLDS), "cells": len(HOLDS)},
        "execution": {
            "evidence": "one-minute trade-print OHLC proxy; executable bid/ask and latency not verified",
            "round_trip_fee": ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": resamples},
        "verdict": "NOT_RUN",
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Run the frozen sequential firewall; later years stay physically unopened."""
    frames: dict[str, dict[int, pd.DataFrame]] = {symbol: {} for symbol in SYMBOLS}
    result = _result_base(bootstrap_resamples)

    def load_year(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v43 may read only 2023-2025")
        for symbol in SYMBOLS:
            frame = loader(symbol, year)
            frames[symbol][year] = frame
            key = frame.attrs.get("source_cache_key")
            sha = frame.attrs.get("source_sha256")
            if key is not None and sha is not None:
                result["source_cache"][f"{symbol}-{year}"] = {
                    "cache_key": str(key), "sha256": str(sha),
                }
        result["years_loaded"].append(year)

    def current_sessions() -> tuple[list[TripleSession], dict[int, dict[str, int]]]:
        years = sorted(frames["MES"])
        return build_sessions({
            symbol: [frames[symbol][year] for year in years]
            for symbol in SYMBOLS
        })

    load_year(2023)
    sessions, exclusions = current_sessions()
    discovery_cells = []
    trades_by_hold: dict[int, list[dict]] = {}
    dates_2023 = [session.date for session in sessions if session.date.startswith("2023-")]
    for hold in HOLDS:
        trades, skips = generate_trades(sessions, 2023, hold)
        summary = summarize_cell(trades, 2023, dates_2023, skips, bootstrap_resamples)
        discovery_cells.append({
            "parameters": {"hold_minutes": hold},
            "eligible": annual_passes(summary),
            "selection_net_to_drawdown": round(_selection_ratio(summary), 10)
            if math.isfinite(_selection_ratio(summary)) else None,
            "metrics": summary,
        })
        trades_by_hold[hold] = trades
    eligible = [cell for cell in discovery_cells if cell["eligible"]]
    order = {hold: index for index, hold in enumerate(HOLDS)}
    ranking_pool = eligible or discovery_cells
    leader = sorted(ranking_pool, key=lambda cell: (
        -_selection_ratio(cell["metrics"]),
        -float(cell["metrics"]["cost_views"]["selection_2t"]["average_trade"] or -math.inf),
        order[cell["parameters"]["hold_minutes"]],
    ))[0]
    leader_hold = int(leader["parameters"]["hold_minutes"])
    result["session_exclusions"] = {str(k): v for k, v in exclusions.items()}
    result["discovery_2023"] = {
        "cells": discovery_cells,
        "selected": leader if eligible else None,
        "diagnostic_leader": leader,
        "cluster_audit": cluster_audit(trades_by_hold[leader_hold], bootstrap_resamples),
    }
    if not eligible:
        result["verdict"] = "FAMILY_FAIL_DISCOVERY"
        result["firewall"] = "2024 and 2025 unopened because no 2023 hold qualified"
        return result, trades_by_hold[leader_hold]

    selected = leader
    ledger = list(trades_by_hold[leader_hold])
    load_year(2024)
    sessions, exclusions = current_sessions()
    dates_2024 = [session.date for session in sessions if session.date.startswith("2024-")]
    trades_2024, skips_2024 = generate_trades(sessions, 2024, leader_hold)
    summary_2024 = summarize_cell(
        trades_2024, 2024, dates_2024, skips_2024, bootstrap_resamples,
    )
    result["session_exclusions"] = {str(k): v for k, v in exclusions.items()}
    result["validation_2024"] = {
        "passed": annual_passes(summary_2024),
        "parameters": selected["parameters"],
        "metrics": summary_2024,
        "cluster_audit": cluster_audit(trades_2024, bootstrap_resamples),
    }
    ledger.extend(trades_2024)
    if not result["validation_2024"]["passed"]:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged 2023 selection failed 2024"
        return result, ledger

    load_year(2025)
    sessions, exclusions = current_sessions()
    dates_2025 = [session.date for session in sessions if session.date.startswith("2025-")]
    trades_2025, skips_2025 = generate_trades(sessions, 2025, leader_hold)
    summary_2025 = summarize_cell(
        trades_2025, 2025, dates_2025, skips_2025, bootstrap_resamples,
    )
    result["session_exclusions"] = {str(k): v for k, v in exclusions.items()}
    result["validation_2025"] = {
        "passed": annual_passes(summary_2025),
        "parameters": selected["parameters"],
        "metrics": summary_2025,
        "cluster_audit": cluster_audit(trades_2025, bootstrap_resamples),
    }
    ledger.extend(trades_2025)
    if not result["validation_2025"]["passed"]:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "unchanged cross-asset rule rejected by 2025 confirmation"
        return result, ledger

    combined = v33.day_cluster_bootstrap(
        trades_2024 + trades_2025, dates_2024 + dates_2025,
        resamples=bootstrap_resamples, seed=BOOTSTRAP_SEED,
    )
    result["final_audit"] = {"combined_validation_day_bootstrap": combined}
    if combined["lower_95"] is not None and combined["lower_95"] > 0:
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = (
            "requires executable MES bid/ask calibration and forward paper fills; size remains unauthorized"
        )
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "historical family rejected by combined 2024-2025 day bootstrap"
    return result, ledger


def postgres_loader(database_url: str) -> tuple[Callable[[str, int], pd.DataFrame], Callable[[], None]]:
    """Create a checksum-validating loader inside one read-only transaction."""
    import psycopg2

    connection = psycopg2.connect(database_url, connect_timeout=15)
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor()

    def load(symbol: str, year: int) -> pd.DataFrame:
        if symbol not in SYMBOLS or year not in ALLOWED_YEARS:
            raise ValueError("only MES/MCL/MGC 2023-2025 cache rows are permitted")
        key = f"GLBX.MDP3:ohlcv-1m:{symbol}.v.0:{year}"
        cursor.execute(
            "SELECT sha256, parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"missing cache row {key}")
        body = bytes(row[1])
        observed = hashlib.sha256(body).hexdigest()
        if observed != str(row[0]):
            raise ValueError(f"cache checksum mismatch {key}")
        frame = pd.read_parquet(io.BytesIO(body))
        frame.attrs["source_cache_key"] = key
        frame.attrs["source_sha256"] = observed
        return frame

    def close() -> None:
        try:
            connection.rollback()
        finally:
            cursor.close()
            connection.close()

    return load, close


def write_outputs(result: dict, ledger: list[dict], json_out: Path,
                  ledger_out: Path) -> None:
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


def persist_result(database_url: str, result: dict, ledger: list[dict]) -> None:
    """Persist immutable v43 research evidence; never touch trading tables."""
    import psycopg2
    from psycopg2.extras import Json

    source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ledger_body = gzip.compress(
        json.dumps(ledger, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode(),
        mtime=0,
    )
    connection = psycopg2.connect(database_url, connect_timeout=15)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS valor_mes_v43_results (
                        study_id text PRIMARY KEY,
                        source_sha256 text NOT NULL,
                        result jsonb NOT NULL,
                        ledger_gzip bytea NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cursor.execute(
                    "SELECT source_sha256, result FROM valor_mes_v43_results WHERE study_id=%s",
                    (STUDY_ID,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if str(existing[0]) != source_sha:
                        raise RuntimeError("completed v43 exists with a different source hash")
                    if existing[1] != result:
                        raise RuntimeError("completed v43 source matches but result differs")
                    return
                cursor.execute("""
                    INSERT INTO valor_mes_v43_results
                        (study_id, source_sha256, result, ledger_gzip)
                    VALUES (%s, %s, %s, %s)
                """, (
                    STUDY_ID, source_sha, Json(result), psycopg2.Binary(ledger_body),
                ))
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path,
                        default=Path("docs/valor_mes_v43/result.json"))
    parser.add_argument("--ledger-out", type=Path,
                        default=Path("docs/valor_mes_v43/ledger.csv"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--bootstrap-resamples", type=int,
                        default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if args.bootstrap_resamples <= 0:
        parser.error("--bootstrap-resamples must be positive")
    loader, close = postgres_loader(args.database_url)
    try:
        result, ledger = run_study(loader, args.bootstrap_resamples)
    finally:
        close()
    write_outputs(result, ledger, args.json_out, args.ledger_out)
    if not args.no_persist:
        persist_result(args.database_url, result, ledger)
    print(json.dumps({
        "study_id": STUDY_ID,
        "verdict": result["verdict"],
        "years_loaded": result["years_loaded"],
        "calendar_year_2026_sealed": result["calendar_year_2026_sealed"],
        "live_ready": result["live_ready"],
        "size_authorized": result["size_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
