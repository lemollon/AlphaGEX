#!/usr/bin/env python3
"""
Migrate existing decision data to the new bot_decision_logs table.

This script consolidates data from:
- trading_decisions table
- autonomous_trader_logs table
- autonomous_trade_log table

Into the comprehensive bot_decision_logs table.

Run with: python scripts/migrate_to_bot_decision_logs.py
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


def migrate_trading_decisions():
    """Migrate data from trading_decisions table."""
    print("\n--- Migrating trading_decisions ---")

    conn = get_connection()
    c = conn.cursor()

    # Check if source table exists
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'trading_decisions'
        )
    """)
    if not c.fetchone()[0]:
        print("  trading_decisions table does not exist, skipping")
        conn.close()
        return 0

    # Get existing records
    c.execute("""
        SELECT id, timestamp, bot_name, decision_type, action, symbol, strategy,
               strike, expiration, option_type, contracts,
               spot_price, vix, reason, confidence
        FROM trading_decisions
        ORDER BY timestamp
    """)
    rows = c.fetchall()

    migrated = 0
    for row in rows:
        try:
            decision_id = f"MIGRATED-{row[0]}"

            # Check if already migrated
            c.execute("SELECT 1 FROM bot_decision_logs WHERE decision_id = %s", (decision_id,))
            if c.fetchone():
                continue

            # Map decision type
            dt = row[3] or "SKIP"
            if "ENTRY" in dt.upper():
                dt = "ENTRY"
            elif "EXIT" in dt.upper():
                dt = "EXIT"
            elif "NO_ACTION" in dt.upper() or "SKIP" in dt.upper():
                dt = "SKIP"

            # Map bot name
            bn = row[2] or "UNKNOWN"

            # Session ID from timestamp
            ts = row[1]
            if ts:
                session_id = f"{ts.strftime('%Y-%m-%d')}-{'AM' if ts.hour < 12 else 'PM'}"
            else:
                session_id = "UNKNOWN"

            c.execute("""
                INSERT INTO bot_decision_logs (
                    decision_id, bot_name, session_id, decision_type, action,
                    symbol, strategy, strike, expiration, option_type, contracts,
                    spot_price, vix, entry_reasoning, ai_confidence, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (decision_id) DO NOTHING
            """, (
                decision_id, bn, session_id, dt, row[4] or "",
                row[5] or "SPY", row[6] or "", row[7] or 0, row[8], row[9] or "",
                row[10] or 0, row[11] or 0, row[12] or 0, row[13] or "", row[14] or "",
                ts or datetime.now()
            ))
            migrated += 1

        except Exception as e:
            print(f"  Error migrating row {row[0]}: {e}")

    conn.commit()
    conn.close()

    print(f"  Migrated {migrated} records from trading_decisions")
    return migrated


