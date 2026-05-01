"""GOLIATH heartbeat writer.

Writes to the existing ``bot_heartbeats`` table (migration 007) using
the platform-standard UPSERT pattern keyed on ``bot_name``. Matches the
shape used by FORTRESS/SOLOMON/etc so the existing dashboard heartbeat
view picks up GOLIATH instances automatically.

Per master spec section 10.2: heartbeat every 60s. v1 implementation
calls ``record_heartbeat`` from each runner cycle (entry + management),
which fires roughly every 5 minutes per LETF instance during market
hours. That's denser than spec-required 60s for any single bot but
cheap (one UPSERT per cycle).

If we need true 60s ticks regardless of cycle activity, that's a v0.3
add (background thread or scheduler entry).

All operations are best-effort: DB unavailable -> return False; failed
INSERT/UPDATE -> log warning, return False. Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _connect():
    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError:
        return None, False
    if not is_database_available():
        return None, False
    try:
        return get_connection(), True
    except Exception as exc:  # noqa: BLE001
        logger.warning("monitoring.heartbeat DB connect failed: %r", exc)
        return None, False


def record_heartbeat(
    bot_name: str,
    status: str = "OK",
    scan_count_delta: int = 1,
    trades_today_delta: int = 0,
    last_trade_time: Optional[datetime] = None,
    details: Optional[dict[str, Any]] = None,
) -> bool:
    """UPSERT one heartbeat row keyed on bot_name.

    Args:
        bot_name: bot-guard tag, e.g. "GOLIATH-MSTU"
        status: short status string ("OK", "DEGRADED", "KILLED", "STOPPED")
        scan_count_delta: increment to scan_count (default 1)
        trades_today_delta: increment to trades_today (default 0)
        last_trade_time: optional timestamp of most recent trade
        details: optional JSON payload for diagnostics

    Returns True on successful persist; False on DB unavailability or
    write failure. Never raises.
    """
    conn, ok = _connect()
    if not ok or conn is None:
        return False

    now = datetime.now(timezone.utc)
    details_json = json.dumps(details, default=str) if details else None

    try:
        cur = conn.cursor()
        try:
            # UPSERT keyed on UNIQUE(bot_name). Increment counters; replace
            # status / last_heartbeat / details on every call.
            cur.execute(
                """
                INSERT INTO bot_heartbeats (
                    bot_name, last_heartbeat, status, scan_count,
                    trades_today, last_trade_time, details
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bot_name) DO UPDATE SET
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    status = EXCLUDED.status,
                    scan_count = bot_heartbeats.scan_count + %s,
                    trades_today = bot_heartbeats.trades_today + %s,
                    last_trade_time = COALESCE(
                        EXCLUDED.last_trade_time, bot_heartbeats.last_trade_time
                    ),
                    details = EXCLUDED.details
                """,
                (
                    bot_name, now, status, scan_count_delta,
                    trades_today_delta, last_trade_time, details_json,
                    scan_count_delta, trades_today_delta,
                ),
            )
            conn.commit()
            return True
        finally:
            cur.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_heartbeat(%s) failed: %r", bot_name, exc)
        return False
    finally:
        conn.close()


def read_heartbeat(bot_name: str) -> Optional[dict[str, Any]]:
    """Read the current heartbeat row for ``bot_name``. None if missing
    or DB unavailable. Useful for staleness checks and the runbook."""
    conn, ok = _connect()
    if not ok or conn is None:
        return None
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT bot_name, last_heartbeat, status, scan_count, "
                "trades_today, last_trade_time, details "
                "FROM bot_heartbeats WHERE bot_name = %s",
                (bot_name,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "bot_name": row[0],
                "last_heartbeat": row[1].isoformat() if row[1] else None,
                "status": row[2],
                "scan_count": row[3],
                "trades_today": row[4],
                "last_trade_time": row[5].isoformat() if row[5] else None,
                "details": row[6] if isinstance(row[6], dict) else (
                    json.loads(row[6]) if row[6] else None
                ),
            }
        finally:
            cur.close()
    finally:
        conn.close()


def is_stale(bot_name: str, max_age_seconds: int = 300) -> bool:
    """True when the heartbeat is missing or older than ``max_age_seconds``.

    Default 300s = 5 min, matches "heartbeat missed > 3 min" spec rule
    with a small buffer for cycle jitter.
    """
    hb = read_heartbeat(bot_name)
    if hb is None or hb.get("last_heartbeat") is None:
        return True
    try:
        last = datetime.fromisoformat(hb["last_heartbeat"])
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last).total_seconds()
    return age > max_age_seconds
