"""JOSHUA paper-live monitoring snapshot.

Run any time:
    python scripts/monitor_joshua.py            # today's view
    python scripts/monitor_joshua.py --days 7   # last 7 days

Prints a single-screen summary: scan activity, signals, positions, errors,
per-setup counts, and recent P&L. Read-only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from collections import Counter

import psycopg2
import psycopg2.extras


def _connect():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=1, help="How many days back to summarize")
    args = p.parse_args()

    now_ct_date_sql = "(NOW() AT TIME ZONE 'America/Chicago')::date"
    window_start_sql = f"{now_ct_date_sql} - INTERVAL '{args.days} days'"

    with _connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print(f"=== JOSHUA MONITOR — last {args.days} day(s) ===")
        print()

        # Scan activity breakdown
        cur.execute(f"""
            SELECT cycle_at::date AS d, outcome, COUNT(*) AS n
            FROM helios_scan_activity
            WHERE cycle_at::date >= {window_start_sql}
            GROUP BY 1, 2
            ORDER BY 1 DESC, n DESC
        """)
        by_day = {}
        for r in cur.fetchall():
            by_day.setdefault(r["d"], []).append((r["outcome"], r["n"]))
        for d in sorted(by_day, reverse=True):
            row = by_day[d]
            total = sum(n for _, n in row)
            parts = " | ".join(f"{o}={n}" for o, n in row)
            print(f"  {d}  ({total:>4} cycles)  {parts}")

        # Recent errors
        print()
        print("=== Last 5 errors ===")
        cur.execute(f"""
            SELECT cycle_at, detail FROM helios_scan_activity
            WHERE outcome = 'ERROR' AND cycle_at::date >= {window_start_sql}
            ORDER BY cycle_at DESC LIMIT 5
        """)
        rows = cur.fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  {r['cycle_at']:%Y-%m-%d %H:%M:%S} {r['detail'][:120]}")

        # Signals (TRADE actions)
        print()
        print("=== Signals (TRADE) ===")
        cur.execute(f"""
            SELECT cycle_at, action, spread_type, long_strike, short_strike, spot, detail
            FROM helios_signals
            WHERE cycle_at::date >= {window_start_sql} AND action = 'TRADE'
            ORDER BY cycle_at DESC
        """)
        rows = cur.fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  {r['cycle_at']:%Y-%m-%d %H:%M} {r['spread_type']} long={r['long_strike']} short={r['short_strike']} spot={r['spot']}")

        # Positions
        print()
        print("=== Positions opened in window ===")
        cur.execute(f"""
            SELECT id, spread_type, long_strike, short_strike, contracts, debit,
                   status, exit_reason, realized_pnl, open_time, close_time
            FROM helios_positions
            WHERE open_time::date >= {window_start_sql}
            ORDER BY open_time DESC
        """)
        rows = cur.fetchall()
        if not rows:
            print("  (none)")
        total_pnl = 0.0
        wins = losses = open_n = 0
        for r in rows:
            pnl = float(r["realized_pnl"] or 0.0)
            total_pnl += pnl
            if r["status"] == "OPEN":
                open_n += 1
            elif pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            ot = r["open_time"]
            ct = r["close_time"]
            print(f"  #{r['id']} {r['spread_type']:<10} {r['contracts']}x@${r['debit']:.2f} "
                  f"{r['status']:<6} {r['exit_reason'] or '':<10} "
                  f"pnl=${pnl:>7.2f} open={ot:%m-%d %H:%M} "
                  f"close={ct.strftime('%m-%d %H:%M') if ct else '-':>11}")
        if rows:
            n_closed = wins + losses
            wr = (100.0 * wins / n_closed) if n_closed else 0.0
            print()
            print(f"  Summary: {len(rows)} total ({open_n} open, {wins} wins, {losses} losses), WR={wr:.1f}%, total P&L=${total_pnl:.2f}")

        # Daily state
        print()
        print("=== helios_daily_state ===")
        cur.execute(f"""
            SELECT trade_date, wall_fade_count, wall_break_count, flip_cross_count, last_signal_minute, updated_at
            FROM helios_daily_state
            WHERE trade_date >= {window_start_sql}
            ORDER BY trade_date DESC
        """)
        rows = cur.fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  {r['trade_date']}  fade={r['wall_fade_count']}  break={r['wall_break_count']}  flip={r['flip_cross_count']}  last_minute={r['last_signal_minute']}")

        # Account snapshot
        print()
        print("=== Paper account ===")
        cur.execute("SELECT starting_capital, cash, realized_pnl FROM helios_paper_account ORDER BY id LIMIT 1")
        r = cur.fetchone()
        if r:
            print(f"  starting_capital=${float(r['starting_capital']):,.2f} cash=${float(r['cash']):,.2f} realized_pnl=${float(r['realized_pnl']):,.2f}")


if __name__ == "__main__":
    main()
