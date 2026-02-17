#!/usr/bin/env python3
"""
RESET ALL PERPETUAL BOT TRADING DATA

This script performs a complete data reset for all 5 perpetual trading bots:
  - AGAPE-BTC-PERP
  - AGAPE-ETH-PERP
  - AGAPE-XRP-PERP
  - AGAPE-DOGE-PERP
  - AGAPE-SHIB-PERP

It does NOT touch: AGAPE_SPOT, AGAPE_BTC (CME), AGAPE_XRP (CME), VALOR,
PHOENIX, HERMES, or any options bots.

Usage:
    # Step 1: Diagnose (show current state, NO changes)
    python scripts/reset_perpetual_bots.py --diagnose

    # Step 2: Backup all data to CSV files
    python scripts/reset_perpetual_bots.py --backup

    # Step 3: Show open positions (check for real exchange positions)
    python scripts/reset_perpetual_bots.py --check-open

    # Step 4: Reset all data (requires --confirm flag)
    python scripts/reset_perpetual_bots.py --reset --confirm

    # Step 5: Verify clean state
    python scripts/reset_perpetual_bots.py --verify
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# All 5 perpetual bots and their table names
PERP_BOTS = {
    "BTC-PERP": {
        "prefix": "agape_btc_perp",
        "starting_capital": 25000.0,
        "config_key": "agape_btc_perp_starting_capital",
        "tables": [
            "agape_btc_perp_positions",
            "agape_btc_perp_equity_snapshots",
            "agape_btc_perp_scan_activity",
            "agape_btc_perp_activity_log",
        ],
    },
    "ETH-PERP": {
        "prefix": "agape_eth_perp",
        "starting_capital": 12500.0,
        "config_key": "agape_eth_perp_starting_capital",
        "tables": [
            "agape_eth_perp_positions",
            "agape_eth_perp_equity_snapshots",
            "agape_eth_perp_scan_activity",
            "agape_eth_perp_activity_log",
        ],
    },
    "XRP-PERP": {
        "prefix": "agape_xrp_perp",
        "starting_capital": 9000.0,
        "config_key": "agape_xrp_perp_starting_capital",
        "tables": [
            "agape_xrp_perp_positions",
            "agape_xrp_perp_equity_snapshots",
            "agape_xrp_perp_scan_activity",
            "agape_xrp_perp_activity_log",
        ],
    },
    "DOGE-PERP": {
        "prefix": "agape_doge_perp",
        "starting_capital": 2500.0,
        "config_key": "agape_doge_perp_starting_capital",
        "tables": [
            "agape_doge_perp_positions",
            "agape_doge_perp_equity_snapshots",
            "agape_doge_perp_scan_activity",
            "agape_doge_perp_activity_log",
        ],
    },
    "SHIB-PERP": {
        "prefix": "agape_shib_perp",
        "starting_capital": 1000.0,
        "config_key": "agape_shib_perp_starting_capital",
        "tables": [
            "agape_shib_perp_positions",
            "agape_shib_perp_equity_snapshots",
            "agape_shib_perp_scan_activity",
            "agape_shib_perp_activity_log",
        ],
    },
}


def get_connection():
    """Get database connection."""
    try:
        from database_adapter import get_connection as _get_conn
        return _get_conn()
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)


def get_table_count(cursor, table_name):
    """Get row count for a table."""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except Exception:
        return -1  # Table doesn't exist


def diagnose(args):
    """Phase 1: Diagnose the -105% bug and show current state of all perp bots."""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("PERPETUAL BOT DIAGNOSIS")
    print(f"Timestamp: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    for ticker, bot in PERP_BOTS.items():
        prefix = bot["prefix"]
        positions_table = f"{prefix}_positions"
        default_capital = bot["starting_capital"]

        print(f"\n{'─' * 60}")
        print(f"  {ticker}")
        print(f"{'─' * 60}")

        # 1. Table row counts
        print(f"\n  Table Row Counts:")
        for table in bot["tables"]:
            count = get_table_count(cursor, table)
            print(f"    {table}: {count} rows")

        # 2. Starting capital from config
        starting_capital = default_capital
        try:
            cursor.execute(
                "SELECT value FROM autonomous_config WHERE key = %s",
                (bot["config_key"],)
            )
            row = cursor.fetchone()
            if row and row[0]:
                starting_capital = float(row[0])
                print(f"\n  Starting Capital: ${starting_capital:,.2f} (from autonomous_config)")
            else:
                print(f"\n  Starting Capital: ${starting_capital:,.2f} (DEFAULT - not in autonomous_config)")
        except Exception:
            print(f"\n  Starting Capital: ${starting_capital:,.2f} (DEFAULT - config query failed)")

        # 3. Total realized PnL
        try:
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_trades,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl,
                    COALESCE(AVG(realized_pnl), 0) as avg_pnl,
                    COALESCE(MIN(realized_pnl), 0) as worst_trade,
                    COALESCE(MAX(realized_pnl), 0) as best_trade
                FROM {positions_table}
                WHERE status IN ('closed', 'expired', 'stopped')
            """)
            row = cursor.fetchone()
            if row:
                total_trades, total_pnl, avg_pnl, worst, best = row
                return_pct = (float(total_pnl) / starting_capital * 100) if starting_capital else 0
                print(f"\n  Realized P&L Summary:")
                print(f"    Total Closed Trades: {total_trades}")
                print(f"    Total Realized P&L:  ${float(total_pnl):+,.2f}")
                print(f"    Average P&L/Trade:   ${float(avg_pnl):+,.2f}")
                print(f"    Worst Trade:         ${float(worst):+,.2f}")
                print(f"    Best Trade:          ${float(best):+,.2f}")
                print(f"    Raw Return %:        {return_pct:+.2f}%")
                if return_pct < -100:
                    print(f"    *** BUG: Return is {return_pct:.2f}% (below -100%!) ***")
                    print(f"    *** Dollar loss (${abs(float(total_pnl)):,.2f}) exceeds starting capital (${starting_capital:,.2f}) ***")
        except Exception as e:
            print(f"\n  Realized P&L: ERROR - {e}")

        # 4. Open positions
        try:
            cursor.execute(f"""
                SELECT COUNT(*) FROM {positions_table} WHERE status = 'open'
            """)
            open_count = cursor.fetchone()[0]
            print(f"\n  Open Positions: {open_count}")
        except Exception:
            print(f"\n  Open Positions: ERROR")

        # 5. Check for absurd P&L values
        try:
            cursor.execute(f"""
                SELECT position_id, side, quantity, entry_price, close_price,
                       realized_pnl, close_reason, open_time, close_time
                FROM {positions_table}
                WHERE (ABS(realized_pnl) > 1000
                   OR realized_pnl IS NULL
                   OR entry_price IS NULL
                   OR entry_price = 0
                   OR quantity = 0)
                  AND status IN ('closed', 'expired', 'stopped')
                ORDER BY ABS(COALESCE(realized_pnl, 0)) DESC
                LIMIT 10
            """)
            suspicious = cursor.fetchall()
            if suspicious:
                print(f"\n  Suspicious Positions ({len(suspicious)}):")
                for s in suspicious:
                    pid, side, qty, entry, close, pnl, reason, ot, ct = s
                    print(f"    {pid}: {side} {qty} @ ${entry} -> ${close} P&L=${pnl} ({reason})")
        except Exception as e:
            print(f"\n  Suspicious Check: ERROR - {e}")

        # 6. Equity snapshots
        try:
            cursor.execute(f"""
                SELECT timestamp, equity, unrealized_pnl, realized_pnl_cumulative
                FROM {prefix}_equity_snapshots
                ORDER BY timestamp DESC LIMIT 5
            """)
            snaps = cursor.fetchall()
            if snaps:
                print(f"\n  Latest Equity Snapshots:")
                for snap in snaps:
                    ts, eq, unr, real = snap
                    ts_str = ts.astimezone(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M") if ts else "?"
                    print(f"    {ts_str}: equity=${float(eq or 0):,.2f} unreal=${float(unr or 0):+,.2f} real_cum=${float(real or 0):+,.2f}")
        except Exception as e:
            print(f"\n  Equity Snapshots: ERROR - {e}")

    cursor.close()
    conn.close()
    print(f"\n{'=' * 80}")
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)


