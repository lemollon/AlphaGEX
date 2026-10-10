"""CINDER signal API: /api/spreadworks/cinder

Read-only surface for `cinder_signal.py`'s repeating intraday scan — current
OPEN position (or null) plus recent CLOSED signals, with the same
never-silently-blank freshness/blocked-state contract as
`routes_squeeze_reactive.py`. ADVISORY ONLY — this does not touch a bot. A
separate LOCAL execution bot (built elsewhere) reads this endpoint and
places the real orders; nothing here does.

The scheduled scan (every 5 min, 09:30-16:00 ET weekdays, entry attempted
only in the 11:25-11:35 ET window) lives in backend/cinder_signal.py,
registered on the same scheduler as the squeeze signals' jobs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .cinder_signal import (
    CINDER_JOB_ID,
    CINDER_SCAN_LOG_TABLE,
    CINDER_SIGNALS_TABLE,
    COOLDOWN_DAYS,
    ENTRY_WINDOW_END_T,
    ENTRY_WINDOW_START_T,
    GEX_TRIGGER_B,
    STRIKE_WIDTH,
    TARGET_MULTIPLE,
    VIX_RATIO_TRIGGER,
)
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_cinder")
router = APIRouter(prefix="/api/spreadworks/cinder", tags=["CINDER Signal"])

# Tests override this via monkeypatch (same convention as routes_squeeze /
# routes_squeeze_reactive).
ENGINE: Engine = _global_engine
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

CLOSED_HISTORY_DAYS = 90
STALE_MINUTES_DURING_SESSION = 15  # > 2 scheduled ticks missed


def _isoformat(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _last_scan_log(engine: Engine) -> tuple[dict | None, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(f"""
                SELECT run_at, gex_b, gex_pass, vix_ratio, vix_ratio_pass,
                       term_vix, term_vix3m, term_pass, triggered, cooldown_ok,
                       block_reason, entry_opened, exit_closed, errors,
                       completed_at
                FROM {CINDER_SCAN_LOG_TABLE} ORDER BY run_at DESC LIMIT 1
            """)).fetchone()
        if row is None:
            return None, None
        return {
            "run_at": row[0].isoformat() if row[0] else None,
            "gex_b": row[1], "gex_pass": row[2], "vix_ratio": row[3],
            "vix_ratio_pass": row[4], "term_vix": row[5], "term_vix3m": row[6],
            "term_pass": row[7], "triggered": row[8], "cooldown_ok": row[9],
            "block_reason": row[10], "entry_opened": row[11],
            "exit_closed": row[12], "errors": row[13],
            "completed_at": row[14].isoformat() if row[14] else None,
        }, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_cinder] scan log query failed: %r", e)
        return None, f"scan log query error: {e}"


def _open_position(engine: Engine) -> tuple[dict | None, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(f"""
                SELECT signal_date, entry_time, entry_spot, long_strike,
                       short_strike, expiration, entry_debit,
                       current_spread_value, target_hit, last_checked_at,
                       opened_at
                FROM {CINDER_SIGNALS_TABLE} WHERE status = 'open'
                ORDER BY signal_date DESC LIMIT 1
            """)).fetchone()
        if row is None:
            return None, None
        return {
            "signal_date": _isoformat(row[0]),
            "entry_time": row[1].isoformat() if row[1] else None,
            "entry_spot": float(row[2]) if row[2] is not None else None,
            "long_strike": float(row[3]) if row[3] is not None else None,
            "short_strike": float(row[4]) if row[4] is not None else None,
            "expiration": _isoformat(row[5]) if row[5] else None,
            "entry_debit": float(row[6]) if row[6] is not None else None,
            "current_spread_value": float(row[7]) if row[7] is not None else None,
            "target_hit": bool(row[8]) if row[8] is not None else None,
            "last_checked_at": row[9].isoformat() if row[9] else None,
            "opened_at": row[10].isoformat() if row[10] else None,
        }, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_cinder] open position query failed: %r", e)
        return None, f"open position query error: {e}"


def _recent_closed(engine: Engine, since: date) -> tuple[list[dict], str | None]:
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT signal_date, entry_time, entry_spot, long_strike,
                       short_strike, expiration, entry_debit, exit_time,
                       exit_value, exit_reason, raw_return, closed_at
                FROM {CINDER_SIGNALS_TABLE}
                WHERE status = 'closed' AND signal_date >= :since
                ORDER BY closed_at DESC
            """), {"since": since}).fetchall()
        return [{
            "signal_date": _isoformat(r[0]),
            "entry_time": r[1].isoformat() if r[1] else None,
            "entry_spot": float(r[2]) if r[2] is not None else None,
            "long_strike": float(r[3]) if r[3] is not None else None,
            "short_strike": float(r[4]) if r[4] is not None else None,
            "expiration": _isoformat(r[5]) if r[5] else None,
            "entry_debit": float(r[6]) if r[6] is not None else None,
            "exit_time": r[7].isoformat() if r[7] else None,
            "exit_value": float(r[8]) if r[8] is not None else None,
            "exit_reason": r[9],
            "raw_return": float(r[10]) if r[10] is not None else None,
            "closed_at": r[11].isoformat() if r[11] else None,
        } for r in rows], None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_cinder] closed signals query failed: %r", e)
        return [], f"closed signals query error: {e}"


