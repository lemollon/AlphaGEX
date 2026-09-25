"""Causal MNQ-to-MES catch-up research for the frozen MES v33 family.

Research only. The command reads existing checksummed Postgres bar-cache rows
in a read-only transaction, never calls a vendor, and never reads 2026. Fills
are one-minute trade-print proxies, not executable bid/ask evidence.
"""
from __future__ import annotations

from collections import defaultdict
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

import numpy as np
import pandas as pd

from scripts import valor_cash_engine_v8 as cash


SCHEMA_VERSION = "valor-mes-v33-result/1.0.0"
STRATEGY_VERSION = "v33"
STUDY_ID = "valor-mes-v33-crossmarket-20260925"
ALLOWED_YEARS = (2023, 2024, 2025)
LOOKBACKS = (5, 15, 30)
THRESHOLDS = (1.5, 2.0)
HOLDS = (5, 15, 30, 60)
CELL_ORDER = tuple((lookback, threshold, hold)
                   for lookback in LOOKBACKS
                   for threshold in THRESHOLDS
                   for hold in HOLDS)
POINT_VALUE = 5.0
TICK_SIZE = 0.25
ROUND_TRIP_FEE = 3.0
BETA_SESSIONS = 60
MIN_BETA_SESSIONS = 40
SCALE_SESSIONS = 20
MIN_SCALE_OBSERVATIONS = 500
BOOTSTRAP_SEED = 330033
BOOTSTRAP_RESAMPLES = 10_000
COST_CASES = (
    ("raw_gross", None),
    ("fee_0t", 0),
    ("planning_1t", 1),
    ("selection_2t", 2),
    ("stress_4t", 4),
)
LEDGER_FIELDS = (
    "year", "date", "lookback_minutes", "threshold_z", "hold_minutes",
    "side", "beta_prior", "scale_prior_bps", "residual_bps", "z_score",
    "signal_bar_start", "decision_time", "entry_time", "exit_time",
    "mes_instrument_id", "entry_price", "exit_price", "gross_dollars",
    "fee_0t", "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class PairSession:
    date: str
    mes: pd.DataFrame
    mnq: pd.DataFrame
    mes_return_bps: float
    mnq_return_bps: float


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _expected_timestamps(day: str) -> pd.DatetimeIndex | None:
    policy = cash.session(day)
    if policy is None:
        return None
    opening, closing, _ = policy
    start = pd.Timestamp(opening).tz_convert("UTC")
    end = pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1)
    return pd.date_range(start, end, freq="1min")


