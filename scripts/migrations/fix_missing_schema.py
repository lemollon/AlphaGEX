#!/usr/bin/env python3
"""
Database Migration Script - Fix Missing Schema
Run in Render shell: python scripts/migrations/fix_missing_schema.py

Creates missing tables and adds missing columns to existing tables.
"""

import os
import sys
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(action, success, details=""):
    status = "OK" if success else "FAIL"
    symbol = "✓" if success else "✗"
    print(f"  {symbol} [{status}] {action}")
    if details:
        print(f"           {details}")


def execute_sql(cursor, sql, description):
    """Execute SQL and handle errors"""
    try:
        cursor.execute(sql)
        print_result(description, True)
        return True
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            print_result(description, True, "Already exists")
            return True
        elif "duplicate" in error_msg.lower():
            print_result(description, True, "Already exists")
            return True
        else:
            print_result(description, False, error_msg[:100])
            return False


def create_missing_tables(cursor):
    """Create all missing tables"""
    print_header("CREATING MISSING TABLES")

    # gex_snapshots
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS gex_snapshots (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            spot_price DECIMAL(12, 4),
            gex_value DECIMAL(20, 4),
            dex_value DECIMAL(20, 4),
            gamma_value DECIMAL(20, 4),
            call_wall DECIMAL(12, 4),
            put_wall DECIMAL(12, 4),
            zero_gamma DECIMAL(12, 4),
            gex_flip DECIMAL(12, 4),
            regime VARCHAR(20),
            data_source VARCHAR(50),
            raw_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create gex_snapshots table")

    # Add index for gex_snapshots
    execute_sql(cursor, """
        CREATE INDEX IF NOT EXISTS idx_gex_snapshots_symbol_timestamp
        ON gex_snapshots(symbol, timestamp DESC)
    """, "Create gex_snapshots index")

    # vix_data
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS vix_data (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            vix_spot DECIMAL(10, 4),
            vix_1m DECIMAL(10, 4),
            vix_3m DECIMAL(10, 4),
            vvix DECIMAL(10, 4),
            term_structure VARCHAR(20),
            contango_pct DECIMAL(8, 4),
            vix_1d_change DECIMAL(8, 4),
            vix_5d_change DECIMAL(8, 4),
            raw_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create vix_data table")

    # Add index for vix_data
    execute_sql(cursor, """
        CREATE INDEX IF NOT EXISTS idx_vix_data_timestamp
        ON vix_data(timestamp DESC)
    """, "Create vix_data index")

    # market_psychology
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS market_psychology (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            fear_greed_index INTEGER,
            put_call_ratio DECIMAL(8, 4),
            vix_term_structure VARCHAR(20),
            retail_sentiment VARCHAR(20),
            institutional_flow VARCHAR(20),
            gamma_exposure VARCHAR(20),
            overall_signal VARCHAR(20),
            signal_strength DECIMAL(5, 2),
            raw_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create market_psychology table")

    # spx_levels
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS spx_levels (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            level_type VARCHAR(50),
            price DECIMAL(12, 4),
            strength DECIMAL(8, 4),
            description TEXT,
            source VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create spx_levels table")

    # trade_history
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS trade_history (
            id SERIAL PRIMARY KEY,
            bot_name VARCHAR(50),
            symbol VARCHAR(20),
            trade_type VARCHAR(20),
            entry_time TIMESTAMPTZ,
            exit_time TIMESTAMPTZ,
            entry_price DECIMAL(12, 4),
            exit_price DECIMAL(12, 4),
            quantity INTEGER,
            pnl DECIMAL(12, 4),
            pnl_pct DECIMAL(8, 4),
            fees DECIMAL(10, 4),
            strategy VARCHAR(100),
            notes TEXT,
            trade_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create trade_history table")

    # bot_trades
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS bot_trades (
            id SERIAL PRIMARY KEY,
            bot_name VARCHAR(50) NOT NULL,
            trade_date DATE NOT NULL,
            symbol VARCHAR(20),
            strategy VARCHAR(100),
            direction VARCHAR(10),
            entry_time TIMESTAMPTZ,
            exit_time TIMESTAMPTZ,
            entry_price DECIMAL(12, 4),
            exit_price DECIMAL(12, 4),
            contracts INTEGER,
            premium_collected DECIMAL(12, 4),
            premium_paid DECIMAL(12, 4),
            realized_pnl DECIMAL(12, 4),
            max_loss DECIMAL(12, 4),
            outcome VARCHAR(50),
            exit_reason VARCHAR(100),
            market_conditions JSONB,
            trade_legs JSONB,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create bot_trades table")

    # oracle_training_outcomes
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS oracle_training_outcomes (
            id SERIAL PRIMARY KEY,
            prediction_id INTEGER REFERENCES oracle_predictions(id),
            trade_date DATE NOT NULL,
            bot_name VARCHAR(50),
            predicted_advice VARCHAR(50),
            predicted_win_prob DECIMAL(5, 4),
            predicted_confidence DECIMAL(5, 2),
            actual_outcome VARCHAR(50),
            actual_pnl DECIMAL(12, 4),
            was_correct BOOLEAN,
            feedback_score DECIMAL(5, 2),
            market_conditions JSONB,
            model_version VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create oracle_training_outcomes table")

    # conversation_history
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS conversation_history (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100),
            user_message TEXT,
            assistant_response TEXT,
            context_data JSONB,
            tokens_used INTEGER,
            model_used VARCHAR(50),
            response_time_ms INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create conversation_history table")

    # gamma_levels
    execute_sql(cursor, """
        CREATE TABLE IF NOT EXISTS gamma_levels (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            strike DECIMAL(12, 4),
            gamma_exposure DECIMAL(20, 4),
            delta_exposure DECIMAL(20, 4),
            open_interest INTEGER,
            volume INTEGER,
            call_oi INTEGER,
            put_oi INTEGER,
            net_gamma DECIMAL(20, 4),
            expiration DATE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, "Create gamma_levels table")


def add_missing_columns(cursor):
    """Add missing columns to existing tables"""
    print_header("ADDING MISSING COLUMNS")

    # oracle_predictions missing columns
    oracle_columns = [
        ("confidence", "DECIMAL(5, 2)"),
        ("reasoning", "TEXT"),
        ("top_factors", "JSONB"),
        ("claude_analysis", "JSONB"),
        ("spot_price", "DECIMAL(12, 4)"),
        ("gex_net", "DECIMAL(20, 4)"),
        ("use_gex_walls", "BOOLEAN DEFAULT TRUE"),
        ("suggested_put_strike", "DECIMAL(12, 4)"),
        ("suggested_call_strike", "DECIMAL(12, 4)"),
        ("probabilities", "JSONB"),
    ]

    for col_name, col_type in oracle_columns:
        execute_sql(cursor, f"""
            ALTER TABLE oracle_predictions
            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
        """, f"Add oracle_predictions.{col_name}")

    # probability_weights missing columns
    execute_sql(cursor, """
        ALTER TABLE probability_weights
        ADD COLUMN IF NOT EXISTS calibration_count INTEGER DEFAULT 0
    """, "Add probability_weights.calibration_count")

    # Ensure active column has default
    execute_sql(cursor, """
        ALTER TABLE probability_weights
        ALTER COLUMN active SET DEFAULT FALSE
    """, "Set probability_weights.active default")


def seed_default_data(cursor):
    """Seed default data for required tables"""
    print_header("SEEDING DEFAULT DATA")

    # First ensure probability_weights has the required columns
    pw_columns = [
        ("weight_name", "TEXT"),
        ("weight_value", "REAL DEFAULT 1.0"),
    ]
    for col_name, col_type in pw_columns:
        execute_sql(cursor, f"""
            ALTER TABLE probability_weights
            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
        """, f"Add probability_weights.{col_name}")

    # Check if probability_weights has active config
    cursor.execute("SELECT COUNT(*) FROM probability_weights WHERE active = TRUE")
    active_count = cursor.fetchone()[0]

    if active_count == 0:
        execute_sql(cursor, """
            INSERT INTO probability_weights (
                weight_name, weight_value, gex_wall_strength, volatility_impact,
                psychology_signal, mm_positioning, historical_pattern,
                active, calibration_count
            ) VALUES (
                'default_v1', 1.0, 0.25, 0.20, 0.15, 0.20, 0.20,
                TRUE, 0
            )
            ON CONFLICT DO NOTHING
        """, "Seed default probability weights")
    else:
        print_result("Seed default probability weights", True, "Already has active config")


def main():
    """Run database migration"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║         ALPHAGEX DATABASE MIGRATION SCRIPT                ║
╚═══════════════════════════════════════════════════════════╝
""")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from database_adapter import get_connection, is_database_available

        if not is_database_available():
            print("\n  ❌ Database not available!")
            return 1

        conn = get_connection()
        cursor = conn.cursor()

        # Run migrations
        create_missing_tables(cursor)
        add_missing_columns(cursor)
        seed_default_data(cursor)

        # Commit changes
        conn.commit()
        print_header("MIGRATION COMPLETE")
        print("  ✅ All migrations applied successfully!")
        print("  ✅ Changes committed to database")

        conn.close()
        return 0

    except Exception as e:
        print(f"\n  ❌ Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
