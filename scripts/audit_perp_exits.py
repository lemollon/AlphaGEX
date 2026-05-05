#!/usr/bin/env python3
"""
AUDIT PERP-BOT EXIT CONFIGS AND POST-RETUNE TRADE OUTCOMES

Read-only inspection script. Pulls:
  - Current autonomous_config rows for each perp/futures bot's exit knobs
  - Closed-trade summary since the 2026-05-03 retune (count, win rate, sum pnl,
    sum of MFE-then-giveback as a "round-trip" proxy)
  - Open-position count

Use this to decide whether DOGE/XRP/SOL/AVAX/SHIB/LINK/LTC/BCH retunes need
to be flipped, tightened, or left alone. NOTHING IS WRITTEN.

Usage:
    python scripts/audit_perp_exits.py
    python scripts/audit_perp_exits.py --since 2026-05-03  # default
    python scripts/audit_perp_exits.py --bot SOL           # one bot
"""

import argparse
import os
import sys
from datetime import datetime, date
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# bot_label -> (autonomous_config prefix, positions table name)
BOTS = {
    "BTC":           ("agape_btc_perp_",       "agape_btc_perp_positions"),
    "ETH":           ("agape_eth_perp_",       "agape_eth_perp_positions"),
    "SOL":           ("agape_sol_perp_",       "agape_sol_perp_positions"),
    "AVAX":          ("agape_avax_perp_",      "agape_avax_perp_positions"),
    "XRP":           ("agape_xrp_perp_",       "agape_xrp_perp_positions"),
    "DOGE":          ("agape_doge_perp_",      "agape_doge_perp_positions"),
    "SHIB":          ("agape_shib_perp_",      "agape_shib_perp_positions"),
    "SHIB_FUTURES":  ("agape_shib_futures_",   "agape_shib_futures_positions"),
    "LINK_FUTURES":  ("agape_link_futures_",   "agape_link_futures_positions"),
    "LTC_FUTURES":   ("agape_ltc_futures_",    "agape_ltc_futures_positions"),
    "BCH_FUTURES":   ("agape_bch_futures_",    "agape_bch_futures_positions"),
}

# Knobs the perp-exit-optimizer /apply endpoint can write
EXIT_KEYS = [
    "no_loss_activation_pct",
    "no_loss_trail_distance_pct",
    "no_loss_profit_target_pct",
    "max_unrealized_loss_pct",
    "no_loss_emergency_stop_pct",
    "max_hold_hours",
    "use_sar",
    "sar_trigger_pct",
    "sar_mfe_threshold_pct",
    "use_no_loss_trailing",
]


def get_connection():
    try:
        from database_adapter import get_connection as _get_conn
        return _get_conn()
    except Exception as e:
        print(f"ERROR: db connect failed: {e}")
        sys.exit(1)


def fetch_applied_config(cursor, prefix):
    cursor.execute(
        "SELECT key, value FROM autonomous_config WHERE key LIKE %s ORDER BY key",
        (f"{prefix}%",),
    )
    rows = cursor.fetchall()
    applied = {r[0].replace(prefix, ""): r[1] for r in rows}
    exit_only = {k: applied[k] for k in EXIT_KEYS if k in applied}
    return exit_only, applied


def _scalar(cursor, sql, params):
    """Run an aggregate query, return the single scalar in row 0 col 0 or None."""
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return row[0]


