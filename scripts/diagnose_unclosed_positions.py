"""
Diagnostic script: Why didn't my position close on Friday?

Run in Render shell:
  python scripts/diagnose_unclosed_positions.py

Checks ALL bots for:
  1. Positions still marked 'open' that should have been closed
  2. Partial closes that never recovered
  3. Errors/warnings in logs around Friday close time (2:50-2:55 PM CT)
  4. Whether the Friday close job actually ran
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


# All bot position/log tables
BOTS = {
    "FORTRESS": {"positions": "fortress_positions", "logs": "fortress_logs"},
    "ANCHOR": {"positions": "anchor_positions", "logs": "anchor_logs"},
    "GIDEON": {"positions": "gideon_positions", "logs": "gideon_logs"},
    "JUBILEE": {"positions": "jubilee_positions", "logs": "jubilee_logs"},
    "JUBILEE_IC": {"positions": "jubilee_ic_positions", "logs": "jubilee_logs"},
    "SAMSON": {"positions": "samson_positions", "logs": "samson_logs"},
    "SOLOMON": {"positions": "solomon_positions", "logs": "solomon_logs"},
    "VALOR": {"positions": "valor_positions", "logs": "valor_logs"},
    "AGAPE": {"positions": "agape_positions", "logs": "agape_activity_log"},
    "AGAPE_SPOT": {"positions": "agape_spot_positions", "logs": "agape_spot_activity_log"},
}


def table_exists(cur, table_name):
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
        (table_name,),
    )
    return cur.fetchone()["exists"]


def run_diagnostic():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    now_ct = datetime.now()  # Render runs in UTC, but we'll query with timezone
    print(f"=" * 80)
    print(f"  ALPHAGEX POSITION CLOSE DIAGNOSTIC")
    print(f"  Run at: {now_ct.strftime('%Y-%m-%d %H:%M:%S')} (server time)")
    print(f"=" * 80)

    # ── 1. Find ALL still-open positions across all bots ──
    print(f"\n{'─' * 80}")
    print("  1. POSITIONS STILL OPEN (should have been closed)")
    print(f"{'─' * 80}")

    found_open = False
    for bot_name, tables in BOTS.items():
        pos_table = tables["positions"]
        if not table_exists(cur, pos_table):
            continue

        # Check column names first
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
            """,
            (pos_table,),
        )
        columns = [r["column_name"] for r in cur.fetchall()]

        status_col = "status" if "status" in columns else None
        if not status_col:
            continue

        cur.execute(
            f"""
            SELECT *
            FROM {pos_table}
            WHERE status IN ('open', 'partial_close')
            ORDER BY entry_time DESC NULLS LAST
            LIMIT 20
            """
        )
        rows = cur.fetchall()
        if rows:
            found_open = True
            print(f"\n  ** {bot_name} ** — {len(rows)} open/partial position(s):")
            for r in rows:
                pid = r.get("position_id") or r.get("id")
                status = r.get("status")
                entry_time = r.get("entry_time")
                expiration = r.get("expiration")
                symbol = r.get("symbol") or r.get("underlying", "?")
                entry_price = r.get("entry_price") or r.get("entry_credit")
                close_reason = r.get("close_reason", "—")
                print(f"    ID: {pid}")
                print(f"    Status: {status} | Symbol: {symbol}")
                print(f"    Entry: {entry_time} | Expiration: {expiration}")
                print(f"    Entry Price: {entry_price} | Close Reason: {close_reason}")
                # Show all leg info if available
                for col in ["short_put", "long_put", "short_call", "long_call",
                            "short_strike", "long_strike", "put_short_strike",
                            "put_long_strike", "call_short_strike", "call_long_strike"]:
                    if col in r and r[col] is not None:
                        print(f"    {col}: {r[col]}")
                print()

    if not found_open:
        print("  No open or partial_close positions found across any bot.")

    # ── 2. Recently closed positions — verify close was clean ──
    print(f"\n{'─' * 80}")
    print("  2. RECENTLY CLOSED POSITIONS (last 3 days)")
    print(f"{'─' * 80}")

    for bot_name, tables in BOTS.items():
        pos_table = tables["positions"]
        if not table_exists(cur, pos_table):
            continue

        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            (pos_table,),
        )
        columns = [r["column_name"] for r in cur.fetchall()]
        if "close_time" not in columns:
            continue

        cur.execute(
            f"""
            SELECT *
            FROM {pos_table}
            WHERE close_time IS NOT NULL
              AND close_time >= NOW() - INTERVAL '3 days'
            ORDER BY close_time DESC
            LIMIT 10
            """
        )
        rows = cur.fetchall()
        if rows:
            print(f"\n  ** {bot_name} ** — {len(rows)} recently closed:")
            for r in rows:
                pid = r.get("position_id") or r.get("id")
                status = r.get("status")
                close_time = r.get("close_time")
                close_reason = r.get("close_reason", "—")
                realized_pnl = r.get("realized_pnl", "?")
                close_price = r.get("close_price", "?")
                print(
                    f"    {pid} | status={status} | closed={close_time} "
                    f"| reason={close_reason} | pnl={realized_pnl} | close_px={close_price}"
                )

    # ── 3. Logs around Friday close window (2:40-3:00 PM CT) ──
    print(f"\n{'─' * 80}")
    print("  3. LOGS AROUND FRIDAY CLOSE WINDOW (last Friday 2:40-3:05 PM CT)")
    print(f"{'─' * 80}")

    # Find last Friday
    today = datetime.now()
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0 and today.hour < 15:
        days_since_friday = 7  # If it's Friday morning, look at last Friday
    last_friday = today - timedelta(days=days_since_friday)
    friday_str = last_friday.strftime("%Y-%m-%d")
    print(f"  Looking at: {friday_str}")

    for bot_name, tables in BOTS.items():
        log_table = tables["logs"]
        if not table_exists(cur, log_table):
            continue

        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            (log_table,),
        )
        columns = [r["column_name"] for r in cur.fetchall()]

        time_col = "log_time" if "log_time" in columns else "timestamp" if "timestamp" in columns else None
        if not time_col:
            continue

        level_col = "level" if "level" in columns else None
        msg_col = "message" if "message" in columns else "action" if "action" in columns else None
        if not msg_col:
            continue

        # Query logs around 2:40-3:05 PM CT (19:40-20:05 UTC)
        try:
            cur.execute(
                f"""
                SELECT *
                FROM {log_table}
                WHERE {time_col} >= ('{friday_str} 19:40:00'::timestamptz)
                  AND {time_col} <= ('{friday_str} 20:05:00'::timestamptz)
                ORDER BY {time_col} ASC
                LIMIT 100
                """,
            )
        except Exception:
            # Try CT timezone approach
            conn.rollback()
            try:
                cur.execute(
                    f"""
                    SELECT *
                    FROM {log_table}
                    WHERE {time_col} >= ('{friday_str} 14:40:00 America/Chicago'::timestamptz)
                      AND {time_col} <= ('{friday_str} 15:05:00 America/Chicago'::timestamptz)
                    ORDER BY {time_col} ASC
                    LIMIT 100
                    """,
                )
            except Exception:
                conn.rollback()
                continue

        rows = cur.fetchall()
        if rows:
            print(f"\n  ** {bot_name} LOGS ** ({len(rows)} entries):")
            for r in rows:
                t = r.get(time_col, "?")
                level = r.get(level_col, "?") if level_col else "?"
                msg = r.get(msg_col, "?")
                details = r.get("details", "")
                marker = ">>>" if level in ("ERROR", "CRITICAL", "WARNING") else "   "
                print(f"    {marker} [{t}] {level}: {msg}")
                if details and level in ("ERROR", "CRITICAL", "WARNING"):
                    detail_str = str(details)[:200]
                    print(f"         Details: {detail_str}")

    # ── 4. Check for errors/warnings in last 24h ──
    print(f"\n{'─' * 80}")
    print("  4. ALL ERRORS & WARNINGS (last 24 hours)")
    print(f"{'─' * 80}")

    for bot_name, tables in BOTS.items():
        log_table = tables["logs"]
        if not table_exists(cur, log_table):
            continue

        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            (log_table,),
        )
        columns = [r["column_name"] for r in cur.fetchall()]

        time_col = "log_time" if "log_time" in columns else "timestamp" if "timestamp" in columns else None
        level_col = "level" if "level" in columns else None
        msg_col = "message" if "message" in columns else "action" if "action" in columns else None
        if not time_col or not level_col or not msg_col:
            continue

        try:
            cur.execute(
                f"""
                SELECT *
                FROM {log_table}
                WHERE {level_col} IN ('ERROR', 'CRITICAL', 'WARNING')
                  AND {time_col} >= NOW() - INTERVAL '24 hours'
                ORDER BY {time_col} DESC
                LIMIT 30
                """,
            )
        except Exception:
            conn.rollback()
            continue

        rows = cur.fetchall()
        if rows:
            print(f"\n  ** {bot_name} ** — {len(rows)} error/warning entries:")
            for r in rows:
                t = r.get(time_col, "?")
                level = r.get(level_col, "?")
                msg = r.get(msg_col, "?")
                details = r.get("details", "")
                print(f"    [{t}] {level}: {msg}")
                if details:
                    detail_str = str(details)[:300]
                    print(f"         {detail_str}")

    # ── 5. Check orphaned orders ──
    print(f"\n{'─' * 80}")
    print("  5. ORPHANED ORDERS (require manual intervention)")
    print(f"{'─' * 80}")

    if table_exists(cur, "orphaned_orders"):
        cur.execute(
            """
            SELECT * FROM orphaned_orders
            WHERE created_at >= NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"    {r}")
        else:
            print("  No orphaned orders in last 7 days.")
    else:
        print("  orphaned_orders table not found.")

    # ── 6. Check bot heartbeats ──
    print(f"\n{'─' * 80}")
    print("  6. BOT HEARTBEATS (is the bot even running?)")
    print(f"{'─' * 80}")

    if table_exists(cur, "bot_heartbeats"):
        cur.execute(
            """
            SELECT * FROM bot_heartbeats
            ORDER BY last_heartbeat DESC
            """
        )
        rows = cur.fetchall()
        if rows:
            for r in rows:
                bot = r.get("bot_name", "?")
                last_hb = r.get("last_heartbeat", "?")
                status = r.get("status", "?")
                print(f"    {bot}: last={last_hb} | status={status}")
        else:
            print("  No heartbeat data.")
    else:
        print("  bot_heartbeats table not found.")

    cur.close()
    conn.close()

    print(f"\n{'=' * 80}")
    print("  DIAGNOSTIC COMPLETE")
    print(f"{'=' * 80}")
    print("\nKey things to look for:")
    print("  - Section 1: Any position still 'open' or 'partial_close'")
    print("  - Section 3: Missing 'FRIDAY_WEEKEND_CLOSE' log entries = job didn't run")
    print("  - Section 3: 'Failed to close' or 'pricing' errors = executor failure")
    print("  - Section 5: Orphaned orders = legs that Tradier filled but DB missed")
    print("  - Section 6: Stale heartbeat = bot crashed before close window")


if __name__ == "__main__":
    run_diagnostic()
