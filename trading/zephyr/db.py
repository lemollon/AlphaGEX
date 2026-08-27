"""
ZEPHYR Database Layer - single source of truth for all ZEPHYR scalp data.

Tables (auto-created on first use):
  zephyr_config           - bot config (starting_capital, locks, provider)
  zephyr_positions        - open + closed scalps (status column)
  zephyr_equity_snapshots - intraday equity curve points
  zephyr_scan_activity    - every scan cycle + outcome
  zephyr_fair_value_log   - fair value vs Kalshi mid over time (lag/edge proof)
  zephyr_game_events      - score events + reaction latency (kill-switch proof)
  zephyr_ml_shadow        - would-be scalps logged before risking money

All reads are decoupled from the trader: routes use ZephyrDatabase directly so a
dead trader never 500s a dashboard. All timestamps are stored UTC/tz-aware and
rendered in America/Chicago at the query edge.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from database_adapter import get_connection
from .models import CENTRAL_TZ, ExitReason, ScalpPosition, PositionStatus, Side

logger = logging.getLogger(__name__)


@contextmanager
def db_connection():
    conn = None
    try:
        conn = get_connection()
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


class ZephyrDatabase:
    def __init__(self, bot_name: str = "ZEPHYR"):
        self.bot_name = bot_name
        self._ensure_tables()

    # --------------------------------------------------------------- schema
    def _ensure_tables(self) -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_config (
                        key VARCHAR(64) PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_positions (
                        id SERIAL PRIMARY KEY,
                        position_id VARCHAR(64) UNIQUE NOT NULL,
                        market_id VARCHAR(96) NOT NULL,
                        sport VARCHAR(16) NOT NULL,
                        side VARCHAR(4) NOT NULL,
                        contracts INTEGER NOT NULL,
                        entry_cents DECIMAL(6,2) NOT NULL,
                        fair_at_entry_cents DECIMAL(6,2),
                        is_maker BOOLEAN DEFAULT TRUE,
                        is_paper BOOLEAN DEFAULT TRUE,
                        kalshi_order_id VARCHAR(64),
                        status VARCHAR(12) NOT NULL DEFAULT 'open',
                        open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        close_time TIMESTAMP WITH TIME ZONE,
                        exit_cents DECIMAL(6,2),
                        exit_reason VARCHAR(24),
                        entry_fee DECIMAL(8,4) DEFAULT 0,
                        exit_fee DECIMAL(8,4) DEFAULT 0,
                        realized_pnl DECIMAL(10,4),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_equity_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        equity DECIMAL(12,2) NOT NULL,
                        realized_pnl DECIMAL(12,4) DEFAULT 0,
                        unrealized_pnl DECIMAL(12,4) DEFAULT 0,
                        open_positions INTEGER DEFAULT 0
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_scan_activity (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        market_id VARCHAR(96),
                        sport VARCHAR(16),
                        outcome VARCHAR(32) NOT NULL,
                        fair_cents DECIMAL(6,2),
                        kalshi_mid_cents DECIMAL(6,2),
                        edge_cents DECIMAL(6,2),
                        required_edge_cents DECIMAL(6,2),
                        reason TEXT
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_fair_value_log (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        market_id VARCHAR(96) NOT NULL,
                        source VARCHAR(24),
                        fair_cents DECIMAL(6,2),
                        kalshi_mid_cents DECIMAL(6,2),
                        gap_cents DECIMAL(6,2),
                        confidence DECIMAL(4,3)
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_game_events (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        market_id VARCHAR(96) NOT NULL,
                        sport VARCHAR(16),
                        event_type VARCHAR(24),
                        reaction_ms INTEGER,
                        detail TEXT
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS zephyr_ml_shadow (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        market_id VARCHAR(96),
                        sport VARCHAR(16),
                        action VARCHAR(24),
                        edge_cents DECIMAL(6,2),
                        required_edge_cents DECIMAL(6,2),
                        would_have_traded BOOLEAN,
                        actual_outcome VARCHAR(24)
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS idx_zephyr_pos_status ON zephyr_positions(status)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_zephyr_pos_close ON zephyr_positions(close_time)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_zephyr_scan_ts ON zephyr_scan_activity(timestamp)")
                conn.commit()
        except Exception as e:
            # Never fatal-raise from table creation (see common-mistakes #3).
            logger.error("zephyr _ensure_tables failed (continuing): %s", e)

    # --------------------------------------------------------------- config
    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT value FROM zephyr_config WHERE key = %s", (key,))
                row = c.fetchone()
                return row[0] if row else default
        except Exception:
            return default

    def set_config(self, key: str, value: str) -> None:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO zephyr_config (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, value))
            conn.commit()

    def get_starting_capital(self, default: float = 500.0) -> float:
        val = self.get_config("starting_capital")
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------ positions
    def insert_position(self, pos: ScalpPosition) -> None:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO zephyr_positions
                    (position_id, market_id, sport, side, contracts, entry_cents,
                     fair_at_entry_cents, is_maker, is_paper, kalshi_order_id,
                     status, open_time, entry_fee)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (position_id) DO NOTHING
            """, (
                pos.position_id, pos.market_id, pos.sport, pos.side.value,
                pos.contracts, pos.entry_cents, pos.fair_at_entry_cents,
                pos.is_maker, pos.is_paper, pos.kalshi_order_id,
                pos.status.value, pos.open_time or datetime.now(CENTRAL_TZ),
                pos.entry_fee,
            ))
            conn.commit()

    def close_position(self, position_id: str, exit_cents: float,
                       exit_reason: ExitReason, realized_pnl: float,
                       exit_fee: float = 0.0) -> None:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE zephyr_positions
                SET status = 'closed', close_time = NOW(), exit_cents = %s,
                    exit_reason = %s, realized_pnl = %s, exit_fee = %s
                WHERE position_id = %s
            """, (exit_cents, exit_reason.value, realized_pnl, exit_fee, position_id))
            conn.commit()

    def get_open_positions(self) -> List[Dict[str, Any]]:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT position_id, market_id, sport, side, contracts, entry_cents,
                       fair_at_entry_cents, is_maker, is_paper,
                       open_time AT TIME ZONE 'America/Chicago' AS open_time_ct
                FROM zephyr_positions WHERE status = 'open' ORDER BY open_time DESC
            """)
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]

    def get_closed_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        # Historical equity must query ALL closed trades - no date filter on SQL.
        with db_connection() as conn:
            c = conn.cursor()
            sql = """
                SELECT position_id, market_id, sport, side, contracts, entry_cents,
                       exit_cents, exit_reason, COALESCE(realized_pnl, 0) AS realized_pnl,
                       COALESCE(entry_fee,0)+COALESCE(exit_fee,0) AS fees,
                       open_time AT TIME ZONE 'America/Chicago' AS open_time_ct,
                       close_time AT TIME ZONE 'America/Chicago' AS close_time_ct
                FROM zephyr_positions WHERE status = 'closed' ORDER BY close_time ASC
            """
            c.execute(sql)
            cols = [d[0] for d in c.description]
            rows = [dict(zip(cols, r)) for r in c.fetchall()]
            return rows[-limit:] if limit else rows

    # --------------------------------------------------------- equity curve
    def equity_curve(self, starting_capital: Optional[float] = None) -> List[Dict[str, Any]]:
        cap = starting_capital if starting_capital is not None else self.get_starting_capital()
        trades = self.get_closed_trades()
        curve, running = [], 0.0
        for t in trades:
            running += float(t["realized_pnl"])
            curve.append({
                "close_time": t["close_time_ct"].isoformat() if t["close_time_ct"] else None,
                "cumulative_pnl": round(running, 4),
                "equity": round(cap + running, 4),
            })
        if not curve:
            # Never return an empty chart silently (common-mistakes #1).
            return [{"close_time": None, "cumulative_pnl": 0.0, "equity": cap,
                     "note": "No closed scalps yet"}]
        return curve

    def save_equity_snapshot(self, equity: float, realized: float,
                            unrealized: float, open_positions: int) -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO zephyr_equity_snapshots
                        (equity, realized_pnl, unrealized_pnl, open_positions)
                    VALUES (%s,%s,%s,%s)
                """, (equity, realized, unrealized, open_positions))
                conn.commit()
        except Exception as e:
            logger.debug("zephyr snapshot save failed: %s", e)

    def intraday_equity(self) -> List[Dict[str, Any]]:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct, equity,
                       realized_pnl, unrealized_pnl, open_positions
                FROM zephyr_equity_snapshots
                WHERE timestamp >= (NOW() AT TIME ZONE 'America/Chicago')::date
                ORDER BY timestamp ASC
            """)
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]

    # ------------------------------------------------------------- logging
    def log_scan(self, *, market_id: Optional[str], sport: Optional[str], outcome: str,
                 fair_cents=None, kalshi_mid_cents=None, edge_cents=None,
                 required_edge_cents=None, reason: str = "") -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO zephyr_scan_activity
                        (market_id, sport, outcome, fair_cents, kalshi_mid_cents,
                         edge_cents, required_edge_cents, reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (market_id, sport, outcome, fair_cents, kalshi_mid_cents,
                      edge_cents, required_edge_cents, reason[:500]))
                conn.commit()
        except Exception as e:
            logger.debug("zephyr log_scan failed: %s", e)

    def get_recent_scans(self, limit: int = 100) -> List[Dict[str, Any]]:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct, market_id,
                       sport, outcome, fair_cents, kalshi_mid_cents, edge_cents,
                       required_edge_cents, reason
                FROM zephyr_scan_activity ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]

    def log_fair_value(self, market_id: str, source: str, fair_cents: float,
                       kalshi_mid_cents: Optional[float], confidence: float) -> None:
        gap = (fair_cents - kalshi_mid_cents) if kalshi_mid_cents is not None else None
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO zephyr_fair_value_log
                        (market_id, source, fair_cents, kalshi_mid_cents, gap_cents, confidence)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (market_id, source, fair_cents, kalshi_mid_cents, gap, confidence))
                conn.commit()
        except Exception as e:
            logger.debug("zephyr log_fair_value failed: %s", e)

    def log_game_event(self, market_id: str, sport: str, event_type: str,
                       reaction_ms: Optional[int], detail: Dict[str, Any]) -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO zephyr_game_events
                        (market_id, sport, event_type, reaction_ms, detail)
                    VALUES (%s,%s,%s,%s,%s)
                """, (market_id, sport, event_type, reaction_ms, json.dumps(detail)[:1000]))
                conn.commit()
        except Exception as e:
            logger.debug("zephyr log_game_event failed: %s", e)

    # --------------------------------------------------------- performance
    def performance(self) -> Dict[str, Any]:
        trades = self.get_closed_trades()
        n = len(trades)
        if n == 0:
            return {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0,
                    "total_fees": 0.0, "avg_pnl": 0.0, "note": "No closed scalps yet"}
        pnls = [float(t["realized_pnl"]) for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        fees = sum(float(t["fees"]) for t in trades)
        total = sum(pnls)
        return {
            "trades": n,
            "win_rate": round(wins / n * 100.0, 2),
            "total_pnl": round(total, 4),
            "total_fees": round(fees, 4),
            "avg_pnl": round(total / n, 4),
        }
