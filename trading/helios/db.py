"""
HELIOS - Database Layer
=======================

Thin SQL adapter for the helios_* bot tables. Mirrors the SOLOMON pattern:

- Single class with all SQL.
- Connection-per-method (no pool).
- Reads return dicts via psycopg2.extras.RealDictCursor.
- Writes return primary keys (or None for void writes).
- Read-side methods can be called even if the trader fails to init
  (per common-mistakes.md rule §3 — decouple data endpoints from
  trader initialization).

Tables targeted (created by migrations/2026-05-07-helios-bot-tables.sql):
  helios_config, helios_paper_account, helios_signals, helios_positions,
  helios_equity_snapshots, helios_daily_perf, helios_logs, helios_scan_activity
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from .models import HeliosTradeSignal

logger = logging.getLogger(__name__)


class HeliosDatabase:
    """All HELIOS database operations in one place."""

    def __init__(self, db_url: Optional[str] = None):
        resolved = db_url or os.environ.get("DATABASE_URL")
        if not resolved:
            raise RuntimeError(
                "HeliosDatabase requires a db_url or DATABASE_URL env var"
            )
        self.db_url = resolved

    # ---- connection helpers --------------------------------------------------

    def _connect(self):
        return psycopg2.connect(self.db_url)

    # =========================================================================
    # READS
    # =========================================================================

    def get_open_position(self) -> Optional[dict]:
        """Return the single open position (max 1 by design), or None."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT *
                    FROM helios_positions
                    WHERE status = 'OPEN'
                    ORDER BY open_time DESC
                    LIMIT 1
                    """
                )
                row = c.fetchone()
                return dict(row) if row else None

    def get_position(self, position_id: int) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    "SELECT * FROM helios_positions WHERE id = %s",
                    (position_id,),
                )
                row = c.fetchone()
                return dict(row) if row else None

    def count_trades_today(self) -> int:
        """Count entries with open_time on today's CT date."""
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT COUNT(*)
                    FROM helios_positions
                    WHERE open_time::timestamptz AT TIME ZONE 'America/Chicago'
                          >= date_trunc('day', NOW() AT TIME ZONE 'America/Chicago')
                    """
                )
                row = c.fetchone()
                return int(row[0]) if row else 0

    def get_starting_capital(self) -> float:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    "SELECT starting_capital FROM helios_paper_account ORDER BY id LIMIT 1"
                )
                row = c.fetchone()
                return float(row[0]) if row else 0.0

    def get_realized_pnl(self) -> float:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    "SELECT realized_pnl FROM helios_paper_account ORDER BY id LIMIT 1"
                )
                row = c.fetchone()
                return float(row[0]) if row else 0.0

    def latest_equity_snapshot(self) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT *
                    FROM helios_equity_snapshots
                    ORDER BY snapshot_at DESC
                    LIMIT 1
                    """
                )
                row = c.fetchone()
                return dict(row) if row else None

    def all_closed_trades(self) -> list[dict]:
        """All closed positions, oldest first (for cumulative equity curve)."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT *
                    FROM helios_positions
                    WHERE status <> 'OPEN'
                    ORDER BY COALESCE(close_time, open_time) ASC
                    """
                )
                return [dict(r) for r in c.fetchall()]

    # =========================================================================
    # WRITES — signals + scan activity
    # =========================================================================

    def insert_signal(
        self,
        sig: HeliosTradeSignal,
        *,
        spot: Optional[float],
        vix: Optional[float],
    ) -> int:
        spread_type = sig.spread_type.value if sig.spread_type else None
        skip_reason = sig.skip_reason.value if sig.skip_reason else None
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO helios_signals (
                        action, spread_type, long_strike, short_strike,
                        skip_reason, detail, spot, vix
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        sig.action,
                        spread_type,
                        sig.long_strike,
                        sig.short_strike,
                        skip_reason,
                        sig.detail,
                        spot,
                        vix,
                    ),
                )
                return int(c.fetchone()[0])

    def insert_scan_activity(self, *, outcome: str, detail: str = "") -> None:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO helios_scan_activity (outcome, detail)
                    VALUES (%s, %s)
                    """,
                    (outcome, detail),
                )

    # =========================================================================
    # WRITES — positions
    # =========================================================================

    def insert_position(
        self,
        *,
        spread_type: str,
        long_symbol: str,
        short_symbol: str,
        long_strike: float,
        short_strike: float,
        expiration_date: dt.date,
        contracts: int,
        debit: float,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO helios_positions (
                        spread_type, long_symbol, short_symbol,
                        long_strike, short_strike, expiration_date,
                        contracts, debit, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'OPEN')
                    RETURNING id
                    """,
                    (
                        spread_type,
                        long_symbol,
                        short_symbol,
                        long_strike,
                        short_strike,
                        expiration_date,
                        contracts,
                        debit,
                    ),
                )
                return int(c.fetchone()[0])

    def close_position(
        self,
        position_id: int,
        *,
        close_price: float,
        realized_pnl: float,
        exit_reason: str,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    UPDATE helios_positions
                    SET status = 'CLOSED',
                        close_time = NOW(),
                        close_price = %s,
                        realized_pnl = %s,
                        exit_reason = %s
                    WHERE id = %s
                    """,
                    (close_price, realized_pnl, exit_reason, position_id),
                )

    # =========================================================================
    # WRITES — paper account
    # =========================================================================

    def bump_realized_pnl(self, delta: float) -> None:
        """Sole writer to helios_paper_account.realized_pnl + cash."""
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    UPDATE helios_paper_account
                    SET realized_pnl = realized_pnl + %s,
                        cash = cash + %s,
                        updated_at = NOW()
                    """,
                    (delta, delta),
                )

    # =========================================================================
    # WRITES — equity snapshots + daily perf
    # =========================================================================

    def insert_equity_snapshot(
        self,
        *,
        equity: float,
        cash: float,
        unrealized_pnl: float,
        open_position_count: int,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO helios_equity_snapshots (
                        equity, cash, unrealized_pnl, open_position_count
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (equity, cash, unrealized_pnl, open_position_count),
                )

    def upsert_daily_perf(
        self,
        trade_date: dt.date,
        trades: int,
        wins: int,
        losses: int,
        realized_pnl: float,
        cumulative_pnl: float,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO helios_daily_perf (
                        trade_date, trades, wins, losses,
                        realized_pnl, cumulative_pnl
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        trades = EXCLUDED.trades,
                        wins = EXCLUDED.wins,
                        losses = EXCLUDED.losses,
                        realized_pnl = EXCLUDED.realized_pnl,
                        cumulative_pnl = EXCLUDED.cumulative_pnl
                    """,
                    (
                        trade_date,
                        trades,
                        wins,
                        losses,
                        realized_pnl,
                        cumulative_pnl,
                    ),
                )

    # =========================================================================
    # LOGS
    # =========================================================================

    def log(
        self,
        level: str,
        message: str,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as c:
                    c.execute(
                        """
                        INSERT INTO helios_logs (level, message, detail)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            level,
                            message,
                            json.dumps(detail) if detail is not None else None,
                        ),
                    )
        except Exception as e:
            # Never fail callers because of a logging hiccup.
            logger.debug("HELIOS log() suppressed exception: %s", e)

    # =========================================================================
    # READS / WRITES — daily setup state (JOSHUA)
    # =========================================================================

    def load_daily_state(self, trade_date):
        """Return the daily state for trade_date. Blank state if no row."""
        from .models import DailyState
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT trade_date, wall_fade_fired, wall_break_fired,
                           flip_cross_fired, last_signal_minute
                    FROM helios_daily_state
                    WHERE trade_date = %s
                    """,
                    (trade_date,),
                )
                row = c.fetchone()
                if row is None:
                    return DailyState(trade_date=trade_date)
                return DailyState(
                    trade_date=row["trade_date"],
                    wall_fade_fired=row["wall_fade_fired"],
                    wall_break_fired=row["wall_break_fired"],
                    flip_cross_fired=row["flip_cross_fired"],
                    last_signal_minute=row["last_signal_minute"],
                )

    def upsert_daily_state(self, trade_date, *, fired, signal_minute: Optional[int] = None) -> None:
        """Set `<setup>_fired = TRUE` for the given setup. Upserts the row.

        `fired` is a SetupType (or its string value). `signal_minute` is
        optional minutes-since-open.
        """
        column_map = {
            "wall_fade": "wall_fade_fired",
            "wall_break": "wall_break_fired",
            "flip_cross": "flip_cross_fired",
        }
        key = fired.value if hasattr(fired, "value") else fired
        col = column_map[key]
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    f"""
                    INSERT INTO helios_daily_state (trade_date, {col}, last_signal_minute)
                    VALUES (%s, TRUE, %s)
                    ON CONFLICT (trade_date)
                    DO UPDATE SET
                        {col} = TRUE,
                        last_signal_minute = COALESCE(EXCLUDED.last_signal_minute, helios_daily_state.last_signal_minute),
                        updated_at = NOW()
                    """,
                    (trade_date, signal_minute),
                )
