"""Frozen MES v39 overnight-extreme sweep-rejection research.

Research only. Reads checksummed cached MES one-minute OHLCV for 2023-2025,
never calls a vendor or broker, and refuses calendar year 2026. Fills are
trade-print planning scenarios, not executable bid/ask evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
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
from scripts import valor_mes_v36_overnight_inventory as v36


SCHEMA_VERSION = "valor-mes-v39-result/1.0.1"
STRATEGY_VERSION = "v39"
STUDY_ID = "valor-mes-v39-overnight-sweep-20260926-r1"
ALLOWED_YEARS = (2023, 2024, 2025)
DEPTHS = (0.10, 0.20)
TARGET_RS = (1.5, 2.0)
HOLDS = (30, 60, 120)
CELL_ORDER = tuple((depth, target_r, hold)
                   for depth in DEPTHS
                   for target_r in TARGET_RS
                   for hold in HOLDS)
POINT_VALUE = 5.0
TICK_SIZE = 0.25
ROUND_TRIP_FEE = 3.0
STOP_BUFFER_ATR = 0.05
MIN_RISK_ATR = 0.10
MAX_RISK_ATR = 0.50
RESET_INSIDE_ATR = 0.25
DAILY_LIMIT = 3
COOLDOWN_MINUTES = 30
BOOTSTRAP_SEED = 390039
BOOTSTRAP_RESAMPLES = 10_000
COST_CASES = (
    ("raw_gross", None),
    ("fee_0t", 0),
    ("planning_1t", 1),
    ("selection_2t", 2),
    ("stress_4t", 4),
)
CLUSTER_FIELDS = (
    "time_bucket", "side_label", "sweep_sequence", "atr_regime",
    "overnight_range_regime", "overnight_alignment", "gap_alignment",
    "return_15_alignment", "return_30_alignment", "return_60_alignment",
    "efficiency_regime", "vwap_regime", "relative_volume_regime",
)
LEDGER_FIELDS = (
    "year", "date", "depth_atr_threshold", "target_r", "hold_minutes",
    "side", "side_label", "instrument_id", "time_bucket", "sweep_sequence",
    "sweep_number", "atr_prior", "atr_percentile", "atr_regime",
    "overnight_high", "overnight_low", "overnight_range_atr",
    "overnight_range_regime", "overnight_return_atr", "overnight_alignment",
    "gap_atr", "gap_alignment", "overshoot_atr", "reclaim_atr",
    "return_15_atr", "return_15_alignment", "return_30_atr",
    "return_30_alignment", "return_60_atr", "return_60_alignment",
    "efficiency_60", "efficiency_regime", "vwap_distance_atr",
    "vwap_regime", "relative_volume", "relative_volume_regime",
    "signal_bar_start", "decision_time", "entry_time", "exit_time",
    "entry_price", "stop_price", "target_price", "exit_price", "exit_reason",
    "planned_risk_points", "actual_risk_points", "mae_points", "mfe_points",
    "gross_dollars", "fee_0t", "planning_1t", "selection_2t", "stress_4t",
)


@dataclass(frozen=True)
class SessionContext:
    date: str
    cash: pd.DataFrame
    instrument_id: int
    atr_prior: float
    atr_percentile: float | None
    overnight_high: float
    overnight_low: float
    overnight_return: float
    prior_close: float | None
    overnight_first: str
    overnight_last: str
    prior_cash: tuple[pd.DataFrame, ...]


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _round_stop(value: float, side: int) -> float:
    """Round a protective stop away from the entry reference."""
    units = value / TICK_SIZE
    return (math.floor(units + 1e-9) if side > 0
            else math.ceil(units - 1e-9)) * TICK_SIZE


def _round_target(value: float, side: int) -> float:
    """Round a target away from the entry reference."""
    units = value / TICK_SIZE
    return (math.ceil(units - 1e-9) if side > 0
            else math.floor(units + 1e-9)) * TICK_SIZE


def _cost(gross: float, ticks_each_side: int | None) -> float:
    if ticks_each_side is None:
        return round(float(gross), 6)
    cost = ROUND_TRIP_FEE + 2 * int(ticks_each_side) * TICK_SIZE * POINT_VALUE
    return round(float(gross) - cost, 6)


def _calendar_days(year: int) -> list[str]:
    current = date(year, 1, 1)
    end = date(year, 12, 31)
    output: list[str] = []
    while current <= end:
        if v33.cash.session(current) is not None:
            output.append(current.isoformat())
        current += pd.Timedelta(days=1).to_pytimedelta()
    return output


def _prior_percentile(history: list[float], value: float) -> float | None:
    if len(history) < 20:
        return None
    prior = np.asarray(history[-60:], dtype=float)
    return float((prior <= value).sum() / len(prior))


def _atr_regime(percentile: float | None) -> str:
    if percentile is None:
        return "unknown"
    if percentile <= 1 / 3:
        return "low"
    if percentile <= 2 / 3:
        return "mid"
    return "high"


def build_sessions(frames: Iterable[pd.DataFrame]) -> tuple[list[SessionContext], dict[int, dict[str, int]]]:
    """Build exact-contract causal sessions and mutually exclusive exclusions."""
    prepared = v36.prepare_raw(frames)
    complete_cash = v33._complete_sessions(prepared)
    atr_by_day = v36.prior_atr(complete_cash)
    years = sorted({int(day[:4]) for day in prepared.date.unique()
                    if int(day[:4]) in ALLOWED_YEARS})
    exclusions = {year: Counter() for year in years}
    atr_history: dict[int, list[float]] = defaultdict(list)
    cash_history: dict[int, list[pd.DataFrame]] = defaultdict(list)
    last_close: dict[int, float] = {}
    sessions: list[SessionContext] = []

    for year in years:
        for day in _calendar_days(year):
            cash = complete_cash.get(day)
            if cash is None:
                exclusions[year]["incomplete_cash_session"] += 1
                continue
            contract = int(cash.instrument_id.iloc[0])
            atr = atr_by_day.get(day)
            overnight, reason = v36.overnight_window(prepared, day, contract)
            if atr is None:
                exclusions[year]["prior_atr_unavailable"] += 1
            elif reason is not None:
                exclusions[year][str(reason)] += 1
            else:
                assert overnight is not None
                percentile = _prior_percentile(atr_history[contract], float(atr))
                sessions.append(SessionContext(
                    date=day,
                    cash=cash,
                    instrument_id=contract,
                    atr_prior=float(atr),
                    atr_percentile=percentile,
                    overnight_high=float(overnight.high.max()),
                    overnight_low=float(overnight.low.min()),
                    overnight_return=float(overnight.close.iloc[-1] - overnight.open.iloc[0]),
                    prior_close=last_close.get(contract),
                    overnight_first=pd.Timestamp(overnight.timestamp.iloc[0]).isoformat(),
                    overnight_last=pd.Timestamp(overnight.timestamp.iloc[-1]).isoformat(),
                    prior_cash=tuple(cash_history[contract][-20:]),
                ))
                exclusions[year]["usable_sessions"] += 1

            if atr is not None:
                atr_history[contract].append(float(atr))
            cash_history[contract].append(cash)
            if len(cash_history[contract]) > 20:
                cash_history[contract] = cash_history[contract][-20:]
            last_close[contract] = float(cash.close.iloc[-1])
    return sessions, {year: dict(value) for year, value in exclusions.items()}


def _alignment(value: float | None, side: int, atr: float) -> str:
    if value is None or not _finite(value):
        return "unknown"
    scaled = float(value) / atr
    if abs(scaled) < 0.05:
        return "flat"
    return "aligned" if (scaled > 0) == (side > 0) else "opposed"


def _time_bucket(minute: int) -> str:
    if minute < 570:
        return "opening"
    if minute < 660:
        return "morning"
    if minute < 780:
        return "midday"
    return "afternoon"


def _range_regime(value: float) -> str:
    if value < 0.75:
        return "narrow"
    if value <= 1.25:
        return "normal"
    return "wide"


def _efficiency_regime(value: float) -> str:
    if value < 0.30:
        return "low"
    if value < 0.60:
        return "mid"
    return "high"


def _relative_volume_regime(value: float | None) -> str:
    if value is None or not _finite(value):
        return "unknown"
    if float(value) < 0.80:
        return "low"
    if float(value) <= 1.20:
        return "normal"
    return "high"


def _window_return(cash: pd.DataFrame, end_position: int, minutes: int) -> float:
    start = end_position - minutes + 1
    if start < 0:
        return 0.0
    return float(cash.close.iloc[end_position] - cash.open.iloc[start])


def _window_efficiency(cash: pd.DataFrame, end_position: int, minutes: int) -> float:
    start = max(0, end_position - minutes + 1)
    window = cash.iloc[start:end_position + 1]
    if window.empty:
        return 0.0
    changes = np.r_[
        abs(float(window.close.iloc[0]) - float(window.open.iloc[0])),
        np.abs(np.diff(window.close.to_numpy(float))),
    ]
    path = float(changes.sum())
    displacement = abs(float(window.close.iloc[-1]) - float(window.open.iloc[0]))
    return displacement / path if path > 0 else 0.0


def _relative_volume(session: SessionContext, decision_minute: int,
                     current_cumulative: float) -> float | None:
    priors: list[float] = []
    last_observed = decision_minute - 1
    for frame in session.prior_cash:
        if frame.empty or int(frame.minute.max()) < last_observed:
            continue
        value = float(frame.loc[frame.minute <= last_observed, "volume"].sum())
        if value > 0:
            priors.append(value)
    if len(priors) < 20:
        return None
    baseline = float(np.median(priors[-20:]))
    return current_cumulative / baseline if baseline > 0 else None


def build_events(sessions: list[SessionContext]) -> tuple[list[dict], dict[int, dict[str, int]]]:
    """Create minimum-depth failed-sweep events from completed five-minute bars."""
    events: list[dict] = []
    counts: dict[int, Counter] = defaultdict(Counter)
    for session in sessions:
        year = int(session.date[:4])
        cash = session.cash.reset_index(drop=True)
        atr = session.atr_prior
        overnight_range_atr = (session.overnight_high - session.overnight_low) / atr
        gap = (float(cash.open.iloc[0]) - session.prior_close
               if session.prior_close is not None else None)
        armed = {1: True, -1: True}
        sequence = {1: 0, -1: 0}
        previous_five_close: float | None = None
        cumulative_pv = 0.0
        cumulative_volume = 0.0
        for start in range(0, len(cash), 5):
            block = cash.iloc[start:start + 5]
            if len(block) != 5:
                break
            expected = pd.date_range(pd.Timestamp(block.timestamp.iloc[0]), periods=5, freq="1min")
            if not pd.DatetimeIndex(block.timestamp).equals(expected):
                counts[year]["noncontiguous_five_minute_block"] += 1
                continue
            decision_minute = int(block.minute.iloc[-1]) + 1
            policy = v33.cash.session(session.date)
            assert policy is not None
            close_minute = policy[1].hour * 60 + policy[1].minute
            if decision_minute < 515 or decision_minute > close_minute - min(HOLDS):
                cumulative_pv += float(((block.high + block.low + block.close) / 3 * block.volume).sum())
                cumulative_volume += float(block.volume.sum())
                previous_five_close = float(block.close.iloc[-1])
                continue

            cumulative_pv += float(((block.high + block.low + block.close) / 3 * block.volume).sum())
            cumulative_volume += float(block.volume.sum())
            close = float(block.close.iloc[-1])
            high = float(block.high.max())
            low = float(block.low.min())
            if previous_five_close is not None:
                if not armed[-1] and previous_five_close <= session.overnight_high - RESET_INSIDE_ATR * atr:
                    armed[-1] = True
                if not armed[1] and previous_five_close >= session.overnight_low + RESET_INSIDE_ATR * atr:
                    armed[1] = True

            short_overshoot = (high - session.overnight_high) / atr
            long_overshoot = (session.overnight_low - low) / atr
            short_signal = armed[-1] and short_overshoot >= min(DEPTHS) and close < session.overnight_high
            long_signal = armed[1] and long_overshoot >= min(DEPTHS) and close > session.overnight_low
            if short_signal and long_signal:
                counts[year]["ambiguous_both_sides"] += 1
                armed[-1] = armed[1] = False
                previous_five_close = close
                continue
            if not (short_signal or long_signal):
                previous_five_close = close
                continue

            side = -1 if short_signal else 1
            overshoot = short_overshoot if side < 0 else long_overshoot
            reclaim = ((session.overnight_high - close) / atr if side < 0
                       else (close - session.overnight_low) / atr)
            extreme = high if side < 0 else low
            stop = _round_stop(extreme - side * STOP_BUFFER_ATR * atr, side)
            risk = side * (close - stop)
            if risk < MIN_RISK_ATR * atr or risk > MAX_RISK_ATR * atr:
                counts[year]["risk_outside_frozen_band"] += 1
                armed[side] = False
                previous_five_close = close
                continue

            sequence[side] += 1
            armed[side] = False
            ret15 = _window_return(cash, start + 4, 15)
            ret30 = _window_return(cash, start + 4, 30)
            ret60 = _window_return(cash, start + 4, 60)
            efficiency = _window_efficiency(cash, start + 4, 60)
            vwap = cumulative_pv / cumulative_volume if cumulative_volume > 0 else close
            relvol = _relative_volume(session, decision_minute, cumulative_volume)
            vwap_scaled = side * (close - vwap) / atr
            vwap_regime = "aligned" if vwap_scaled > 0.05 else "opposed" if vwap_scaled < -0.05 else "near"
            events.append({
                "year": year, "date": session.date, "side": side,
                "side_label": "long" if side > 0 else "short",
                "instrument_id": session.instrument_id,
                "signal_index": int(block.raw_index.iloc[-1]),
                "signal_bar_start": pd.Timestamp(block.timestamp.iloc[0]).isoformat(),
                "decision_time": (pd.Timestamp(block.timestamp.iloc[-1]) + pd.Timedelta(minutes=1)).isoformat(),
                "decision_minute": decision_minute,
                "time_bucket": _time_bucket(decision_minute),
                "sweep_number": sequence[side],
                "sweep_sequence": "first" if sequence[side] == 1 else "repeat",
                "atr_prior": round(atr, 10),
                "atr_percentile": (round(session.atr_percentile, 10)
                                   if session.atr_percentile is not None else None),
                "atr_regime": _atr_regime(session.atr_percentile),
                "overnight_high": session.overnight_high,
                "overnight_low": session.overnight_low,
                "overnight_first": session.overnight_first,
                "overnight_last": session.overnight_last,
                "overnight_range_atr": round(overnight_range_atr, 10),
                "overnight_range_regime": _range_regime(overnight_range_atr),
                "overnight_return_atr": round(session.overnight_return / atr, 10),
                "overnight_alignment": _alignment(session.overnight_return, side, atr),
                "gap_atr": round(gap / atr, 10) if gap is not None else None,
                "gap_alignment": _alignment(gap, side, atr),
                "overshoot_atr": round(overshoot, 10),
                "reclaim_atr": round(reclaim, 10),
                "return_15_atr": round(ret15 / atr, 10),
                "return_15_alignment": _alignment(ret15, side, atr),
                "return_30_atr": round(ret30 / atr, 10),
                "return_30_alignment": _alignment(ret30, side, atr),
                "return_60_atr": round(ret60 / atr, 10),
                "return_60_alignment": _alignment(ret60, side, atr),
                "efficiency_60": round(efficiency, 10),
                "efficiency_regime": _efficiency_regime(efficiency),
                "vwap_distance_atr": round((close - vwap) / atr, 10),
                "vwap_regime": vwap_regime,
                "relative_volume": round(relvol, 10) if relvol is not None else None,
                "relative_volume_regime": _relative_volume_regime(relvol),
                "reference_price": close, "stop_price": stop,
                "planned_risk_points": round(risk, 10),
            })
            counts[year]["candidate_events"] += 1
            previous_five_close = close
    return sorted(events, key=lambda row: (row["decision_time"], row["side"])), {
        year: dict(value) for year, value in counts.items()
    }


def _record_trade(event: dict, depth: float, target_r: float, hold: int,
                  entry_time: pd.Timestamp, exit_time: pd.Timestamp,
                  entry: float, stop: float, target: float, exit_price: float,
                  reason: str, mae: float, mfe: float) -> dict:
    side = int(event["side"])
    gross = round(side * (exit_price - entry) * POINT_VALUE, 6)
    trade = {key: value for key, value in event.items()
             if key not in {"signal_index", "decision_minute", "reference_price"}}
    trade.update({
        "depth_atr_threshold": depth, "target_r": target_r,
        "hold_minutes": hold, "entry_time": entry_time.isoformat(),
        "exit_time": exit_time.isoformat(), "entry_price": entry,
        "stop_price": stop, "target_price": target, "exit_price": exit_price,
        "exit_reason": reason,
        "actual_risk_points": round(side * (entry - stop), 10),
        "mae_points": round(mae, 10), "mfe_points": round(mfe, 10),
        "gross_dollars": gross,
    })
    for name, ticks in COST_CASES[1:]:
        trade[name] = _cost(gross, ticks)
    return trade


def replay_cell(sessions: list[SessionContext], events: list[dict], year: int,
                depth: float, target_r: float, hold: int) -> tuple[list[dict], dict]:
    if (depth, target_r, hold) not in CELL_ORDER:
        raise ValueError("cell outside frozen v39 family")
    session_map = {session.date: session for session in sessions if int(session.date[:4]) == year}
    trades: list[dict] = []
    skips: Counter = Counter()
    next_allowed: dict[str, pd.Timestamp] = {}
    daily_count: Counter = Counter()
    for event in events:
        if event["year"] != year or float(event["overshoot_atr"]) < depth:
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
        reference = float(event["reference_price"])
        stop = float(event["stop_price"])
        planned_risk = float(event["planned_risk_points"])
        target = _round_target(reference + side * target_r * planned_risk, side)
        entry = float(path.open.iloc[0])
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
            stop_hit = ((side > 0 and float(row.low) <= stop)
                        or (side < 0 and float(row.high) >= stop))
            target_hit = ((side > 0 and float(row.high) >= target + TICK_SIZE)
                          or (side < 0 and float(row.low) <= target - TICK_SIZE))
            if stop_hit:
                exit_price, exit_time, reason = stop, row_time + pd.Timedelta(minutes=1), "stop"
                mae = max(mae, max(0.0, side * (entry - stop)))
                break
            if side * (float(row.open) - target) >= 0 or target_hit:
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
            event, depth, target_r, hold, decision, exit_time,
            entry, stop, target, exit_price, reason, mae, mfe,
        ))
        daily_count[event["date"]] += 1
        next_allowed[event["date"]] = exit_time + pd.Timedelta(minutes=COOLDOWN_MINUTES)
    return trades, {"skips": dict(skips), "candidate_events": sum(
        1 for event in events if event["year"] == year and float(event["overshoot_atr"]) >= depth
    )}


def _profit_factor(values: np.ndarray) -> float | None:
    wins = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses == 0:
        return None
    return round(wins / losses, 6)


def _profit_factor_value(metrics: dict) -> float:
    value = metrics.get("profit_factor")
    if value is None:
        return math.inf if metrics.get("net_dollars", 0) > 0 else 0.0
    return float(value)


def _pnl_metrics(trades: list[dict], key: str) -> dict:
    ordered = sorted(trades, key=lambda row: (row["entry_time"], row["side"]))
    values = np.asarray([float(row[key]) for row in ordered], dtype=float)
    equity = np.r_[0.0, values.cumsum()]
    drawdown = float((np.maximum.accumulate(equity) - equity).max()) if len(values) else 0.0
    monthly: dict[str, float] = defaultdict(float)
    for row in ordered:
        monthly[row["date"][:7]] += float(row[key])
    monthly = {month: round(value, 6) for month, value in sorted(monthly.items())}
    best_month = max(monthly.values()) if monthly else 0.0
    net = float(values.sum()) if len(values) else 0.0
    return {
        "trade_count": len(values), "net_dollars": round(net, 6),
        "profit_factor": _profit_factor(values),
        "average_trade": round(float(values.mean()), 6) if len(values) else None,
        "win_rate": round(float((values > 0).mean()), 6) if len(values) else None,
        "max_drawdown": round(drawdown, 6),
        "net_to_drawdown": round(net / drawdown, 6) if drawdown > 0 else None,
        "best_month_removed_net": round(net - best_month, 6),
        "monthly": monthly,
    }


def summarize_cell(trades: list[dict], year: int, replay: dict) -> dict:
    return {
        "year": year,
        "parameters": {
            "depth_atr_threshold": trades[0]["depth_atr_threshold"] if trades else None,
            "target_r": trades[0]["target_r"] if trades else None,
            "hold_minutes": trades[0]["hold_minutes"] if trades else None,
        },
        "replay": replay,
        "cost_views": {name: _pnl_metrics(trades, "gross_dollars" if ticks is None else name)
                       for name, ticks in COST_CASES},
        "long_trades": sum(int(row["side"]) > 0 for row in trades),
        "short_trades": sum(int(row["side"]) < 0 for row in trades),
        "exit_reasons": dict(Counter(row["exit_reason"] for row in trades)),
    }


def annual_passes(summary: dict) -> bool:
    selection = summary["cost_views"]["selection_2t"]
    stress = summary["cost_views"]["stress_4t"]
    ratio = selection["net_to_drawdown"]
    return (
        selection["trade_count"] >= 150
        and selection["net_dollars"] > 0
        and _profit_factor_value(selection) >= 1.20
        and selection["average_trade"] is not None
        and selection["average_trade"] >= 8.0
        and ratio is not None and ratio >= 1.0
        and stress["net_dollars"] > 0
        and selection["best_month_removed_net"] > 0
    )


def _selection_rank(summary: dict) -> tuple:
    metrics = summary["cost_views"]["selection_2t"]
    ratio = metrics["net_to_drawdown"]
    params = summary["parameters"]
    cell_index = CELL_ORDER.index((
        float(params["depth_atr_threshold"]), float(params["target_r"]), int(params["hold_minutes"])
    ))
    return (float(ratio) if ratio is not None else -math.inf,
            float(metrics["average_trade"] or -math.inf), -cell_index)


def _diagnostic_cell(cells: list[dict]) -> dict | None:
    """Choose a cluster-audit cell with enough observations to test a rule."""
    if not cells:
        return None
    cluster_eligible = [
        cell for cell in cells
        if cell["cost_views"]["selection_2t"]["trade_count"] >= 40
    ]
    return max(cluster_eligible or cells, key=_selection_rank)


def evaluate_year(sessions: list[SessionContext], events: list[dict], year: int,
                  parameters: dict | None = None) -> tuple[list[dict], dict | None, list[dict]]:
    cells: list[dict] = []
    trades_by_cell: dict[tuple[float, float, int], list[dict]] = {}
    cell_iterable = CELL_ORDER if parameters is None else ((
        float(parameters["depth_atr_threshold"]),
        float(parameters["target_r"]), int(parameters["hold_minutes"]),
    ),)
    for depth, target_r, hold in cell_iterable:
        trades, replay = replay_cell(sessions, events, year, depth, target_r, hold)
        summary = summarize_cell(trades, year, replay)
        summary["parameters"] = {
            "depth_atr_threshold": depth, "target_r": target_r, "hold_minutes": hold,
        }
        summary["passed"] = annual_passes(summary)
        cells.append(summary)
        trades_by_cell[(depth, target_r, hold)] = trades
    if parameters is not None:
        return cells, cells[0], trades_by_cell[next(iter(trades_by_cell))]
    qualified = [cell for cell in cells if cell["passed"]]
    selected = max(qualified, key=_selection_rank) if qualified else None
    diagnostic = _diagnostic_cell(cells)
    chosen = selected or diagnostic
    ledger = trades_by_cell[(
        float(chosen["parameters"]["depth_atr_threshold"]),
        float(chosen["parameters"]["target_r"]), int(chosen["parameters"]["hold_minutes"]),
    )] if chosen is not None else []
    return cells, selected, ledger


def _condition_bootstrap(trades: list[dict], key: str, seed: int,
                         resamples: int) -> dict:
    by_day: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        by_day[trade["date"]].append(float(trade[key]))
    days = sorted(by_day)
    if not days:
        return {"active_days": 0, "lower_95": None, "upper_95": None}
    totals = np.asarray([sum(by_day[day]) for day in days], dtype=float)
    counts = np.asarray([len(by_day[day]) for day in days], dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=float)
    chunk = 1_000
    for start in range(0, resamples, chunk):
        stop = min(start + chunk, resamples)
        indices = rng.integers(0, len(days), size=(stop - start, len(days)))
        denominator = counts[indices].sum(axis=1)
        means[start:stop] = totals[indices].sum(axis=1) / denominator
    return {
        "active_days": len(days),
        "lower_95": round(float(np.quantile(means, 0.025, method="linear")), 6),
        "upper_95": round(float(np.quantile(means, 0.975, method="linear")), 6),
    }


def _streaks(trades: list[dict], key: str) -> dict:
    ordered = sorted(trades, key=lambda row: (row["entry_time"], row["side"]))
    runs: list[dict] = []
    current: list[dict] = []
    current_kind: str | None = None
    for row in ordered:
        value = float(row[key])
        kind = "win" if value > 0 else "loss" if value < 0 else "flat"
        if kind != current_kind and current:
            runs.append({
                "kind": current_kind, "start": current[0]["date"], "end": current[-1]["date"],
                "trades": len(current), "pnl": round(sum(float(item[key]) for item in current), 6),
            })
            current = []
        current_kind = kind
        current.append(row)
    if current:
        runs.append({
            "kind": current_kind, "start": current[0]["date"], "end": current[-1]["date"],
            "trades": len(current), "pnl": round(sum(float(item[key]) for item in current), 6),
        })
    wins = [run for run in runs if run["kind"] == "win"]
    losses = [run for run in runs if run["kind"] == "loss"]
    return {
        "largest_win_streak": max(wins, key=lambda row: (row["trades"], row["pnl"]), default=None),
        "largest_loss_streak": max(losses, key=lambda row: (row["trades"], -row["pnl"]), default=None),
        "worst_loss_runs": sorted(losses, key=lambda row: row["pnl"])[:10],
        "best_win_runs": sorted(wins, key=lambda row: row["pnl"], reverse=True)[:10],
    }


def _five_session_windows(trades: list[dict], key: str) -> dict:
    by_day: dict[str, float] = defaultdict(float)
    for trade in trades:
        by_day[trade["date"]] += float(trade[key])
    days = sorted(by_day)
    windows = [{
        "start": days[index], "end": days[index + 4],
        "pnl": round(sum(by_day[day] for day in days[index:index + 5]), 6),
    } for index in range(max(0, len(days) - 4))]
    return {
        "worst": sorted(windows, key=lambda row: row["pnl"])[:10],
        "best": sorted(windows, key=lambda row: row["pnl"], reverse=True)[:10],
    }


def cluster_audit(trades: list[dict], resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    rows: list[dict] = []
    for field in CLUSTER_FIELDS:
        values = sorted({str(trade.get(field, "unknown")) for trade in trades})
        for value in values:
            cohort = [trade for trade in trades if str(trade.get(field, "unknown")) == value]
            selection = _pnl_metrics(cohort, "selection_2t")
            stress = _pnl_metrics(cohort, "stress_4t")
            seed_material = f"{BOOTSTRAP_SEED}:{field}:{value}".encode()
            seed = int(hashlib.sha256(seed_material).hexdigest()[:8], 16)
            bootstrap = _condition_bootstrap(cohort, "selection_2t", seed, resamples)
            first = [row for row in cohort if row["date"][5:7] <= "06"]
            second = [row for row in cohort if row["date"][5:7] >= "07"]
            months = {row["date"][:7] for row in cohort}
            avoid_eligible = (
                selection["trade_count"] >= 40
                and _profit_factor_value(selection) < 0.80
                and selection["net_dollars"] < 0
                and bootstrap["upper_95"] is not None and bootstrap["upper_95"] < 0
            )
            size_eligible = (
                selection["trade_count"] >= 40
                and _profit_factor_value(selection) >= 1.40
                and selection["average_trade"] is not None and selection["average_trade"] >= 12
                and stress["net_dollars"] > 0
                and bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0
                and len(months) >= 6
                and sum(float(row["selection_2t"]) for row in first) > 0
                and sum(float(row["selection_2t"]) for row in second) > 0
            )
            rows.append({
                "field": field, "value": value, "selection_2t": selection,
                "stress_4t": stress, "bootstrap": bootstrap,
                "active_months": len(months), "avoid_eligible": avoid_eligible,
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
        "selected_avoid": ({"field": selected_avoid["field"], "value": selected_avoid["value"]}
                           if selected_avoid else None),
        "selected_size": ({"field": selected_size["field"], "value": selected_size["value"]}
                          if selected_size else None),
        "streaks": _streaks(trades, "selection_2t"),
        "five_active_session_windows": _five_session_windows(trades, "selection_2t"),
        "winner_mae_mfe": {
            "mae_mean": round(float(np.mean([row["mae_points"] for row in trades if row["selection_2t"] > 0])), 6)
            if any(row["selection_2t"] > 0 for row in trades) else None,
            "mfe_mean": round(float(np.mean([row["mfe_points"] for row in trades if row["selection_2t"] > 0])), 6)
            if any(row["selection_2t"] > 0 for row in trades) else None,
        },
        "loser_mae_mfe": {
            "mae_mean": round(float(np.mean([row["mae_points"] for row in trades if row["selection_2t"] < 0])), 6)
            if any(row["selection_2t"] < 0 for row in trades) else None,
            "mfe_mean": round(float(np.mean([row["mfe_points"] for row in trades if row["selection_2t"] < 0])), 6)
            if any(row["selection_2t"] < 0 for row in trades) else None,
        },
    }


def _rule_cohort(trades: list[dict], rule: dict | None) -> list[dict]:
    if rule is None:
        return []
    return [row for row in trades if str(row.get(rule["field"], "unknown")) == rule["value"]]


def validate_cluster_rules(trades: list[dict], avoid: dict | None, size: dict | None,
                           resamples: int) -> dict:
    avoid_cohort = _rule_cohort(trades, avoid)
    size_cohort = _rule_cohort(trades, size)
    avoid_metrics = _pnl_metrics(avoid_cohort, "selection_2t")
    size_selection = _pnl_metrics(size_cohort, "selection_2t")
    size_stress = _pnl_metrics(size_cohort, "stress_4t")
    avoid_boot = _condition_bootstrap(avoid_cohort, "selection_2t", BOOTSTRAP_SEED + 101, resamples)
    size_boot = _condition_bootstrap(size_cohort, "selection_2t", BOOTSTRAP_SEED + 202, resamples)
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
        "avoid_confirmed": bool(avoid and avoid_metrics["trade_count"] >= 40
                                and _profit_factor_value(avoid_metrics) < 0.80
                                and avoid_metrics["net_dollars"] < 0
                                and avoid_boot["upper_95"] is not None
                                and avoid_boot["upper_95"] < 0),
        "filtered_strategy": _pnl_metrics(filtered, "selection_2t"),
        "size_rule": size,
        "size_cohort_selection": size_selection,
        "size_cohort_stress": size_stress,
        "size_bootstrap": size_boot,
        "size_confirmed": bool(size and size_selection["trade_count"] >= 40
                               and _profit_factor_value(size_selection) >= 1.40
                               and size_selection["average_trade"] is not None
                               and size_selection["average_trade"] >= 12
                               and size_stress["net_dollars"] > 0
                               and size_boot["lower_95"] is not None
                               and size_boot["lower_95"] > 0),
        "tiered_two_contract_diagnostic": _pnl_metrics(tiered, "tiered_selection_2t"),
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
            "mechanism": "failed sweep of completed Globex overnight high or low",
            "depths_atr": list(DEPTHS), "target_r": list(TARGET_RS),
            "holds_minutes": list(HOLDS), "cells": len(CELL_ORDER),
            "daily_limit": DAILY_LIMIT, "cooldown_minutes": COOLDOWN_MINUTES,
        },
        "execution": {
            "fill_convention": "completed five-minute signal; next one-minute open; stop-first ambiguity; one-tick target trade-through",
            "evidence": "one-minute trade-print OHLC proxy; executable bid/ask and latency not verified",
            "round_trip_fee": ROUND_TRIP_FEE,
            "adverse_ticks_each_side": [0, 1, 2, 4],
        },
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
        "years_loaded": [], "verdict": None,
    }


def run_study(loader: Callable[[str, int], pd.DataFrame],
              bootstrap_resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[dict, list[dict]]:
    """Run the frozen sequential firewall; never load a later year after failure."""
    frames: dict[int, pd.DataFrame] = {}
    result = _result_base()

    def load(year: int) -> None:
        if year not in ALLOWED_YEARS:
            raise ValueError("v39 may read only 2023-2025")
        frames[year] = loader("MES", year)
        result["years_loaded"].append(year)

    def prepared() -> tuple[list[SessionContext], list[dict], dict, dict]:
        sessions, session_exclusions = build_sessions([frames[year] for year in sorted(frames)])
        events, event_exclusions = build_events(sessions)
        return sessions, events, session_exclusions, event_exclusions

    load(2023)
    sessions, events, session_exclusions, event_exclusions = prepared()
    cells, selected, diagnostic_ledger = evaluate_year(sessions, events, 2023)
    diagnostic_cell = _diagnostic_cell(cells)
    audit = cluster_audit(diagnostic_ledger, bootstrap_resamples)
    result["discovery_2023"] = {
        "cells": cells, "selected": selected, "diagnostic_cell": diagnostic_cell,
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
    _, validation_2024, trades_2024 = evaluate_year(sessions, events, 2024, parameters)
    assert validation_2024 is not None
    clusters_2024 = validate_cluster_rules(trades_2024, avoid_rule, size_rule, bootstrap_resamples)
    passed_2024 = annual_passes(validation_2024)
    result["validation_2024"] = {
        "passed": passed_2024, "metrics": validation_2024,
        "cluster_rules": clusters_2024,
        "session_exclusions": session_exclusions.get(2024, {}),
        "event_counts": event_exclusions.get(2024, {}),
    }
    ledger.extend(trades_2024)
    if not passed_2024:
        result["verdict"] = "FAILED_2024_VALIDATION"
        result["firewall"] = "2025 unopened because the unchanged selected cell failed 2024"
        return result, ledger

    load(2025)
    sessions, events, session_exclusions, event_exclusions = prepared()
    _, validation_2025, trades_2025 = evaluate_year(sessions, events, 2025, parameters)
    assert validation_2025 is not None
    clusters_2025 = validate_cluster_rules(trades_2025, avoid_rule, size_rule, bootstrap_resamples)
    passed_2025 = annual_passes(validation_2025)
    result["validation_2025"] = {
        "passed": passed_2025, "metrics": validation_2025,
        "cluster_rules": clusters_2025,
        "session_exclusions": session_exclusions.get(2025, {}),
        "event_counts": event_exclusions.get(2025, {}),
    }
    ledger.extend(trades_2025)
    if not passed_2025:
        result["verdict"] = "FAILED_2025_VALIDATION"
        result["firewall"] = "historical family rejected by unchanged 2025 confirmation"
        return result, ledger

    annual_counts = [
        selected["cost_views"]["selection_2t"]["trade_count"],
        validation_2024["cost_views"]["selection_2t"]["trade_count"],
        validation_2025["cost_views"]["selection_2t"]["trade_count"],
    ]
    average_frequency = float(np.mean(annual_counts))
    validation_dates = [session.date for session in sessions if session.date[:4] in {"2024", "2025"}]
    bootstrap = v33.day_cluster_bootstrap(
        trades_2024 + trades_2025, validation_dates,
        resamples=bootstrap_resamples, seed=BOOTSTRAP_SEED,
    )
    result["final_audit"] = {
        "annual_trade_counts": annual_counts,
        "average_trades_per_year": round(average_frequency, 6),
        "frequency_passed": average_frequency >= 180,
        "validation_day_bootstrap": bootstrap,
        "avoid_rule_historically_confirmed": bool(
            avoid_rule and clusters_2024["avoid_confirmed"] and clusters_2025["avoid_confirmed"]
        ),
        "size_rule_historically_confirmed": bool(
            size_rule and clusters_2024["size_confirmed"] and clusters_2025["size_confirmed"]
        ),
        "size_authorized": False,
    }
    if average_frequency >= 180 and bootstrap["lower_95"] is not None and bootstrap["lower_95"] > 0:
        result["verdict"] = "HISTORICAL_CANDIDATE"
        result["firewall"] = "requires untouched 2026, executable fill calibration, and forward shadow evidence"
    elif average_frequency < 180:
        result["verdict"] = "FAILED_FREQUENCY_GATE"
        result["firewall"] = "historical family rejected because activity missed the frozen target"
    else:
        result["verdict"] = "FAILED_BOOTSTRAP"
        result["firewall"] = "historical family rejected by combined 2024-2025 session bootstrap"
    return result, ledger


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


def persist_result(database_url: str, result: dict, ledger: list[dict]) -> None:
    """Persist only immutable v39 research evidence; never touch trading tables."""
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
                    CREATE TABLE IF NOT EXISTS valor_mes_v39_results (
                        study_id text PRIMARY KEY,
                        source_sha256 text NOT NULL,
                        result jsonb NOT NULL,
                        ledger_gzip bytea NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
                cursor.execute(
                    "SELECT source_sha256, result FROM valor_mes_v39_results WHERE study_id=%s",
                    (STUDY_ID,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if str(existing[0]) != source_sha:
                        raise RuntimeError("completed v39 exists with a different source hash")
                    if existing[1] != result:
                        raise RuntimeError("completed v39 source matches but result differs")
                    return
                cursor.execute("""
                    INSERT INTO valor_mes_v39_results
                        (study_id, source_sha256, result, ledger_gzip)
                    VALUES (%s, %s, %s, %s)
                """, (STUDY_ID, source_sha, Json(result), psycopg2.Binary(ledger_body)))
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path,
                        default=Path("docs/valor_mes_v39/result.json"))
    parser.add_argument("--ledger-out", type=Path,
                        default=Path("docs/valor_mes_v39/ledger.csv"))
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
        "study_id": STUDY_ID, "verdict": result["verdict"],
        "years_loaded": result["years_loaded"],
        "selected": selected["parameters"] if selected else None,
        "calendar_year_2026_sealed": result["calendar_year_2026_sealed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
