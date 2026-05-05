#!/usr/bin/env python3
"""
WIPE AGAPE-SHIB-FUTURES HISTORY

The 1000SHIB-FUT bot was running with a price-scaling bug: it stored raw SHIB
spot price ($0.000018) instead of the 1000SHIB index price (raw * 1000), and
its P&L math did not multiply by the 10,000-unit contract_size. Every row in
agape_shib_futures_* is in a broken scale that cannot be back-converted
unambiguously, so we wipe and let the bot start fresh.

This does NOT touch any other bot, the legacy agape_shib_perp tables, or the
configured starting_capital row.

Usage on Render web shell (the trader worker has DATABASE_URL):
    python scripts/wipe_agape_shib_futures.py --diagnose
    python scripts/wipe_agape_shib_futures.py --check-open
    python scripts/wipe_agape_shib_futures.py --wipe --confirm
    python scripts/wipe_agape_shib_futures.py --verify
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

TABLES = [
    "agape_shib_futures_positions",
    "agape_shib_futures_equity_snapshots",
    "agape_shib_futures_scan_activity",
    "agape_shib_futures_activity_log",
]


def get_connection():
    try:
        from database_adapter import get_connection as _get_conn
        return _get_conn()
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)


def get_count(cursor, table):
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except Exception:
        return -1


def diagnose():
    conn = get_connection()
    cursor = conn.cursor()
    ts = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M:%S CT")
    print("=" * 70)
    print(f"AGAPE-SHIB-FUTURES DIAGNOSE  ({ts})")
    print("=" * 70)
    for t in TABLES:
        n = get_count(cursor, t)
        print(f"  {t:<46} {n} rows")
    try:
        cursor.execute("""
            SELECT COUNT(*),
                   COALESCE(SUM(realized_pnl), 0),
                   COALESCE(MIN(entry_price), 0),
                   COALESCE(MAX(entry_price), 0)
            FROM agape_shib_futures_positions
            WHERE status IN ('closed', 'expired', 'stopped')
        """)
        n, total_pnl, min_e, max_e = cursor.fetchone()
        print(f"\n  Closed trades:        {n}")
        print(f"  Sum realized_pnl:     {float(total_pnl):+.6f}  (expect tiny under bug)")
        print(f"  entry_price range:    {float(min_e):.10f} .. {float(max_e):.10f}")
    except Exception as e:
        print(f"  closed-trade summary error: {e}")
    cursor.close()
    conn.close()


def check_open():
    conn = get_connection()
    cursor = conn.cursor()
    print("Open SHIB-FUT positions (paper bot — these are all paper):")
    try:
        cursor.execute("""
            SELECT position_id, side, quantity, entry_price, open_time
            FROM agape_shib_futures_positions
            WHERE status = 'open'
            ORDER BY open_time ASC
        """)
        rows = cursor.fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            pid, side, qty, entry, ot = r
            ot_str = ot.astimezone(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M") if ot else "?"
            print(f"  {pid}: {side} {qty} @ {entry}  opened {ot_str}")
    except Exception as e:
        print(f"  query error: {e}")
    cursor.close()
    conn.close()


def wipe(confirm):
    if not confirm:
        print("Refusing to wipe without --confirm.")
        sys.exit(1)
    conn = get_connection()
    cursor = conn.cursor()
    print("Wiping AGAPE-SHIB-FUTURES tables …")
    for t in TABLES:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            before = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM {t}")
            conn.commit()
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            after = cursor.fetchone()[0]
            print(f"  {t:<46} {before:>6} -> {after}")
        except Exception as e:
            conn.rollback()
            print(f"  {t}: ERROR {e}")
    cursor.close()
    conn.close()
    print("Wipe complete. Restart alphagex-trader so the bot reinitializes.")


def verify():
    conn = get_connection()
    cursor = conn.cursor()
    print("Verifying SHIB-FUT clean state:")
    clean = True
    for t in TABLES:
        n = get_count(cursor, t)
        ok = (n == 0)
        clean = clean and ok
        print(f"  {t:<46} {n} rows  {'CLEAN' if ok else 'DIRTY'}")
    cursor.close()
    conn.close()
    if clean:
        print("\nAll SHIB-FUT tables empty.")
    else:
        print("\nSome tables still have data — rerun --wipe --confirm.")


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    p.add_argument("--diagnose", action="store_true")
    p.add_argument("--check-open", action="store_true")
    p.add_argument("--wipe", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--confirm", action="store_true", help="required with --wipe")
    args = p.parse_args()
    if not any([args.diagnose, args.check_open, args.wipe, args.verify]):
        p.print_help()
        return
    if args.diagnose:
        diagnose()
    if args.check_open:
        check_open()
    if args.wipe:
        wipe(args.confirm)
    if args.verify:
        verify()


if __name__ == "__main__":
    main()
