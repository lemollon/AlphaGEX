#!/usr/bin/env python3
"""Faithful-SPARK comparison: SPARK's actual exits vs EMBER's exit sweep on SPARK's REAL trades.

Replays SPARK's actual recorded iron condors (real strikes) through EMBER's minute data
(2026-02-27 -> 2026-05-21) and reports, per fill model: SPARK's actual outcome vs EMBER's
PT30/SL0.5x config vs EMBER's best exit, over the same priced trades.

    python scripts/spark_compare.py
"""
import datetime as dt
import os

from backtest.ember.spark_replay import build_spark_paths, compare_spark, load_spark_trades

START, END = dt.date(2026, 2, 27), dt.date(2026, 5, 21)


def _line(label, s):
    if not s:
        return f"  {label:<28} (none)"
    return (f"  {label:<28} n={s['n']:>3}  WR={s['win_rate']:>5}%  "
            f"EV/ct=${s['ev_per_contract']:>9}  total=${s['total_pnl']:>9}")


def main() -> int:
    db = os.environ["DATABASE_URL"]
    trades = load_spark_trades(db, START, END)
    print(f"SPARK distinct trades {START}..{END}: {len(trades)}")
    for fill in ("ask_cross", "mid"):
        paths, priced, skipped = build_spark_paths(trades, db, fill)
        res = compare_spark(priced, paths)
        print(f"\n===== FILL = {fill}  (priced {len(priced)} / skipped {skipped}) =====")
        print(_line("SPARK actual exits", res["spark_actual"]))
        print(_line("EMBER PT30/SL0.5x (spark_live)", res["ember_spark_live_config"]))
        print(_line("EMBER best exit (" + (res["ember_best"]["policy"] if res["ember_best"] else "-") + ")",
                    res["ember_best"]))
        print("  top 5 EMBER exits by EV/ct:")
        for m in res["top5"]:
            print(f"     {m['policy']:<18} EV/ct=${m['ev_per_contract']:>9}  WR={m['win_rate']}%  total=${m['total_pnl']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
