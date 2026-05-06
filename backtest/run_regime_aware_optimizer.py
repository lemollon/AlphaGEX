"""Convenience runner — for ONE bot, evaluates current production config,
default chop+trend profiles, and a small grid around the defaults; reports
per-regime metrics so the operator can pick profile values to /apply.

Usage:
    python -m backtest.run_regime_aware_optimizer --bot SOL --since 2026-04-01
    python -m backtest.run_regime_aware_optimizer --bot SHIB_FUTURES --grid coarse
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import os
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.agape_shared.exit_profile import (
    ExitProfile, default_chop_profile, default_trend_profile,
)
from backtest.perp_exit_optimizer import (
    BOTS, load_entries, load_price_stream, load_regime_per_entry,
    evaluate_with_profile,
)


def _bot_by_label(label: str) -> dict:
    norm = f"AGAPE_{label.upper()}"
    if not norm.endswith(("_PERP", "_FUTURES")):
        # Caller said e.g. SOL — assume perp
        norm = norm + "_PERP" if norm.split("_")[1] not in ("LINK","LTC","BCH","SHIB_FUTURES") else norm
    for b in BOTS:
        if b["name"].endswith(label.upper()) or b["name"] == norm:
            return b
    raise SystemExit(f"unknown bot {label}")


def _split_entries(entries, regimes):
    chop, trend, unknown = [], [], []
    for e in entries:
        r = regimes.get(e["position_id"], "unknown")
        if r == "trend":
            trend.append(e)
        elif r == "chop":
            chop.append(e)
        else:
            unknown.append(e)
    return chop, trend, unknown


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", required=True, help="e.g. SOL, AVAX, SHIB_FUTURES")
    p.add_argument("--since", default=None, help="YYYY-MM-DD entry filter (open_time >=)")
    p.add_argument("--grid", default="coarse", choices=("coarse","fine"))
    args = p.parse_args()

    from database_adapter import get_connection
    conn = get_connection()
    if not conn:
        raise SystemExit("no DB connection")

    bot = _bot_by_label(args.bot)
    print(f"bot={bot['name']}  table={bot['table']}  starting_capital={bot['starting_capital']}")

    entries = load_entries(conn, bot["table"])
    if args.since:
        cutoff = dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc)
        entries = [e for e in entries if e["open_time"] >= cutoff]
    print(f"entries: {len(entries)}")

    ts_arr, px_arr = load_price_stream(conn, bot["table"], bot["price_col"])
    print(f"price-stream points: {len(ts_arr)}")

    regimes = load_regime_per_entry(conn, bot["table"])
    chop_e, trend_e, unk_e = _split_entries(entries, regimes)
    print(f"split: chop={len(chop_e)}  trend={len(trend_e)}  unknown={len(unk_e)}")

    # Baseline: default chop applied to everyone (apples-to-current behaviour)
    bl = evaluate_with_profile(entries, ts_arr, px_arr, default_chop_profile())
    print("\n[baseline: default chop profile, all entries]")
    print(json.dumps(bl, indent=2))

    # Per-regime: chop entries -> chop profile; trend entries -> trend profile
    rc = evaluate_with_profile(chop_e, ts_arr, px_arr, default_chop_profile())
    rt = evaluate_with_profile(trend_e, ts_arr, px_arr, default_trend_profile())
    ru = evaluate_with_profile(unk_e, ts_arr, px_arr, default_chop_profile())
    combined_pnl = rc["total_pnl"] + rt["total_pnl"] + ru["total_pnl"]
    combined_trades = rc["trades"] + rt["trades"] + ru["trades"]
    print("\n[regime-aware: default chop+trend profiles]")
    print(f"  chop:    {json.dumps(rc)}")
    print(f"  trend:   {json.dumps(rt)}")
    print(f"  unknown: {json.dumps(ru)}")
    print(f"  combined total_pnl={combined_pnl:+.2f}  trades={combined_trades}")

    if args.grid == "fine":
        # Tiny per-bot grid around the defaults, only on the chop portion
        # (trend portion has fewer knobs that matter — keep it simple for v1).
        print("\n[chop grid search around defaults]")
        best = None
        for act in [0.2, 0.3, 0.5]:
            for trail in [0.1, 0.15, 0.25]:
                for tgt in [0.6, 1.0, 1.5]:
                    for mfe in [30.0, 40.0, 60.0]:
                        prof = ExitProfile(act, trail, tgt, mfe, 6, 1.5, 5.0)
                        r = evaluate_with_profile(chop_e, ts_arr, px_arr, prof)
                        if best is None or r["total_pnl"] > best[0]["total_pnl"]:
                            best = (r, prof)
        print(f"  best chop config: pnl={best[0]['total_pnl']:+.2f} "
              f"trades={best[0]['trades']} wr={best[0]['win_rate_pct']}%")
        print(f"  profile: {best[1].to_dict()}")

    conn.close()


if __name__ == "__main__":
    main()
