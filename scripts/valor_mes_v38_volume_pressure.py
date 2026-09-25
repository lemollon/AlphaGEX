"""Frozen MES v38 opening volume-pressure/price-response research.

The pressure measure is an OHLCV close-location proxy, not true aggressor flow.
Research only: this command reads existing checksummed MES cache rows through a
read-only transaction, never calls a vendor or broker, and refuses 2026.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
import argparse
import csv
import json
import math
import os
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v36_overnight_inventory as v36


SCHEMA_VERSION = "valor-mes-v38-result/1.0.0"
STRATEGY_VERSION = "v38"
STUDY_ID = "valor-mes-v38-volume-pressure-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
MODES = ("flow_follow", "absorption_reversal")
REGIMES = ("all", "causal_high")
HOLDS = (30, 60, 120, 240)
CELL_ORDER = tuple((mode, regime, hold)
                   for mode in MODES for regime in REGIMES for hold in HOLDS)
ROLLING_SESSIONS = 60
BOOTSTRAP_SEED = 380038
BOOTSTRAP_RESAMPLES = 10_000
LEDGER_FIELDS = (
    "year", "date", "mode", "pressure_regime", "hold_minutes", "side",
    "signed_volume_proxy", "opening_price_response", "prior_60_abs_median",
    "observation_volume", "decision_time", "entry_time", "exit_time",
    "instrument_id", "entry_price", "exit_price", "gross_dollars", "fee_0t",
    "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class VolumeFeature:
    date: str
    cash: pd.DataFrame
    instrument_id: int
    signed_volume_proxy: float
    opening_price_response: float
    observation_volume: float
    prior_60_abs_median: float | None = None


def bar_clv(frame: pd.DataFrame) -> np.ndarray:
    """Return close-location values, defining zero-range bars as exactly zero."""
    high = frame.high.to_numpy(float)
    low = frame.low.to_numpy(float)
    close = frame.close.to_numpy(float)
    spread = high - low
    result = np.zeros(len(frame), dtype=float)
    nonzero = spread != 0
    result[nonzero] = ((close[nonzero] - low[nonzero])
                       - (high[nonzero] - close[nonzero])) / spread[nonzero]
    return result


def assign_prior_medians(features: list[VolumeFeature]) -> list[VolumeFeature]:
    """Attach the median of 60 strictly prior usable sessions."""
    ordered = sorted(features, key=lambda feature: feature.date)
    output = []
    for index, feature in enumerate(ordered):
        median = None
        if index >= ROLLING_SESSIONS:
            prior = [abs(row.signed_volume_proxy)
                     for row in ordered[index - ROLLING_SESSIONS:index]]
            median = float(np.median(np.asarray(prior, dtype=float)))
        output.append(replace(feature, prior_60_abs_median=median))
    return output


def build_features(frames: Iterable[pd.DataFrame]) -> tuple[list[VolumeFeature], dict[int, dict[str, int]]]:
    prepared = v36.prepare_raw(frames)
    complete_cash = v33._complete_sessions(prepared)
    years = sorted({int(day[:4]) for day in prepared.date.unique()
                    if int(day[:4]) in ALLOWED_YEARS})
    exclusions = {year: Counter() for year in years}
    features: list[VolumeFeature] = []
    for year in years:
        for day in v36._calendar_days(year):
            cash = complete_cash.get(day)
            if cash is None:
                exclusions[year]["incomplete_cash_session"] += 1
                continue
            observation = cash.iloc[:30]
            if (len(observation) != 30 or int(observation.minute.iloc[0]) != 510
                    or int(observation.minute.iloc[-1]) != 539):
                exclusions[year]["opening_30_unavailable"] += 1
                continue
            total_volume = float(observation.volume.sum())
            if not math.isfinite(total_volume) or total_volume <= 0:
                exclusions[year]["nonpositive_observation_volume"] += 1
                continue
            proxy = float(np.dot(observation.volume.to_numpy(float), bar_clv(observation))
                          / total_volume)
            response = float(observation.close.iloc[-1]) - float(observation.open.iloc[0])
            if proxy == 0:
                exclusions[year]["zero_pressure_sign"] += 1
                continue
            if response == 0:
                exclusions[year]["zero_price_response_sign"] += 1
                continue
            features.append(VolumeFeature(
                date=day, cash=cash, instrument_id=int(cash.instrument_id.iloc[0]),
                signed_volume_proxy=proxy, opening_price_response=response,
                observation_volume=total_volume,
            ))
            exclusions[year]["usable_sessions"] += 1
    return assign_prior_medians(features), {
        year: dict(counts) for year, counts in exclusions.items()
    }


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def signal_side(feature: VolumeFeature, mode: str) -> int:
    pressure = _sign(feature.signed_volume_proxy)
    response = _sign(feature.opening_price_response)
    if pressure == 0 or response == 0:
        return 0
    if mode == "flow_follow":
        return pressure if pressure == response else 0
    if mode == "absorption_reversal":
        return response if pressure == -response else 0
    raise ValueError("mode outside frozen v38 family")


def generate_trades(features: list[VolumeFeature], year: int, mode: str,
                    regime: str, hold: int) -> list[dict]:
    if (mode, regime, hold) not in CELL_ORDER or year not in ALLOWED_YEARS:
        raise ValueError("cell or year outside frozen v38 family")
    trades: list[dict] = []
    for feature in features:
        if int(feature.date[:4]) != year:
            continue
        if regime == "causal_high":
            if (feature.prior_60_abs_median is None
                    or abs(feature.signed_volume_proxy) < feature.prior_60_abs_median):
                continue
        side = signal_side(feature, mode)
        if side == 0:
            continue
        cash = feature.cash
        entry_position, exit_position = 30, 30 + hold - 1
        if exit_position >= len(cash):
            continue
        entry_time = pd.Timestamp(cash.timestamp.iloc[entry_position])
        exit_time = pd.Timestamp(cash.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
        policy = v33.cash.session(feature.date)
        if policy is None or exit_time > pd.Timestamp(policy[1]).tz_convert("UTC"):
            continue
        path = cash.iloc[entry_position:exit_position + 1]
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
            "pressure_regime": regime, "hold_minutes": hold, "side": side,
            "signed_volume_proxy": round(feature.signed_volume_proxy, 10),
            "opening_price_response": round(feature.opening_price_response, 10),
            "prior_60_abs_median": (None if feature.prior_60_abs_median is None
                                    else round(feature.prior_60_abs_median, 10)),
            "observation_volume": feature.observation_volume,
            "decision_time": (pd.Timestamp(cash.timestamp.iloc[29]) + pd.Timedelta(minutes=1)).isoformat(),
            "entry_time": entry_time.isoformat(), "exit_time": exit_time.isoformat(),
            "instrument_id": feature.instrument_id,
            "entry_price": entry_price, "exit_price": exit_price,
            "gross_dollars": gross,
        }
        for name, ticks in v33.COST_CASES[1:]:
            trade[name] = v33._cost(gross, ticks)
        trades.append(trade)
    return trades


def annual_passes(summary: dict) -> bool:
    two, four = (summary["cost_views"][name] for name in ("selection_2t", "stress_4t"))
    return (two["trade_count"] >= 60 and two["net_dollars"] > 0
            and v33._profit_factor_value(two) >= 1.10
            and two["average_trade"] is not None and two["average_trade"] >= 8
            and four["net_dollars"] > 0)


def _ratio(summary: dict) -> float:
    two = summary["cost_views"]["selection_2t"]
    drawdown = float(two["maximum_drawdown"])
    return math.inf if drawdown == 0 else float(two["net_dollars"]) / drawdown


def evaluate_discovery(features: list[VolumeFeature]) -> tuple[list[dict], dict | None, list[dict]]:
    cells, trades_by_cell = [], {}
    for mode, regime, hold in CELL_ORDER:
        trades = generate_trades(features, 2023, mode, regime, hold)
        summary = v33.summarize_cell(trades, 2023)
        eligible = annual_passes(summary)
        ratio = _ratio(summary) if eligible else None
        cells.append({
            "parameters": {"mode": mode, "pressure_regime": regime,
                           "hold_minutes": hold},
            "eligible": eligible,
            "selection_net_to_drawdown": None if ratio is None or math.isinf(ratio) else round(ratio, 10),
            "selection_net_to_drawdown_infinite": bool(ratio is not None and math.isinf(ratio)),
            "metrics": summary,
        })
        trades_by_cell[(mode, regime, hold)] = trades
    eligible_cells = [cell for cell in cells if cell["eligible"]]
    if not eligible_cells:
        return cells, None, []
    order = {cell: index for index, cell in enumerate(CELL_ORDER)}
    selected = sorted(eligible_cells, key=lambda cell: (
        -_ratio(cell["metrics"]),
        -float(cell["metrics"]["cost_views"]["selection_2t"]["average_trade"]),
        order[(cell["parameters"]["mode"], cell["parameters"]["pressure_regime"],
               cell["parameters"]["hold_minutes"])],
    ))[0]
    p = selected["parameters"]
    key = (p["mode"], p["pressure_regime"], p["hold_minutes"])
    return cells, selected, trades_by_cell[key]


def evaluate_selected(features: list[VolumeFeature], year: int,
                      parameters: dict) -> tuple[dict, list[dict]]:
    trades = generate_trades(
        features, year, parameters["mode"], parameters["pressure_regime"],
        parameters["hold_minutes"],
    )
    return v33.summarize_cell(trades, year), trades


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID, "research_only": True,
        "production_changed": False, "live_ready": False,
        "calendar_year_2026_sealed": True,
        "pressure_evidence": "OHLCV close-location proxy; not true aggressor flow",
        "family": {"modes": list(MODES), "pressure_regimes": list(REGIMES),
                   "holds_minutes": list(HOLDS), "cells": len(CELL_ORDER)},
        "execution": {
            "fill_convention": "09:00 MES open to exact hold-minute MES close",
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
            raise ValueError("v38 may read only 2023-2025")
        frames[year] = loader("MES", year)
        result["years_loaded"].append(year)

    def features_now():
        return build_features([frames[year] for year in sorted(frames)])

    load(2023)
    features, exclusions = features_now()
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
    features, exclusions = features_now()
    result["session_exclusions"].update({str(k): v for k, v in exclusions.items()})
    summary_2024, trades_2024 = evaluate_selected(features, 2024, parameters)
    passed_2024 = annual_passes(summary_2024)
    result["validation_2024"] = {"passed": passed_2024, "metrics": summary_2024}
    ledger.extend(trades_2024)
    if not passed_2024:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged selected cell failed 2024"
        return result, ledger

    load(2025)
    features, exclusions = features_now()
    result["session_exclusions"].update({str(k): v for k, v in exclusions.items()})
    summary_2025, trades_2025 = evaluate_selected(features, 2025, parameters)
    passed_2025 = annual_passes(summary_2025)
    result["validation_2025"] = {"passed": passed_2025, "metrics": summary_2025}
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