def _is_regular_session(now_et: datetime) -> bool:
    return now_et.weekday() < 5 and dtime(9, 30) <= now_et.time() <= dtime(16, 0)


@router.get("/state")
async def state(closed_days: int = CLOSED_HISTORY_DAYS):
    """Current CINDER state: is the job armed, is it keeping up with the
    5-minute cadence during the regular session, the open position (or
    null) with its live current spread value + target-hit flag, and what
    closed in the last `closed_days` days. Never raises — degrades to a
    BLOCKED-shaped payload with a `reason` rather than a 500 or a silently
    empty page."""
    now_et = datetime.now(ET)
    in_session = _is_regular_session(now_et)

    scan_log, scan_log_err = _last_scan_log(ENGINE)
    open_position, open_err = _open_position(ENGINE)

    try:
        from .cinder_signal import scheduled_jobs
        jobs = scheduled_jobs()
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_cinder] scheduled_jobs failed: %r", e)
        jobs = {"registered": None, "jobs": {}, "reason": f"scheduled_jobs error: {e}"}

    n_days = max(1, min(365, closed_days))
    since = now_et.date() - timedelta(days=n_days)
    closed_signals, closed_err = _recent_closed(ENGINE, since)

    # BLOCKED-STATE PRECEDENCE — same shape as routes_squeeze_reactive's
    # health gate: say why nothing is tradeable instead of rendering a
    # verdict off a blind spot. Only evaluated for staleness WHILE the
    # regular session is open — a job that hasn't ticked since last night's
    # close is expected, not blocked.
    block: str | None = None
    if jobs.get("registered") is False:
        block = "The CINDER scan job is not scheduled. Nothing is updating this signal."
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
    if scan_log_err or open_err:
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
        "last_scan": scan_log,
        "rule": {
            "gex_trigger_b": GEX_TRIGGER_B,
            "vix_ratio_trigger": VIX_RATIO_TRIGGER,
            "cooldown_days": COOLDOWN_DAYS,
            "strike_width": STRIKE_WIDTH,
            "target_multiple": TARGET_MULTIPLE,
            "entry_window_et": [ENTRY_WINDOW_START_T.isoformat(),
                               ENTRY_WINDOW_END_T.isoformat()],
            "name": ("SPY 1DTE debit call spread -- prior-session net_gex_b "
                     "<= -10B, live VIX ratio < 0.90, VIX-VIX3M term "
                     "structure in contango, 5-calendar-day cooldown from "
                     "the last entry. Backtest: 10 trades 2024-2026, 90% WR, "
                     "+12.32 units, real NBBO fills both legs separately."),
        },
        "open_position": open_position,
        "closed_history_days": n_days,
        "closed_signals": closed_signals,
        "errors": {k: v for k, v in {
            "scan_log": scan_log_err, "open_position": open_err,
            "closed_signals": closed_err,
        }.items() if v},
        "advisory_only": True,
    }
