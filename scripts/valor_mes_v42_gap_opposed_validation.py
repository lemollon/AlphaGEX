"""Frozen MES v42 gap-opposed holdout validation.

Research only. Validates one v41 cluster lead on 2024 first and opens 2025 only
after a pass. Calendar 2026 is refused. No vendor or broker call is permitted.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import os
from typing import Callable

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v39_overnight_sweep as v39
from scripts import valor_mes_v40_vwap_reversion as v40
from scripts import valor_mes_v41_opening_range_retest as v41


SCHEMA_VERSION = "valor-mes-v42-result/1.0.0"
STRATEGY_VERSION = "v42"
STUDY_ID = "valor-mes-v42-gap-opposed-validation-20260926"
ALLOWED_YEARS = (2023, 2024, 2025)
BUFFER_ATR = 0.10
TARGET_R = 1.5
HOLD_MINUTES = 120
GAP_ALIGNMENT = "opposed"
MIN_TRADES = 40
MIN_ACTIVE_MONTHS = 6
BOOTSTRAP_SEED = 420042
BOOTSTRAP_RESAMPLES = 10_000


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "family": "v41_gap_opposed_holdout_validation",
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "size_authorized": False,
        "calendar_year_2026_sealed": True,
        "years_loaded": [],
        "evaluation_years": [],
        "source_cache": {},
        "fixed_rule": {
            "breakout_buffer_atr": BUFFER_ATR,
            "target_r": TARGET_R,
            "hold_minutes": HOLD_MINUTES,
            "gap_alignment": GAP_ALIGNMENT,
        },
        "discovery_provenance": {
            "source_study": v41.STUDY_ID,
            "year": 2023,
            "trade_count": 41,
            "selection_2t_net": 797.0,
            "selection_2t_average": 19.439024,
            "selection_2t_profit_factor": 2.307093,
            "stress_4t_net": 592.0,
            "bootstrap_lower_95": 3.158537,
            "role": "prior discovery only; v42 selects no parameter from 2023",
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "execution": {
            "evidence": "one-minute trade-print OHLC proxy; executable bid/ask and latency not verified",
            "round_trip_fee": v41.ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "verdict": "NOT_RUN",
    }


def _filter_events(events: list[dict], year: int) -> list[dict]:
    return [
        event for event in events
        if int(event["year"]) == year
        and float(event["breakout_buffer_atr"]) == BUFFER_ATR
        and str(event.get("gap_alignment")) == GAP_ALIGNMENT
    ]


def _annual_audit(sessions: list[v39.SessionContext], events: list[dict],
                  year: int, resamples: int) -> tuple[dict, list[dict]]:
    filtered_events = _filter_events(events, year)
    trades, replay = v41.replay_cell(
        sessions, filtered_events, year, BUFFER_ATR, TARGET_R, HOLD_MINUTES,
    )
    summary = v41.summarize_cell(
        trades, year, replay, (BUFFER_ATR, TARGET_R, HOLD_MINUTES),
    )
    selection = summary["cost_views"]["selection_2t"]
    stress = summary["cost_views"]["stress_4t"]
    ratio = selection["net_to_drawdown"]
    pf = selection["profit_factor"]
    months = sorted({trade["date"][:7] for trade in trades})
    first_half_net = round(sum(
        float(trade["selection_2t"])
        for trade in trades if trade["date"][5:7] <= "06"
    ), 6)
    second_half_net = round(sum(
        float(trade["selection_2t"])
        for trade in trades if trade["date"][5:7] >= "07"
    ), 6)
    bootstrap = v39._condition_bootstrap(
        trades, "selection_2t", BOOTSTRAP_SEED, resamples,
    )
    passed = bool(
        selection["trade_count"] >= MIN_TRADES
        and len(months) >= MIN_ACTIVE_MONTHS
        and selection["net_dollars"] > 0
        and pf is not None and pf >= 1.40
        and selection["average_trade"] is not None
        and selection["average_trade"] >= 12.0
        and ratio is not None and ratio >= 0.75
        and selection["best_month_removed_net"] > 0
        and stress["net_dollars"] > 0
        and first_half_net > 0
        and second_half_net > 0
        and bootstrap["lower_95"] is not None
        and bootstrap["lower_95"] > 0
    )
    return {
        "year": year,
        "passed": passed,
        "metrics": summary,
        "active_months": months,
        "first_half_selection_2t_net": first_half_net,
        "second_half_selection_2t_net": second_half_net,
        "active_session_mean_trade_bootstrap": bootstrap,
        "descriptive_streaks": v39._streaks(trades, "selection_2t"),
        "descriptive_five_active_session_windows": v39._five_session_windows(
            trades, "selection_2t",
        ),
        "second_generation_filter_authorized": False,
    }, trades


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Validate 2024 first; never open 2025 after a failed 2024."""
    frames: dict[int, pd.DataFrame] = {}
    result = _result_base()
    result["bootstrap"]["resamples"] = bootstrap_resamples

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v42 may read only 2023-2025")
        frame = loader("MES", year)
        frames[year] = frame
        cache_key = frame.attrs.get("source_cache_key")
        source_sha = frame.attrs.get("source_sha256")
        if cache_key is not None and source_sha is not None:
            result["source_cache"][str(year)] = {
                "cache_key": str(cache_key), "sha256": str(source_sha),
            }
        result["years_loaded"].append(year)

    def prepared() -> tuple[list[v39.SessionContext], list[dict], dict, dict]:
        sessions, session_exclusions = v39.build_sessions(
            [frames[year] for year in sorted(frames)]
        )
        events, event_counts = v41.build_events(sessions)
        return sessions, events, session_exclusions, event_counts

    load(2023)
    load(2024)
    sessions, events, session_exclusions, event_counts = prepared()
    result["evaluation_years"].append(2024)
    validation_2024, trades_2024 = _annual_audit(
        sessions, events, 2024, bootstrap_resamples,
    )
    validation_2024["session_exclusions"] = session_exclusions.get(2024, {})
    validation_2024["event_counts"] = event_counts.get(2024, {})
    result["validation_2024"] = validation_2024
    if not validation_2024["passed"]:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the fixed v41 cluster failed 2024"
        return result, trades_2024

    load(2025)
    sessions, events, session_exclusions, event_counts = prepared()
    result["evaluation_years"].append(2025)
    validation_2025, trades_2025 = _annual_audit(
        sessions, events, 2025, bootstrap_resamples,
    )
    validation_2025["session_exclusions"] = session_exclusions.get(2025, {})
    validation_2025["event_counts"] = event_counts.get(2025, {})
    result["validation_2025"] = validation_2025
    ledger = trades_2024 + trades_2025
    if not validation_2025["passed"]:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "fixed cluster rejected by unchanged 2025 confirmation"
        return result, ledger

    validation_dates = [
        session.date for session in sessions
        if session.date[:4] in {"2024", "2025"}
    ]
    combined_bootstrap = v33.day_cluster_bootstrap(
        ledger, validation_dates, resamples=bootstrap_resamples,
        seed=BOOTSTRAP_SEED,
    )
    annual_counts = [
        validation_2024["metrics"]["cost_views"]["selection_2t"]["trade_count"],
        validation_2025["metrics"]["cost_views"]["selection_2t"]["trade_count"],
    ]
    average_frequency = float(np.mean(annual_counts))
    result["final_audit"] = {
        "annual_trade_counts": annual_counts,
        "average_validation_trades_per_year": round(average_frequency, 6),
        "frequency_passed": average_frequency >= MIN_TRADES,
        "combined_validation_day_bootstrap": combined_bootstrap,
        "size_authorized": False,
    }
    if (average_frequency >= MIN_TRADES
            and combined_bootstrap["lower_95"] is not None
            and combined_bootstrap["lower_95"] > 0):
        result["verdict"] = "HISTORICAL_CLUSTER_CANDIDATE"
        result["firewall"] = (
            "requires untouched 2026, executable fill calibration, and forward shadow evidence"
        )
    elif average_frequency < MIN_TRADES:
        result["verdict"] = "FAILED_FREQUENCY_GATE"
        result["firewall"] = "fixed cluster rejected by validation frequency gate"
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "fixed cluster rejected by combined validation bootstrap"
    return result, ledger


