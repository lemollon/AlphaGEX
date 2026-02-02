"""
HERACLES - Database Layer
=========================

SINGLE SOURCE OF TRUTH for all position and trade data.
MES Futures Scalping Bot using GEX signals.

Design principles:
1. Database is THE source of truth - never trust in-memory state
2. Every operation syncs with DB before acting
3. All DB operations in ONE place - no scattered SQL
4. Explicit error handling with clear return values
"""

import logging
import json
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager
from decimal import Decimal

from database_adapter import get_connection
from .models import (
    FuturesPosition, TradeDirection, GammaRegime, PositionStatus,
    SignalSource, HERACLESConfig, TradingMode, DailySummary,
    BayesianWinTracker, FuturesSignal, CENTRAL_TZ, MES_POINT_VALUE
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
    if isinstance(val, Decimal):
        return float(val)
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


class HERACLESDatabase:
    """
    All HERACLES database operations in one place.

    No SQL scattered throughout the codebase.
    Clear, explicit methods for each operation.
    """

    def __init__(self, bot_name: str = "HERACLES"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure required tables exist"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Main positions table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_positions (
                        id SERIAL PRIMARY KEY,
                        position_id VARCHAR(50) UNIQUE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        direction VARCHAR(10) NOT NULL,
                        contracts INTEGER NOT NULL,
                        entry_price DECIMAL(12, 4) NOT NULL,
                        entry_value DECIMAL(12, 2) NOT NULL,
                        initial_stop DECIMAL(12, 4) NOT NULL,
                        current_stop DECIMAL(12, 4) NOT NULL,
                        breakeven_price DECIMAL(12, 4),
                        trailing_active BOOLEAN DEFAULT FALSE,
                        gamma_regime VARCHAR(20),
                        gex_value DECIMAL(18, 4),
                        flip_point DECIMAL(12, 4),
                        call_wall DECIMAL(12, 4),
                        put_wall DECIMAL(12, 4),
                        vix_at_entry DECIMAL(6, 2),
                        atr_at_entry DECIMAL(10, 4),
                        signal_source VARCHAR(30),
                        signal_confidence DECIMAL(5, 4),
                        win_probability DECIMAL(5, 4),
                        trade_reasoning TEXT,
                        order_id VARCHAR(100),
                        status VARCHAR(20) NOT NULL DEFAULT 'open',
                        open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        close_time TIMESTAMP WITH TIME ZONE,
                        close_price DECIMAL(12, 4),
                        close_reason VARCHAR(100),
                        realized_pnl DECIMAL(12, 2),
                        high_water_mark DECIMAL(12, 4),
                        max_adverse_excursion DECIMAL(12, 4),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Closed trades history (for permanent record)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_closed_trades (
                        id SERIAL PRIMARY KEY,
                        position_id VARCHAR(50) UNIQUE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        direction VARCHAR(10) NOT NULL,
                        contracts INTEGER NOT NULL,
                        entry_price DECIMAL(12, 4) NOT NULL,
                        exit_price DECIMAL(12, 4) NOT NULL,
                        realized_pnl DECIMAL(12, 2) NOT NULL,
                        gamma_regime VARCHAR(20),
                        signal_source VARCHAR(30),
                        signal_confidence DECIMAL(5, 4),
                        win_probability DECIMAL(5, 4),
                        vix_at_entry DECIMAL(6, 2),
                        atr_at_entry DECIMAL(10, 4),
                        close_reason VARCHAR(100),
                        trade_reasoning TEXT,
                        open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        close_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        hold_duration_minutes INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Signals history
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_signals (
                        id SERIAL PRIMARY KEY,
                        signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        direction VARCHAR(10) NOT NULL,
                        source VARCHAR(30) NOT NULL,
                        confidence DECIMAL(5, 4),
                        current_price DECIMAL(12, 4),
                        gamma_regime VARCHAR(20),
                        gex_value DECIMAL(18, 4),
                        flip_point DECIMAL(12, 4),
                        call_wall DECIMAL(12, 4),
                        put_wall DECIMAL(12, 4),
                        vix DECIMAL(6, 2),
                        atr DECIMAL(10, 4),
                        win_probability DECIMAL(5, 4),
                        contracts INTEGER,
                        was_executed BOOLEAN DEFAULT FALSE,
                        skip_reason VARCHAR(200),
                        reasoning TEXT
                    )
                """)

                # Equity snapshots for equity curve
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_equity_snapshots (
                        id SERIAL PRIMARY KEY,
                        snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        account_balance DECIMAL(12, 2) NOT NULL,
                        unrealized_pnl DECIMAL(12, 2) DEFAULT 0,
                        realized_pnl_today DECIMAL(12, 2) DEFAULT 0,
                        open_positions INTEGER DEFAULT 0,
                        trades_today INTEGER DEFAULT 0,
                        wins_today INTEGER DEFAULT 0,
                        losses_today INTEGER DEFAULT 0
                    )
                """)

                # Configuration table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_config (
                        id SERIAL PRIMARY KEY,
                        config_key VARCHAR(50) UNIQUE NOT NULL,
                        config_value TEXT,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Win tracker for Bayesian probability
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_win_tracker (
                        id SERIAL PRIMARY KEY,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        alpha DECIMAL(10, 4) DEFAULT 1.0,
                        beta DECIMAL(10, 4) DEFAULT 1.0,
                        total_trades INTEGER DEFAULT 0,
                        positive_gamma_wins INTEGER DEFAULT 0,
                        positive_gamma_losses INTEGER DEFAULT 0,
                        negative_gamma_wins INTEGER DEFAULT 0,
                        negative_gamma_losses INTEGER DEFAULT 0
                    )
                """)

                # Activity logs
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_logs (
                        id SERIAL PRIMARY KEY,
                        log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        level VARCHAR(10),
                        action VARCHAR(50),
                        message TEXT,
                        details JSONB
                    )
                """)

                # Daily performance
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_daily_perf (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE UNIQUE NOT NULL,
                        trades_executed INTEGER DEFAULT 0,
                        positions_closed INTEGER DEFAULT 0,
                        realized_pnl DECIMAL(12, 2) DEFAULT 0,
                        positive_gamma_trades INTEGER DEFAULT 0,
                        negative_gamma_trades INTEGER DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Paper trading account - tracks virtual balance for simulation
                c.execute("""
                    CREATE TABLE IF NOT EXISTS heracles_paper_account (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        starting_capital DECIMAL(12, 2) NOT NULL DEFAULT 100000.00,
                        current_balance DECIMAL(12, 2) NOT NULL DEFAULT 100000.00,
                        cumulative_pnl DECIMAL(12, 2) DEFAULT 0.00,
                        total_trades INTEGER DEFAULT 0,
                        margin_used DECIMAL(12, 2) DEFAULT 0.00,
                        margin_available DECIMAL(12, 2) DEFAULT 100000.00,
                        high_water_mark DECIMAL(12, 2) DEFAULT 100000.00,
                        max_drawdown DECIMAL(12, 2) DEFAULT 0.00,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)

                # Create indexes for performance
                c.execute("CREATE INDEX IF NOT EXISTS idx_heracles_positions_status ON heracles_positions(status)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_heracles_closed_trades_close_time ON heracles_closed_trades(close_time)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_heracles_equity_snapshots_time ON heracles_equity_snapshots(snapshot_time)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_heracles_signals_time ON heracles_signals(signal_time)")

                conn.commit()
                logger.info("HERACLES database tables ensured")

        except Exception as e:
            logger.error(f"Failed to ensure HERACLES tables: {e}")

    # ========================================================================
    # Position Operations
    # ========================================================================

    def save_position(self, position: FuturesPosition) -> bool:
        """Save a position to database (insert or update)"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                c.execute("""
                    INSERT INTO heracles_positions (
                        position_id, symbol, direction, contracts,
                        entry_price, entry_value, initial_stop, current_stop,
                        breakeven_price, trailing_active, gamma_regime, gex_value,
                        flip_point, call_wall, put_wall, vix_at_entry, atr_at_entry,
                        signal_source, signal_confidence, win_probability, trade_reasoning,
                        order_id, status, open_time, close_time, close_price,
                        close_reason, realized_pnl, high_water_mark, max_adverse_excursion
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (position_id) DO UPDATE SET
                        current_stop = EXCLUDED.current_stop,
                        trailing_active = EXCLUDED.trailing_active,
                        status = EXCLUDED.status,
                        close_time = EXCLUDED.close_time,
                        close_price = EXCLUDED.close_price,
                        close_reason = EXCLUDED.close_reason,
                        realized_pnl = EXCLUDED.realized_pnl,
                        high_water_mark = EXCLUDED.high_water_mark,
                        max_adverse_excursion = EXCLUDED.max_adverse_excursion,
                        updated_at = NOW()
                """, (
                    position.position_id,
                    position.symbol,
                    position.direction.value,
                    position.contracts,
                    _to_python(position.entry_price),
                    _to_python(position.entry_value),
                    _to_python(position.initial_stop),
                    _to_python(position.current_stop),
                    _to_python(position.breakeven_price),
                    position.trailing_active,
                    position.gamma_regime.value,
                    _to_python(position.gex_value),
                    _to_python(position.flip_point),
                    _to_python(position.call_wall),
                    _to_python(position.put_wall),
                    _to_python(position.vix_at_entry),
                    _to_python(position.atr_at_entry),
                    position.signal_source.value,
                    _to_python(position.signal_confidence),
                    _to_python(position.win_probability),
                    position.trade_reasoning,
                    position.order_id,
                    position.status.value,
                    position.open_time,
                    position.close_time,
                    _to_python(position.close_price),
                    position.close_reason,
                    _to_python(position.realized_pnl),
                    _to_python(position.high_water_mark),
                    _to_python(position.max_adverse_excursion),
                ))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to save position {position.position_id}: {e}")
            return False

    def get_open_positions(self) -> List[FuturesPosition]:
        """Get all open positions"""
        positions = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM heracles_positions WHERE status = 'open'
                    ORDER BY open_time DESC
                """)

                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    data = dict(zip(columns, row))
                    position = self._row_to_position(data)
                    positions.append(position)

        except Exception as e:
            logger.error(f"Failed to get open positions: {e}")

        return positions

    def get_position_by_id(self, position_id: str) -> Optional[FuturesPosition]:
        """Get a specific position by ID"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM heracles_positions WHERE position_id = %s
                """, (position_id,))

                row = c.fetchone()
                if row:
                    columns = [desc[0] for desc in c.description]
                    data = dict(zip(columns, row))
                    return self._row_to_position(data)

        except Exception as e:
            logger.error(f"Failed to get position {position_id}: {e}")

        return None

    def close_position(
        self,
        position_id: str,
        close_price: float,
        close_reason: str,
        status: PositionStatus = PositionStatus.CLOSED
    ) -> Tuple[bool, float]:
        """
        Close a position and calculate P&L.

        Returns: (success, realized_pnl)
        """
        try:
            position = self.get_position_by_id(position_id)
            if not position:
                return False, 0.0

            # Calculate P&L
            realized_pnl = position.calculate_pnl(close_price)

            with db_connection() as conn:
                c = conn.cursor()
                now = datetime.now(CENTRAL_TZ)

                # Update position
                c.execute("""
                    UPDATE heracles_positions
                    SET status = %s, close_time = %s, close_price = %s,
                        close_reason = %s, realized_pnl = %s, updated_at = NOW()
                    WHERE position_id = %s
                """, (
                    status.value, now, _to_python(close_price),
                    close_reason, _to_python(realized_pnl), position_id
                ))

                # Insert into closed trades for permanent record
                hold_duration = int((now - position.open_time).total_seconds() / 60) if position.open_time else 0

                c.execute("""
                    INSERT INTO heracles_closed_trades (
                        position_id, symbol, direction, contracts,
                        entry_price, exit_price, realized_pnl, gamma_regime,
                        signal_source, signal_confidence, win_probability,
                        vix_at_entry, atr_at_entry, close_reason, trade_reasoning,
                        open_time, close_time, hold_duration_minutes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (position_id) DO NOTHING
                """, (
                    position_id, position.symbol, position.direction.value,
                    position.contracts, _to_python(position.entry_price),
                    _to_python(close_price), _to_python(realized_pnl),
                    position.gamma_regime.value, position.signal_source.value,
                    _to_python(position.signal_confidence), _to_python(position.win_probability),
                    _to_python(position.vix_at_entry), _to_python(position.atr_at_entry),
                    close_reason, position.trade_reasoning,
                    position.open_time, now, hold_duration
                ))

                conn.commit()
                logger.info(f"Closed position {position_id}: P&L=${realized_pnl:.2f}, reason={close_reason}")
                return True, realized_pnl

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            return False, 0.0

    def update_stop(self, position_id: str, new_stop: float, trailing_active: bool = False) -> bool:
        """Update position stop price"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE heracles_positions
                    SET current_stop = %s, trailing_active = %s, updated_at = NOW()
                    WHERE position_id = %s
                """, (_to_python(new_stop), trailing_active, position_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update stop for {position_id}: {e}")
            return False

    def _row_to_position(self, data: Dict) -> FuturesPosition:
        """Convert database row to FuturesPosition"""
        return FuturesPosition(
            position_id=data['position_id'],
            symbol=data['symbol'],
            direction=TradeDirection(data['direction']),
            contracts=data['contracts'],
            entry_price=float(data['entry_price']),
            entry_value=float(data['entry_value']),
            initial_stop=float(data['initial_stop']),
            current_stop=float(data['current_stop']),
            breakeven_price=float(data.get('breakeven_price') or 0),
            trailing_active=data.get('trailing_active', False),
            gamma_regime=GammaRegime(data.get('gamma_regime', 'NEUTRAL')),
            gex_value=float(data.get('gex_value') or 0),
            flip_point=float(data.get('flip_point') or 0),
            call_wall=float(data.get('call_wall') or 0),
            put_wall=float(data.get('put_wall') or 0),
            vix_at_entry=float(data.get('vix_at_entry') or 0),
            atr_at_entry=float(data.get('atr_at_entry') or 0),
            signal_source=SignalSource(data.get('signal_source', 'GEX_MEAN_REVERSION')),
            signal_confidence=float(data.get('signal_confidence') or 0),
            win_probability=float(data.get('win_probability') or 0),
            trade_reasoning=data.get('trade_reasoning', ''),
            order_id=data.get('order_id', ''),
            status=PositionStatus(data['status']),
            open_time=data['open_time'],
            close_time=data.get('close_time'),
            close_price=float(data.get('close_price') or 0),
            close_reason=data.get('close_reason', ''),
            realized_pnl=float(data.get('realized_pnl') or 0),
            high_water_mark=float(data.get('high_water_mark') or 0),
            max_adverse_excursion=float(data.get('max_adverse_excursion') or 0),
        )

    # ========================================================================
    # Trade History
    # ========================================================================

    def get_closed_trades(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get closed trades history"""
        trades = []
        try:
            with db_connection() as conn:
                c = conn.cursor()

                query = "SELECT * FROM heracles_closed_trades WHERE 1=1"
                params = []

                if start_date:
                    query += " AND close_time >= %s"
                    params.append(start_date)
                if end_date:
                    query += " AND close_time <= %s"
                    params.append(end_date)

                query += " ORDER BY close_time DESC LIMIT %s"
                params.append(limit)

                c.execute(query, params)
                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    trade = dict(zip(columns, row))
                    # Convert datetime to string for JSON
                    for key in ['open_time', 'close_time', 'created_at']:
                        if trade.get(key) and hasattr(trade[key], 'isoformat'):
                            trade[key] = trade[key].isoformat()
                    trades.append(trade)

        except Exception as e:
            logger.error(f"Failed to get closed trades: {e}")

        return trades

    # ========================================================================
    # Equity Curve
    # ========================================================================

    def save_equity_snapshot(
        self,
        account_balance: float,
        unrealized_pnl: float = 0,
        realized_pnl_today: float = 0,
        open_positions: int = 0,
        trades_today: int = 0,
        wins_today: int = 0,
        losses_today: int = 0
    ) -> bool:
        """Save equity snapshot for equity curve"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO heracles_equity_snapshots (
                        account_balance, unrealized_pnl, realized_pnl_today,
                        open_positions, trades_today, wins_today, losses_today
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    _to_python(account_balance), _to_python(unrealized_pnl),
                    _to_python(realized_pnl_today), open_positions,
                    trades_today, wins_today, losses_today
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save equity snapshot: {e}")
            return False

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        """Get equity curve data"""
        data = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT snapshot_time, account_balance, unrealized_pnl,
                           realized_pnl_today, open_positions
                    FROM heracles_equity_snapshots
                    WHERE snapshot_time >= NOW() - INTERVAL '%s days'
                    ORDER BY snapshot_time ASC
                """, (days,))

                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    point = dict(zip(columns, row))
                    if point.get('snapshot_time') and hasattr(point['snapshot_time'], 'isoformat'):
                        point['snapshot_time'] = point['snapshot_time'].isoformat()
                    data.append(point)

        except Exception as e:
            logger.error(f"Failed to get equity curve: {e}")

        return data

    def get_intraday_equity(self) -> List[Dict]:
        """Get today's equity snapshots"""
        data = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT snapshot_time, account_balance, unrealized_pnl,
                           realized_pnl_today, open_positions, trades_today
                    FROM heracles_equity_snapshots
                    WHERE DATE(snapshot_time AT TIME ZONE 'America/Chicago') =
                          DATE(NOW() AT TIME ZONE 'America/Chicago')
                    ORDER BY snapshot_time ASC
                """)

                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    point = dict(zip(columns, row))
                    if point.get('snapshot_time') and hasattr(point['snapshot_time'], 'isoformat'):
                        point['snapshot_time'] = point['snapshot_time'].isoformat()
                    data.append(point)

        except Exception as e:
            logger.error(f"Failed to get intraday equity: {e}")

        return data

    # ========================================================================
    # Configuration
    # ========================================================================

    def get_config(self) -> HERACLESConfig:
        """Load configuration from database"""
        config = HERACLESConfig()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT config_key, config_value FROM heracles_config")
                rows = c.fetchall()

                config_dict = {}
                for key, value in rows:
                    # Try to parse JSON, fall back to string
                    try:
                        config_dict[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        config_dict[key] = value

                config = HERACLESConfig.from_dict(config_dict)

        except Exception as e:
            logger.warning(f"Failed to load config, using defaults: {e}")

        return config

    def save_config(self, config: HERACLESConfig) -> bool:
        """Save configuration to database"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Save each config field
                config_dict = {
                    'capital': config.capital,
                    'risk_per_trade_pct': config.risk_per_trade_pct,
                    'max_contracts': config.max_contracts,
                    'max_open_positions': config.max_open_positions,
                    'symbol': config.symbol,
                    'initial_stop_points': config.initial_stop_points,
                    'breakeven_activation_points': config.breakeven_activation_points,
                    'trailing_stop_points': config.trailing_stop_points,
                    'min_win_probability': config.min_win_probability,
                    'mode': config.mode.value,
                    'account_id': config.account_id,
                }

                for key, value in config_dict.items():
                    c.execute("""
                        INSERT INTO heracles_config (config_key, config_value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (config_key) DO UPDATE SET
                            config_value = EXCLUDED.config_value,
                            updated_at = NOW()
                    """, (key, json.dumps(value) if not isinstance(value, str) else value))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    # ========================================================================
    # Win Probability Tracker
    # ========================================================================

    def get_win_tracker(self) -> BayesianWinTracker:
        """Load Bayesian win tracker from database"""
        tracker = BayesianWinTracker()
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM heracles_win_tracker ORDER BY id DESC LIMIT 1
                """)
                row = c.fetchone()

                if row:
                    columns = [desc[0] for desc in c.description]
                    data = dict(zip(columns, row))
                    tracker = BayesianWinTracker(
                        alpha=float(data.get('alpha', 1.0)),
                        beta=float(data.get('beta', 1.0)),
                        total_trades=int(data.get('total_trades', 0)),
                        positive_gamma_wins=int(data.get('positive_gamma_wins', 0)),
                        positive_gamma_losses=int(data.get('positive_gamma_losses', 0)),
                        negative_gamma_wins=int(data.get('negative_gamma_wins', 0)),
                        negative_gamma_losses=int(data.get('negative_gamma_losses', 0)),
                    )

        except Exception as e:
            logger.warning(f"Failed to load win tracker, using defaults: {e}")

        return tracker

    def save_win_tracker(self, tracker: BayesianWinTracker) -> bool:
        """Save win tracker to database"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO heracles_win_tracker (
                        alpha, beta, total_trades,
                        positive_gamma_wins, positive_gamma_losses,
                        negative_gamma_wins, negative_gamma_losses
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    tracker.alpha, tracker.beta, tracker.total_trades,
                    tracker.positive_gamma_wins, tracker.positive_gamma_losses,
                    tracker.negative_gamma_wins, tracker.negative_gamma_losses
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save win tracker: {e}")
            return False

    # ========================================================================
    # Signals
    # ========================================================================

    def save_signal(self, signal: FuturesSignal, was_executed: bool, skip_reason: str = "") -> bool:
        """Save a trading signal"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO heracles_signals (
                        direction, source, confidence, current_price,
                        gamma_regime, gex_value, flip_point, call_wall, put_wall,
                        vix, atr, win_probability, contracts,
                        was_executed, skip_reason, reasoning
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    signal.direction.value,
                    signal.source.value,
                    _to_python(signal.confidence),
                    _to_python(signal.current_price),
                    signal.gamma_regime.value,
                    _to_python(signal.gex_value),
                    _to_python(signal.flip_point),
                    _to_python(signal.call_wall),
                    _to_python(signal.put_wall),
                    _to_python(signal.vix),
                    _to_python(signal.atr),
                    _to_python(signal.win_probability),
                    signal.contracts,
                    was_executed,
                    skip_reason,
                    signal.reasoning
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return False

    def get_recent_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals"""
        signals = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM heracles_signals
                    ORDER BY signal_time DESC
                    LIMIT %s
                """, (limit,))

                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    signal = dict(zip(columns, row))
                    if signal.get('signal_time') and hasattr(signal['signal_time'], 'isoformat'):
                        signal['signal_time'] = signal['signal_time'].isoformat()
                    signals.append(signal)

        except Exception as e:
            logger.error(f"Failed to get recent signals: {e}")

        return signals

    # ========================================================================
    # Logging
    # ========================================================================

    def log(self, level: str, action: str, message: str, details: Optional[Dict] = None) -> bool:
        """Log an activity"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO heracles_logs (level, action, message, details)
                    VALUES (%s, %s, %s, %s)
                """, (level, action, message, json.dumps(details) if details else None))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to log: {e}")
            return False

    def get_logs(self, limit: int = 100, level: Optional[str] = None) -> List[Dict]:
        """Get recent logs"""
        logs = []
        try:
            with db_connection() as conn:
                c = conn.cursor()

                query = "SELECT * FROM heracles_logs"
                params = []

                if level:
                    query += " WHERE level = %s"
                    params.append(level)

                query += " ORDER BY log_time DESC LIMIT %s"
                params.append(limit)

                c.execute(query, params)
                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]

                for row in rows:
                    log = dict(zip(columns, row))
                    if log.get('log_time') and hasattr(log['log_time'], 'isoformat'):
                        log['log_time'] = log['log_time'].isoformat()
                    logs.append(log)

        except Exception as e:
            logger.error(f"Failed to get logs: {e}")

        return logs

    # ========================================================================
    # Performance Stats
    # ========================================================================

    def get_performance_stats(self) -> Dict:
        """Get overall performance statistics"""
        stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'positive_gamma_stats': {},
            'negative_gamma_stats': {},
        }

        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Overall stats
                c.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
                        SUM(realized_pnl) as total_pnl,
                        AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
                        AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END) as avg_loss,
                        MAX(realized_pnl) as best_trade,
                        MIN(realized_pnl) as worst_trade,
                        SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as gross_profit,
                        ABS(SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END)) as gross_loss
                    FROM heracles_closed_trades
                """)

                row = c.fetchone()
                if row:
                    stats['total_trades'] = row[0] or 0
                    stats['winning_trades'] = row[1] or 0
                    stats['losing_trades'] = row[2] or 0
                    stats['total_pnl'] = float(row[3] or 0)
                    stats['avg_win'] = float(row[4] or 0)
                    stats['avg_loss'] = float(row[5] or 0)
                    stats['best_trade'] = float(row[6] or 0)
                    stats['worst_trade'] = float(row[7] or 0)

                    gross_profit = float(row[8] or 0)
                    gross_loss = float(row[9] or 0)

                    if stats['total_trades'] > 0:
                        stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100

                    if gross_loss > 0:
                        stats['profit_factor'] = gross_profit / gross_loss

                # By gamma regime
                for regime in ['POSITIVE', 'NEGATIVE']:
                    c.execute("""
                        SELECT
                            COUNT(*) as trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(realized_pnl) as pnl
                        FROM heracles_closed_trades
                        WHERE gamma_regime = %s
                    """, (regime,))

                    row = c.fetchone()
                    if row and row[0]:
                        key = f"{regime.lower()}_gamma_stats"
                        stats[key] = {
                            'trades': row[0],
                            'wins': row[1] or 0,
                            'win_rate': ((row[1] or 0) / row[0]) * 100 if row[0] > 0 else 0,
                            'total_pnl': float(row[2] or 0),
                        }

        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")

        return stats

    def get_daily_summary(self, trade_date: date = None) -> DailySummary:
        """Get daily trading summary"""
        if trade_date is None:
            trade_date = datetime.now(CENTRAL_TZ).date()

        summary = DailySummary(date=trade_date.isoformat())

        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Get daily stats from closed trades
                c.execute("""
                    SELECT
                        COUNT(*) as trades,
                        SUM(realized_pnl) as pnl,
                        SUM(CASE WHEN gamma_regime = 'POSITIVE' THEN 1 ELSE 0 END) as positive_trades,
                        SUM(CASE WHEN gamma_regime = 'NEGATIVE' THEN 1 ELSE 0 END) as negative_trades
                    FROM heracles_closed_trades
                    WHERE DATE(close_time AT TIME ZONE 'America/Chicago') = %s
                """, (trade_date,))

                row = c.fetchone()
                if row:
                    summary.positions_closed = row[0] or 0
                    summary.realized_pnl = float(row[1] or 0)
                    summary.positive_gamma_trades = row[2] or 0
                    summary.negative_gamma_trades = row[3] or 0

                # Get open positions count
                c.execute("SELECT COUNT(*) FROM heracles_positions WHERE status = 'open'")
                summary.open_positions = c.fetchone()[0] or 0

        except Exception as e:
            logger.error(f"Failed to get daily summary: {e}")

        return summary

    # ========================================================================
    # Paper Trading Account
    # ========================================================================

    def initialize_paper_account(self, starting_capital: float = 100000.0) -> bool:
        """
        Initialize paper trading account with starting capital.

        This creates a virtual account for paper trading simulation.
        Only creates if no active account exists.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Check if active account exists
                c.execute("SELECT id FROM heracles_paper_account WHERE is_active = TRUE")
                existing = c.fetchone()

                if existing:
                    logger.info(f"Paper account already exists (id={existing[0]})")
                    return True

                # Create new paper account
                c.execute("""
                    INSERT INTO heracles_paper_account (
                        starting_capital, current_balance, cumulative_pnl,
                        margin_available, high_water_mark
                    ) VALUES (%s, %s, 0, %s, %s)
                """, (starting_capital, starting_capital, starting_capital, starting_capital))

                conn.commit()
                logger.info(f"Paper trading account initialized with ${starting_capital:,.2f}")
                return True

        except Exception as e:
            logger.error(f"Failed to initialize paper account: {e}")
            return False

    def get_paper_account(self) -> Optional[Dict]:
        """Get current paper trading account state"""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM heracles_paper_account
                    WHERE is_active = TRUE
                    ORDER BY id DESC LIMIT 1
                """)

                row = c.fetchone()
                if row:
                    columns = [desc[0] for desc in c.description]
                    account = dict(zip(columns, row))

                    # Convert datetimes and decimals
                    for key in ['created_at', 'updated_at']:
                        if account.get(key) and hasattr(account[key], 'isoformat'):
                            account[key] = account[key].isoformat()
                    for key in ['starting_capital', 'current_balance', 'cumulative_pnl',
                               'margin_used', 'margin_available', 'high_water_mark', 'max_drawdown']:
                        if account.get(key) is not None:
                            account[key] = float(account[key])

                    return account

        except Exception as e:
            logger.error(f"Failed to get paper account: {e}")

        return None

    def update_paper_balance(self, realized_pnl: float, margin_change: float = 0) -> Tuple[bool, Dict]:
        """
        Update paper trading balance after a trade.

        Args:
            realized_pnl: P&L from the trade (positive or negative)
            margin_change: Change in margin used (positive = opening, negative = closing)

        Returns:
            (success, updated_account_dict)
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Get current account
                c.execute("""
                    SELECT id, current_balance, cumulative_pnl, total_trades,
                           margin_used, high_water_mark, max_drawdown, starting_capital
                    FROM heracles_paper_account
                    WHERE is_active = TRUE
                    ORDER BY id DESC LIMIT 1
                """)

                row = c.fetchone()
                if not row:
                    logger.error("No active paper account found")
                    return False, {}

                account_id = row[0]
                current_balance = float(row[1])
                cumulative_pnl = float(row[2])
                total_trades = int(row[3])
                margin_used = float(row[4])
                high_water_mark = float(row[5])
                max_drawdown = float(row[6])
                starting_capital = float(row[7])

                # Update values
                new_balance = current_balance + realized_pnl
                new_cumulative_pnl = cumulative_pnl + realized_pnl
                new_margin_used = max(0, margin_used + margin_change)
                new_margin_available = new_balance - new_margin_used
                new_total_trades = total_trades + (1 if realized_pnl != 0 else 0)

                # Update high water mark and max drawdown
                new_high_water_mark = max(high_water_mark, new_balance)
                current_drawdown = new_high_water_mark - new_balance
                new_max_drawdown = max(max_drawdown, current_drawdown)

                # Update database
                c.execute("""
                    UPDATE heracles_paper_account
                    SET current_balance = %s,
                        cumulative_pnl = %s,
                        total_trades = %s,
                        margin_used = %s,
                        margin_available = %s,
                        high_water_mark = %s,
                        max_drawdown = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    new_balance, new_cumulative_pnl, new_total_trades,
                    new_margin_used, new_margin_available,
                    new_high_water_mark, new_max_drawdown, account_id
                ))

                conn.commit()

                return True, {
                    'current_balance': new_balance,
                    'cumulative_pnl': new_cumulative_pnl,
                    'total_trades': new_total_trades,
                    'margin_used': new_margin_used,
                    'margin_available': new_margin_available,
                    'high_water_mark': new_high_water_mark,
                    'max_drawdown': new_max_drawdown,
                    'starting_capital': starting_capital,
                    'return_pct': (new_cumulative_pnl / starting_capital) * 100
                }

        except Exception as e:
            logger.error(f"Failed to update paper balance: {e}")
            return False, {}

    def reset_paper_account(self, starting_capital: float = 100000.0) -> bool:
        """Reset paper trading account (for fresh start)"""
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Deactivate existing accounts
                c.execute("UPDATE heracles_paper_account SET is_active = FALSE")

                # Create new account
                c.execute("""
                    INSERT INTO heracles_paper_account (
                        starting_capital, current_balance, cumulative_pnl,
                        margin_available, high_water_mark
                    ) VALUES (%s, %s, 0, %s, %s)
                """, (starting_capital, starting_capital, starting_capital, starting_capital))

                conn.commit()
                logger.info(f"Paper trading account reset with ${starting_capital:,.2f}")
                return True

        except Exception as e:
            logger.error(f"Failed to reset paper account: {e}")
            return False

    def get_paper_equity_curve(self, days: int = 30) -> List[Dict]:
        """
        Get paper trading equity curve using closed trades for cumulative P&L.

        This calculates equity as: starting_capital + cumulative_realized_pnl + unrealized_pnl
        """
        data = []
        try:
            with db_connection() as conn:
                c = conn.cursor()

                # Get starting capital
                account = self.get_paper_account()
                starting_capital = account.get('starting_capital', 100000.0) if account else 100000.0

                # Get daily cumulative P&L from closed trades
                c.execute("""
                    WITH daily_pnl AS (
                        SELECT
                            DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                            SUM(realized_pnl) as daily_realized_pnl,
                            COUNT(*) as trades
                        FROM heracles_closed_trades
                        WHERE close_time >= NOW() - INTERVAL '%s days'
                        GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
                        ORDER BY trade_date
                    )
                    SELECT
                        trade_date,
                        daily_realized_pnl,
                        trades,
                        SUM(daily_realized_pnl) OVER (ORDER BY trade_date) as cumulative_pnl
                    FROM daily_pnl
                """, (days,))

                rows = c.fetchall()

                for row in rows:
                    trade_date, daily_pnl, trades, cumulative_pnl = row
                    equity = starting_capital + float(cumulative_pnl or 0)

                    data.append({
                        'date': trade_date.isoformat() if trade_date else None,
                        'daily_pnl': float(daily_pnl or 0),
                        'cumulative_pnl': float(cumulative_pnl or 0),
                        'equity': equity,
                        'trades': trades,
                        'return_pct': (float(cumulative_pnl or 0) / starting_capital) * 100
                    })

        except Exception as e:
            logger.error(f"Failed to get paper equity curve: {e}")

        return data
