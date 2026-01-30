"""
PROMETHEUS Database Layer - Full Transparency Storage

All database operations for the box spread synthetic borrowing system.
Includes comprehensive audit trails for educational purposes.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import json

# Database adapter import with fallback
try:
    from database_adapter import get_connection
except ImportError:
    get_connection = None

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    PrometheusConfig,
    BorrowingCostAnalysis,
    CapitalDeployment,
    PositionStatus,
    BoxSpreadStatus,
    TradingMode,
    DailyBriefing,
    RollDecision,
)

logger = logging.getLogger(__name__)

# Central timezone for all operations
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


class PrometheusDatabase:
    """
    Database operations for PROMETHEUS box spread system.

    EDUCATIONAL NOTE - Database Design:
    ====================================
    The database stores:
    1. Box spread positions with full audit trail
    2. Signals generated (executed or skipped)
    3. Capital deployments to IC bots
    4. Borrowing cost analysis history
    5. Daily briefings for review
    6. Configuration history

    Everything is retained for learning and analysis.
    """

    def __init__(self, bot_name: str = "PROMETHEUS"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _get_connection(self):
        """Get database connection with fallback handling"""
        if get_connection is None:
            raise RuntimeError("Database adapter not available")
        return get_connection()

    def _ensure_tables(self):
        """Create all PROMETHEUS tables if they don't exist"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Main positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,

                    -- Strike details
                    lower_strike DECIMAL(10, 2),
                    upper_strike DECIMAL(10, 2),
                    strike_width DECIMAL(10, 2),
                    expiration DATE,
                    dte_at_entry INTEGER,
                    current_dte INTEGER,

                    -- Option symbols
                    call_long_symbol VARCHAR(50),
                    call_short_symbol VARCHAR(50),
                    put_long_symbol VARCHAR(50),
                    put_short_symbol VARCHAR(50),

                    -- Order tracking
                    call_spread_order_id VARCHAR(50),
                    put_spread_order_id VARCHAR(50),

                    -- Pricing
                    contracts INTEGER,
                    entry_credit DECIMAL(10, 4),
                    total_credit_received DECIMAL(15, 2),
                    theoretical_value DECIMAL(10, 4),
                    total_owed_at_expiration DECIMAL(15, 2),

                    -- Borrowing costs (KEY TRANSPARENCY)
                    borrowing_cost DECIMAL(15, 2),
                    implied_annual_rate DECIMAL(8, 4),
                    daily_cost DECIMAL(10, 4),
                    cost_accrued_to_date DECIMAL(15, 2),

                    -- Rate comparisons
                    fed_funds_at_entry DECIMAL(8, 4),
                    margin_rate_at_entry DECIMAL(8, 4),
                    savings_vs_margin DECIMAL(15, 2),

                    -- Capital deployment tracking
                    cash_deployed_to_ares DECIMAL(15, 2) DEFAULT 0,
                    cash_deployed_to_titan DECIMAL(15, 2) DEFAULT 0,
                    cash_deployed_to_pegasus DECIMAL(15, 2) DEFAULT 0,
                    cash_held_in_reserve DECIMAL(15, 2) DEFAULT 0,
                    total_cash_deployed DECIMAL(15, 2) DEFAULT 0,

                    -- Returns tracking
                    returns_from_ares DECIMAL(15, 2) DEFAULT 0,
                    returns_from_titan DECIMAL(15, 2) DEFAULT 0,
                    returns_from_pegasus DECIMAL(15, 2) DEFAULT 0,
                    total_ic_returns DECIMAL(15, 2) DEFAULT 0,
                    net_profit DECIMAL(15, 2) DEFAULT 0,

                    -- Market context
                    spot_at_entry DECIMAL(10, 2),
                    vix_at_entry DECIMAL(6, 2),

                    -- Risk
                    early_assignment_risk VARCHAR(20),
                    current_margin_used DECIMAL(15, 2),
                    margin_cushion DECIMAL(15, 2),

                    -- Status
                    status VARCHAR(30) DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE,
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_reason VARCHAR(100),

                    -- Educational
                    position_explanation TEXT,
                    daily_briefing TEXT,

                    -- Timestamps
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Signals table (generated signals, executed or not)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_signals (
                    id SERIAL PRIMARY KEY,
                    signal_id VARCHAR(50) UNIQUE NOT NULL,
                    signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                    -- Underlying
                    ticker VARCHAR(10),
                    spot_price DECIMAL(10, 2),

                    -- Strikes
                    lower_strike DECIMAL(10, 2),
                    upper_strike DECIMAL(10, 2),
                    strike_width DECIMAL(10, 2),
                    expiration DATE,
                    dte INTEGER,

                    -- Pricing
                    theoretical_value DECIMAL(10, 4),
                    market_bid DECIMAL(10, 4),
                    market_ask DECIMAL(10, 4),
                    mid_price DECIMAL(10, 4),

                    -- Borrowing analysis
                    cash_received DECIMAL(15, 2),
                    cash_owed_at_expiration DECIMAL(15, 2),
                    borrowing_cost DECIMAL(15, 2),
                    implied_annual_rate DECIMAL(8, 4),

                    -- Rate comparisons
                    fed_funds_rate DECIMAL(8, 4),
                    margin_rate DECIMAL(8, 4),
                    rate_advantage DECIMAL(10, 2),

                    -- Risk
                    early_assignment_risk VARCHAR(20),
                    margin_requirement DECIMAL(15, 2),

                    -- Sizing
                    recommended_contracts INTEGER,
                    total_cash_generated DECIMAL(15, 2),

                    -- Educational
                    strategy_explanation TEXT,
                    why_this_expiration TEXT,
                    why_these_strikes TEXT,

                    -- Execution
                    was_executed BOOLEAN DEFAULT FALSE,
                    skip_reason VARCHAR(500),
                    executed_position_id VARCHAR(50),

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Capital deployments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_capital_deployments (
                    id SERIAL PRIMARY KEY,
                    deployment_id VARCHAR(50) UNIQUE NOT NULL,
                    deployment_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    source_box_position_id VARCHAR(50),

                    total_capital_available DECIMAL(15, 2),

                    -- ARES allocation
                    ares_allocation DECIMAL(15, 2),
                    ares_allocation_pct DECIMAL(6, 2),
                    ares_allocation_reasoning TEXT,
                    ares_returns_to_date DECIMAL(15, 2) DEFAULT 0,

                    -- TITAN allocation
                    titan_allocation DECIMAL(15, 2),
                    titan_allocation_pct DECIMAL(6, 2),
                    titan_allocation_reasoning TEXT,
                    titan_returns_to_date DECIMAL(15, 2) DEFAULT 0,

                    -- PEGASUS allocation
                    pegasus_allocation DECIMAL(15, 2),
                    pegasus_allocation_pct DECIMAL(6, 2),
                    pegasus_allocation_reasoning TEXT,
                    pegasus_returns_to_date DECIMAL(15, 2) DEFAULT 0,

                    -- Reserve
                    reserve_amount DECIMAL(15, 2),
                    reserve_pct DECIMAL(6, 2),
                    reserve_reasoning TEXT,

                    -- Methodology
                    allocation_method VARCHAR(50),
                    methodology_explanation TEXT,

                    total_returns_to_date DECIMAL(15, 2) DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    deactivation_reason VARCHAR(200),

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Borrowing cost analysis history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_rate_analysis (
                    id SERIAL PRIMARY KEY,
                    analysis_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                    box_implied_rate DECIMAL(8, 4),
                    fed_funds_rate DECIMAL(8, 4),
                    sofr_rate DECIMAL(8, 4),
                    broker_margin_rate DECIMAL(8, 4),

                    spread_to_fed_funds DECIMAL(8, 4),
                    spread_to_margin DECIMAL(8, 4),

                    cost_per_100k_monthly DECIMAL(10, 2),
                    cost_per_100k_annual DECIMAL(10, 2),

                    required_ic_return_monthly DECIMAL(8, 4),
                    current_ic_return_estimate DECIMAL(8, 4),
                    projected_profit_per_100k DECIMAL(10, 2),

                    avg_box_rate_30d DECIMAL(8, 4),
                    avg_box_rate_90d DECIMAL(8, 4),
                    rate_trend VARCHAR(20),

                    is_favorable BOOLEAN,
                    recommendation TEXT,
                    reasoning TEXT
                )
            """)

            # Daily briefings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_daily_briefings (
                    id SERIAL PRIMARY KEY,
                    briefing_date DATE UNIQUE,
                    briefing_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                    system_status VARCHAR(30),

                    total_open_positions INTEGER,
                    total_borrowed_amount DECIMAL(15, 2),
                    total_cash_deployed DECIMAL(15, 2),
                    total_margin_used DECIMAL(15, 2),
                    margin_remaining DECIMAL(15, 2),

                    total_borrowing_cost_to_date DECIMAL(15, 2),
                    average_borrowing_rate DECIMAL(8, 4),
                    comparison_to_margin_rate DECIMAL(8, 4),

                    total_ic_returns_to_date DECIMAL(15, 2),
                    net_profit_to_date DECIMAL(15, 2),
                    roi_on_strategy DECIMAL(8, 4),

                    highest_assignment_risk_position VARCHAR(50),
                    days_until_nearest_expiration INTEGER,

                    current_box_rate DECIMAL(8, 4),
                    rate_vs_yesterday DECIMAL(8, 4),
                    rate_trend_7d VARCHAR(20),

                    recommended_actions JSONB,
                    warnings JSONB,
                    daily_tip TEXT
                )
            """)

            # Roll decisions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_roll_decisions (
                    id SERIAL PRIMARY KEY,
                    decision_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    current_position_id VARCHAR(50),

                    current_expiration DATE,
                    current_dte INTEGER,
                    current_implied_rate DECIMAL(8, 4),

                    target_expiration DATE,
                    target_dte INTEGER,
                    target_implied_rate DECIMAL(8, 4),

                    roll_cost DECIMAL(15, 2),
                    rate_improvement DECIMAL(8, 4),
                    total_borrowing_extension INTEGER,

                    should_roll BOOLEAN,
                    decision_reasoning TEXT,

                    was_executed BOOLEAN DEFAULT FALSE,
                    new_position_id VARCHAR(50)
                )
            """)

            # Configuration table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_config (
                    id SERIAL PRIMARY KEY,
                    config_key VARCHAR(50) UNIQUE DEFAULT 'default',
                    config_data JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Activity log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_logs (
                    id SERIAL PRIMARY KEY,
                    log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    level VARCHAR(20),
                    action VARCHAR(100),
                    message TEXT,
                    details JSONB,
                    position_id VARCHAR(50),
                    signal_id VARCHAR(50)
                )
            """)

            # Equity snapshots for intraday tracking with FULL TRANSPARENCY
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_equity_snapshots (
                    id SERIAL PRIMARY KEY,
                    snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    total_equity DECIMAL(15, 2),
                    total_borrowed DECIMAL(15, 2),
                    total_deployed DECIMAL(15, 2),
                    unrealized_pnl DECIMAL(15, 2),
                    net_position_value DECIMAL(15, 2),
                    open_position_count INTEGER,

                    -- Enhanced transparency fields
                    quote_source VARCHAR(50),                    -- 'tradier_production', 'cache', 'simulated'
                    calculation_method VARCHAR(50),              -- 'real_quotes', 'theoretical'
                    total_mtm_unrealized DECIMAL(15, 2),         -- Box spread MTM unrealized
                    total_ic_returns DECIMAL(15, 2),             -- IC bot returns
                    total_costs_accrued DECIMAL(15, 2),          -- Borrowing costs accrued

                    details JSONB                                -- Full position-level MTM details
                )
            """)

            # Add new columns if they don't exist (for schema migration)
            # These columns were added for enhanced transparency tracking
            migration_columns = [
                ("prometheus_equity_snapshots", "quote_source", "VARCHAR(50)"),
                ("prometheus_equity_snapshots", "calculation_method", "VARCHAR(50)"),
                ("prometheus_equity_snapshots", "total_mtm_unrealized", "DECIMAL(15, 2)"),
                ("prometheus_equity_snapshots", "total_ic_returns", "DECIMAL(15, 2)"),
                ("prometheus_equity_snapshots", "total_costs_accrued", "DECIMAL(15, 2)"),
            ]

            for table, column, col_type in migration_columns:
                try:
                    cursor.execute(f"""
                        ALTER TABLE {table}
                        ADD COLUMN IF NOT EXISTS {column} {col_type}
                    """)
                except Exception as e:
                    # Column might already exist or other issue
                    logger.debug(f"Column migration for {table}.{column}: {e}")

            conn.commit()
            cursor.close()
            logger.info("PROMETHEUS tables initialized successfully")

        except Exception as e:
            logger.error(f"Error creating PROMETHEUS tables: {e}")
            raise

    # ========== Configuration Methods ==========

    def load_config(self) -> PrometheusConfig:
        """Load configuration from database or return defaults"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT config_data FROM prometheus_config
                WHERE config_key = 'default'
            """)
            row = cursor.fetchone()
            cursor.close()

            if row and row[0]:
                return PrometheusConfig.from_dict(row[0])
            return PrometheusConfig()

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return PrometheusConfig()

    def save_config(self, config: PrometheusConfig) -> bool:
        """Save configuration to database"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_config (config_key, config_data, updated_at)
                VALUES ('default', %s, NOW())
                ON CONFLICT (config_key)
                DO UPDATE SET config_data = %s, updated_at = NOW()
            """, (json.dumps(config.to_dict()), json.dumps(config.to_dict())))
            conn.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    # ========== Position Methods ==========

    def get_open_positions(self) -> List[BoxSpreadPosition]:
        """Get all open box spread positions"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_positions
                WHERE status IN ('open', 'pending', 'assignment_risk')
                ORDER BY open_time DESC
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            positions = []
            for row in rows:
                data = dict(zip(columns, row))
                positions.append(self._row_to_position(data))
            return positions

        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def get_position(self, position_id: str) -> Optional[BoxSpreadPosition]:
        """Get a specific position by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_positions
                WHERE position_id = %s
            """, (position_id,))
            row = cursor.fetchone()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            if row:
                data = dict(zip(columns, row))
                return self._row_to_position(data)
            return None

        except Exception as e:
            logger.error(f"Error getting position {position_id}: {e}")
            return None

    def get_closed_positions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get closed box spread positions.

        Returns closed positions with realized P&L for trade history analysis.
        This follows the STANDARDS.md requirement for /closed-trades endpoint.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    position_id,
                    ticker,
                    lower_strike,
                    upper_strike,
                    strike_width,
                    expiration,
                    contracts,
                    entry_credit,
                    total_credit_received,
                    borrowing_cost,
                    implied_annual_rate,
                    total_ic_returns,
                    net_profit as realized_pnl,
                    open_time,
                    close_time,
                    close_reason,
                    status,
                    dte_at_entry,
                    spot_at_entry,
                    vix_at_entry
                FROM prometheus_positions
                WHERE status = 'closed'
                ORDER BY close_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting closed positions: {e}")
            return []

    def save_position(self, position: BoxSpreadPosition) -> bool:
        """Save a new or updated position"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_positions (
                    position_id, ticker, lower_strike, upper_strike, strike_width,
                    expiration, dte_at_entry, current_dte,
                    call_long_symbol, call_short_symbol, put_long_symbol, put_short_symbol,
                    call_spread_order_id, put_spread_order_id,
                    contracts, entry_credit, total_credit_received,
                    theoretical_value, total_owed_at_expiration,
                    borrowing_cost, implied_annual_rate, daily_cost, cost_accrued_to_date,
                    fed_funds_at_entry, margin_rate_at_entry, savings_vs_margin,
                    cash_deployed_to_ares, cash_deployed_to_titan, cash_deployed_to_pegasus,
                    cash_held_in_reserve, total_cash_deployed,
                    returns_from_ares, returns_from_titan, returns_from_pegasus,
                    total_ic_returns, net_profit,
                    spot_at_entry, vix_at_entry,
                    early_assignment_risk, current_margin_used, margin_cushion,
                    status, open_time,
                    position_explanation, daily_briefing
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    current_dte = EXCLUDED.current_dte,
                    cost_accrued_to_date = EXCLUDED.cost_accrued_to_date,
                    returns_from_ares = EXCLUDED.returns_from_ares,
                    returns_from_titan = EXCLUDED.returns_from_titan,
                    returns_from_pegasus = EXCLUDED.returns_from_pegasus,
                    total_ic_returns = EXCLUDED.total_ic_returns,
                    net_profit = EXCLUDED.net_profit,
                    current_margin_used = EXCLUDED.current_margin_used,
                    margin_cushion = EXCLUDED.margin_cushion,
                    status = EXCLUDED.status,
                    daily_briefing = EXCLUDED.daily_briefing,
                    updated_at = NOW()
            """, (
                position.position_id, position.ticker,
                position.lower_strike, position.upper_strike, position.strike_width,
                position.expiration, position.dte_at_entry, position.current_dte,
                position.call_long_symbol, position.call_short_symbol,
                position.put_long_symbol, position.put_short_symbol,
                position.call_spread_order_id, position.put_spread_order_id,
                position.contracts, position.entry_credit, position.total_credit_received,
                position.theoretical_value, position.total_owed_at_expiration,
                position.borrowing_cost, position.implied_annual_rate,
                position.daily_cost, position.cost_accrued_to_date,
                position.fed_funds_at_entry, position.margin_rate_at_entry,
                position.savings_vs_margin,
                position.cash_deployed_to_ares, position.cash_deployed_to_titan,
                position.cash_deployed_to_pegasus, position.cash_held_in_reserve,
                position.total_cash_deployed,
                position.returns_from_ares, position.returns_from_titan,
                position.returns_from_pegasus, position.total_ic_returns, position.net_profit,
                position.spot_at_entry, position.vix_at_entry,
                position.early_assignment_risk, position.current_margin_used,
                position.margin_cushion,
                position.status.value, position.open_time,
                position.position_explanation, position.daily_briefing
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error saving position: {e}")
            return False

    def close_position(
        self,
        position_id: str,
        close_reason: str,
        final_ic_returns: float = 0.0
    ) -> bool:
        """Close a position and record final results"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get current position data to calculate net profit
            cursor.execute("""
                SELECT borrowing_cost, total_ic_returns
                FROM prometheus_positions
                WHERE position_id = %s
            """, (position_id,))
            row = cursor.fetchone()

            if row:
                borrowing_cost = float(row[0] or 0)
                current_returns = float(row[1] or 0)
                total_returns = current_returns + final_ic_returns
                net_profit = total_returns - borrowing_cost

                cursor.execute("""
                    UPDATE prometheus_positions
                    SET status = 'closed',
                        close_time = NOW(),
                        close_reason = %s,
                        total_ic_returns = %s,
                        net_profit = %s,
                        updated_at = NOW()
                    WHERE position_id = %s
                """, (close_reason, total_returns, net_profit, position_id))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            return False

    def _row_to_position(self, data: Dict[str, Any]) -> BoxSpreadPosition:
        """Convert database row to BoxSpreadPosition object"""
        return BoxSpreadPosition(
            position_id=data['position_id'],
            ticker=data['ticker'],
            lower_strike=float(data['lower_strike'] or 0),
            upper_strike=float(data['upper_strike'] or 0),
            strike_width=float(data['strike_width'] or 0),
            expiration=str(data['expiration']),
            dte_at_entry=int(data['dte_at_entry'] or 0),
            current_dte=int(data['current_dte'] or 0),
            call_long_symbol=data['call_long_symbol'] or '',
            call_short_symbol=data['call_short_symbol'] or '',
            put_long_symbol=data['put_long_symbol'] or '',
            put_short_symbol=data['put_short_symbol'] or '',
            call_spread_order_id=data['call_spread_order_id'] or '',
            put_spread_order_id=data['put_spread_order_id'] or '',
            contracts=int(data['contracts'] or 0),
            entry_credit=float(data['entry_credit'] or 0),
            total_credit_received=float(data['total_credit_received'] or 0),
            theoretical_value=float(data['theoretical_value'] or 0),
            total_owed_at_expiration=float(data['total_owed_at_expiration'] or 0),
            borrowing_cost=float(data['borrowing_cost'] or 0),
            implied_annual_rate=float(data['implied_annual_rate'] or 0),
            daily_cost=float(data['daily_cost'] or 0),
            cost_accrued_to_date=float(data['cost_accrued_to_date'] or 0),
            fed_funds_at_entry=float(data['fed_funds_at_entry'] or 0),
            margin_rate_at_entry=float(data['margin_rate_at_entry'] or 0),
            savings_vs_margin=float(data['savings_vs_margin'] or 0),
            cash_deployed_to_ares=float(data['cash_deployed_to_ares'] or 0),
            cash_deployed_to_titan=float(data['cash_deployed_to_titan'] or 0),
            cash_deployed_to_pegasus=float(data['cash_deployed_to_pegasus'] or 0),
            cash_held_in_reserve=float(data['cash_held_in_reserve'] or 0),
            total_cash_deployed=float(data['total_cash_deployed'] or 0),
            returns_from_ares=float(data['returns_from_ares'] or 0),
            returns_from_titan=float(data['returns_from_titan'] or 0),
            returns_from_pegasus=float(data['returns_from_pegasus'] or 0),
            total_ic_returns=float(data['total_ic_returns'] or 0),
            net_profit=float(data['net_profit'] or 0),
            spot_at_entry=float(data['spot_at_entry'] or 0),
            vix_at_entry=float(data['vix_at_entry'] or 0),
            early_assignment_risk=data['early_assignment_risk'] or 'UNKNOWN',
            current_margin_used=float(data['current_margin_used'] or 0),
            margin_cushion=float(data['margin_cushion'] or 0),
            status=PositionStatus(data['status']) if data['status'] else PositionStatus.OPEN,
            open_time=data['open_time'],
            close_time=data.get('close_time'),
            close_reason=data.get('close_reason', ''),
            position_explanation=data.get('position_explanation', ''),
            daily_briefing=data.get('daily_briefing', ''),
        )

    # ========== Signal Methods ==========

    def log_signal(self, signal: BoxSpreadSignal, was_executed: bool,
                   executed_position_id: str = None) -> bool:
        """Log a generated signal"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_signals (
                    signal_id, signal_time, ticker, spot_price,
                    lower_strike, upper_strike, strike_width, expiration, dte,
                    theoretical_value, market_bid, market_ask, mid_price,
                    cash_received, cash_owed_at_expiration, borrowing_cost,
                    implied_annual_rate, fed_funds_rate, margin_rate, rate_advantage,
                    early_assignment_risk, margin_requirement,
                    recommended_contracts, total_cash_generated,
                    strategy_explanation, why_this_expiration, why_these_strikes,
                    was_executed, skip_reason, executed_position_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                signal.signal_id, signal.signal_time, signal.ticker, signal.spot_price,
                signal.lower_strike, signal.upper_strike, signal.strike_width,
                signal.expiration, signal.dte,
                signal.theoretical_value, signal.market_bid, signal.market_ask,
                signal.mid_price,
                signal.cash_received, signal.cash_owed_at_expiration, signal.borrowing_cost,
                signal.implied_annual_rate, signal.fed_funds_rate, signal.margin_rate,
                signal.rate_advantage,
                signal.early_assignment_risk, signal.margin_requirement,
                signal.recommended_contracts, signal.total_cash_generated,
                signal.strategy_explanation, signal.why_this_expiration,
                signal.why_these_strikes,
                was_executed, signal.skip_reason if not was_executed else '',
                executed_position_id
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error logging signal: {e}")
            return False

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signals for display"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_signals
                ORDER BY signal_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            return []

    # ========== Capital Deployment Methods ==========

    def save_deployment(self, deployment: CapitalDeployment) -> bool:
        """Save a capital deployment record"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_capital_deployments (
                    deployment_id, deployment_time, source_box_position_id,
                    total_capital_available,
                    ares_allocation, ares_allocation_pct, ares_allocation_reasoning,
                    titan_allocation, titan_allocation_pct, titan_allocation_reasoning,
                    pegasus_allocation, pegasus_allocation_pct, pegasus_allocation_reasoning,
                    reserve_amount, reserve_pct, reserve_reasoning,
                    allocation_method, methodology_explanation,
                    is_active
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                deployment.deployment_id, deployment.deployment_time,
                deployment.source_box_position_id,
                deployment.total_capital_available,
                deployment.ares_allocation, deployment.ares_allocation_pct,
                deployment.ares_allocation_reasoning,
                deployment.titan_allocation, deployment.titan_allocation_pct,
                deployment.titan_allocation_reasoning,
                deployment.pegasus_allocation, deployment.pegasus_allocation_pct,
                deployment.pegasus_allocation_reasoning,
                deployment.reserve_amount, deployment.reserve_pct,
                deployment.reserve_reasoning,
                deployment.allocation_method, deployment.methodology_explanation,
                deployment.is_active
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error saving deployment: {e}")
            return False

    def get_active_deployments(self) -> List[Dict[str, Any]]:
        """Get all active capital deployments"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_capital_deployments
                WHERE is_active = TRUE
                ORDER BY deployment_time DESC
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting deployments: {e}")
            return []

    def update_deployment_returns(
        self,
        deployment_id: str,
        ares_returns: float,
        titan_returns: float,
        pegasus_returns: float
    ) -> bool:
        """Update returns for a deployment"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            total_returns = ares_returns + titan_returns + pegasus_returns
            cursor.execute("""
                UPDATE prometheus_capital_deployments
                SET ares_returns_to_date = %s,
                    titan_returns_to_date = %s,
                    pegasus_returns_to_date = %s,
                    total_returns_to_date = %s,
                    updated_at = NOW()
                WHERE deployment_id = %s
            """, (ares_returns, titan_returns, pegasus_returns,
                  total_returns, deployment_id))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error updating deployment returns: {e}")
            return False

    # ========== Rate Analysis Methods ==========

    def save_rate_analysis(self, analysis: BorrowingCostAnalysis) -> bool:
        """Save a rate analysis snapshot"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_rate_analysis (
                    analysis_time, box_implied_rate, fed_funds_rate, sofr_rate,
                    broker_margin_rate, spread_to_fed_funds, spread_to_margin,
                    cost_per_100k_monthly, cost_per_100k_annual,
                    required_ic_return_monthly, current_ic_return_estimate,
                    projected_profit_per_100k,
                    avg_box_rate_30d, avg_box_rate_90d, rate_trend,
                    is_favorable, recommendation, reasoning
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                analysis.analysis_time, analysis.box_implied_rate,
                analysis.fed_funds_rate, analysis.sofr_rate,
                analysis.broker_margin_rate, analysis.spread_to_fed_funds,
                analysis.spread_to_margin, analysis.cost_per_100k_monthly,
                analysis.cost_per_100k_annual, analysis.required_ic_return_monthly,
                analysis.current_ic_return_estimate, analysis.projected_profit_per_100k,
                analysis.avg_box_rate_30d, analysis.avg_box_rate_90d, analysis.rate_trend,
                analysis.is_favorable, analysis.recommendation, analysis.reasoning
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error saving rate analysis: {e}")
            return False

    def get_rate_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get rate analysis history"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_rate_analysis
                WHERE analysis_time > NOW() - INTERVAL '%s days'
                ORDER BY analysis_time DESC
            """, (days,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting rate history: {e}")
            return []

    # ========== Equity & Performance Methods ==========

    def get_starting_capital(self) -> float:
        """Get starting capital from config"""
        config = self.load_config()
        return config.capital

    def get_equity_curve(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical equity curve data"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get closed positions for equity curve
            cursor.execute("""
                SELECT
                    DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                    SUM(net_profit) as daily_profit,
                    COUNT(*) as positions_closed
                FROM prometheus_positions
                WHERE status = 'closed' AND close_time IS NOT NULL
                GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date ASC
                LIMIT %s
            """, (limit,))

            rows = cursor.fetchall()
            cursor.close()

            starting_capital = self.get_starting_capital()
            cumulative_pnl = 0
            equity_curve = []

            for row in rows:
                cumulative_pnl += float(row[1] or 0)
                equity_curve.append({
                    'date': row[0].isoformat() if row[0] else None,
                    'daily_profit': float(row[1] or 0),
                    'cumulative_pnl': cumulative_pnl,
                    'equity': starting_capital + cumulative_pnl,
                    'positions_closed': row[2],
                })

            return equity_curve

        except Exception as e:
            logger.error(f"Error getting equity curve: {e}")
            return []

    def record_equity_snapshot(self, use_real_quotes: bool = True) -> bool:
        """
        Record current equity snapshot for intraday tracking.

        ENHANCED FOR TRANSPARENCY:
        ==========================
        When use_real_quotes=True, this fetches actual production quotes
        from Tradier to calculate real mark-to-market values instead of
        theoretical values. This provides:

        1. Accurate unrealized P&L based on current market prices
        2. Real bid-ask spreads for more realistic equity tracking
        3. Current implied rates for comparison to entry rates

        This makes paper trading "as real as possible" by using the same
        quotes that would be used in live trading.
        """
        try:
            from datetime import datetime
            now = datetime.now(CENTRAL_TZ)

            positions = self.get_open_positions()
            total_borrowed = sum(p.total_credit_received for p in positions)
            total_deployed = sum(p.total_cash_deployed for p in positions)
            total_ic_returns = sum(p.total_ic_returns for p in positions)
            total_costs = sum(p.cost_accrued_to_date for p in positions)

            # Calculate MTM for each position using real quotes
            position_mtm_details = []
            total_mtm_unrealized = 0.0
            quote_source = 'calculated'

            if use_real_quotes:
                try:
                    # Import here to avoid circular imports
                    from .executor import calculate_box_spread_mark_to_market

                    for position in positions:
                        mtm = calculate_box_spread_mark_to_market(
                            ticker=position.ticker,
                            expiration=position.expiration,
                            lower_strike=position.lower_strike,
                            upper_strike=position.upper_strike,
                            contracts=position.contracts,
                            entry_credit=position.entry_credit,
                            use_cache=True
                        )

                        if mtm['success']:
                            position_mtm = {
                                'position_id': position.position_id,
                                'entry_credit': position.entry_credit,
                                'current_value': mtm['current_value'],
                                'unrealized_pnl': mtm['unrealized_pnl'],
                                'current_implied_rate': mtm.get('current_implied_rate'),
                                'entry_implied_rate': position.implied_annual_rate,
                                'quote_source': mtm['quote_source'],
                                'quote_time': mtm['timestamp'],
                            }
                            total_mtm_unrealized += mtm['unrealized_pnl']
                            quote_source = mtm['quote_source']
                        else:
                            # Fallback to calculated unrealized
                            position_mtm = {
                                'position_id': position.position_id,
                                'entry_credit': position.entry_credit,
                                'unrealized_pnl': 0,  # Box spread MTM is roughly 0 if rates stable
                                'error': mtm.get('error', 'unknown'),
                            }

                        position_mtm_details.append(position_mtm)

                except Exception as e:
                    logger.warning(f"Could not get real quotes for MTM: {e}")
                    # Fall back to simple calculation
                    total_mtm_unrealized = 0  # Box spreads have near-zero MTM change typically

            # Total unrealized = MTM unrealized + IC returns - borrowing costs accrued
            unrealized_pnl = total_mtm_unrealized + total_ic_returns - total_costs

            starting_capital = self.get_starting_capital()
            total_equity = starting_capital + unrealized_pnl

            conn = self._get_connection()
            cursor = conn.cursor()

            calculation_method = 'real_quotes' if use_real_quotes else 'theoretical'

            cursor.execute("""
                INSERT INTO prometheus_equity_snapshots (
                    snapshot_time, total_equity, total_borrowed, total_deployed,
                    unrealized_pnl, net_position_value, open_position_count,
                    quote_source, calculation_method, total_mtm_unrealized,
                    total_ic_returns, total_costs_accrued, details
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                total_equity, total_borrowed, total_deployed, unrealized_pnl,
                total_ic_returns - total_costs, len(positions),
                quote_source, calculation_method, total_mtm_unrealized,
                total_ic_returns, total_costs,
                json.dumps({
                    'positions': [p.position_id for p in positions],
                    'position_mtm_details': position_mtm_details,
                    'snapshot_timestamp': now.isoformat(),
                })
            ))
            conn.commit()
            cursor.close()

            logger.info(
                f"Recorded equity snapshot: equity=${total_equity:,.2f}, "
                f"unrealized=${unrealized_pnl:,.2f}, source={quote_source}"
            )
            return True

        except Exception as e:
            logger.error(f"Error recording equity snapshot: {e}")
            return False

    def get_intraday_equity(self) -> List[Dict[str, Any]]:
        """Get today's equity snapshots"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_equity_snapshots
                WHERE DATE(snapshot_time AT TIME ZONE 'America/Chicago') =
                      DATE(NOW() AT TIME ZONE 'America/Chicago')
                ORDER BY snapshot_time ASC
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting intraday equity: {e}")
            return []

    # ========== Logging Methods ==========

    def log_action(
        self,
        action: str,
        message: str,
        level: str = "INFO",
        details: Dict[str, Any] = None,
        position_id: str = None,
        signal_id: str = None
    ) -> bool:
        """Log an action for audit trail"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_logs (
                    log_time, level, action, message, details, position_id, signal_id
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s)
            """, (level, action, message, json.dumps(details) if details else None,
                  position_id, signal_id))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return False

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent logs"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_logs
                ORDER BY log_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return []

    # ========== Performance Metrics ==========

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get closed positions stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_closed,
                    SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as winners,
                    SUM(net_profit) as total_pnl,
                    AVG(net_profit) as avg_pnl,
                    SUM(borrowing_cost) as total_borrowing_cost,
                    SUM(total_ic_returns) as total_ic_returns,
                    AVG(implied_annual_rate) as avg_implied_rate
                FROM prometheus_positions
                WHERE status = 'closed'
            """)
            closed_stats = cursor.fetchone()

            # Get open positions stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_open,
                    SUM(total_credit_received) as total_borrowed,
                    SUM(total_cash_deployed) as total_deployed,
                    SUM(total_ic_returns) as unrealized_returns,
                    SUM(cost_accrued_to_date) as accrued_costs
                FROM prometheus_positions
                WHERE status IN ('open', 'assignment_risk')
            """)
            open_stats = cursor.fetchone()

            cursor.close()

            total_closed = int(closed_stats[0] or 0)
            winners = int(closed_stats[1] or 0)
            win_rate = winners / total_closed if total_closed > 0 else 0

            return {
                'closed_positions': {
                    'total': total_closed,
                    'winners': winners,
                    'win_rate': win_rate,
                    'total_pnl': float(closed_stats[2] or 0),
                    'avg_pnl': float(closed_stats[3] or 0),
                    'total_borrowing_cost': float(closed_stats[4] or 0),
                    'total_ic_returns': float(closed_stats[5] or 0),
                    'avg_implied_rate': float(closed_stats[6] or 0),
                },
                'open_positions': {
                    'total': int(open_stats[0] or 0),
                    'total_borrowed': float(open_stats[1] or 0),
                    'total_deployed': float(open_stats[2] or 0),
                    'unrealized_returns': float(open_stats[3] or 0),
                    'accrued_costs': float(open_stats[4] or 0),
                    'unrealized_pnl': float(open_stats[3] or 0) - float(open_stats[4] or 0),
                },
                'starting_capital': self.get_starting_capital(),
            }

        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
