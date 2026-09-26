"""Frozen MES v40 intraday VWAP-extension rejection research.

Research only. Reads checksummed cached MES one-minute OHLCV for 2023-2025,
never calls a vendor or broker, and refuses calendar year 2026. Fills are
trade-print planning scenarios, not executable bid/ask evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
from typing import Callable

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v39_overnight_sweep as v39


SCHEMA_VERSION = "valor-mes-v40-result/1.0.0"
STRATEGY_VERSION = "v40"
STUDY_ID = "valor-mes-v40-vwap-reversion-20260926"
ALLOWED_YEARS = (2023, 2024, 2025)
EXTENSIONS = (0.50, 0.75)
MINIMUM_REWARD_RISKS = (1.0, 1.5)
HOLDS = (30, 60, 120)
CELL_ORDER = tuple(
    (extension, minimum_rr, hold)
    for extension in EXTENSIONS
    for minimum_rr in MINIMUM_REWARD_RISKS
    for hold in HOLDS
)
POINT_VALUE = 5.0
TICK_SIZE = 0.25
ROUND_TRIP_FEE = 3.0
MIN_EXTENSION_ATR = min(EXTENSIONS)
MIN_REVERSAL_ATR = 0.10
MIN_REMAINING_EXTENSION_ATR = 0.05
REARM_ATR = 0.10
STOP_BUFFER_ATR = 0.05
MIN_RISK_ATR = 0.10
MAX_RISK_ATR = 0.60
DAILY_LIMIT = 3
COOLDOWN_MINUTES = 30
BOOTSTRAP_SEED = 400040
BOOTSTRAP_RESAMPLES = 10_000
COST_CASES = v39.COST_CASES


def _cost(gross: float, ticks_each_side: int | None) -> float:
    if ticks_each_side is None:
        return round(float(gross), 6)
    cost = ROUND_TRIP_FEE + 2 * int(ticks_each_side) * TICK_SIZE * POINT_VALUE
    return round(float(gross) - cost, 6)


def _round_target_adverse(value: float, side: int) -> float:
    """Round VWAP toward the entry so target geometry is conservative."""
    units = value / TICK_SIZE
    return (math.floor(units + 1e-9) if side > 0
            else math.ceil(units - 1e-9)) * TICK_SIZE


def _feature_payload(session: v39.SessionContext, cash: pd.DataFrame,
                     end_position: int, decision_minute: int, side: int,
                     close: float, vwap: float, cumulative_volume: float) -> dict:
    atr = session.atr_prior
    overnight_range_atr = (session.overnight_high - session.overnight_low) / atr
    gap = (float(cash.open.iloc[0]) - session.prior_close
           if session.prior_close is not None else None)
    ret15 = v39._window_return(cash, end_position, 15)
    ret30 = v39._window_return(cash, end_position, 30)
    ret60 = v39._window_return(cash, end_position, 60)
    efficiency = v39._window_efficiency(cash, end_position, 60)
    relvol = v39._relative_volume(session, decision_minute, cumulative_volume)
    vwap_scaled = side * (close - vwap) / atr
    vwap_regime = (
        "aligned" if vwap_scaled > 0.05
        else "opposed" if vwap_scaled < -0.05
        else "near"
    )
    return {
        "atr_prior": round(atr, 10),
        "atr_percentile": (round(session.atr_percentile, 10)
                           if session.atr_percentile is not None else None),
        "atr_regime": v39._atr_regime(session.atr_percentile),
        "overnight_high": session.overnight_high,
        "overnight_low": session.overnight_low,
        "overnight_range_atr": round(overnight_range_atr, 10),
        "overnight_range_regime": v39._range_regime(overnight_range_atr),
        "overnight_return_atr": round(session.overnight_return / atr, 10),
        "overnight_alignment": v39._alignment(session.overnight_return, side, atr),
        "gap_atr": round(gap / atr, 10) if gap is not None else None,
        "gap_alignment": v39._alignment(gap, side, atr),
        "return_15_atr": round(ret15 / atr, 10),
        "return_15_alignment": v39._alignment(ret15, side, atr),
        "return_30_atr": round(ret30 / atr, 10),
        "return_30_alignment": v39._alignment(ret30, side, atr),
        "return_60_atr": round(ret60 / atr, 10),
        "return_60_alignment": v39._alignment(ret60, side, atr),
        "efficiency_60": round(efficiency, 10),
        "efficiency_regime": v39._efficiency_regime(efficiency),
        "vwap_distance_atr": round((close - vwap) / atr, 10),
        "vwap_regime": vwap_regime,
        "relative_volume": round(relvol, 10) if relvol is not None else None,
        "relative_volume_regime": v39._relative_volume_regime(relvol),
    }


def build_events(sessions: list[v39.SessionContext]) -> tuple[list[dict], dict[int, dict[str, int]]]:
    """Create causal all-day VWAP-extension rejection events."""
    events: list[dict] = []
    counts: dict[int, Counter] = defaultdict(Counter)
    for session in sessions:
        year = int(session.date[:4])
        cash = session.cash.reset_index(drop=True)
        atr = float(session.atr_prior)
        policy = v33.cash.session(session.date)
        if policy is None:
            counts[year]["cash_policy_missing"] += 1
            continue
        close_minute = policy[1].hour * 60 + policy[1].minute
        cumulative_pv = 0.0
        cumulative_volume = 0.0
        armed = {1: True, -1: True}
        peak_distance = {1: 0.0, -1: 0.0}
        sequence = {1: 0, -1: 0}
        for start in range(0, len(cash), 5):
            block = cash.iloc[start:start + 5]
            if len(block) != 5:
                break
            expected = pd.date_range(pd.Timestamp(block.timestamp.iloc[0]), periods=5, freq="1min")
            if not pd.DatetimeIndex(block.timestamp).equals(expected):
                counts[year]["noncontiguous_five_minute_block"] += 1
                continue
            cumulative_pv += float((((block.high + block.low + block.close) / 3)
                                    * block.volume).sum())
            cumulative_volume += float(block.volume.sum())
            if cumulative_volume <= 0:
                counts[year]["nonpositive_cumulative_volume"] += 1
                continue
            close = float(block.close.iloc[-1])
            vwap = cumulative_pv / cumulative_volume
            decision_minute = int(block.minute.iloc[-1]) + 1
            deviation = (close - vwap) / atr

            current_side = -1 if deviation > MIN_REMAINING_EXTENSION_ATR else (
                1 if deviation < -MIN_REMAINING_EXTENSION_ATR else 0
            )
            if abs(deviation) <= REARM_ATR:
                for rearm_side in (1, -1):
                    if (rearm_side != current_side or not armed[rearm_side]
                            or peak_distance[rearm_side] < MIN_EXTENSION_ATR):
                        armed[rearm_side] = True
                        peak_distance[rearm_side] = 0.0
            if decision_minute < 540 or decision_minute > close_minute - min(HOLDS):
                continue

            side = current_side
            if side == 0:
                continue
            distance = abs(deviation)
            prior_peak = peak_distance[side]
            peak_distance[side] = max(prior_peak, distance)
            reversal = peak_distance[side] - distance
            if (not armed[side] or peak_distance[side] < MIN_EXTENSION_ATR
                    or reversal < MIN_REVERSAL_ATR):
                continue

            extreme = float(block.low.min()) if side > 0 else float(block.high.max())
            stop = v39._round_stop(extreme - side * STOP_BUFFER_ATR * atr, side)
            risk = side * (close - stop)
            target = _round_target_adverse(vwap, side)
            reward = side * (target - close)
            if risk < MIN_RISK_ATR * atr or risk > MAX_RISK_ATR * atr:
                counts[year]["risk_outside_frozen_band"] += 1
                armed[side] = False
                continue
            if reward <= 0:
                counts[year]["nonpositive_planned_reward"] += 1
                armed[side] = False
                continue

            sequence[side] += 1
            armed[side] = False
            decision_time = pd.Timestamp(block.timestamp.iloc[-1]) + pd.Timedelta(minutes=1)
            event = {
                "year": year,
                "date": session.date,
                "side": side,
                "side_label": "long" if side > 0 else "short",
                "instrument_id": int(session.instrument_id),
                "signal_bar_start": pd.Timestamp(block.timestamp.iloc[0]).isoformat(),
                "decision_time": decision_time.isoformat(),
                "decision_minute": decision_minute,
                "time_bucket": v39._time_bucket(decision_minute),
                "sweep_number": sequence[side],
                "sweep_sequence": "first" if sequence[side] == 1 else "repeat",
                "extension_atr": round(peak_distance[side], 10),
                "reversal_atr": round(reversal, 10),
                "overshoot_atr": round(peak_distance[side], 10),
                "reclaim_atr": round(reversal, 10),
                "signal_vwap": round(vwap, 10),
                "reference_price": close,
                "stop_price": stop,
                "target_price": target,
                "planned_risk_points": round(risk, 10),
                "planned_reward_points": round(reward, 10),
                "planned_reward_risk": round(reward / risk, 10),
            }
            event.update(_feature_payload(
                session, cash, start + 4, decision_minute, side, close, vwap,
                cumulative_volume,
            ))
            events.append(event)
            counts[year]["candidate_events"] += 1
    return sorted(events, key=lambda row: (row["decision_time"], row["side"])), {
        year: dict(value) for year, value in counts.items()
    }


def _record_trade(event: dict, extension: float, minimum_rr: float, hold: int,
                  entry_time: pd.Timestamp, exit_time: pd.Timestamp,
                  entry: float, exit_price: float, reason: str,
                  mae: float, mfe: float) -> dict:
    side = int(event["side"])
    gross = round(side * (exit_price - entry) * POINT_VALUE, 6)
    trade = {key: value for key, value in event.items()
             if key not in {"decision_minute", "reference_price"}}
    trade.update({
        "extension_threshold": extension,
        "minimum_reward_risk": minimum_rr,
        "hold_minutes": hold,
        "entry_time": entry_time.isoformat(),
        "exit_time": exit_time.isoformat(),
        "entry_price": entry,
        "exit_price": exit_price,
        "exit_reason": reason,
        "actual_risk_points": round(side * (entry - float(event["stop_price"])), 10),
        "mae_points": round(mae, 10),
        "mfe_points": round(mfe, 10),
        "gross_dollars": gross,
    })
    for name, ticks in COST_CASES[1:]:
        trade[name] = _cost(gross, ticks)
    return trade


def replay_cell(sessions: list[v39.SessionContext], events: list[dict], year: int,
                extension: float, minimum_rr: float, hold: int) -> tuple[list[dict], dict]:
    if (extension, minimum_rr, hold) not in CELL_ORDER:
        raise ValueError("cell outside frozen v40 family")
    session_map = {session.date: session for session in sessions
                   if int(session.date[:4]) == year}
    trades: list[dict] = []
    skips: Counter = Counter()
    next_allowed: dict[str, pd.Timestamp] = {}
    daily_count: Counter = Counter()
    for event in events:
        if event["year"] != year:
            continue
        if (float(event["extension_atr"]) < extension
                or float(event["planned_reward_risk"]) < minimum_rr):
            continue
        session = session_map.get(event["date"])
        if session is None:
            skips["session_missing"] += 1
            continue
        decision = pd.Timestamp(event["decision_time"])
        if decision < next_allowed.get(event["date"], pd.Timestamp.min.tz_localize("UTC")):
            skips["position_or_cooldown"] += 1
            continue
        if daily_count[event["date"]] >= DAILY_LIMIT:
            skips["daily_limit"] += 1
            continue
        policy = v33.cash.session(event["date"])
        assert policy is not None
        close_time = pd.Timestamp(policy[1]).tz_convert("UTC")
        if decision > close_time - pd.Timedelta(minutes=hold):
            skips["insufficient_full_hold"] += 1
            continue
        cash = session.cash.reset_index(drop=True)
        positions = np.flatnonzero(pd.DatetimeIndex(cash.timestamp) == decision)
        if len(positions) != 1:
            skips["missing_entry_minute"] += 1
            continue
        entry_position = int(positions[0])
        path = cash.iloc[entry_position:entry_position + hold]
        expected = pd.date_range(decision, periods=hold, freq="1min")
        if (len(path) != hold or not pd.DatetimeIndex(path.timestamp).equals(expected)
                or path.instrument_id.nunique(dropna=False) != 1
                or int(path.instrument_id.iloc[0]) != session.instrument_id):
            skips["incomplete_hold_or_contract_switch"] += 1
            continue

        side = int(event["side"])
        stop = float(event["stop_price"])
        target = float(event["target_price"])
        entry = float(path.open.iloc[0])
        if side * (entry - stop) <= 0:
            skips["entry_gap_beyond_stop"] += 1
            continue
        if side * (entry - target) >= 0:
            skips["entry_gap_beyond_target"] += 1
            continue

        exit_price: float | None = None
        exit_time: pd.Timestamp | None = None
        reason: str | None = None
        mae = 0.0
        mfe = 0.0
        for offset, row in enumerate(path.itertuples(index=False)):
            row_time = pd.Timestamp(row.timestamp)
            if side * (float(row.open) - stop) <= 0:
                exit_price, exit_time, reason = float(row.open), row_time, "gap_stop"
                mae = max(mae, max(0.0, side * (entry - exit_price)))
                break
            if side * (float(row.open) - target) >= 0:
                exit_price, exit_time, reason = float(row.open), row_time, "gap_target"
                mfe = max(mfe, max(0.0, side * (exit_price - entry)))
                break
            stop_hit = ((side > 0 and float(row.low) <= stop)
                        or (side < 0 and float(row.high) >= stop))
            target_hit = ((side > 0 and float(row.high) >= target + TICK_SIZE)
                          or (side < 0 and float(row.low) <= target - TICK_SIZE))
            if stop_hit:
                exit_price, exit_time, reason = stop, row_time + pd.Timedelta(minutes=1), "stop"
                mae = max(mae, max(0.0, side * (entry - stop)))
                break
            if target_hit:
                exit_price, exit_time, reason = target, row_time + pd.Timedelta(minutes=1), "target"
                mfe = max(mfe, max(0.0, side * (target - entry)))
                break
            adverse = entry - float(row.low) if side > 0 else float(row.high) - entry
            favorable = float(row.high) - entry if side > 0 else entry - float(row.low)
            mae = max(mae, max(0.0, adverse))
            mfe = max(mfe, max(0.0, favorable))
            if offset == hold - 1:
                exit_price = float(row.close)
                exit_time = row_time + pd.Timedelta(minutes=1)
                reason = "time_stop"
        assert exit_price is not None and exit_time is not None and reason is not None
        trades.append(_record_trade(
            event, extension, minimum_rr, hold, decision, exit_time,
            entry, exit_price, reason, mae, mfe,
        ))
        daily_count[event["date"]] += 1
        next_allowed[event["date"]] = exit_time + pd.Timedelta(minutes=COOLDOWN_MINUTES)
    candidates = sum(
        1 for event in events
        if event["year"] == year
        and float(event["extension_atr"]) >= extension
        and float(event["planned_reward_risk"]) >= minimum_rr
    )
    return trades, {"skips": dict(skips), "candidate_events": candidates}


def summarize_cell(trades: list[dict], year: int, replay: dict,
                   parameters: tuple[float, float, int]) -> dict:
    extension, minimum_rr, hold = parameters
    return {
        "year": year,
        "parameters": {
            "extension_threshold": extension,
            "minimum_reward_risk": minimum_rr,
            "hold_minutes": hold,
        },
        "replay": replay,
        "cost_views": {
            name: v39._pnl_metrics(trades, "gross_dollars" if ticks is None else name)
            for name, ticks in COST_CASES
        },
        "long_trades": sum(int(row["side"]) > 0 for row in trades),
        "short_trades": sum(int(row["side"]) < 0 for row in trades),
        "exit_reasons": dict(Counter(row["exit_reason"] for row in trades)),
    }


def annual_passes(summary: dict, minimum_trades: int) -> bool:
    selection = summary["cost_views"]["selection_2t"]
    stress = summary["cost_views"]["stress_4t"]
    ratio = selection["net_to_drawdown"]
    pf = selection["profit_factor"]
    return bool(
        selection["trade_count"] >= minimum_trades
        and selection["net_dollars"] > 0
        and pf is not None and pf >= 1.15
        and selection["average_trade"] is not None
        and selection["average_trade"] >= 8.0
        and ratio is not None and ratio >= 0.75
        and stress["net_dollars"] > 0
        and selection["best_month_removed_net"] > 0
    )


def _selection_rank(summary: dict) -> tuple:
    metrics = summary["cost_views"]["selection_2t"]
    ratio = metrics["net_to_drawdown"]
    params = summary["parameters"]
    cell_index = CELL_ORDER.index((
        float(params["extension_threshold"]),
        float(params["minimum_reward_risk"]),
        int(params["hold_minutes"]),
    ))
    return (
        float(ratio) if ratio is not None else -math.inf,
        float(metrics["average_trade"] if metrics["average_trade"] is not None else -math.inf),
        -cell_index,
    )


def _diagnostic_cell(cells: list[dict]) -> dict | None:
    if not cells:
        return None
    eligible = [cell for cell in cells
                if cell["cost_views"]["selection_2t"]["trade_count"] >= 40]
    return max(eligible or cells, key=_selection_rank)


def evaluate_year(sessions: list[v39.SessionContext], events: list[dict], year: int,
                  parameters: dict | None = None,
                  minimum_trades: int = 80) -> tuple[list[dict], dict | None, list[dict]]:
    if parameters is None:
        cells_to_run = CELL_ORDER
    else:
        cells_to_run = ((
            float(parameters["extension_threshold"]),
            float(parameters["minimum_reward_risk"]),
            int(parameters["hold_minutes"]),
        ),)
    cells: list[dict] = []
    ledgers: dict[tuple[float, float, int], list[dict]] = {}
    for cell in cells_to_run:
        trades, replay = replay_cell(sessions, events, year, *cell)
        summary = summarize_cell(trades, year, replay, cell)
        summary["passed"] = annual_passes(summary, minimum_trades)
        cells.append(summary)
        ledgers[cell] = trades
    if parameters is not None:
        return cells, cells[0], ledgers[next(iter(ledgers))]
    qualified = [cell for cell in cells if cell["passed"]]
    selected = max(qualified, key=_selection_rank) if qualified else None
    diagnostic = _diagnostic_cell(cells)
    chosen = selected or diagnostic
    ledger: list[dict] = []
    if chosen is not None:
        p = chosen["parameters"]
        ledger = ledgers[(float(p["extension_threshold"]),
                          float(p["minimum_reward_risk"]),
                          int(p["hold_minutes"]))]
    return cells, selected, ledger


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "family": "intraday_vwap_extension_rejection",
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "calendar_year_2026_sealed": True,
        "years_loaded": [],
        "source_cache": {},
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "execution": {
            "evidence": "one-minute trade-print OHLC proxy; executable bid/ask and latency not verified",
            "fill_convention": "completed five-minute signal; next one-minute open; stop-first ambiguity; one-tick target trade-through",
            "round_trip_fee": ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "verdict": "NOT_RUN",
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Run the frozen sequential firewall; never load a later year after failure."""
    frames: dict[int, pd.DataFrame] = {}
    result = _result_base()
    result["bootstrap"]["resamples"] = bootstrap_resamples
    v39.BOOTSTRAP_SEED = BOOTSTRAP_SEED

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v40 may read only 2023-2025")
        frame = loader("MES", year)
        frames[year] = frame
        cache_key = frame.attrs.get("source_cache_key")
        source_sha = frame.attrs.get("source_sha256")
        if cache_key is not None and source_sha is not None:
            result["source_cache"][str(year)] = {
                "cache_key": str(cache_key),
                "sha256": str(source_sha),
            }
        result["years_loaded"].append(year)

    def prepared() -> tuple[list[v39.SessionContext], list[dict], dict, dict]:
        sessions, session_exclusions = v39.build_sessions(
            [frames[year] for year in sorted(frames)]
        )
        events, event_exclusions = build_events(sessions)
        return sessions, events, session_exclusions, event_exclusions

    load(2023)
    sessions, events, session_exclusions, event_exclusions = prepared()
    cells, selected, diagnostic_ledger = evaluate_year(sessions, events, 2023)
    diagnostic_cell = _diagnostic_cell(cells)
    audit = v39.cluster_audit(diagnostic_ledger, bootstrap_resamples)
    result["discovery_2023"] = {
        "cells": cells,
        "selected": selected,
        "diagnostic_cell": diagnostic_cell,
        "cluster_audit": audit,
        "session_exclusions": session_exclusions.get(2023, {}),
        "event_counts": event_exclusions.get(2023, {}),
    }
    if selected is None:
        result["verdict"] = "FAMILY_FAIL_DISCOVERY"
        result["firewall"] = "2024 and 2025 unopened because no frozen 2023 cell qualified"
        return result, diagnostic_ledger

    parameters = selected["parameters"]
    avoid_rule = audit["selected_avoid"]
    size_rule = audit["selected_size"]
    ledger = list(diagnostic_ledger)

    load(2024)
    sessions, events, session_exclusions, event_exclusions = prepared()
    _, validation_2024, trades_2024 = evaluate_year(
        sessions, events, 2024, parameters, minimum_trades=60
    )
    assert validation_2024 is not None
    clusters_2024 = v39.validate_cluster_rules(
        trades_2024, avoid_rule, size_rule, bootstrap_resamples
    )
    result["validation_2024"] = {
        "passed": bool(validation_2024["passed"]),
        "metrics": validation_2024,
        "cluster_rules": clusters_2024,
        "session_exclusions": session_exclusions.get(2024, {}),
        "event_counts": event_exclusions.get(2024, {}),
    }
    ledger.extend(trades_2024)
    if not validation_2024["passed"]:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged selected cell failed 2024"
        return result, ledger

    load(2025)
    sessions, events, session_exclusions, event_exclusions = prepared()
    _, validation_2025, trades_2025 = evaluate_year(
        sessions, events, 2025, parameters, minimum_trades=60
    )
    assert validation_2025 is not None
    clusters_2025 = v39.validate_cluster_rules(
        trades_2025, avoid_rule, size_rule, bootstrap_resamples
    )
    result["validation_2025"] = {
        "passed": bool(validation_2025["passed"]),
        "metrics": validation_2025,
        "cluster_rules": clusters_2025,
        "session_exclusions": session_exclusions.get(2025, {}),
        "event_counts": event_exclusions.get(2025, {}),
    }
    ledger.extend(trades_2025)
    if not validation_2025["passed"]:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "historical family rejected by unchanged 2025 confirmation"
        return result, ledger

    annual_counts = [
        selected["cost_views"]["selection_2t"]["trade_count"],
        validation_2024["cost_views"]["selection_2t"]["trade_count"],
        validation_2025["cost_views"]["selection_2t"]["trade_count"],
    ]
    average_frequency = float(np.mean(annual_counts))
    validation_dates = [session.date for session in sessions
                        if session.date[:4] in {"2024", "2025"}]
    bootstrap = v33.day_cluster_bootstrap(
        trades_2024 + trades_2025,
        validation_dates,
        resamples=bootstrap_resamples,
        seed=BOOTSTRAP_SEED,
    )
    result["final_audit"] = {
        "annual_trade_counts": annual_counts,
        "average_trades_per_year": round(average_frequency, 6),
        "frequency_passed": average_frequency >= 100,
        "validation_day_bootstrap": bootstrap,
        "avoid_rule_historically_confirmed": bool(
            avoid_rule and clusters_2024["avoid_confirmed"] and clusters_2025["avoid_confirmed"]
        ),
        "size_rule_historically_confirmed": bool(
            size_rule and clusters_2024["size_confirmed"] and clusters_2025["size_confirmed"]
        ),
        "size_authorized": False,
    }
    if average_frequency >= 100 and bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0:
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = "requires untouched 2026, executable fill calibration, and forward shadow evidence"
    elif average_frequency < 100:
        result["verdict"] = "FAILED_FREQUENCY_GATE"
        result["firewall"] = "historical family rejected because activity missed the frozen target"
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "historical family rejected by combined 2024-2025 session bootstrap"
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
    """Persist only immutable v40 research evidence; never touch trading tables."""
    import psycopg2
    from psycopg2.extras import Json

    source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ledger_body = gzip.compress(
        json.dumps(ledger, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        mtime=0,
    )
    connection = psycopg2.connect(database_url, connect_timeout=15)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS valor_mes_v40_results (
                        study_id text PRIMARY KEY,
                        source_sha256 text NOT NULL,
                        result jsonb NOT NULL,
                        ledger_gzip bytea NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cursor.execute(
                    "SELECT source_sha256, result FROM valor_mes_v40_results WHERE study_id=%s",
                    (STUDY_ID,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if str(existing[0]) != source_sha:
                        raise RuntimeError("completed v40 exists with a different source hash")
                    if existing[1] != result:
                        raise RuntimeError("completed v40 source matches but result differs")
                    return
                cursor.execute("""
                    INSERT INTO valor_mes_v40_results
                        (study_id, source_sha256, result, ledger_gzip)
                    VALUES (%s, %s, %s, %s)
                """, (STUDY_ID, source_sha, Json(result), psycopg2.Binary(ledger_body)))
    finally:
        connection.close()


def postgres_loader(database_url: str) -> tuple[Callable[[str, int], pd.DataFrame], Callable[[], None]]:
    """Create a checksum-validating MES-only cache loader in a read-only transaction."""
    import psycopg2

    connection = psycopg2.connect(database_url, connect_timeout=15)
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor()

    def load(symbol: str, year: int) -> pd.DataFrame:
        if symbol != "MES" or year not in ALLOWED_YEARS:
            raise ValueError("only cached MES 2023-2025 is permitted")
        key = f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path,
                        default=Path("docs/valor_mes_v40/result.json"))
    parser.add_argument("--ledger-out", type=Path,
                        default=Path("docs/valor_mes_v40/ledger.csv"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--bootstrap-resamples", type=int, default=BOOTSTRAP_RESAMPLES)
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
    selected = result.get("discovery_2023", {}).get("selected")
    print(json.dumps({
        "study_id": STUDY_ID,
        "verdict": result["verdict"],
        "years_loaded": result["years_loaded"],
        "selected": selected["parameters"] if selected else None,
        "calendar_year_2026_sealed": result["calendar_year_2026_sealed"],
        "live_ready": result["live_ready"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
