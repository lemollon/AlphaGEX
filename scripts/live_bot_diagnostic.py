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

    # 1. Bot Heartbeats (are bots running?)
    print("\n" + "-" * 60)
    print("BOT HEARTBEATS (Last 30 minutes)")
    print("-" * 60)

    try:
        cursor.execute("""
            SELECT bot_name, status, scan_count, last_heartbeat, details
            FROM bot_heartbeats
            WHERE last_heartbeat >= NOW() - INTERVAL '30 minutes'
            ORDER BY last_heartbeat DESC
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, status, scans, last_hb, details = row
                age = (now.replace(tzinfo=None) - last_hb.replace(tzinfo=None)).total_seconds() if last_hb else 0
                print(f"  {bot:10} | {status:15} | Scans: {scans:5} | {age:.0f}s ago")
        else:
            print("  [WARNING] No heartbeats in last 30 minutes - bots may not be running!")
    except Exception as e:
        print(f"  [ERROR] Could not check heartbeats: {e}")

    # 2. Scan Activity (are scans being logged?)
    print("\n" + "-" * 60)
    print("SCAN ACTIVITY TODAY")
    print("-" * 60)

    try:
        cursor.execute("""
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
        rows = cursor.fetchall()
        if rows:
            current_bot = None
            for row in rows:
                bot, outcome, count, last_scan = row
                if bot != current_bot:
                    if current_bot is not None:
                        print()
                    current_bot = bot
                    print(f"  {bot}:")
                print(f"    {outcome:15} : {count:4} scans (last: {last_scan.strftime('%I:%M %p') if last_scan else 'N/A'})")
        else:
            print("  [WARNING] No scan activity logged today!")
    except Exception as e:
        print(f"  [ERROR] Could not check scan activity: {e}")

    # 3. Open Positions (blocking new trades?)
    print("\n" + "-" * 60)
    print("OPEN POSITIONS")
    print("-" * 60)

    position_tables = [
        ('ares_positions', 'ARES'),
        ('athena_positions', 'ATHENA'),
        ('pegasus_positions', 'PEGASUS'),
        ('icarus_positions', 'ICARUS'),
        ('titan_positions', 'TITAN'),
    ]

    for table, bot in position_tables:
        try:
            cursor.execute(f"""
                SELECT COUNT(*), MAX(entry_time), SUM(COALESCE(entry_credit, 0))
                FROM {table}
                WHERE status = 'OPEN'
            """)
            row = cursor.fetchone()
            if row and row[0] > 0:
                print(f"  {bot:10} : {row[0]} open | Last entry: {row[1]} | Credit: ${row[2] or 0:.2f}")
            else:
                print(f"  {bot:10} : No open positions")
        except Exception as e:
            if 'does not exist' in str(e).lower():
                print(f"  {bot:10} : Table not found ({table})")
            else:
                print(f"  {bot:10} : Error - {e}")

    # 4. Recent Oracle Predictions
    print("\n" + "-" * 60)
    print("ORACLE PREDICTIONS TODAY")
    print("-" * 60)

    try:
        cursor.execute("""
            SELECT bot_name, COUNT(*),
                   AVG(win_probability::numeric),
                   AVG(confidence::numeric),
                   MAX(prediction_time)
            FROM oracle_predictions
            WHERE trade_date = %s
            GROUP BY bot_name
            ORDER BY bot_name
        """, (today,))
        rows = cursor.fetchall()
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
        cursor.execute("""
            SELECT
                bot_name,
                time_ct,
                decision_summary,
                oracle_win_probability,
                quant_ml_win_probability,
                min_win_probability_threshold
            FROM scan_activity
            WHERE date = %s AND outcome = 'NO_TRADE'
            ORDER BY timestamp DESC
            LIMIT 20
        """, (today,))
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, time_ct, decision, oracle_wp, ml_wp, threshold = row
                oracle_wp = float(oracle_wp) if oracle_wp else 0
                ml_wp = float(ml_wp) if ml_wp else 0
                threshold = float(threshold) if threshold else 0
                print(f"  {bot:8} @ {time_ct or 'N/A':>10} | Oracle:{oracle_wp:.0%} ML:{ml_wp:.0%} Thresh:{threshold:.0%}")
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
        cursor.execute("""
            SELECT bot_name, config_key, config_value
            FROM autonomous_config
            WHERE config_key LIKE '%min_win%' OR config_key LIKE '%confidence%' OR config_key LIKE '%threshold%'
            ORDER BY bot_name, config_key
        """)
        rows = cursor.fetchall()
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
        cursor.execute("""
            SELECT bot_name,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 hour') as last_hour,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '5 minutes') as last_5min,
                   MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name
        """, (today,))
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, last_hour, last_5min, last_scan = row
                status = "ACTIVE" if last_5min > 0 else ("SLOW" if last_hour > 0 else "STALE")
                print(f"  {bot:10} | Last hour: {last_hour:3} | Last 5min: {last_5min:2} | Status: {status}")
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
        cursor.execute("""
            SELECT COUNT(*) FROM bot_heartbeats
            WHERE last_heartbeat >= NOW() - INTERVAL '10 minutes'
        """)
        if cursor.fetchone()[0] == 0:
            issues.append("No bot heartbeats in last 10 minutes - scheduler may be down")
    except:
        pass

    # Check scan activity during market hours
    if is_weekday and market_open <= now < market_close:
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM scan_activity
                WHERE date = %s
                AND outcome NOT IN ('BEFORE_WINDOW', 'AFTER_WINDOW', 'MARKET_CLOSED')
            """, (today,))
            if cursor.fetchone()[0] == 0:
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
