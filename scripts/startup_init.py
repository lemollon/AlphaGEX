#!/usr/bin/env python3
"""
Startup Initialization Script
Creates database tables on first startup - NO FAKE DATA
"""
import logging
from db.config_and_database import init_database
from database_adapter import get_connection

# Configure logging
logger = logging.getLogger('startup_init')
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def ensure_all_tables_exist(conn):
    """Create all required tables if they don't exist"""
    c = conn.cursor()

    # Core trading tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS gamma_history (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            date TEXT NOT NULL,
            time_of_day TEXT,
            spot_price REAL NOT NULL,
            net_gex REAL NOT NULL,
            flip_point REAL NOT NULL,
            call_wall REAL,
            put_wall REAL,
            implied_volatility REAL,
            put_call_ratio REAL,
            distance_to_flip_pct REAL,
            regime TEXT,
            UNIQUE(symbol, timestamp)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS gex_history (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            net_gex REAL,
            spot_price REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            UNIQUE(symbol, timestamp)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS regime_signals (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT DEFAULT 'SPY',
            spy_price REAL,
            net_gamma REAL,
            primary_regime_type TEXT,
            secondary_regime_type TEXT,
            confidence_score REAL,
            trade_direction TEXT,
            risk_level TEXT,
            description TEXT,
            rsi_5m REAL,
            rsi_15m REAL,
            rsi_1h REAL,
            rsi_4h REAL,
            rsi_1d REAL,
            is_critical INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            pattern_name TEXT NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            lookback_days INTEGER,
            total_signals INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            win_rate REAL,
            avg_win REAL,
            avg_loss REAL,
            profit_factor REAL,
            total_pnl REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            kelly_fraction REAL,
            recommended_position_pct REAL,
            regime_filter TEXT,
            notes TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_open_positions (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL,
            current_price REAL,
            quantity INTEGER,
            unrealized_pnl REAL,
            status TEXT DEFAULT 'open'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_closed_trades (
            id SERIAL PRIMARY KEY,
            open_timestamp TIMESTAMPTZ,
            close_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            quantity INTEGER,
            realized_pnl REAL,
            outcome TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_trade_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            symbol TEXT,
            details TEXT,
            success BOOLEAN DEFAULT TRUE
        )
    """)

    conn.commit()
    logger.info("All database tables verified/created")


def initialize_on_startup():
    """Initialize database tables on startup - NO FAKE DATA"""

    print("\n" + "="*70)
    print("STARTUP INITIALIZATION - REAL DATA ONLY")
    print("="*70)

    try:
        # Initialize base database schema
        print("📊 Initializing database schema...")
        init_database()

        # Ensure all tables exist
        conn = get_connection()
        ensure_all_tables_exist(conn)
        conn.close()

        print("✅ Database tables ready")
        print("📈 Data will be populated from REAL API sources")
        print("   - Tradier: Real-time quotes and options")
        print("   - Polygon: Historical data")
        print("   - Trading Volatility: GEX analysis")
        print("="*70 + "\n")

    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        print(f"⚠️  Initialization error: {e}")
        print("   Tables will be created as needed during operation")


if __name__ == "__main__":
    initialize_on_startup()
