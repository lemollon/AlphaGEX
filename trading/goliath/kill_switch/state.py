"""GOLIATH kill-switch persistent state.

Per master spec section 6 + Phase 5 acceptance criteria:
    "Kill state persisted across process restarts."

Postgres-backed via migration 030. Thin Python facade exposes:
    is_killed(scope, instance_name) -> bool
    record_kill(scope, instance_name, trigger_id, reason, context)
    clear_kill(scope, instance_name, cleared_by)
    list_active_kills() -> List[dict]

All functions are best-effort: when DATABASE_URL is unset or the
adapter import fails, queries return safe defaults. is_killed
defaults to FALSE so dev shells without a DB don't deadlock the bot.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class KillScope(str, Enum):
    INSTANCE = "INSTANCE"
    PLATFORM = "PLATFORM"


@dataclass(frozen=True)
class KillEvent:
    scope: KillScope
    instance_name: Optional[str]   # None for PLATFORM
    trigger_id: str                # e.g. "I-K1", "P-K3"
    reason: str
    context: dict[str, Any]


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
        logger.warning("kill_switch.state DB connect failed: %r", exc)
        return None, False


def _normalize(scope: KillScope | str, instance_name: Optional[str]) -> tuple[str, Optional[str]]:
    s = scope.value if isinstance(scope, KillScope) else str(scope)
    return s, instance_name


def is_killed(scope: KillScope | str, instance_name: Optional[str] = None) -> bool:
    """True when an active kill row exists for the (scope, instance_name)."""
    s, name = _normalize(scope, instance_name)
    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            if name is None:
                cur.execute(
                    "SELECT 1 FROM goliath_kill_state "
                    "WHERE scope = %s AND active = TRUE LIMIT 1",
                    (s,),
                )
            else:
                cur.execute(
                    "SELECT 1 FROM goliath_kill_state "
                    "WHERE scope = %s AND instance_name = %s AND active = TRUE "
                    "LIMIT 1",
                    (s, name),
                )
            return cur.fetchone() is not None
        finally:
            cur.close()
    finally:
        conn.close()


def record_kill(event: KillEvent) -> bool:
    """Insert an active kill row. Returns True on successful persist."""
    conn, ok = _connect()
    if not ok or conn is None:
        logger.warning("record_kill(%s/%s): DB unavailable",
                       event.scope.value, event.instance_name)
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO goliath_kill_state
                    (scope, instance_name, active, trigger_id, reason, context)
                VALUES (%s, %s, TRUE, %s, %s, %s)
                """,
                (
                    event.scope.value,
                    event.instance_name,
                    event.trigger_id,
                    event.reason,
                    json.dumps(event.context, default=str),
                ),
            )
            conn.commit()
            return True
        finally:
            cur.close()
    finally:
        conn.close()


def clear_kill(
    scope: KillScope | str,
    instance_name: Optional[str],
    cleared_by: str,
) -> bool:
    """Mark all active kill rows in (scope, instance_name) as cleared.

    Returns True if at least one row was cleared. Manual-override safety:
    cleared_by is required (no anonymous overrides).
    """
    s, name = _normalize(scope, instance_name)
    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            if name is None:
                cur.execute(
                    "UPDATE goliath_kill_state SET active = FALSE, "
                    "cleared_at = NOW(), cleared_by = %s "
                    "WHERE scope = %s AND active = TRUE",
                    (cleared_by, s),
                )
            else:
                cur.execute(
                    "UPDATE goliath_kill_state SET active = FALSE, "
                    "cleared_at = NOW(), cleared_by = %s "
                    "WHERE scope = %s AND instance_name = %s AND active = TRUE",
                    (cleared_by, s, name),
                )
            cleared = cur.rowcount or 0
            conn.commit()
            return cleared > 0
        finally:
            cur.close()
    finally:
        conn.close()


def list_active_kills() -> List[dict]:
    conn, ok = _connect()
    if not ok or conn is None:
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, scope, instance_name, trigger_id, reason, killed_at "
                "FROM goliath_kill_state WHERE active = TRUE ORDER BY killed_at DESC"
            )
            rows = cur.fetchall() or []
            return [
                {
                    "id": r[0], "scope": r[1], "instance_name": r[2],
                    "trigger_id": r[3], "reason": r[4],
                    "killed_at": r[5].isoformat() if r[5] else None,
                }
                for r in rows
            ]
        finally:
            cur.close()
    finally:
        conn.close()
