#!/usr/bin/env python3
"""
SPX Bot Maintenance Script

Combined utility for SPX-trading bots (TITAN, PEGASUS):
1. Verify SPX quotes work with Tradier production API
2. Clean up test/demo/orphaned positions

Usage:
    python scripts/spx_bot_maintenance.py --verify          # Test SPX quotes
    python scripts/spx_bot_maintenance.py --cleanup         # Preview cleanup
    python scripts/spx_bot_maintenance.py --cleanup --confirm  # Actually cleanup
    python scripts/spx_bot_maintenance.py --all             # Verify + preview cleanup
    python scripts/spx_bot_maintenance.py --all --confirm   # Verify + cleanup
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_db_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection
        return get_connection()
    except ImportError:
        import psycopg2
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("  ✗ DATABASE_URL not set")
            return None
        return psycopg2.connect(database_url)


# =============================================================================
# SPX QUOTE VERIFICATION
# =============================================================================

def verify_env_vars():
    """Check required environment variables"""
    print("\n  Checking environment variables...")

    prod_key = os.environ.get('TRADIER_API_KEY')
    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY')

    print(f"    TRADIER_API_KEY (production): {'✓ SET' if prod_key else '✗ NOT SET'}")
    print(f"    TRADIER_SANDBOX_API_KEY:      {'✓ SET' if sandbox_key else '✗ NOT SET'}")

    if not prod_key:
        print("\n  ⚠️  WARNING: Production key not set - SPX quotes will fail!")
        return False
    return True


def verify_spx_quote():
    """Test fetching SPX quote with production API"""
    print("\n  Testing SPX quote (production API)...")

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            print("    ✗ No production key")
            return False

        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)
        quote = tradier.get_quote('SPX')

        if quote and quote.get('last'):
            price = float(quote['last'])
            print(f"    ✓ SPX: ${price:,.2f}")
            return True
        else:
            print(f"    ✗ No SPX quote returned")
            return False

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def verify_spy_comparison():
    """Compare SPX vs SPY*10"""
    print("\n  Comparing SPX vs SPY×10...")

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            return False

        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)
        spx = tradier.get_quote('SPX')
        spy = tradier.get_quote('SPY')

        if spx and spy and spx.get('last') and spy.get('last'):
            spx_price = float(spx['last'])
            spy_price = float(spy['last']) * 10
            diff_pct = abs(spx_price - spy_price) / spx_price * 100

            print(f"    SPX actual: ${spx_price:,.2f}")
            print(f"    SPY × 10:   ${spy_price:,.2f}")
            print(f"    Difference: {diff_pct:.3f}%")
            return True
        return False

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def verify_mtm():
    """Test Mark-to-Market for SPX"""
    print("\n  Testing Mark-to-Market utility...")

    try:
        from trading.mark_to_market import _get_tradier_client

        client = _get_tradier_client(underlying='SPXW')
        if client:
            mode = 'SANDBOX' if client.sandbox else 'PRODUCTION'
            print(f"    MTM client mode: {mode}")
            if not client.sandbox:
                print(f"    ✓ Correctly using PRODUCTION for SPXW")
                return True
            else:
                print(f"    ✗ Should use PRODUCTION for SPXW!")
                return False
        else:
            print(f"    ✗ Failed to create MTM client")
            return False

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def run_verification():
    """Run all SPX verification tests"""
    print("\n" + "=" * 60)
    print("SPX QUOTE VERIFICATION")
    print("=" * 60)

    results = {
        'env': verify_env_vars(),
        'spx': verify_spx_quote(),
        'comparison': verify_spy_comparison(),
        'mtm': verify_mtm()
    }

    print("\n  Results:")
    all_pass = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        if not passed:
            all_pass = False
        print(f"    {name}: {status}")

    return all_pass


# =============================================================================
# POSITION CLEANUP
# =============================================================================

def get_open_positions(bot: str):
    """Get open positions for a bot"""
    conn = get_db_connection()
    if not conn:
        return []

    table = f"{bot}_positions"
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            SELECT position_id, expiration, total_credit, contracts,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   open_time
            FROM {table}
            WHERE status = 'open'
            ORDER BY open_time DESC
        """)
        positions = cursor.fetchall()
    except Exception as e:
        print(f"    Error reading {bot} positions: {e}")
        positions = []

    conn.close()
    return positions


