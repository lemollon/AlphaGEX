#!/usr/bin/env python3
"""
SAMSON Data Reset — Archive fake paper data and reset tables.

CONTEXT: SAMSON's paper MTM was broken. All 537 trades have identical:
  entry=$0.80, exit=$0.08, P&L=$1,872, contracts=26, hold=5min, 100% WR.
  The "$1M in profits" is fake — no real Tradier orders, no real fills.

This script:
1. Archives all fake data to timestamped backup tables
2. Verifies archives are populated
3. Truncates live tables (with confirmation)
4. Verifies clean state

Run on Render shell:
    python3 system_audit/reset_samson_data.py              # Dry run (show what would happen)
    python3 system_audit/reset_samson_data.py --execute     # Actually run the reset

⚠️ DESTRUCTIVE OPERATION — archives are created first, but live data is cleared.
"""

import os
import sys
from datetime import datetime


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        sys.exit(1)


def main():
    dry_run = '--execute' not in sys.argv
    timestamp = datetime.now().strftime('%Y%m%d')

    if dry_run:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║     SAMSON DATA RESET — DRY RUN (no changes made)      ║")
        print("║     Run with --execute to apply changes                 ║")
        print("╚══════════════════════════════════════════════════════════╝\n")
    else:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║     SAMSON DATA RESET — EXECUTING                       ║")
        print("║     ⚠️  This will archive and clear SAMSON tables       ║")
        print("╚══════════════════════════════════════════════════════════╝\n")

    conn = get_connection()
    cur = conn.cursor()

    # Tables to archive and reset
    tables = [
        'samson_positions',
        'samson_equity_snapshots',
        'samson_signals',
        'samson_daily_perf',
        'samson_logs',
    ]

    # ============================================================
    # STEP 1: Show current state
    # ============================================================
    print("--- CURRENT STATE ---")
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: ❌ {e}")
            conn.rollback()

    # Show the "SAMSON test" — are trades identical?
    print("\n--- SAMSON FAKE DATA TEST ---")
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT total_credit) as unique_credits,
                COUNT(DISTINCT close_price) as unique_close_prices,
                COUNT(DISTINCT realized_pnl) as unique_pnls,
                COUNT(DISTINCT contracts) as unique_contracts,
                ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 1) as avg_hold_min,
                ROUND(STDDEV(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 2) as stddev_hold_min,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses
            FROM samson_positions
            WHERE status = 'closed' AND close_time IS NOT NULL
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            total, u_credits, u_prices, u_pnls, u_contracts, avg_hold, stddev_hold, wins, losses = row
            win_rate = wins / total * 100 if total > 0 else 0
            print(f"  Total closed trades: {total}")
            print(f"  Unique entry credits: {u_credits} {'🚨 ALL IDENTICAL' if u_credits == 1 else ''}")
            print(f"  Unique close prices: {u_prices} {'🚨 ALL IDENTICAL' if u_prices == 1 else ''}")
            print(f"  Unique P&Ls: {u_pnls} {'🚨 ALL IDENTICAL' if u_pnls == 1 else ''}")
            print(f"  Unique contract sizes: {u_contracts} {'🚨 ALL IDENTICAL' if u_contracts == 1 else ''}")
            print(f"  Avg hold time: {avg_hold}min, stddev: {stddev_hold}min {'🚨 ZERO VARIANCE' if stddev_hold and float(stddev_hold) < 1 else ''}")
            print(f"  Win rate: {win_rate:.1f}% ({wins}W / {losses}L) {'🚨 IMPOSSIBLE' if win_rate >= 99 else ''}")

            if u_credits == 1 and u_prices == 1 and win_rate >= 99:
                print(f"\n  VERDICT: 🚨 CONFIRMED FAKE — all trades are identical paper fills")
            else:
                print(f"\n  VERDICT: Data appears varied — review before resetting")
        else:
            print("  No closed trades found")
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        conn.rollback()

    if dry_run:
        print("\n--- DRY RUN COMPLETE ---")
        print("Run with --execute to archive and reset tables.")
        cur.close()
        conn.close()
        return

    # ============================================================
    # STEP 2: Create archive tables
    # ============================================================
    print("\n--- CREATING ARCHIVES ---")
    for table in tables:
        archive_name = f"{table}_archive_{timestamp}"
        try:
            # Check if archive already exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                )
            """, (archive_name,))
            exists = cur.fetchone()[0]

            if exists:
                print(f"  {archive_name}: already exists (skipping create)")
            else:
                cur.execute(f"""
                    CREATE TABLE {archive_name} AS
                    SELECT *, 'PAPER_MODE_FAKE_DATA' AS archive_reason, NOW() AS archived_at
                    FROM {table}
                """)
                conn.commit()
                print(f"  ✅ Created {archive_name}")
        except Exception as e:
            print(f"  ❌ Failed to create {archive_name}: {e}")
            conn.rollback()

    # ============================================================
    # STEP 3: Verify archives
    # ============================================================
    print("\n--- VERIFYING ARCHIVES ---")
    all_archived = True
    for table in tables:
        archive_name = f"{table}_archive_{timestamp}"
        try:
            cur.execute(f"SELECT COUNT(*) FROM {archive_name}")
            archive_count = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            live_count = cur.fetchone()[0]

            if archive_count == live_count:
                print(f"  ✅ {archive_name}: {archive_count} rows (matches live)")
            elif archive_count > 0:
                print(f"  ⚠️  {archive_name}: {archive_count} rows (live has {live_count})")
            else:
                print(f"  ❌ {archive_name}: EMPTY — aborting reset for {table}")
                all_archived = False
        except Exception as e:
            print(f"  ❌ {archive_name}: {e}")
            all_archived = False
            conn.rollback()

    if not all_archived:
        print("\n❌ ABORTING: Not all archives populated. Fix archive issues first.")
        cur.close()
        conn.close()
        return

    # ============================================================
    # STEP 4: Truncate live tables
    # ============================================================
    print("\n--- TRUNCATING LIVE TABLES ---")
    for table in tables:
        try:
            cur.execute(f"TRUNCATE {table}")
            conn.commit()
            print(f"  ✅ Truncated {table}")
        except Exception as e:
            print(f"  ❌ Failed to truncate {table}: {e}")
            conn.rollback()

    # ============================================================
    # STEP 5: Verify clean state
    # ============================================================
    print("\n--- VERIFYING CLEAN STATE ---")
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            if count == 0:
                print(f"  ✅ {table}: empty (clean)")
            else:
                print(f"  ⚠️  {table}: {count} rows remaining")
        except Exception as e:
            print(f"  ❌ {table}: {e}")
            conn.rollback()

    print(f"\n{'='*60}")
    print(f"  SAMSON DATA RESET COMPLETE")
    print(f"  Archives: samson_*_archive_{timestamp}")
    print(f"  Live tables: truncated and ready for fresh data")
    print(f"  Next step: deploy MTM fix and wait for next trading session")
    print(f"{'='*60}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
