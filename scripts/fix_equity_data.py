#!/usr/bin/env python3
"""
FIX EQUITY CURVE DATA
=====================
Run this to fix missing data that prevents equity curves from showing.

Fixes:
1. Sets starting_capital config for all bots
2. Populates missing close_time for closed positions
3. Calculates missing realized_pnl for closed positions

Usage:
    python scripts/fix_equity_data.py
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")


def fix_all_data():
    print("=" * 80)
    print("FIX EQUITY CURVE DATA")
    print("=" * 80)

    now = datetime.now(CENTRAL_TZ)
    print(f"\nTimestamp: {now.strftime('%Y-%m-%d %H:%M:%S CT')}")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("✅ Database connection successful\n")
    except Exception as e:
        print(f"❌ Database connection FAILED: {e}")
        return

    fixes_applied = 0

    # ========== FIX 1: SET STARTING CAPITAL ==========
    print("=" * 80)
    print("FIX 1: SETTING STARTING CAPITAL CONFIG")
    print("=" * 80)

    capitals = {
        'ares_starting_capital': '100000',
        'athena_starting_capital': '100000',
        'titan_starting_capital': '200000',
        'pegasus_starting_capital': '200000',
        'icarus_starting_capital': '100000',
    }

    for key, value in capitals.items():
        try:
            cursor.execute("""
                INSERT INTO autonomous_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (key, value))
            print(f"  ✅ Set {key} = ${int(value):,}")
            fixes_applied += 1
        except Exception as e:
            print(f"  ❌ Failed to set {key}: {e}")

    conn.commit()

    # ========== FIX 2: POPULATE CLOSE_TIME ==========
    print("\n" + "=" * 80)
    print("FIX 2: POPULATE MISSING close_time FOR CLOSED POSITIONS")
    print("=" * 80)

    tables = ['ares_positions', 'athena_positions', 'titan_positions', 'pegasus_positions', 'icarus_positions']

    for table in tables:
        try:
            # Check if table exists
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            if not cursor.fetchone()[0]:
                print(f"  ⚠️  {table}: Table doesn't exist, skipping")
                continue

            # Count positions needing fix
            cursor.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE status IN ('closed', 'expired')
                AND close_time IS NULL
            """)
            count = cursor.fetchone()[0]

            if count == 0:
                print(f"  ✅ {table}: No positions need close_time fix")
                continue

            # Check if updated_at column exists
            cursor.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = 'updated_at'
            """)
            has_updated_at = cursor.fetchone() is not None

            if has_updated_at:
                # Use updated_at as close_time
                cursor.execute(f"""
                    UPDATE {table}
                    SET close_time = updated_at
                    WHERE status IN ('closed', 'expired')
                    AND close_time IS NULL
                    AND updated_at IS NOT NULL
                """)
            else:
                # Fallback: use open_time + 1 day
                cursor.execute(f"""
                    UPDATE {table}
                    SET close_time = open_time + interval '1 day'
                    WHERE status IN ('closed', 'expired')
                    AND close_time IS NULL
                    AND open_time IS NOT NULL
                """)

            updated = cursor.rowcount
            print(f"  ✅ {table}: Fixed close_time for {updated} positions")
            fixes_applied += updated

        except Exception as e:
            print(f"  ❌ {table}: Failed - {e}")

    conn.commit()

    # ========== FIX 3: CALCULATE REALIZED P&L ==========
    print("\n" + "=" * 80)
    print("FIX 3: CALCULATE MISSING realized_pnl FOR CLOSED POSITIONS")
    print("=" * 80)

    # Iron Condor bots: P&L = (credit_received - close_price) * contracts * 100
    ic_bots = ['ares_positions', 'titan_positions', 'pegasus_positions']

    for table in ic_bots:
        try:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            if not cursor.fetchone()[0]:
                print(f"  ⚠️  {table}: Table doesn't exist, skipping")
                continue

            # Count positions needing fix
            cursor.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NULL
            """)
            count = cursor.fetchone()[0]

            if count == 0:
                print(f"  ✅ {table}: No positions need realized_pnl fix")
                continue

            # For IC: P&L = (total_credit - close_price) * contracts * 100
            # If close_price is NULL (expired worthless), P&L = total_credit * contracts * 100
            cursor.execute(f"""
                UPDATE {table}
                SET realized_pnl = (total_credit - COALESCE(close_price, 0)) * contracts * 100
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NULL
                AND total_credit IS NOT NULL
                AND contracts IS NOT NULL
            """)
            updated = cursor.rowcount
            print(f"  ✅ {table}: Calculated realized_pnl for {updated} IC positions")
            fixes_applied += updated

        except Exception as e:
            print(f"  ❌ {table}: Failed - {e}")

    # Directional spread bots: P&L = (close_price - entry_debit) * contracts * 100
    spread_bots = ['athena_positions', 'icarus_positions']

    for table in spread_bots:
        try:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            if not cursor.fetchone()[0]:
                print(f"  ⚠️  {table}: Table doesn't exist, skipping")
                continue

            cursor.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NULL
            """)
            count = cursor.fetchone()[0]

            if count == 0:
                print(f"  ✅ {table}: No positions need realized_pnl fix")
                continue

            # For spreads: P&L = (close_price - entry_debit) * contracts * 100
            # If expired worthless (close_price NULL or 0), P&L = -entry_debit * contracts * 100
            cursor.execute(f"""
                UPDATE {table}
                SET realized_pnl = (COALESCE(close_price, 0) - entry_debit) * contracts * 100
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NULL
                AND entry_debit IS NOT NULL
                AND contracts IS NOT NULL
            """)
            updated = cursor.rowcount
            print(f"  ✅ {table}: Calculated realized_pnl for {updated} spread positions")
            fixes_applied += updated

        except Exception as e:
            print(f"  ❌ {table}: Failed - {e}")

    conn.commit()

    # ========== FIX 4: CREATE SNAPSHOT TABLES IF MISSING ==========
    print("\n" + "=" * 80)
    print("FIX 4: CREATE SNAPSHOT TABLES IF MISSING")
    print("=" * 80)

    snapshot_tables = [
        'ares_equity_snapshots',
        'athena_equity_snapshots',
        'titan_equity_snapshots',
        'pegasus_equity_snapshots',
        'icarus_equity_snapshots'
    ]

    for table in snapshot_tables:
        try:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    balance DECIMAL(12, 2) NOT NULL,
                    unrealized_pnl DECIMAL(12, 2),
                    realized_pnl DECIMAL(12, 2),
                    open_positions INTEGER,
                    note TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            print(f"  ✅ {table}: Ensured table exists")
            fixes_applied += 1
        except Exception as e:
            print(f"  ❌ {table}: Failed - {e}")

    conn.commit()
    conn.close()

    # ========== SUMMARY ==========
    print("\n" + "=" * 80)
    print("FIX SUMMARY")
    print("=" * 80)
    print(f"\n✅ Applied {fixes_applied} fixes")
    print("\nNow run: python scripts/diagnose_all_bots.py")
    print("to verify all issues are resolved.")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    fix_all_data()