def migrate_autonomous_trader_logs():
    """Migrate data from autonomous_trader_logs table."""
    print("\n--- Migrating autonomous_trader_logs ---")

    conn = get_connection()
    c = conn.cursor()

    # Check if source table exists
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'autonomous_trader_logs'
        )
    """)
    if not c.fetchone()[0]:
        print("  autonomous_trader_logs table does not exist, skipping")
        conn.close()
        return 0

    # Get existing records
    c.execute("""
        SELECT id, timestamp, cycle_number, action_taken, position_status,
               current_price, vix_level, gex_level, psychology_state,
               reasoning, confidence, ai_response
        FROM autonomous_trader_logs
        ORDER BY timestamp
    """)
    rows = c.fetchall()

    migrated = 0
    for row in rows:
        try:
            decision_id = f"AUTO-{row[0]}"

            # Check if already migrated
            c.execute("SELECT 1 FROM bot_decision_logs WHERE decision_id = %s", (decision_id,))
            if c.fetchone():
                continue

            # Map action to decision type
            action = row[3] or ""
            if "ENTRY" in action.upper() or "BUY" in action.upper() or "SELL" in action.upper():
                dt = "ENTRY"
            elif "EXIT" in action.upper() or "CLOSE" in action.upper():
                dt = "EXIT"
            else:
                dt = "SKIP"

            # Session ID from timestamp
            ts = row[1]
            if ts:
                session_id = f"{ts.strftime('%Y-%m-%d')}-{'AM' if ts.hour < 12 else 'PM'}"
            else:
                session_id = "UNKNOWN"

            c.execute("""
                INSERT INTO bot_decision_logs (
                    decision_id, bot_name, session_id, scan_cycle, decision_type,
                    action, symbol, spot_price, vix, psychology_pattern,
                    entry_reasoning, ai_confidence, claude_response, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (decision_id) DO NOTHING
            """, (
                decision_id, "AUTONOMOUS", session_id, row[2] or 0, dt,
                action, "SPY", row[5] or 0, row[6] or 0, row[8] or "",
                row[9] or "", str(row[10] or ""), row[11] or "", ts or datetime.now()
            ))
            migrated += 1

        except Exception as e:
            print(f"  Error migrating row {row[0]}: {e}")

    conn.commit()
    conn.close()

    print(f"  Migrated {migrated} records from autonomous_trader_logs")
    return migrated


def migrate_autonomous_trade_log():
    """Migrate data from autonomous_trade_log table."""
    print("\n--- Migrating autonomous_trade_log ---")

    conn = get_connection()
    c = conn.cursor()

    # Check if source table exists
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'autonomous_trade_log'
        )
    """)
    if not c.fetchone()[0]:
        print("  autonomous_trade_log table does not exist, skipping")
        conn.close()
        return 0

    # Get existing records
    c.execute("""
        SELECT id, date, time, action, details, position_id, success
        FROM autonomous_trade_log
        ORDER BY date, time
    """)
    rows = c.fetchall()

    migrated = 0
    for row in rows:
        try:
            decision_id = f"TRADE-{row[0]}"

            # Check if already migrated
            c.execute("SELECT 1 FROM bot_decision_logs WHERE decision_id = %s", (decision_id,))
            if c.fetchone():
                continue

            # Map action to decision type
            action = row[3] or ""
            if "OPEN" in action.upper() or "ENTRY" in action.upper():
                dt = "ENTRY"
            elif "CLOSE" in action.upper() or "EXIT" in action.upper():
                dt = "EXIT"
            else:
                dt = "SKIP"

            # Combine date and time
            trade_date = row[1]
            trade_time = row[2]
            if trade_date:
                session_id = f"{trade_date}-{'AM' if (trade_time and trade_time.hour < 12) else 'PM'}"
                if trade_time:
                    ts = datetime.combine(trade_date, trade_time)
                else:
                    ts = datetime.combine(trade_date, datetime.min.time())
            else:
                session_id = "UNKNOWN"
                ts = datetime.now()

            c.execute("""
                INSERT INTO bot_decision_logs (
                    decision_id, bot_name, session_id, decision_type, action,
                    symbol, entry_reasoning, passed_all_checks, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (decision_id) DO NOTHING
            """, (
                decision_id, "AUTONOMOUS", session_id, dt, action,
                "SPY", row[4] or "", row[6] if row[6] is not None else True, ts
            ))
            migrated += 1

        except Exception as e:
            print(f"  Error migrating row {row[0]}: {e}")

    conn.commit()
    conn.close()

    print(f"  Migrated {migrated} records from autonomous_trade_log")
    return migrated


def verify_migration():
    """Verify the migration was successful."""
    print("\n--- Verifying Migration ---")

    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM bot_decision_logs")
    total = c.fetchone()[0]

    c.execute("SELECT bot_name, COUNT(*) FROM bot_decision_logs GROUP BY bot_name ORDER BY COUNT(*) DESC")
    by_bot = c.fetchall()

    c.execute("SELECT decision_type, COUNT(*) FROM bot_decision_logs GROUP BY decision_type ORDER BY COUNT(*) DESC")
    by_type = c.fetchall()

    conn.close()

    print(f"\n  Total records in bot_decision_logs: {total}")
    print("\n  By Bot:")
    for bot, count in by_bot:
        print(f"    {bot}: {count}")
    print("\n  By Decision Type:")
    for dt, count in by_type:
        print(f"    {dt}: {count}")

    return total


def main():
    """Run the migration."""
    print("=" * 60)
    print("Bot Decision Logs Migration")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # First ensure the table exists
    print("\n--- Ensuring bot_decision_logs table exists ---")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'bot_decision_logs'
        )
    """)
    if not c.fetchone()[0]:
        print("  ERROR: bot_decision_logs table does not exist!")
        print("  Run: python db/config_and_database.py to create tables first")
        conn.close()
        return 1
    print("  Table exists, proceeding with migration")
    conn.close()

    # Run migrations
    total = 0
    total += migrate_trading_decisions()
    total += migrate_autonomous_trader_logs()
    total += migrate_autonomous_trade_log()

    # Verify
    final_count = verify_migration()

    print("\n" + "=" * 60)
    print(f"Migration Complete!")
    print(f"  Records migrated this run: {total}")
    print(f"  Total records in table: {final_count}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
