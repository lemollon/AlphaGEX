"""
FAITH - Database Layer
=====================

Single source of truth for all FAITH paper trading data.
Cloned from FORTRESS with FAITH-specific tables and paper account tracking.

Tables:
- faith_positions: Open and closed IC positions
- faith_signals: Generated trading signals
- faith_daily_perf: Daily performance summary
- faith_logs: Activity and decision logs
- faith_equity_snapshots: Equity curve data
- faith_paper_account: Paper account balance tracking
- faith_pdt_log: Pattern Day Trade tracking

All tables have a dte_mode column ('2DTE' or '1DTE') to support
side-by-side comparison of different DTE strategies.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from database_adapter import get_connection
from .models import (
    IronCondorPosition, PositionStatus,
    FaithConfig, TradingMode, PaperAccount,
    DailySummary, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


def _to_python(val):
    """Convert numpy types to native Python types for database insertion."""
    if val is None:
        return None
    type_name = type(val).__name__
    if 'float' in type_name or 'Float' in type_name:
        return float(val)
    if 'int' in type_name or 'Int' in type_name:
        return int(val)
    if 'bool' in type_name:
        return bool(val)
    if 'str' in type_name:
        return str(val)
    if hasattr(val, 'item'):
        return val.item()
    return val


@contextmanager
def db_connection():
    """Context manager for database connections."""
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


class FaithDatabase:
    """
    All FAITH database operations in one place.

    No SQL scattered throughout the codebase.
    """

    def __init__(self, bot_name: str = "FAITH", dte_mode: str = "2DTE"):
        """Initialize the database layer and ensure all tables exist."""
        self.bot_name = bot_name
        self.dte_mode = dte_mode
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure all required tables exist."""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Main positions table for Iron Condors
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_positions (
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
                        collateral_required DECIMAL(10, 2) DEFAULT 0,

                        -- Market context
                        underlying_at_entry DECIMAL(10, 2) NOT NULL,
                        vix_at_entry DECIMAL(6, 2),
                        expected_move DECIMAL(10, 2),
                        call_wall DECIMAL(10, 2),
                        put_wall DECIMAL(10, 2),
                        gex_regime VARCHAR(30),
                        flip_point DECIMAL(10, 2),
                        net_gex DECIMAL(15, 2),

                        -- Prophet/Oracle context
                        oracle_confidence DECIMAL(5, 4),
                        oracle_win_probability DECIMAL(8, 4),
                        oracle_advice VARCHAR(20),
                        oracle_reasoning TEXT,
                        oracle_top_factors TEXT,
                        oracle_use_gex_walls BOOLEAN DEFAULT FALSE,

                        -- Wing symmetry tracking
                        wings_adjusted BOOLEAN DEFAULT FALSE,
                        original_put_width DECIMAL(10, 2),
                        original_call_width DECIMAL(10, 2),

                        -- Order tracking (always PAPER for FAITH)
                        put_order_id VARCHAR(50) DEFAULT 'PAPER',
                        call_order_id VARCHAR(50) DEFAULT 'PAPER',

                        -- Status
                        status VARCHAR(20) NOT NULL DEFAULT 'open',
                        open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        open_date DATE,
                        close_time TIMESTAMP WITH TIME ZONE,
                        close_price DECIMAL(10, 4),
                        close_reason VARCHAR(100),
                        realized_pnl DECIMAL(10, 2),

                        -- DTE mode for 1DTE vs 2DTE comparison
                        dte_mode VARCHAR(5) DEFAULT '2DTE',

                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Signals table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_signals (
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
                        reasoning TEXT,
                        wings_adjusted BOOLEAN DEFAULT FALSE,
                        dte_mode VARCHAR(5) DEFAULT '2DTE'
                    )
                """)

                # Daily performance
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_daily_perf (
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
                    CREATE TABLE IF NOT EXISTS faith_logs (
                        id SERIAL PRIMARY KEY,
                        log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        level VARCHAR(10),
                        message TEXT,
                        details JSONB,
                        dte_mode VARCHAR(5) DEFAULT '2DTE'
                    )
                """)

                # Equity snapshots
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_equity_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        balance DECIMAL(12, 2) NOT NULL,
                        unrealized_pnl DECIMAL(12, 2) DEFAULT 0,
                        realized_pnl DECIMAL(12, 2) DEFAULT 0,
                        open_positions INTEGER DEFAULT 0,
                        note TEXT,
                        dte_mode VARCHAR(5) DEFAULT '2DTE',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Paper account tracking
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_paper_account (
                        id SERIAL PRIMARY KEY,
                        starting_capital DECIMAL(12, 2) NOT NULL,
                        current_balance DECIMAL(12, 2) NOT NULL,
                        cumulative_pnl DECIMAL(12, 2) DEFAULT 0,
                        total_trades INTEGER DEFAULT 0,
                        collateral_in_use DECIMAL(12, 2) DEFAULT 0,
                        buying_power DECIMAL(12, 2) NOT NULL,
                        high_water_mark DECIMAL(12, 2) NOT NULL,
                        max_drawdown DECIMAL(12, 2) DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        dte_mode VARCHAR(5) DEFAULT '2DTE',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # PDT day trade log
                c.execute("""
                    CREATE TABLE IF NOT EXISTS faith_pdt_log (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE NOT NULL,
                        symbol VARCHAR(10) NOT NULL,
                        position_id VARCHAR(50) NOT NULL,
                        opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        closed_at TIMESTAMP WITH TIME ZONE,
                        is_day_trade BOOLEAN DEFAULT FALSE,
                        contracts INTEGER NOT NULL,
                        entry_credit DECIMAL(10, 4),
                        exit_cost DECIMAL(10, 4),
                        pnl DECIMAL(10, 2),
                        close_reason VARCHAR(50),
                        dte_mode VARCHAR(5) DEFAULT '2DTE',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Create indexes
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_faith_positions_status
                    ON faith_positions(status)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_faith_positions_open_date
                    ON faith_positions(open_date)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_faith_pdt_log_date
                    ON faith_pdt_log(trade_date)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_faith_positions_dte_mode
                    ON faith_positions(dte_mode)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_faith_paper_account_dte_mode
                    ON faith_paper_account(dte_mode)
                """)

                # Add dte_mode column to existing tables if missing
                # and backfill NULL values to '2DTE' for pre-existing data
                for table in ['faith_positions', 'faith_signals', 'faith_logs',
                              'faith_equity_snapshots', 'faith_paper_account', 'faith_pdt_log']:
                    try:
                        c.execute(f"""
                            ALTER TABLE {table}
                            ADD COLUMN IF NOT EXISTS dte_mode VARCHAR(5) DEFAULT '2DTE'
                        """)
                        # Backfill any NULL values from before column was added
                        c.execute(f"""
                            UPDATE {table} SET dte_mode = '2DTE' WHERE dte_mode IS NULL
                        """)
                    except Exception:
                        pass  # Column already exists

                conn.commit()
                logger.info(f"{self.bot_name}: Database tables verified (dte_mode={self.dte_mode})")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to ensure tables: {e}")

    # =========================================================================
    # PAPER ACCOUNT OPERATIONS
    # =========================================================================

    def initialize_paper_account(self, starting_capital: float = 5000.0) -> bool:
        """Initialize paper trading account with starting capital."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Check if active account exists for this dte_mode
                c.execute("""
                    SELECT id FROM faith_paper_account
                    WHERE is_active = TRUE AND dte_mode = %s
                    LIMIT 1
                """, (self.dte_mode,))
                if c.fetchone():
                    logger.info(f"{self.bot_name}: Paper account already exists (dte_mode={self.dte_mode})")
                    return True

                c.execute("""
                    INSERT INTO faith_paper_account (
                        starting_capital, current_balance, cumulative_pnl,
                        buying_power, high_water_mark, dte_mode
                    ) VALUES (%s, %s, 0, %s, %s, %s)
                """, (starting_capital, starting_capital, starting_capital, starting_capital, self.dte_mode))
                conn.commit()
                logger.info(f"{self.bot_name}: Paper account initialized with ${starting_capital} (dte_mode={self.dte_mode})")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to initialize paper account: {e}")
            return False

    def get_paper_account(self) -> PaperAccount:
        """Get current paper account state."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT starting_capital, current_balance, cumulative_pnl,
                           total_trades, collateral_in_use, buying_power,
                           high_water_mark, max_drawdown, is_active
                    FROM faith_paper_account
                    WHERE is_active = TRUE AND dte_mode = %s
                    ORDER BY id DESC LIMIT 1
                """, (self.dte_mode,))
                row = c.fetchone()
                if row:
                    return PaperAccount(
                        starting_balance=float(row[0]),
                        balance=float(row[1]),
                        cumulative_pnl=float(row[2]),
                        total_trades=int(row[3]),
                        collateral_in_use=float(row[4]),
                        buying_power=float(row[5]),
                        high_water_mark=float(row[6]),
                        max_drawdown=float(row[7]),
                        is_active=bool(row[8]),
                    )
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get paper account: {e}")

        # Return default if not found
        return PaperAccount()

    def update_paper_balance(
        self,
        realized_pnl: float = 0,
        collateral_change: float = 0
    ) -> bool:
        """
        Update paper trading balance after a trade event.

        Args:
            realized_pnl: P&L from closing a trade (positive for profit, negative for loss)
            collateral_change: Change in collateral (positive = locked up, negative = released)
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT id, current_balance, cumulative_pnl, total_trades,
                           collateral_in_use, high_water_mark, max_drawdown, starting_capital
                    FROM faith_paper_account
                    WHERE is_active = TRUE AND dte_mode = %s
                    ORDER BY id DESC LIMIT 1
                """, (self.dte_mode,))
                row = c.fetchone()
                if not row:
                    logger.error(f"{self.bot_name}: No active paper account found (dte_mode={self.dte_mode})")
                    return False

                account_id = row[0]
                current_balance = float(row[1])
                cumulative_pnl = float(row[2])
                total_trades = int(row[3])
                collateral_in_use = float(row[4])
                high_water_mark = float(row[5])
                max_drawdown = float(row[6])

                # Update values
                new_balance = current_balance + realized_pnl
                new_cumulative_pnl = cumulative_pnl + realized_pnl
                new_collateral = max(0, collateral_in_use + collateral_change)
                new_buying_power = new_balance - new_collateral
                new_total_trades = total_trades + (1 if realized_pnl != 0 else 0)

                # Update high water mark and max drawdown
                new_hwm = max(high_water_mark, new_balance)
                current_dd = new_hwm - new_balance
                new_max_dd = max(max_drawdown, current_dd)

                c.execute("""
                    UPDATE faith_paper_account
                    SET current_balance = %s,
                        cumulative_pnl = %s,
                        total_trades = %s,
                        collateral_in_use = %s,
                        buying_power = %s,
                        high_water_mark = %s,
                        max_drawdown = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    new_balance, new_cumulative_pnl, new_total_trades,
                    new_collateral, new_buying_power, new_hwm, new_max_dd,
                    account_id
                ))
                conn.commit()

                logger.info(
                    f"{self.bot_name}: Paper account updated: "
                    f"balance=${new_balance:.2f}, P&L=${realized_pnl:.2f}, "
                    f"BP=${new_buying_power:.2f}, collateral=${new_collateral:.2f}"
                )
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update paper balance: {e}")
            return False

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    def get_open_positions(self) -> List[IronCondorPosition]:
        """Get all open positions from database."""
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
                        wings_adjusted, original_put_width, original_call_width,
                        put_order_id, call_order_id,
                        status, open_time, close_time, close_price, close_reason,
                        realized_pnl, collateral_required
                    FROM faith_positions
                    WHERE status = 'open' AND dte_mode = %s
                    ORDER BY open_time DESC
                """, (self.dte_mode,))

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
                        flip_point=float(row[20] or 0),
                        net_gex=float(row[21] or 0),
                        oracle_confidence=float(row[22] or 0),
                        oracle_win_probability=float(row[23] or 0),
                        oracle_advice=row[24] or "",
                        oracle_reasoning=row[25] or "",
                        oracle_top_factors=row[26] or "",
                        oracle_use_gex_walls=bool(row[27]),
                        wings_adjusted=bool(row[28]),
                        original_put_width=float(row[29] or 0),
                        original_call_width=float(row[30] or 0),
                        put_order_id=row[31] or "PAPER",
                        call_order_id=row[32] or "PAPER",
                        status=PositionStatus(row[33]),
                        open_time=row[34],
                        close_time=row[35],
                        close_price=float(row[36] or 0),
                        close_reason=row[37] or "",
                        realized_pnl=float(row[38] or 0),
                        collateral_required=float(row[39] or 0),
                    )
                    positions.append(pos)

                logger.debug(f"{self.bot_name}: Loaded {len(positions)} open positions")
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load positions: {e}")

        return positions

    def save_position(self, pos: IronCondorPosition) -> bool:
        """Save a new position to database."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_positions (
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        collateral_required,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        flip_point, net_gex,
                        oracle_confidence, oracle_win_probability, oracle_advice,
                        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
                        wings_adjusted, original_put_width, original_call_width,
                        put_order_id, call_order_id,
                        status, open_time, open_date, dte_mode
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    pos.position_id, pos.ticker, pos.expiration,
                    _to_python(pos.put_short_strike), _to_python(pos.put_long_strike),
                    _to_python(pos.put_credit),
                    _to_python(pos.call_short_strike), _to_python(pos.call_long_strike),
                    _to_python(pos.call_credit),
                    _to_python(pos.contracts), _to_python(pos.spread_width),
                    _to_python(pos.total_credit),
                    _to_python(pos.max_loss), _to_python(pos.max_profit),
                    _to_python(pos.collateral_required),
                    _to_python(pos.underlying_at_entry), _to_python(pos.vix_at_entry),
                    _to_python(pos.expected_move),
                    _to_python(pos.call_wall), _to_python(pos.put_wall),
                    pos.gex_regime or None,
                    _to_python(pos.flip_point), _to_python(pos.net_gex),
                    _to_python(pos.oracle_confidence), _to_python(pos.oracle_win_probability),
                    pos.oracle_advice or None,
                    pos.oracle_reasoning or None, pos.oracle_top_factors or None,
                    bool(pos.oracle_use_gex_walls),
                    bool(pos.wings_adjusted),
                    _to_python(pos.original_put_width), _to_python(pos.original_call_width),
                    pos.put_order_id or "PAPER", pos.call_order_id or "PAPER",
                    pos.status.value, pos.open_time,
                    pos.open_time.date() if pos.open_time else datetime.now(CENTRAL_TZ).date(),
                    self.dte_mode,
                ))
                conn.commit()
                logger.info(f"{self.bot_name}: Saved position {pos.position_id} (dte_mode={self.dte_mode})")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save position: {e}")
            import traceback
            traceback.print_exc()
            return False

    def close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str
    ) -> bool:
        """Close a position."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE faith_positions
                    SET status = 'closed',
                        close_time = NOW(),
                        close_price = %s,
                        realized_pnl = %s,
                        close_reason = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open' AND dte_mode = %s
                    RETURNING id
                """, (close_price, realized_pnl, close_reason, position_id, self.dte_mode))
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
        """Mark position as expired with final P&L."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE faith_positions
                    SET status = 'expired',
                        close_time = NOW(),
                        close_reason = 'EXPIRED',
                        close_price = %s,
                        realized_pnl = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND status = 'open' AND dte_mode = %s
                    RETURNING id
                """, (_to_python(close_price), _to_python(realized_pnl), position_id, self.dte_mode))
                result = c.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to expire position: {e}")
            return False

    def get_position_count(self) -> int:
        """Get count of open positions."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(
                    "SELECT COUNT(*) FROM faith_positions WHERE status = 'open' AND dte_mode = %s",
                    (self.dte_mode,)
                )
                return c.fetchone()[0]
        except Exception:
            return 0

    def has_traded_today(self, date: str) -> bool:
        """Check if FAITH has already traded today."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*)
                    FROM faith_positions
                    WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
                    AND dte_mode = %s
                """, (date, self.dte_mode))
                return c.fetchone()[0] > 0
        except Exception:
            return False

    def get_trades_today_count(self, date: str) -> int:
        """Get count of trades opened today."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*)
                    FROM faith_positions
                    WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
                    AND dte_mode = %s
                """, (date, self.dte_mode))
                return c.fetchone()[0]
        except Exception:
            return 0

    # =========================================================================
    # PDT TRACKING
    # =========================================================================

    def log_pdt_entry(
        self,
        position_id: str,
        symbol: str,
        opened_at: datetime,
        contracts: int,
        entry_credit: float
    ) -> bool:
        """Log a PDT entry when a position is opened."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_pdt_log (
                        trade_date, symbol, position_id, opened_at,
                        contracts, entry_credit, dte_mode
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    opened_at.date(), symbol, position_id,
                    opened_at, contracts, entry_credit, self.dte_mode
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log PDT entry: {e}")
            return False

    def update_pdt_close(
        self,
        position_id: str,
        closed_at: datetime,
        exit_cost: float,
        pnl: float,
        close_reason: str
    ) -> bool:
        """Update PDT log when a position is closed."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Determine if this is a day trade (opened and closed same calendar day)
                c.execute("""
                    UPDATE faith_pdt_log
                    SET closed_at = %s,
                        exit_cost = %s,
                        pnl = %s,
                        close_reason = %s,
                        is_day_trade = (DATE(opened_at::timestamptz AT TIME ZONE 'America/New_York')
                                     = DATE(%s::timestamptz AT TIME ZONE 'America/New_York'))
                    WHERE position_id = %s AND dte_mode = %s
                    RETURNING id
                """, (closed_at, exit_cost, pnl, close_reason, closed_at, position_id, self.dte_mode))
                result = c.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update PDT close: {e}")
            return False

    def get_day_trade_count_rolling_5_days(self) -> int:
        """
        Count day trades in the rolling 5 business day window.

        A day trade is a position that was opened and closed on the same calendar day.

        NOTE: This query skips weekends (DOW 0=Sun, 6=Sat) but does NOT account
        for market holidays (e.g., MLK Day, Presidents Day). On weeks with a
        holiday, the rolling window may be 1 day too short. This is a conservative
        error — it may block a legal trade but will never allow an illegal one.
        A future enhancement could integrate MarketCalendar for exact holiday handling.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Calculate 5 business days ago (approximately 7 calendar days)
                c.execute("""
                    SELECT COUNT(*)
                    FROM faith_pdt_log
                    WHERE is_day_trade = TRUE
                    AND dte_mode = %s
                    AND trade_date >= (
                        -- Get the date 5 business days ago
                        SELECT d::date
                        FROM generate_series(
                            CURRENT_DATE - INTERVAL '10 days',
                            CURRENT_DATE,
                            '1 day'::interval
                        ) d
                        WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
                        ORDER BY d DESC
                        LIMIT 1 OFFSET 4
                    )
                """, (self.dte_mode,))
                result = c.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT count: {e}")
            return 0

    def get_pdt_log(self, days: int = 10) -> List[Dict[str, Any]]:
        """Get recent PDT log entries."""
        entries = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT trade_date, symbol, position_id, opened_at, closed_at,
                           is_day_trade, contracts, entry_credit, exit_cost, pnl, close_reason
                    FROM faith_pdt_log
                    WHERE trade_date >= CURRENT_DATE - %s AND dte_mode = %s
                    ORDER BY opened_at DESC
                """, (days, self.dte_mode))
                for row in c.fetchall():
                    entries.append({
                        'trade_date': str(row[0]),
                        'symbol': row[1],
                        'position_id': row[2],
                        'opened_at': row[3].isoformat() if row[3] else None,
                        'closed_at': row[4].isoformat() if row[4] else None,
                        'is_day_trade': bool(row[5]) if row[5] is not None else False,
                        'contracts': row[6],
                        'entry_credit': float(row[7]) if row[7] else 0,
                        'exit_cost': float(row[8]) if row[8] else 0,
                        'pnl': float(row[9]) if row[9] else 0,
                        'close_reason': row[10],
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT log: {e}")
        return entries

    def get_next_pdt_reset_date(self) -> Optional[str]:
        """Get the date when the oldest day trade drops off the 5-day window."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Get the oldest day trade in the rolling window
                c.execute("""
                    SELECT MIN(trade_date)
                    FROM faith_pdt_log
                    WHERE is_day_trade = TRUE
                    AND dte_mode = %s
                    AND trade_date >= (
                        SELECT d::date
                        FROM generate_series(
                            CURRENT_DATE - INTERVAL '10 days',
                            CURRENT_DATE,
                            '1 day'::interval
                        ) d
                        WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
                        ORDER BY d DESC
                        LIMIT 1 OFFSET 4
                    )
                """, (self.dte_mode,))
                result = c.fetchone()
                if result and result[0]:
                    oldest_date = result[0]
                    # The reset date is 6 business days after the oldest day trade
                    reset_date = oldest_date
                    biz_days = 0
                    while biz_days < 6:
                        reset_date += timedelta(days=1)
                        if reset_date.weekday() < 5:
                            biz_days += 1
                    return str(reset_date)
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT reset date: {e}")
        return None

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
        reasoning: Optional[str] = None,
        wings_adjusted: bool = False,
    ) -> Optional[int]:
        """Log an Iron Condor signal."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_signals (
                        spot_price, vix, expected_move, call_wall, put_wall,
                        gex_regime, put_short, put_long, call_short, call_long,
                        total_credit, confidence, was_executed, skip_reason, reasoning,
                        wings_adjusted, dte_mode
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    _to_python(spot_price), _to_python(vix), _to_python(expected_move),
                    _to_python(call_wall), _to_python(put_wall),
                    gex_regime, _to_python(put_short), _to_python(put_long),
                    _to_python(call_short), _to_python(call_long),
                    _to_python(total_credit), _to_python(confidence),
                    was_executed, skip_reason, reasoning, wings_adjusted,
                    self.dte_mode
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

    def load_config(self) -> FaithConfig:
        """Load config from database or return defaults."""
        config = FaithConfig()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT key, value
                    FROM autonomous_config
                    WHERE key LIKE 'faith_%'
                """)
                for key, value in c.fetchall():
                    field_name = key.replace('faith_', '', 1)
                    if hasattr(config, field_name):
                        if field_name == 'mode':
                            setattr(config, field_name, TradingMode(value))
                        elif isinstance(getattr(config, field_name), float):
                            setattr(config, field_name, float(value))
                        elif isinstance(getattr(config, field_name), int):
                            setattr(config, field_name, int(value))
                        elif isinstance(getattr(config, field_name), bool):
                            setattr(config, field_name, value.lower() == 'true')
                        else:
                            setattr(config, field_name, value)

                logger.info(f"{self.bot_name}: Loaded config from DB")
        except Exception as e:
            logger.warning(f"{self.bot_name}: Using default config: {e}")

        return config

    def log(self, level: str, message: str, details: Optional[Dict] = None) -> None:
        """Log to database."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_logs (level, message, details, dte_mode)
                    VALUES (%s, %s, %s, %s)
                """, (level, message, json.dumps(details) if details else None, self.dte_mode))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to log to database: {e}")

    def update_heartbeat(self, status: str, action: str) -> None:
        """Update bot heartbeat."""
        try:
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
            logger.debug(f"Failed to update heartbeat: {e}")

    def get_heartbeat_info(self) -> Optional[Dict[str, Any]]:
        """Get heartbeat info for this bot from DB (scan_count, last_heartbeat, status)."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT scan_count, last_heartbeat, status, details
                    FROM bot_heartbeats WHERE bot_name = %s
                """, (self.bot_name,))
                row = c.fetchone()
                if row:
                    return {
                        'scan_count': row[0] or 0,
                        'last_heartbeat': row[1].isoformat() if row[1] else None,
                        'status': row[2],
                        'details': row[3],
                    }
        except Exception as e:
            logger.debug(f"Failed to get heartbeat info: {e}")
        return None

    def update_daily_performance(self, summary: DailySummary) -> bool:
        """Update daily performance record."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_daily_perf (
                        trade_date, trades_executed, positions_closed, realized_pnl
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        trades_executed = faith_daily_perf.trades_executed + EXCLUDED.trades_executed,
                        positions_closed = faith_daily_perf.positions_closed + EXCLUDED.positions_closed,
                        realized_pnl = faith_daily_perf.realized_pnl + EXCLUDED.realized_pnl,
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

    def save_equity_snapshot(
        self,
        balance: float,
        realized_pnl: float = 0,
        unrealized_pnl: float = 0,
        open_positions: int = 0,
        note: str = ""
    ) -> bool:
        """Save equity snapshot for equity curve tracking."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO faith_equity_snapshots
                    (timestamp, balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
                    VALUES (NOW(), %s, %s, %s, %s, %s, %s)
                """, (balance, realized_pnl, unrealized_pnl, open_positions, note, self.dte_mode))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save equity snapshot: {e}")
            return False

    def get_current_balance(self) -> float:
        """Get current balance from paper account."""
        account = self.get_paper_account()
        return account.balance

    # =========================================================================
    # TRADE HISTORY
    # =========================================================================

    def get_closed_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get closed/expired trade history."""
        trades = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike,
                        call_short_strike, call_long_strike,
                        contracts, spread_width, total_credit,
                        close_price, close_reason, realized_pnl,
                        open_time, close_time,
                        underlying_at_entry, vix_at_entry,
                        wings_adjusted, original_put_width, original_call_width
                    FROM faith_positions
                    WHERE status IN ('closed', 'expired') AND dte_mode = %s
                    ORDER BY close_time DESC
                    LIMIT %s
                """, (self.dte_mode, limit))

                for row in c.fetchall():
                    put_width = float(row[3]) - float(row[4])
                    call_width = float(row[6]) - float(row[5])
                    trades.append({
                        'position_id': row[0],
                        'ticker': row[1],
                        'expiration': str(row[2]),
                        'put_short_strike': float(row[3]),
                        'put_long_strike': float(row[4]),
                        'call_short_strike': float(row[5]),
                        'call_long_strike': float(row[6]),
                        'contracts': int(row[7]),
                        'spread_width': float(row[8]),
                        'total_credit': float(row[9]),
                        'close_price': float(row[10] or 0),
                        'close_reason': row[11] or '',
                        'realized_pnl': float(row[12] or 0),
                        'open_time': row[13].isoformat() if row[13] else None,
                        'close_time': row[14].isoformat() if row[14] else None,
                        'underlying_at_entry': float(row[15]),
                        'vix_at_entry': float(row[16] or 0),
                        'wings_adjusted': bool(row[17]),
                        'original_put_width': float(row[18] or 0),
                        'original_call_width': float(row[19] or 0),
                        'put_width': put_width,
                        'call_width': call_width,
                        'wings_symmetric': abs(put_width - call_width) < 0.01,
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get closed trades: {e}")
        return trades

    def get_performance_stats(self) -> Dict[str, Any]:
        """Calculate performance statistics from closed trades."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    WITH trades AS (
                        SELECT realized_pnl, close_reason, total_credit, contracts
                        FROM faith_positions
                        WHERE status IN ('closed', 'expired')
                        AND realized_pnl IS NOT NULL
                        AND dte_mode = %s
                    )
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(*) FILTER (WHERE realized_pnl > 0) as wins,
                        COUNT(*) FILTER (WHERE realized_pnl <= 0) as losses,
                        COALESCE(SUM(realized_pnl), 0) as total_pnl,
                        COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) as avg_win,
                        COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl <= 0), 0) as avg_loss,
                        COALESCE(MAX(realized_pnl), 0) as best_trade,
                        COALESCE(MIN(realized_pnl), 0) as worst_trade
                    FROM trades
                """, (self.dte_mode,))
                row = c.fetchone()
                if row:
                    total = int(row[0])
                    wins = int(row[1])
                    win_rate = (wins / total * 100) if total > 0 else 0
                    return {
                        'total_trades': total,
                        'wins': wins,
                        'losses': int(row[2]),
                        'win_rate': round(win_rate, 1),
                        'total_pnl': round(float(row[3]), 2),
                        'avg_win': round(float(row[4]), 2),
                        'avg_loss': round(float(row[5]), 2),
                        'best_trade': round(float(row[6]), 2),
                        'worst_trade': round(float(row[7]), 2),
                    }
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get performance stats: {e}")

        return {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
            'best_trade': 0, 'worst_trade': 0,
        }

    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Get historical equity curve from closed trades."""
        curve = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Get starting capital
                c.execute("""
                    SELECT starting_capital FROM faith_paper_account
                    WHERE is_active = TRUE AND dte_mode = %s LIMIT 1
                """, (self.dte_mode,))
                row = c.fetchone()
                starting_capital = float(row[0]) if row else 5000.0

                # Build cumulative P&L curve
                c.execute("""
                    SELECT
                        close_time,
                        realized_pnl,
                        SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
                    FROM faith_positions
                    WHERE status IN ('closed', 'expired')
                    AND realized_pnl IS NOT NULL
                    AND close_time IS NOT NULL
                    AND dte_mode = %s
                    ORDER BY close_time
                """, (self.dte_mode,))

                for row in c.fetchall():
                    curve.append({
                        'timestamp': row[0].isoformat() if row[0] else None,
                        'pnl': round(float(row[1]), 2),
                        'cumulative_pnl': round(float(row[2]), 2),
                        'equity': round(starting_capital + float(row[2]), 2),
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get equity curve: {e}")
        return curve

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent activity logs."""
        logs = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT log_time, level, message, details
                    FROM faith_logs
                    WHERE dte_mode = %s
                    ORDER BY log_time DESC
                    LIMIT %s
                """, (self.dte_mode, limit))
                for row in c.fetchall():
                    logs.append({
                        'timestamp': row[0].isoformat() if row[0] else None,
                        'level': row[1],
                        'message': row[2],
                        'details': row[3],
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get logs: {e}")
        return logs
