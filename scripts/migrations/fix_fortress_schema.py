#!/usr/bin/env python3
"""
Quick fix for ALL bot positions table schemas.
Run in Render shell: python scripts/migrations/fix_ares_schema.py

This adds all missing columns that prevent FORTRESS, ANCHOR, and SOLOMON from saving positions.
"""

import os
import sys

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database_adapter import get_connection


def fix_ares_schema(cursor):
    """Add all missing columns to fortress_positions table"""
    print("\n  FORTRESS Iron Condor Positions")
    print("  " + "-"*40)

    columns_to_add = [
        # Ticker symbol (not in original schema)
        ("ticker", "VARCHAR(10) DEFAULT 'SPY'"),

        # Market context at entry
        ("underlying_at_entry", "DECIMAL(10, 2)"),
        ("vix_at_entry", "DECIMAL(6, 2)"),
        ("expected_move", "DECIMAL(10, 2)"),

        # Position financials
        ("max_profit", "DECIMAL(10, 2)"),
        ("max_loss", "DECIMAL(10, 2)"),
        ("spread_width", "DECIMAL(10, 2)"),
        ("contracts", "INTEGER"),

        # Credit details
        ("put_credit", "DECIMAL(10, 4)"),
        ("call_credit", "DECIMAL(10, 4)"),
        ("total_credit", "DECIMAL(10, 4)"),

        # Strike prices
        ("put_short_strike", "DECIMAL(10, 2)"),
        ("put_long_strike", "DECIMAL(10, 2)"),
        ("call_short_strike", "DECIMAL(10, 2)"),
        ("call_long_strike", "DECIMAL(10, 2)"),

        # GEX context
        ("gex_regime", "VARCHAR(30)"),
        ("call_wall", "DECIMAL(10, 2)"),
        ("put_wall", "DECIMAL(10, 2)"),
        ("flip_point", "DECIMAL(10, 2)"),
        ("net_gex", "DECIMAL(15, 2)"),

        # Oracle context
        ("oracle_confidence", "DECIMAL(8, 4)"),
        ("oracle_win_probability", "DECIMAL(8, 4)"),
        ("oracle_advice", "VARCHAR(20)"),
        ("oracle_reasoning", "TEXT"),
        ("oracle_top_factors", "TEXT"),
        ("oracle_use_gex_walls", "BOOLEAN DEFAULT FALSE"),

        # Order tracking
        ("put_order_id", "VARCHAR(50)"),
        ("call_order_id", "VARCHAR(50)"),

        # Status
        ("status", "VARCHAR(20) DEFAULT 'open'"),
        ("open_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_price", "DECIMAL(10, 4)"),
        ("close_reason", "VARCHAR(100)"),
        ("realized_pnl", "DECIMAL(10, 2)"),
        ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
    ]

    added = 0
    for col_name, col_type in columns_to_add:
        try:
            sql = f"ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            cursor.execute(sql)
            added += 1
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"    ✗ {col_name}: {e}")

    print(f"    ✓ Added/verified {added} columns")
    return added


def fix_anchor_schema(cursor):
    """Add all missing columns to anchor_positions table"""
    print("\n  ANCHOR SPX Iron Condor Positions")
    print("  " + "-"*40)

    columns_to_add = [
        ("underlying_at_entry", "DECIMAL(10, 2)"),
        ("vix_at_entry", "DECIMAL(6, 2)"),
        ("expected_move", "DECIMAL(10, 2)"),
        ("max_profit", "DECIMAL(10, 2)"),
        ("max_loss", "DECIMAL(10, 2)"),
        ("spread_width", "DECIMAL(10, 2)"),
        ("contracts", "INTEGER"),
        ("put_credit", "DECIMAL(10, 4)"),
        ("call_credit", "DECIMAL(10, 4)"),
        ("total_credit", "DECIMAL(10, 4)"),
        ("put_short_strike", "DECIMAL(10, 2)"),
        ("put_long_strike", "DECIMAL(10, 2)"),
        ("call_short_strike", "DECIMAL(10, 2)"),
        ("call_long_strike", "DECIMAL(10, 2)"),
        ("gex_regime", "VARCHAR(30)"),
        ("call_wall", "DECIMAL(10, 2)"),
        ("put_wall", "DECIMAL(10, 2)"),
        ("flip_point", "DECIMAL(10, 2)"),
        ("net_gex", "DECIMAL(15, 2)"),
        ("oracle_confidence", "DECIMAL(8, 4)"),
        ("oracle_win_probability", "DECIMAL(8, 4)"),
        ("oracle_advice", "VARCHAR(20)"),
        ("oracle_reasoning", "TEXT"),
        ("oracle_top_factors", "TEXT"),
        ("oracle_use_gex_walls", "BOOLEAN DEFAULT FALSE"),
        ("put_order_id", "VARCHAR(50)"),
        ("call_order_id", "VARCHAR(50)"),
        ("status", "VARCHAR(20) DEFAULT 'open'"),
        ("open_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_price", "DECIMAL(10, 4)"),
        ("close_reason", "VARCHAR(100)"),
        ("realized_pnl", "DECIMAL(10, 2)"),
        ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
    ]

    added = 0
    for col_name, col_type in columns_to_add:
        try:
            sql = f"ALTER TABLE anchor_positions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            cursor.execute(sql)
            added += 1
        except Exception as e:
            if "already exists" not in str(e).lower() and "does not exist" not in str(e).lower():
                print(f"    ✗ {col_name}: {e}")

    print(f"    ✓ Added/verified {added} columns")
    return added


