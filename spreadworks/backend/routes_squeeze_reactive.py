"""Reactive-momentum squeeze signal API: /api/spreadworks/squeeze-reactive

Read-only surface for `squeeze_reactive_alerts.py`'s repeating intraday scan
(ported REACTIVE_WIDE_FADE_PNL_BACKTEST_MODE) — current OPEN positions plus
recent CLOSED signals, with the same never-silently-blank freshness/
blocked-state contract as `routes_squeeze_premarket.py`. A sibling route,
not an extension of the premarket one: the state model is fundamentally
different (open/closed positions tracked across many ticks a day, not one
daily signal list), so it gets its own prefix and tables rather than
overloading `/squeeze-premarket`. ADVISORY ONLY — this does not touch a bot.

The scheduled scan (every 5 min, 09:30-16:00 ET weekdays) lives in
backend/squeeze_reactive_alerts.py, registered on the same scheduler as the
premarket and gamma-regime squeeze signals' jobs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import engine as _global_engine
from .squeeze_reactive_alerts import (
    PREFILTER_MOVE_FLOOR,
    REACTIVE_JOB_ID,
    REACTIVE_MOVE_FLOOR,
    REACTIVE_WIDE_FADE_ACCEL_LOW,
    SCAN_LOG_TABLE,
    SIGNALS_TABLE,
)
from .squeeze_premarket_alerts import DEDUPE_DAYS, MONEY_PACE_ACCEL_HIGH, UNIVERSE_TABLE

logger = logging.getLogger("spreadworks.routes_squeeze_reactive")
router = APIRouter(prefix="/api/spreadworks/squeeze-reactive",
                    tags=["Squeeze Reactive Signal"])

ENGINE: Engine = _global_engine
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

CLOSED_HISTORY_DAYS = 30
STALE_MINUTES_DURING_SESSION = 15  # > 2 scheduled ticks missed


def _isoformat(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _universe_size(engine: Engine) -> tuple[int, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT count(*) FROM {UNIVERSE_TABLE} "
                "WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0"
            )).fetchone()
        return int(row[0]) if row else 0, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_reactive] universe size query failed: %r", e)
        return 0, f"universe query error: {e}"


def _last_scan_log(engine: Engine) -> tuple[dict | None, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(f"""
                SELECT run_at, universe_size, prefilter_candidates, prefilter_shortlist,
                       snapshot_batches, snapshot_errors, open_checked, errors,
                       entries_opened, exits_closed, open_after, completed_at
                FROM {SCAN_LOG_TABLE} ORDER BY run_at DESC LIMIT 1
            """)).fetchone()
        if row is None:
            return None, None
        return {
            "run_at": row[0].isoformat() if row[0] else None,
            "universe_size": row[1], "prefilter_candidates": row[2],
            "prefilter_shortlist": row[3], "snapshot_batches": row[4],
            "snapshot_errors": row[5], "open_checked": row[6], "errors": row[7],
            "entries_opened": row[8], "exits_closed": row[9], "open_after": row[10],
            "completed_at": row[11].isoformat() if row[11] else None,
        }, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_reactive] scan log query failed: %r", e)
        return None, f"scan log query error: {e}"


def _open_positions(engine: Engine) -> tuple[list[dict], str | None]:
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT symbol, signal_date, entry_bar_time, entry_time, entry_ask,
                       entry_move, prior_close, opened_at
                FROM {SIGNALS_TABLE} WHERE status = 'open'
                ORDER BY entry_time DESC
            """)).fetchall()
        return [{
            "symbol": r[0], "signal_date": _isoformat(r[1]),
            "entry_bar_time": r[2].isoformat() if r[2] else None,
            "entry_time": r[3].isoformat() if r[3] else None,
            "entry_ask": float(r[4]) if r[4] is not None else None,
            "entry_move": float(r[5]) if r[5] is not None else None,
            "prior_close": float(r[6]) if r[6] is not None else None,
            "opened_at": r[7].isoformat() if r[7] else None,
        } for r in rows], None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_reactive] open positions query failed: %r", e)
        return [], f"open positions query error: {e}"


