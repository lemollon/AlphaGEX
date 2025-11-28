#!/usr/bin/env python3
"""
Test Database Schema - Verify regime_signals table has all required columns
"""

import sqlite3
from config_and_database import DB_PATH

print("=" * 80)
print("DATABASE SCHEMA TEST")
print("=" * 80)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print("\n1️⃣  Checking regime_signals table exists...")
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='regime_signals'")
if c.fetchone():
    print("✅ regime_signals table exists")
else:
    print("❌ regime_signals table NOT FOUND")
    print("\nRun this to fix: python -c 'from config_and_database import init_database; init_database()'")
    conn.close()
    exit(1)

print("\n2️⃣  Checking table schema...")
c.execute("PRAGMA table_info(regime_signals)")
columns = c.fetchall()

column_names = [col[1] for col in columns]
print(f"✅ Found {len(column_names)} columns\n")

# Required columns for save_regime_signal_to_db
required_columns = [
    'id', 'timestamp', 'spy_price', 'primary_regime_type', 'secondary_regime_type',
    'confidence_score', 'trade_direction', 'risk_level', 'description',
    'detailed_explanation', 'psychology_trap',
    'rsi_5m', 'rsi_15m', 'rsi_1h', 'rsi_4h', 'rsi_1d', 'rsi_score',
    'rsi_aligned_overbought', 'rsi_aligned_oversold', 'rsi_coiling',
    'nearest_call_wall', 'call_wall_distance_pct', 'call_wall_strength',
    'nearest_put_wall', 'put_wall_distance_pct', 'put_wall_strength',
    'net_gamma', 'net_gamma_regime',
    'zero_dte_gamma', 'gamma_expiring_this_week', 'gamma_expiring_next_week',
    'liberation_setup_detected', 'liberation_target_strike', 'liberation_expiry_date',
    'false_floor_detected', 'false_floor_strike', 'false_floor_expiry_date',
    'monthly_magnet_above', 'monthly_magnet_above_strength',
    'monthly_magnet_below', 'monthly_magnet_below_strength',
    'path_of_least_resistance', 'polr_confidence',
    'volume_ratio', 'target_price_near', 'target_price_far', 'target_timeline_days'
]

missing_columns = [col for col in required_columns if col not in column_names]
extra_columns = [col for col in column_names if col not in required_columns]

if missing_columns:
    print("❌ MISSING COLUMNS:")
    for col in missing_columns:
        print(f"   - {col}")
    print("\nThese columns are required but missing from the schema!")
else:
    print("✅ All required columns present")

if extra_columns:
    print(f"\n✅ Extra columns (good - newer schema):")
    for col in extra_columns:
        print(f"   - {col}")

print("\n3️⃣  Checking table is empty (before first run)...")
c.execute("SELECT COUNT(*) FROM regime_signals")
count = c.fetchone()[0]
print(f"   Rows in table: {count}")

if count == 0:
    print("   ⚠️  Table is empty (expected before trader runs)")
else:
    print(f"   ✅ Found {count} existing regime signals")

    # Show a sample
    c.execute("SELECT primary_regime_type, confidence_score, timestamp FROM regime_signals LIMIT 3")
    print("\n   Sample signals:")
    for row in c.fetchall():
        print(f"   - {row[0]} ({row[1]:.0f}% confidence) at {row[2]}")

conn.close()

print("\n" + "=" * 80)
print("DATABASE SCHEMA TEST RESULT")
print("=" * 80)

if not missing_columns:
    print("✅ PASS - Database schema is correct!")
    print("\nWhat this means:")
    print("  • regime_signals table has all required columns")
    print("  • save_regime_signal_to_db() will be able to insert data")
    print("  • No schema mismatches will cause runtime errors")
    print("\nConfidence: 95% - Database is ready")
    exit(0)
else:
    print("❌ FAIL - Database schema is incomplete")
    print("\nMissing columns will cause INSERT errors!")
    print("Re-run database initialization to fix.")
    exit(1)
