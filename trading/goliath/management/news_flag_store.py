"""Postgres-backed material-news flag store.

Per Leron Q5 (2026-04-29): material-news flagging is a manual CLI
action. Flag persists in goliath_news_flags (migration 029) until
manually cleared. T6 reads is_ticker_flagged() each management cycle.

All functions are best-effort: when DATABASE_URL is unset or the
adapter import fails, queries return safe defaults (False for
is_ticker_flagged, [] for list, no-op writes). This keeps unit tests
and dev shells working without a database.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _connect():
    """Return (conn, available) -- conn is None when DB is unreachable."""
    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError:
        return None, False
    if not is_database_available():
        return None, False
    try:
        return get_connection(), True
    except Exception as exc:  # noqa: BLE001
        logger.warning("news_flag_store DB connect failed: %r", exc)
        return None, False


def is_ticker_flagged(ticker: str) -> bool:
    """True when ticker has an active row in goliath_news_flags."""
    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM goliath_news_flags WHERE ticker = %s LIMIT 1",
                (ticker,),
            )
            return cur.fetchone() is not None
        finally:
            cur.close()
    finally:
        conn.close()


def flag_ticker(ticker: str, reason: str = "", flagged_by: str = "cli") -> bool:
    """Insert or update flag for ticker. Returns True on success."""
    conn, ok = _connect()
    if not ok or conn is None:
        logger.warning("flag_ticker(%s): DB unavailable; flag not persisted", ticker)
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO goliath_news_flags (ticker, reason, flagged_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE
                  SET reason = EXCLUDED.reason,
                      flagged_at = NOW(),
                      flagged_by = EXCLUDED.flagged_by
                """,
                (ticker, reason, flagged_by),
            )
            conn.commit()
            return True
        finally:
            cur.close()
    finally:
        conn.close()


def unflag_ticker(ticker: str) -> bool:
    """Remove flag for ticker. Returns True if a row was deleted."""
    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM goliath_news_flags WHERE ticker = %s", (ticker,))
            deleted = cur.rowcount or 0
            conn.commit()
            return deleted > 0
        finally:
            cur.close()
    finally:
        conn.close()


def list_flagged_tickers() -> List[dict]:
    """Return all active flags as dicts."""
    conn, ok = _connect()
    if not ok or conn is None:
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT ticker, reason, flagged_at, flagged_by FROM goliath_news_flags "
                "ORDER BY flagged_at DESC"
            )
            rows = cur.fetchall() or []
            return [
                {
                    "ticker": r[0],
                    "reason": r[1],
                    "flagged_at": r[2].isoformat() if r[2] else None,
                    "flagged_by": r[3],
                }
                for r in rows
            ]
        finally:
            cur.close()
    finally:
        conn.close()