def backup(args):
    """Phase 3 Step 0: Backup all perp bot data to CSV files."""
    conn = get_connection()
    cursor = conn.cursor()
    timestamp = datetime.now(CENTRAL_TZ).strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups", f"perp_reset_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)

    print(f"Backup directory: {backup_dir}")
    print()

    for ticker, bot in PERP_BOTS.items():
        print(f"Backing up {ticker}...")
        for table in bot["tables"]:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]
                filepath = os.path.join(backup_dir, f"{table}.csv")
                with open(filepath, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(col_names)
                    writer.writerows(rows)
                print(f"  {table}: {len(rows)} rows -> {filepath}")
            except Exception as e:
                print(f"  {table}: ERROR - {e}")

    cursor.close()
    conn.close()
    print(f"\nBackup complete: {backup_dir}")
    return backup_dir


def check_open(args):
    """Phase 3 Step 2: Check for open positions on all perp bots."""
    conn = get_connection()
    cursor = conn.cursor()

    print("CHECKING OPEN POSITIONS (All Perpetual Bots)")
    print("=" * 60)

    has_open = False
    for ticker, bot in PERP_BOTS.items():
        positions_table = f"{bot['prefix']}_positions"
        try:
            cursor.execute(f"""
                SELECT position_id, side, quantity, entry_price, open_time, status
                FROM {positions_table}
                WHERE status = 'open'
                ORDER BY open_time ASC
            """)
            open_pos = cursor.fetchall()
            if open_pos:
                has_open = True
                print(f"\n{ticker}: {len(open_pos)} OPEN positions:")
                for p in open_pos:
                    pid, side, qty, entry, ot, status = p
                    ot_str = ot.astimezone(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M") if ot else "?"
                    print(f"  {pid}: {side} {qty} @ ${entry} opened {ot_str}")
            else:
                print(f"\n{ticker}: 0 open positions")
        except Exception as e:
            print(f"\n{ticker}: ERROR checking open positions - {e}")

    cursor.close()
    conn.close()

    if has_open:
        print("\n*** WARNING: Open positions exist! ***")
        print("These are PAPER positions (perp bots don't execute on real exchanges).")
        print("They will be deleted during reset.")
    else:
        print("\nNo open positions found. Safe to reset.")


def reset(args):
    """Phase 3 Steps 3-4: Reset all perp bot data."""
    if not args.confirm:
        print("ERROR: Must pass --confirm flag to actually reset data.")
        print("Usage: python scripts/reset_perpetual_bots.py --reset --confirm")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    print("RESETTING ALL PERPETUAL BOT DATA")
    print("=" * 60)
    print()

    for ticker, bot in PERP_BOTS.items():
        print(f"{ticker}:")
        for table in bot["tables"]:
            try:
                # Get before count
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                before = cursor.fetchone()[0]

                # Delete all data
                cursor.execute(f"DELETE FROM {table}")
                conn.commit()

                # Get after count
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                after = cursor.fetchone()[0]

                status = "OK" if after == 0 else "WARN"
                print(f"  {table}: BEFORE={before} -> AFTER={after} {status}")
            except Exception as e:
                conn.rollback()
                print(f"  {table}: ERROR - {e}")

        # Reset starting capital in autonomous_config to ensure clean state
        config_key = bot["config_key"]
        starting_capital = bot["starting_capital"]
        try:
            cursor.execute("""
                INSERT INTO autonomous_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (config_key, str(starting_capital)))
            conn.commit()
            print(f"  {config_key} = ${starting_capital:,.2f} (set in autonomous_config)")
        except Exception as e:
            conn.rollback()
            print(f"  Config update failed: {e}")

        print()

    cursor.close()
    conn.close()
    print("RESET COMPLETE")
    print("Restart the server/workers to reinitialize trader instances from clean database state.")


def verify(args):
    """Phase 3 Step 6: Verify clean state after reset."""
    conn = get_connection()
    cursor = conn.cursor()

    print("VERIFYING CLEAN STATE (All Perpetual Bots)")
    print("=" * 60)

    all_clean = True
    for ticker, bot in PERP_BOTS.items():
        print(f"\n{ticker}:")
        starting_capital = bot["starting_capital"]

        # Check each table is empty
        for table in bot["tables"]:
            count = get_table_count(cursor, table)
            status = "CLEAN" if count == 0 else f"DIRTY ({count} rows)"
            if count != 0:
                all_clean = False
            print(f"  {table}: {count} rows [{status}]")

        # Check starting capital in config
        try:
            cursor.execute(
                "SELECT value FROM autonomous_config WHERE key = %s",
                (bot["config_key"],)
            )
            row = cursor.fetchone()
            if row:
                val = float(row[0])
                status = "OK" if val == starting_capital else f"MISMATCH (expected ${starting_capital})"
                print(f"  Starting Capital: ${val:,.2f} [{status}]")
            else:
                print(f"  Starting Capital: NOT SET (will use default ${starting_capital:,.2f})")
        except Exception:
            print(f"  Starting Capital: ERROR reading config")

        # Summary for this bot
        tables_clean = all(get_table_count(cursor, t) == 0 for t in bot["tables"])
        checks = [
            ("Open positions", get_table_count(cursor, f"{bot['prefix']}_positions") == 0),
            ("Closed trades", True),  # Already checked via positions table
            ("Equity snapshots", get_table_count(cursor, f"{bot['prefix']}_equity_snapshots") == 0),
            ("Scan activity", get_table_count(cursor, f"{bot['prefix']}_scan_activity") == 0),
        ]
        print(f"  Verification:")
        for check_name, passed in checks:
            print(f"    {'[PASS]' if passed else '[FAIL]'} {check_name}: {'0' if passed else 'NOT EMPTY'}")

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    if all_clean:
        print("ALL PERPETUAL BOTS: CLEAN STATE VERIFIED")
        print("Return % should show 0.00% for all bots.")
        print("Bots will start fresh on next scan cycle after server restart.")
    else:
        print("WARNING: Some tables still have data. Re-run --reset --confirm.")


def main():
    parser = argparse.ArgumentParser(description="Reset perpetual bot trading data")
    parser.add_argument("--diagnose", action="store_true", help="Phase 1: Show diagnosis of -105%% bug")
    parser.add_argument("--backup", action="store_true", help="Phase 3: Backup all data to CSV")
    parser.add_argument("--check-open", action="store_true", help="Phase 3: Check for open positions")
    parser.add_argument("--reset", action="store_true", help="Phase 3: Reset all data (requires --confirm)")
    parser.add_argument("--verify", action="store_true", help="Phase 3: Verify clean state")
    parser.add_argument("--confirm", action="store_true", help="Confirm destructive operations")
    parser.add_argument("--all", action="store_true", help="Run full sequence: diagnose -> backup -> check -> reset -> verify")

    args = parser.parse_args()

    if not any([args.diagnose, args.backup, args.check_open, args.reset, args.verify, args.all]):
        parser.print_help()
        return

    if args.all:
        print("Running full reset sequence...\n")
        diagnose(args)
        print("\n")
        backup_dir = backup(args)
        print(f"\nBackups saved to: {backup_dir}\n")
        check_open(args)
        print()
        if args.confirm:
            reset(args)
            print()
            verify(args)
        else:
            print("\nTo proceed with reset, re-run with --all --confirm")
        return

    if args.diagnose:
        diagnose(args)
    if args.backup:
        backup(args)
    if args.check_open:
        check_open(args)
    if args.reset:
        reset(args)
    if args.verify:
        verify(args)


if __name__ == "__main__":
    main()
