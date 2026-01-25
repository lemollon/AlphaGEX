#!/usr/bin/env python3
"""
COMPREHENSIVE BOT EQUITY CURVE DIAGNOSTICS
==========================================
Run this in Render shell to diagnose why equity curves aren't showing for ANY bot.

Usage:
    python scripts/diagnose_all_bots.py
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

BOTS = {
    'ares': {'table': 'ares_positions', 'snapshots': 'ares_equity_snapshots', 'default_capital': 100000, 'type': 'ic'},
    'athena': {'table': 'athena_positions', 'snapshots': 'athena_equity_snapshots', 'default_capital': 100000, 'type': 'spread'},
    'titan': {'table': 'titan_positions', 'snapshots': 'titan_equity_snapshots', 'default_capital': 200000, 'type': 'ic'},
    'pegasus': {'table': 'pegasus_positions', 'snapshots': 'pegasus_equity_snapshots', 'default_capital': 200000, 'type': 'ic'},
    'icarus': {'table': 'icarus_positions', 'snapshots': 'icarus_equity_snapshots', 'default_capital': 100000, 'type': 'spread'},
}

def run_diagnostics():
    print("=" * 80)
    print("COMPREHENSIVE BOT EQUITY CURVE DIAGNOSTICS")
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

    issues_found = []

    # ========== STARTING CAPITAL CONFIG ==========
    print("=" * 80)
    print("1. STARTING CAPITAL CONFIGURATION")
    print("=" * 80)

    cursor.execute("""
        SELECT key, value FROM autonomous_config
        WHERE key LIKE '%_starting_capital'
        ORDER BY key
    """)
    configs = cursor.fetchall()

    config_map = {row[0]: row[1] for row in configs}

    for bot, info in BOTS.items():
        key = f"{bot}_starting_capital"
        if key in config_map:
            print(f"  ✅ {bot.upper()}: ${float(config_map[key]):,.0f}")
        else:
            print(f"  ⚠️  {bot.upper()}: NOT SET (using default ${info['default_capital']:,})")
            issues_found.append(f"{bot.upper()}: starting_capital not configured")

    # ========== POSITIONS TABLE CHECKS ==========
    print("\n" + "=" * 80)
    print("2. POSITIONS TABLES - DATA CHECK")
    print("=" * 80)

    for bot, info in BOTS.items():
        table = info['table']
        print(f"\n  --- {bot.upper()} ({table}) ---")

        # Check if table exists
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        exists = cursor.fetchone()[0]

        if not exists:
            print(f"    ❌ Table does NOT exist")
            issues_found.append(f"{bot.upper()}: positions table doesn't exist")
            continue

        print(f"    ✅ Table exists")

        # Count all positions
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total = cursor.fetchone()[0]
        print(f"    Total positions: {total}")

        # Count by status
        cursor.execute(f"""
            SELECT status, COUNT(*)
            FROM {table}
            GROUP BY status
            ORDER BY status
        """)
        statuses = cursor.fetchall()
        for status, count in statuses:
            print(f"      - {status}: {count}")

        # Count closed with close_time
        cursor.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE status IN ('closed', 'expired')
        """)
        closed_total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE status IN ('closed', 'expired')
            AND close_time IS NOT NULL
        """)
        closed_with_time = cursor.fetchone()[0]

        print(f"    Closed/expired positions: {closed_total}")
        print(f"    With close_time populated: {closed_with_time}")

        if closed_total > 0 and closed_with_time == 0:
            print(f"    ❌ CRITICAL: No closed positions have close_time!")
            issues_found.append(f"{bot.upper()}: {closed_total} closed positions but close_time is NULL for all")
        elif closed_with_time < closed_total:
            missing = closed_total - closed_with_time
            print(f"    ⚠️  {missing} closed positions missing close_time")
            issues_found.append(f"{bot.upper()}: {missing} closed positions missing close_time")
        elif closed_with_time > 0:
            print(f"    ✅ All closed positions have close_time")

        # Check realized_pnl
        cursor.execute(f"""
            SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0),
                   MIN(realized_pnl), MAX(realized_pnl)
            FROM {table}
            WHERE status IN ('closed', 'expired')
            AND realized_pnl IS NOT NULL
        """)
        pnl_row = cursor.fetchone()
        pnl_count = pnl_row[0] or 0
        pnl_sum = float(pnl_row[1] or 0)
        pnl_min = pnl_row[2]
        pnl_max = pnl_row[3]

        print(f"    Positions with realized_pnl: {pnl_count}")
        if pnl_count > 0:
            print(f"    Total realized P&L: ${pnl_sum:,.2f}")
            print(f"    Range: ${float(pnl_min or 0):,.2f} to ${float(pnl_max or 0):,.2f}")

        if closed_total > 0 and pnl_count == 0:
            print(f"    ❌ CRITICAL: No closed positions have realized_pnl!")
            issues_found.append(f"{bot.upper()}: closed positions exist but realized_pnl is NULL")

    # ========== SNAPSHOT TABLE CHECKS ==========
    print("\n" + "=" * 80)
    print("3. EQUITY SNAPSHOTS TABLES")
    print("=" * 80)

    today = now.strftime('%Y-%m-%d')

    for bot, info in BOTS.items():
        table = info['snapshots']
        print(f"\n  --- {bot.upper()} ({table}) ---")

        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        exists = cursor.fetchone()[0]

        if not exists:
            print(f"    ❌ Table does NOT exist")
            issues_found.append(f"{bot.upper()}: snapshots table doesn't exist")
            continue

        print(f"    ✅ Table exists")

        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total = cursor.fetchone()[0]
        print(f"    Total snapshots: {total}")

        cursor.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_count = cursor.fetchone()[0]
        print(f"    Today's snapshots: {today_count}")

        if today_count == 0:
            print(f"    ⚠️  No snapshots today")

        # Latest snapshot
        cursor.execute(f"""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl
            FROM {table}
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            print(f"    Latest: {row[0]}")
            print(f"      Balance: ${float(row[1] or 0):,.2f}")
            print(f"      Unrealized: ${float(row[2] or 0):,.2f}")
            print(f"      Realized: ${float(row[3] or 0):,.2f}")

    # ========== TEST HISTORICAL EQUITY CURVE QUERY ==========
    print("\n" + "=" * 80)
    print("4. HISTORICAL EQUITY CURVE QUERY TEST")
    print("=" * 80)

    for bot, info in BOTS.items():
        table = info['table']
        print(f"\n  --- {bot.upper()} ---")

        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        if not cursor.fetchone()[0]:
            print(f"    ❌ Skipped - table doesn't exist")
            continue

        try:
            # This is the EXACT query used by equity curve endpoints
            cursor.execute(f"""
                SELECT DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') as close_date,
                       SUM(realized_pnl) as daily_pnl,
                       COUNT(*) as trade_count
                FROM {table}
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NOT NULL
                GROUP BY DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago')
                ORDER BY close_date
                LIMIT 10
            """)
            rows = cursor.fetchall()

            if rows:
                print(f"    ✅ Query returned {len(rows)} days of data")
                print(f"    Sample data (first 5 days):")
                for row in rows[:5]:
                    print(f"      {row[0]}: ${float(row[1]):,.2f} ({row[2]} trades)")
            else:
                print(f"    ❌ Query returned NO DATA")
                print(f"       This is why historical equity curve is empty!")
                issues_found.append(f"{bot.upper()}: historical equity query returns no data")

        except Exception as e:
            print(f"    ❌ Query FAILED: {e}")
            issues_found.append(f"{bot.upper()}: historical equity query failed - {e}")

    # ========== COLUMN TYPE CHECK ==========
    print("\n" + "=" * 80)
    print("5. COLUMN TYPE VERIFICATION")
    print("=" * 80)

    for bot, info in BOTS.items():
        table = info['table']
        print(f"\n  --- {bot.upper()} ({table}) ---")

        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        if not cursor.fetchone()[0]:
            continue

        cursor.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table}'
            AND column_name IN ('close_time', 'open_time', 'realized_pnl', 'status')
            ORDER BY column_name
        """)
        cols = cursor.fetchall()

        for col_name, col_type in cols:
            expected = {
                'close_time': 'timestamp with time zone',
                'open_time': 'timestamp with time zone',
                'realized_pnl': 'numeric',
                'status': 'character varying'
            }
            if col_name in expected:
                if expected[col_name] in col_type:
                    print(f"    ✅ {col_name}: {col_type}")
                else:
                    print(f"    ⚠️  {col_name}: {col_type} (expected {expected[col_name]})")
                    issues_found.append(f"{bot.upper()}: {col_name} type is {col_type}, expected {expected[col_name]}")

    conn.close()

    # ========== SUMMARY ==========
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)

    if issues_found:
        print(f"\n❌ {len(issues_found)} ISSUE(S) FOUND:\n")
        for i, issue in enumerate(issues_found, 1):
            print(f"   {i}. {issue}")

        print("\n" + "=" * 80)
        print("RECOMMENDED FIXES")
        print("=" * 80)

        # Group recommendations
        if any("close_time is NULL" in i for i in issues_found):
            print("""
