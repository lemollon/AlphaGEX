"""Premarket squeeze signal API: /api/spreadworks/squeeze-premarket

Read-only surface for `squeeze_premarket_alerts.py`'s scan (PREREG.md #3 /
V3) — today's new signals plus enough recent history for a page or a quick
check to show "is this armed and did it run". Same freshness/blocked-state
contract as `routes_squeeze.py`: never silently blank, always say why if
there is nothing to show. ADVISORY ONLY — this does not touch a bot.

The scheduled scan (08:15 CT / 09:15 ET weekdays) lives in
backend/squeeze_premarket_alerts.py, registered on the same scheduler as the
gamma-regime squeeze signal's jobs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import engine as _global_engine
from .squeeze_premarket_alerts import (DEDUPE_DAYS, MOVE_FLOOR,
                                        OVEREXTENDED_MOVE_CAP,
                                        OVEREXTENDED_TURNOVER_CAP,
                                        PREMARKET_JOB_ID, SCAN_LOG_TABLE,
                                        SIGNALS_TABLE, TURNOVER_FLOOR,
                                        UNIVERSE_TABLE)

logger = logging.getLogger("spreadworks.routes_squeeze_premarket")
router = APIRouter(prefix="/api/spreadworks/squeeze-premarket",
                    tags=["Squeeze Premarket Signal"])

ENGINE: Engine = _global_engine
ET = ZoneInfo("America/New_York")   # the frozen rule's own session clock
CT = ZoneInfo("America/Chicago")

SIGNAL_HISTORY_DAYS = 30


def _isoformat(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _expected_run_date(today_et: date) -> date:
    """Last weekday on/before today ET — the session the scan should have
    most recently run for. Same shape as gamma_regime.data_freshness()'s
    `expected` date, just without a holiday calendar (neither the cron nor
    this port had one)."""
    d = today_et
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _universe_size(engine: Engine) -> tuple[int, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT count(*) FROM {UNIVERSE_TABLE} "
                "WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0"
            )).fetchone()
        return int(row[0]) if row else 0, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_premarket] universe size query failed: %r", e)
        return 0, f"universe query error: {e}"


def _last_scan_log(engine: Engine) -> tuple[dict | None, str | None]:
    try:
        with engine.begin() as conn:
            row = conn.execute(text(f"""
                SELECT run_date, universe_size, checked, errors, no_data,
                       below_floor, overextended_excluded, candidates,
                       new_signals, completed_at
                FROM {SCAN_LOG_TABLE} ORDER BY run_date DESC LIMIT 1
            """)).fetchone()
        if row is None:
            return None, None
        return {
            "run_date": _isoformat(row[0]), "universe_size": row[1],
            "checked": row[2], "errors": row[3], "no_data": row[4],
            "below_floor": row[5], "overextended_excluded": row[6],
            "candidates": row[7], "new_signals": row[8],
            "completed_at": row[9].isoformat() if row[9] else None,
        }, None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_premarket] scan log query failed: %r", e)
        return None, f"scan log query error: {e}"


def _last_claimed_date(engine: Engine) -> tuple[date | None, str | None]:
    """When the job last CLAIMED its dedup slot — compared against the scan
    log's own run_date the same way gamma_regime.capture_health() compares
    `_dedup_ok`'s claim against sw_gamma_daily's newest stored row, so a job
    that claimed the slot and then crashed before writing a scan-log row
    does not read as healthy."""
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT MAX(fire_date) FROM discord_post_log WHERE message_key = :k"
            ), {"k": PREMARKET_JOB_ID}).fetchone()
        if row is None or row[0] is None:
            return None, None
        d = row[0]
        return (d if isinstance(d, date) else date.fromisoformat(str(d))), None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_premarket] claim-ledger query failed: %r", e)
        return None, f"claim ledger query error: {e}"


def _recent_signals(engine: Engine, since: date) -> tuple[list[dict], str | None]:
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT signal_date, symbol, premarket_turnover, premarket_move,
                       premarket_vol, has_options, suggested_entry_ask, noted_at
                FROM {SIGNALS_TABLE} WHERE signal_date >= :since
                ORDER BY signal_date DESC, symbol
            """), {"since": since}).fetchall()
        return [{
            "signal_date": _isoformat(r[0]), "symbol": r[1],
            "premarket_turnover": float(r[2]) if r[2] is not None else None,
            "premarket_move": float(r[3]) if r[3] is not None else None,
            "premarket_vol": r[4], "has_options": r[5],
            "suggested_entry_ask": float(r[6]) if r[6] is not None else None,
            "noted_at": r[7].isoformat() if r[7] else None,
        } for r in rows], None
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_premarket] signals query failed: %r", e)
        return [], f"signals query error: {e}"


