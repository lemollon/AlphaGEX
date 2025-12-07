#!/usr/bin/env python3
"""
Create Backtest Database Schema

Creates all tables needed for ORAT options data and price history.
Can be used with existing database or a separate backtest database.

Usage:
    python scripts/create_backtest_schema.py
"""

import os
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def create_schema():
    """Create backtest database schema"""
    try:
        from database_adapter import get_connection
    except ImportError:
        print("❌ Database adapter not available")
        print("   Set DATABASE_URL environment variable")
        return False

    print("=" * 70)
    print("📊 CREATING BACKTEST DATABASE SCHEMA")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    tables = []

    # =========================================================================
    # TABLE 1: ORAT Options EOD Data
    # =========================================================================
    tables.append(('orat_options_eod', """
        CREATE TABLE IF NOT EXISTS orat_options_eod (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            expiration_date DATE,
            strike DECIMAL(10,2) NOT NULL,
            option_type VARCHAR(10) DEFAULT 'BOTH',

            -- Call prices
            call_bid DECIMAL(10,4),
            call_ask DECIMAL(10,4),
            call_mid DECIMAL(10,4),

            -- Put prices
            put_bid DECIMAL(10,4),
            put_ask DECIMAL(10,4),
            put_mid DECIMAL(10,4),

            -- Greeks (from ORAT, applies to ATM or specific delta)
            delta DECIMAL(10,6),
            gamma DECIMAL(10,6),
            theta DECIMAL(10,4),
            vega DECIMAL(10,4),
            rho DECIMAL(10,6),

            -- Implied Volatility
            call_iv DECIMAL(10,6),
            put_iv DECIMAL(10,6),

            -- Underlying
            underlying_price DECIMAL(10,2),
            dte INTEGER,

            -- Volume and Open Interest
            call_volume INTEGER DEFAULT 0,
            put_volume INTEGER DEFAULT 0,
            call_oi INTEGER DEFAULT 0,
            put_oi INTEGER DEFAULT 0,

            -- Metadata
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            -- Unique constraint
            UNIQUE(trade_date, ticker, expiration_date, strike)
        );

        -- Indexes for fast queries
        CREATE INDEX IF NOT EXISTS idx_orat_options_date ON orat_options_eod(trade_date);
        CREATE INDEX IF NOT EXISTS idx_orat_options_ticker ON orat_options_eod(ticker);
        CREATE INDEX IF NOT EXISTS idx_orat_options_exp ON orat_options_eod(expiration_date);
        CREATE INDEX IF NOT EXISTS idx_orat_options_dte ON orat_options_eod(dte);
        CREATE INDEX IF NOT EXISTS idx_orat_options_strike ON orat_options_eod(strike);
        CREATE INDEX IF NOT EXISTS idx_orat_options_date_ticker ON orat_options_eod(trade_date, ticker);
        CREATE INDEX IF NOT EXISTS idx_orat_options_0dte ON orat_options_eod(trade_date, ticker, dte) WHERE dte <= 1;
    """))

    # =========================================================================
    # TABLE 2: Underlying Prices (SPX, SPY)
    # =========================================================================
    tables.append(('underlying_prices', """
        CREATE TABLE IF NOT EXISTS underlying_prices (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            open DECIMAL(10,2),
            high DECIMAL(10,2),
            low DECIMAL(10,2),
            close DECIMAL(10,2),
            volume BIGINT DEFAULT 0,
            vwap DECIMAL(10,2),
            source VARCHAR(20) DEFAULT 'polygon',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(trade_date, symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_underlying_date ON underlying_prices(trade_date);
        CREATE INDEX IF NOT EXISTS idx_underlying_symbol ON underlying_prices(symbol);
    """))

    # =========================================================================
    # TABLE 3: VIX History
    # =========================================================================
    tables.append(('vix_history', """
        CREATE TABLE IF NOT EXISTS vix_history (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL UNIQUE,
            open DECIMAL(8,2),
            high DECIMAL(8,2),
            low DECIMAL(8,2),
            close DECIMAL(8,2),
            volume BIGINT DEFAULT 0,
            vwap DECIMAL(8,2),
            source VARCHAR(20) DEFAULT 'polygon',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_vix_date ON vix_history(trade_date);
    """))

    # =========================================================================
    # TABLE 4: 0DTE Backtest Results
    # =========================================================================
    tables.append(('zero_dte_backtest_results', """
        CREATE TABLE IF NOT EXISTS zero_dte_backtest_results (
            id SERIAL PRIMARY KEY,
            backtest_id TEXT NOT NULL,
            run_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            -- Configuration
            strategy_name VARCHAR(100) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            config JSONB,

            -- Results Summary
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            win_rate DECIMAL(8,4),

            -- P&L
            total_pnl DECIMAL(14,2),
            total_pnl_pct DECIMAL(10,4),
            avg_trade_pnl DECIMAL(10,2),
            avg_win DECIMAL(10,2),
            avg_loss DECIMAL(10,2),
            largest_win DECIMAL(10,2),
            largest_loss DECIMAL(10,2),

            -- Risk Metrics
            max_drawdown_pct DECIMAL(10,4),
            sharpe_ratio DECIMAL(8,4),
            sortino_ratio DECIMAL(8,4),
            profit_factor DECIMAL(8,4),
            expectancy DECIMAL(10,4),

            -- Data Quality
            days_with_data INTEGER,
            days_skipped INTEGER,
            data_quality_score DECIMAL(5,2),

            UNIQUE(backtest_id)
        );
    """))

    # =========================================================================
    # TABLE 5: 0DTE Individual Trades
    # =========================================================================
    tables.append(('zero_dte_backtest_trades', """
        CREATE TABLE IF NOT EXISTS zero_dte_backtest_trades (
            id SERIAL PRIMARY KEY,
            backtest_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            trade_number INTEGER,

            -- Entry
            entry_time TIMESTAMPTZ,
            underlying_price_entry DECIMAL(10,2),
            vix_entry DECIMAL(8,2),
            short_strike DECIMAL(10,2),
            long_strike DECIMAL(10,2),
            spread_width DECIMAL(10,2),
            entry_credit DECIMAL(10,4),
            short_delta_entry DECIMAL(8,4),
            short_iv_entry DECIMAL(8,4),
            contracts INTEGER DEFAULT 1,

            -- Exit
            exit_time TIMESTAMPTZ,
            underlying_price_exit DECIMAL(10,2),
            settlement_price DECIMAL(10,2),
            exit_debit DECIMAL(10,4),

            -- Results
            pnl_per_spread DECIMAL(10,2),
            pnl_percent DECIMAL(10,4),
            max_profit DECIMAL(10,2),
            max_loss DECIMAL(10,2),
            total_pnl DECIMAL(12,2),

            -- Classification
            outcome VARCHAR(20),
            short_strike_breached BOOLEAN DEFAULT FALSE,
            long_strike_breached BOOLEAN DEFAULT FALSE,
            exit_reason VARCHAR(50),

            -- Context
            day_of_week INTEGER,
            vix_regime VARCHAR(20),
            gex_regime VARCHAR(20),

            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (backtest_id) REFERENCES zero_dte_backtest_results(backtest_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_0dte_trades_backtest ON zero_dte_backtest_trades(backtest_id);
        CREATE INDEX IF NOT EXISTS idx_0dte_trades_date ON zero_dte_backtest_trades(trade_date);
        CREATE INDEX IF NOT EXISTS idx_0dte_trades_outcome ON zero_dte_backtest_trades(outcome);
    """))

    # =========================================================================
    # TABLE 6: Equity Curve for Backtests
    # =========================================================================
    tables.append(('zero_dte_equity_curve', """
        CREATE TABLE IF NOT EXISTS zero_dte_equity_curve (
            id SERIAL PRIMARY KEY,
            backtest_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            trade_number INTEGER,
            equity DECIMAL(14,2),
            daily_pnl DECIMAL(10,2),
            cumulative_pnl DECIMAL(12,2),
            drawdown_pct DECIMAL(10,4),
            high_water_mark DECIMAL(14,2),

            FOREIGN KEY (backtest_id) REFERENCES zero_dte_backtest_results(backtest_id) ON DELETE CASCADE,
            UNIQUE(backtest_id, trade_date, trade_number)
        );

        CREATE INDEX IF NOT EXISTS idx_equity_backtest ON zero_dte_equity_curve(backtest_id);
    """))

    # Execute all table creations
    success_count = 0
    error_count = 0

    for table_name, sql in tables:
        try:
            cursor.execute(sql)
            conn.commit()
            print(f"  ✅ {table_name}")
            success_count += 1
        except Exception as e:
            print(f"  ❌ {table_name}: {e}")
            conn.rollback()
            error_count += 1

    conn.close()

    print("\n" + "=" * 70)
    print(f"✅ Created {success_count} tables")
    if error_count:
        print(f"❌ {error_count} tables failed")
    print("=" * 70)

    return error_count == 0


if __name__ == '__main__':
    create_schema()
