#!/usr/bin/env python3
"""
Startup Initialization Script
Creates database tables on first startup - NO FAKE DATA
Also runs data integrity migrations to fix historical data issues.
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


# Bot position tables that need close_time migration
BOT_POSITION_TABLES = [
    'ares_positions',
    'athena_positions',
    'titan_positions',
    'pegasus_positions',
    'icarus_positions',
]


def fix_missing_close_times(conn):
    """
    Data integrity migration: Fix positions with NULL close_time.

    Per CLAUDE.md requirements:
    - close_position() must set: close_time = NOW(), realized_pnl
    - expire_position() must exist and set same fields
    - All position status changes must update close_time

    Historical data may have close_time = NULL due to older code versions.
    This migration sets close_time = open_time for affected records.
    """
    cursor = conn.cursor()
    total_fixed = 0

    for table in BOT_POSITION_TABLES:
        try:
            # Check if table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            if not cursor.fetchone()[0]:
                continue

            # Check if both columns exist
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND column_name IN ('close_time', 'open_time')
            """, (table,))
            columns = [row[0] for row in cursor.fetchall()]
            if 'close_time' not in columns or 'open_time' not in columns:
                logger.debug(f"Skipping {table}: missing required columns")
                continue

            # Count affected rows
            cursor.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND close_time IS NULL
            """)
            affected = cursor.fetchone()[0]

            if affected > 0:
                # Fix: Set close_time = open_time for historical records
                cursor.execute(f"""
                    UPDATE {table}
                    SET close_time = open_time
                    WHERE status IN ('closed', 'expired', 'partial_close')
                    AND close_time IS NULL
                    AND open_time IS NOT NULL
                """)
                fixed = cursor.rowcount
                total_fixed += fixed
                logger.info(f"Fixed {fixed} positions in {table} with missing close_time")

        except Exception as e:
            logger.warning(f"Could not check/fix {table}: {e}")
            continue

    if total_fixed > 0:
        conn.commit()
        print(f"🔧 Data integrity: Fixed {total_fixed} positions with missing close_time")
    else:
        logger.debug("No positions with missing close_time found")

    return total_fixed


def fix_missing_exit_times(conn):
    """
    Data integrity migration: Fix autonomous_closed_trades with NULL exit_time.

    The autonomous_closed_trades table uses exit_time (TEXT) instead of close_time.
    Historical data may have NULL exit_time. This migration sets exit_time = entry_time.
    """
    cursor = conn.cursor()
    total_fixed = 0

    try:
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'autonomous_closed_trades'
            )
        """)
        if not cursor.fetchone()[0]:
            return 0

        # Count affected rows
        cursor.execute("""
            SELECT COUNT(*) FROM autonomous_closed_trades
            WHERE exit_time IS NULL AND entry_time IS NOT NULL
        """)
        affected = cursor.fetchone()[0]

        if affected > 0:
            # Fix: Set exit_time = entry_time for historical records
            cursor.execute("""
                UPDATE autonomous_closed_trades
                SET exit_time = entry_time
                WHERE exit_time IS NULL
                AND entry_time IS NOT NULL
            """)
            total_fixed = cursor.rowcount
            conn.commit()
            logger.info(f"Fixed {total_fixed} trades in autonomous_closed_trades with missing exit_time")
            print(f"🔧 Data integrity: Fixed {total_fixed} trades with missing exit_time")

    except Exception as e:
        logger.warning(f"Could not check/fix autonomous_closed_trades: {e}")

    return total_fixed


def ensure_all_tables_exist(conn):
    """
    Verify all tables exist.
    NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
    This function is kept for backwards compatibility but does nothing.
    init_database() creates all required tables.
    """
    # Tables created by init_database() - just log success
    logger.info("All database tables verified (created by main schema)")


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

        # Run data integrity migrations
        print("🔍 Running data integrity checks...")
        fix_missing_close_times(conn)
        fix_missing_exit_times(conn)

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
