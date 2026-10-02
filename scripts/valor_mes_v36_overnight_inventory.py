"""Frozen MES v36 overnight-inventory research.

Research only. Reads existing checksummed MES minute bars in a read-only
transaction, never requests vendor data, and refuses calendar year 2026.
Reported fills are trade-print planning proxies, not executable quotes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import argparse
import csv
import json
import math
import os
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33


SCHEMA_VERSION = "valor-mes-v36-result/1.0.0"
STRATEGY_VERSION = "v36"
STUDY_ID = "valor-mes-v36-overnight-inventory-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
MODES = ("confirmed_continuation", "opening_rejection")
MAGNITUDES = (0.25, 0.50)
EFFICIENCIES = (0.05, 0.10)
HOLDS = (30, 60, 120)
CELL_ORDER = tuple((mode, magnitude, efficiency, hold)
                   for mode in MODES
                   for magnitude in MAGNITUDES
                   for efficiency in EFFICIENCIES
                   for hold in HOLDS)
ATR_SESSIONS = 20
BOOTSTRAP_SEED = 360036
BOOTSTRAP_RESAMPLES = 10_000
CT = ZoneInfo("America/Chicago")
LEDGER_FIELDS = (
    "year", "date", "mode", "magnitude_atr_threshold",
    "efficiency_threshold", "hold_minutes", "side", "instrument_id",
    "atr_prior", "overnight_move", "overnight_move_atr",
    "overnight_efficiency", "last_hour_return", "opening_response",
    "overnight_first", "overnight_last", "decision_time", "entry_time",
    "exit_time", "entry_price", "exit_price", "gross_dollars", "fee_0t",
    "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class FeatureSession:
    date: str
    cash: pd.DataFrame
    instrument_id: int
    atr_prior: float
    overnight_move: float
    overnight_efficiency: float
    last_hour_return: float
    opening_response: float
    overnight_first: pd.Timestamp
    overnight_last: pd.Timestamp


def _raw_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "timestamp" in frame:
        source = frame["timestamp"]
    elif "ts_event" in frame:
        source = frame["ts_event"]
    else:
        reset = frame.reset_index()
        if "ts_event" not in reset:
            raise ValueError("timestamp or ts_event required")
        source = reset["ts_event"]
    timestamp = pd.to_datetime(source, utc=True)
    if not timestamp.is_monotonic_increasing:
        raise ValueError("raw timestamps must be monotonic")
    return timestamp


def prepare_raw(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    normalized = []
    for frame in frames:
        item = frame
        if ("timestamp" not in item and "ts_event" not in item
                and item.index.name in {"timestamp", "ts_event"}):
            item = item.reset_index()
        normalized.append(item)
    raw = pd.concat(normalized, ignore_index=True)
    _raw_timestamp(raw)
    return v33.cash.prepare(raw, v33.TICK_SIZE)


def _overnight_bounds(day: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    cash_day = date.fromisoformat(day)
    previous = cash_day - timedelta(days=1)
    start = pd.Timestamp(datetime.combine(previous, time(17, 0), tzinfo=CT)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(cash_day, time(8, 29), tzinfo=CT)).tz_convert("UTC")
    return start, end


def overnight_window(prepared: pd.DataFrame, day: str,
                     instrument_id: int) -> tuple[pd.DataFrame | None, str | None]:
    """Validate one observed-bar overnight window without forward filling."""
    start, end = _overnight_bounds(day)
    window = prepared[(prepared.timestamp >= start) & (prepared.timestamp <= end)].copy()
    window = window.sort_values("timestamp").reset_index(drop=True)
    if window.empty:
        return None, "overnight_missing"
    if pd.Timestamp(window.timestamp.iloc[0]) > start + pd.Timedelta(minutes=5):
        return None, "overnight_first_after_1705"
    if pd.Timestamp(window.timestamp.iloc[-1]) != end:
        return None, "overnight_missing_0829"
    if len(window) < 900:
        return None, "overnight_under_900_minutes"
    final_hour = window[(window.timestamp >= end - pd.Timedelta(minutes=59))]
    if len(final_hour) < 55:
        return None, "overnight_final_hour_under_55"
    if not window.timestamp.is_monotonic_increasing or window.timestamp.duplicated().any():
        return None, "overnight_nonmonotonic"
    if window.instrument_id.nunique(dropna=False) != 1:
        return None, "overnight_contract_change"
    if int(window.instrument_id.iloc[0]) != int(instrument_id):
        return None, "overnight_cash_contract_mismatch"
    return window, None


def prior_atr(cash_sessions: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Assign prior-20-session ATR, resetting when the exact contract changes."""
    result: dict[str, float] = {}
    prior_contract: int | None = None
    prior_close: float | None = None
    true_ranges: list[float] = []
    for day in sorted(cash_sessions):
        frame = cash_sessions[day]
        contract = int(frame.instrument_id.iloc[0])
        if contract != prior_contract:
            true_ranges = []
            prior_close = None
        if len(true_ranges) >= ATR_SESSIONS:
            value = float(np.mean(true_ranges[-ATR_SESSIONS:]))
            if math.isfinite(value) and value > 0:
                result[day] = value
        high, low = float(frame.high.max()), float(frame.low.min())
        if prior_close is not None:
            true_range = max(high - low, abs(high - prior_close), abs(low - prior_close))
            if math.isfinite(true_range) and true_range > 0:
                true_ranges.append(true_range)
            else:
                true_ranges = []
        prior_contract = contract
        prior_close = float(frame.close.iloc[-1])
    return result


