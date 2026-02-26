"""
IronForge Table Setup (PostgreSQL)
===================================

Creates all required PostgreSQL tables for FLAME and SPARK bots.
Run this once to initialize the schema.

Usage:
    python setup_tables.py
"""

import logging
import sys

try:
    from databricks.config import DatabricksConfig
    from databricks.trading.db_adapter import db_connection, table
except ImportError:
    from config import DatabricksConfig
    from trading.db_adapter import db_connection, table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ============================================================================
# Table definitions for both FLAME and SPARK
# ============================================================================

def _position_table_ddl(bot: str) -> str:
    """DDL for the main positions table (parameterized by bot name)."""
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_positions')} (
        id BIGSERIAL PRIMARY KEY,
        position_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
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
        contracts INT NOT NULL,
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
        gex_regime TEXT,
        flip_point DECIMAL(10, 2),
        net_gex DECIMAL(15, 2),

        -- Oracle context
        oracle_confidence DECIMAL(5, 4),
        oracle_win_probability DECIMAL(8, 4),
        oracle_advice TEXT,
        oracle_reasoning TEXT,
        oracle_top_factors TEXT,
        oracle_use_gex_walls BOOLEAN DEFAULT FALSE,

        -- Wing symmetry tracking
        wings_adjusted BOOLEAN DEFAULT FALSE,
        original_put_width DECIMAL(10, 2),
        original_call_width DECIMAL(10, 2),

        -- Order tracking
        put_order_id TEXT DEFAULT 'PAPER',
        call_order_id TEXT DEFAULT 'PAPER',

        -- Status
        status TEXT NOT NULL DEFAULT 'open',
        open_time TIMESTAMP NOT NULL,
        open_date DATE,
        close_time TIMESTAMP,
        close_price DECIMAL(10, 4),
        close_reason TEXT,
        realized_pnl DECIMAL(10, 2),

        -- DTE mode ('2DTE' or '1DTE')
        dte_mode TEXT DEFAULT '2DTE',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """


def _signals_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_signals')} (
        id BIGSERIAL PRIMARY KEY,
        signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        spot_price DECIMAL(10, 2),
        vix DECIMAL(6, 2),
        expected_move DECIMAL(10, 2),
        call_wall DECIMAL(10, 2),
        put_wall DECIMAL(10, 2),
        gex_regime TEXT,
        put_short DECIMAL(10, 2),
        put_long DECIMAL(10, 2),
        call_short DECIMAL(10, 2),
        call_long DECIMAL(10, 2),
        total_credit DECIMAL(10, 4),
        confidence DECIMAL(5, 4),
        was_executed BOOLEAN DEFAULT FALSE,
        skip_reason TEXT,
        reasoning TEXT,
        wings_adjusted BOOLEAN DEFAULT FALSE,
        dte_mode TEXT DEFAULT '2DTE'
    )
    """


def _daily_perf_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_daily_perf')} (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL UNIQUE,
        trades_executed INT DEFAULT 0,
        positions_closed INT DEFAULT 0,
        realized_pnl DECIMAL(10, 2) DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """


def _logs_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_logs')} (
        id BIGSERIAL PRIMARY KEY,
        log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        level TEXT,
        message TEXT,
        details TEXT,
        dte_mode TEXT DEFAULT '2DTE'
    )
    """


def _equity_snapshots_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_equity_snapshots')} (
        id BIGSERIAL PRIMARY KEY,
        snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        balance DECIMAL(12, 2) NOT NULL,
        unrealized_pnl DECIMAL(12, 2) DEFAULT 0,
        realized_pnl DECIMAL(12, 2) DEFAULT 0,
        open_positions INT DEFAULT 0,
        note TEXT,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """


def _paper_account_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_paper_account')} (
        id BIGSERIAL PRIMARY KEY,
        starting_capital DECIMAL(12, 2) NOT NULL,
        current_balance DECIMAL(12, 2) NOT NULL,
        cumulative_pnl DECIMAL(12, 2) DEFAULT 0,
        total_trades INT DEFAULT 0,
        collateral_in_use DECIMAL(12, 2) DEFAULT 0,
        buying_power DECIMAL(12, 2) NOT NULL,
        high_water_mark DECIMAL(12, 2) NOT NULL,
        max_drawdown DECIMAL(12, 2) DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """


def _pdt_log_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table(f'{bot}_pdt_log')} (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        symbol TEXT NOT NULL,
        position_id TEXT NOT NULL,
        opened_at TIMESTAMP NOT NULL,
        closed_at TIMESTAMP,
        is_day_trade BOOLEAN DEFAULT FALSE,
        contracts INT NOT NULL,
        entry_credit DECIMAL(10, 4),
        exit_cost DECIMAL(10, 4),
        pnl DECIMAL(10, 2),
        close_reason TEXT,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """


def _heartbeats_table_ddl() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table('bot_heartbeats')} (
        bot_name TEXT NOT NULL UNIQUE,
        last_heartbeat TIMESTAMP,
        status TEXT,
        scan_count BIGINT DEFAULT 0,
        details TEXT
    )
    """


def setup_all_tables():
    """Create all PostgreSQL tables for FLAME and SPARK."""
    valid, msg = DatabricksConfig.validate()
    if not valid:
        logger.error(f"Configuration invalid: {msg}")
        sys.exit(1)

    logger.info("Setting up IronForge tables in PostgreSQL")

    with db_connection() as conn:
        cursor = conn.cursor()

        # Create tables for both bots
        for bot in ['flame', 'spark']:
            logger.info(f"Creating tables for {bot.upper()}...")

            ddl_funcs = [
                _position_table_ddl,
                _signals_table_ddl,
                _daily_perf_table_ddl,
                _logs_table_ddl,
                _equity_snapshots_table_ddl,
                _paper_account_table_ddl,
                _pdt_log_table_ddl,
            ]

            for ddl_func in ddl_funcs:
                ddl = ddl_func(bot)
                cursor.execute(ddl)
                logger.info(f"  {bot}_{ddl_func.__name__.replace('_table_ddl', '')} OK")

        # Shared heartbeats table
        cursor.execute(_heartbeats_table_ddl())
        logger.info("  bot_heartbeats OK")

        conn.commit()

    logger.info("All tables created successfully.")


if __name__ == "__main__":
    setup_all_tables()
