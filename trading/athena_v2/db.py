"""
ATHENA V2 - Database Layer
===========================

SINGLE SOURCE OF TRUTH for all position and trade data.

Design principles:
1. Database is THE source of truth - never trust in-memory state
2. Every operation syncs with DB before acting
3. All DB operations in ONE place - no scattered SQL
4. Explicit error handling with clear return values
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager

from database_adapter import get_connection
from .models import (
    SpreadPosition, SpreadType, PositionStatus,
    ATHENAConfig, TradingMode, DailySummary, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


@contextmanager
def db_connection():
    """Context manager for database connections"""
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


class ATHENADatabase:
    """
    All ATHENA database operations in one place.

    No SQL scattered throughout the codebase.
    Clear, explicit methods for each operation.
    """

    def __init__(self, bot_name: str = "ATHENA"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure required tables exist"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Main positions table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS athena_positions (
                        id SERIAL PRIMARY KEY,
                        position_id VARCHAR(50) UNIQUE NOT NULL,
                        spread_type VARCHAR(30) NOT NULL,
                        ticker VARCHAR(10) NOT NULL,
                        long_strike DECIMAL(10, 2) NOT NULL,
                        short_strike DECIMAL(10, 2) NOT NULL,
                        expiration DATE NOT NULL,
                        entry_debit DECIMAL(10, 4) NOT NULL,
                        contracts INTEGER NOT NULL,
                        max_profit DECIMAL(10, 2) NOT NULL,
                        max_loss DECIMAL(10, 2) NOT NULL,
                        underlying_at_entry DECIMAL(10, 2) NOT NULL,
                        call_wall DECIMAL(10, 2),
                        put_wall DECIMAL(10, 2),
                        gex_regime VARCHAR(30),
                        vix_at_entry DECIMAL(6, 2),
                        oracle_confidence DECIMAL(5, 4),
                        ml_direction VARCHAR(20),
                        ml_confidence DECIMAL(5, 4),
                        order_id VARCHAR(50),
                        status VARCHAR(20) NOT NULL DEFAULT 'open',
                        open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        close_time TIMESTAMP WITH TIME ZONE,
                        close_price DECIMAL(10, 4),
                        close_reason VARCHAR(100),
                        realized_pnl DECIMAL(10, 2),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Signals table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS athena_signals (
                        id SERIAL PRIMARY KEY,
                        signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        direction VARCHAR(20) NOT NULL,
                        spread_type VARCHAR(30),
                        confidence DECIMAL(5, 4),
                        spot_price DECIMAL(10, 2),
                        call_wall DECIMAL(10, 2),
                        put_wall DECIMAL(10, 2),
                        gex_regime VARCHAR(30),
                        vix DECIMAL(6, 2),
                        rr_ratio DECIMAL(6, 2),
                        was_executed BOOLEAN DEFAULT FALSE,
                        skip_reason VARCHAR(200),
                        reasoning TEXT
                    )
                """)

                # Daily performance
                c.execute("""
                    CREATE TABLE IF NOT EXISTS athena_daily_perf (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE UNIQUE NOT NULL,
                        trades_executed INTEGER DEFAULT 0,
                        positions_closed INTEGER DEFAULT 0,
                        realized_pnl DECIMAL(10, 2) DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Logs table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS athena_logs (
                        id SERIAL PRIMARY KEY,
                        log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        level VARCHAR(10),
                        message TEXT,
                        details JSONB
                    )
                """)

                conn.commit()
                logger.info(f"{self.bot_name}: Database tables verified")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to ensure tables: {e}")

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    def get_open_positions(self) -> List[SpreadPosition]:
        """
        Get ALL open positions from database.

        This is the ONLY way to get current positions.
        Never trust in-memory state.
        """
        positions = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT
                        position_id, spread_type, ticker,
                        long_strike, short_strike, expiration,
                        entry_debit, contracts, max_profit, max_loss,
                        underlying_at_entry, call_wall, put_wall,
                        gex_regime, vix_at_entry, oracle_confidence,
                        ml_direction, ml_confidence, order_id,
                        status, open_time, close_time, close_price,
                        close_reason, realized_pnl
                    FROM athena_positions
                    WHERE status = 'open'
                    ORDER BY open_time DESC
                """)

                for row in c.fetchall():
                    pos = SpreadPosition(
                        position_id=row[0],
                        spread_type=SpreadType(row[1]),
                        ticker=row[2],
                        long_strike=float(row[3]),
                        short_strike=float(row[4]),
                        expiration=str(row[5]),
                        entry_debit=float(row[6]),
                        contracts=int(row[7]),
                        max_profit=float(row[8]),
                        max_loss=float(row[9]),
                        underlying_at_entry=float(row[10]),
                        call_wall=float(row[11] or 0),
                        put_wall=float(row[12] or 0),
                        gex_regime=row[13] or "",
                        vix_at_entry=float(row[14] or 0),
                        oracle_confidence=float(row[15] or 0),
                        ml_direction=row[16] or "",
                        ml_confidence=float(row[17] or 0),
                        order_id=row[18] or "",
                        status=PositionStatus(row[19]),
                        open_time=row[20],
                        close_time=row[21],
                        close_price=float(row[22] or 0),
                        close_reason=row[23] or "",
                        realized_pnl=float(row[24] or 0),
                    )
                    positions.append(pos)

                logger.debug(f"{self.bot_name}: Loaded {len(positions)} open positions from DB")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load positions: {e}")

        return positions

    def save_position(self, pos: SpreadPosition) -> bool:
        """
        Save a new position to database.

        Returns True if successful, False otherwise.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO athena_positions (
                        position_id, spread_type, ticker,
                        long_strike, short_strike, expiration,
                        entry_debit, contracts, max_profit, max_loss,
                        underlying_at_entry, call_wall, put_wall,
                        gex_regime, vix_at_entry, oracle_confidence,
                        ml_direction, ml_confidence, order_id,
                        status, open_time
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    pos.position_id,
                    pos.spread_type.value,
                    pos.ticker,
                    pos.long_strike,
                    pos.short_strike,
                    pos.expiration,
                    pos.entry_debit,
                    pos.contracts,
                    pos.max_profit,
                    pos.max_loss,
                    pos.underlying_at_entry,
                    pos.call_wall if pos.call_wall else None,
                    pos.put_wall if pos.put_wall else None,
                    pos.gex_regime or None,
                    pos.vix_at_entry if pos.vix_at_entry else None,
                    pos.oracle_confidence if pos.oracle_confidence else None,
                    pos.ml_direction or None,
                    pos.ml_confidence if pos.ml_confidence else None,
                    pos.order_id or None,
                    pos.status.value,
                    pos.open_time,
                ))
                conn.commit()
                logger.info(f"{self.bot_name}: Saved position {pos.position_id} to DB")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save position: {e}")
            return False

    def close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str
    ) -> bool:
        """
        Close a position in database.

        Returns True if successful, False otherwise.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE athena_positions
                    SET status = 'closed',
                        close_time = NOW(),
                        close_price = %s,
                        realized_pnl = %s,
                        close_reason = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open'
                    RETURNING id
                """, (close_price, realized_pnl, close_reason, position_id))

                result = c.fetchone()
                conn.commit()

                if result:
                    logger.info(f"{self.bot_name}: Closed position {position_id}, P&L: ${realized_pnl:.2f}")
                    return True
                else:
                    logger.warning(f"{self.bot_name}: Position {position_id} not found or already closed")
                    return False
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to close position: {e}")
            return False

    def expire_position(self, position_id: str, realized_pnl: float) -> bool:
        """Mark a position as expired with final P&L"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE athena_positions
                    SET status = 'expired',
                        close_time = NOW(),
                        close_reason = 'EXPIRED',
                        realized_pnl = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open'
                    RETURNING id
                """, (realized_pnl, position_id))

                result = c.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to expire position: {e}")
            return False

    def get_position_count(self) -> int:
        """Get count of open positions - quick check without loading all data"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM athena_positions WHERE status = 'open'")
                return c.fetchone()[0]
        except Exception:
            return 0

    # =========================================================================
    # DAILY TRACKING
    # =========================================================================

    def get_daily_trades_count(self, date: str) -> int:
        """Get number of trades executed today"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*)
                    FROM athena_positions
                    WHERE DATE(open_time AT TIME ZONE 'America/Chicago') = %s
                """, (date,))
                return c.fetchone()[0]
        except Exception:
            return 0

    def update_daily_performance(self, summary: DailySummary) -> bool:
        """Update or insert daily performance record"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO athena_daily_perf (
                        trade_date, trades_executed, positions_closed, realized_pnl
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        trades_executed = EXCLUDED.trades_executed,
                        positions_closed = EXCLUDED.positions_closed,
                        realized_pnl = EXCLUDED.realized_pnl,
                        updated_at = NOW()
                """, (
                    summary.date,
                    summary.trades_executed,
                    summary.positions_closed,
                    summary.realized_pnl,
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update daily perf: {e}")
            return False

    # =========================================================================
    # SIGNAL LOGGING
    # =========================================================================

    def log_signal(
        self,
        direction: str,
        spread_type: Optional[str],
        confidence: float,
        spot_price: float,
        call_wall: float,
        put_wall: float,
        gex_regime: str,
        vix: float,
        rr_ratio: float,
        was_executed: bool,
        skip_reason: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> Optional[int]:
        """Log a trading signal"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO athena_signals (
                        direction, spread_type, confidence, spot_price,
                        call_wall, put_wall, gex_regime, vix, rr_ratio,
                        was_executed, skip_reason, reasoning
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    direction, spread_type, confidence, spot_price,
                    call_wall, put_wall, gex_regime, vix, rr_ratio,
                    was_executed, skip_reason, reasoning
                ))
                signal_id = c.fetchone()[0]
                conn.commit()
                return signal_id
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log signal: {e}")
            return None

    # =========================================================================
    # CONFIG
    # =========================================================================

    def load_config(self) -> ATHENAConfig:
        """Load config from database, with defaults"""
        config = ATHENAConfig()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT config_key, config_value
                    FROM autonomous_config
                    WHERE bot_name = 'ATHENA'
                """)

                for key, value in c.fetchall():
                    if hasattr(config, key):
                        if key == 'mode':
                            setattr(config, key, TradingMode(value))
                        elif isinstance(getattr(config, key), float):
                            setattr(config, key, float(value))
                        elif isinstance(getattr(config, key), int):
                            setattr(config, key, int(value))
                        else:
                            setattr(config, key, value)

                logger.info(f"{self.bot_name}: Loaded config from DB")
        except Exception as e:
            logger.warning(f"{self.bot_name}: Using default config: {e}")

        return config

    # =========================================================================
    # LOGGING
    # =========================================================================

    def log(self, level: str, message: str, details: Optional[Dict] = None) -> None:
        """Log to database"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                import json
                c.execute("""
                    INSERT INTO athena_logs (level, message, details)
                    VALUES (%s, %s, %s)
                """, (level, message, json.dumps(details) if details else None))
                conn.commit()
        except Exception:
            pass  # Don't fail on logging errors

    def update_heartbeat(self, status: str, action: str) -> None:
        """Update bot heartbeat for monitoring"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO bot_heartbeat (bot_name, status, last_action, last_scan_time)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (bot_name) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_action = EXCLUDED.last_action,
                        last_scan_time = NOW()
                """, (self.bot_name, status, action))
                conn.commit()
        except Exception:
            pass
