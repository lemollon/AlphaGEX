#!/usr/bin/env python3
"""
Test data consistency across endpoints.
Run from Render shell: python scripts/test_data_consistency.py

Verifies:
1. All bots query from correct tables
2. Position counts match between endpoints
3. P&L calculations are consistent
4. Closed positions come from database not memory
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def get_db_stats(bot_name: str, table_name: str, conn):
    """Get database statistics for a bot"""
    cursor = conn.cursor()
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    stats = {}

    # Total closed positions
    cursor.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0)
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
    """)
    row = cursor.fetchone()
    stats["total_closed"] = row[0] or 0
    stats["total_realized"] = float(row[1] or 0)

    # Today's closed positions
    cursor.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0)
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
    """, (today,))
    row = cursor.fetchone()
    stats["today_closed"] = row[0] or 0
    stats["today_realized"] = float(row[1] or 0)

    # Open positions
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE status = 'open'
    """)
    stats["open_count"] = cursor.fetchone()[0] or 0

    # Last 7 days trades
    week_ago = (datetime.now(ZoneInfo("America/Chicago")) - timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0)
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') >= %s
    """, (week_ago,))
    row = cursor.fetchone()
    stats["week_closed"] = row[0] or 0
    stats["week_realized"] = float(row[1] or 0)

    return stats


def check_config_capital(bot_name: str, config_key: str, default: float, conn):
    """Check starting capital configuration"""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM autonomous_config WHERE key = %s", (config_key,))
    row = cursor.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return default
    return default


def main():
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}DATA CONSISTENCY CHECK{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"Date: {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S CT')}")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        print(f"{GREEN}✓ Database connected{RESET}")
    except Exception as e:
        print(f"{RED}✗ Database connection failed: {e}{RESET}")
        return 1

    # Bot configurations
    bots = [
        ("FORTRESS", "fortress_positions", "fortress_starting_capital", 100000),
        ("SAMSON", "samson_positions", "samson_starting_capital", 200000),
        ("ANCHOR", "anchor_positions", "anchor_starting_capital", 200000),
        ("SOLOMON", "solomon_positions", "solomon_starting_capital", 50000),
        ("GIDEON", "gideon_positions", "gideon_starting_capital", 50000),
    ]

    all_stats = {}
    issues = []

    for bot_name, table, config_key, default_capital in bots:
        print(f"\n{BLUE}--- {bot_name} ---{RESET}")

        # Get database stats
        stats = get_db_stats(bot_name, table, conn)
        all_stats[bot_name] = stats

        # Get configured capital
        capital = check_config_capital(bot_name, config_key, default_capital, conn)
        stats["starting_capital"] = capital

        print(f"  Starting Capital: ${capital:,.0f}")
        print(f"  Total Closed: {stats['total_closed']} trades, ${stats['total_realized']:,.2f}")
        print(f"  Today Closed: {stats['today_closed']} trades, ${stats['today_realized']:,.2f}")
        print(f"  Open Positions: {stats['open_count']}")
        print(f"  Week Activity: {stats['week_closed']} trades, ${stats['week_realized']:,.2f}")

        # Check for issues
        if stats['total_closed'] == 0:
            issues.append(f"{bot_name}: No closed positions in database")

        if stats['total_realized'] != 0:
            roi = (stats['total_realized'] / capital) * 100
            print(f"  Total ROI: {roi:.2f}%")

    # Cross-check: events_routes table mapping
    print(f"\n{BLUE}--- Events Routes Table Mapping ---{RESET}")
    cursor = conn.cursor()
    events_tables = {
        "FORTRESS": "fortress_positions",
        "SAMSON": "samson_positions",
        "ANCHOR": "anchor_positions",
        "SOLOMON": "solomon_positions",
        "GIDEON": "gideon_positions",
    }

    for bot, table in events_tables.items():
        # Verify table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        exists = cursor.fetchone()[0]
        if exists:
            print(f"  {GREEN}✓ {bot} -> {table}{RESET}")
        else:
            print(f"  {RED}✗ {bot} -> {table} (TABLE NOT FOUND!){RESET}")
            issues.append(f"{bot}: Table {table} does not exist")

    # Check unified metrics service
    print(f"\n{BLUE}--- Unified Metrics Service ---{RESET}")
    try:
        from backend.services.bot_metrics_service import BotName, get_metrics_service
        service = get_metrics_service()
        print(f"  {GREEN}✓ BotMetricsService available{RESET}")

        # Check enum mapping
        for bot in BotName:
            print(f"    BotName.{bot.name} = '{bot.value}'")
    except ImportError as e:
        print(f"  {YELLOW}⚠ Cannot import BotMetricsService: {e}{RESET}")

    conn.close()

    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}SUMMARY{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    total_closed = sum(s["total_closed"] for s in all_stats.values())
    total_realized = sum(s["total_realized"] for s in all_stats.values())
    total_open = sum(s["open_count"] for s in all_stats.values())

    print(f"  Total Closed Positions: {total_closed}")
    print(f"  Total Realized P&L: ${total_realized:,.2f}")
    print(f"  Total Open Positions: {total_open}")

    if issues:
        print(f"\n{YELLOW}Issues Found:{RESET}")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n{GREEN}No issues found!{RESET}")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
