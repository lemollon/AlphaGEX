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
    # IC Trading Models
    ICPositionStatus,
    PrometheusICSignal,
    PrometheusICPosition,
    PrometheusICConfig,
    PrometheusPerformanceSummary,
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
                    quote_source VARCHAR(50),                    -- 'tradier_production', 'cache', 'unavailable'
                    calculation_method VARCHAR(50),              -- 'real_quotes', 'theoretical'
                    total_mtm_unrealized DECIMAL(15, 2),         -- Box spread MTM unrealized
                    total_ic_returns DECIMAL(15, 2),             -- IC bot returns
                    total_costs_accrued DECIMAL(15, 2),          -- Borrowing costs accrued

                    details JSONB                                -- Full position-level MTM details
                )
            """)

            # ==================================================================
            # IC TRADING TABLES
            # ==================================================================
            # These tables support PROMETHEUS's own Iron Condor trading
            # using capital borrowed via box spreads.
            # ==================================================================

            # IC Positions table - Active Iron Condor positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_ic_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    source_box_position_id VARCHAR(50),          -- Links to box spread funding this

                    -- Underlying
                    ticker VARCHAR(10) NOT NULL,

                    -- Put spread leg
                    put_short_strike DECIMAL(10, 2),
                    put_long_strike DECIMAL(10, 2),
                    put_short_symbol VARCHAR(50),
                    put_long_symbol VARCHAR(50),
                    put_spread_order_id VARCHAR(50),

                    -- Call spread leg
                    call_short_strike DECIMAL(10, 2),
                    call_long_strike DECIMAL(10, 2),
                    call_short_symbol VARCHAR(50),
                    call_long_symbol VARCHAR(50),
                    call_spread_order_id VARCHAR(50),

                    -- Spread details
                    spread_width DECIMAL(10, 2),
                    expiration DATE,
                    dte_at_entry INTEGER,
                    current_dte INTEGER,

                    -- Execution
                    contracts INTEGER,
                    entry_credit DECIMAL(10, 4),                 -- Credit per contract
                    total_credit_received DECIMAL(15, 2),        -- entry_credit × contracts × 100
                    max_loss DECIMAL(15, 2),                     -- (width - credit) × contracts × 100

                    -- Mark-to-market
                    current_value DECIMAL(15, 2),                -- Current cost to close
                    unrealized_pnl DECIMAL(15, 2),               -- Credit - current_value

                    -- Exit details
                    exit_price DECIMAL(10, 4) DEFAULT 0,
                    realized_pnl DECIMAL(15, 2) DEFAULT 0,

                    -- Market context at entry
                    spot_at_entry DECIMAL(10, 2),
                    vix_at_entry DECIMAL(6, 2),
                    gamma_regime_at_entry VARCHAR(20),

                    -- Oracle decision context
                    oracle_confidence DECIMAL(5, 4),
                    oracle_reasoning TEXT,

                    -- Risk management
                    stop_loss_pct DECIMAL(6, 2) DEFAULT 200,
                    profit_target_pct DECIMAL(6, 2) DEFAULT 50,
                    time_stop_dte INTEGER DEFAULT 0,

                    -- Status
                    status VARCHAR(30) DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE,
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_reason VARCHAR(100),

                    -- Timestamps
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # IC Closed Trades table - Historical IC trades
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_ic_closed_trades (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    source_box_position_id VARCHAR(50),

                    ticker VARCHAR(10),
                    put_short_strike DECIMAL(10, 2),
                    put_long_strike DECIMAL(10, 2),
                    call_short_strike DECIMAL(10, 2),
                    call_long_strike DECIMAL(10, 2),
                    spread_width DECIMAL(10, 2),
                    expiration DATE,
                    dte_at_entry INTEGER,

                    contracts INTEGER,
                    entry_credit DECIMAL(10, 4),
                    exit_price DECIMAL(10, 4),
                    realized_pnl DECIMAL(15, 2),

                    spot_at_entry DECIMAL(10, 2),
                    vix_at_entry DECIMAL(6, 2),
                    gamma_regime VARCHAR(20),
                    oracle_confidence DECIMAL(5, 4),

                    open_time TIMESTAMP WITH TIME ZONE,
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_reason VARCHAR(100),
                    hold_duration_minutes INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # IC Signals table - Generated IC trading signals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_ic_signals (
                    id SERIAL PRIMARY KEY,
                    signal_id VARCHAR(50) UNIQUE NOT NULL,
                    signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    source_box_position_id VARCHAR(50),

                    ticker VARCHAR(10),
                    spot_price DECIMAL(10, 2),

                    -- Put spread
                    put_short_strike DECIMAL(10, 2),
                    put_long_strike DECIMAL(10, 2),
                    put_spread_credit DECIMAL(10, 4),

                    -- Call spread
                    call_short_strike DECIMAL(10, 2),
                    call_long_strike DECIMAL(10, 2),
                    call_spread_credit DECIMAL(10, 4),

                    -- Total IC
                    expiration DATE,
                    dte INTEGER,
                    total_credit DECIMAL(10, 4),
                    max_loss DECIMAL(15, 2),

                    -- Risk metrics
                    probability_of_profit DECIMAL(5, 4),
                    delta_of_short_put DECIMAL(6, 4),
                    delta_of_short_call DECIMAL(6, 4),

                    -- Sizing
                    contracts INTEGER,
                    margin_required DECIMAL(15, 2),
                    capital_at_risk DECIMAL(15, 2),

                    -- Oracle decision
                    oracle_approved BOOLEAN,
                    oracle_confidence DECIMAL(5, 4),
                    oracle_reasoning TEXT,

                    -- Market context
                    vix_level DECIMAL(6, 2),
                    gamma_regime VARCHAR(20),
                    gex_regime VARCHAR(20),

                    -- Execution status
                    was_executed BOOLEAN DEFAULT FALSE,
                    skip_reason VARCHAR(500),
                    executed_position_id VARCHAR(50),

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # IC Config table - IC trading configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_ic_config (
                    id SERIAL PRIMARY KEY,
                    config_key VARCHAR(50) UNIQUE DEFAULT 'default',
                    config_data JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # IC Equity Snapshots table - for intraday IC equity tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prometheus_ic_equity_snapshots (
                    id SERIAL PRIMARY KEY,
                    snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    total_equity DECIMAL(15, 2),
                    starting_capital DECIMAL(15, 2),
                    total_realized_pnl DECIMAL(15, 2),
                    total_unrealized_pnl DECIMAL(15, 2),
                    open_position_count INTEGER,
                    details JSONB
                )
            """)

            # ==================================================================
            # BOX SPREAD TABLE INDEXES - per STANDARDS.md Performance Requirements
            # ==================================================================
            # These indexes ensure efficient queries on box spread data

            # Box Positions - query by status and close_time
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_positions_status
                ON prometheus_positions (status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_positions_close_time
                ON prometheus_positions (close_time DESC NULLS LAST)
            """)

            # Box Signals - query by time and execution status
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_signals_time
                ON prometheus_signals (signal_time DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_signals_executed
                ON prometheus_signals (was_executed, signal_time DESC)
            """)

            # Box Equity Snapshots - query by time for intraday
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_equity_snapshots_time
                ON prometheus_equity_snapshots (snapshot_time DESC)
            """)

            # Capital Deployments - query by time
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_capital_deployments_time
                ON prometheus_capital_deployments (deployment_time DESC)
            """)

            # Rate Analysis - query by time
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_rate_analysis_time
                ON prometheus_rate_analysis (analysis_time DESC)
            """)

            # ==================================================================
            # IC TABLE INDEXES - per STANDARDS.md Performance Requirements
            # ==================================================================
            # These indexes ensure efficient queries on IC trading data

            # IC Positions - query by status and open_time
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_positions_status
                ON prometheus_ic_positions (status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_positions_open_time
                ON prometheus_ic_positions (open_time DESC)
            """)

            # IC Closed Trades - query by close_time for equity curve
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_closed_trades_close_time
                ON prometheus_ic_closed_trades (close_time DESC)
            """)

            # IC Signals - query by time and execution status
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_signals_time
                ON prometheus_ic_signals (signal_time DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_signals_executed
                ON prometheus_ic_signals (was_executed, signal_time DESC)
            """)

            # IC Equity Snapshots - query by time for intraday
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_ic_equity_snapshots_time
                ON prometheus_ic_equity_snapshots (snapshot_time DESC)
            """)

            # Logs - query by action type for IC logs
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prometheus_logs_action
                ON prometheus_logs (action, log_time DESC)
            """)

            # Add new columns if they don't exist (for schema migration)
            # These columns were added for enhanced transparency tracking
            migration_columns = [
                ("prometheus_equity_snapshots", "quote_source", "VARCHAR(50)"),
                ("prometheus_equity_snapshots", "calculation_method", "VARCHAR(50)"),
                ("prometheus_equity_snapshots", "total_mtm_unrealized", "DECIMAL(15, 2)"),
                ("prometheus_equity_snapshots", "total_ic_returns", "DECIMAL(15, 2)"),
                ("prometheus_equity_snapshots", "total_costs_accrued", "DECIMAL(15, 2)"),
                # Fix for logs table schema mismatch
                ("prometheus_logs", "log_time", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
                ("prometheus_logs", "level", "VARCHAR(20)"),
                ("prometheus_logs", "action", "VARCHAR(100)"),
                ("prometheus_logs", "message", "TEXT"),
                ("prometheus_logs", "details", "JSONB"),
                ("prometheus_logs", "position_id", "VARCHAR(50)"),
                ("prometheus_logs", "signal_id", "VARCHAR(50)"),
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

            # ==================================================================
            # FOREIGN KEY CONSTRAINTS - Referential Integrity
            # ==================================================================
            # These ensure data consistency across related tables.
            # Using DO NOTHING on conflict since constraint may already exist.

            foreign_keys = [
                # IC Positions → Box Spread Positions (capital source)
                (
                    "prometheus_ic_positions",
                    "fk_ic_positions_box_source",
                    "source_box_position_id",
                    "prometheus_positions(position_id)",
                    "SET NULL"  # If box spread deleted, IC position retains but loses link
                ),
                # IC Closed Trades → Box Spread Positions (capital source history)
                (
                    "prometheus_ic_closed_trades",
                    "fk_ic_closed_trades_box_source",
                    "source_box_position_id",
                    "prometheus_positions(position_id)",
                    "SET NULL"  # Preserve trade history even if box spread deleted
                ),
                # IC Signals → Box Spread Positions (capital source for signal)
                (
                    "prometheus_ic_signals",
                    "fk_ic_signals_box_source",
                    "source_box_position_id",
                    "prometheus_positions(position_id)",
                    "SET NULL"
                ),
                # Capital Deployments → Box Spread Positions
                (
                    "prometheus_capital_deployments",
                    "fk_deployments_box_source",
                    "source_box_position_id",
                    "prometheus_positions(position_id)",
                    "CASCADE"  # If box spread deleted, deployment records should go too
                ),
                # Signals → Box Spread Positions (executed position)
                (
                    "prometheus_signals",
                    "fk_signals_executed_position",
                    "executed_position_id",
                    "prometheus_positions(position_id)",
                    "SET NULL"  # Preserve signal history
                ),
            ]

            for table, constraint_name, column, references, on_delete in foreign_keys:
                try:
                    # Check if constraint already exists
                    cursor.execute("""
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = %s AND table_name = %s
                    """, (constraint_name, table))
                    if cursor.fetchone():
                        continue  # Constraint already exists

                    cursor.execute(f"""
                        ALTER TABLE {table}
                        ADD CONSTRAINT {constraint_name}
                        FOREIGN KEY ({column})
                        REFERENCES {references}
                        ON DELETE {on_delete}
                    """)
                    logger.info(f"Added foreign key {constraint_name} on {table}")
                except Exception as e:
                    # Constraint might already exist or column has invalid data
                    logger.debug(f"Foreign key {constraint_name}: {e}")

            # ==================================================================
            # DEFAULT VALUE MIGRATIONS - Reduce NULL handling in code
            # ==================================================================
            # Set DEFAULT 0 on numeric columns that currently allow NULL.
            # This reduces the need for "or 0" fallbacks throughout the codebase.

            default_value_columns = [
                # prometheus_positions - cost tracking
                ("prometheus_positions", "borrowing_cost", "0"),
                ("prometheus_positions", "implied_annual_rate", "0"),
                ("prometheus_positions", "daily_cost", "0"),
                ("prometheus_positions", "cost_accrued_to_date", "0"),
                ("prometheus_positions", "fed_funds_at_entry", "0"),
                ("prometheus_positions", "margin_rate_at_entry", "0"),
                ("prometheus_positions", "savings_vs_margin", "0"),
                ("prometheus_positions", "spot_at_entry", "0"),
                ("prometheus_positions", "vix_at_entry", "0"),
                ("prometheus_positions", "current_margin_used", "0"),
                ("prometheus_positions", "margin_cushion", "0"),
                ("prometheus_positions", "contracts", "1"),
                ("prometheus_positions", "entry_credit", "0"),
                ("prometheus_positions", "total_credit_received", "0"),
                ("prometheus_positions", "dte_at_entry", "0"),
                ("prometheus_positions", "current_dte", "0"),
                # prometheus_ic_positions - IC trading
                ("prometheus_ic_positions", "contracts", "1"),
                ("prometheus_ic_positions", "entry_credit", "0"),
                ("prometheus_ic_positions", "total_credit_received", "0"),
                ("prometheus_ic_positions", "current_value", "0"),
                ("prometheus_ic_positions", "unrealized_pnl", "0"),
                ("prometheus_ic_positions", "entry_delta", "0"),
                ("prometheus_ic_positions", "entry_vega", "0"),
                ("prometheus_ic_positions", "entry_theta", "0"),
                ("prometheus_ic_positions", "current_dte", "0"),
                ("prometheus_ic_positions", "max_profit", "0"),
                ("prometheus_ic_positions", "max_loss", "0"),
                ("prometheus_ic_positions", "profit_target_pct", "50"),
                ("prometheus_ic_positions", "stop_loss_pct", "200"),
                ("prometheus_ic_positions", "oracle_confidence_at_entry", "0"),
                # prometheus_ic_closed_trades
                ("prometheus_ic_closed_trades", "realized_pnl", "0"),
                ("prometheus_ic_closed_trades", "exit_price", "0"),
                ("prometheus_ic_closed_trades", "hold_duration_minutes", "0"),
            ]

            for table, column, default_val in default_value_columns:
                try:
                    cursor.execute(f"""
                        ALTER TABLE {table}
                        ALTER COLUMN {column} SET DEFAULT {default_val}
                    """)
                except Exception as e:
                    # Column might not exist or already has default
                    logger.debug(f"Default value for {table}.{column}: {e}")

            # Update existing NULL values to their defaults
            null_updates = [
                ("prometheus_positions", "borrowing_cost", "0"),
                ("prometheus_positions", "cost_accrued_to_date", "0"),
                ("prometheus_ic_positions", "unrealized_pnl", "0"),
                ("prometheus_ic_positions", "current_value", "0"),
            ]

            for table, column, default_val in null_updates:
                try:
                    cursor.execute(f"""
                        UPDATE {table}
                        SET {column} = {default_val}
                        WHERE {column} IS NULL
                    """)
                except Exception as e:
                    logger.debug(f"NULL update for {table}.{column}: {e}")

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

    def get_equity_curve(self, limit: int = 100, days: int = None) -> List[Dict[str, Any]]:
        """
        Get historical equity curve data.

        STANDARDS.md COMPLIANCE:
        - Query ALL closed trades (no LIMIT in SQL) to ensure accurate cumulative P&L
        - Calculate running total across all trades
        - Only limit the OUTPUT, not the SQL query
        - Date filtering happens AFTER cumulative calculation for accuracy

        Args:
            limit: Maximum number of records to return (applied to output, not SQL)
            days: If provided, filter to trades within last N days.
                  0 = today only, None = all history
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # CRITICAL: No LIMIT in SQL - query ALL closed positions
            # Then filter output only (per STANDARDS.md)
            # Use COALESCE to handle legacy records where close_time might be NULL
            cursor.execute("""
                SELECT
                    DATE(COALESCE(close_time, open_time, created_at) AT TIME ZONE 'America/Chicago') as trade_date,
                    SUM(net_profit) as daily_profit,
                    COUNT(*) as positions_closed
                FROM prometheus_positions
                WHERE status = 'closed'
                GROUP BY DATE(COALESCE(close_time, open_time, created_at) AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date ASC
            """)

            rows = cursor.fetchall()
            cursor.close()

            starting_capital = self.get_starting_capital()
            cumulative_pnl = 0
            equity_curve = []

            # Calculate date cutoff if days parameter provided
            date_cutoff = None
            if days is not None:
                if days == 0:
                    # Today only - use start of today in Central Time
                    today = datetime.now(CENTRAL_TZ).date()
                    date_cutoff = today
                else:
                    date_cutoff = (datetime.now(CENTRAL_TZ) - timedelta(days=days)).date()

            # Calculate cumulative across ALL trades for accuracy
            # But only include trades within date range in output
            for row in rows:
                trade_date = row[0]
                daily_profit = float(row[1] or 0)

                # Always add to cumulative (for accuracy)
                cumulative_pnl += daily_profit

                # Only include in output if within date range
                if date_cutoff is None or (trade_date and trade_date >= date_cutoff):
                    equity_curve.append({
                        'date': trade_date.isoformat() if trade_date else None,
                        'daily_profit': daily_profit,
                        'cumulative_pnl': cumulative_pnl,
                        'equity': starting_capital + cumulative_pnl,
                        'positions_closed': row[2],
                    })

            # Limit OUTPUT only (return most recent points)
            return equity_curve[-limit:] if len(equity_curve) > limit else equity_curve

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

    # ========== Daily Briefings Methods ==========

    def save_daily_briefing(self, briefing: Dict[str, Any]) -> bool:
        """
        Save daily briefing to database.

        This persists the daily briefing data for historical analysis
        and operational tracking.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO prometheus_daily_briefings (
                    briefing_date, briefing_time, system_status,
                    total_open_positions, total_borrowed_amount, total_cash_deployed,
                    total_margin_used, margin_remaining,
                    total_borrowing_cost_to_date, average_borrowing_rate, comparison_to_margin_rate,
                    total_ic_returns_to_date, net_profit_to_date, roi_on_strategy,
                    highest_assignment_risk_position, days_until_nearest_expiration,
                    current_box_rate, rate_vs_yesterday, rate_trend_7d,
                    recommended_actions, warnings, daily_tip
                ) VALUES (
                    %s, NOW(), %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (briefing_date)
                DO UPDATE SET
                    briefing_time = NOW(),
                    system_status = EXCLUDED.system_status,
                    total_open_positions = EXCLUDED.total_open_positions,
                    total_borrowed_amount = EXCLUDED.total_borrowed_amount,
                    total_cash_deployed = EXCLUDED.total_cash_deployed,
                    total_margin_used = EXCLUDED.total_margin_used,
                    margin_remaining = EXCLUDED.margin_remaining,
                    total_borrowing_cost_to_date = EXCLUDED.total_borrowing_cost_to_date,
                    average_borrowing_rate = EXCLUDED.average_borrowing_rate,
                    comparison_to_margin_rate = EXCLUDED.comparison_to_margin_rate,
                    total_ic_returns_to_date = EXCLUDED.total_ic_returns_to_date,
                    net_profit_to_date = EXCLUDED.net_profit_to_date,
                    roi_on_strategy = EXCLUDED.roi_on_strategy,
                    highest_assignment_risk_position = EXCLUDED.highest_assignment_risk_position,
                    days_until_nearest_expiration = EXCLUDED.days_until_nearest_expiration,
                    current_box_rate = EXCLUDED.current_box_rate,
                    rate_vs_yesterday = EXCLUDED.rate_vs_yesterday,
                    rate_trend_7d = EXCLUDED.rate_trend_7d,
                    recommended_actions = EXCLUDED.recommended_actions,
                    warnings = EXCLUDED.warnings,
                    daily_tip = EXCLUDED.daily_tip
            """, (
                briefing.get('briefing_date'),
                briefing.get('system_status'),
                briefing.get('total_open_positions', 0),
                briefing.get('total_borrowed_amount', 0),
                briefing.get('total_cash_deployed', 0),
                briefing.get('total_margin_used', 0),
                briefing.get('margin_remaining', 0),
                briefing.get('total_borrowing_cost_to_date', 0),
                briefing.get('average_borrowing_rate', 0),
                briefing.get('comparison_to_margin_rate', 0),
                briefing.get('total_ic_returns_to_date', 0),
                briefing.get('net_profit_to_date', 0),
                briefing.get('roi_on_strategy', 0),
                briefing.get('highest_assignment_risk_position', ''),
                briefing.get('days_until_nearest_expiration', 999),
                briefing.get('current_box_rate', 0),
                briefing.get('rate_vs_yesterday', 0),
                briefing.get('rate_trend_7d', 'STABLE'),
                json.dumps(briefing.get('recommended_actions', [])),
                json.dumps(briefing.get('warnings', [])),
                briefing.get('daily_tip', ''),
            ))

            conn.commit()
            cursor.close()
            logger.info(f"Saved daily briefing for {briefing.get('briefing_date')}")
            return True

        except Exception as e:
            logger.error(f"Error saving daily briefing: {e}")
            return False

    def get_daily_briefing_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical daily briefings for trend analysis"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_daily_briefings
                ORDER BY briefing_date DESC
                LIMIT %s
            """, (days,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting briefing history: {e}")
            return []

    # ========== Roll Decisions Methods ==========

    def save_roll_decision(
        self,
        position_id: str,
        current_expiration: date,
        current_dte: int,
        current_rate: float,
        target_expiration: date,
        target_dte: int,
        target_rate: float,
        roll_cost: float,
        should_roll: bool,
        reasoning: str
    ) -> bool:
        """
        Save a roll decision for audit trail.

        Tracks all roll evaluations whether executed or not.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO prometheus_roll_decisions (
                    decision_time, current_position_id,
                    current_expiration, current_dte, current_implied_rate,
                    target_expiration, target_dte, target_implied_rate,
                    roll_cost, rate_improvement, total_borrowing_extension,
                    should_roll, decision_reasoning,
                    was_executed, new_position_id
                ) VALUES (
                    NOW(), %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    FALSE, NULL
                )
            """, (
                position_id,
                current_expiration, current_dte, current_rate,
                target_expiration, target_dte, target_rate,
                roll_cost,
                target_rate - current_rate,  # rate_improvement
                target_dte - current_dte,    # borrowing extension
                should_roll, reasoning,
            ))

            conn.commit()
            cursor.close()
            logger.info(f"Saved roll decision for position {position_id}: should_roll={should_roll}")
            return True

        except Exception as e:
            logger.error(f"Error saving roll decision: {e}")
            return False

    def mark_roll_executed(self, position_id: str, new_position_id: str) -> bool:
        """Mark a roll decision as executed with the new position ID"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE prometheus_roll_decisions
                SET was_executed = TRUE, new_position_id = %s
                WHERE current_position_id = %s
                  AND was_executed = FALSE
                ORDER BY decision_time DESC
                LIMIT 1
            """, (new_position_id, position_id))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error marking roll executed: {e}")
            return False

    def get_roll_history(self, position_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get roll decision history"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if position_id:
                cursor.execute("""
                    SELECT * FROM prometheus_roll_decisions
                    WHERE current_position_id = %s
                    ORDER BY decision_time DESC
                    LIMIT %s
                """, (position_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM prometheus_roll_decisions
                    ORDER BY decision_time DESC
                    LIMIT %s
                """, (limit,))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting roll history: {e}")
            return []

    # ========== Logging Methods ==========

    def log_action(
        self,
        action: str,
        message: str,
        level: str = "INFO",
        details: Dict[str, Any] = None,
        position_id: str = None,
        signal_id: str = None,
        log_type: str = "SYSTEM"  # BOX, IC, or SYSTEM
    ) -> bool:
        """Log an action for audit trail"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_logs (
                    log_time, log_type, level, action, message, details, position_id, signal_id
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
            """, (log_type, level, action, message, json.dumps(details) if details else None,
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

    # ==========================================================================
    # IC TRADING DATABASE METHODS
    # ==========================================================================
    # These methods support PROMETHEUS's own Iron Condor trading using
    # capital borrowed via box spreads.
    # ==========================================================================

    # ========== IC Configuration Methods ==========

    def load_ic_config(self) -> PrometheusICConfig:
        """Load IC trading configuration from database or return defaults"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT config_data FROM prometheus_ic_config
                WHERE config_key = 'default'
            """)
            row = cursor.fetchone()
            cursor.close()

            if row and row[0]:
                return PrometheusICConfig.from_dict(row[0])
            return PrometheusICConfig()

        except Exception as e:
            logger.error(f"Error loading IC config: {e}")
            return PrometheusICConfig()

    def save_ic_config(self, config: PrometheusICConfig) -> bool:
        """Save IC trading configuration to database"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_ic_config (config_key, config_data, updated_at)
                VALUES ('default', %s, NOW())
                ON CONFLICT (config_key)
                DO UPDATE SET config_data = %s, updated_at = NOW()
            """, (json.dumps(config.to_dict()), json.dumps(config.to_dict())))
            conn.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Error saving IC config: {e}")
            return False

    # ========== IC Position Methods ==========

    def get_open_ic_positions(self) -> List[PrometheusICPosition]:
        """Get all open IC positions"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_ic_positions
                WHERE status IN ('open', 'pending', 'closing')
                ORDER BY open_time DESC
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            positions = []
            for row in rows:
                data = dict(zip(columns, row))
                positions.append(self._row_to_ic_position(data))
            return positions

        except Exception as e:
            logger.error(f"Error getting open IC positions: {e}")
            return []

    def get_ic_position(self, position_id: str) -> Optional[PrometheusICPosition]:
        """Get a specific IC position by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_ic_positions
                WHERE position_id = %s
            """, (position_id,))
            row = cursor.fetchone()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            if row:
                data = dict(zip(columns, row))
                return self._row_to_ic_position(data)
            return None

        except Exception as e:
            logger.error(f"Error getting IC position {position_id}: {e}")
            return None

    def save_ic_position(self, position: PrometheusICPosition) -> bool:
        """Save a new or updated IC position"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prometheus_ic_positions (
                    position_id, source_box_position_id, ticker,
                    put_short_strike, put_long_strike, put_short_symbol, put_long_symbol,
                    put_spread_order_id,
                    call_short_strike, call_long_strike, call_short_symbol, call_long_symbol,
                    call_spread_order_id,
                    spread_width, expiration, dte_at_entry, current_dte,
                    contracts, entry_credit, total_credit_received, max_loss,
                    current_value, unrealized_pnl, exit_price, realized_pnl,
                    spot_at_entry, vix_at_entry, gamma_regime_at_entry,
                    oracle_confidence, oracle_reasoning,
                    stop_loss_pct, profit_target_pct, time_stop_dte,
                    status, open_time, close_time, close_reason
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    current_dte = EXCLUDED.current_dte,
                    current_value = EXCLUDED.current_value,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    exit_price = EXCLUDED.exit_price,
                    realized_pnl = EXCLUDED.realized_pnl,
                    status = EXCLUDED.status,
                    close_time = EXCLUDED.close_time,
                    close_reason = EXCLUDED.close_reason,
                    updated_at = NOW()
            """, (
                position.position_id, position.source_box_position_id, position.ticker,
                position.put_short_strike, position.put_long_strike,
                position.put_short_symbol, position.put_long_symbol,
                position.put_spread_order_id,
                position.call_short_strike, position.call_long_strike,
                position.call_short_symbol, position.call_long_symbol,
                position.call_spread_order_id,
                position.spread_width, position.expiration, position.dte_at_entry,
                position.current_dte,
                position.contracts, position.entry_credit, position.total_credit_received,
                position.max_loss,
                position.current_value, position.unrealized_pnl,
                position.exit_price, position.realized_pnl,
                position.spot_at_entry, position.vix_at_entry, position.gamma_regime_at_entry,
                position.oracle_confidence_at_entry, position.oracle_reasoning,
                position.stop_loss_pct, position.profit_target_pct, position.time_stop_dte,
                position.status.value, position.open_time, position.close_time,
                position.close_reason
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error saving IC position: {e}")
            return False

    def close_ic_position(
        self,
        position_id: str,
        exit_price: float,
        close_reason: str
    ) -> bool:
        """
        Close an IC position and move to closed trades table.

        This method:
        1. Updates the position status to closed
        2. Calculates realized P&L
        3. Copies the record to closed_trades table
        4. Updates the source box spread's IC returns
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get current position data
            cursor.execute("""
                SELECT * FROM prometheus_ic_positions
                WHERE position_id = %s
            """, (position_id,))
            row = cursor.fetchone()

            if not row:
                logger.error(f"IC position {position_id} not found")
                return False

            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row))

            # Calculate realized P&L
            entry_credit = float(data['entry_credit'] or 0)
            contracts = int(data['contracts'] or 0)
            # P&L = (entry_credit - exit_price) × contracts × 100
            realized_pnl = (entry_credit - exit_price) * contracts * 100

            # Calculate hold duration
            open_time = data['open_time']
            now = datetime.now(CENTRAL_TZ)
            hold_duration_minutes = 0
            if open_time:
                hold_duration_minutes = int((now - open_time).total_seconds() / 60)

            # Update the position
            cursor.execute("""
                UPDATE prometheus_ic_positions
                SET status = 'closed',
                    exit_price = %s,
                    realized_pnl = %s,
                    close_time = NOW(),
                    close_reason = %s,
                    updated_at = NOW()
                WHERE position_id = %s
            """, (exit_price, realized_pnl, close_reason, position_id))

            # Insert into closed trades table
            cursor.execute("""
                INSERT INTO prometheus_ic_closed_trades (
                    position_id, source_box_position_id, ticker,
                    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                    spread_width, expiration, dte_at_entry,
                    contracts, entry_credit, exit_price, realized_pnl,
                    spot_at_entry, vix_at_entry, gamma_regime, oracle_confidence,
                    open_time, close_time, close_reason, hold_duration_minutes
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s
                )
                ON CONFLICT (position_id) DO NOTHING
            """, (
                position_id, data['source_box_position_id'], data['ticker'],
                data['put_short_strike'], data['put_long_strike'],
                data['call_short_strike'], data['call_long_strike'],
                data['spread_width'], data['expiration'], data['dte_at_entry'],
                contracts, entry_credit, exit_price, realized_pnl,
                data['spot_at_entry'], data['vix_at_entry'],
                data['gamma_regime_at_entry'], data['oracle_confidence'],
                open_time, close_reason, hold_duration_minutes
            ))

            # Update the source box spread's IC returns
            source_box_id = data['source_box_position_id']
            if source_box_id:
                cursor.execute("""
                    UPDATE prometheus_positions
                    SET total_ic_returns = COALESCE(total_ic_returns, 0) + %s,
                        net_profit = COALESCE(total_ic_returns, 0) + %s - COALESCE(borrowing_cost, 0),
                        updated_at = NOW()
                    WHERE position_id = %s
                """, (realized_pnl, realized_pnl, source_box_id))

            conn.commit()
            cursor.close()

            logger.info(
                f"Closed IC position {position_id}: exit=${exit_price:.4f}, "
                f"P&L=${realized_pnl:,.2f}, reason={close_reason}"
            )

            # Log action for audit trail (per STANDARDS.md)
            self.log_action(
                action="IC_POSITION_CLOSED",
                message=f"Closed IC position {position_id}: P&L=${realized_pnl:,.2f}",
                level="INFO",
                details={
                    'exit_price': exit_price,
                    'realized_pnl': realized_pnl,
                    'close_reason': close_reason,
                    'hold_duration_minutes': hold_duration_minutes,
                    'entry_credit': entry_credit,
                    'contracts': contracts,
                },
                position_id=position_id,
            )

            return True

        except Exception as e:
            logger.error(f"Error closing IC position {position_id}: {e}")
            return False

    def expire_ic_position(self, position_id: str, expired_worthless: bool = True) -> bool:
        """
        Mark an IC position as expired.

        If expired_worthless=True, the position is a full winner (kept all credit).
        Otherwise, some assignment/exercise occurred.
        """
        exit_price = 0.0 if expired_worthless else None
        close_reason = "Expired worthless - max profit" if expired_worthless else "Expired with exercise"

        if exit_price is None:
            # Need to calculate exit price if not worthless
            position = self.get_ic_position(position_id)
            if position:
                # This would require actual price calculation
                exit_price = position.entry_credit  # Break even as fallback
            else:
                exit_price = 0.0

        return self.close_ic_position(position_id, exit_price, close_reason)

    def _row_to_ic_position(self, data: Dict[str, Any]) -> PrometheusICPosition:
        """Convert database row to PrometheusICPosition object"""
        return PrometheusICPosition(
            position_id=data['position_id'],
            source_box_position_id=data['source_box_position_id'] or '',
            ticker=data['ticker'],
            put_short_strike=float(data['put_short_strike'] or 0),
            put_long_strike=float(data['put_long_strike'] or 0),
            call_short_strike=float(data['call_short_strike'] or 0),
            call_long_strike=float(data['call_long_strike'] or 0),
            spread_width=float(data['spread_width'] or 0),
            put_short_symbol=data['put_short_symbol'] or '',
            put_long_symbol=data['put_long_symbol'] or '',
            call_short_symbol=data['call_short_symbol'] or '',
            call_long_symbol=data['call_long_symbol'] or '',
            put_spread_order_id=data['put_spread_order_id'] or '',
            call_spread_order_id=data['call_spread_order_id'] or '',
            expiration=str(data['expiration']),
            dte_at_entry=int(data['dte_at_entry'] or 0),
            current_dte=int(data['current_dte'] or 0),
            contracts=int(data['contracts'] or 0),
            entry_credit=float(data['entry_credit'] or 0),
            total_credit_received=float(data['total_credit_received'] or 0),
            max_loss=float(data['max_loss'] or 0),
            current_value=float(data['current_value'] or 0),
            unrealized_pnl=float(data['unrealized_pnl'] or 0),
            exit_price=float(data['exit_price'] or 0),
            realized_pnl=float(data['realized_pnl'] or 0),
            spot_at_entry=float(data['spot_at_entry'] or 0),
            vix_at_entry=float(data['vix_at_entry'] or 0),
            gamma_regime_at_entry=data['gamma_regime_at_entry'] or '',
            oracle_confidence_at_entry=float(data['oracle_confidence'] or 0),
            oracle_reasoning=data['oracle_reasoning'] or '',
            status=ICPositionStatus(data['status']) if data['status'] else ICPositionStatus.OPEN,
            open_time=data['open_time'],
            close_time=data.get('close_time'),
            close_reason=data.get('close_reason', ''),
            stop_loss_pct=float(data['stop_loss_pct'] or 200),
            profit_target_pct=float(data['profit_target_pct'] or 50),
            time_stop_dte=int(data['time_stop_dte'] or 0),
        )

    # ========== IC Signal Methods ==========

    def log_ic_signal(
        self,
        signal: PrometheusICSignal,
        was_executed: bool,
        executed_position_id: str = None
    ) -> bool:
        """Log a generated IC signal (UPSERT - updates if signal already exists)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Use UPSERT to handle case where signal is logged first as SKIPPED,
            # then updated to EXECUTED when trade goes through
            cursor.execute("""
                INSERT INTO prometheus_ic_signals (
                    signal_id, signal_time, source_box_position_id,
                    ticker, spot_price,
                    put_short_strike, put_long_strike, put_spread_credit,
                    call_short_strike, call_long_strike, call_spread_credit,
                    expiration, dte, total_credit, max_loss,
                    probability_of_profit, delta_of_short_put, delta_of_short_call,
                    contracts, margin_required, capital_at_risk,
                    oracle_approved, oracle_confidence, oracle_reasoning,
                    vix_level, gamma_regime, gex_regime,
                    was_executed, skip_reason, executed_position_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (signal_id) DO UPDATE SET
                    was_executed = EXCLUDED.was_executed,
                    executed_position_id = EXCLUDED.executed_position_id,
                    skip_reason = EXCLUDED.skip_reason
            """, (
                signal.signal_id, signal.signal_time, signal.source_box_position_id,
                signal.ticker, signal.spot_price,
                signal.put_short_strike, signal.put_long_strike, signal.put_spread_credit,
                signal.call_short_strike, signal.call_long_strike, signal.call_spread_credit,
                signal.expiration, signal.dte, signal.total_credit, signal.max_loss,
                signal.probability_of_profit, signal.delta_of_short_put, signal.delta_of_short_call,
                signal.contracts, signal.margin_required, signal.capital_at_risk,
                signal.oracle_approved, signal.oracle_confidence, signal.oracle_reasoning,
                signal.vix_level, signal.gamma_regime, signal.gex_regime,
                was_executed, signal.skip_reason if not was_executed else '',
                executed_position_id
            ))
            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error logging IC signal: {e}")
            return False

    def get_recent_ic_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent IC signals for display"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_ic_signals
                ORDER BY signal_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting IC signals: {e}")
            return []

    # ========== IC Closed Trades Methods ==========

    def get_ic_closed_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get closed IC trades history"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM prometheus_ic_closed_trades
                ORDER BY close_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting closed IC trades: {e}")
            return []

    # ========== IC Performance Methods ==========

    def get_ic_performance(self) -> Dict[str, Any]:
        """Get IC trading performance metrics"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get closed trades stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
                    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losers,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl,
                    SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as total_wins,
                    SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) as total_losses,
                    AVG(hold_duration_minutes) as avg_hold_minutes,
                    MAX(realized_pnl) as best_trade,
                    MIN(realized_pnl) as worst_trade
                FROM prometheus_ic_closed_trades
            """)
            closed_stats = cursor.fetchone()

            # Get open positions stats
            cursor.execute("""
                SELECT
                    COUNT(*) as open_count,
                    SUM(unrealized_pnl) as total_unrealized,
                    SUM(total_credit_received) as total_credit_outstanding
                FROM prometheus_ic_positions
                WHERE status IN ('open', 'pending')
            """)
            open_stats = cursor.fetchone()

            # Get today's stats
            cursor.execute("""
                SELECT
                    COUNT(*) as trades_today,
                    SUM(realized_pnl) as pnl_today
                FROM prometheus_ic_closed_trades
                WHERE DATE(close_time AT TIME ZONE 'America/Chicago') =
                      DATE(NOW() AT TIME ZONE 'America/Chicago')
            """)
            today_stats = cursor.fetchone()

            # Get streak data
            cursor.execute("""
                SELECT realized_pnl > 0 as is_win
                FROM prometheus_ic_closed_trades
                ORDER BY close_time DESC
                LIMIT 20
            """)
            recent_results = cursor.fetchall()

            cursor.close()

            # Calculate streaks
            current_streak = 0
            current_streak_type = None
            max_win_streak = 0
            max_loss_streak = 0
            win_streak = 0
            loss_streak = 0

            for (is_win,) in recent_results:
                if current_streak_type is None:
                    current_streak_type = is_win
                    current_streak = 1
                elif is_win == current_streak_type:
                    current_streak += 1
                else:
                    break

            for (is_win,) in recent_results:
                if is_win:
                    win_streak += 1
                    loss_streak = 0
                    max_win_streak = max(max_win_streak, win_streak)
                else:
                    loss_streak += 1
                    win_streak = 0
                    max_loss_streak = max(max_loss_streak, loss_streak)

            total_trades = int(closed_stats[0] or 0)
            winners = int(closed_stats[1] or 0)
            losers = int(closed_stats[2] or 0)
            win_rate = winners / total_trades if total_trades > 0 else 0

            total_wins = float(closed_stats[5] or 0)
            total_losses = float(closed_stats[6] or 0)
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            return {
                'closed_trades': {
                    'total': total_trades,
                    'winners': winners,
                    'losers': losers,
                    'win_rate': win_rate,
                    'total_pnl': float(closed_stats[3] or 0),
                    'avg_pnl': float(closed_stats[4] or 0),
                    'total_wins': total_wins,
                    'total_losses': total_losses,
                    'profit_factor': profit_factor,
                    'avg_hold_minutes': float(closed_stats[7] or 0),
                    'best_trade': float(closed_stats[8] or 0),
                    'worst_trade': float(closed_stats[9] or 0),
                },
                'open_positions': {
                    'count': int(open_stats[0] or 0),
                    'unrealized_pnl': float(open_stats[1] or 0),
                    'credit_outstanding': float(open_stats[2] or 0),
                },
                'today': {
                    'trades': int(today_stats[0] or 0),
                    'pnl': float(today_stats[1] or 0),
                },
                'streaks': {
                    'current': current_streak,
                    'current_type': 'win' if current_streak_type else 'loss',
                    'max_win_streak': max_win_streak,
                    'max_loss_streak': max_loss_streak,
                },
            }

        except Exception as e:
            logger.error(f"Error getting IC performance: {e}")
            return {}

    def get_ic_equity_curve(self, limit: int = 100, days: int = None) -> List[Dict[str, Any]]:
        """
        Get IC trading equity curve data.

        STANDARDS.md COMPLIANCE:
        - Query ALL closed trades (no LIMIT in SQL) to ensure accurate cumulative P&L
        - Calculate running total across all trades
        - Only limit the OUTPUT, not the SQL query
        - Include equity (starting capital + cumulative)

        Args:
            limit: Maximum number of records to return (applied to output, not SQL)
            days: If provided, filter to trades within last N days.
                  0 = today only (intraday), None = all history
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # CRITICAL: No LIMIT in SQL - query ALL closed trades
            # Then filter output only (per STANDARDS.md)
            # Date filtering happens AFTER cumulative calculation for accuracy
            # Use COALESCE to handle legacy records where close_time might be NULL
            cursor.execute("""
                SELECT
                    COALESCE(close_time, open_time, created_at) as effective_close_time,
                    realized_pnl,
                    position_id
                FROM prometheus_ic_closed_trades
                ORDER BY COALESCE(close_time, open_time, created_at) ASC
            """)

            rows = cursor.fetchall()
            cursor.close()

            # Get IC starting capital from config (load_ic_config always returns object with defaults)
            ic_config = self.load_ic_config()
            starting_capital = ic_config.starting_capital

            cumulative_pnl = 0
            equity_curve = []

            # Calculate date cutoff if days parameter provided
            date_cutoff = None
            if days is not None:
                if days == 0:
                    # Today only - use start of today in Central Time
                    today = datetime.now(CENTRAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
                    date_cutoff = today
                else:
                    date_cutoff = datetime.now(CENTRAL_TZ) - timedelta(days=days)

            # Calculate cumulative across ALL trades for accuracy
            # But only include trades within date range in output
            for row in rows:
                trade_time = row[0]
                trade_pnl = float(row[1] or 0)

                # Always add to cumulative (for accuracy)
                cumulative_pnl += trade_pnl

                # Only include in output if within date range
                if date_cutoff is None or (trade_time and trade_time >= date_cutoff):
                    equity_curve.append({
                        'time': trade_time.isoformat() if trade_time else None,
                        'date': trade_time.strftime('%Y-%m-%d') if trade_time else None,
                        'trade_pnl': trade_pnl,
                        'cumulative_pnl': cumulative_pnl,
                        'equity': starting_capital + cumulative_pnl,
                        'position_id': row[2],
                    })

            # Limit OUTPUT only (return most recent points)
            return equity_curve[-limit:] if len(equity_curve) > limit else equity_curve

        except Exception as e:
            logger.error(f"Error getting IC equity curve: {e}")
            return []

    def get_daily_ic_trades_count(self) -> int:
        """Get number of IC trades made today (for daily limit checking)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM prometheus_ic_positions
                WHERE DATE(open_time AT TIME ZONE 'America/Chicago') =
                      DATE(NOW() AT TIME ZONE 'America/Chicago')
            """)
            count = cursor.fetchone()[0]
            cursor.close()
            return int(count or 0)

        except Exception as e:
            logger.error(f"Error getting daily IC trade count: {e}")
            return 0

    def get_last_ic_trade_time(self) -> Optional[datetime]:
        """Get the time of the last IC trade (for cooldown checking)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT open_time FROM prometheus_ic_positions
                ORDER BY open_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            cursor.close()
            return row[0] if row else None

        except Exception as e:
            logger.error(f"Error getting last IC trade time: {e}")
            return None

    def get_last_ic_trade_result(self) -> Optional[Dict[str, Any]]:
        """Get the result of the last closed IC trade (for cooldown logic)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT position_id, realized_pnl, close_time, close_reason
                FROM prometheus_ic_closed_trades
                ORDER BY close_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    'position_id': row[0],
                    'realized_pnl': float(row[1] or 0),
                    'close_time': row[2],
                    'close_reason': row[3],
                    'was_winner': float(row[1] or 0) > 0,
                }
            return None

        except Exception as e:
            logger.error(f"Error getting last IC trade result: {e}")
            return None

    # ========== Combined Performance Summary ==========

    def get_combined_performance_summary(self) -> PrometheusPerformanceSummary:
        """
        Get combined performance for both box spreads and IC trading.

        This is the key metric: Are IC returns > borrowing costs?
        """
        try:
            box_perf = self.get_performance_summary()
            ic_perf = self.get_ic_performance()

            now = datetime.now(CENTRAL_TZ)

            # Box spread metrics
            total_box = box_perf.get('closed_positions', {}).get('total', 0) + \
                        box_perf.get('open_positions', {}).get('total', 0)
            total_borrowed = box_perf.get('open_positions', {}).get('total_borrowed', 0) + \
                            box_perf.get('closed_positions', {}).get('total_pnl', 0)  # approximate
            total_borrowing_cost = box_perf.get('closed_positions', {}).get('total_borrowing_cost', 0) + \
                                   box_perf.get('open_positions', {}).get('accrued_costs', 0)
            avg_rate = box_perf.get('closed_positions', {}).get('avg_implied_rate', 0)

            # IC metrics
            ic_closed = ic_perf.get('closed_trades', {})
            total_ic_trades = ic_closed.get('total', 0)
            ic_win_rate = ic_closed.get('win_rate', 0)
            total_ic_premium = ic_closed.get('total_wins', 0)  # Total premium collected
            total_ic_realized = ic_closed.get('total_pnl', 0)
            total_ic_unrealized = ic_perf.get('open_positions', {}).get('unrealized_pnl', 0)
            avg_ic_return = ic_closed.get('avg_pnl', 0)

            # Combined
            net_profit = total_ic_realized - total_borrowing_cost
            roi = net_profit / total_borrowed if total_borrowed > 0 else 0

            # Approximate monthly return
            monthly_return = roi * 30 / 365  # Rough annualization

            return PrometheusPerformanceSummary(
                summary_time=now,
                total_box_positions=total_box,
                total_borrowed=total_borrowed,
                total_borrowing_cost=total_borrowing_cost,
                average_borrowing_rate=avg_rate,
                borrowing_cost_to_date=total_borrowing_cost,
                total_ic_trades=total_ic_trades,
                ic_win_rate=ic_win_rate,
                total_ic_premium_collected=total_ic_premium,
                total_ic_realized_pnl=total_ic_realized,
                total_ic_unrealized_pnl=total_ic_unrealized,
                average_ic_return_per_trade=avg_ic_return,
                net_profit=net_profit,
                roi_on_borrowed_capital=roi,
                monthly_return_rate=monthly_return,
                max_drawdown=0,  # Would need more complex calculation
                sharpe_ratio=0,  # Would need daily returns
                win_streak=ic_perf.get('streaks', {}).get('max_win_streak', 0),
                loss_streak=ic_perf.get('streaks', {}).get('max_loss_streak', 0),
                vs_margin_borrowing=total_borrowed * 0.03,  # Assume 3% margin savings
                vs_buy_and_hold_spx=0,  # Would need SPX tracking
            )

        except Exception as e:
            logger.error(f"Error getting combined performance: {e}")
            return PrometheusPerformanceSummary(
                summary_time=datetime.now(CENTRAL_TZ),
                total_box_positions=0,
                total_borrowed=0,
                total_borrowing_cost=0,
                average_borrowing_rate=0,
                borrowing_cost_to_date=0,
                total_ic_trades=0,
                ic_win_rate=0,
                total_ic_premium_collected=0,
                total_ic_realized_pnl=0,
                total_ic_unrealized_pnl=0,
                average_ic_return_per_trade=0,
                net_profit=0,
                roi_on_borrowed_capital=0,
                monthly_return_rate=0,
                max_drawdown=0,
                sharpe_ratio=0,
                win_streak=0,
                loss_streak=0,
                vs_margin_borrowing=0,
                vs_buy_and_hold_spx=0,
            )

    # ========== IC Intraday Equity & Logs ==========

    def record_ic_equity_snapshot(self) -> bool:
        """
        Record an intraday equity snapshot for IC trading.

        STANDARDS.md COMPLIANCE:
        - Records equity snapshots during trading for intraday tracking
        - Includes unrealized P&L from open positions
        - Uses prometheus_ic_equity_snapshots table
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Table created in _ensure_tables() - no lazy creation needed

            # Get IC config for starting capital (load_ic_config always returns object with defaults)
            ic_config = self.load_ic_config()
            starting_capital = ic_config.starting_capital

            # Get total realized P&L from closed trades
            cursor.execute("""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM prometheus_ic_closed_trades
            """)
            total_realized = float(cursor.fetchone()[0] or 0)

            # Get unrealized P&L from open positions
            cursor.execute("""
                SELECT COALESCE(SUM(unrealized_pnl), 0), COUNT(*)
                FROM prometheus_ic_positions
                WHERE status = 'open'
            """)
            row = cursor.fetchone()
            total_unrealized = float(row[0] or 0)
            open_count = int(row[1] or 0)

            # Calculate total equity
            total_equity = starting_capital + total_realized + total_unrealized

            # Get open position details
            cursor.execute("""
                SELECT position_id, unrealized_pnl, current_value
                FROM prometheus_ic_positions
                WHERE status = 'open'
            """)
            position_details = [
                {
                    'position_id': r[0],
                    'unrealized_pnl': float(r[1] or 0),
                    'current_value': float(r[2] or 0),
                }
                for r in cursor.fetchall()
            ]

            # Insert snapshot
            cursor.execute("""
                INSERT INTO prometheus_ic_equity_snapshots (
                    snapshot_time, total_equity, starting_capital,
                    total_realized_pnl, total_unrealized_pnl,
                    open_position_count, details
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s)
            """, (total_equity, starting_capital, total_realized,
                  total_unrealized, open_count, json.dumps(position_details)))

            conn.commit()
            cursor.close()

            logger.info(f"IC equity snapshot recorded: equity=${total_equity:,.2f}, "
                       f"unrealized=${total_unrealized:,.2f}")
            return True

        except Exception as e:
            logger.error(f"Error recording IC equity snapshot: {e}")
            return False

    def get_ic_intraday_equity(self) -> List[Dict[str, Any]]:
        """
        Get today's IC equity snapshots for intraday tracking.

        STANDARDS.md COMPLIANCE:
        - Returns snapshots for current trading day
        - Used by /ic/equity-curve/intraday endpoint
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Table created in _ensure_tables() - no lazy creation needed

            # Get today's snapshots
            cursor.execute("""
                SELECT
                    snapshot_time,
                    total_equity,
                    starting_capital,
                    total_realized_pnl,
                    total_unrealized_pnl,
                    open_position_count,
                    details
                FROM prometheus_ic_equity_snapshots
                WHERE DATE(snapshot_time AT TIME ZONE 'America/Chicago') =
                      DATE(NOW() AT TIME ZONE 'America/Chicago')
                ORDER BY snapshot_time ASC
            """)

            rows = cursor.fetchall()
            cursor.close()

            return [
                {
                    'time': row[0].isoformat() if row[0] else None,
                    'total_equity': float(row[1] or 0),
                    'starting_capital': float(row[2] or 0),
                    'realized_pnl': float(row[3] or 0),
                    'unrealized_pnl': float(row[4] or 0),
                    'open_positions': int(row[5] or 0),
                    'details': row[6] if row[6] else [],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error getting IC intraday equity: {e}")
            return []

    def get_recent_ic_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent IC-related activity logs.

        STANDARDS.md COMPLIANCE:
        - Returns activity log for IC trading actions
        - Used by /ic/logs endpoint
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get logs with IC-related actions
            cursor.execute("""
                SELECT
                    id, log_time, level, action, message, details, position_id, signal_id
                FROM prometheus_logs
                WHERE action LIKE 'IC_%'
                   OR action IN ('SIGNAL_EXECUTED', 'POSITION_OPENED', 'POSITION_CLOSED',
                                 'MTM_UPDATE', 'EXIT_CHECK', 'STOP_LOSS', 'PROFIT_TARGET',
                                 'TIME_STOP', 'EXPIRATION')
                ORDER BY log_time DESC
                LIMIT %s
            """, (limit,))

            rows = cursor.fetchall()
            cursor.close()

            return [
                {
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'level': row[2],
                    'action': row[3],
                    'message': row[4],
                    'details': row[5] if row[5] else {},
                    'position_id': row[6],
                    'signal_id': row[7],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error getting IC logs: {e}")
            return []
