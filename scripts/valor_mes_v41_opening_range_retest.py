"""Frozen MES v41 opening-range breakout-retest continuation research.

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
import json
import math
import os
from typing import Callable

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33
from scripts import valor_mes_v39_overnight_sweep as v39
from scripts import valor_mes_v40_vwap_reversion as v40


SCHEMA_VERSION = "valor-mes-v41-result/1.0.0"
STRATEGY_VERSION = "v41"
STUDY_ID = "valor-mes-v41-opening-range-retest-20260926"
ALLOWED_YEARS = (2023, 2024, 2025)
BREAKOUT_BUFFERS = (0.05, 0.10)
TARGET_RS = (1.5, 2.0)
HOLDS = (30, 60, 120)
CELL_ORDER = tuple(
    (buffer_atr, target_r, hold)
    for buffer_atr in BREAKOUT_BUFFERS
    for target_r in TARGET_RS
    for hold in HOLDS
)
POINT_VALUE = 5.0
TICK_SIZE = 0.25
ROUND_TRIP_FEE = 3.0
RETEST_DISTANCE_ATR = 0.05
INVALIDATION_ATR = 0.05
STOP_BUFFER_ATR = 0.05
MIN_RISK_ATR = 0.10
MAX_RISK_ATR = 0.60
DAILY_LIMIT = 2
COOLDOWN_MINUTES = 30
BOOTSTRAP_SEED = 410041
BOOTSTRAP_RESAMPLES = 10_000
COST_CASES = v39.COST_CASES
CLUSTER_FIELDS = tuple(
    field for field in v39.CLUSTER_FIELDS if field != "sweep_sequence"
) + ("opening_range_regime", "opening_drive_alignment")


def _opening_range_regime(value: float) -> str:
    if value < 0.50:
        return "narrow"
    if value <= 1.00:
        return "normal"
    return "wide"


def _feature_payload(session: v39.SessionContext, cash: pd.DataFrame,
                     end_position: int, decision_minute: int, side: int,
                     close: float, vwap: float, cumulative_volume: float,
                     opening_range_atr: float, opening_drive: float) -> dict:
    payload = v40._feature_payload(
        session, cash, end_position, decision_minute, side, close, vwap,
        cumulative_volume,
    )
    payload.update({
        "opening_range_atr": round(opening_range_atr, 10),
        "opening_range_regime": _opening_range_regime(opening_range_atr),
        "opening_drive_atr": round(opening_drive / session.atr_prior, 10),
        "opening_drive_alignment": v39._alignment(
            opening_drive, side, session.atr_prior,
        ),
    })
    return payload


def _reset(state: dict[int, str], retest_extreme: dict[int, float | None],
           side: int) -> None:
    state[side] = "looking"
    retest_extreme[side] = None


def build_events(sessions: list[v39.SessionContext]) -> tuple[list[dict], dict[int, dict[str, int]]]:
    """Build causal three-stage opening-range continuation events."""
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
        opening = cash.iloc[:30]
        expected_minutes = list(range(510, 540))
        expected_times = pd.date_range(
            pd.Timestamp(opening.timestamp.iloc[0]), periods=30, freq="1min",
        ) if len(opening) == 30 else pd.DatetimeIndex([])
        if (len(opening) != 30 or opening.minute.astype(int).tolist() != expected_minutes
                or not pd.DatetimeIndex(opening.timestamp).equals(expected_times)
                or opening.instrument_id.nunique(dropna=False) != 1):
            counts[year]["opening_range_incomplete"] += 1
            continue
        opening_high = float(opening.high.max())
        opening_low = float(opening.low.min())
        opening_width = opening_high - opening_low
        if not math.isfinite(opening_width) or opening_width <= 0:
            counts[year]["opening_range_nonpositive"] += 1
            continue
        opening_range_atr = opening_width / atr
        opening_drive = float(opening.close.iloc[-1] - opening.open.iloc[0])
        close_minute = policy[1].hour * 60 + policy[1].minute
        typical = (cash.high + cash.low + cash.close) / 3
        cumulative_pv = (typical * cash.volume).cumsum()
        cumulative_volume = cash.volume.cumsum()

        blocks: list[tuple[int, pd.DataFrame, int, float, float]] = []
        for start in range(30, len(cash), 5):
            block = cash.iloc[start:start + 5]
            if len(block) != 5:
                break
            expected = pd.date_range(
                pd.Timestamp(block.timestamp.iloc[0]), periods=5, freq="1min",
            )
            if not pd.DatetimeIndex(block.timestamp).equals(expected):
                counts[year]["noncontiguous_five_minute_block"] += 1
                continue
            decision_minute = int(block.minute.iloc[-1]) + 1
            if decision_minute > close_minute - min(HOLDS):
                continue
            volume = float(cumulative_volume.iloc[start + 4])
            if volume <= 0:
                counts[year]["nonpositive_cumulative_volume"] += 1
                continue
            vwap = float(cumulative_pv.iloc[start + 4]) / volume
            blocks.append((start, block, decision_minute, volume, vwap))

        for buffer_atr in BREAKOUT_BUFFERS:
            state = {1: "looking", -1: "looking"}
            retest_extreme: dict[int, float | None] = {1: None, -1: None}
            breakout_time: dict[int, str | None] = {1: None, -1: None}
            retest_time: dict[int, str | None] = {1: None, -1: None}
            for start, block, decision_minute, volume, vwap in blocks:
                close = float(block.close.iloc[-1])
                for side in (1, -1):
                    if state[side] == "done":
                        continue
                    boundary = opening_high if side > 0 else opening_low
                    breakout_level = boundary + side * buffer_atr * atr
                    invalidation_level = boundary - side * INVALIDATION_ATR * atr
                    beyond = side * (close - breakout_level) >= 0
                    invalidated = side * (close - invalidation_level) < 0
                    touch = (float(block.low.min()) <= boundary + RETEST_DISTANCE_ATR * atr
                             if side > 0 else
                             float(block.high.max()) >= boundary - RETEST_DISTANCE_ATR * atr)

                    if state[side] == "looking":
                        if beyond:
                            state[side] = "broken"
                            breakout_time[side] = pd.Timestamp(
                                block.timestamp.iloc[-1]
                            ).isoformat()
                        continue
                    if state[side] == "broken":
                        if invalidated:
                            _reset(state, retest_extreme, side)
                            breakout_time[side] = None
                        elif touch:
                            state[side] = "retested"
                            retest_extreme[side] = (
                                float(block.low.min()) if side > 0
                                else float(block.high.max())
                            )
                            retest_time[side] = pd.Timestamp(
                                block.timestamp.iloc[-1]
                            ).isoformat()
                        continue
                    if state[side] != "retested":
                        continue
                    current_extreme = (
                        float(block.low.min()) if side > 0
                        else float(block.high.max())
                    )
                    if retest_extreme[side] is None:
                        retest_extreme[side] = current_extreme
                    elif side > 0:
                        retest_extreme[side] = min(
                            float(retest_extreme[side]), current_extreme,
                        )
                    else:
                        retest_extreme[side] = max(
                            float(retest_extreme[side]), current_extreme,
                        )
                    if invalidated:
                        _reset(state, retest_extreme, side)
                        breakout_time[side] = None
                        retest_time[side] = None
                        continue
                    if not beyond:
                        continue

                    state[side] = "done"
                    extreme = float(retest_extreme[side])
                    stop = v39._round_stop(
                        extreme - side * STOP_BUFFER_ATR * atr, side,
                    )
                    risk = side * (close - stop)
                    key_suffix = str(buffer_atr).replace(".", "_")
                    if risk < MIN_RISK_ATR * atr or risk > MAX_RISK_ATR * atr:
                        counts[year][f"risk_outside_band_{key_suffix}"] += 1
                        continue
                    decision_time = (
                        pd.Timestamp(block.timestamp.iloc[-1])
                        + pd.Timedelta(minutes=1)
                    )
                    event = {
                        "year": year,
                        "date": session.date,
                        "side": side,
                        "side_label": "long" if side > 0 else "short",
                        "instrument_id": int(session.instrument_id),
                        "signal_bar_start": pd.Timestamp(
                            block.timestamp.iloc[0]
                        ).isoformat(),
                        "decision_time": decision_time.isoformat(),
                        "decision_minute": decision_minute,
                        "time_bucket": v39._time_bucket(decision_minute),
                        "sweep_number": 1,
                        "sweep_sequence": "first",
                        "breakout_buffer_atr": buffer_atr,
                        "opening_range_high": opening_high,
                        "opening_range_low": opening_low,
                        "breakout_time": breakout_time[side],
                        "retest_time": retest_time[side],
                        "signal_vwap": round(vwap, 10),
                        "reference_price": close,
                        "stop_price": stop,
                        "planned_risk_points": round(risk, 10),
                        "overshoot_atr": round(
                            side * (close - boundary) / atr, 10,
                        ),
                        "reclaim_atr": round(
                            side * (close - boundary) / atr, 10,
                        ),
                    }
                    event.update(_feature_payload(
                        session, cash, start + 4, decision_minute, side, close,
                        vwap, volume, opening_range_atr, opening_drive,
                    ))
                    events.append(event)
                    counts[year][f"candidate_events_{key_suffix}"] += 1
    return sorted(
        events,
        key=lambda row: (row["decision_time"], row["side"], row["breakout_buffer_atr"]),
    ), {year: dict(value) for year, value in counts.items()}


def _record_trade(event: dict, target_r: float, hold: int,
                  entry_time: pd.Timestamp, exit_time: pd.Timestamp,
                  entry: float, target: float, exit_price: float, reason: str,
                  mae: float, mfe: float) -> dict:
    side = int(event["side"])
    gross = round(side * (exit_price - entry) * POINT_VALUE, 6)
    trade = {key: value for key, value in event.items()
             if key not in {"decision_minute", "reference_price"}}
    trade.update({
        "target_r": target_r,
        "hold_minutes": hold,
        "entry_time": entry_time.isoformat(),
        "exit_time": exit_time.isoformat(),
        "entry_price": entry,
        "target_price": target,
        "exit_price": exit_price,
        "exit_reason": reason,
        "actual_risk_points": round(
            side * (entry - float(event["stop_price"])), 10,
        ),
        "mae_points": round(mae, 10),
        "mfe_points": round(mfe, 10),
        "gross_dollars": gross,
    })
    for name, ticks in COST_CASES[1:]:
        trade[name] = v40._cost(gross, ticks)
    return trade


def replay_cell(sessions: list[v39.SessionContext], events: list[dict], year: int,
                buffer_atr: float, target_r: float, hold: int) -> tuple[list[dict], dict]:
    if (buffer_atr, target_r, hold) not in CELL_ORDER:
        raise ValueError("cell outside frozen v41 family")
    session_map = {session.date: session for session in sessions
                   if int(session.date[:4]) == year}
    trades: list[dict] = []
    skips: Counter = Counter()
    next_allowed: dict[str, pd.Timestamp] = {}
    daily_count: Counter = Counter()
    candidates = [
        event for event in events
        if event["year"] == year
        and float(event["breakout_buffer_atr"]) == buffer_atr
    ]
    for event in candidates:
        session = session_map.get(event["date"])
        if session is None:
            skips["session_missing"] += 1
            continue
        decision = pd.Timestamp(event["decision_time"])
        if decision < next_allowed.get(
                event["date"], pd.Timestamp.min.tz_localize("UTC")):
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
        reference = float(event["reference_price"])
        risk = float(event["planned_risk_points"])
        target = v39._round_target(reference + side * target_r * risk, side)
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
                exit_price, exit_time, reason = (
                    stop, row_time + pd.Timedelta(minutes=1), "stop",
                )
                mae = max(mae, max(0.0, side * (entry - stop)))
                break
            if target_hit:
                exit_price, exit_time, reason = (
                    target, row_time + pd.Timedelta(minutes=1), "target",
                )
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
            event, target_r, hold, decision, exit_time, entry, target,
            exit_price, reason, mae, mfe,
        ))
        daily_count[event["date"]] += 1
        next_allowed[event["date"]] = exit_time + pd.Timedelta(
            minutes=COOLDOWN_MINUTES,
        )
    return trades, {"skips": dict(skips), "candidate_events": len(candidates)}


def summarize_cell(trades: list[dict], year: int, replay: dict,
                   parameters: tuple[float, float, int]) -> dict:
    buffer_atr, target_r, hold = parameters
    return {
        "year": year,
        "parameters": {
            "breakout_buffer_atr": buffer_atr,
            "target_r": target_r,
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


def _selection_rank(summary: dict) -> tuple:
    metrics = summary["cost_views"]["selection_2t"]
    ratio = metrics["net_to_drawdown"]
    params = summary["parameters"]
    cell_index = CELL_ORDER.index((
        float(params["breakout_buffer_atr"]),
        float(params["target_r"]),
        int(params["hold_minutes"]),
    ))
    return (
        float(ratio) if ratio is not None else -math.inf,
        float(metrics["average_trade"]
              if metrics["average_trade"] is not None else -math.inf),
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
            float(parameters["breakout_buffer_atr"]),
            float(parameters["target_r"]),
            int(parameters["hold_minutes"]),
        ),)
    cells: list[dict] = []
    ledgers: dict[tuple[float, float, int], list[dict]] = {}
    for cell in cells_to_run:
        trades, replay = replay_cell(sessions, events, year, *cell)
        summary = summarize_cell(trades, year, replay, cell)
        summary["passed"] = v40.annual_passes(summary, minimum_trades)
        cells.append(summary)
        ledgers[cell] = trades
    if parameters is not None:
        return cells, cells[0], ledgers[next(iter(ledgers))]
    qualified = [cell for cell in cells if cell["passed"]]
    selected = max(qualified, key=_selection_rank) if qualified else None
    diagnostic = _diagnostic_cell(cells)
    ledger: list[dict] = []
    if diagnostic is not None:
        p = (selected or diagnostic)["parameters"]
        ledger = ledgers[(float(p["breakout_buffer_atr"]),
                          float(p["target_r"]), int(p["hold_minutes"]))]
    return cells, selected, ledger


def cluster_audit(trades: list[dict], resamples: int) -> dict:
    rows: list[dict] = []
    for field in CLUSTER_FIELDS:
        values = sorted({str(trade.get(field, "unknown")) for trade in trades})
        for value in values:
            cohort = [trade for trade in trades
                      if str(trade.get(field, "unknown")) == value]
            selection = v39._pnl_metrics(cohort, "selection_2t")
            stress = v39._pnl_metrics(cohort, "stress_4t")
            seed_material = f"{BOOTSTRAP_SEED}:{field}:{value}".encode()
            seed = int(hashlib.sha256(seed_material).hexdigest()[:8], 16)
            bootstrap = v39._condition_bootstrap(
                cohort, "selection_2t", seed, resamples,
            )
            first = [row for row in cohort if row["date"][5:7] <= "06"]
            second = [row for row in cohort if row["date"][5:7] >= "07"]
            months = {row["date"][:7] for row in cohort}
            avoid_eligible = (
                selection["trade_count"] >= 40
                and v39._profit_factor_value(selection) < 0.80
                and selection["net_dollars"] < 0
                and bootstrap["upper_95"] is not None
                and bootstrap["upper_95"] < 0
            )
            size_eligible = (
                selection["trade_count"] >= 40
                and v39._profit_factor_value(selection) >= 1.40
                and selection["average_trade"] is not None
                and selection["average_trade"] >= 12
                and stress["net_dollars"] > 0
                and bootstrap["lower_95"] is not None
                and bootstrap["lower_95"] > 0
                and len(months) >= 6
                and sum(float(row["selection_2t"]) for row in first) > 0
                and sum(float(row["selection_2t"]) for row in second) > 0
            )
            rows.append({
                "field": field,
                "value": value,
                "selection_2t": selection,
                "stress_4t": stress,
                "bootstrap": bootstrap,
                "active_months": len(months),
                "avoid_eligible": avoid_eligible,
                "size_eligible": size_eligible,
            })
    avoid = [row for row in rows if row["avoid_eligible"]]
    size = [row for row in rows if row["size_eligible"]]
    selected_avoid = min(avoid, key=lambda row: (
        row["bootstrap"]["upper_95"], row["selection_2t"]["average_trade"],
        row["field"], row["value"],
    )) if avoid else None
    selected_size = max(size, key=lambda row: (
        row["bootstrap"]["lower_95"], row["selection_2t"]["average_trade"],
        row["field"], row["value"],
    )) if size else None
    return {
        "conditions": rows,
        "selected_avoid": ({"field": selected_avoid["field"],
                            "value": selected_avoid["value"]}
                           if selected_avoid else None),
        "selected_size": ({"field": selected_size["field"],
                           "value": selected_size["value"]}
                          if selected_size else None),
        "streaks": v39._streaks(trades, "selection_2t"),
        "five_active_session_windows": v39._five_session_windows(
            trades, "selection_2t",
        ),
        "winner_mae_mfe": {
            "mae_mean": round(float(np.mean([
                row["mae_points"] for row in trades if row["selection_2t"] > 0
            ])), 6) if any(row["selection_2t"] > 0 for row in trades) else None,
            "mfe_mean": round(float(np.mean([
                row["mfe_points"] for row in trades if row["selection_2t"] > 0
            ])), 6) if any(row["selection_2t"] > 0 for row in trades) else None,
        },
        "loser_mae_mfe": {
            "mae_mean": round(float(np.mean([
                row["mae_points"] for row in trades if row["selection_2t"] < 0
            ])), 6) if any(row["selection_2t"] < 0 for row in trades) else None,
            "mfe_mean": round(float(np.mean([
                row["mfe_points"] for row in trades if row["selection_2t"] < 0
            ])), 6) if any(row["selection_2t"] < 0 for row in trades) else None,
        },
    }


def _rule_cohort(trades: list[dict], rule: dict | None) -> list[dict]:
    if rule is None:
        return []
    return [row for row in trades
            if str(row.get(rule["field"], "unknown")) == rule["value"]]


def validate_cluster_rules(trades: list[dict], avoid: dict | None,
                           size: dict | None, resamples: int) -> dict:
    avoid_cohort = _rule_cohort(trades, avoid)
    size_cohort = _rule_cohort(trades, size)
    avoid_metrics = v39._pnl_metrics(avoid_cohort, "selection_2t")
    size_selection = v39._pnl_metrics(size_cohort, "selection_2t")
    size_stress = v39._pnl_metrics(size_cohort, "stress_4t")
    avoid_boot = v39._condition_bootstrap(
        avoid_cohort, "selection_2t", BOOTSTRAP_SEED + 101, resamples,
    )
    size_boot = v39._condition_bootstrap(
        size_cohort, "selection_2t", BOOTSTRAP_SEED + 202, resamples,
    )
    filtered = [row for row in trades if row not in avoid_cohort]
    tiered = []
    for row in filtered:
        copy = dict(row)
        multiplier = 2 if row in size_cohort else 1
        copy["tiered_selection_2t"] = multiplier * float(row["selection_2t"])
        tiered.append(copy)
    return {
        "avoid_rule": avoid,
        "avoid_cohort": avoid_metrics,
        "avoid_bootstrap": avoid_boot,
        "avoid_confirmed": bool(
            avoid and avoid_metrics["trade_count"] >= 40
            and v39._profit_factor_value(avoid_metrics) < 0.80
            and avoid_metrics["net_dollars"] < 0
            and avoid_boot["upper_95"] is not None
            and avoid_boot["upper_95"] < 0
        ),
        "filtered_strategy": v39._pnl_metrics(filtered, "selection_2t"),
        "size_rule": size,
        "size_cohort_selection": size_selection,
        "size_cohort_stress": size_stress,
        "size_bootstrap": size_boot,
        "size_confirmed": bool(
            size and size_selection["trade_count"] >= 40
            and v39._profit_factor_value(size_selection) >= 1.40
            and size_selection["average_trade"] is not None
            and size_selection["average_trade"] >= 12
            and size_stress["net_dollars"] > 0
            and size_boot["lower_95"] is not None
            and size_boot["lower_95"] > 0
        ),
        "tiered_two_contract_diagnostic": v39._pnl_metrics(
            tiered, "tiered_selection_2t",
        ),
    }


def _result_base() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "study_id": STUDY_ID,
        "family": "opening_range_breakout_retest_continuation",
        "research_only": True,
        "production_changed": False,
        "live_ready": False,
        "calendar_year_2026_sealed": True,
        "years_loaded": [],
        "source_cache": {},
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "execution": {
            "evidence": "one-minute trade-print OHLC proxy; executable bid/ask and latency not verified",
            "fill_convention": "three distinct completed five-minute stages; next one-minute open; stop-first ambiguity; one-tick target trade-through",
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

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v41 may read only 2023-2025")
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
        events, event_exclusions = build_events(sessions)
        return sessions, events, session_exclusions, event_exclusions

    load(2023)
    sessions, events, session_exclusions, event_exclusions = prepared()
    cells, selected, diagnostic_ledger = evaluate_year(sessions, events, 2023)
    diagnostic_cell = _diagnostic_cell(cells)
    audit = cluster_audit(diagnostic_ledger, bootstrap_resamples)
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
        result["firewall"] = (
            "2024 and 2025 unopened because no frozen 2023 cell qualified"
        )
        return result, diagnostic_ledger

    parameters = selected["parameters"]
    avoid_rule = audit["selected_avoid"]
    size_rule = audit["selected_size"]
    ledger = list(diagnostic_ledger)

    load(2024)
    sessions, events, session_exclusions, event_exclusions = prepared()
    _, validation_2024, trades_2024 = evaluate_year(
        sessions, events, 2024, parameters, minimum_trades=60,
    )
    assert validation_2024 is not None
    clusters_2024 = validate_cluster_rules(
        trades_2024, avoid_rule, size_rule, bootstrap_resamples,
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
        result["firewall"] = (
            "2025 unopened because the unchanged selected cell failed 2024"
        )
        return result, ledger

    load(2025)
    sessions, events, session_exclusions, event_exclusions = prepared()
    _, validation_2025, trades_2025 = evaluate_year(
        sessions, events, 2025, parameters, minimum_trades=60,
    )
    assert validation_2025 is not None
    clusters_2025 = validate_cluster_rules(
        trades_2025, avoid_rule, size_rule, bootstrap_resamples,
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
        result["firewall"] = (
            "historical family rejected by unchanged 2025 confirmation"
        )
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
            avoid_rule and clusters_2024["avoid_confirmed"]
            and clusters_2025["avoid_confirmed"]
        ),
        "size_rule_historically_confirmed": bool(
            size_rule and clusters_2024["size_confirmed"]
            and clusters_2025["size_confirmed"]
        ),
        "size_authorized": False,
    }
    if (average_frequency >= 100 and bootstrap["lower_95"] is not None
            and bootstrap["lower_95"] > 0):
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = (
            "requires untouched 2026, executable fill calibration, and forward shadow evidence"
        )
    elif average_frequency < 100:
        result["verdict"] = "FAILED_FREQUENCY_GATE"
        result["firewall"] = (
            "historical family rejected because activity missed the frozen target"
        )
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = (
            "historical family rejected by combined 2024-2025 session bootstrap"
        )
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
    """Persist only immutable v41 research evidence; never touch trading tables."""
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
                    CREATE TABLE IF NOT EXISTS valor_mes_v41_results (
                        study_id text PRIMARY KEY,
                        source_sha256 text NOT NULL,
                        result jsonb NOT NULL,
                        ledger_gzip bytea NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cursor.execute(
                    "SELECT source_sha256, result FROM valor_mes_v41_results WHERE study_id=%s",
                    (STUDY_ID,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if str(existing[0]) != source_sha:
                        raise RuntimeError(
                            "completed v41 exists with a different source hash"
                        )
                    if existing[1] != result:
                        raise RuntimeError(
                            "completed v41 source matches but result differs"
                        )
                    return
                cursor.execute("""
                    INSERT INTO valor_mes_v41_results
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
                        default=Path("docs/valor_mes_v41/result.json"))
    parser.add_argument("--ledger-out", type=Path,
                        default=Path("docs/valor_mes_v41/ledger.csv"))
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
