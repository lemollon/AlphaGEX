"""
ARES V2 - Database Layer
=========================

SINGLE SOURCE OF TRUTH for all Iron Condor position and trade data.

Design principles:
1. Database is THE source of truth - never trust in-memory state
2. Every operation syncs with DB before acting
3. All DB operations in ONE place - no scattered SQL
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from database_adapter import get_connection
from .models import (
    IronCondorPosition, PositionStatus,
    ARESConfig, TradingMode, StrategyPreset,
    DailySummary, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


def _to_python(val):
    """Convert numpy types to native Python types for database insertion"""
    if val is None:
        return None
    # Handle numpy types
    type_name = type(val).__name__
    if 'float' in type_name or 'Float' in type_name:
        return float(val)
    if 'int' in type_name or 'Int' in type_name:
        return int(val)
    if 'bool' in type_name:
        return bool(val)
    if 'str' in type_name:
        return str(val)
    # Check for numpy array scalar
    if hasattr(val, 'item'):
        return val.item()
    return val


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


class ARESDatabase:
    """
    All ARES database operations in one place.

    No SQL scattered throughout the codebase.
    """

    def __init__(self, bot_name: str = "ARES"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure required tables exist"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Main positions table for Iron Condors
                c.execute("""
                    CREATE TABLE IF NOT EXISTS ares_positions (
                        id SERIAL PRIMARY KEY,
                        position_id VARCHAR(50) UNIQUE NOT NULL,
                        ticker VARCHAR(10) NOT NULL,
                        expiration DATE NOT NULL,

                        -- Put spread
                        put_short_strike DECIMAL(10, 2) NOT NULL,
                        put_long_strike DECIMAL(10, 2) NOT NULL,
                        put_credit DECIMAL(10, 4) NOT NULL,

                        -- Call spread
                        call_short_strike DECIMAL(10, 2) NOT NULL,
                        call_long_strike DECIMAL(10, 2) NOT NULL,
                        call_credit DECIMAL(10, 4) NOT NULL,

                        -- Position details
                        contracts INTEGER NOT NULL,
                        spread_width DECIMAL(10, 2) NOT NULL,
                        total_credit DECIMAL(10, 4) NOT NULL,
                        max_loss DECIMAL(10, 2) NOT NULL,
                        max_profit DECIMAL(10, 2) NOT NULL,

                        -- Market context
                        underlying_at_entry DECIMAL(10, 2) NOT NULL,
                        vix_at_entry DECIMAL(6, 2),
                        expected_move DECIMAL(10, 2),
                        call_wall DECIMAL(10, 2),
                        put_wall DECIMAL(10, 2),
                        gex_regime VARCHAR(30),
                        oracle_confidence DECIMAL(5, 4),
                        oracle_reasoning TEXT,

                        -- Order tracking
                        put_order_id VARCHAR(50),
                        call_order_id VARCHAR(50),

                        -- Status
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
                    CREATE TABLE IF NOT EXISTS ares_signals (
                        id SERIAL PRIMARY KEY,
                        signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        spot_price DECIMAL(10, 2),
                        vix DECIMAL(6, 2),
                        expected_move DECIMAL(10, 2),
                        call_wall DECIMAL(10, 2),
                        put_wall DECIMAL(10, 2),
                        gex_regime VARCHAR(30),
                        put_short DECIMAL(10, 2),
                        put_long DECIMAL(10, 2),
                        call_short DECIMAL(10, 2),
                        call_long DECIMAL(10, 2),
                        total_credit DECIMAL(10, 4),
                        confidence DECIMAL(5, 4),
                        was_executed BOOLEAN DEFAULT FALSE,
                        skip_reason VARCHAR(200),
                        reasoning TEXT
                    )
                """)

                # Daily performance
                c.execute("""
                    CREATE TABLE IF NOT EXISTS ares_daily_perf (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE UNIQUE NOT NULL,
                        trades_executed INTEGER DEFAULT 0,
                        positions_closed INTEGER DEFAULT 0,
                        realized_pnl DECIMAL(10, 2) DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Logs
                c.execute("""
                    CREATE TABLE IF NOT EXISTS ares_logs (
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

    def get_open_positions(self) -> List[IronCondorPosition]:
        """Get ALL open positions from database"""
        positions = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        flip_point, net_gex,
                        oracle_confidence, oracle_win_probability, oracle_advice,
                        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
                        put_order_id, call_order_id,
                        status, open_time, close_time, close_price, close_reason, realized_pnl
                    FROM ares_positions
                    WHERE status = 'open'
                    ORDER BY open_time DESC
                """)

                for row in c.fetchall():
                    pos = IronCondorPosition(
                        position_id=row[0],
                        ticker=row[1],
                        expiration=str(row[2]),
                        put_short_strike=float(row[3]),
                        put_long_strike=float(row[4]),
                        put_credit=float(row[5]),
                        call_short_strike=float(row[6]),
                        call_long_strike=float(row[7]),
                        call_credit=float(row[8]),
                        contracts=int(row[9]),
                        spread_width=float(row[10]),
                        total_credit=float(row[11]),
                        max_loss=float(row[12]),
                        max_profit=float(row[13]),
                        underlying_at_entry=float(row[14]),
                        vix_at_entry=float(row[15] or 0),
                        expected_move=float(row[16] or 0),
                        call_wall=float(row[17] or 0),
                        put_wall=float(row[18] or 0),
                        gex_regime=row[19] or "",
                        # Kronos context
                        flip_point=float(row[20] or 0),
                        net_gex=float(row[21] or 0),
                        # Oracle context (FULL audit trail)
                        oracle_confidence=float(row[22] or 0),
                        oracle_win_probability=float(row[23] or 0),
                        oracle_advice=row[24] or "",
                        oracle_reasoning=row[25] or "",
                        oracle_top_factors=row[26] or "",
                        oracle_use_gex_walls=bool(row[27]),
                        put_order_id=row[28] or "",
                        call_order_id=row[29] or "",
                        status=PositionStatus(row[30]),
                        open_time=row[31],
                        close_time=row[32],
                        close_price=float(row[33] or 0),
                        close_reason=row[34] or "",
                        realized_pnl=float(row[35] or 0),
                    )
                    positions.append(pos)

                logger.debug(f"{self.bot_name}: Loaded {len(positions)} open positions")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load positions: {e}")

        return positions

    def save_position(self, pos: IronCondorPosition) -> bool:
        """Save a new position to database with FULL Oracle/Kronos context"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Ensure new columns exist (migration)
                self._ensure_oracle_columns(c)

                c.execute("""
                    INSERT INTO ares_positions (
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        flip_point, net_gex,
                        oracle_confidence, oracle_win_probability, oracle_advice,
                        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
                        put_order_id, call_order_id,
                        status, open_time, open_date
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                """, (
                    pos.position_id, pos.ticker, pos.expiration,
                    _to_python(pos.put_short_strike), _to_python(pos.put_long_strike), _to_python(pos.put_credit),
                    _to_python(pos.call_short_strike), _to_python(pos.call_long_strike), _to_python(pos.call_credit),
                    _to_python(pos.contracts), _to_python(pos.spread_width), _to_python(pos.total_credit),
                    _to_python(pos.max_loss), _to_python(pos.max_profit),
                    _to_python(pos.underlying_at_entry), _to_python(pos.vix_at_entry), _to_python(pos.expected_move),
                    _to_python(pos.call_wall), _to_python(pos.put_wall), pos.gex_regime or None,
                    _to_python(pos.flip_point), _to_python(pos.net_gex),
                    _to_python(pos.oracle_confidence), _to_python(pos.oracle_win_probability), pos.oracle_advice or None,
                    pos.oracle_reasoning or None, pos.oracle_top_factors or None, bool(pos.oracle_use_gex_walls),
                    pos.put_order_id or None, pos.call_order_id or None,
                    pos.status.value, pos.open_time, pos.open_time.date() if pos.open_time else datetime.now(CENTRAL_TZ).date(),
                ))
                conn.commit()
                logger.info(f"{self.bot_name}: Saved position {pos.position_id}")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save position: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _ensure_oracle_columns(self, cursor) -> None:
        """Add new Oracle/Kronos columns if they don't exist (migration)"""
        columns_to_add = [
            ("flip_point", "DECIMAL(10, 2)"),
            ("net_gex", "DECIMAL(15, 2)"),
            ("oracle_win_probability", "DECIMAL(8, 4)"),  # DECIMAL(8,4) for proper precision
            ("oracle_advice", "VARCHAR(20)"),
            ("oracle_top_factors", "TEXT"),
            ("oracle_use_gex_walls", "BOOLEAN DEFAULT FALSE"),
            ("open_date", "DATE"),  # Extracted date from open_time for easier queries
        ]

        for col_name, col_type in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE ares_positions
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """)
            except Exception:
                pass  # Column might already exist

    def close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str
    ) -> bool:
        """Close a position"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE ares_positions
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
                    logger.info(f"{self.bot_name}: Closed {position_id}, P&L=${realized_pnl:.2f}")
                    return True
                return False
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to close position: {e}")
            return False

    def expire_position(self, position_id: str, realized_pnl: float, close_price: float = None) -> bool:
        """Mark position as expired with final P&L and close price"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE ares_positions
                    SET status = 'expired',
                        close_time = NOW(),
                        close_reason = 'EXPIRED',
                        close_price = %s,
                        realized_pnl = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open'
                    RETURNING id
                """, (_to_python(close_price), _to_python(realized_pnl), position_id))
                result = c.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to expire position: {e}")
            return False

    def partial_close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str,
        closed_leg: str  # 'put' or 'call'
    ) -> bool:
        """
        Mark position as partially closed when one leg closes but the other fails.

        This prevents orphaned positions where Tradier has one leg closed
        but the database still shows position as fully open.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE ares_positions
                    SET status = 'partial_close',
                        close_time = NOW(),
                        close_price = %s,
                        realized_pnl = %s,
                        close_reason = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open'
                    RETURNING id
                """, (
                    _to_python(close_price),
                    _to_python(realized_pnl),
                    f"{close_reason}_{closed_leg.upper()}_ONLY",
                    position_id
                ))
                result = c.fetchone()
                conn.commit()

                if result:
                    logger.warning(
                        f"{self.bot_name}: PARTIAL CLOSE {position_id} - "
                        f"Only {closed_leg} leg closed, P&L=${realized_pnl:.2f}"
                    )
                    return True
                return False
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to partial close position: {e}")
            return False

    def get_position_count(self) -> int:
        """Get count of open positions"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM ares_positions WHERE status = 'open'")
                return c.fetchone()[0]
        except Exception:
            return 0

    def has_traded_today(self, date: str) -> bool:
        """Check if we've already traded today"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*)
                    FROM ares_positions
                    WHERE DATE(open_time AT TIME ZONE 'America/Chicago') = %s
                """, (date,))
                return c.fetchone()[0] > 0
        except Exception:
            return False

    def get_trades_today_count(self, date: str) -> int:
        """Get count of trades opened today (for multi-trade-per-day support)"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*)
                    FROM ares_positions
                    WHERE DATE(open_time AT TIME ZONE 'America/Chicago') = %s
                """, (date,))
                return c.fetchone()[0]
        except Exception:
            return 0

    def get_daily_realized_pnl(self, date: str) -> float:
        """
        Get total realized P&L for positions closed today.

        Used for daily loss limit enforcement to prevent unlimited losses.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM ares_positions
                    WHERE status IN ('closed', 'expired', 'partial_close')
                    AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
                """, (date,))
                result = c.fetchone()[0]
                return float(result) if result else 0.0
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get daily P&L: {e}")
            return 0.0

    def get_partial_close_positions(self) -> List[IronCondorPosition]:
        """
        Get positions in partial_close state that need manual intervention.

        These are positions where one leg closed but the other failed.
        """
        positions = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        put_order_id, call_order_id,
                        status, open_time, close_time, close_price, close_reason, realized_pnl
                    FROM ares_positions
                    WHERE status = 'partial_close'
                    ORDER BY close_time DESC
                """)

                for row in c.fetchall():
                    pos = IronCondorPosition(
                        position_id=row[0],
                        ticker=row[1],
                        expiration=str(row[2]),
                        put_short_strike=float(row[3]),
                        put_long_strike=float(row[4]),
                        put_credit=float(row[5]),
                        call_short_strike=float(row[6]),
                        call_long_strike=float(row[7]),
                        call_credit=float(row[8]),
                        contracts=int(row[9]),
                        spread_width=float(row[10]),
                        total_credit=float(row[11]),
                        max_loss=float(row[12]),
                        max_profit=float(row[13]),
                        underlying_at_entry=float(row[14]),
                        vix_at_entry=float(row[15] or 0),
                        expected_move=float(row[16] or 0),
                        call_wall=float(row[17] or 0),
                        put_wall=float(row[18] or 0),
                        gex_regime=row[19] or "",
                        put_order_id=row[20] or "",
                        call_order_id=row[21] or "",
                        status=PositionStatus(row[22]),
                        open_time=row[23],
                        close_time=row[24],
                        close_price=float(row[25] or 0),
                        close_reason=row[26] or "",
                        realized_pnl=float(row[27] or 0),
                    )
                    positions.append(pos)

                logger.info(f"{self.bot_name}: Found {len(positions)} partial_close positions")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get partial_close positions: {e}")

        return positions

    # =========================================================================
    # SIGNAL LOGGING
    # =========================================================================

    def log_signal(
        self,
        spot_price: float,
        vix: float,
        expected_move: float,
        call_wall: float,
        put_wall: float,
        gex_regime: str,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        total_credit: float,
        confidence: float,
        was_executed: bool,
        skip_reason: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> Optional[int]:
        """Log an Iron Condor signal"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO ares_signals (
                        spot_price, vix, expected_move, call_wall, put_wall,
                        gex_regime, put_short, put_long, call_short, call_long,
                        total_credit, confidence, was_executed, skip_reason, reasoning
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    _to_python(spot_price), _to_python(vix), _to_python(expected_move),
                    _to_python(call_wall), _to_python(put_wall),
                    gex_regime, _to_python(put_short), _to_python(put_long),
                    _to_python(call_short), _to_python(call_long),
                    _to_python(total_credit), _to_python(confidence),
                    was_executed, skip_reason, reasoning
                ))
                signal_id = c.fetchone()[0]
                conn.commit()
                return signal_id
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log signal: {e}")
            return None

    # =========================================================================
    # CONFIG & LOGGING
    # =========================================================================

    def load_config(self) -> ARESConfig:
        """Load config from database"""
        config = ARESConfig()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT config_key, config_value
                    FROM autonomous_config
                    WHERE bot_name = 'ARES'
                """)

                for key, value in c.fetchall():
                    if hasattr(config, key):
                        if key == 'mode':
                            setattr(config, key, TradingMode(value))
                        elif key == 'preset':
                            setattr(config, key, StrategyPreset(value))
                        elif isinstance(getattr(config, key), float):
                            setattr(config, key, float(value))
                        elif isinstance(getattr(config, key), int):
                            setattr(config, key, int(value))
                        elif isinstance(getattr(config, key), bool):
                            setattr(config, key, value.lower() == 'true')
                        else:
                            setattr(config, key, value)

                logger.info(f"{self.bot_name}: Loaded config from DB")
        except Exception as e:
            logger.warning(f"{self.bot_name}: Using default config: {e}")

        return config

    def log(self, level: str, message: str, details: Optional[Dict] = None) -> None:
        """Log to database"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                import json
                c.execute("""
                    INSERT INTO ares_logs (level, message, details)
                    VALUES (%s, %s, %s)
                """, (level, message, json.dumps(details) if details else None))
                conn.commit()
        except Exception as e:
            # Log silently but don't crash - logging failures shouldn't stop trading
            logger.debug(f"Failed to log to database: {e}")

    def log_orphaned_order(
        self,
        order_id: str,
        order_type: str,  # 'put_spread', 'call_spread', 'position'
        ticker: str,
        expiration: str,
        strikes: Dict[str, float],
        contracts: int,
        reason: str,
        error_details: str = None
    ) -> bool:
        """
        Log an orphaned order that requires manual intervention.

        Called when:
        - Put spread executes but call spread fails during IC open
        - Rollback of orphaned spread fails
        - Partial close leaves one leg in broker
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Ensure table exists
                c.execute("""
                    CREATE TABLE IF NOT EXISTS orphaned_orders (
                        id SERIAL PRIMARY KEY,
                        bot_name VARCHAR(20) NOT NULL,
                        order_id VARCHAR(50),
                        order_type VARCHAR(30) NOT NULL,
                        ticker VARCHAR(10) NOT NULL,
                        expiration DATE,
                        strikes JSONB,
                        contracts INTEGER,
                        reason VARCHAR(200) NOT NULL,
                        error_details TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolved_at TIMESTAMP WITH TIME ZONE,
                        resolved_by VARCHAR(50),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                import json
                c.execute("""
                    INSERT INTO orphaned_orders (
                        bot_name, order_id, order_type, ticker, expiration,
                        strikes, contracts, reason, error_details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    self.bot_name,
                    order_id,
                    order_type,
                    ticker,
                    expiration,
                    json.dumps(strikes),
                    contracts,
                    reason,
                    error_details
                ))
                orphan_id = c.fetchone()[0]
                conn.commit()

                logger.error(
                    f"{self.bot_name}: ORPHANED ORDER #{orphan_id} logged - "
                    f"{order_type} {order_id} ({reason}). REQUIRES MANUAL REVIEW."
                )
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log orphaned order: {e}")
            return False

    def update_heartbeat(self, status: str, action: str) -> None:
        """Update bot heartbeat"""
        try:
            import json
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
                    VALUES (%s, NOW(), %s, 1, %s)
                    ON CONFLICT (bot_name) DO UPDATE SET
                        last_heartbeat = NOW(),
                        status = EXCLUDED.status,
                        scan_count = bot_heartbeats.scan_count + 1,
                        details = EXCLUDED.details
                """, (self.bot_name, status, json.dumps({"last_action": action})))
                conn.commit()
        except Exception as e:
            # Heartbeat failures are non-critical
            logger.debug(f"Failed to update heartbeat: {e}")

    def update_daily_performance(self, summary: DailySummary) -> bool:
        """Update daily performance record"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO ares_daily_perf (
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

    def get_orphaned_orders(self, include_resolved: bool = False) -> List[Dict[str, Any]]:
        """Get orphaned orders that need manual intervention."""
        orders = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                if include_resolved:
                    c.execute("""
                        SELECT id, bot_name, order_id, ticker, expiration, strikes,
                               contracts, reason, error_details, resolved, resolved_at, created_at
                        FROM orphaned_orders
                        WHERE bot_name = %s
                        ORDER BY created_at DESC
                    """, (self.bot_name,))
                else:
                    c.execute("""
                        SELECT id, bot_name, order_id, ticker, expiration, strikes,
                               contracts, reason, error_details, resolved, resolved_at, created_at
                        FROM orphaned_orders
                        WHERE bot_name = %s AND resolved = FALSE
                        ORDER BY created_at DESC
                    """, (self.bot_name,))

                for row in c.fetchall():
                    orders.append({
                        'id': row[0],
                        'bot_name': row[1],
                        'order_id': row[2],
                        'ticker': row[3],
                        'expiration': str(row[4]) if row[4] else None,
                        'strikes': row[5],
                        'contracts': row[6],
                        'reason': row[7],
                        'error_details': row[8],
                        'resolved': row[9],
                        'resolved_at': row[10],
                        'created_at': row[11]
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get orphaned orders: {e}")

        return orders
