#!/usr/bin/env python3
"""
DUMP PERP SIGNAL × CONFIDENCE HISTOGRAM

Counts every (combined_signal, combined_confidence) pair that ever stamped a
position_id on a perp/futures bot's scan_activity table. Fast diagnostic for
why classify_regime() reports trend=0 — if MEDIUM/HIGH directional reads
never appear in this output, the classifier rules need to widen, OR the
signal engine needs to escalate confidence.

Usage:
    python scripts/dump_perp_signal_histogram.py            # all 11 bots
    python scripts/dump_perp_signal_histogram.py --bot BTC  # one bot
    python scripts/dump_perp_signal_histogram.py --since 2026-04-01
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Bot label -> scan_activity table name.
# Mirrors the BOTS list in backtest/perp_exit_optimizer.py.
_BOTS = {
    "BTC":           "agape_btc_perp_scan_activity",
    "ETH":           "agape_eth_perp_scan_activity",
    "SOL":           "agape_sol_perp_scan_activity",
    "AVAX":          "agape_avax_perp_scan_activity",
    "XRP":           "agape_xrp_perp_scan_activity",
    "DOGE":          "agape_doge_perp_scan_activity",
    "SHIB_PERP":     "agape_shib_perp_scan_activity",
    "SHIB_FUTURES":  "agape_shib_futures_scan_activity",
    "LINK_FUTURES":  "agape_link_futures_scan_activity",
    "LTC_FUTURES":   "agape_ltc_futures_scan_activity",
    "BCH_FUTURES":   "agape_bch_futures_scan_activity",
}


def _get_connection():
    try:
        from database_adapter import get_connection as _get
        conn = _get()
    except Exception as e:
        raise SystemExit(f"db connect failed: {e}")
    if conn is None:
        raise SystemExit("db connect returned None — DATABASE_URL likely unset")
    return conn


def _classify(sig, conf, gex):
    """Inline mirror of trading.agape_shared.regime_classifier.classify_regime
    so we can label rows alongside their counts."""
    if sig in ("LONG", "SHORT") and conf in ("MEDIUM", "HIGH"):
        return "trend"
    if sig == "RANGE_BOUND":
        return "chop"
    if sig in ("LONG", "SHORT"):
        return "chop"
    if sig is None:
        if gex == "NEGATIVE":
            return "trend"
        if gex == "POSITIVE":
            return "chop"
    return "unknown"


def _dump_one(cursor, label: str, table: str, since: str | None) -> None:
    where = "WHERE position_id IS NOT NULL"
    params: list = []
    if since:
        where += " AND timestamp >= %s"
        params.append(since)

    cursor.execute(
        f"""
        SELECT
            COALESCE(combined_signal, '<none>'),
            COALESCE(combined_confidence, '<none>'),
            COALESCE(crypto_gex_regime, '<none>'),
            COUNT(*)
        FROM {table}
        {where}
        GROUP BY combined_signal, combined_confidence, crypto_gex_regime
        ORDER BY COUNT(*) DESC
        """,
        params,
    )
    rows = cursor.fetchall()

    print(f"\n[{label}]  table={table}")
    print("-" * 78)
    if not rows:
        print("  (no scan rows with position_id since cutoff)")
        return

    total = sum(int(r[3] or 0) for r in rows)
    regime_totals = {"chop": 0, "trend": 0, "unknown": 0}

    print(f"  {'signal':<14} {'conf':<8} {'gex':<10} {'count':>7}  {'pct':>6}  regime")
    for sig, conf, gex, n in rows:
        n = int(n or 0)
        pct = (n / total * 100) if total else 0
        sig_for_classify = None if sig == "<none>" else sig
        conf_for_classify = None if conf == "<none>" else conf
        gex_for_classify = None if gex == "<none>" else gex
        regime = _classify(sig_for_classify, conf_for_classify, gex_for_classify)
        regime_totals[regime] += n
        print(f"  {sig:<14} {conf:<8} {gex:<10} {n:>7}  {pct:>5.1f}%  {regime}")

    print(f"\n  total scans w/ position_id: {total}")
    for r, c in regime_totals.items():
        rpct = (c / total * 100) if total else 0
        print(f"    classified as {r:<8} {c:>7}  ({rpct:.1f}%)")


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    p.add_argument("--bot", default=None,
                   help=f"one of: {', '.join(_BOTS.keys())}; default = all 11")
    p.add_argument("--since", default=None,
                   help="ISO date filter (timestamp >=). Default = all history.")
    args = p.parse_args()

    if args.bot and args.bot.upper() not in _BOTS:
        raise SystemExit(f"unknown bot '{args.bot}'. Available: {', '.join(_BOTS.keys())}")

    bots = {args.bot.upper(): _BOTS[args.bot.upper()]} if args.bot else _BOTS

    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except ValueError:
            raise SystemExit(f"bad --since '{args.since}', expected YYYY-MM-DD")

    ts = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M CT")
    print("=" * 78)
    cutoff = args.since or "all history"
    print(f"PERP SIGNAL × CONFIDENCE HISTOGRAM   ({cutoff}; {ts})")
    print("=" * 78)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        for label, table in bots.items():
            try:
                _dump_one(cursor, label, table, since_dt)
            except Exception as e:
                print(f"\n[{label}] ERROR: {e}")
                conn.rollback()
        cursor.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
