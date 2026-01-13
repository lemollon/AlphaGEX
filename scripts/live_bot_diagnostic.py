#!/usr/bin/env python3
"""
LIVE BOT DIAGNOSTIC - Run during market hours to identify why bots aren't trading

This script checks:
1. Are bots actually running (scheduler heartbeats)?
2. Are scans being logged to scan_activity?
3. What's blocking trades (thresholds, open positions, etc)?
4. Is the database accessible?

RUN THIS ON RENDER API SERVICE:
  python scripts/live_bot_diagnostic.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def run_diagnostic():
    print("=" * 80)
    print("LIVE BOT DIAGNOSTIC")
    now = datetime.now(CENTRAL_TZ)
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S CT')} ({now.strftime('%A')})")
    print("=" * 80)

    # Check market hours
    market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
    is_weekday = now.weekday() < 5

    if not is_weekday:
        print("\n[WARNING] Today is a weekend - bots won't trade")
    elif now < market_open:
        print(f"\n[INFO] Market opens at 8:30 AM CT ({market_open - now} from now)")
    elif now >= market_close:
        print(f"\n[INFO] Market closed at 3:00 PM CT ({now - market_close} ago)")
    else:
        print(f"\n[OK] Market is OPEN (closes in {market_close - now})")

    # Database connection
    print("\n" + "-" * 60)
    print("DATABASE CONNECTION")
    print("-" * 60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("[OK] Database connected successfully")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return

    today = now.strftime("%Y-%m-%d")

    def safe_execute(query, params=None):
        """Execute query with automatic rollback on error"""
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            conn.rollback()  # Critical: rollback to clear aborted transaction
            raise e

    # 1. Bot Heartbeats (are bots running?)
    print("\n" + "-" * 60)
    print("BOT HEARTBEATS (Last 30 minutes)")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, status, scan_count, last_heartbeat, details
            FROM bot_heartbeats
            ORDER BY last_heartbeat DESC
        """)
        if rows:
            recent_count = 0
            for row in rows:
                bot, status, scans, last_hb, details = row
                # Handle timezone-aware timestamps from database (stored as UTC)
                if last_hb:
                    if last_hb.tzinfo is None:
                        # Assume UTC if no timezone
                        from zoneinfo import ZoneInfo
                        last_hb = last_hb.replace(tzinfo=ZoneInfo("UTC"))
                    # Convert to Central Time for comparison
                    last_hb_ct = last_hb.astimezone(CENTRAL_TZ)
                    age = (now - last_hb_ct).total_seconds()
                    if age < 1800:  # 30 minutes
                        recent_count += 1
                else:
                    age = 99999
                age_str = f"{int(age)}s ago" if age < 3600 else f"{int(age/3600)}h ago"
                status_flag = "🟢" if age < 600 else "🟡" if age < 1800 else "🔴"
                print(f"  {status_flag} {bot:10} | {status:15} | Scans: {scans:5} | {age_str}")
            if recent_count == 0:
                print("\n  [WARNING] No heartbeats in last 30 minutes - bots may not be running!")
        else:
            print("  [WARNING] No heartbeats found - scheduler has never run!")
    except Exception as e:
        print(f"  [ERROR] Could not check heartbeats: {e}")

    # 2. Scan Activity (are scans being logged?)
    print("\n" + "-" * 60)
    print("SCAN ACTIVITY TODAY")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT
                bot_name,
                outcome,
                COUNT(*) as count,
                MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name, outcome
            ORDER BY bot_name, count DESC
        """, (today,))
        if rows:
            current_bot = None
            for row in rows:
                bot, outcome, count, last_scan = row
                if bot != current_bot:
                    if current_bot is not None:
                        print()
                    current_bot = bot
                    print(f"  {bot}:")
                # Convert timestamp to CT for display
                if last_scan:
                    if last_scan.tzinfo is None:
                        last_scan = last_scan.replace(tzinfo=ZoneInfo("UTC"))
                    last_ct = last_scan.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT')
                else:
                    last_ct = 'N/A'
                print(f"    {outcome:15} : {count:4} scans (last: {last_ct})")
        else:
            print("  [WARNING] No scan activity logged today!")
    except Exception as e:
        print(f"  [ERROR] Could not check scan activity: {e}")

    # 3. Open Positions (blocking new trades?)
    print("\n" + "-" * 60)
    print("OPEN POSITIONS")
    print("-" * 60)

    # Correct table names matching actual database schema
    position_tables = [
        ('ares_ic_positions', 'ARES'),
        ('athena_directional_positions', 'ATHENA'),
        ('pegasus_ic_positions', 'PEGASUS'),
        ('icarus_directional_positions', 'ICARUS'),
        ('titan_ic_positions', 'TITAN'),
    ]

    for table, bot in position_tables:
        try:
            rows = safe_execute(f"""
                SELECT COUNT(*), MAX(entry_time), SUM(COALESCE(entry_credit, 0))
                FROM {table}
                WHERE status = 'OPEN'
            """)
            row = rows[0] if rows else None
            if row and row[0] > 0:
                entry_time = row[1]
                # Convert entry_time to CT for display
                if entry_time and entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=ZoneInfo("UTC"))
                entry_ct = entry_time.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT') if entry_time else 'N/A'
                print(f"  {bot:10} : {row[0]} open | Entry: {entry_ct} | Credit: ${row[2] or 0:.2f}")
            else:
                print(f"  {bot:10} : No open positions")
        except Exception as e:
            conn.rollback()  # Rollback on error to clear transaction
            if 'does not exist' in str(e).lower():
                print(f"  {bot:10} : Table not found ({table})")
            else:
                print(f"  {bot:10} : Error - {e}")

    # 4. Recent Oracle Predictions
    print("\n" + "-" * 60)
    print("ORACLE PREDICTIONS TODAY")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, COUNT(*),
                   AVG(win_probability::numeric),
                   AVG(confidence::numeric),
                   MAX(prediction_time)
            FROM oracle_predictions
            WHERE trade_date = %s
            GROUP BY bot_name
            ORDER BY bot_name
        """, (today,))
        if rows:
            for row in rows:
                bot, count, avg_wp, avg_conf, last = row
                avg_wp = float(avg_wp) if avg_wp else 0
                avg_conf = float(avg_conf) if avg_conf else 0
                print(f"  {bot:10} : {count:3} predictions | Avg WP: {avg_wp:.0%} | Avg Conf: {avg_conf:.0%}")
        else:
            print("  [INFO] No Oracle predictions stored today")
    except Exception as e:
        print(f"  [ERROR] Could not check Oracle predictions: {e}")

    # 5. Latest NO_TRADE Reasons
    print("\n" + "-" * 60)
    print("RECENT NO_TRADE REASONS (Last 20)")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT
                bot_name,
                timestamp,
                decision_summary,
                oracle_win_probability,
                quant_ml_win_probability,
                min_win_probability_threshold
            FROM scan_activity
            WHERE date = %s AND outcome = 'NO_TRADE'
            ORDER BY timestamp DESC
            LIMIT 20
        """, (today,))
        if rows:
            for row in rows:
                bot, ts, decision, oracle_wp, ml_wp, threshold = row
                # Convert timestamp to CT
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=ZoneInfo("UTC"))
                time_ct = ts.astimezone(CENTRAL_TZ).strftime('%I:%M %p') if ts else 'N/A'
                oracle_wp = float(oracle_wp) if oracle_wp else 0
                ml_wp = float(ml_wp) if ml_wp else 0
                threshold = float(threshold) if threshold else 0
                print(f"  {bot:8} @ {time_ct:>10} | Oracle:{oracle_wp:.0%} ML:{ml_wp:.0%} Thresh:{threshold:.0%}")
                if decision:
                    print(f"           Reason: {decision[:60]}")
        else:
            print("  [INFO] No NO_TRADE scans logged today")
    except Exception as e:
        print(f"  [ERROR] Could not check NO_TRADE reasons: {e}")

    # 6. Check config thresholds in database
    print("\n" + "-" * 60)
    print("BOT CONFIGURATION THRESHOLDS")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, config_key, config_value
            FROM autonomous_config
            WHERE config_key LIKE '%min_win%' OR config_key LIKE '%confidence%' OR config_key LIKE '%threshold%'
            ORDER BY bot_name, config_key
        """)
        if rows:
            current_bot = None
            for row in rows:
                bot, key, value = row
                if bot != current_bot:
                    current_bot = bot
                    print(f"\n  {bot}:")
                print(f"    {key}: {value}")
        else:
            print("  [INFO] No config thresholds in database (using code defaults)")
    except Exception as e:
        if 'does not exist' in str(e).lower():
            print("  [INFO] autonomous_config table not found (using code defaults)")
        else:
            print(f"  [ERROR] {e}")

    # 7. Check if scheduler is running
    print("\n" + "-" * 60)
    print("SCHEDULER STATUS")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 hour') as last_hour,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '5 minutes') as last_5min,
                   MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name
        """, (today,))
        if rows:
            for row in rows:
                bot, last_hour, last_5min, last_scan = row
                status = "🟢 ACTIVE" if last_5min > 0 else ("🟡 SLOW" if last_hour > 0 else "🔴 STALE")
                # Convert last_scan to CT
                if last_scan and last_scan.tzinfo is None:
                    last_scan = last_scan.replace(tzinfo=ZoneInfo("UTC"))
                last_ct = last_scan.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT') if last_scan else 'N/A'
                print(f"  {bot:10} | Last hour: {last_hour:3} | Last 5min: {last_5min:2} | {status} | Last: {last_ct}")
        else:
            print("  [WARNING] No scans today - scheduler may not be running")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)

    # Check for common issues
    issues = []

    # Check heartbeats
    try:
        rows = safe_execute("""
            SELECT COUNT(*) FROM bot_heartbeats
            WHERE last_heartbeat >= NOW() - INTERVAL '10 minutes'
        """)
        if rows and rows[0][0] == 0:
            issues.append("No bot heartbeats in last 10 minutes - scheduler may be down")
    except:
        pass

    # Check scan activity during market hours
    if is_weekday and market_open <= now < market_close:
        try:
            rows = safe_execute("""
                SELECT COUNT(*) FROM scan_activity
                WHERE date = %s
                AND outcome NOT IN ('BEFORE_WINDOW', 'AFTER_WINDOW', 'MARKET_CLOSED')
            """, (today,))
            if rows and rows[0][0] == 0:
                issues.append("No market-hours scans logged today - bots may not be scanning")
        except:
            pass

    if issues:
        print("\n[ISSUES FOUND]:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n[OK] No critical issues detected")

    print("\n[TIP] Run this script during market hours (8:30 AM - 3:00 PM CT) for best results")

    conn.close()


if __name__ == "__main__":
    run_diagnostic()
