"""
PostgreSQL Table Setup
=======================

Creates all required tables for FLAME and SPARK bots (IronForge on Render).

Usage:
    python setup_tables.py
"""

import logging
import sys

from config import Config
from trading.db_adapter import db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _position_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_positions (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        position_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        expiration DATE NOT NULL,

        put_short_strike NUMERIC(10, 2) NOT NULL,
        put_long_strike NUMERIC(10, 2) NOT NULL,
        put_credit NUMERIC(10, 4) NOT NULL,

        call_short_strike NUMERIC(10, 2) NOT NULL,
        call_long_strike NUMERIC(10, 2) NOT NULL,
        call_credit NUMERIC(10, 4) NOT NULL,

        contracts INT NOT NULL,
        spread_width NUMERIC(10, 2) NOT NULL,
        total_credit NUMERIC(10, 4) NOT NULL,
        max_loss NUMERIC(10, 2) NOT NULL,
        max_profit NUMERIC(10, 2) NOT NULL,
        collateral_required NUMERIC(10, 2) DEFAULT 0,

        underlying_at_entry NUMERIC(10, 2) NOT NULL,
        vix_at_entry NUMERIC(6, 2),
        expected_move NUMERIC(10, 2),
        call_wall NUMERIC(10, 2),
        put_wall NUMERIC(10, 2),
        gex_regime TEXT,
        flip_point NUMERIC(10, 2),
        net_gex NUMERIC(15, 2),

        oracle_confidence NUMERIC(5, 4),
        oracle_win_probability NUMERIC(8, 4),
        oracle_advice TEXT,
        oracle_reasoning TEXT,
        oracle_top_factors TEXT,
        oracle_use_gex_walls BOOLEAN DEFAULT FALSE,

        wings_adjusted BOOLEAN DEFAULT FALSE,
        original_put_width NUMERIC(10, 2),
        original_call_width NUMERIC(10, 2),

        put_order_id TEXT DEFAULT 'PAPER',
        call_order_id TEXT DEFAULT 'PAPER',
        sandbox_order_id TEXT,
        sandbox_close_order_id TEXT,

        status TEXT NOT NULL DEFAULT 'open',
        open_time TIMESTAMPTZ NOT NULL,
        open_date DATE,
        close_time TIMESTAMPTZ,
        close_price NUMERIC(10, 4),
        close_reason TEXT,
        realized_pnl NUMERIC(10, 2),

        dte_mode TEXT DEFAULT '2DTE',

        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _signals_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_signals (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        signal_time TIMESTAMPTZ DEFAULT NOW(),
        spot_price NUMERIC(10, 2),
        vix NUMERIC(6, 2),
        expected_move NUMERIC(10, 2),
        call_wall NUMERIC(10, 2),
        put_wall NUMERIC(10, 2),
        gex_regime TEXT,
        put_short NUMERIC(10, 2),
        put_long NUMERIC(10, 2),
        call_short NUMERIC(10, 2),
        call_long NUMERIC(10, 2),
        total_credit NUMERIC(10, 4),
        confidence NUMERIC(5, 4),
        was_executed BOOLEAN DEFAULT FALSE,
        skip_reason TEXT,
        reasoning TEXT,
        wings_adjusted BOOLEAN DEFAULT FALSE,
        dte_mode TEXT DEFAULT '2DTE'
    )
    """


def _daily_perf_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_daily_perf (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        trade_date DATE NOT NULL UNIQUE,
        trades_executed INT DEFAULT 0,
        positions_closed INT DEFAULT 0,
        realized_pnl NUMERIC(10, 2) DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _logs_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_logs (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        log_time TIMESTAMPTZ DEFAULT NOW(),
        level TEXT,
        message TEXT,
        details TEXT,
        dte_mode TEXT DEFAULT '2DTE'
    )
    """


def _equity_snapshots_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_equity_snapshots (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        snapshot_time TIMESTAMPTZ DEFAULT NOW(),
        balance NUMERIC(12, 2) NOT NULL,
        unrealized_pnl NUMERIC(12, 2) DEFAULT 0,
        realized_pnl NUMERIC(12, 2) DEFAULT 0,
        open_positions INT DEFAULT 0,
        note TEXT,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _paper_account_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_paper_account (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        starting_capital NUMERIC(12, 2) NOT NULL,
        current_balance NUMERIC(12, 2) NOT NULL,
        cumulative_pnl NUMERIC(12, 2) DEFAULT 0,
        total_trades INT DEFAULT 0,
        collateral_in_use NUMERIC(12, 2) DEFAULT 0,
        buying_power NUMERIC(12, 2) NOT NULL,
        high_water_mark NUMERIC(12, 2) NOT NULL,
        max_drawdown NUMERIC(12, 2) DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _pdt_log_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_pdt_log (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        trade_date DATE NOT NULL,
        symbol TEXT NOT NULL,
        position_id TEXT NOT NULL,
        opened_at TIMESTAMPTZ NOT NULL,
        closed_at TIMESTAMPTZ,
        is_day_trade BOOLEAN DEFAULT FALSE,
        contracts INT NOT NULL,
        entry_credit NUMERIC(10, 4),
        exit_cost NUMERIC(10, 4),
        pnl NUMERIC(10, 2),
        close_reason TEXT,
        dte_mode TEXT DEFAULT '2DTE',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _config_table_ddl(bot: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {bot}_config (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        dte_mode TEXT NOT NULL UNIQUE,
        sd_multiplier NUMERIC(5, 2) DEFAULT 1.2,
        spread_width NUMERIC(5, 2) DEFAULT 5.0,
        min_credit NUMERIC(5, 4) DEFAULT 0.05,
        profit_target_pct NUMERIC(5, 2) DEFAULT 30.0,
        stop_loss_pct NUMERIC(5, 2) DEFAULT 100.0,
        vix_skip NUMERIC(5, 2) DEFAULT 32.0,
        max_contracts INT DEFAULT 10,
        max_trades_per_day INT DEFAULT 1,
        buying_power_usage_pct NUMERIC(5, 4) DEFAULT 0.85,
        risk_per_trade_pct NUMERIC(5, 4) DEFAULT 0.15,
        min_win_probability NUMERIC(5, 4) DEFAULT 0.42,
        entry_start TEXT DEFAULT '08:30',
        entry_end TEXT DEFAULT '14:00',
        eod_cutoff_et TEXT DEFAULT '15:45',
        pdt_max_day_trades INT DEFAULT 3,
        starting_capital NUMERIC(12, 2) DEFAULT 10000.0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """


def _heartbeats_table_ddl() -> str:
    return """
    CREATE TABLE IF NOT EXISTS bot_heartbeats (
        bot_name TEXT NOT NULL PRIMARY KEY,
        last_heartbeat TIMESTAMPTZ,
        status TEXT,
        scan_count BIGINT DEFAULT 0,
        details TEXT
    )
    """


def setup_all_tables():
    """Create all PostgreSQL tables for FLAME and SPARK."""
    valid, msg = Config.validate()
    if not valid:
        logger.error(f"Configuration invalid: {msg}")
        sys.exit(1)

    logger.info("Setting up IronForge tables in PostgreSQL")

    with db_connection() as conn:
        cursor = conn.cursor()

        for bot in ['flame', 'spark', 'inferno']:
            logger.info(f"Creating tables for {bot.upper()}...")

            ddl_funcs = [
                _position_table_ddl,
                _signals_table_ddl,
                _daily_perf_table_ddl,
                _logs_table_ddl,
                _equity_snapshots_table_ddl,
                _paper_account_table_ddl,
                _pdt_log_table_ddl,
                _config_table_ddl,
            ]

            for ddl_func in ddl_funcs:
                ddl = ddl_func(bot)
                cursor.execute(ddl)
                name = ddl_func.__name__.replace('_table_ddl', '')
                logger.info(f"  {bot}_{name} OK")

        cursor.execute(_heartbeats_table_ddl())
        logger.info("  bot_heartbeats OK")

        # Migrations: add columns that may not exist on older deployments
        for bot in ['flame', 'spark', 'inferno']:
            cursor.execute(f"""
                ALTER TABLE {bot}_positions
                ADD COLUMN IF NOT EXISTS sandbox_order_id TEXT
            """)
            cursor.execute(f"""
                ALTER TABLE {bot}_positions
                ADD COLUMN IF NOT EXISTS sandbox_close_order_id TEXT
            """)
        logger.info("  sandbox_order_id migration OK")

    logger.info("All tables created successfully.")


if __name__ == "__main__":
    setup_all_tables()