1. POPULATE MISSING close_time VALUES:

   For positions that are closed but missing close_time:

   UPDATE ares_positions
   SET close_time = updated_at  -- or open_time + interval '1 day'
   WHERE status IN ('closed', 'expired')
   AND close_time IS NULL;

   (Repeat for each bot's positions table)
""")

        if any("starting_capital not configured" in i for i in issues_found):
            print("""
2. SET STARTING CAPITAL IN CONFIG:

   INSERT INTO autonomous_config (key, value) VALUES
   ('ares_starting_capital', '100000'),
   ('athena_starting_capital', '100000'),
   ('titan_starting_capital', '200000'),
   ('pegasus_starting_capital', '200000'),
   ('icarus_starting_capital', '100000')
   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
""")

        if any("snapshots table doesn't exist" in i for i in issues_found):
            print("""
3. SNAPSHOTS TABLE WILL AUTO-CREATE:

   Snapshot tables are created automatically by the scheduler.
   Ensure the scheduler worker (alphagex-trader) is running.
""")

        if any("realized_pnl is NULL" in i for i in issues_found):
            print("""
4. POPULATE MISSING realized_pnl VALUES:

   For Iron Condor bots (credit received):
   UPDATE ares_positions
   SET realized_pnl = (total_credit - COALESCE(close_price, 0)) * contracts * 100
   WHERE status IN ('closed', 'expired')
   AND realized_pnl IS NULL;

   For Directional bots (debit paid):
   UPDATE athena_positions
   SET realized_pnl = (COALESCE(close_price, 0) - entry_debit) * contracts * 100
   WHERE status IN ('closed', 'expired')
   AND realized_pnl IS NULL;
""")
    else:
        print("\n✅ No critical issues found - data should be available")
        print("   If charts still don't show, check frontend console for errors")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    run_diagnostics()
