"""Frozen v37 overnight MNQ/M2K leader transfer to MES.

Research only. Reads checksummed cached bars through a read-only transaction,
never calls a vendor or broker, and refuses calendar year 2026. Reported fills
are trade-print planning proxies, not executable quotes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import math
import os
from typing import Callable, Iterable

import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v35_dual_leader as v35
from scripts import valor_mes_v36_overnight_inventory as v36


SCHEMA_VERSION = "valor-mes-v37-result/1.0.0"
STRATEGY_VERSION = "v37"
STUDY_ID = "valor-mes-v37-overnight-equity-leaders-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
SYMBOLS = ("MES", "MNQ", "M2K")
LEADERS = ("MNQ", "M2K")
MODES = ("leader_confirmed", "leader_rejected")
HOLDS = (30, 60, 120, 240)
CELL_ORDER = tuple((mode, hold) for mode in MODES for hold in HOLDS)
BOOTSTRAP_SEED = 370037
BOOTSTRAP_RESAMPLES = 10_000
LEDGER_FIELDS = (
    "year", "date", "mode", "hold_minutes", "side", "leader_sign",
    "mnq_overnight_return", "m2k_overnight_return", "opening_response",
    "mnq_overnight_first", "mnq_overnight_last", "m2k_overnight_first",
    "m2k_overnight_last", "decision_time", "entry_time", "exit_time",
    "mes_instrument_id", "mnq_instrument_id", "m2k_instrument_id",
    "entry_price", "exit_price", "gross_dollars", "fee_0t", "planning_1t",
    "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class LeaderFeature:
    date: str
    mes_cash: pd.DataFrame
    mes_instrument_id: int
    mnq_instrument_id: int
    m2k_instrument_id: int
    mnq_overnight_return: float
    m2k_overnight_return: float
    opening_response: float
    mnq_first: pd.Timestamp
    mnq_last: pd.Timestamp
    m2k_first: pd.Timestamp
    m2k_last: pd.Timestamp


def prepare_market(frames: Iterable[pd.DataFrame], symbol: str) -> pd.DataFrame:
    if symbol not in SYMBOLS:
        raise ValueError("unsupported v37 symbol")
    normalized = []
    for frame in frames:
        item = frame
        if ("timestamp" not in item and "ts_event" not in item
                and item.index.name in {"timestamp", "ts_event"}):
            item = item.reset_index()
        normalized.append(item)
    raw = pd.concat(normalized, ignore_index=True)
    v36._raw_timestamp(raw)
    return v33.cash.prepare(raw, v35.TICK_SIZES[symbol])


def leader_window(prepared: pd.DataFrame,
                  day: str) -> tuple[pd.DataFrame | None, str | None]:
    """Validate one leader's observed overnight path without forward filling."""
    start, end = v36._overnight_bounds(day)
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
    final_hour = window[window.timestamp >= end - pd.Timedelta(minutes=59)]
    if len(final_hour) < 55:
        return None, "overnight_final_hour_under_55"
    if not window.timestamp.is_monotonic_increasing or window.timestamp.duplicated().any():
        return None, "overnight_nonmonotonic"
    if window.instrument_id.nunique(dropna=False) != 1:
        return None, "overnight_contract_change"
    return window, None


