#!/usr/bin/env python3
"""Close all open AGAPE-SPOT positions in the database.

This script connects directly to PostgreSQL and force-closes every open
position with reason='SYSTEM_RESET'.  It does NOT sell on Coinbase —
any crypto still held there must be manually sold or will be cleaned up
by the orphan-sell logic on the next scan cycle.

Usage:
    python scripts/agape_spot_close_all_positions.py

Requires DATABASE_URL environment variable.
"""
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Show what's currently open
        cur.execute("""
            SELECT position_id, ticker, account_label, status,
                   entry_price, quantity, open_time
            FROM agape_spot_positions
            WHERE status = 'open'
            ORDER BY ticker, account_label
        """)
        open_positions = cur.fetchall()

        if not open_positions:
            print("No open positions found. System is already clean.")
            return

        print(f"\n{'='*70}")
        print(f"  OPEN POSITIONS TO CLOSE: {len(open_positions)}")
        print(f"{'='*70}")
        for p in open_positions:
            notional = (p["entry_price"] or 0) * (p["quantity"] or 0)
            print(
                f"  {p['ticker']:10s} [{p['account_label']:10s}] "
                f"qty={p['quantity']}  entry=${p['entry_price']:.4f}  "
                f"notional=${notional:.2f}  opened={p['open_time']}"
            )

        # 2. Close all open positions at entry price (P&L = $0 since we
        #    don't have live prices here)
        cur.execute("""
            UPDATE agape_spot_positions
            SET status = 'closed',
                close_time = NOW(),
                close_price = entry_price,
                realized_pnl = 0,
                close_reason = 'SYSTEM_RESET'
            WHERE status = 'open'
            RETURNING position_id, ticker, account_label
        """)
        closed = cur.fetchall()
        conn.commit()

        print(f"\n{'='*70}")
        print(f"  CLOSED {len(closed)} POSITIONS (reason=SYSTEM_RESET, P&L=$0)")
        print(f"{'='*70}")
        for c in closed:
            print(f"  Closed: {c['ticker']} [{c['account_label']}] {c['position_id']}")

        # 3. Verify nothing is left open
        cur.execute("SELECT COUNT(*) AS cnt FROM agape_spot_positions WHERE status = 'open'")
        remaining = cur.fetchone()["cnt"]
        print(f"\n  Remaining open positions: {remaining}")
        if remaining == 0:
            print("  System is clean — new trades can start fresh.\n")
        else:
            print(f"  WARNING: {remaining} positions still open!\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
