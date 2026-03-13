"""
Force-close VALOR stuck positions from 2/26.

These 30 positions have been open for 15+ days with no position management.
They are paper positions (PAPER mode) so no broker orders needed.

Usage: python scripts/valor_force_close_stuck.py
Add --dry-run to preview without making changes.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def run(dry_run: bool = False):
    from database_adapter import get_connection

    conn = get_connection()
    cur = conn.cursor()

    # Find all stuck open positions
    cur.execute("""
        SELECT position_id, ticker, direction, contracts, entry_price,
               open_time AT TIME ZONE 'America/Chicago' as open_ct
        FROM valor_positions
        WHERE status = 'open'
        ORDER BY open_time
    """)
    positions = cur.fetchall()
    print(f"Found {len(positions)} stuck open positions")

    if not positions:
        print("Nothing to close.")
        conn.close()
        return

    now = datetime.now(CENTRAL_TZ)
    closed_count = 0

    for pos in positions:
        pos_id, ticker, direction, contracts, entry_price, open_ct = pos
        # Close at entry price (P&L = 0) since these are stale paper positions
        # with no valid close price available
        realized_pnl = 0.0
        close_reason = "FORCE_CLOSE_STALE_15D"

        print(f"  {'[DRY RUN] ' if dry_run else ''}Closing {pos_id} | {ticker} {direction} | "
              f"entry={entry_price} | opened {open_ct} | pnl=${realized_pnl:.2f}")

        if not dry_run:
            # Update position to closed
            cur.execute("""
                UPDATE valor_positions
                SET status = 'closed',
                    close_time = NOW(),
                    close_price = %s,
                    close_reason = %s,
                    realized_pnl = %s
                WHERE position_id = %s AND status = 'open'
            """, (float(entry_price), close_reason, realized_pnl, pos_id))

            # Insert into closed trades for permanent record
            cur.execute("""
                INSERT INTO valor_closed_trades (
                    position_id, symbol, ticker, direction, contracts,
                    entry_price, exit_price, realized_pnl,
                    gamma_regime, signal_source, close_reason,
                    open_time, close_time, hold_duration_minutes,
                    is_overnight_session
                )
                SELECT
                    position_id, symbol, ticker, direction, contracts,
                    entry_price, %s, %s,
                    gamma_regime, signal_source, %s,
                    open_time, NOW(),
                    EXTRACT(EPOCH FROM (NOW() - open_time)) / 60,
                    TRUE
                FROM valor_positions
                WHERE position_id = %s
                ON CONFLICT (position_id) DO NOTHING
            """, (float(entry_price), realized_pnl, close_reason, pos_id))

            closed_count += 1

    if not dry_run:
        conn.commit()
        print(f"\nForce-closed {closed_count} positions at entry price (P&L = $0 each)")
        print("Margin is now freed up for new trades.")
    else:
        print(f"\n[DRY RUN] Would close {len(positions)} positions. Run without --dry-run to execute.")

    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
