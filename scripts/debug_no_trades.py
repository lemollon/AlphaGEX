#!/usr/bin/env python3
"""
Debug script to find out exactly why no bots traded today.
Run this on production or locally with DATABASE_URL set.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

def main():
    from database_adapter import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
    print(f"\n{'='*80}")
    print(f"DEBUG: WHY NO BOTS TRADED ON {today}")
    print(f"{'='*80}\n")

    # 1. Bot Heartbeats - Are bots even running?
    print("1. BOT HEARTBEATS (Are bots running?)")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT bot_name, last_heartbeat, status, scan_count,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat))/60 as minutes_ago
            FROM bot_heartbeats
            ORDER BY last_heartbeat DESC NULLS LAST
        ''')
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, hb, status, scans, mins_ago = row
                mins_str = f"{mins_ago:.0f} min ago" if mins_ago else "Never"
                print(f"  {bot:12} | {status:20} | Last: {mins_str} | Scans: {scans}")
        else:
            print("  ❌ NO HEARTBEATS FOUND - Bots may not be running!")
    except Exception as e:
        print(f"  Error: {e}")

    # 2. Today's Scan Activity - What happened on each scan?
    print(f"\n2. TODAY'S SCAN ACTIVITY ({today})")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT bot_name, timestamp, outcome, decision_summary,
                   oracle_advice, oracle_win_probability, oracle_confidence
            FROM scan_activity
            WHERE date = %s
            ORDER BY timestamp DESC
            LIMIT 50
        ''', (today,))
        rows = cursor.fetchall()
        if rows:
            print(f"  Found {len(rows)} scans today:\n")
            for row in rows:
                bot, ts, outcome, summary, advice, win_prob, conf = row
                time_str = ts.strftime('%H:%M:%S') if ts else 'N/A'
                win_prob_str = f"{win_prob:.0%}" if win_prob else "N/A"
                print(f"  {time_str} | {bot:8} | {outcome:15} | Win%: {win_prob_str}")
                if summary:
                    print(f"           Reason: {summary[:70]}")
                print()
        else:
            print("  ❌ NO SCAN ACTIVITY TODAY - Scheduler may not be running!")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Summary of scan outcomes
    print(f"\n3. SCAN OUTCOME SUMMARY")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT bot_name, outcome, COUNT(*) as count
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name, outcome
            ORDER BY bot_name, count DESC
        ''', (today,))
        rows = cursor.fetchall()
        if rows:
            current_bot = None
            for bot, outcome, count in rows:
                if bot != current_bot:
                    print(f"\n  {bot}:")
                    current_bot = bot
                print(f"    {outcome:15}: {count}")
        else:
            print("  No data")
    except Exception as e:
        print(f"  Error: {e}")

    # 4. Check for open positions (blocking new entries)
    print(f"\n4. OPEN POSITIONS (May block new entries)")
    print("-" * 60)
    for table, bot in [('ares_positions', 'ARES'), ('athena_positions', 'ATHENA')]:
        try:
            cursor.execute(f'''
                SELECT position_id, status, open_time
                FROM {table}
                WHERE status = 'open'
            ''')
            rows = cursor.fetchall()
            if rows:
                print(f"  {bot}: {len(rows)} open position(s) - BLOCKING NEW ENTRIES")
                for row in rows:
                    print(f"    - {row[0]} opened at {row[2]}")
            else:
                print(f"  {bot}: No open positions")
        except Exception as e:
            print(f"  {bot}: Table not found or error: {e}")

    # 5. Circuit breaker status
    print(f"\n5. CIRCUIT BREAKER STATUS")
    print("-" * 60)
    try:
        # Check if there's a circuit breaker state in DB
        cursor.execute('''
            SELECT key, value FROM system_state
            WHERE key LIKE '%circuit%' OR key LIKE '%kill%'
        ''')
        rows = cursor.fetchall()
        if rows:
            for key, value in rows:
                print(f"  {key}: {value}")
        else:
            print("  No circuit breaker state in DB (may use file)")
    except Exception as e:
        print(f"  No system_state table: {e}")

    # 6. Recent decision logs with full context
    print(f"\n6. RECENT DECISION LOGS (Detailed)")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT bot_name, timestamp, decision_type, decision_value,
                   context, reasoning
            FROM decision_logs
            WHERE DATE(timestamp) = %s
            ORDER BY timestamp DESC
            LIMIT 20
        ''', (today,))
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, ts, dtype, dvalue, ctx, reasoning = row
                time_str = ts.strftime('%H:%M:%S') if ts else 'N/A'
                print(f"  {time_str} | {bot:8} | {dtype}: {dvalue}")
                if reasoning:
                    print(f"           Reasoning: {reasoning[:80]}")
        else:
            print("  No decision logs today")
    except Exception as e:
        print(f"  Error: {e}")

    # 7. Check scheduler state
    print(f"\n7. SCHEDULER STATE")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT is_running, last_trade_check, execution_count,
                   should_auto_restart, updated_at
            FROM scheduler_state WHERE id = 1
        ''')
        row = cursor.fetchone()
        if row:
            is_running, last_check, exec_count, auto_restart, updated = row
            print(f"  Is Running: {bool(is_running)}")
            print(f"  Last Trade Check: {last_check}")
            print(f"  Execution Count: {exec_count}")
            print(f"  Auto Restart: {bool(auto_restart)}")
            print(f"  Last Updated: {updated}")
        else:
            print("  No scheduler state found")
    except Exception as e:
        print(f"  Error: {e}")

    # 8. Oracle predictions today
    print(f"\n8. ORACLE PREDICTIONS TODAY")
    print("-" * 60)
    try:
        cursor.execute('''
            SELECT bot_name, timestamp, advice, win_probability,
                   confidence, reasoning
            FROM oracle_predictions
            WHERE DATE(timestamp) = %s
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (today,))
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                bot, ts, advice, win_prob, conf, reasoning = row
                time_str = ts.strftime('%H:%M:%S') if ts else 'N/A'
                print(f"  {time_str} | {bot:8} | {advice:12} | Win: {win_prob:.0%} | Conf: {conf:.0%}")
                if reasoning:
                    print(f"           {reasoning[:70]}")
        else:
            print("  No oracle predictions logged today")
    except Exception as e:
        print(f"  Error (table may not exist): {e}")

    conn.close()

    print(f"\n{'='*80}")
    print("END OF DEBUG REPORT")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