def _calendar_days(year: int) -> list[str]:
    day = date(year, 1, 1)
    end = date(year, 12, 31)
    output = []
    while day <= end:
        if v33.cash.session(day) is not None:
            output.append(day.isoformat())
        day += timedelta(days=1)
    return output


def build_features(frames: Iterable[pd.DataFrame]) -> tuple[list[FeatureSession], dict[int, dict[str, int]]]:
    """Build causal daily features and mutually exclusive exclusion counts."""
    prepared = prepare_raw(frames)
    complete_cash = v33._complete_sessions(prepared)
    atr = prior_atr(complete_cash)
    years = sorted({int(day[:4]) for day in prepared.date.unique()
                    if int(day[:4]) in ALLOWED_YEARS})
    exclusions = {year: Counter() for year in years}
    features: list[FeatureSession] = []
    for year in years:
        for day in _calendar_days(year):
            cash_frame = complete_cash.get(day)
            if cash_frame is None:
                exclusions[year]["incomplete_cash_session"] += 1
                continue
            contract = int(cash_frame.instrument_id.iloc[0])
            overnight, reason = overnight_window(prepared, day, contract)
            if reason is not None:
                exclusions[year][reason] += 1
                continue
            atr_value = atr.get(day)
            if atr_value is None:
                exclusions[year]["prior_atr_unavailable"] += 1
                continue
            assert overnight is not None
            opening = cash_frame.iloc[:5]
            if (len(opening) != 5
                    or int(opening.minute.iloc[0]) != 510
                    or int(opening.minute.iloc[-1]) != 514):
                exclusions[year]["opening_five_unavailable"] += 1
                continue
            first_open = float(overnight.open.iloc[0])
            last_close = float(overnight.close.iloc[-1])
            changes = np.r_[
                abs(float(overnight.close.iloc[0]) - first_open),
                np.abs(np.diff(overnight.close.to_numpy(float))),
            ]
            path = float(changes.sum())
            move = last_close - first_open
            efficiency = abs(move) / path if path > 0 else 0.0
            _, overnight_end = _overnight_bounds(day)
            final_hour = overnight[overnight.timestamp >= overnight_end - pd.Timedelta(minutes=59)]
            last_hour_return = last_close - float(final_hour.close.iloc[0])
            opening_response = float(opening.close.iloc[-1]) - float(opening.open.iloc[0])
            features.append(FeatureSession(
                date=day, cash=cash_frame, instrument_id=contract,
                atr_prior=atr_value, overnight_move=move,
                overnight_efficiency=efficiency,
                last_hour_return=last_hour_return,
                opening_response=opening_response,
                overnight_first=pd.Timestamp(overnight.timestamp.iloc[0]),
                overnight_last=pd.Timestamp(overnight.timestamp.iloc[-1]),
            ))
            exclusions[year]["usable_sessions"] += 1
    return features, {year: dict(counts) for year, counts in exclusions.items()}


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def signal_side(feature: FeatureSession, mode: str) -> int:
    overnight = _sign(feature.overnight_move)
    final_hour = _sign(feature.last_hour_return)
    opening = _sign(feature.opening_response)
    if mode == "confirmed_continuation":
        return overnight if overnight != 0 and overnight == final_hour == opening else 0
    if mode == "opening_rejection":
        return opening if overnight != 0 and opening != 0 and opening == -overnight else 0
    raise ValueError("mode outside frozen v36 family")