def build_features(frames: dict[str, list[pd.DataFrame]]) -> tuple[list[LeaderFeature], dict[int, dict[str, int]]]:
    prepared = {symbol: prepare_market(frames[symbol], symbol) for symbol in SYMBOLS}
    mes_cash = v33._complete_sessions(prepared["MES"])
    years = sorted({int(day[:4]) for day in prepared["MES"].date.unique()
                    if int(day[:4]) in ALLOWED_YEARS})
    exclusions = {year: Counter() for year in years}
    features: list[LeaderFeature] = []
    for year in years:
        for day in v36._calendar_days(year):
            cash = mes_cash.get(day)
            if cash is None:
                exclusions[year]["incomplete_mes_cash_session"] += 1
                continue
            windows: dict[str, pd.DataFrame] = {}
            rejected = False
            for symbol in LEADERS:
                window, reason = leader_window(prepared[symbol], day)
                if reason is not None:
                    exclusions[year][f"{symbol.lower()}_{reason}"] += 1
                    rejected = True
                    break
                assert window is not None
                windows[symbol] = window
            if rejected:
                continue
            opening = cash.iloc[:5]
            if (len(opening) != 5 or int(opening.minute.iloc[0]) != 510
                    or int(opening.minute.iloc[-1]) != 514):
                exclusions[year]["opening_five_unavailable"] += 1
                continue
            mnq, m2k = windows["MNQ"], windows["M2K"]
            features.append(LeaderFeature(
                date=day, mes_cash=cash,
                mes_instrument_id=int(cash.instrument_id.iloc[0]),
                mnq_instrument_id=int(mnq.instrument_id.iloc[0]),
                m2k_instrument_id=int(m2k.instrument_id.iloc[0]),
                mnq_overnight_return=float(mnq.close.iloc[-1]) - float(mnq.open.iloc[0]),
                m2k_overnight_return=float(m2k.close.iloc[-1]) - float(m2k.open.iloc[0]),
                opening_response=float(opening.close.iloc[-1]) - float(opening.open.iloc[0]),
                mnq_first=pd.Timestamp(mnq.timestamp.iloc[0]),
                mnq_last=pd.Timestamp(mnq.timestamp.iloc[-1]),
                m2k_first=pd.Timestamp(m2k.timestamp.iloc[0]),
                m2k_last=pd.Timestamp(m2k.timestamp.iloc[-1]),
            ))
            exclusions[year]["usable_sessions"] += 1
    return features, {year: dict(counts) for year, counts in exclusions.items()}


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def signal_side(feature: LeaderFeature, mode: str) -> int:
    mnq = _sign(feature.mnq_overnight_return)
    m2k = _sign(feature.m2k_overnight_return)
    opening = _sign(feature.opening_response)
    if mnq == 0 or mnq != m2k:
        return 0
    if mode == "leader_confirmed":
        return mnq if opening == mnq else 0
    if mode == "leader_rejected":
        return opening if opening != 0 and opening == -mnq else 0
    raise ValueError("mode outside frozen v37 family")