def _recent_closed(engine: Engine, since: date) -> tuple[list[dict], str | None]:
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT symbol, signal_date, entry_time, entry_ask, entry_move,
                       prior_close, exit_time, exit_bid, exit_reason, raw_return,
                       closed_at
                FROM {SIGNALS_TABLE}
                WHERE status = 'closed' AND signal_date >= :since
                ORDER BY closed_at DESC
            """), {"since": since}).fetchall()
        return [{
            "symbol": r[0], "signal_date": _isoformat(r[1]),
            "entry_time": r[2].isoformat() if r[2] else None,
            "entry_ask": float(r[3]) if r[3] is not None else None,
            "entry_move": float(r[4]) if r[4] is not None else None,
            "prior_close": float(r[5]) if r[5] is not None else None,
            "exit_time": r[6].isoformat() if r[6] else None,
            "exit_bid": float(r[7]) if r[7] is not None else None,
            "exit_reason": r[8], "raw_return": float(r[9]) if r[9] is not None else None,
            "closed_at": r[10].isoformat() if r[10] else None,
        } for r in rows], None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_reactive] closed signals query failed: %r", e)
        return [], f"closed signals query error: {e}"


def _is_regular_session(now_et: datetime) -> bool:
    return now_et.weekday() < 5 and dtime(9, 30) <= now_et.time() <= dtime(16, 0)


@router.get("/state")
async def state(closed_days: int = CLOSED_HISTORY_DAYS):
    """Current reactive-momentum state: is the job armed, is it keeping up
    with the 5-minute cadence during the regular session, which positions
    are open right now, and what closed in the last `closed_days` days.
    Never raises — degrades to a BLOCKED-shaped payload with a `reason`
    rather than a 500 or a silently empty page."""
    now_et = datetime.now(ET)
    in_session = _is_regular_session(now_et)

    universe_size, universe_err = _universe_size(ENGINE)
    scan_log, scan_log_err = _last_scan_log(ENGINE)
    open_positions, open_err = _open_positions(ENGINE)

    try:
        from .squeeze_reactive_alerts import scheduled_jobs
        jobs = scheduled_jobs()
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_reactive] scheduled_jobs failed: %r", e)
        jobs = {"registered": None, "jobs": {}, "reason": f"scheduled_jobs error: {e}"}

    n_days = max(1, min(90, closed_days))
    since = now_et.date() - timedelta(days=n_days)
    closed_signals, closed_err = _recent_closed(ENGINE, since)

    # BLOCKED-STATE PRECEDENCE — same shape as routes_squeeze_premarket's
    # health gate: say why nothing is tradeable instead of rendering a
    # verdict off a blind spot. Only evaluated for staleness WHILE the
    # regular session is open — a job that hasn't ticked since last night's
    # close is expected, not blocked.
    block: str | None = None
    if jobs.get("registered") is False:
        block = "The reactive scan job is not scheduled. Nothing is updating this signal."
    elif universe_size == 0:
        block = (f"{UNIVERSE_TABLE} has no symbols with a usable share count — "
                 "the separate local universe-sync job has not populated it yet.")
    elif in_session:
        if scan_log is None:
            block = "The scan has never completed a run (no scan-log row yet)."
        else:
            last_run = datetime.fromisoformat(scan_log["run_at"]).replace(tzinfo=ET)
            stale_minutes = (now_et - last_run).total_seconds() / 60.0
            if stale_minutes > STALE_MINUTES_DURING_SESSION:
                block = (f"The newest completed scan was {stale_minutes:.0f} "
                         f"minute(s) ago ({scan_log['run_at']}) — more than "
                         f"{STALE_MINUTES_DURING_SESSION} minutes behind the "
                         "5-minute cadence during the regular session.")

    capture_state = "unknown"
    if universe_err or scan_log_err or open_err:
        capture_state = "unknown"
    elif block is None:
        capture_state = "ok" if in_session else "ok_outside_session"
    elif scan_log is None:
        capture_state = "never_run"
    else:
        capture_state = "stale"

    return {
        "asof": now_et.isoformat(),
        "in_regular_session": in_session,
        "blocked": block is not None,
        "block_reason": block,
        "jobs": jobs,
        "capture_health": {
            "state": capture_state,
            "last_scan_at": scan_log["run_at"] if scan_log else None,
        },
        "universe_size": universe_size,
        "last_scan": scan_log,
        "rule": {
            "move_floor": REACTIVE_MOVE_FLOOR,
            "money_pace_accel_high": MONEY_PACE_ACCEL_HIGH,
            "wide_fade_accel_low": REACTIVE_WIDE_FADE_ACCEL_LOW,
            "prefilter_move_floor": PREFILTER_MOVE_FLOOR,
            "dedupe_days": DEDUPE_DAYS,
            "name": ("REACTIVE_WIDE_FADE_PNL_BACKTEST_MODE (live port) — no "
                     "premarket gate, regular session only, real NBBO both legs"),
        },
        "open_positions": open_positions,
        "open_count": len(open_positions),
        "closed_history_days": n_days,
        "closed_signals": closed_signals,
        "errors": {k: v for k, v in {
            "universe": universe_err, "scan_log": scan_log_err,
            "open_positions": open_err, "closed_signals": closed_err,
        }.items() if v},
        "advisory_only": True,
    }
