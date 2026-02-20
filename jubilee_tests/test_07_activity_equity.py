#!/usr/bin/env python3
"""Test 7: Activity Log and Equity Snapshots

Verifies activity log and equity snapshots are being recorded.
Read-only — no data modification.
"""
import sys
import traceback
from datetime import datetime

HEADER = """
╔══════════════════════════════════════╗
║  TEST 7: Activity Log & Equity       ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    overall_pass = True

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        return

    # --- Check 7A: Activity Log (jubilee_logs) ---
    print("--- Check 7A: Activity Log (last 10 entries) ---")
    try:
        cursor.execute("""
            SELECT *
            FROM jubilee_logs
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        if rows:
            print(f"  Last {len(rows)} log entries:")
            for i, row in enumerate(rows):
                r = dict(zip(columns, row))
                print(f"\n  Entry {i+1}:")
                for key in ['log_id', 'timestamp', 'action', 'message', 'level']:
                    if key in r:
                        val = r[key]
                        # Truncate long messages
                        if isinstance(val, str) and len(val) > 150:
                            val = val[:150] + '...'
                        print(f"    {key}: {val}")
                if 'details' in r and r['details']:
                    details_str = str(r['details'])
                    if len(details_str) > 200:
                        details_str = details_str[:200] + '...'
                    print(f"    details: {details_str}")

            # Count total
            cursor.execute("SELECT COUNT(*) FROM jubilee_logs")
            total = int(cursor.fetchone()[0] or 0)
            print(f"\n  Total log entries: {total}")
            print(f"Result: ✅ PASS — activity log has data")
        else:
            print(f"  ❌ Activity log is EMPTY")
            print(f"Result: ❌ FAIL — no log entries")
            overall_pass = False
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot query logs")
        overall_pass = False
    print()

    # --- Check 7B: Box Spread Equity Snapshots ---
    print("--- Check 7B: Box Spread Equity Snapshots ---")
    try:
        # Today's count
        cursor.execute("""
            SELECT COUNT(*)
            FROM jubilee_equity_snapshots
            WHERE snapshot_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date
        """)
        today_count = int(cursor.fetchone()[0] or 0)

        # Per-day count for last 7 days
        cursor.execute("""
            SELECT (snapshot_time AT TIME ZONE 'America/Chicago')::date AS day,
                   COUNT(*) AS cnt
            FROM jubilee_equity_snapshots
            WHERE snapshot_time > NOW() - INTERVAL '7 days'
            GROUP BY day
            ORDER BY day DESC
        """)
        daily_rows = cursor.fetchall()

        print(f"  Box equity snapshots today: {today_count}")
        if daily_rows:
            print(f"  Per-day count (last 7 days):")
            for row in daily_rows:
                print(f"    {row[0]}: {row[1]} snapshots")
        else:
            print(f"  No snapshots in last 7 days")

        # Latest snapshot value
        cursor.execute("""
            SELECT snapshot_time, total_equity, total_capital, realized_pnl, unrealized_pnl
            FROM jubilee_equity_snapshots
            ORDER BY snapshot_time DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        if latest:
            equity = float(latest[1] or 0)
            print(f"\n  Latest snapshot:")
            print(f"    Time:           {latest[0]}")
            print(f"    Total Equity:   ${equity:,.2f}")
            print(f"    Total Capital:  ${float(latest[2] or 0):,.2f}")
            print(f"    Realized P&L:   ${float(latest[3] or 0):,.2f}")
            print(f"    Unrealized P&L: ${float(latest[4] or 0):,.2f}")

            # Sanity check
            if equity < 0:
                print(f"    ⚠️ Negative equity — unusual")
            elif equity > 10_000_000:
                print(f"    ⚠️ Equity > $10M — suspicious")
            elif equity == 0:
                print(f"    ⚠️ Zero equity — may not be recording correctly")

        print(f"\nResult: ✅ PASS — box equity snapshots queried")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Check 7C: IC Equity Snapshots ---
    print("--- Check 7C: IC Equity Snapshots ---")
    try:
        # Today's count
        cursor.execute("""
            SELECT COUNT(*)
            FROM jubilee_ic_equity_snapshots
            WHERE snapshot_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date
        """)
        today_count = int(cursor.fetchone()[0] or 0)

        # Per-day count for last 7 days
        cursor.execute("""
            SELECT (snapshot_time AT TIME ZONE 'America/Chicago')::date AS day,
                   COUNT(*) AS cnt
            FROM jubilee_ic_equity_snapshots
            WHERE snapshot_time > NOW() - INTERVAL '7 days'
            GROUP BY day
            ORDER BY day DESC
        """)
        daily_rows = cursor.fetchall()

        print(f"  IC equity snapshots today: {today_count}")
        if daily_rows:
            print(f"  Per-day count (last 7 days):")
            for row in daily_rows:
                print(f"    {row[0]}: {row[1]} snapshots")
        else:
            print(f"  No IC snapshots in last 7 days")

        # Check market hours
        try:
            from zoneinfo import ZoneInfo
            ct = ZoneInfo("America/Chicago")
        except ImportError:
            import pytz
            ct = pytz.timezone("America/Chicago")

        now_ct = datetime.now(ct)
        is_weekday = now_ct.weekday() < 5
        is_market_hours = 8 <= now_ct.hour < 16

        if today_count == 0 and is_weekday and is_market_hours:
            print(f"\n  ❌ IC equity snapshots NOT recording during market hours")
            overall_pass = False
            print(f"Result: ❌ FAIL — 0 snapshots today during market hours")
        elif today_count == 1 and is_weekday and is_market_hours and now_ct.hour >= 10:
            print(f"\n  ⚠️ Only 1 snapshot — scheduled job may not be running")
            print(f"Result: ⚠️ WARNING — only 1 snapshot")
        else:
            print(f"Result: ✅ PASS")

        # Latest IC snapshot
        cursor.execute("""
            SELECT snapshot_time, total_equity, total_capital, realized_pnl, unrealized_pnl
            FROM jubilee_ic_equity_snapshots
            ORDER BY snapshot_time DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        if latest:
            equity = float(latest[1] or 0)
            print(f"\n  Latest IC snapshot:")
            print(f"    Time:           {latest[0]}")
            print(f"    Total Equity:   ${equity:,.2f}")
            print(f"    Total Capital:  ${float(latest[2] or 0):,.2f}")
            print(f"    Realized P&L:   ${float(latest[3] or 0):,.2f}")
            print(f"    Unrealized P&L: ${float(latest[4] or 0):,.2f}")

            if equity < 0:
                print(f"    ⚠️ Negative IC equity")
            elif equity > 10_000_000:
                print(f"    ⚠️ IC equity > $10M — suspicious")
            elif equity == 0:
                print(f"    ⚠️ Zero IC equity — may not be recording")
        else:
            print(f"\n  No IC equity snapshots found at all")

    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Cleanup ---
    try:
        cursor.close()
        conn.close()
    except Exception:
        pass

    print(f"""
═══════════════════════════════
TEST 7 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