def generate_trades(features: list[LeaderFeature], year: int,
                    mode: str, hold: int) -> list[dict]:
    if (mode, hold) not in CELL_ORDER or year not in ALLOWED_YEARS:
        raise ValueError("cell or year outside frozen v37 family")
    trades: list[dict] = []
    for feature in features:
        if int(feature.date[:4]) != year:
            continue
        side = signal_side(feature, mode)
        if side == 0:
            continue
        cash = feature.mes_cash
        entry_position, exit_position = 5, 5 + hold - 1
        if exit_position >= len(cash):
            continue
        entry_time = pd.Timestamp(cash.timestamp.iloc[entry_position])
        exit_time = pd.Timestamp(cash.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
        policy = v33.cash.session(feature.date)
        if policy is None or exit_time > pd.Timestamp(policy[2]).tz_convert("UTC"):
            continue
        path = cash.iloc[entry_position:exit_position + 1]
        if (len(path) != hold or path.instrument_id.nunique(dropna=False) != 1
                or int(path.instrument_id.iloc[0]) != feature.mes_instrument_id):
            continue
        expected = pd.date_range(entry_time, periods=hold, freq="1min")
        if not pd.DatetimeIndex(path.timestamp).equals(expected):
            continue
        entry_price, exit_price = float(path.open.iloc[0]), float(path.close.iloc[-1])
        gross = round(side * (exit_price - entry_price) * v33.POINT_VALUE, 6)
        trade = {
            "year": year, "date": feature.date, "mode": mode,
            "hold_minutes": hold, "side": side,
            "leader_sign": _sign(feature.mnq_overnight_return),
            "mnq_overnight_return": round(feature.mnq_overnight_return, 10),
            "m2k_overnight_return": round(feature.m2k_overnight_return, 10),
            "opening_response": round(feature.opening_response, 10),
            "mnq_overnight_first": feature.mnq_first.isoformat(),
            "mnq_overnight_last": feature.mnq_last.isoformat(),
            "m2k_overnight_first": feature.m2k_first.isoformat(),
            "m2k_overnight_last": feature.m2k_last.isoformat(),
            "decision_time": (pd.Timestamp(cash.timestamp.iloc[4]) + pd.Timedelta(minutes=1)).isoformat(),
            "entry_time": entry_time.isoformat(), "exit_time": exit_time.isoformat(),
            "mes_instrument_id": feature.mes_instrument_id,
            "mnq_instrument_id": feature.mnq_instrument_id,
            "m2k_instrument_id": feature.m2k_instrument_id,
            "entry_price": entry_price, "exit_price": exit_price,
            "gross_dollars": gross,
        }
        for name, ticks in v33.COST_CASES[1:]:
            trade[name] = v33._cost(gross, ticks)
        trades.append(trade)
    return trades


def discovery_eligible(summary: dict) -> bool:
    two, four = (summary["cost_views"][name] for name in ("selection_2t", "stress_4t"))
    return (two["trade_count"] >= 80 and two["net_dollars"] > 0
            and v33._profit_factor_value(two) >= 1.10
            and two["average_trade"] is not None and two["average_trade"] >= 8
            and four["net_dollars"] > 0)


def confirmation_passes(summary: dict) -> bool:
    two, four = (summary["cost_views"][name] for name in ("selection_2t", "stress_4t"))
    return (two["trade_count"] >= 60 and two["net_dollars"] > 0
            and v33._profit_factor_value(two) >= 1.10
            and two["average_trade"] is not None and two["average_trade"] >= 8
            and four["net_dollars"] > 0)


def _ratio(summary: dict) -> float:
    two = summary["cost_views"]["selection_2t"]
    drawdown = float(two["maximum_drawdown"])
    return math.inf if drawdown == 0 else float(two["net_dollars"]) / drawdown


def evaluate_discovery(features: list[LeaderFeature]) -> tuple[list[dict], dict | None, list[dict]]:
    cells, trades_by_cell = [], {}
    for mode, hold in CELL_ORDER:
        trades = generate_trades(features, 2023, mode, hold)
        summary = v33.summarize_cell(trades, 2023)
        eligible = discovery_eligible(summary)
        ratio = _ratio(summary) if eligible else None
        cells.append({
            "parameters": {"mode": mode, "hold_minutes": hold},
            "eligible": eligible,
            "selection_net_to_drawdown": None if ratio is None or math.isinf(ratio) else round(ratio, 10),
            "selection_net_to_drawdown_infinite": bool(ratio is not None and math.isinf(ratio)),
            "metrics": summary,
        })
        trades_by_cell[(mode, hold)] = trades
    eligible_cells = [cell for cell in cells if cell["eligible"]]
    if not eligible_cells:
        return cells, None, []
    order = {cell: index for index, cell in enumerate(CELL_ORDER)}
    selected = sorted(eligible_cells, key=lambda cell: (
        -_ratio(cell["metrics"]),
        -float(cell["metrics"]["cost_views"]["selection_2t"]["average_trade"]),
        order[(cell["parameters"]["mode"], cell["parameters"]["hold_minutes"])],
    ))[0]
    key = (selected["parameters"]["mode"], selected["parameters"]["hold_minutes"])
    return cells, selected, trades_by_cell[key]


def evaluate_selected(features: list[LeaderFeature], year: int,
                      parameters: dict) -> tuple[dict, list[dict]]:
    trades = generate_trades(features, year, parameters["mode"], parameters["hold_minutes"])
    return v33.summarize_cell(trades, year), trades


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID, "research_only": True,
        "production_changed": False, "live_ready": False,
        "calendar_year_2026_sealed": True,
        "family": {"modes": list(MODES), "holds_minutes": list(HOLDS),
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
    frames = {symbol: {} for symbol in SYMBOLS}
    result, ledger = _result_base(), []

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v37 may read only 2023-2025")
        for symbol in SYMBOLS:
            frames[symbol][year] = loader(symbol, year)
        result["years_loaded"].append(year)

    def features_now() -> tuple[list[LeaderFeature], dict[int, dict[str, int]]]:
        years = sorted(frames["MES"])
        return build_features({symbol: [frames[symbol][year] for year in years]
                               for symbol in SYMBOLS})

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
    passed_2024 = confirmation_passes(summary_2024)
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
    passed_2025 = confirmation_passes(summary_2025)
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


def postgres_loader(database_url: str) -> tuple[Callable[[str, int], pd.DataFrame], Callable[[], None]]:
    """Create a checksum-validating three-market loader in a read-only transaction."""
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
