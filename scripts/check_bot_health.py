#!/usr/bin/env python3
"""
Bot Health Check Script
=======================
Checks the status of all trading bots by querying heartbeats and recent activity.

Usage:
    python scripts/check_bot_health.py

    # Or with custom API URL:
    API_URL=https://your-api.onrender.com python scripts/check_bot_health.py
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

def check_database_heartbeats():
    """Check bot heartbeats directly from database"""
    print("\n" + "=" * 70)
    print("BOT HEARTBEATS (from database)")
    print("=" * 70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Get all bot heartbeats
        c.execute("""
            SELECT
                bot_name,
                last_heartbeat,
                status,
                scan_count,
                details
            FROM bot_heartbeats
            ORDER BY bot_name
        """)
        rows = c.fetchall()

        now = datetime.now(CENTRAL_TZ)

        if not rows:
            print("No heartbeat records found!")
            return

        print(f"\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print("-" * 70)
        print(f"{'Bot':<12} {'Last Heartbeat':<22} {'Age':<12} {'Status':<15} {'Scans':<6}")
        print("-" * 70)

        for row in rows:
            bot_name, last_heartbeat, status, scan_count, details = row

            if last_heartbeat:
                # Handle timezone
                if last_heartbeat.tzinfo is None:
                    last_heartbeat = last_heartbeat.replace(tzinfo=CENTRAL_TZ)
                else:
                    last_heartbeat = last_heartbeat.astimezone(CENTRAL_TZ)

                age = now - last_heartbeat
                age_minutes = age.total_seconds() / 60

                if age_minutes < 10:
                    age_str = f"{age_minutes:.1f}m ago"
                    health = "OK"
                elif age_minutes < 60:
                    age_str = f"{age_minutes:.0f}m ago"
                    health = "STALE"
                else:
                    age_str = f"{age_minutes/60:.1f}h ago"
                    health = "DEAD"

                hb_str = last_heartbeat.strftime('%H:%M:%S')
            else:
                hb_str = "Never"
                age_str = "N/A"
                health = "NEVER RAN"

            # Color coding for terminal
            if health == "OK":
                status_display = f"\033[92m{status or 'UNKNOWN'}\033[0m"  # Green
            elif health == "STALE":
                status_display = f"\033[93m{status or 'UNKNOWN'}\033[0m"  # Yellow
            else:
                status_display = f"\033[91m{status or 'UNKNOWN'}\033[0m"  # Red

            print(f"{bot_name:<12} {hb_str:<22} {age_str:<12} {status_display:<24} {scan_count or 0:<6}")

        conn.close()

    except Exception as e:
        print(f"Error checking heartbeats: {e}")
        import traceback
        traceback.print_exc()


def check_scan_activity():
    """Check recent scan activity for each bot"""
    print("\n" + "=" * 70)
    print("RECENT SCAN ACTIVITY")
    print("=" * 70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime('%Y-%m-%d')

        # Get scan counts by bot for today
        c.execute("""
            SELECT
                bot_name,
                COUNT(*) as total_scans,
                MAX(timestamp) as last_scan,
                SUM(CASE WHEN trade_executed THEN 1 ELSE 0 END) as trades,
                SUM(CASE WHEN outcome = 'ERROR' THEN 1 ELSE 0 END) as errors
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name
            ORDER BY bot_name
        """, (today,))
        rows = c.fetchall()

        print(f"\nToday's activity ({today}):")
        print("-" * 70)
        print(f"{'Bot':<12} {'Scans':<10} {'Last Scan':<22} {'Trades':<8} {'Errors':<8}")
        print("-" * 70)

        if not rows:
            print("No scan activity found for today!")
        else:
            for row in rows:
                bot_name, total_scans, last_scan, trades, errors = row

                if last_scan:
                    if last_scan.tzinfo is None:
                        last_scan = last_scan.replace(tzinfo=CENTRAL_TZ)
                    else:
                        last_scan = last_scan.astimezone(CENTRAL_TZ)
                    last_scan_str = last_scan.strftime('%H:%M:%S')

                    age = now - last_scan
                    age_minutes = age.total_seconds() / 60
                    if age_minutes > 10:
                        last_scan_str += f" ({age_minutes:.0f}m ago)"
                else:
                    last_scan_str = "Never"

                print(f"{bot_name:<12} {total_scans:<10} {last_scan_str:<22} {trades or 0:<8} {errors or 0:<8}")

        conn.close()

    except Exception as e:
        print(f"Error checking scan activity: {e}")
        import traceback
        traceback.print_exc()


def check_open_positions():
    """Check open positions for each bot"""
    print("\n" + "=" * 70)
    print("OPEN POSITIONS")
    print("=" * 70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Check FORTRESS positions
        try:
            c.execute("SELECT COUNT(*) FROM fortress_positions WHERE status = 'open'")
            fortress_open = c.fetchone()[0]
        except:
            fortress_open = "N/A"

        # Check SOLOMON positions
        try:
            c.execute("SELECT COUNT(*) FROM solomon_positions WHERE status = 'open'")
            solomon_open = c.fetchone()[0]
        except:
            solomon_open = "N/A"

        # Check GIDEON positions
        try:
            c.execute("SELECT COUNT(*) FROM gideon_positions WHERE status = 'open'")
            icarus_open = c.fetchone()[0]
        except:
            icarus_open = "N/A"

        # Check ANCHOR positions
        try:
            c.execute("SELECT COUNT(*) FROM anchor_positions WHERE status = 'open'")
            anchor_open = c.fetchone()[0]
        except:
            anchor_open = "N/A"

        # Check SAMSON positions
        try:
            c.execute("SELECT COUNT(*) FROM samson_positions WHERE status = 'open'")
            titan_open = c.fetchone()[0]
        except:
            titan_open = "N/A"

        print(f"\n{'Bot':<12} {'Open Positions':<15}")
        print("-" * 30)
        print(f"{'FORTRESS':<12} {fortress_open}")
        print(f"{'SOLOMON':<12} {solomon_open}")
        print(f"{'GIDEON':<12} {icarus_open}")
        print(f"{'ANCHOR':<12} {anchor_open}")
        print(f"{'SAMSON':<12} {titan_open}")

        conn.close()

    except Exception as e:
        print(f"Error checking positions: {e}")


def check_trading_window():
    """Check if we're in the trading window"""
    print("\n" + "=" * 70)
    print("TRADING WINDOW STATUS")
    print("=" * 70)

    now = datetime.now(CENTRAL_TZ)

    # Define trading windows (market closes at 3:00 PM CT)
    # Entry windows end 15 min before market close
    windows = {
        'FORTRESS': ('08:30', '14:45'),
        'SOLOMON': ('08:35', '14:30'),
        'GIDEON': ('08:35', '14:30'),
        'ANCHOR': ('08:30', '14:45'),
        'SAMSON': ('08:30', '14:45'),
        'CORNERSTONE': ('09:05', '09:10'),  # Daily run
        'ARGUS': ('08:30', '14:45'),
    }

    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Day of week: {now.strftime('%A')} (weekday={now.weekday()})")

    if now.weekday() >= 5:
        print("\n*** WEEKEND - Markets closed ***")
        return

    print("-" * 50)
    print(f"{'Bot':<12} {'Window':<20} {'Status':<15}")
    print("-" * 50)

    for bot, (start, end) in windows.items():
        start_h, start_m = map(int, start.split(':'))
        end_h, end_m = map(int, end.split(':'))

        start_time = now.replace(hour=start_h, minute=start_m, second=0)
        end_time = now.replace(hour=end_h, minute=end_m, second=0)

        if now < start_time:
            status = "Before window"
        elif now > end_time:
            status = "After window"
        else:
            status = "\033[92mIN WINDOW\033[0m"  # Green

        print(f"{bot:<12} {start} - {end} CT     {status}")


def main():
    print("\n" + "=" * 70)
    print("ALPHAGEX BOT HEALTH CHECK")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")

    check_trading_window()
    check_database_heartbeats()
    check_scan_activity()
    check_open_positions()

    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    print("""
If bots show "STALE" or "DEAD" heartbeats during trading window:
1. Check Render dashboard for alphagex-trader worker status
2. Review worker logs for errors
3. Restart the worker if needed

If scan activity stopped mid-day:
1. Worker likely crashed - check logs for stack trace
2. May need to redeploy to pick up latest code changes
""")


if __name__ == "__main__":
    main()