@router.get("/state")
async def state(days: int = SIGNAL_HISTORY_DAYS):
    """Today's premarket squeeze scan state: is it armed, did it run, and
    what did it find in the last `days` calendar days. Never raises —
    degrades to a BLOCKED-shaped payload with a `reason` rather than a 500 or
    a silently empty page."""
    today_et = datetime.now(ET).date()
    expected = _expected_run_date(today_et)

    universe_size, universe_err = _universe_size(ENGINE)
    scan_log, scan_log_err = _last_scan_log(ENGINE)
    claimed_date, claim_err = _last_claimed_date(ENGINE)

    try:
        from .squeeze_premarket_alerts import scheduled_jobs
        jobs = scheduled_jobs()
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze_premarket] scheduled_jobs failed: %r", e)
        jobs = {"registered": None, "jobs": {}, "reason": f"scheduled_jobs error: {e}"}

    n_days = max(1, min(90, days))
    since = today_et - timedelta(days=n_days)
    signals, signals_err = _recent_signals(ENGINE, since)

    # BLOCKED-STATE PRECEDENCE — same shape as gamma_alerts' health gate:
    # say why nothing is tradeable instead of rendering a verdict off a blind
    # spot. Checked in order from "most fundamentally broken" down.
    block: str | None = None
    if jobs.get("registered") is False:
        block = "The premarket scan job is not scheduled. Nothing is updating this signal."
    elif universe_size == 0:
        block = (f"{UNIVERSE_TABLE} has no symbols with a usable share count — "
                 "the separate local universe-sync job has not populated it yet.")
    elif scan_log is None:
        block = "The scan has never completed a run (no scan-log row yet)."
    else:
        last_run = date.fromisoformat(scan_log["run_date"])
        stale_sessions = 0
        d = expected
        while d > last_run:
            if d.weekday() < 5:
                stale_sessions += 1
            d -= timedelta(days=1)
        if last_run < expected and stale_sessions > 0:
            block = (f"The newest completed scan is {scan_log['run_date']}, "
                     f"{stale_sessions} session(s) behind {expected.isoformat()}.")
        elif claimed_date is not None and scan_log["run_date"] < claimed_date.isoformat():
            block = (f"The scan claimed {claimed_date.isoformat()} but the newest "
                     f"completed scan-log row is {scan_log['run_date']} — the job "
                     "ran and did not finish writing its summary.")

    capture_state = "unknown"
    if universe_err or scan_log_err or claim_err:
        capture_state = "unknown"
    elif block is None:
        capture_state = "ok"
    elif scan_log is None and claimed_date is None:
        capture_state = "never_run"
    elif claimed_date is not None and (scan_log is None or scan_log["run_date"] < claimed_date.isoformat()):
        capture_state = "claimed_but_not_stored"
    else:
        capture_state = "stale"

    return {
        "asof": today_et.isoformat(),
        "expected_run_date": expected.isoformat(),
        "blocked": block is not None,
        "block_reason": block,
        "jobs": jobs,
        "capture_health": {
            "state": capture_state,
            "claimed": claimed_date.isoformat() if claimed_date else None,
            "stored": scan_log["run_date"] if scan_log else None,
        },
        "universe_size": universe_size,
        "last_scan": scan_log,
        "rule": {
            "turnover_floor": TURNOVER_FLOOR, "move_floor": MOVE_FLOOR,
            "dedupe_days": DEDUPE_DAYS,
            "overextended_move_cap": OVEREXTENDED_MOVE_CAP,
            "overextended_turnover_cap": OVEREXTENDED_TURNOVER_CAP,
            "name": "PREREG.md #3 (V3), signal-only — no exit/P&L computed",
        },
        "signal_history_days": n_days,
        "signals": signals,
        "errors": {k: v for k, v in {
            "universe": universe_err, "scan_log": scan_log_err,
            "claim_ledger": claim_err, "signals": signals_err,
        }.items() if v},
        "advisory_only": True,
    }