def fetch_trade_summary(cursor, table, since_date):
    """Closed-trade outcomes since `since_date`. Multiple small queries for
    robustness — one query per scalar avoids per-row tuple-shape surprises and
    keeps each result independent of the others."""
    out = {}
    try:
        # Counts and aggregates over closed trades since cutoff
        out["n_closed"] = int(_scalar(cursor, f"""
            SELECT COUNT(*) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
        """, (since_date,)) or 0)

        out["wins"] = int(_scalar(cursor, f"""
            SELECT COUNT(*) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
              AND realized_pnl > 0
        """, (since_date,)) or 0)

        out["losses"] = int(_scalar(cursor, f"""
            SELECT COUNT(*) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
              AND realized_pnl <= 0
        """, (since_date,)) or 0)

        out["sum_pnl"] = float(_scalar(cursor, f"""
            SELECT COALESCE(SUM(realized_pnl), 0) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
        """, (since_date,)) or 0)

        out["avg_win"] = float(_scalar(cursor, f"""
            SELECT COALESCE(AVG(realized_pnl), 0) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
              AND realized_pnl > 0
        """, (since_date,)) or 0)

        out["avg_loss"] = float(_scalar(cursor, f"""
            SELECT COALESCE(AVG(realized_pnl), 0) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
              AND realized_pnl <= 0
        """, (since_date,)) or 0)

        out["best"] = float(_scalar(cursor, f"""
            SELECT COALESCE(MAX(realized_pnl), 0) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
        """, (since_date,)) or 0)

        out["worst"] = float(_scalar(cursor, f"""
            SELECT COALESCE(MIN(realized_pnl), 0) FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
        """, (since_date,)) or 0)

        out["n_open"] = int(_scalar(cursor, f"""
            SELECT COUNT(*) FROM {table} WHERE status = 'open'
        """, ()) or 0)

        # Close-reason histogram (group by reason, then bucket into our 5 categories)
        cursor.execute(f"""
            SELECT close_reason, COUNT(*)
            FROM {table}
            WHERE status IN ('closed','expired','stopped')
              AND COALESCE(close_time, open_time) >= %s
            GROUP BY close_reason
        """, (since_date,))
        buckets = {"TRAIL_STOP": 0, "MAX_LOSS": 0, "MAX_HOLD": 0,
                   "TAKE_PROFIT": 0, "STOP_LOSS": 0, "OTHER": 0}
        for reason, count in cursor.fetchall():
            r = (reason or "").upper()
            n = int(count or 0)
            if r.startswith("TRAIL_STOP"):
                buckets["TRAIL_STOP"] += n
            elif r.startswith("MAX_LOSS") or r.startswith("EMERGENCY_STOP") or r.startswith("MARGIN_LIQUIDATION"):
                buckets["MAX_LOSS"] += n
            elif r == "MAX_HOLD_TIME" or r == "STALE_RECOVERY":
                buckets["MAX_HOLD"] += n
            elif r.startswith("TAKE_PROFIT") or r.startswith("PROFIT_TARGET"):
                buckets["TAKE_PROFIT"] += n
            elif r.startswith("STOP_LOSS"):
                buckets["STOP_LOSS"] += n
            else:
                buckets["OTHER"] += n
        out["by_reason"] = buckets

        n = out["n_closed"]
        out["win_rate_pct"] = round(out["wins"] / n * 100, 1) if n else None
        return out
    except Exception as e:
        # If anything blew up mid-stream, rollback so subsequent bots' queries
        # aren't poisoned by a transaction-aborted state.
        try:
            cursor.connection.rollback()
        except Exception:
            pass
        return {"error": str(e)}


def print_bot(label, applied_exit, summary):
    print(f"  exit config (autonomous_config rows):")
    if not applied_exit:
        print("    (no rows — bot is on dataclass defaults)")
    else:
        for k, v in applied_exit.items():
            print(f"    {k:<32} = {v}")
    if "error" in summary:
        print(f"  trade summary error: {summary['error']}")
        return
    s = summary
    print(f"  trades since cutoff:")
    print(f"    closed={s['n_closed']:<5} open={s['n_open']:<3} wr={s['win_rate_pct']}%")
    print(f"    sum_pnl={s['sum_pnl']:+,.2f}  avg_win={s['avg_win']:+,.2f}  avg_loss={s['avg_loss']:+,.2f}")
    print(f"    best={s['best']:+,.2f}  worst={s['worst']:+,.2f}")
    if s["n_closed"]:
        br = s["by_reason"]
        denom = s["n_closed"]
        def pct(v): return f"{v/denom*100:.0f}%"
        print(
            "    by close_reason:  "
            f"trail={br['TRAIL_STOP']} ({pct(br['TRAIL_STOP'])})  "
            f"max_loss={br['MAX_LOSS']} ({pct(br['MAX_LOSS'])})  "
            f"max_hold={br['MAX_HOLD']} ({pct(br['MAX_HOLD'])})  "
            f"take_profit={br['TAKE_PROFIT']} ({pct(br['TAKE_PROFIT'])})  "
            f"stop_loss={br['STOP_LOSS']} ({pct(br['STOP_LOSS'])})  "
            f"other={br.get('OTHER', 0)} ({pct(br.get('OTHER', 0))})"
        )


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    p.add_argument("--since", default="2026-05-03",
                   help="ISO date cutoff (close_time >= this). Default = day of last retune.")
    p.add_argument("--bot", default=None, help=f"One of: {', '.join(BOTS.keys())}. Default = all.")
    args = p.parse_args()

    try:
        since_date = datetime.fromisoformat(args.since).date()
    except ValueError:
        print(f"bad --since {args.since}; use YYYY-MM-DD")
        sys.exit(2)

    bots = {args.bot: BOTS[args.bot]} if args.bot else BOTS
    if args.bot and args.bot not in BOTS:
        print(f"unknown --bot {args.bot}. Available: {', '.join(BOTS.keys())}")
        sys.exit(2)

    conn = get_connection()
    cursor = conn.cursor()
    print("=" * 78)
    print(f"PERP EXIT AUDIT  (since {since_date}, ts={datetime.now(CENTRAL_TZ):%Y-%m-%d %H:%M CT})")
    print("=" * 78)
    for label, (prefix, table) in bots.items():
        print(f"\n[{label}]  table={table}  prefix={prefix}")
        print("-" * 78)
        applied_exit, _all = fetch_applied_config(cursor, prefix)
        summary = fetch_trade_summary(cursor, table, since_date)
        print_bot(label, applied_exit, summary)
    cursor.close()
    conn.close()
    print()


if __name__ == "__main__":
    main()
