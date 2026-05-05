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


def fetch_trade_summary(cursor, table, since_date):
    """Closed-trade outcomes since `since_date`."""
    try:
        cursor.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped') AND realized_pnl > 0),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped') AND realized_pnl <= 0),
                COALESCE(SUM(realized_pnl) FILTER (WHERE status IN ('closed', 'expired', 'stopped')), 0),
                COALESCE(AVG(realized_pnl) FILTER (WHERE status IN ('closed', 'expired', 'stopped') AND realized_pnl > 0), 0),
                COALESCE(AVG(realized_pnl) FILTER (WHERE status IN ('closed', 'expired', 'stopped') AND realized_pnl <= 0), 0),
                COALESCE(MAX(realized_pnl) FILTER (WHERE status IN ('closed', 'expired', 'stopped')), 0),
                COALESCE(MIN(realized_pnl) FILTER (WHERE status IN ('closed', 'expired', 'stopped')), 0),
                COUNT(*) FILTER (WHERE status = 'open'),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')
                                  AND close_reason LIKE 'TRAIL_STOP%'),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')
                                  AND close_reason LIKE 'MAX_LOSS%'),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')
                                  AND close_reason = 'MAX_HOLD_TIME'),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')
                                  AND close_reason LIKE 'TAKE_PROFIT%'),
                COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')
                                  AND close_reason LIKE 'STOP_LOSS%')
            FROM {table}
            WHERE COALESCE(close_time, open_time) >= %s
            """,
            (since_date,),
        )
        r = cursor.fetchone()
        n = int(r[0] or 0)
        wins = int(r[1] or 0)
        losses = int(r[2] or 0)
        return {
            "n_closed": n,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(wins / n * 100, 1) if n else None,
            "sum_pnl": float(r[3] or 0),
            "avg_win": float(r[4] or 0),
            "avg_loss": float(r[5] or 0),
            "best": float(r[6] or 0),
            "worst": float(r[7] or 0),
            "n_open": int(r[8] or 0),
            "by_reason": {
                "TRAIL_STOP":   int(r[9] or 0),
                "MAX_LOSS":     int(r[10] or 0),
                "MAX_HOLD":     int(r[11] or 0),
                "TAKE_PROFIT":  int(r[12] or 0),
                "STOP_LOSS":    int(r[13] or 0),
            },
        }
    except Exception as e:
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
            f"stop_loss={br['STOP_LOSS']} ({pct(br['STOP_LOSS'])})"
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
