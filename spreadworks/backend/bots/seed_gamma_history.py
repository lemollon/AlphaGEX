"""Backfill sw_gamma_daily so the squeeze signal works from day one.

WHY THIS EXISTS
---------------
gamma_percentile() needs 60 prior sessions before it returns a number
(PCT_WINDOW in gamma_regime.py), and unknown BLOCKS — squeeze_signal() comes
back UNKNOWN until the window fills. Without a backfill that is ~3 months of
the live 15:05 CT capture job running silently dead while history
accumulates one session at a time. Seed first.

SOURCE
------
`backend/data/gamma_baseline.csv` — a committed baseline (net dealer gamma,
solved per session, 2020-01-02..2026-08-11), the same "ship a CSV in the repo"
pattern `routes_risk.py` uses for `risk_flow_baseline.csv`. NOT DuckDB: the
research warehouse doesn't exist on Render, so a script that reads it can
never run in prod. `net_gex` in the CSV is raw dollars per 1% move (NOT
billions) — record_gamma stores it the same way; only display divides by 1e9.

This script MERGES the CSV with whatever is already live in sw_gamma_daily —
a live-captured row always wins over the static CSV value for the same date
(mirrors the baseline+live overlay `routes_risk._flow_history()` uses for
flow snapshots) — so re-running after the capture job has been running a
while never regresses a real reading back to the seed's estimate.

`ensure_gamma_table`'s caller also auto-seeds from this same CSV on startup
if the table is empty (see backend/gamma_alerts.py), so a fresh deploy is
never blind for three months even if nobody runs this manually. This script
remains useful for a deliberate/verbose backfill, or refreshing after the
CSV baseline itself is regenerated.

USAGE
-----
    # dry run — prints what it would write, touches nothing
    python -m backend.bots.seed_gamma_history

    # actually write
    python -m backend.bots.seed_gamma_history --commit

Reads DATABASE_URL from the environment (the same one the backend uses).
Idempotent: upserts by trade_date, so re-running is harmless.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date
from pathlib import Path

BASELINE_CSV = Path(__file__).resolve().parent.parent / "data" / "gamma_baseline.csv"
LOOKBACK_SESSIONS = 400


def load_from_csv(limit: int = LOOKBACK_SESSIONS) -> list[tuple]:
    if not BASELINE_CSV.exists():
        sys.exit(f"baseline CSV not found at {BASELINE_CSV}")
    rows = []
    with open(BASELINE_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append((date.fromisoformat(r["d"]), float(r["net_gex"]),
                        float(r["spot"]) if r.get("spot") not in (None, "") else None))
    rows.sort(key=lambda r: r[0])
    if limit:
        rows = rows[-limit:]
    return rows


def merged_with_live(engine, csv_rows: list[tuple]) -> list[tuple]:
    """CSV baseline + whatever sw_gamma_daily already has, deduped by date —
    a live row always overrides the CSV value for that date. Same dict-merge
    shape as routes_risk._flow_history()'s baseline+live overlay."""
    from sqlalchemy import text
    from .gamma_regime import GAMMA_DAILY_TABLE

    merged: dict[date, tuple] = {d: (g, s) for d, g, s in csv_rows}
    with engine.begin() as conn:
        live = conn.execute(text(
            f"SELECT trade_date, net_gex, spot FROM {GAMMA_DAILY_TABLE}"
        )).fetchall()
    for d, g, s in live:
        merged[d] = (float(g), float(s) if s is not None else None)
    return sorted((d, g, s) for d, (g, s) in merged.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--limit", type=int, default=LOOKBACK_SESSIONS)
    args = ap.parse_args()

    rows = load_from_csv(args.limit)
    if not rows:
        sys.exit("no gamma rows found")

    print(f"{len(rows)} sessions  {rows[0][0]} .. {rows[-1][0]}")
    d, g, s = rows[-1]
    print(f"  latest: {d} net_gex=${g / 1e9:.2f}B spot={s}")
    if len(rows) >= 60:
        window = [v for _, v, _ in rows[-60:]]
        latest = window[-1]
        implied_pct = sum(1 for v in window if latest > v) / len(window)
        print(f"  implied 60-session percentile for the next reading: "
              f"{implied_pct:.2f}")
    else:
        print(f"  only {len(rows)} sessions — need 60 before the percentile "
              f"(and squeeze_signal) return anything but UNKNOWN")

    if not args.commit:
        print("\nDRY RUN — nothing written. Re-run with --commit.")
        return

    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    from sqlalchemy import create_engine
    from .gamma_regime import ensure_gamma_table, record_gamma

    engine = create_engine(url)
    ensure_gamma_table(engine)
    merged = merged_with_live(engine, rows)
    for d, g, s in merged:
        record_gamma(engine, d, g, s, None)
    print(f"\nwrote {len(merged)} rows to sw_gamma_daily "
          f"(CSV baseline merged with live — live rows win)")


if __name__ == "__main__":
    main()
