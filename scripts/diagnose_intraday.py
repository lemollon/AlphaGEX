#!/usr/bin/env python3
"""
ARES Intraday Snapshot Diagnostic Script
Run this in Render shell to diagnose why intraday equity chart isn't working.

Usage:
    python scripts/diagnose_intraday.py
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

def run_diagnostics():
    print("=" * 70)
    print("ARES INTRADAY SNAPSHOT DIAGNOSTICS")
    print("=" * 70)

    now = datetime.now(CENTRAL_TZ)
    today = now.strftime('%Y-%m-%d')
    print(f"\nCurrent time (CT): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Today: {today}")

    # Market hours check
    is_weekday = now.weekday() < 5
    market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
    is_market_hours = market_open <= now <= market_close

    print(f"\nMarket Status:")
    print(f"  Is weekday: {is_weekday}")
    print(f"  Is market hours (8:30-15:00 CT): {is_market_hours}")
    if not is_weekday:
        print("  ⚠️  Weekend - scheduler won't save snapshots")
    elif not is_market_hours:
        print(f"  ⚠️  Outside market hours - scheduler won't save snapshots")
    else:
        print("  ✅ Market is open - scheduler should be saving snapshots")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("\n✅ Database connection successful")
    except Exception as e:
        print(f"\n❌ Database connection FAILED: {e}")
        return

    # ========== ARES EQUITY SNAPSHOTS TABLE ==========
    print("\n" + "=" * 70)
    print("ARES EQUITY SNAPSHOTS TABLE")
    print("=" * 70)

    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'ares_equity_snapshots'
        )
    """)
    table_exists = cursor.fetchone()[0]

    if not table_exists:
        print("\n❌ ares_equity_snapshots table does NOT EXIST")
        print("   This is the root cause - no table means no snapshots!")
        print("   The scheduler creates this table when it first runs during market hours.")
    else:
        print("\n✅ ares_equity_snapshots table exists")

        # Get columns
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'ares_equity_snapshots'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        print(f"\n   Columns ({len(columns)}):")
        for col_name, col_type in columns:
            print(f"     - {col_name}: {col_type}")

        # Check for required columns
        col_names = {c[0] for c in columns}
        required = {'timestamp', 'balance', 'unrealized_pnl', 'realized_pnl', 'open_positions'}
        missing = required - col_names
        if missing:
            print(f"\n   ❌ MISSING REQUIRED COLUMNS: {missing}")
        else:
            print(f"\n   ✅ All required columns present")

        # Count snapshots
        cursor.execute("SELECT COUNT(*) FROM ares_equity_snapshots")
        total = cursor.fetchone()[0]
        print(f"\n   Total snapshots: {total}")

        cursor.execute("""
            SELECT COUNT(*) FROM ares_equity_snapshots
            WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_count = cursor.fetchone()[0]
        print(f"   Today's snapshots: {today_count}")

        if today_count == 0:
            print("   ⚠️  No snapshots today - this is why intraday chart is empty!")

        # Get latest snapshot
        cursor.execute("""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note
            FROM ares_equity_snapshots
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            print(f"\n   Latest snapshot:")
            print(f"     Timestamp: {row[0]}")
            print(f"     Balance: ${row[1]:,.2f}" if row[1] else "     Balance: NULL")
            print(f"     Unrealized P&L: ${row[2]:,.2f}" if row[2] else "     Unrealized P&L: NULL")
            print(f"     Realized P&L: ${row[3]:,.2f}" if row[3] else "     Realized P&L: NULL")
            print(f"     Open positions: {row[4]}")
            print(f"     Note: {row[5]}")

            # Time since last snapshot
            if row[0]:
                last_ts = row[0]
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=CENTRAL_TZ)
                delta = now - last_ts
                hours = delta.total_seconds() / 3600
                print(f"\n   ⏱️  Time since last snapshot: {hours:.1f} hours")
                if hours > 1:
                    print("   ⚠️  Last snapshot is old - scheduler may not be running")
        else:
            print("\n   ❌ No snapshots ever saved!")

    # ========== ARES POSITIONS TABLE ==========
    print("\n" + "=" * 70)
    print("ARES POSITIONS TABLE")
    print("=" * 70)

    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'ares_positions'
        )
    """)
    pos_exists = cursor.fetchone()[0]

    if not pos_exists:
        print("\n❌ ares_positions table does NOT EXIST")
    else:
        print("\n✅ ares_positions table exists")

        cursor.execute("SELECT COUNT(*) FROM ares_positions WHERE status = 'open'")
        open_count = cursor.fetchone()[0]
        print(f"   Open positions: {open_count}")

        cursor.execute("SELECT COUNT(*) FROM ares_positions WHERE status IN ('closed', 'expired')")
        closed_count = cursor.fetchone()[0]
        print(f"   Closed positions: {closed_count}")

        cursor.execute("SELECT COALESCE(SUM(realized_pnl), 0) FROM ares_positions WHERE status IN ('closed', 'expired')")
        total_pnl = cursor.fetchone()[0]
        print(f"   Total realized P&L: ${float(total_pnl):,.2f}")

    # ========== TITAN COMPARISON ==========
    print("\n" + "=" * 70)
    print("TITAN COMPARISON (for reference)")
    print("=" * 70)

    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'titan_equity_snapshots'
        )
    """)
    titan_exists = cursor.fetchone()[0]

    if titan_exists:
        cursor.execute("SELECT COUNT(*) FROM titan_equity_snapshots")
        titan_total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM titan_equity_snapshots
            WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        titan_today = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(timestamp) FROM titan_equity_snapshots")
        titan_last = cursor.fetchone()[0]

        print(f"\n   TITAN total snapshots: {titan_total}")
        print(f"   TITAN today's snapshots: {titan_today}")
        print(f"   TITAN last snapshot: {titan_last}")

        if titan_today > 0 and today_count == 0:
            print("\n   ⚠️  TITAN has snapshots today but ARES doesn't!")
            print("      This suggests ARES-specific issue in scheduler")
        elif titan_today == 0 and today_count == 0:
            print("\n   ℹ️  Neither TITAN nor ARES have snapshots today")
            print("      Scheduler may not be running or market is closed")
    else:
        print("\n   titan_equity_snapshots table doesn't exist")

    # ========== CONFIG CHECK ==========
    print("\n" + "=" * 70)
    print("CONFIGURATION")
    print("=" * 70)

    cursor.execute("SELECT key, value FROM autonomous_config WHERE key LIKE '%starting_capital'")
    configs = cursor.fetchall()
    if configs:
        print("\n   Starting capital configs:")
        for key, val in configs:
            print(f"     {key}: ${float(val):,.2f}" if val else f"     {key}: NOT SET")
    else:
        print("\n   ⚠️  No starting_capital configs found - using defaults")

    conn.close()

    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)

    issues = []
    if not table_exists:
        issues.append("ares_equity_snapshots table doesn't exist")
    elif today_count == 0:
        issues.append("No snapshots saved today")

    if issues:
        print("\n❌ ISSUES FOUND:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print("\n📋 RECOMMENDED ACTIONS:")
        print("   1. Check if scheduler worker (alphagex-trader) is running on Render")
        print("   2. Check scheduler logs for EQUITY_SNAPSHOTS errors")
        print("   3. If market is open, snapshots should save every 5 minutes")
    else:
        print("\n✅ No issues found - snapshots are being saved")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    run_diagnostics()
