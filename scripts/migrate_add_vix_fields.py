#!/usr/bin/env python3
"""
Database Migration: Add VIX and Volatility Regime Fields

This script adds new columns to the regime_signals table for VIX tracking
and volatility regime detection.

New columns:
- vix_current: Current VIX level
- vix_change_pct: VIX % change from previous close
- vix_spike_detected: Boolean flag for VIX spikes
- zero_gamma_level: The flip point strike price
- volatility_regime: Regime name (EXPLOSIVE_VOLATILITY, etc.)
- at_flip_point: Boolean flag if price near flip point

Run this script ONCE to upgrade your database schema.
"""

import sqlite3
from db.config_and_database import DB_PATH

def migrate_database():
    """Add VIX and volatility fields to regime_signals table"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if columns already exist
    c.execute("PRAGMA table_info(regime_signals)")
    columns = [col[1] for col in c.fetchall()]

    migrations_needed = []

    # Check each new column
    new_columns = {
        'vix_current': 'REAL',
        'vix_change_pct': 'REAL',
        'vix_spike_detected': 'INTEGER DEFAULT 0',
        'zero_gamma_level': 'REAL',
        'volatility_regime': 'TEXT',
        'at_flip_point': 'INTEGER DEFAULT 0'
    }

    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            migrations_needed.append((col_name, col_type))

    if not migrations_needed:
        print("✅ Database schema is already up to date!")
        conn.close()
        return

    print(f"🔄 Adding {len(migrations_needed)} new columns to regime_signals table...")

    for col_name, col_type in migrations_needed:
        try:
            c.execute(f"ALTER TABLE regime_signals ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added column: {col_name} ({col_type})")
        except sqlite3.OperationalError as e:
            print(f"  ⚠ Warning: Could not add {col_name}: {e}")

    conn.commit()
    conn.close()

    print(f"\n✅ Database migration complete! Added {len(migrations_needed)} columns.")
    print("\nNew columns:")
    for col_name, _ in migrations_needed:
        print(f"  - {col_name}")

if __name__ == "__main__":
    print("=" * 60)
    print("Psychology Trap Detection - Database Migration")
    print("Adding VIX and Volatility Regime Fields")
    print("=" * 60)
    print()

    migrate_database()

    print("\n" + "=" * 60)
    print("Migration complete! You can now use the enhanced psychology detector.")
    print("=" * 60)
