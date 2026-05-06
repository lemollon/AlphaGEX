"""
Persistent storage for AGAPE perp signal briefs.

Briefs are generated once per day by the scheduler (after equity close at
3:30 PM CT, Mon-Fri) and stored here. Per-bot `/brief` routes read the
latest stored brief instead of calling Claude on-demand, so a dashboard
left open does not trigger fresh API spend on every SWR refresh.

One row per ticker; UPSERT replaces the prior brief on each scheduled run.
"""

import json
import logging
from typing import Any, Dict, Optional

from database_adapter import get_connection

logger = logging.getLogger(__name__)


def _ensure_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agape_perp_signal_briefs (
            ticker        TEXT PRIMARY KEY,
            brief_text    TEXT NOT NULL,
            brief_payload JSONB NOT NULL,
            generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def store_brief(ticker: str, payload: Dict[str, Any]) -> None:
    """Upsert the latest brief for a ticker."""
    brief_text = payload.get("brief") or ""
    if not brief_text:
        logger.warning(f"perp_brief_storage: refusing to store empty brief for {ticker}")
        return

    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        cur.execute(
            """
            INSERT INTO agape_perp_signal_briefs (ticker, brief_text, brief_payload, generated_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (ticker) DO UPDATE
              SET brief_text    = EXCLUDED.brief_text,
                  brief_payload = EXCLUDED.brief_payload,
                  generated_at  = EXCLUDED.generated_at
            """,
            (ticker.upper(), brief_text, json.dumps(payload, default=str)),
        )
        conn.commit()
    finally:
        conn.close()


def read_brief(ticker: str) -> Optional[Dict[str, Any]]:
    """Return the most recently stored brief for a ticker, or None."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        cur.execute(
            """
            SELECT brief_payload, generated_at
            FROM agape_perp_signal_briefs
            WHERE ticker = %s
            """,
            (ticker.upper(),),
        )
        row = cur.fetchone()
        if not row:
            return None

        payload, generated_at = row[0], row[1]
        if isinstance(payload, str):
            payload = json.loads(payload)

        result = dict(payload) if payload else {}
        result["generated_at"] = generated_at.isoformat() if generated_at else None
        return result
    finally:
        conn.close()