def print_positions(positions, bot_name):
    """Print positions in a table format"""
    if not positions:
        print(f"    No open positions for {bot_name}")
        return

    print(f"\n    {bot_name} Open Positions ({len(positions)}):")
    print("    " + "-" * 70)
    print(f"    {'Expiration':<12} {'Put Spread':<15} {'Call Spread':<15} {'Contracts':<10}")
    print("    " + "-" * 70)

    for pos in positions:
        exp = str(pos[1])[:10] if pos[1] else "N/A"
        put_spread = f"{pos[5]}/{pos[4]}" if pos[5] and pos[4] else "N/A"
        call_spread = f"{pos[6]}/{pos[7]}" if pos[6] and pos[7] else "N/A"
        contracts = pos[3] or 0
        print(f"    {exp:<12} {put_spread:<15} {call_spread:<15} {contracts:<10}")

    print("    " + "-" * 70)


def cleanup_positions(bot: str, confirm: bool = False):
    """Clean up open positions for a bot"""
    conn = get_db_connection()
    if not conn:
        return {"error": "No database connection"}

    table = f"{bot}_positions"
    snapshot_table = f"{bot}_equity_snapshots"
    cursor = conn.cursor()

    if not confirm:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE status = 'open'")
        count = cursor.fetchone()[0]
        conn.close()
        return {"preview": True, "count": count}

    # Delete open positions
    cursor.execute(f"DELETE FROM {table} WHERE status = 'open'")
    deleted_positions = cursor.rowcount

    # Clear today's snapshots
    deleted_snapshots = 0
    try:
        cursor.execute(f"""
            DELETE FROM {snapshot_table}
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = CURRENT_DATE
        """)
        deleted_snapshots = cursor.rowcount
    except Exception:
        pass

    conn.commit()
    conn.close()

    return {
        "deleted_positions": deleted_positions,
        "deleted_snapshots": deleted_snapshots
    }


def run_cleanup(confirm: bool = False):
    """Run cleanup for all SPX bots"""
    print("\n" + "=" * 60)
    print(f"POSITION CLEANUP {'(PREVIEW)' if not confirm else '(DELETING)'}")
    print("=" * 60)

    for bot in ['pegasus', 'titan']:
        print(f"\n  {bot.upper()}:")

        if not confirm:
            positions = get_open_positions(bot)
            print_positions(positions, bot.upper())
        else:
            result = cleanup_positions(bot, confirm=True)
            if 'error' in result:
                print(f"    ✗ {result['error']}")
            else:
                print(f"    ✓ Deleted {result['deleted_positions']} positions")
                print(f"    ✓ Deleted {result['deleted_snapshots']} today's snapshots")

    if not confirm:
        print("\n  To delete, run with --confirm")
    else:
        print("\n  ✓ Cleanup complete! Closed trade history preserved.")

    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='SPX Bot Maintenance - Verify quotes and cleanup positions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/spx_bot_maintenance.py --verify              # Test SPX quotes
  python scripts/spx_bot_maintenance.py --cleanup             # Preview cleanup
  python scripts/spx_bot_maintenance.py --cleanup --confirm   # Delete positions
  python scripts/spx_bot_maintenance.py --all --confirm       # Full maintenance
        """
    )
    parser.add_argument('--verify', action='store_true', help='Verify SPX quotes work')
    parser.add_argument('--cleanup', action='store_true', help='Cleanup open positions')
    parser.add_argument('--all', action='store_true', help='Run both verify and cleanup')
    parser.add_argument('--confirm', action='store_true', help='Actually delete (for cleanup)')

    args = parser.parse_args()

    # Default to --all if nothing specified
    if not args.verify and not args.cleanup and not args.all:
        args.all = True

    print("\n" + "=" * 60)
    print("SPX BOT MAINTENANCE")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    success = True

    if args.verify or args.all:
        if not run_verification():
            success = False

    if args.cleanup or args.all:
        run_cleanup(confirm=args.confirm)

    print("\n" + "=" * 60)
    if success:
        print("✓ MAINTENANCE COMPLETE")
    else:
        print("⚠️ SOME CHECKS FAILED - Review output above")
    print("=" * 60 + "\n")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
