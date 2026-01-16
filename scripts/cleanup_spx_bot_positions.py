#!/usr/bin/env python3
"""
Cleanup Script for SPX Bot Test/Demo Positions

This script removes open positions from TITAN and PEGASUS bots
without affecting closed trade history.

Use this when:
- You have test/demo positions showing incorrect Live P&L
- Orphaned positions are stuck in 'open' status
- You want to reset the bots to a clean state without losing history

Usage:
    python scripts/cleanup_spx_bot_positions.py --preview      # Preview what will be deleted
    python scripts/cleanup_spx_bot_positions.py --confirm      # Actually delete
    python scripts/cleanup_spx_bot_positions.py --bot pegasus  # Only clean PEGASUS
    python scripts/cleanup_spx_bot_positions.py --bot titan    # Only clean TITAN
"""

import os
import sys
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection as db_get_connection
        return db_get_connection()
    except ImportError:
        import psycopg2
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("ERROR: DATABASE_URL environment variable not set")
            sys.exit(1)
        return psycopg2.connect(database_url)


def preview_pegasus_positions():
    """Preview PEGASUS open positions"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT position_id, expiration, total_credit, contracts,
               put_short_strike, put_long_strike, call_short_strike, call_long_strike,
               open_time, status
        FROM pegasus_positions
        WHERE status = 'open'
        ORDER BY open_time DESC
    """)
    positions = cursor.fetchall()
    conn.close()

    return positions


def preview_titan_positions():
    """Preview TITAN open positions"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT position_id, expiration, total_credit, contracts,
               put_short_strike, put_long_strike, call_short_strike, call_long_strike,
               open_time, status
        FROM titan_positions
        WHERE status = 'open'
        ORDER BY open_time DESC
    """)
    positions = cursor.fetchall()
    conn.close()

    return positions


def cleanup_pegasus_positions(confirm: bool = False):
    """Clean up PEGASUS open positions"""
    conn = get_connection()
    cursor = conn.cursor()

    if not confirm:
        cursor.execute("SELECT COUNT(*) FROM pegasus_positions WHERE status = 'open'")
        count = cursor.fetchone()[0]
        conn.close()
        return {"preview": True, "count": count}

    # Delete open positions
    cursor.execute("DELETE FROM pegasus_positions WHERE status = 'open'")
    deleted_positions = cursor.rowcount

    # Clear today's snapshots
    cursor.execute("""
        DELETE FROM pegasus_equity_snapshots
        WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = CURRENT_DATE
    """)
    deleted_snapshots = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "deleted_positions": deleted_positions,
        "deleted_snapshots": deleted_snapshots
    }


def cleanup_titan_positions(confirm: bool = False):
    """Clean up TITAN open positions"""
    conn = get_connection()
    cursor = conn.cursor()

    if not confirm:
        cursor.execute("SELECT COUNT(*) FROM titan_positions WHERE status = 'open'")
        count = cursor.fetchone()[0]
        conn.close()
        return {"preview": True, "count": count}

    # Delete open positions
    cursor.execute("DELETE FROM titan_positions WHERE status = 'open'")
    deleted_positions = cursor.rowcount

    # Clear today's snapshots
    cursor.execute("""
        DELETE FROM titan_equity_snapshots
        WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = CURRENT_DATE
    """)
    deleted_snapshots = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "deleted_positions": deleted_positions,
        "deleted_snapshots": deleted_snapshots
    }


def print_positions(positions, bot_name):
    """Print positions in a table format"""
    if not positions:
        print(f"  No open positions found for {bot_name}")
        return

    print(f"\n  {bot_name} Open Positions ({len(positions)}):")
    print("  " + "-" * 80)
    print(f"  {'ID':<20} {'Expiration':<12} {'Put':<15} {'Call':<15} {'Contracts':<10}")
    print("  " + "-" * 80)

    for pos in positions:
        pos_id = str(pos[0])[:18]
        exp = str(pos[1])[:10] if pos[1] else "N/A"
        put_spread = f"{pos[5]}/{pos[4]}" if pos[5] and pos[4] else "N/A"
        call_spread = f"{pos[6]}/{pos[7]}" if pos[6] and pos[7] else "N/A"
        contracts = pos[3] or 0

        print(f"  {pos_id:<20} {exp:<12} {put_spread:<15} {call_spread:<15} {contracts:<10}")

    print("  " + "-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Clean up SPX bot test/demo positions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cleanup_spx_bot_positions.py --preview
  python scripts/cleanup_spx_bot_positions.py --confirm
  python scripts/cleanup_spx_bot_positions.py --bot pegasus --confirm
        """
    )
    parser.add_argument('--preview', action='store_true', help='Preview positions to be deleted')
    parser.add_argument('--confirm', action='store_true', help='Actually delete positions')
    parser.add_argument('--bot', choices=['pegasus', 'titan', 'all'], default='all',
                       help='Which bot to clean up (default: all)')

    args = parser.parse_args()

    if not args.preview and not args.confirm:
        args.preview = True  # Default to preview mode

    print("\n" + "=" * 60)
    print("SPX BOT POSITION CLEANUP")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'PREVIEW' if args.preview else 'DELETE'}")
    print(f"Bots: {args.bot.upper()}")

    if args.preview:
        print("\n" + "=" * 60)
        print("PREVIEW MODE - No changes will be made")
        print("=" * 60)

        if args.bot in ['pegasus', 'all']:
            positions = preview_pegasus_positions()
            print_positions(positions, "PEGASUS")

        if args.bot in ['titan', 'all']:
            positions = preview_titan_positions()
            print_positions(positions, "TITAN")

        print("\n  To delete these positions, run with --confirm")

    else:
        print("\n" + "=" * 60)
        print("DELETE MODE - Positions will be removed")
        print("=" * 60)

        if args.bot in ['pegasus', 'all']:
            print("\n  Cleaning up PEGASUS...")
            result = cleanup_pegasus_positions(confirm=True)
            print(f"  ✓ Deleted {result['deleted_positions']} positions")
            print(f"  ✓ Deleted {result['deleted_snapshots']} today's snapshots")

        if args.bot in ['titan', 'all']:
            print("\n  Cleaning up TITAN...")
            result = cleanup_titan_positions(confirm=True)
            print(f"  ✓ Deleted {result['deleted_positions']} positions")
            print(f"  ✓ Deleted {result['deleted_snapshots']} today's snapshots")

        print("\n  ✓ Cleanup complete! Closed trade history preserved.")

    print("\n" + "=" * 60 + "\n")


if __name__ == '__main__':
    main()
