"""Replay engine — drives a list of snapshots through the setup-stack
dispatcher and simulates each fire to PT/SL/TIME_STOP via quant.sim.

Per-day reset: DailyState and FlipBuffer reset every trading day.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, List, Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch
from quant.sim import simulate_intraday, MarkSeries


@dataclass(frozen=True)
class TradeOutcome:
    trade_date: dt.date
    setup: str
    direction: str
    entry_minute: int
    exit_minute: int
    debit: float
    exit_reason: str
    realized_pct: float


SpotMarkProvider = Callable[..., float]


def replay_day(
    snapshots: List[GexSnapshot],
    *,
    config: JoshuaConfig,
    spot_mark_provider: SpotMarkProvider,
    debit_estimator: Optional[Callable[[GexSnapshot, SetupAction], float]] = None,
) -> List[TradeOutcome]:
    if not snapshots:
        return []

    trade_date = (snapshots[0].snapshot_at - dt.timedelta(hours=5)).date()
    state = DailyState(trade_date=trade_date)
    buffer = FlipBuffer(max_minutes=config.flip_buffer_minutes)
    outcomes: List[TradeOutcome] = []
    eod_h, eod_m = (int(x) for x in config.eod_time_ct.split(":"))
    eod_minute = (eod_h - 8) * 60 + (eod_m - 30)

    for snap in snapshots:
        buffer.add(snap)
        entry_minute = _minutes_since_open_ct(snap.snapshot_at)
        if entry_minute < 0:
            continue
        if entry_minute >= eod_minute:
            break
        action = dispatch(snap, state=state, buffer=buffer, config=config)
        if action is None:
            continue

        debit = debit_estimator(snap, action) if debit_estimator else 0.50
        if debit <= 0:
            continue

        marks = {}
        for future_snap in snapshots:
            m = _minutes_since_open_ct(future_snap.snapshot_at)
            if m < entry_minute:
                continue
            if m > eod_minute:
                break
            marks[m] = spot_mark_provider(
                snapshot=future_snap, action=action, minute=m, entry_minute=entry_minute, debit=debit,
            )
        if entry_minute not in marks:
            marks[entry_minute] = debit

        ms = MarkSeries(marks)
        sim = simulate_intraday(
            debit=debit,
            entry_minute=entry_minute,
            eod_minute=eod_minute,
            bars=ms,
            pt_pct=config.profit_target_pct,
            sl_pct=config.stop_loss_pct,
        )
        outcomes.append(TradeOutcome(
            trade_date=trade_date,
            setup=action.setup.value,
            direction=action.direction,
            entry_minute=entry_minute,
            exit_minute=sim.exit_minute,
            debit=debit,
            exit_reason=sim.exit_reason,
            realized_pct=sim.realized_pct,
        ))
        state = _mark_fired(state, action.setup)

    return outcomes


def _minutes_since_open_ct(ts: dt.datetime) -> int:
    ct = ts - dt.timedelta(hours=5)
    open_t = ct.replace(hour=8, minute=30, second=0, microsecond=0)
    return int((ct - open_t).total_seconds() // 60)


def _mark_fired(state: DailyState, setup: SetupType) -> DailyState:
    return DailyState(
        trade_date=state.trade_date,
        wall_fade_fired=state.wall_fade_fired or setup == SetupType.WALL_FADE,
        wall_break_fired=state.wall_break_fired or setup == SetupType.WALL_BREAK,
        flip_cross_fired=state.flip_cross_fired or setup == SetupType.FLIP_CROSS,
        last_signal_minute=state.last_signal_minute,
    )
