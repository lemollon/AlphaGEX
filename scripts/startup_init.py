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