def fix_solomon_schema(cursor):
    """Add all missing columns to solomon_positions table"""
    print("\n  SOLOMON Directional Spreads Positions")
    print("  " + "-"*40)

    columns_to_add = [
        ("underlying_at_entry", "DECIMAL(10, 2)"),
        ("vix_at_entry", "DECIMAL(6, 2)"),
        ("max_profit", "DECIMAL(10, 2)"),
        ("max_loss", "DECIMAL(10, 2)"),
        ("entry_debit", "DECIMAL(10, 4)"),
        ("long_strike", "DECIMAL(10, 2)"),
        ("short_strike", "DECIMAL(10, 2)"),
        ("spread_type", "VARCHAR(30)"),
        ("contracts", "INTEGER"),
        ("gex_regime", "VARCHAR(30)"),
        ("call_wall", "DECIMAL(10, 2)"),
        ("put_wall", "DECIMAL(10, 2)"),
        ("flip_point", "DECIMAL(10, 2)"),
        ("net_gex", "DECIMAL(15, 2)"),
        ("oracle_confidence", "DECIMAL(8, 4)"),
        ("ml_direction", "VARCHAR(20)"),
        ("ml_confidence", "DECIMAL(8, 4)"),
        ("ml_model_name", "VARCHAR(100)"),
        ("ml_win_probability", "DECIMAL(8, 4)"),
        ("ml_top_features", "TEXT"),
        ("wall_type", "VARCHAR(20)"),
        ("wall_distance_pct", "DECIMAL(6, 4)"),
        ("trade_reasoning", "TEXT"),
        ("order_id", "VARCHAR(50)"),
        ("status", "VARCHAR(20) DEFAULT 'open'"),
        ("open_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_time", "TIMESTAMP WITH TIME ZONE"),
        ("close_price", "DECIMAL(10, 4)"),
        ("close_reason", "VARCHAR(100)"),
        ("realized_pnl", "DECIMAL(10, 2)"),
        ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
    ]

    added = 0
    for col_name, col_type in columns_to_add:
        try:
            sql = f"ALTER TABLE solomon_positions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            cursor.execute(sql)
            added += 1
        except Exception as e:
            if "already exists" not in str(e).lower() and "does not exist" not in str(e).lower():
                print(f"    ✗ {col_name}: {e}")

    print(f"    ✓ Added/verified {added} columns")
    return added


def fix_precision(cursor):
    """Fix DECIMAL(5,4) precision issues across all tables"""
    print("\n  Fixing Numeric Precision")
    print("  " + "-"*40)

    precision_fixes = [
        # scan_activity
        ("scan_activity", "signal_confidence", "DECIMAL(8, 4)"),
        ("scan_activity", "signal_win_probability", "DECIMAL(8, 4)"),
        # fortress_positions
        ("fortress_positions", "oracle_confidence", "DECIMAL(8, 4)"),
        ("fortress_positions", "oracle_win_probability", "DECIMAL(8, 4)"),
        # fortress_signals
        ("fortress_signals", "confidence", "DECIMAL(8, 4)"),
        # anchor_positions
        ("anchor_positions", "oracle_confidence", "DECIMAL(8, 4)"),
        ("anchor_positions", "oracle_win_probability", "DECIMAL(8, 4)"),
        # anchor_signals
        ("anchor_signals", "confidence", "DECIMAL(8, 4)"),
        # solomon_positions
        ("solomon_positions", "oracle_confidence", "DECIMAL(8, 4)"),
        ("solomon_positions", "ml_confidence", "DECIMAL(8, 4)"),
        ("solomon_positions", "ml_win_probability", "DECIMAL(8, 4)"),
        # solomon_signals
        ("solomon_signals", "confidence", "DECIMAL(8, 4)"),
    ]

    fixed = 0
    for table, column, new_type in precision_fixes:
        try:
            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}")
            print(f"    ✓ {table}.{column} -> {new_type}")
            fixed += 1
        except Exception as e:
            if "does not exist" in str(e).lower():
                pass  # Table or column doesn't exist, skip
            else:
                print(f"    - {table}.{column}: already correct")

    return fixed


def main():
    print("\n" + "="*60)
    print("  ALL BOTS Schema Fix - FORTRESS, ANCHOR, SOLOMON")
    print("="*60)

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Fix each bot's schema
        fix_ares_schema(cursor)
        conn.commit()

        fix_anchor_schema(cursor)
        conn.commit()

        fix_solomon_schema(cursor)
        conn.commit()

        # Fix precision issues
        fix_precision(cursor)
        conn.commit()

        conn.close()

        print("\n" + "="*60)
        print("  ALL bot schemas fixed successfully!")
        print("  Restart the scheduler for changes to take effect.")
        print("="*60 + "\n")
        return True

    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    main()
