"""Postgres-backed append-only audit store for GOLIATH trade events.

Per master spec section 10.1 + Leron Q2 (2026-04-29): audit storage is
Postgres-only in v0.2. Append-only enforced at the application layer
-- this module exposes ``insert`` and ``query`` only; no UPDATE/DELETE.

All functions are best-effort: when DATABASE_URL is unset or the
adapter import fails, ``insert`` returns False and ``query`` returns
[]. This keeps unit tests and dev shells working without a database.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


VALID_EVENT_TYPES = frozenset({
    "ENTRY_EVAL",
    "ENTRY_FILLED",
    "MANAGEMENT_EVAL",
    "EXIT_FILLED",
})


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
        logger.warning("audit.store DB connect failed: %r", exc)
        return None, False


def insert(
    instance: str,
    event_type: str,
    data: dict[str, Any],
    position_id: Optional[str] = None,
) -> bool:
    """Append one audit row. Returns True on success, False on failure.

    Args:
        instance: e.g. "GOLIATH-MSTU"
        event_type: one of VALID_EVENT_TYPES
        data: arbitrary JSON-serializable payload
        position_id: optional UUID/name correlating events for one trade
    """
    if event_type not in VALID_EVENT_TYPES:
        logger.warning("audit.insert: invalid event_type %r", event_type)
        return False

    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO goliath_trade_audit (instance, event_type, data, position_id)
                VALUES (%s, %s, %s, %s)
                """,
                (instance, event_type, json.dumps(data, default=str), position_id),
            )
            conn.commit()
            return True
        finally:
            cur.close()
    finally:
        conn.close()


def query_by_position(position_id: str) -> List[dict]:
    """Return all events for a single position, oldest first."""
    conn, ok = _connect()
    if not ok or conn is None:
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, timestamp, instance, event_type, data, position_id "
                "FROM goliath_trade_audit "
                "WHERE position_id = %s ORDER BY timestamp ASC",
                (position_id,),
            )
            return _rows_to_dicts(cur.fetchall() or [])
        finally:
            cur.close()
    finally:
        conn.close()


def query_recent(instance: str, limit: int = 100) -> List[dict]:
    """Return most recent events for an instance, newest first."""
    conn, ok = _connect()
    if not ok or conn is None:
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, timestamp, instance, event_type, data, position_id "
                "FROM goliath_trade_audit "
                "WHERE instance = %s ORDER BY timestamp DESC LIMIT %s",
                (instance, int(limit)),
            )
            return _rows_to_dicts(cur.fetchall() or [])
        finally:
            cur.close()
    finally:
        conn.close()


def _rows_to_dicts(rows: list) -> List[dict]:
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "timestamp": r[1].isoformat() if r[1] else None,
            "instance": r[2],
            "event_type": r[3],
            "data": r[4] if isinstance(r[4], dict) else (json.loads(r[4]) if r[4] else {}),
            "position_id": r[5],
        })
    return out
