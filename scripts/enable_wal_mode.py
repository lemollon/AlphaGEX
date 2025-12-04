#!/usr/bin/env python3
"""
Enable WAL Mode on Database
This script converts the database to WAL (Write-Ahead Logging) mode,
which allows concurrent reads and writes without locking issues.

Run this ONCE to enable WAL mode permanently on the database.

Usage:
    python enable_wal_mode.py
"""

import sqlite3
import sys
from db.config_and_database import DB_PATH

def enable_wal_mode():
    """Enable WAL mode on the database"""
    print("=" * 70)
    print("ENABLE WAL MODE")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print()

    try:
        # Connect with a long timeout
        print("Connecting to database...")
        conn = sqlite3.connect(DB_PATH, timeout=60.0)

        # Check current mode
        current_mode = conn.execute('PRAGMA journal_mode').fetchone()
        print(f"Current journal mode: {current_mode[0]}")

        # Enable WAL mode
        print("\nEnabling WAL mode...")
        result = conn.execute('PRAGMA journal_mode=WAL').fetchone()

        if result and result[0] == 'wal':
            print("✅ SUCCESS! WAL mode enabled")
            print()
            print("Benefits:")
            print("  • Multiple readers can access database while writing")
            print("  • Backfill scripts can run while API is active")
            print("  • Better concurrency and performance")
            print()
            print("WAL mode is now permanent for this database.")
        else:
            print(f"⚠️  WARNING: Journal mode is now: {result[0]}")
            print("WAL mode may not be supported on this system.")

        # Also set optimal settings
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=-64000')  # 64MB cache
        print("✅ Optimized database settings")

        conn.close()
        return True

    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            print("❌ ERROR: Database is locked")
            print()
            print("The database is currently in use by another process.")
            print("Please try one of these options:")
            print()
            print("Option 1: Wait a moment and try again")
            print("  The lock may be temporary")
            print()
            print("Option 2: Stop the API service temporarily")
            print("  1. Go to Render Dashboard")
            print("  2. Suspend alphagex-api service")
            print("  3. Run this script again")
            print("  4. Resume the service")
            print()
            return False
        else:
            print(f"❌ ERROR: {e}")
            return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = enable_wal_mode()
    sys.exit(0 if success else 1)
