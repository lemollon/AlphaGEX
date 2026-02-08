"""
Setup Unified Gamma History Table
=================================

Creates a unified gamma history table that can be used by both
WATCHTOWER (0DTE) and GLORY (Weekly) for ROC calculations.

This replaces the separate hyperion_gamma_history table with a
unified structure that supports both systems.

Usage:
    python scripts/setup_unified_gamma_history.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_unified_gamma_history_table():
    """Create the unified gamma history table with indexes"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        # Create the unified table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unified_gamma_history (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,  -- 'WATCHTOWER' or 'GLORY'
                symbol VARCHAR(10) NOT NULL,
                expiration_date DATE,
                strike DECIMAL(10, 2) NOT NULL,
                net_gamma DECIMAL(20, 8) NOT NULL,
                call_gamma DECIMAL(20, 8),
                put_gamma DECIMAL(20, 8),
                call_oi INTEGER,
                put_oi INTEGER,
                spot_price DECIMAL(10, 2),
                recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        logger.info("Created unified_gamma_history table")

        # Create indexes for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_gamma_system_symbol_strike_time
            ON unified_gamma_history(system, symbol, strike, recorded_at DESC)
        """)
        logger.info("Created index: idx_unified_gamma_system_symbol_strike_time")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_gamma_recorded_at
            ON unified_gamma_history(recorded_at)
        """)
        logger.info("Created index: idx_unified_gamma_recorded_at")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_gamma_system
            ON unified_gamma_history(system)
        """)
        logger.info("Created index: idx_unified_gamma_system")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_gamma_symbol_expiration
            ON unified_gamma_history(symbol, expiration_date)
        """)
        logger.info("Created index: idx_unified_gamma_symbol_expiration")

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Successfully created unified gamma history table with all indexes")
        return True

    except Exception as e:
        logger.error(f"Error creating unified gamma history table: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def create_alerts_table():
    """Create alerts table for both WATCHTOWER and GLORY"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_alerts (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,  -- 'WATCHTOWER' or 'GLORY'
                symbol VARCHAR(10) NOT NULL,
                alert_type VARCHAR(50) NOT NULL,
                strike DECIMAL(10, 2),
                message TEXT NOT NULL,
                priority VARCHAR(10) NOT NULL,
                spot_price DECIMAL(10, 2),
                old_value TEXT,
                new_value TEXT,
                acknowledged BOOLEAN DEFAULT FALSE,
                acknowledged_at TIMESTAMP WITH TIME ZONE,
                triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        logger.info("Created gamma_alerts table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_alerts_system_symbol
            ON gamma_alerts(system, symbol, triggered_at DESC)
        """)
        logger.info("Created index: idx_gamma_alerts_system_symbol")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_alerts_acknowledged
            ON gamma_alerts(acknowledged, triggered_at DESC)
        """)
        logger.info("Created index: idx_gamma_alerts_acknowledged")

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Successfully created gamma_alerts table")
        return True

    except Exception as e:
        logger.error(f"Error creating gamma_alerts table: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def create_patterns_table():
    """Create pattern matching table for historical analysis"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_patterns (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,  -- 'WATCHTOWER' or 'GLORY'
                symbol VARCHAR(10) NOT NULL,
                pattern_date DATE NOT NULL,
                spot_price DECIMAL(10, 2),
                open_price DECIMAL(10, 2),
                close_price DECIMAL(10, 2),
                day_high DECIMAL(10, 2),
                day_low DECIMAL(10, 2),
                gamma_regime VARCHAR(20),
                total_net_gamma DECIMAL(20, 8),
                top_magnet DECIMAL(10, 2),
                likely_pin DECIMAL(10, 2),
                flip_point DECIMAL(10, 2),
                call_wall DECIMAL(10, 2),
                put_wall DECIMAL(10, 2),
                vix DECIMAL(6, 2),
                outcome_direction VARCHAR(10),  -- UP, DOWN, FLAT
                outcome_pct DECIMAL(6, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(system, symbol, pattern_date)
            )
        """)
        logger.info("Created gamma_patterns table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_patterns_lookup
            ON gamma_patterns(system, symbol, gamma_regime)
        """)
        logger.info("Created index: idx_gamma_patterns_lookup")

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Successfully created gamma_patterns table")
        return True

    except Exception as e:
        logger.error(f"Error creating gamma_patterns table: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def create_danger_zone_logs_table():
    """Create danger zone logs table"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_danger_zones (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,  -- 'WATCHTOWER' or 'GLORY'
                symbol VARCHAR(10) NOT NULL,
                strike DECIMAL(10, 2) NOT NULL,
                danger_type VARCHAR(20) NOT NULL,
                roc_1min DECIMAL(10, 2),
                roc_5min DECIMAL(10, 2),
                spot_price DECIMAL(10, 2),
                distance_from_spot_pct DECIMAL(6, 2),
                is_active BOOLEAN DEFAULT TRUE,
                detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
                resolved_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        logger.info("Created gamma_danger_zones table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_danger_zones_active
            ON gamma_danger_zones(system, symbol, is_active, detected_at DESC)
        """)
        logger.info("Created index: idx_gamma_danger_zones_active")

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Successfully created gamma_danger_zones table")
        return True

    except Exception as e:
        logger.error(f"Error creating gamma_danger_zones table: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def create_strike_trends_table():
    """Create strike trends table for tracking behavior over time"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_strike_trends (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                strike DECIMAL(10, 2) NOT NULL,
                trend_date DATE NOT NULL,
                spike_count INTEGER DEFAULT 0,
                flip_count INTEGER DEFAULT 0,
                building_count INTEGER DEFAULT 0,
                collapsing_count INTEGER DEFAULT 0,
                peak_roc DECIMAL(10, 2),
                time_as_magnet_mins INTEGER DEFAULT 0,
                dominant_status VARCHAR(20),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(system, symbol, strike, trend_date)
            )
        """)
        logger.info("Created gamma_strike_trends table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_strike_trends_lookup
            ON gamma_strike_trends(system, symbol, trend_date)
        """)
        logger.info("Created index: idx_gamma_strike_trends_lookup")

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Successfully created gamma_strike_trends table")
        return True

    except Exception as e:
        logger.error(f"Error creating gamma_strike_trends table: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def migrate_glory_history():
    """Migrate existing hyperion_gamma_history to unified table"""
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return False

    try:
        cursor = conn.cursor()

        # Check if old table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'hyperion_gamma_history'
            )
        """)
        old_table_exists = cursor.fetchone()[0]

        if old_table_exists:
            # Migrate data
            cursor.execute("""
                INSERT INTO unified_gamma_history
                    (system, symbol, strike, net_gamma, recorded_at, created_at)
                SELECT
                    'GLORY',
                    symbol,
                    strike,
                    gamma_value,
                    recorded_at,
                    created_at
                FROM hyperion_gamma_history
                ON CONFLICT DO NOTHING
            """)
            migrated = cursor.rowcount
            logger.info(f"Migrated {migrated} rows from hyperion_gamma_history")

            conn.commit()
        else:
            logger.info("No hyperion_gamma_history table to migrate")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Error migrating glory history: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False


def main():
    """Run all setup steps"""
    print("=" * 60)
    print("Setting up Unified Gamma Tables")
    print("=" * 60)

    success = True

    print("\n1. Creating unified_gamma_history table...")
    if not create_unified_gamma_history_table():
        success = False

    print("\n2. Creating gamma_alerts table...")
    if not create_alerts_table():
        success = False

    print("\n3. Creating gamma_patterns table...")
    if not create_patterns_table():
        success = False

    print("\n4. Creating gamma_danger_zones table...")
    if not create_danger_zone_logs_table():
        success = False

    print("\n5. Creating gamma_strike_trends table...")
    if not create_strike_trends_table():
        success = False

    print("\n6. Migrating existing Glory history...")
    if not migrate_glory_history():
        success = False

    print("\n" + "=" * 60)
    if success:
        print("All tables created successfully!")
    else:
        print("Some tables failed to create. Check logs above.")
    print("=" * 60)

    return success


if __name__ == "__main__":
    main()