def write_outputs(result: dict, ledger: list[dict], json_out: Path,
                  ledger_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    ledger_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    fields = sorted({key for row in ledger for key in row})
    with ledger_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ledger)


def persist_result(database_url: str, result: dict, ledger: list[dict]) -> None:
    """Persist immutable v42 evidence only; never touch trading tables."""
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
                    CREATE TABLE IF NOT EXISTS valor_mes_v42_results (
                        study_id text PRIMARY KEY,
                        source_sha256 text NOT NULL,
                        result jsonb NOT NULL,
                        ledger_gzip bytea NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cursor.execute(
                    "SELECT source_sha256, result FROM valor_mes_v42_results WHERE study_id=%s",
                    (STUDY_ID,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if str(existing[0]) != source_sha:
                        raise RuntimeError(
                            "completed v42 exists with a different source hash"
                        )
                    if existing[1] != result:
                        raise RuntimeError(
                            "completed v42 source matches but result differs"
                        )
                    return
                cursor.execute("""
                    INSERT INTO valor_mes_v42_results
                        (study_id, source_sha256, result, ledger_gzip)
                    VALUES (%s, %s, %s, %s)
                """, (
                    STUDY_ID, source_sha, Json(result),
                    psycopg2.Binary(ledger_body),
                ))
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path,
                        default=Path("docs/valor_mes_v42/result.json"))
    parser.add_argument("--ledger-out", type=Path,
                        default=Path("docs/valor_mes_v42/ledger.csv"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--bootstrap-resamples", type=int,
                        default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if args.bootstrap_resamples <= 0:
        parser.error("--bootstrap-resamples must be positive")
    loader, close = v40.postgres_loader(args.database_url)
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
        "evaluation_years": result["evaluation_years"],
        "calendar_year_2026_sealed": result["calendar_year_2026_sealed"],
        "live_ready": result["live_ready"],
        "size_authorized": result["size_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
