#!/usr/bin/env python3
"""
Database Migration: Fix Probability System Tables

This script creates/updates the probability system tables to match
the expected schema for:
- probability_predictions (new table)
- probability_outcomes (updated columns)
- probability_weights (updated columns)
- calibration_history (updated columns)

Run this script to upgrade your database schema for the probability system.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database_adapter import get_connection, is_database_available


def check_table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in PostgreSQL"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table_name,))
    return cursor.fetchone()[0]


def check_column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, (table_name, column_name))
    return cursor.fetchone()[0]


def migrate_database():
    """Migrate probability tables to correct schema"""

    if not is_database_available():
        print("❌ Database not available. Set DATABASE_URL environment variable.")
        return False

    conn = get_connection()
    cursor = conn.cursor()

    print("🔄 Starting probability system migration...")

    # =========================================================================
    # 1. Create probability_predictions table (if not exists)
    # =========================================================================
    print("\n📋 Checking probability_predictions table...")

    if not check_table_exists(cursor, 'probability_predictions'):
        print("  Creating probability_predictions table...")
        cursor.execute('''
            CREATE TABLE probability_predictions (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                symbol TEXT NOT NULL,
                prediction_type TEXT NOT NULL,
                target_date DATE NOT NULL,
                current_price REAL,
                range_low REAL,
                range_high REAL,
                prob_in_range REAL,
                prob_above REAL,
                prob_below REAL,
                confidence_level TEXT,
                net_gex REAL,
                flip_point REAL,
                call_wall REAL,
                put_wall REAL,
                vix_level REAL,
                implied_vol REAL,
                psychology_state TEXT,
                fomo_level REAL,
                fear_level REAL,
                mm_state TEXT,
                actual_close_price REAL,
                prediction_correct BOOLEAN,
                recorded_at TIMESTAMPTZ
            )
        ''')
        print("  ✅ Created probability_predictions table")
    else:
        print("  ✓ probability_predictions table exists")

    # =========================================================================
    # 2. Update probability_outcomes table
    # =========================================================================
    print("\n📋 Checking probability_outcomes table...")

    if not check_table_exists(cursor, 'probability_outcomes'):
        print("  Creating probability_outcomes table...")
        cursor.execute('''
            CREATE TABLE probability_outcomes (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                prediction_id INTEGER REFERENCES probability_predictions(id),
                prediction_type TEXT,
                predicted_probability REAL,
                actual_outcome BOOLEAN,
                correct_prediction BOOLEAN,
                outcome_timestamp TIMESTAMPTZ,
                confidence REAL,
                regime_type TEXT,
                gex_value REAL,
                vix_value REAL,
                error_pct REAL
            )
        ''')
        print("  ✅ Created probability_outcomes table")
    else:
        # Add missing columns
        new_columns = {
            'prediction_id': 'INTEGER',
            'correct_prediction': 'BOOLEAN',
            'outcome_timestamp': 'TIMESTAMPTZ',
            'error_pct': 'REAL'
        }
        for col_name, col_type in new_columns.items():
            if not check_column_exists(cursor, 'probability_outcomes', col_name):
                print(f"  Adding column {col_name}...")
                cursor.execute(f"ALTER TABLE probability_outcomes ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Added {col_name}")
        print("  ✓ probability_outcomes table updated")

    # =========================================================================
    # 3. Update probability_weights table
    # =========================================================================
    print("\n📋 Checking probability_weights table...")

    if not check_table_exists(cursor, 'probability_weights'):
        print("  Creating probability_weights table...")
        cursor.execute('''
            CREATE TABLE probability_weights (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                weight_name TEXT,
                weight_value REAL,
                description TEXT,
                last_updated TIMESTAMPTZ DEFAULT NOW(),
                calibration_count INTEGER DEFAULT 0,
                gex_wall_strength REAL DEFAULT 0.35,
                volatility_impact REAL DEFAULT 0.25,
                psychology_signal REAL DEFAULT 0.20,
                mm_positioning REAL DEFAULT 0.15,
                historical_pattern REAL DEFAULT 0.05,
                accuracy_score REAL,
                active BOOLEAN DEFAULT TRUE
            )
        ''')
        print("  ✅ Created probability_weights table")
    else:
        # Add missing columns for ProbabilityCalculator
        new_columns = {
            'gex_wall_strength': 'REAL DEFAULT 0.35',
            'volatility_impact': 'REAL DEFAULT 0.25',
            'psychology_signal': 'REAL DEFAULT 0.20',
            'mm_positioning': 'REAL DEFAULT 0.15',
            'historical_pattern': 'REAL DEFAULT 0.05',
            'accuracy_score': 'REAL',
            'active': 'BOOLEAN DEFAULT TRUE',
            'calibration_count': 'INTEGER DEFAULT 0',
            'weight_name': 'TEXT',
            'weight_value': 'REAL',
            'last_updated': 'TIMESTAMPTZ DEFAULT NOW()'
        }
        for col_name, col_type in new_columns.items():
            if not check_column_exists(cursor, 'probability_weights', col_name):
                print(f"  Adding column {col_name}...")
                cursor.execute(f"ALTER TABLE probability_weights ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Added {col_name}")
        print("  ✓ probability_weights table updated")

    # =========================================================================
    # 4. Update calibration_history table
    # =========================================================================
    print("\n📋 Checking calibration_history table...")

    if not check_table_exists(cursor, 'calibration_history'):
        print("  Creating calibration_history table...")
        cursor.execute('''
            CREATE TABLE calibration_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                calibration_date TIMESTAMPTZ DEFAULT NOW(),
                weight_name TEXT,
                old_value REAL,
                new_value REAL,
                reason TEXT,
                performance_delta REAL,
                predictions_analyzed INTEGER,
                overall_accuracy REAL,
                high_conf_accuracy REAL,
                adjustments_made JSONB
            )
        ''')
        print("  ✅ Created calibration_history table")
    else:
        # Add missing columns
        new_columns = {
            'calibration_date': 'TIMESTAMPTZ DEFAULT NOW()',
            'weight_name': 'TEXT',
            'old_value': 'REAL',
            'new_value': 'REAL',
            'reason': 'TEXT',
            'performance_delta': 'REAL',
            'predictions_analyzed': 'INTEGER',
            'overall_accuracy': 'REAL',
            'high_conf_accuracy': 'REAL',
            'adjustments_made': 'JSONB'
        }
        for col_name, col_type in new_columns.items():
            if not check_column_exists(cursor, 'calibration_history', col_name):
                print(f"  Adding column {col_name}...")
                cursor.execute(f"ALTER TABLE calibration_history ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Added {col_name}")
        print("  ✓ calibration_history table updated")

    # =========================================================================
    # 5. Insert default weights if none exist
    # =========================================================================
    print("\n📋 Checking for default weights...")
    cursor.execute("SELECT COUNT(*) FROM probability_weights WHERE active = TRUE")
    count = cursor.fetchone()[0]

    if count == 0:
        print("  Inserting default weights...")
        cursor.execute('''
            INSERT INTO probability_weights (
                gex_wall_strength, volatility_impact, psychology_signal,
                mm_positioning, historical_pattern, active, calibration_count
            ) VALUES (0.35, 0.25, 0.20, 0.15, 0.05, TRUE, 0)
        ''')
        print("  ✅ Default weights inserted")
    else:
        print(f"  ✓ {count} active weight configuration(s) found")

    # Commit all changes
    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ Probability system migration complete!")
    print("=" * 60)
    return True


def verify_schema():
    """Verify the schema is correct after migration"""
    print("\n🔍 Verifying schema...")

    conn = get_connection()
    cursor = conn.cursor()

    tables = ['probability_predictions', 'probability_outcomes',
              'probability_weights', 'calibration_history']

    for table in tables:
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        columns = cursor.fetchall()
        print(f"\n  {table}:")
        for col_name, col_type in columns:
            print(f"    - {col_name}: {col_type}")

    conn.close()
    print("\n✅ Schema verification complete")


if __name__ == "__main__":
    print("=" * 60)
    print("Probability System - Database Migration")
    print("=" * 60)
    print()

    success = migrate_database()

    if success:
        verify_schema()

    print("\n" + "=" * 60)
    print("Migration script finished.")
    print("=" * 60)