def generate_trades(features: list[FeatureSession], year: int, mode: str,
                    magnitude: float, efficiency: float, hold: int) -> list[dict]:
    if (mode, magnitude, efficiency, hold) not in CELL_ORDER:
        raise ValueError("cell outside frozen v36 family")
    trades: list[dict] = []
    for feature in features:
        if int(feature.date[:4]) != year:
            continue
        move_atr = abs(feature.overnight_move) / feature.atr_prior
        if move_atr < magnitude or feature.overnight_efficiency < efficiency:
            continue
        side = signal_side(feature, mode)
        if side == 0:
            continue
        cash_frame = feature.cash
        entry_position = 5
        exit_position = entry_position + hold - 1
        if exit_position >= len(cash_frame):
            continue
        entry_time = pd.Timestamp(cash_frame.timestamp.iloc[entry_position])
        exit_time = pd.Timestamp(cash_frame.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
        policy = v33.cash.session(feature.date)
        if policy is None or exit_time > pd.Timestamp(policy[2]).tz_convert("UTC"):
            continue
        path = cash_frame.iloc[entry_position:exit_position + 1]
        if (len(path) != hold or path.instrument_id.nunique(dropna=False) != 1
                or int(path.instrument_id.iloc[0]) != feature.instrument_id):
            continue
        expected = pd.date_range(entry_time, periods=hold, freq="1min")
        if not pd.DatetimeIndex(path.timestamp).equals(expected):
            continue
        entry_price, exit_price = float(path.open.iloc[0]), float(path.close.iloc[-1])
        gross = round(side * (exit_price - entry_price) * v33.POINT_VALUE, 6)
        trade = {
            "year": year, "date": feature.date, "mode": mode,
            "magnitude_atr_threshold": magnitude,
            "efficiency_threshold": efficiency, "hold_minutes": hold,
            "side": side, "instrument_id": feature.instrument_id,
            "atr_prior": round(feature.atr_prior, 10),
            "overnight_move": round(feature.overnight_move, 10),
            "overnight_move_atr": round(move_atr, 10),
            "overnight_efficiency": round(feature.overnight_efficiency, 10),
            "last_hour_return": round(feature.last_hour_return, 10),
            "opening_response": round(feature.opening_response, 10),
            "overnight_first": feature.overnight_first.isoformat(),
            "overnight_last": feature.overnight_last.isoformat(),
            "decision_time": (pd.Timestamp(cash_frame.timestamp.iloc[4]) + pd.Timedelta(minutes=1)).isoformat(),
            "entry_time": entry_time.isoformat(), "exit_time": exit_time.isoformat(),
            "entry_price": entry_price, "exit_price": exit_price,
            "gross_dollars": gross,
        }
        for name, ticks in v33.COST_CASES[1:]:
            trade[name] = v33._cost(gross, ticks)
        trades.append(trade)
    return trades


def discovery_eligible(summary: dict) -> bool:
    two, four = (summary["cost_views"][name] for name in ("selection_2t", "stress_4t"))
    return (
        two["trade_count"] >= 80 and two["net_dollars"] > 0
        and v33._profit_factor_value(two) >= 1.10
        and two["average_trade"] is not None and two["average_trade"] >= 8
        and four["net_dollars"] > 0
    )


def confirmation_passes(summary: dict) -> bool:
    two, four = (summary["cost_views"][name] for name in ("selection_2t", "stress_4t"))
    return (
        two["trade_count"] >= 60 and two["net_dollars"] > 0
        and v33._profit_factor_value(two) >= 1.10
        and two["average_trade"] is not None and two["average_trade"] >= 8
        and four["net_dollars"] > 0
    )


def _ratio(summary: dict) -> float:
    two = summary["cost_views"]["selection_2t"]
    drawdown = float(two["maximum_drawdown"])
    return math.inf if drawdown == 0 else float(two["net_dollars"]) / drawdown


def evaluate_discovery(features: list[FeatureSession]) -> tuple[list[dict], dict | None, list[dict]]:
    cells, trades_by_cell = [], {}
    for cell in CELL_ORDER:
        mode, magnitude, efficiency, hold = cell
        trades = generate_trades(features, 2023, *cell)
        summary = v33.summarize_cell(trades, 2023)
        eligible = discovery_eligible(summary)
        ratio = _ratio(summary) if eligible else None
        cells.append({
            "parameters": {"mode": mode, "magnitude_atr": magnitude,
                           "efficiency": efficiency, "hold_minutes": hold},
            "eligible": eligible,
            "selection_net_to_drawdown": None if ratio is None or math.isinf(ratio) else round(ratio, 10),
            "selection_net_to_drawdown_infinite": bool(ratio is not None and math.isinf(ratio)),
            "metrics": summary,
        })
        trades_by_cell[cell] = trades
    eligible_cells = [cell for cell in cells if cell["eligible"]]
    if not eligible_cells:
        return cells, None, []
    order = {cell: index for index, cell in enumerate(CELL_ORDER)}
    selected = sorted(eligible_cells, key=lambda cell: (
        -_ratio(cell["metrics"]),
        -float(cell["metrics"]["cost_views"]["selection_2t"]["average_trade"]),
        order[(cell["parameters"]["mode"], cell["parameters"]["magnitude_atr"],
               cell["parameters"]["efficiency"], cell["parameters"]["hold_minutes"])],
    ))[0]
    p = selected["parameters"]
    key = (p["mode"], p["magnitude_atr"], p["efficiency"], p["hold_minutes"])
    return cells, selected, trades_by_cell[key]


def evaluate_selected(features: list[FeatureSession], year: int,
                      parameters: dict) -> tuple[dict, list[dict]]:
    trades = generate_trades(
        features, year, parameters["mode"], parameters["magnitude_atr"],
        parameters["efficiency"], parameters["hold_minutes"],
    )
    return v33.summarize_cell(trades, year), trades


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID, "research_only": True,
        "production_changed": False, "live_ready": False,
        "calendar_year_2026_sealed": True,
        "family": {"modes": list(MODES), "magnitude_atr": list(MAGNITUDES),
                   "efficiencies": list(EFFICIENCIES), "holds_minutes": list(HOLDS),
                   "cells": len(CELL_ORDER)},
        "execution": {
            "fill_convention": "08:35 MES open to exact hold-minute MES close",
            "evidence": "trade-print proxy; executable bid/ask and latency not verified",
            "round_trip_fee": v33.ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "years_loaded": [], "session_exclusions": {}, "verdict": None,
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    frames: dict[int, pd.DataFrame] = {}
    result, ledger = _result_base(), []

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v36 may read only 2023-2025")
        frames[year] = loader("MES", year)
        result["years_loaded"].append(year)

    load(2023)
    features, exclusions = build_features([frames[year] for year in sorted(frames)])
    result["session_exclusions"].update({str(k): v for k, v in exclusions.items()})
    cells, selected, trades_2023 = evaluate_discovery(features)
    result["discovery_2023"] = {"cells": cells, "selected": selected}
    if selected is None:
        result["verdict"] = "FAMILY_FAIL_DISCOVERY"
        result["firewall"] = "2024 and 2025 unopened because no 2023 cell qualified"
        return result, []

    parameters = selected["parameters"]
    ledger.extend(trades_2023)
    load(2024)
    features, exclusions = build_features([frames[year] for year in sorted(frames)])
    result["session_exclusions"].update({str(k): v for k, v in exclusions.items()})
    validation_2024, trades_2024 = evaluate_selected(features, 2024, parameters)
    passed_2024 = confirmation_passes(validation_2024)
    result["validation_2024"] = {"passed": passed_2024, "metrics": validation_2024}
    ledger.extend(trades_2024)
    if not passed_2024:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged selected cell failed 2024"
        return result, ledger

    load(2025)
    features, exclusions = build_features([frames[year] for year in sorted(frames)])
    result["session_exclusions"].update({str(k): v for k, v in exclusions.items()})
    validation_2025, trades_2025 = evaluate_selected(features, 2025, parameters)
    passed_2025 = confirmation_passes(validation_2025)
    result["validation_2025"] = {"passed": passed_2025, "metrics": validation_2025}
    ledger.extend(trades_2025)
    if not passed_2025:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "historical family rejected by independent 2025 confirmation"
        return result, ledger

    validation_dates = [feature.date for feature in features
                        if feature.date[:4] in {"2024", "2025"}]
    bootstrap = v33.day_cluster_bootstrap(
        trades_2024 + trades_2025, validation_dates,
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


def write_outputs(result: dict, ledger: list[dict], json_out: Path,
                  ledger_out: Path) -> None:
    json_out, ledger_out = Path(json_out), Path(ledger_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    ledger_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
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
