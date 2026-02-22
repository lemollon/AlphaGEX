#!/usr/bin/env python3
"""
SAMSON MTM Fix Verification — Run after first trading session post-deploy.

Verifies that the MTM fix is producing varied, realistic trade data
instead of identical $0.08 exits.

Run on Render shell:
    python3 system_audit/verify_samson_fix.py

Expected results after fix:
- Entry credits: varied (not all $0.80)
- Exit prices: varied (not all $0.08)
- P&L: has both wins AND losses
- Hold times: varied (not all exactly 5 min)
- Win rate: < 90% (realistic range is 60-80%)
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
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     SAMSON MTM FIX VERIFICATION                         ║")
    print(f"║     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    conn = get_connection()
    cur = conn.cursor()

    passed = 0
    failed = 0

    # CHECK 1: Any new trades today?
    print("--- CHECK 1: New trades today ---")
    cur.execute("""
        SELECT COUNT(*) FROM samson_positions
        WHERE DATE(open_time AT TIME ZONE 'America/Chicago') = CURRENT_DATE
    """)
    today_count = cur.fetchone()[0]
    print(f"  Trades opened today: {today_count}")

    if today_count == 0:
        print("  ⚠️  No trades today — run this during/after market hours")
        print("  Checking ALL trades instead...\n")

    # CHECK 2: Entry credit distribution
    print("--- CHECK 2: Entry credit variety ---")
    cur.execute("""
        SELECT total_credit, COUNT(*) as cnt
        FROM samson_positions
        GROUP BY total_credit
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)
    if rows:
        top_pct = rows[0][1] / total * 100 if total > 0 else 0
        for val, cnt in rows:
            print(f"  ${val}: {cnt} trades ({cnt/total*100:.1f}%)")
        if top_pct > 90 and total > 10:
            print(f"  ❌ STILL BROKEN: {top_pct:.0f}% have same entry credit")
            failed += 1
        else:
            print(f"  ✅ Entry credits are varied")
            passed += 1
    else:
        print("  No trades found")

    # CHECK 3: Exit price distribution
    print("\n--- CHECK 3: Exit price variety ---")
    cur.execute("""
        SELECT close_price, COUNT(*) as cnt
        FROM samson_positions
        WHERE close_price IS NOT NULL
        GROUP BY close_price
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)
    if rows:
        top_pct = rows[0][1] / total * 100 if total > 0 else 0
        for val, cnt in rows:
            print(f"  ${val}: {cnt} trades ({cnt/total*100:.1f}%)")
        if top_pct > 80 and total > 10:
            print(f"  ❌ STILL BROKEN: {top_pct:.0f}% have same exit price")
            failed += 1
        else:
            print(f"  ✅ Exit prices are varied")
            passed += 1
    else:
        print("  No closed trades yet")

    # CHECK 4: P&L distribution (wins AND losses)
    print("\n--- CHECK 4: P&L distribution ---")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl,
            ROUND(MIN(realized_pnl)::numeric, 2) as min_pnl,
            ROUND(MAX(realized_pnl)::numeric, 2) as max_pnl,
            ROUND(STDDEV(realized_pnl)::numeric, 2) as stddev_pnl
        FROM samson_positions
        WHERE realized_pnl IS NOT NULL
    """)
    row = cur.fetchone()
    if row and row[0] > 0:
        total, wins, losses, avg_pnl, min_pnl, max_pnl, stddev_pnl = row
        win_rate = wins / total * 100 if total > 0 else 0
        print(f"  Total: {total} trades")
        print(f"  Wins: {wins}, Losses: {losses}")
        print(f"  Win rate: {win_rate:.1f}%")
        print(f"  Avg P&L: ${avg_pnl}")
        print(f"  Min P&L: ${min_pnl}, Max P&L: ${max_pnl}")
        print(f"  P&L stddev: ${stddev_pnl}")

        if win_rate >= 99 and total > 20:
            print(f"  ❌ STILL BROKEN: 100% win rate with {total} trades is impossible")
            failed += 1
        elif losses == 0 and total > 10:
            print(f"  ⚠️  No losses yet — may need more data")
            passed += 1
        else:
            print(f"  ✅ P&L has realistic distribution")
            passed += 1
    else:
        print("  No P&L data yet")

    # CHECK 5: Hold time distribution
    print("\n--- CHECK 5: Hold time variety ---")
    cur.execute("""
        SELECT
            ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 1) as avg_min,
            ROUND(MIN(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 1) as min_min,
            ROUND(MAX(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 1) as max_min,
            ROUND(STDDEV(EXTRACT(EPOCH FROM (close_time - open_time)) / 60)::numeric, 2) as stddev_min
        FROM samson_positions
        WHERE close_time IS NOT NULL AND open_time IS NOT NULL
    """)
    row = cur.fetchone()
    if row and row[0] is not None:
        avg_min, min_min, max_min, stddev_min = row
        print(f"  Avg: {avg_min}min, Min: {min_min}min, Max: {max_min}min")
        print(f"  Stddev: {stddev_min}min")
        if stddev_min and float(stddev_min) < 1.0 and cur.rowcount > 20:
            print(f"  ❌ STILL BROKEN: all trades have nearly identical hold times")
            failed += 1
        else:
            print(f"  ✅ Hold times are varied")
            passed += 1
    else:
        print("  No hold time data yet")

    # CHECK 6: Close reasons (not all PROFIT_TARGET)
    print("\n--- CHECK 6: Close reason variety ---")
    cur.execute("""
        SELECT close_reason, COUNT(*) as cnt
        FROM samson_positions
        WHERE close_reason IS NOT NULL
        GROUP BY close_reason
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)
    if rows:
        for reason, cnt in rows:
            pct = cnt / total * 100 if total > 0 else 0
            print(f"  {reason}: {cnt} ({pct:.1f}%)")
        # Check if all are profit target
        if len(rows) == 1 and total > 20:
            print(f"  ⚠️  Only one close reason — may indicate issue")
        else:
            print(f"  ✅ Multiple close reasons")
            passed += 1
    else:
        print("  No close reasons yet")

    # CHECK 7: Equity snapshots
    print("\n--- CHECK 7: Equity snapshots ---")
    cur.execute("SELECT COUNT(*) FROM samson_equity_snapshots")
    snap_count = cur.fetchone()[0]
    print(f"  Equity snapshots: {snap_count}")
    if snap_count > 0:
        cur.execute("""
            SELECT MAX(created_at) as latest
            FROM samson_equity_snapshots
        """)
        latest = cur.fetchone()[0]
        print(f"  Latest snapshot: {latest}")

    # CHECK 8: Activity log
    print("\n--- CHECK 8: Activity log ---")
    cur.execute("SELECT COUNT(*) FROM samson_logs")
    log_count = cur.fetchone()[0]
    print(f"  Log entries: {log_count}")

    # SUMMARY
    print(f"\n{'='*60}")
    print(f"  VERIFICATION RESULT: {passed} passed, {failed} failed")
    if failed > 0:
        print(f"  ❌ MTM FIX NOT WORKING — trades are still identical")
        print(f"  Check: Is TRADIER_API_KEY set? Can it quote SPXW options?")
    elif passed == 0:
        print(f"  ⚠️  NOT ENOUGH DATA — wait for trading session")
    else:
        print(f"  ✅ MTM fix appears to be working")
    print(f"{'='*60}")

    cur.close()
    conn.close()
    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
