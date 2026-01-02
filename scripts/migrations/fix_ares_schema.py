#!/usr/bin/env python3
"""
Quick fix for ARES positions table schema.
Run in Render shell: python scripts/migrations/fix_ares_schema.py

This adds all missing columns that prevent ARES from saving positions.
"""

import os
import sys

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database_adapter import get_connection


def fix_ares_schema():
    """Add all missing columns to ares_positions table"""
    print("\n" + "="*60)
    print("  ARES Schema Fix - Adding Missing Columns")
    print("="*60 + "\n")

    columns_to_add = [
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

    try:
        conn = get_connection()
        c = conn.cursor()

        added = 0
        skipped = 0

        for col_name, col_type in columns_to_add:
            try:
                sql = f"ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                c.execute(sql)
                print(f"  ✓ Added: {col_name} ({col_type})")
                added += 1
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"  - Exists: {col_name}")
                    skipped += 1
                else:
                    print(f"  ✗ Error: {col_name} - {e}")

        conn.commit()
        print(f"\n  Summary: {added} added, {skipped} already existed")

        # Fix numeric precision issues
        print("\n  Fixing numeric precision...")
        precision_fixes = [
            ("scan_activity", "signal_confidence", "DECIMAL(8, 4)"),
            ("scan_activity", "signal_win_probability", "DECIMAL(8, 4)"),
            ("ares_positions", "oracle_confidence", "DECIMAL(8, 4)"),
            ("ares_positions", "oracle_win_probability", "DECIMAL(8, 4)"),
        ]

        for table, column, new_type in precision_fixes:
            try:
                c.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}")
                print(f"  ✓ Fixed: {table}.{column} -> {new_type}")
            except Exception as e:
                print(f"  - Skip: {table}.{column} ({e})")

        conn.commit()
        conn.close()

        print("\n" + "="*60)
        print("  ARES schema fix complete!")
        print("="*60 + "\n")
        return True

    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    fix_ares_schema()
