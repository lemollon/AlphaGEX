"""
ICARUS - Database Layer
========================

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
    ICARUSConfig, TradingMode, DailySummary, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


def _to_python(val):
    """Convert numpy types to native Python types for database insertion"""
    if val is None:
        return None
    type_name = type(val).__name__
    if 'float' in type_name or 'Float' in type_name:
        return float(val)
    if 'int' in type_name or 'Int' in type_name:
        return int(val)
    if 'bool' in type_name:
        return bool(val)
    if hasattr(val, 'item'):
        return val.item()
    return val


def _normalize_confidence(value) -> float:
    """
    Normalize confidence values to 0-1 range.

    Handles both decimal (0.75) and percentage (75) formats.
    Returns None if value is None/0.
    """
    if value is None:
        return None

    val = _to_python(value)
    if val is None or val == 0:
        return None

    val = float(val)

    # If value > 1, assume it's a percentage and convert
    if val > 1.0:
        val = val / 100.0

    # Clamp to valid range
    return max(0.0, min(1.0, val))


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


class ICARUSDatabase:
    """
    All ICARUS database operations in one place.

    No SQL scattered throughout the codebase.
    Clear, explicit methods for each operation.
    """

    def __init__(self, bot_name: str = "ICARUS"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure required tables exist"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Main positions table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS icarus_positions (
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
                        -- Kronos GEX context
                        flip_point DECIMAL(10, 2),
                        net_gex DECIMAL(15, 2),
                        -- Oracle/ML context (FULL audit trail)
                        oracle_confidence DECIMAL(8, 4),
                        oracle_advice VARCHAR(50),
                        ml_direction VARCHAR(20),
                        ml_confidence DECIMAL(8, 4),
                        ml_model_name VARCHAR(100),
                        ml_win_probability DECIMAL(8, 4),
                        ml_top_features TEXT,
                        -- Wall proximity context
                        wall_type VARCHAR(20),
                        wall_distance_pct DECIMAL(6, 4),
                        -- Trade reasoning
                        trade_reasoning TEXT,
                        -- Order tracking
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
                    CREATE TABLE IF NOT EXISTS icarus_signals (
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
                    CREATE TABLE IF NOT EXISTS icarus_daily_perf (
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
                    CREATE TABLE IF NOT EXISTS icarus_logs (
                        id SERIAL PRIMARY KEY,
                        log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        level VARCHAR(10),
                        message TEXT,
                        details JSONB
                    )
                """)

                conn.commit()

                # Ensure new ML/Kronos context columns exist (migration)
                self._ensure_ml_columns(c)
                conn.commit()

                logger.info(f"{self.bot_name}: Database tables verified")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to ensure tables: {e}")

    def _ensure_ml_columns(self, cursor) -> None:
        """
        Add new ML/Kronos context columns if they don't exist (migration).

        These columns provide FULL audit trail for trade decisions.
        """
        columns_to_add = [
            # Kronos GEX context
            ("flip_point", "DECIMAL(10, 2)"),
            ("net_gex", "DECIMAL(15, 2)"),
            # ML model context
            ("ml_model_name", "VARCHAR(100)"),
            ("ml_win_probability", "DECIMAL(8, 4)"),
            ("ml_top_features", "TEXT"),
            # Wall proximity context
            ("wall_type", "VARCHAR(20)"),
            ("wall_distance_pct", "DECIMAL(6, 4)"),
            # Full trade reasoning
            ("trade_reasoning", "TEXT"),
            # Oracle advice (for audit trail)
            ("oracle_advice", "VARCHAR(50)"),
            # Migration 023: Feedback loop enhancements
            ("oracle_prediction_id", "INTEGER"),  # Links to oracle_predictions.id
            ("direction_taken", "VARCHAR(10)"),   # BULLISH or BEARISH
        ]

        for col_name, col_type in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE icarus_positions
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """)
            except Exception as e:
                # Log but don't fail - column might already exist
                logger.debug(f"{self.bot_name}: Column migration {col_name}: {e}")

        # Widen confidence columns from DECIMAL(5,4) to DECIMAL(8,4) to handle percentage inputs
        columns_to_widen = [
            ("oracle_confidence", "DECIMAL(8, 4)"),
            ("ml_confidence", "DECIMAL(8, 4)"),
        ]

        for col_name, col_type in columns_to_widen:
            try:
                cursor.execute(f"""
                    ALTER TABLE icarus_positions
                    ALTER COLUMN {col_name} TYPE {col_type}
                """)
                logger.debug(f"{self.bot_name}: Widened column {col_name} to {col_type}")
            except Exception as e:
                # Column might already have correct type
                logger.debug(f"{self.bot_name}: Column type migration {col_name}: {e}")

    def update_oracle_prediction_id(self, position_id: str, oracle_prediction_id: int, direction_taken: str = None) -> bool:
        """
        Update the oracle_prediction_id for a position after Oracle prediction is stored.

        Migration 023: This links the position to the specific oracle prediction for
        accurate outcome tracking in the feedback loop.

        Args:
            position_id: The position to update
            oracle_prediction_id: The ID from oracle_predictions table
            direction_taken: BULLISH or BEARISH (for directional bots)
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE icarus_positions
                    SET oracle_prediction_id = %s,
                        direction_taken = COALESCE(%s, direction_taken),
                        updated_at = NOW()
                    WHERE position_id = %s
                """, (oracle_prediction_id, direction_taken, position_id))
                conn.commit()
                if c.rowcount > 0:
                    logger.info(f"{self.bot_name}: Linked position {position_id} to oracle_prediction_id={oracle_prediction_id}")
                    return True
                else:
                    logger.warning(f"{self.bot_name}: No position found to update: {position_id}")
                    return False
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update oracle_prediction_id: {e}")
            return False

    def get_oracle_prediction_id(self, position_id: str) -> int | None:
        """Get the oracle_prediction_id for a position (for outcome recording)."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT oracle_prediction_id
                    FROM icarus_positions
                    WHERE position_id = %s
                """, (position_id,))
                row = c.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get oracle_prediction_id: {e}")
            return None

    def get_direction_taken(self, position_id: str) -> str | None:
        """Get the direction_taken for a position (for direction accuracy tracking)."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT direction_taken
                    FROM icarus_positions
                    WHERE position_id = %s
                """, (position_id,))
                row = c.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get direction_taken: {e}")
            return None

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    def get_open_positions(self) -> List[SpreadPosition]:
        """
        Get ALL open positions from database with FULL context.

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
                        gex_regime, vix_at_entry,
                        flip_point, net_gex,
                        oracle_confidence, oracle_advice, ml_direction, ml_confidence,
                        ml_model_name, ml_win_probability, ml_top_features,
                        wall_type, wall_distance_pct, trade_reasoning,
                        order_id, status, open_time, close_time,
                        close_price, close_reason, realized_pnl
                    FROM icarus_positions
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
                        expiration=str(row[5]) if row[5] else "",
                        entry_debit=float(row[6]),
                        contracts=int(row[7]),
                        max_profit=float(row[8]),
                        max_loss=float(row[9]),
                        underlying_at_entry=float(row[10]),
                        call_wall=float(row[11] or 0),
                        put_wall=float(row[12] or 0),
                        gex_regime=row[13] or "",
                        vix_at_entry=float(row[14] or 0),
                        # Kronos context
                        flip_point=float(row[15] or 0),
                        net_gex=float(row[16] or 0),
                        # ML context (FULL audit trail)
                        oracle_confidence=float(row[17] or 0),
                        oracle_advice=row[18] or "",
                        ml_direction=row[19] or "",
                        ml_confidence=float(row[20] or 0),
                        ml_model_name=row[21] or "",
                        ml_win_probability=float(row[22] or 0),
                        ml_top_features=row[23] or "",
                        # Wall proximity context
                        wall_type=row[24] or "",
                        wall_distance_pct=float(row[25] or 0),
                        trade_reasoning=row[26] or "",
                        order_id=row[27] or "",
                        status=PositionStatus(row[28]),
                        open_time=row[29],
                        close_time=row[30],
                        close_price=float(row[31] or 0),
                        close_reason=row[32] or "",
                        realized_pnl=float(row[33] or 0),
                    )
                    positions.append(pos)

                logger.debug(f"{self.bot_name}: Loaded {len(positions)} open positions from DB")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load positions: {e}")

        return positions

    def save_position(self, pos: SpreadPosition) -> bool:
        """
        Save a new position to database with FULL context for audit trail.

        Returns True if successful, False otherwise.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO icarus_positions (
                        position_id, spread_type, ticker,
                        long_strike, short_strike, expiration,
                        entry_debit, contracts, max_profit, max_loss,
                        underlying_at_entry, call_wall, put_wall,
                        gex_regime, vix_at_entry,
                        flip_point, net_gex,
                        oracle_confidence, oracle_advice, ml_direction, ml_confidence,
                        ml_model_name, ml_win_probability, ml_top_features,
                        wall_type, wall_distance_pct, trade_reasoning,
                        order_id, status, open_time
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    pos.position_id,
                    pos.spread_type.value,
                    pos.ticker,
                    _to_python(pos.long_strike),
                    _to_python(pos.short_strike),
                    pos.expiration,
                    _to_python(pos.entry_debit),
                    _to_python(pos.contracts),
                    _to_python(pos.max_profit),
                    _to_python(pos.max_loss),
                    _to_python(pos.underlying_at_entry),
                    _to_python(pos.call_wall) if pos.call_wall else None,
                    _to_python(pos.put_wall) if pos.put_wall else None,
                    pos.gex_regime or None,
                    _to_python(pos.vix_at_entry) if pos.vix_at_entry else None,
                    # Kronos context
                    _to_python(pos.flip_point) if pos.flip_point else None,
                    _to_python(pos.net_gex) if pos.net_gex else None,
                    # ML context (FULL audit trail) - normalize confidence to 0-1 range
                    _normalize_confidence(pos.oracle_confidence),
                    pos.oracle_advice or None,
                    pos.ml_direction or None,
                    _normalize_confidence(pos.ml_confidence),
                    pos.ml_model_name or None,
                    _normalize_confidence(pos.ml_win_probability),
                    pos.ml_top_features or None,
                    # Wall proximity context
                    pos.wall_type or None,
                    _to_python(pos.wall_distance_pct) if pos.wall_distance_pct else None,
                    pos.trade_reasoning or None,
                    pos.order_id or None,
                    pos.status.value,
                    pos.open_time,
                ))
                conn.commit()
                logger.info(f"{self.bot_name}: Saved position {pos.position_id} to DB")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save position: {e}")
            import traceback
            logger.error(f"{self.bot_name}: Save position traceback: {traceback.format_exc()}")
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
                    UPDATE icarus_positions
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

    def expire_position(self, position_id: str, realized_pnl: float, close_price: float = None) -> bool:
        """Mark a position as expired with final P&L and close price"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE icarus_positions
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

    def get_position_count(self) -> int:
        """Get count of open positions - quick check without loading all data"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM icarus_positions WHERE status = 'open'")
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
                    FROM icarus_positions
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
                    INSERT INTO icarus_daily_perf (
                        trade_date, trades_executed, positions_closed, realized_pnl
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        trades_executed = icarus_daily_perf.trades_executed + EXCLUDED.trades_executed,
                        positions_closed = icarus_daily_perf.positions_closed + EXCLUDED.positions_closed,
                        realized_pnl = icarus_daily_perf.realized_pnl + EXCLUDED.realized_pnl,
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
    # EQUITY SNAPSHOTS - For real-time equity curve tracking
    # =========================================================================

    def save_equity_snapshot(
        self,
        balance: float,
        realized_pnl: float = 0,
        unrealized_pnl: float = 0,
        open_positions: int = 0,
        note: str = ""
    ) -> bool:
        """
        Save equity snapshot for equity curve tracking.

        Called after every trade open/close to ensure equity curve updates immediately.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS icarus_equity_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        balance DECIMAL(12, 2) NOT NULL,
                        unrealized_pnl DECIMAL(12, 2) DEFAULT 0,
                        realized_pnl DECIMAL(12, 2) DEFAULT 0,
                        open_positions INTEGER DEFAULT 0,
                        note TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                c.execute("""
                    INSERT INTO icarus_equity_snapshots
                    (timestamp, balance, realized_pnl, unrealized_pnl, open_positions, note)
                    VALUES (NOW(), %s, %s, %s, %s, %s)
                """, (balance, realized_pnl, unrealized_pnl, open_positions, note))
                conn.commit()
                logger.debug(f"{self.bot_name}: Equity snapshot saved: ${balance:.2f}")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save equity snapshot: {e}")
            return False

    def get_current_balance(self) -> float:
        """Get current balance from latest equity snapshot or config."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT balance FROM icarus_equity_snapshots
                    ORDER BY timestamp DESC LIMIT 1
                """)
                row = c.fetchone()
                if row:
                    return float(row[0])
        except Exception as e:
            logger.debug(f"{self.bot_name}: Could not get balance from snapshots: {e}")
        return 100000.0  # ICARUS default capital

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
                    INSERT INTO icarus_signals (
                        direction, spread_type, confidence, spot_price,
                        call_wall, put_wall, gex_regime, vix, rr_ratio,
                        was_executed, skip_reason, reasoning
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    direction, spread_type, _to_python(confidence), _to_python(spot_price),
                    _to_python(call_wall), _to_python(put_wall), gex_regime, _to_python(vix), _to_python(rr_ratio),
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

    def load_config(self) -> ICARUSConfig:
        """Load config from database, with defaults"""
        config = ICARUSConfig()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT config_key, config_value
                    FROM autonomous_config
                    WHERE bot_name = 'ICARUS'
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
                    INSERT INTO icarus_logs (level, message, details)
                    VALUES (%s, %s, %s)
                """, (level, message, json.dumps(details) if details else None))
                conn.commit()
        except Exception:
            pass  # Don't fail on logging errors

    def update_heartbeat(self, status: str, action: str) -> None:
        """Update bot heartbeat for monitoring"""
        try:
            import json
            with db_connection() as conn:
                c = conn.cursor()
                details = json.dumps({"last_action": action})
                c.execute("""
                    INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, details)
                    VALUES (%s, NOW(), %s, %s)
                    ON CONFLICT (bot_name) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_heartbeat = NOW(),
                        details = EXCLUDED.details
                """, (self.bot_name, status, details))
                conn.commit()
        except Exception:
            pass

    # =========================================================================
    # PARTIAL CLOSE AND ORPHANED ORDER TRACKING
    # =========================================================================

    def partial_close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str,
        closed_leg: str
    ) -> bool:
        """
        Mark a position as partially closed when one leg closes but other fails.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE icarus_positions
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
                    f"{close_reason} [PARTIAL: {closed_leg} leg closed]",
                    position_id
                ))
                result = c.fetchone()
                conn.commit()

                if result:
                    logger.warning(
                        f"{self.bot_name}: PARTIAL CLOSE - Position {position_id}, "
                        f"only {closed_leg} leg closed. Needs manual intervention."
                    )
                    return True
                return False
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to partial_close position: {e}")
            return False

    def get_partial_close_positions(self) -> List[SpreadPosition]:
        """Get positions in partial_close state that need manual intervention."""
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
                        gex_regime, vix_at_entry,
                        flip_point, net_gex,
                        oracle_confidence, oracle_advice, ml_direction, ml_confidence,
                        ml_model_name, ml_win_probability, ml_top_features,
                        wall_type, wall_distance_pct, trade_reasoning,
                        order_id, status, open_time, close_time,
                        close_price, close_reason, realized_pnl
                    FROM icarus_positions
                    WHERE status = 'partial_close'
                    ORDER BY COALESCE(close_time, open_time) DESC
                """)

                for row in c.fetchall():
                    pos = SpreadPosition(
                        position_id=row[0],
                        spread_type=SpreadType(row[1]),
                        ticker=row[2],
                        long_strike=float(row[3]),
                        short_strike=float(row[4]),
                        expiration=row[5].strftime("%Y-%m-%d") if row[5] else "",
                        entry_debit=float(row[6]),
                        contracts=int(row[7]),
                        max_profit=float(row[8]),
                        max_loss=float(row[9]),
                        underlying_at_entry=float(row[10]),
                        call_wall=float(row[11]) if row[11] else None,
                        put_wall=float(row[12]) if row[12] else None,
                        gex_regime=row[13] or "",
                        vix_at_entry=float(row[14]) if row[14] else None,
                        flip_point=float(row[15]) if row[15] else None,
                        net_gex=float(row[16]) if row[16] else None,
                        oracle_confidence=float(row[17]) if row[17] else None,
                        oracle_advice=row[18] or "",
                        ml_direction=row[19] or "",
                        ml_confidence=float(row[20]) if row[20] else None,
                        ml_model_name=row[21] or "",
                        ml_win_probability=float(row[22]) if row[22] else None,
                        ml_top_features=row[23] or "",
                        wall_type=row[24] or "",
                        wall_distance_pct=float(row[25]) if row[25] else None,
                        trade_reasoning=row[26] or "",
                        order_id=row[27] or "",
                        status=PositionStatus(row[28]),
                        open_time=row[29],
                        close_time=row[30],
                        close_price=float(row[31]) if row[31] else None,
                        close_reason=row[32] or "",
                        realized_pnl=float(row[33]) if row[33] else None,
                    )
                    positions.append(pos)

                logger.info(f"{self.bot_name}: Found {len(positions)} partial_close positions")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get partial_close positions: {e}")

        return positions

    def log_orphaned_order(
        self,
        order_id: str,
        position_id: str,
        order_type: str,
        details: str,
        action_required: str
    ) -> bool:
        """Log an orphaned order that requires manual intervention."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Ensure table exists
                c.execute("""
                    CREATE TABLE IF NOT EXISTS orphaned_orders (
                        id SERIAL PRIMARY KEY,
                        bot_name VARCHAR(20) NOT NULL,
                        order_id VARCHAR(50) NOT NULL,
                        position_id VARCHAR(50),
                        order_type VARCHAR(50) NOT NULL,
                        details TEXT,
                        action_required TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolved_at TIMESTAMP,
                        resolved_by VARCHAR(100),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                c.execute("""
                    INSERT INTO orphaned_orders (
                        bot_name, order_id, position_id, order_type, details, action_required
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    self.bot_name,
                    order_id,
                    position_id,
                    order_type,
                    details,
                    action_required
                ))
                conn.commit()
                logger.critical(
                    f"{self.bot_name}: ORPHANED ORDER LOGGED - Order {order_id}, "
                    f"Position {position_id}. ACTION: {action_required}"
                )
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log orphaned order: {e}")
            return False

    def get_orphaned_orders(self, include_resolved: bool = False) -> List[Dict]:
        """Get orphaned orders that need manual intervention."""
        orders = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                if include_resolved:
                    c.execute("""
                        SELECT id, bot_name, order_id, position_id, order_type,
                               details, action_required, resolved, resolved_at, created_at
                        FROM orphaned_orders
                        WHERE bot_name = %s
                        ORDER BY created_at DESC
                    """, (self.bot_name,))
                else:
                    c.execute("""
                        SELECT id, bot_name, order_id, position_id, order_type,
                               details, action_required, resolved, resolved_at, created_at
                        FROM orphaned_orders
                        WHERE bot_name = %s AND resolved = FALSE
                        ORDER BY created_at DESC
                    """, (self.bot_name,))

                for row in c.fetchall():
                    orders.append({
                        'id': row[0],
                        'bot_name': row[1],
                        'order_id': row[2],
                        'position_id': row[3],
                        'order_type': row[4],
                        'details': row[5],
                        'action_required': row[6],
                        'resolved': row[7],
                        'resolved_at': row[8],
                        'created_at': row[9]
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get orphaned orders: {e}")

        return orders
