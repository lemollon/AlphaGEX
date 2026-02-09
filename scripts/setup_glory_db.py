#!/usr/bin/env python3
"""
Setup script for GLORY ROC persistence database table.

Run this in Render shell to create the glory_gamma_history table:
    python scripts/setup_glory_db.py

The table will also be auto-created on first API call, but running this
ensures it's ready before users access GLORY.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


def setup_glory_tables():
    """Create GLORY gamma history table and indexes."""
    print("Setting up GLORY database tables...")

    conn = get_connection()
    if not conn:
        print("ERROR: Could not connect to database")
        print("Make sure DATABASE_URL environment variable is set")
        return False

    cursor = conn.cursor()

    # Create table
    print("Creating glory_gamma_history table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS glory_gamma_history (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            strike DECIMAL(10, 2) NOT NULL,
            gamma_value DECIMAL(20, 8) NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # Create indexes
    print("Creating indexes...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_glory_gamma_history_strike_time
        ON glory_gamma_history(symbol, strike, recorded_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_glory_gamma_history_recorded_at
        ON glory_gamma_history(recorded_at)
    """)

    conn.commit()

    # Verify
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'glory_gamma_history'
        );
    """)
    exists = cursor.fetchone()[0]

    if exists:
        print("SUCCESS: glory_gamma_history table created")

        # Show indexes
        cursor.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'glory_gamma_history';
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        print(f"Indexes: {', '.join(indexes)}")
    else:
        print("ERROR: Table creation failed")
        cursor.close()
        conn.close()
        return False

    cursor.close()
    conn.close()

    print("\nGLORY database setup complete!")
    return True


if __name__ == "__main__":
    success = setup_glory_tables()
    sys.exit(0 if success else 1)
