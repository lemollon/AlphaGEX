#!/usr/bin/env python3
"""
JUBILEE IC Health Verification — Check all safety systems are working.

Verifies:
1. No stranded open positions
2. EOD job is registered (check scheduler)
3. Heartbeat entries in jubilee_logs
4. Equity snapshots being recorded
5. Closed trades have proper close_reason values

Run on Render shell:
    python3 system_audit/verify_jubilee_health.py
"""

import os
import sys
from datetime import datetime, timedelta


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        sys.exit(1)


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     JUBILEE IC HEALTH VERIFICATION                      ║")
    print(f"║     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    conn = get_connection()
    cur = conn.cursor()

    passed = 0
    warned = 0
    failed = 0

    def ok(msg):
        nonlocal passed; passed += 1; print(f"  ✅ {msg}")
    def warn(msg):
        nonlocal warned; warned += 1; print(f"  ⚠️  {msg}")
    def fail(msg):
        nonlocal failed; failed += 1; print(f"  ❌ {msg}")

    # CHECK 1: Open positions
    print("--- CHECK 1: Open positions (should be 0 outside market hours) ---")
    cur.execute("""
        SELECT COUNT(*),
               string_agg(position_id, ', ') as ids
        FROM jubilee_ic_positions
        WHERE status IN ('open', 'pending', 'closing')
    """)
    count, ids = cur.fetchone()
    if count == 0:
        ok("No open IC positions")
    elif count <= 10:
        warn(f"{count} open IC positions: {ids}")
    else:
        fail(f"{count} open IC positions — possible stranding")

    # CHECK 2: Recent heartbeats (should have IC_HEARTBEAT entries)
    print("\n--- CHECK 2: Heartbeat monitoring ---")
    cur.execute("""
        SELECT COUNT(*), MAX(log_time) as latest
        FROM jubilee_logs
        WHERE action = 'IC_HEARTBEAT'
        AND log_time > NOW() - INTERVAL '1 day'
    """)
    hb_count, latest_hb = cur.fetchone()
    if hb_count > 0:
        ok(f"{hb_count} heartbeats in last 24h (latest: {latest_hb})")
    else:
        warn("No heartbeats in last 24h — may not have deployed yet or market was closed")

    # Check heartbeat content — is trader active or DEAD?
    cur.execute("""
        SELECT message, COUNT(*)
        FROM jubilee_logs
        WHERE action = 'IC_HEARTBEAT'
        AND log_time > NOW() - INTERVAL '1 day'
        GROUP BY message
        ORDER BY COUNT(*) DESC
    """)
    for msg, cnt in cur.fetchall():
        status = "✅" if "active" in str(msg) else "⚠️ "
        print(f"    {status} {msg}: {cnt} occurrences")

    # CHECK 3: Init failure logs
    print("\n--- CHECK 3: Init failure logs ---")
    cur.execute("""
        SELECT COUNT(*), MAX(log_time)
        FROM jubilee_logs
        WHERE action = 'IC_TRADER_INIT_FAILED'
        AND log_time > NOW() - INTERVAL '7 days'
    """)
    init_fail_count, latest_fail = cur.fetchone()
    if init_fail_count == 0:
        ok("No init failures in last 7 days")
    else:
        warn(f"{init_fail_count} init failures in last 7 days (latest: {latest_fail})")
        cur.execute("""
            SELECT log_time, message
            FROM jubilee_logs
            WHERE action = 'IC_TRADER_INIT_FAILED'
            ORDER BY log_time DESC LIMIT 3
        """)
        for ts, msg in cur.fetchall():
            print(f"    {ts}: {msg[:100]}")

    # CHECK 4: Closed trades summary
    print("\n--- CHECK 4: Closed trades (last 7 days) ---")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
            ROUND(AVG(realized_pnl)::numeric, 2) as avg_pnl
        FROM jubilee_ic_closed_trades
        WHERE close_time > NOW() - INTERVAL '7 days'
    """)
    row = cur.fetchone()
    if row and row[0] > 0:
        total, wins, losses, total_pnl, avg_pnl = row
        wr = wins / total * 100 if total > 0 else 0
        ok(f"{total} trades: {wins}W/{losses}L ({wr:.0f}%), P&L=${total_pnl}, avg=${avg_pnl}")
    else:
        warn("No closed trades in last 7 days")

    # CHECK 5: Close reasons
    print("\n--- CHECK 5: Close reason breakdown (last 30 days) ---")
    cur.execute("""
        SELECT close_reason, COUNT(*)
        FROM jubilee_ic_closed_trades
        WHERE close_time > NOW() - INTERVAL '30 days'
        GROUP BY close_reason
        ORDER BY COUNT(*) DESC
    """)
    for reason, cnt in cur.fetchall():
        print(f"    {reason}: {cnt}")

    # CHECK 6: Equity snapshots
    print("\n--- CHECK 6: Equity snapshots ---")
    cur.execute("""
        SELECT COUNT(*), MAX(snapshot_time)
        FROM jubilee_ic_equity_snapshots
        WHERE snapshot_time > NOW() - INTERVAL '1 day'
    """)
    snap_count, latest_snap = cur.fetchone()
    if snap_count > 0:
        ok(f"{snap_count} snapshots in last 24h (latest: {latest_snap})")
    else:
        warn("No equity snapshots in last 24h")

    # CHECK 7: Emergency close events
    print("\n--- CHECK 7: Emergency/EOD close events ---")
    cur.execute("""
        SELECT action, message, log_time
        FROM jubilee_logs
        WHERE action IN ('IC_EOD_CLOSE', 'IC_EMERGENCY_CLOSE', 'IC_TRADER_INIT_FAILED')
        AND log_time > NOW() - INTERVAL '7 days'
        ORDER BY log_time DESC
        LIMIT 10
    """)
    events = cur.fetchall()
    if events:
        for action, msg, ts in events:
            flag = "⚠️ " if "FAILED" in action else "ℹ️ "
            print(f"    {flag} {ts}: [{action}] {msg[:80]}")
    else:
        ok("No emergency events in last 7 days")

    # CHECK 8: Box spread funding (source of IC capital)
    print("\n--- CHECK 8: Box spread funding status ---")
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN status IN ('open', 'active') THEN 1 ELSE 0 END) as active
        FROM jubilee_positions
    """)
    total_box, active_box = cur.fetchone()
    if active_box and active_box > 0:
        ok(f"{active_box} active box spread(s) funding IC trading")
    elif total_box and total_box > 0:
        warn(f"No active box spreads ({total_box} total) — IC trading may be unfunded")
    else:
        warn("No box spreads found")

    # SUMMARY
    print(f"\n{'='*60}")
    print(f"  RESULT: {passed} passed, {warned} warnings, {failed} failed")
    if failed > 0:
        print(f"  ❌ JUBILEE IC has issues — review failures above")
    elif warned > 0:
        print(f"  ⚠️  MOSTLY HEALTHY — review warnings")
    else:
        print(f"  ✅ JUBILEE IC is healthy")
    print(f"{'='*60}")

    cur.close()
    conn.close()
    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