def prepare_market(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the audited v8 calendar, geometry, tick, and duplicate checks."""
    return cash.prepare(frame, TICK_SIZE)


def _complete_sessions(prepared: pd.DataFrame) -> dict[str, pd.DataFrame]:
    complete: dict[str, pd.DataFrame] = {}
    for day, group in prepared[prepared.rth].groupby("date", sort=True):
        expected = _expected_timestamps(str(day))
        group = group.sort_values("timestamp").reset_index(drop=True)
        if expected is None or len(group) != len(expected):
            continue
        observed = pd.DatetimeIndex(group.timestamp)
        if not observed.equals(expected):
            continue
        if group.instrument_id.nunique(dropna=False) != 1:
            continue
        if group.segment.nunique(dropna=False) != 1:
            continue
        complete[str(day)] = group
    return complete


def build_pair_sessions(mes_frames: Iterable[pd.DataFrame],
                        mnq_frames: Iterable[pd.DataFrame]) -> list[PairSession]:
    """Return only exact, contiguous, synchronized complete cash sessions."""
    mes_raw = pd.concat(list(mes_frames), ignore_index=True)
    mnq_raw = pd.concat(list(mnq_frames), ignore_index=True)
    mes = _complete_sessions(prepare_market(mes_raw))
    mnq = _complete_sessions(prepare_market(mnq_raw))
    pairs: list[PairSession] = []
    for day in sorted(set(mes).intersection(mnq)):
        left, right = mes[day], mnq[day]
        if not pd.DatetimeIndex(left.timestamp).equals(pd.DatetimeIndex(right.timestamp)):
            continue
        mes_return = (float(left.close.iloc[-1]) / float(left.open.iloc[0]) - 1.0) * 10_000
        mnq_return = (float(right.close.iloc[-1]) / float(right.open.iloc[0]) - 1.0) * 10_000
        if not (_finite(mes_return) and _finite(mnq_return)):
            continue
        pairs.append(PairSession(day, left, right, mes_return, mnq_return))
    return pairs


def prior_betas(sessions: list[PairSession]) -> dict[str, float]:
    """No-intercept daily beta using at most 60 dates strictly before each date."""
    result: dict[str, float] = {}
    for index, current in enumerate(sessions):
        prior = sessions[max(0, index - BETA_SESSIONS):index]
        if len(prior) < MIN_BETA_SESSIONS:
            continue
        x = np.asarray([row.mnq_return_bps for row in prior], dtype=float)
        y = np.asarray([row.mes_return_bps for row in prior], dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        x, y = x[valid], y[valid]
        denominator = float(np.dot(x, x))
        if len(x) < MIN_BETA_SESSIONS or denominator <= 0:
            continue
        beta = float(np.dot(x, y) / denominator)
        if math.isfinite(beta) and beta > 0:
            result[current.date] = beta
    return result


def _session_residuals(session: PairSession, beta: float,
                       lookback: int) -> np.ndarray:
    mes_close = session.mes.close.to_numpy(float)
    mnq_close = session.mnq.close.to_numpy(float)
    mes_returns = (mes_close[lookback:] / mes_close[:-lookback] - 1.0) * 10_000
    mnq_returns = (mnq_close[lookback:] / mnq_close[:-lookback] - 1.0) * 10_000
    return beta * mnq_returns - mes_returns


def prior_scales(sessions: list[PairSession], betas: dict[str, float],
                 lookback: int) -> dict[str, float]:
    """Prior-20-session residual scale; each source date uses its own prior beta."""
    historical = {
        row.date: _session_residuals(row, betas[row.date], lookback)
        for row in sessions if row.date in betas
    }
    result: dict[str, float] = {}
    for index, current in enumerate(sessions):
        prior_dates = [row.date for row in sessions[max(0, index - SCALE_SESSIONS):index]]
        if (len(prior_dates) != SCALE_SESSIONS
                or any(day not in historical for day in prior_dates)):
            continue
        arrays = [historical[day] for day in prior_dates if day in historical]
        values = np.concatenate(arrays)
        values = values[np.isfinite(values)]
        if len(values) < MIN_SCALE_OBSERVATIONS:
            continue
        scale = float(np.std(values, ddof=1))
        if math.isfinite(scale) and scale > 0:
            result[current.date] = scale
    return result


def build_feature_rows(sessions: list[PairSession]) -> dict[int, list[dict]]:
    """Build completed-bar residual features with no current-date estimators."""
    betas = prior_betas(sessions)
    output: dict[int, list[dict]] = {lookback: [] for lookback in LOOKBACKS}
    for lookback in LOOKBACKS:
        scales = prior_scales(sessions, betas, lookback)
        for session in sessions:
            beta = betas.get(session.date)
            scale = scales.get(session.date)
            if beta is None or scale is None:
                continue
            residuals = _session_residuals(session, beta, lookback)
            for position, residual in enumerate(residuals, start=lookback):
                if not math.isfinite(float(residual)):
                    continue
                bar_start = pd.Timestamp(session.mes.timestamp.iloc[position])
                output[lookback].append({
                    "date": session.date,
                    "year": int(session.date[:4]),
                    "position": position,
                    "session": session,
                    "beta_prior": beta,
                    "scale_prior_bps": scale,
                    "residual_bps": float(residual),
                    "z_score": float(residual / scale),
                    "signal_bar_start": bar_start,
                    "decision_time": bar_start + pd.Timedelta(minutes=1),
                })
    return output


def _cost(gross: float, ticks_each_side: int | None) -> float:
    if ticks_each_side is None:
        return round(float(gross), 6)
    cost = ROUND_TRIP_FEE + 2 * ticks_each_side * TICK_SIZE * POINT_VALUE
    return round(float(gross) - cost, 6)


def generate_trades(feature_rows: list[dict], year: int, lookback: int,
                    threshold: float, hold: int) -> list[dict]:
    """Generate one-position-at-a-time MES fills for a frozen cell."""
    if (lookback, threshold, hold) not in CELL_ORDER:
        raise ValueError("cell is outside the frozen v33 family")
    trades: list[dict] = []
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    for row in feature_rows:
        if row["year"] != year or abs(row["z_score"]) < threshold:
            continue
        session: PairSession = row["session"]
        entry_position = int(row["position"]) + 1
        exit_position = entry_position + hold - 1
        if exit_position >= len(session.mes):
            continue
        entry_time = pd.Timestamp(session.mes.timestamp.iloc[entry_position])
        exit_time = pd.Timestamp(session.mes.timestamp.iloc[exit_position]) + pd.Timedelta(minutes=1)
        policy = cash.session(row["date"])
        if policy is None or exit_time > pd.Timestamp(policy[2]).tz_convert("UTC"):
            continue
        if entry_time < last_exit:
            continue
        mes_path = session.mes.iloc[entry_position:exit_position + 1]
        if len(mes_path) != hold or mes_path.instrument_id.nunique(dropna=False) != 1:
            continue
        expected = pd.date_range(entry_time, periods=hold, freq="1min")
        if not pd.DatetimeIndex(mes_path.timestamp).equals(expected):
            continue
        side = 1 if row["z_score"] > 0 else -1
        entry_price = float(mes_path.open.iloc[0])
        exit_price = float(mes_path.close.iloc[-1])
        gross = round(side * (exit_price - entry_price) * POINT_VALUE, 6)
        trade = {
            "year": year,
            "date": row["date"],
            "lookback_minutes": lookback,
            "threshold_z": threshold,
            "hold_minutes": hold,
            "side": side,
            "beta_prior": round(float(row["beta_prior"]), 10),
            "scale_prior_bps": round(float(row["scale_prior_bps"]), 10),
            "residual_bps": round(float(row["residual_bps"]), 10),
            "z_score": round(float(row["z_score"]), 10),
            "signal_bar_start": row["signal_bar_start"].isoformat(),
            "decision_time": row["decision_time"].isoformat(),
            "entry_time": entry_time.isoformat(),
            "exit_time": exit_time.isoformat(),
            "mes_instrument_id": int(mes_path.instrument_id.iloc[0]),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_dollars": gross,
        }
        for name, ticks in COST_CASES[1:]:
            trade[name] = _cost(gross, ticks)
        trades.append(trade)
        last_exit = exit_time
    return trades


def _cost_metrics(trades: list[dict], case: str, year: int) -> dict:
    values = np.asarray([
        trade["gross_dollars"] if case == "raw_gross" else trade[case]
        for trade in trades
    ], dtype=float)
    wins = float(values[values > 0].sum()) if len(values) else 0.0
    losses = float(-values[values < 0].sum()) if len(values) else 0.0
    equity = np.r_[0.0, values.cumsum()]
    drawdown = float((np.maximum.accumulate(equity) - equity).max())
    monthly = {f"{year}-{month:02}": 0.0 for month in range(1, 13)}
    for trade, pnl in zip(trades, values):
        monthly[trade["date"][:7]] += float(pnl)
    monthly = {month: round(value, 6) for month, value in monthly.items()}
    return {
        "trade_count": len(trades),
        "net_dollars": round(float(values.sum()), 6),
        "average_trade": round(float(values.mean()), 6) if len(values) else None,
        "gross_profit": round(wins, 6),
        "gross_loss": round(losses, 6),
        "profit_factor": round(wins / losses, 6) if losses else None,
        "profit_factor_infinite": bool(wins > 0 and losses == 0),
        "maximum_drawdown": round(drawdown, 6),
        "monthly_pnl": monthly,
    }


def summarize_cell(trades: list[dict], year: int) -> dict:
    return {
        "year": year,
        "fill_convention": "next-minute MES open to exact hold-minute MES close; trade-print proxy",
        "cost_views": {
            name: _cost_metrics(trades, name, year) for name, _ in COST_CASES
        },
    }


def _profit_factor_value(metrics: dict) -> float:
    if metrics["profit_factor_infinite"]:
        return math.inf
    value = metrics["profit_factor"]
    return float(value) if value is not None else 0.0


def discovery_eligible(summary: dict) -> bool:
    metrics = summary["cost_views"]["selection_2t"]
    return (
        metrics["trade_count"] >= 80
        and metrics["net_dollars"] > 0
        and _profit_factor_value(metrics) >= 1.10
        and metrics["average_trade"] is not None
        and metrics["average_trade"] >= 8
    )


def confirmation_passes(summary: dict) -> bool:
    two = summary["cost_views"]["selection_2t"]
    four = summary["cost_views"]["stress_4t"]
    return (
        two["trade_count"] >= 60
        and two["net_dollars"] > 0
        and _profit_factor_value(two) >= 1.10
        and two["average_trade"] is not None
        and two["average_trade"] >= 8
        and four["net_dollars"] > 0
    )


def _selection_ratio(summary: dict) -> float:
    metrics = summary["cost_views"]["selection_2t"]
    drawdown = float(metrics["maximum_drawdown"])
    return math.inf if drawdown == 0 else float(metrics["net_dollars"]) / drawdown


def evaluate_discovery(features: dict[int, list[dict]]) -> tuple[list[dict], dict | None, list[dict]]:
    cells: list[dict] = []
    trades_by_cell: dict[tuple[int, float, int], list[dict]] = {}
    for lookback, threshold, hold in CELL_ORDER:
        trades = generate_trades(features[lookback], 2023, lookback, threshold, hold)
        summary = summarize_cell(trades, 2023)
        eligible = discovery_eligible(summary)
        ratio = _selection_ratio(summary) if eligible else None
        cells.append({
            "parameters": {"lookback_minutes": lookback, "threshold_z": threshold,
                           "hold_minutes": hold},
            "eligible": eligible,
            "selection_net_to_drawdown": None if ratio is None or math.isinf(ratio) else round(ratio, 10),
            "selection_net_to_drawdown_infinite": bool(ratio is not None and math.isinf(ratio)),
            "metrics": summary,
        })
        trades_by_cell[(lookback, threshold, hold)] = trades
    eligible_cells = [cell for cell in cells if cell["eligible"]]
    if not eligible_cells:
        return cells, None, []
    order = {cell: index for index, cell in enumerate(CELL_ORDER)}
    selected = sorted(
        eligible_cells,
        key=lambda cell: (
            -_selection_ratio(cell["metrics"]),
            -float(cell["metrics"]["cost_views"]["selection_2t"]["average_trade"]),
            order[(cell["parameters"]["lookback_minutes"],
                   cell["parameters"]["threshold_z"],
                   cell["parameters"]["hold_minutes"])],
        ),
    )[0]
    params = selected["parameters"]
    key = (params["lookback_minutes"], params["threshold_z"], params["hold_minutes"])
    return cells, selected, trades_by_cell[key]


def evaluate_selected(features: dict[int, list[dict]], year: int,
                      parameters: dict) -> tuple[dict, list[dict]]:
    trades = generate_trades(
        features[parameters["lookback_minutes"]], year,
        parameters["lookback_minutes"], parameters["threshold_z"],
        parameters["hold_minutes"],
    )
    return summarize_cell(trades, year), trades


def day_cluster_bootstrap(trades: list[dict], session_dates: list[str],
                          resamples: int = BOOTSTRAP_RESAMPLES,
                          seed: int = BOOTSTRAP_SEED) -> dict:
    """Bootstrap complete session-day P&L clusters, including zero-trade days."""
    if resamples <= 0:
        raise ValueError("bootstrap resamples must be positive")
    pnl = defaultdict(float)
    for trade in trades:
        pnl[trade["date"]] += float(trade["selection_2t"])
    dates = sorted(set(session_dates))
    values = np.asarray([pnl[day] for day in dates], dtype=float)
    if not len(values):
        return {"seed": seed, "resamples": resamples, "session_days": 0,
                "mean_daily_pnl": None, "lower_95": None}
    rng = np.random.default_rng(seed)
    sampled_means = np.empty(resamples, dtype=float)
    chunk = 1_000
    for start in range(0, resamples, chunk):
        stop = min(start + chunk, resamples)
        indices = rng.integers(0, len(values), size=(stop - start, len(values)))
        sampled_means[start:stop] = values[indices].mean(axis=1)
    return {
        "seed": seed,
        "resamples": resamples,
        "session_days": len(values),
        "mean_daily_pnl": round(float(values.mean()), 6),
        "lower_95": round(float(np.quantile(sampled_means, 0.025, method="linear")), 6),
    }


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "calendar_year_2026_sealed": True,
        "family": {
            "lookbacks_minutes": list(LOOKBACKS),
            "thresholds_z": list(THRESHOLDS),
            "holds_minutes": list(HOLDS),
            "cells": len(CELL_ORDER),
        },
        "estimation": {
            "beta": "prior 60 complete sessions, minimum 40, no-intercept OLS",
            "scale": "sample standard deviation of residuals from prior 20 complete sessions",
            "minimum_scale_observations": MIN_SCALE_OBSERVATIONS,
        },
        "execution": {
            "fill_convention": "next-minute MES open to exact hold-minute MES close",
            "evidence": "trade-print proxy; executable bid/ask and latency not verified",
            "round_trip_fee": ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "years_loaded": [],
        "verdict": None,
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Run the sequential firewall; later years are not loaded after a failure."""
    frames: dict[str, dict[int, pd.DataFrame]] = {"MES": {}, "MNQ": {}}

    def load_year(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v33 may read only 2023-2025")
        for symbol in ("MES", "MNQ"):
            frames[symbol][year] = loader(symbol, year)

    def current_sessions() -> list[PairSession]:
        years = sorted(frames["MES"])
        return build_pair_sessions(
            [frames["MES"][year] for year in years],
            [frames["MNQ"][year] for year in years],
        )

    result = _result_base()
    load_year(2023)
    result["years_loaded"].append(2023)
    sessions = current_sessions()
    features = build_feature_rows(sessions)
    cells, selected, discovery_trades = evaluate_discovery(features)
    result["discovery_2023"] = {"cells": cells, "selected": selected}
    if selected is None:
        result["verdict"] = "FAMILY_FAIL_DISCOVERY"
        result["firewall"] = "2024 and 2025 unopened because no 2023 cell qualified"
        return result, []

    parameters = selected["parameters"]
    ledger = list(discovery_trades)
    load_year(2024)
    result["years_loaded"].append(2024)
    sessions = current_sessions()
    features = build_feature_rows(sessions)
    validation_2024, trades_2024 = evaluate_selected(features, 2024, parameters)
    passed_2024 = confirmation_passes(validation_2024)
    result["validation_2024"] = {"passed": passed_2024, "metrics": validation_2024}
    ledger.extend(trades_2024)
    if not passed_2024:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged selected cell failed 2024"
        return result, ledger

    load_year(2025)
    result["years_loaded"].append(2025)
    sessions = current_sessions()
    features = build_feature_rows(sessions)
    validation_2025, trades_2025 = evaluate_selected(features, 2025, parameters)
    passed_2025 = confirmation_passes(validation_2025)
    result["validation_2025"] = {"passed": passed_2025, "metrics": validation_2025}
    ledger.extend(trades_2025)
    if not passed_2025:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "historical family rejected by independent 2025 confirmation"
        return result, ledger

    validation_dates = [row.date for row in sessions if row.date[:4] in {"2024", "2025"}]
    bootstrap = day_cluster_bootstrap(
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
    """Create a checksum-validating cache loader in one read-only transaction."""
    import psycopg2

    connection = psycopg2.connect(database_url, connect_timeout=15)
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor()

    def load(symbol: str, year: int) -> pd.DataFrame:
        if symbol not in {"MES", "MNQ"} or year not in ALLOWED_YEARS:
            raise ValueError("only MES/MNQ 2023-2025 cache rows are permitted")
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
    json_out = Path(json_out)
    ledger_out = Path(ledger_out)
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
