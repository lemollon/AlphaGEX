"""
Force-close stuck perpetual positions across all AGAPE perp bots.

Root cause: Positions opened on 2/25-2/26 2026 never closed because the worker
restarted and the bots failed to re-initialize. With max_positions filled,
no new trades could open. This script closes them at current market price.

Usage (Render shell):
    python scripts/perp_force_close_stuck.py              # Dry run (show what would close)
    python scripts/perp_force_close_stuck.py --execute     # Actually close them
"""

import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")

# All perp bots with their table prefix and price ticker
PERP_BOTS = [
    {"prefix": "agape_eth_perp", "ticker": "ETH", "label": "ETH-PERP"},
    {"prefix": "agape_sol_perp", "ticker": "SOL", "label": "SOL-PERP"},
    {"prefix": "agape_avax_perp", "ticker": "AVAX", "label": "AVAX-PERP"},
    {"prefix": "agape_btc_perp", "ticker": "BTC", "label": "BTC-PERP"},
    {"prefix": "agape_xrp_perp", "ticker": "XRP", "label": "XRP-PERP"},
    {"prefix": "agape_doge_perp", "ticker": "DOGE", "label": "DOGE-PERP"},
    {"prefix": "agape_shib_perp", "ticker": "SHIB", "label": "SHIB-PERP"},
]


def get_coinbase_price(ticker: str) -> float:
    """Get current spot price from Coinbase public API."""
    try:
        url = f"https://api.coinbase.com/v2/prices/{ticker}-USD/spot"
        resp = requests.get(url, headers={"User-Agent": "AlphaGEX/1.0"}, timeout=5)
        if resp.status_code == 200:
            return float(resp.json()["data"]["amount"])
    except Exception as e:
        print(f"  ERROR: Could not get {ticker} price: {e}")
    return 0.0


def main():
    execute = "--execute" in sys.argv

    try:
        from database_adapter import get_connection
    except ImportError:
        print("ERROR: database_adapter not available. Run from project root.")
        sys.exit(1)

    print("=" * 70)
    print(f"AGAPE PERPETUAL - FORCE CLOSE STUCK POSITIONS")
    print(f"Mode: {'EXECUTE' if execute else 'DRY RUN (add --execute to apply)'}")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70)

    total_closed = 0
    total_pnl = 0.0

    for bot in PERP_BOTS:
        prefix = bot["prefix"]
        table = f"{prefix}_positions"
        label = bot["label"]

        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(f"""
                SELECT position_id, side, quantity, entry_price, open_time
                FROM {table}
                WHERE status = 'open'
                ORDER BY open_time
            """)
            stuck = cur.fetchall()
        except Exception as e:
            print(f"\n{label}: Table error - {e}")
            cur.close()
            conn.close()
            continue

        if not stuck:
            print(f"\n{label}: No stuck positions")
            cur.close()
            conn.close()
            continue

        current_price = get_coinbase_price(bot["ticker"])
        if current_price <= 0:
            print(f"\n{label}: Could not get price, skipping")
            cur.close()
            conn.close()
            continue

        print(f"\n{label}: {len(stuck)} stuck positions (current price: ${current_price:,.2f})")
        print("-" * 70)

        for row in stuck:
            pos_id, side, qty, entry, open_time = row
            qty = float(qty)
            entry = float(entry)
            direction = 1 if side == "long" else -1
            pnl = round((current_price - entry) * qty * direction, 2)
            age_hours = (datetime.now(CENTRAL_TZ) - open_time.astimezone(CENTRAL_TZ)).total_seconds() / 3600

            print(f"  {pos_id}: {side} {qty} @ ${entry:,.2f} | "
                  f"P&L: ${pnl:+,.2f} | Age: {age_hours:.0f}h")

            if execute:
                try:
                    cur.execute(f"""
                        UPDATE {table}
                        SET status = 'closed', close_time = NOW(),
                            close_price = %s, realized_pnl = %s,
                            close_reason = 'FORCE_CLOSED_STALE'
                        WHERE position_id = %s AND status = 'open'
                    """, (current_price, pnl, pos_id))
                    conn.commit()
                    print(f"    -> CLOSED")
                except Exception as e:
                    conn.rollback()
                    print(f"    -> FAILED: {e}")
                    continue

            total_closed += 1
            total_pnl += pnl

        # Log the action
        if execute:
            try:
                log_table = f"{prefix}_activity_log"
                cur.execute(f"""
                    INSERT INTO {log_table} (level, action, message)
                    VALUES ('INFO', 'FORCE_CLOSE_STALE',
                            'Force-closed {len(stuck)} stale positions. Total P&L: ${total_pnl:+,.2f}')
                """)
                conn.commit()
            except Exception:
                conn.rollback()

        cur.close()
        conn.close()

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {total_closed} positions {'closed' if execute else 'would close'}")
    print(f"Total P&L impact: ${total_pnl:+,.2f}")
    if not execute:
        print(f"\nRun with --execute to apply changes")
    print("=" * 70)


if __name__ == "__main__":
    main()
