"""Backfill sw_vix_daily so the VIX decay gate works from day one.

WHY THIS EXISTS
---------------
vix_decay_ratio() needs 21 prior sessions before it returns a number, and
unknown BLOCKS. Without a backfill, EBB PM would sit out roughly a month after
deploy while the scanner accumulates history one session at a time — safe, but
silently dead, which is the failure mode that is hardest to notice.

SOURCE
------
The local research warehouse's `vol_regime_daily` (VIX daily closes back to
1990). Only the trailing ~90 sessions are needed; we take 400 for headroom.

USAGE
-----
    # dry run — prints what it would write, touches nothing
    python -m backend.bots.seed_vix_history

    # actually write
    python -m backend.bots.seed_vix_history --commit

Reads DATABASE_URL from the environment (the same one the backend uses).
Idempotent: upserts by trade_date, so re-running is harmless and simply
refreshes any rows whose closes were revised.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

WAREHOUSE = Path.home() / "dev" / "ironforge-data" / "warehouse" / "ironforge.duckdb"
LOOKBACK_SESSIONS = 400


def load_from_warehouse(limit: int = LOOKBACK_SESSIONS) -> list[tuple]:
    try:
        import duckdb
    except ImportError:
        sys.exit("duckdb not installed — run this from the research box, or "
                 "hand-supply rows via --csv")
    if not WAREHOUSE.exists():
        sys.exit(f"warehouse not found at {WAREHOUSE}")
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    rows = con.execute(
        "SELECT date, vix FROM vol_regime_daily "
        "WHERE vix IS NOT NULL ORDER BY date DESC LIMIT ?", [limit]
    ).fetchall()
    con.close()
    return sorted((d, float(v)) for d, v in rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--limit", type=int, default=LOOKBACK_SESSIONS)
    args = ap.parse_args()

    rows = load_from_warehouse(args.limit)
    if not rows:
        sys.exit("no VIX rows found")

    print(f"{len(rows)} sessions  {rows[0][0]} .. {rows[-1][0]}")
    print(f"  latest: {rows[-1][0]} vix={rows[-1][1]:.2f}")
    tail = [v for _, v in rows[-21:]]
    print(f"  implied ratio for the next session: "
          f"{tail[-1] / max(tail[:-1]):.3f}  "
          f"(prior {tail[-1]:.2f} / 20d max {max(tail[:-1]):.2f})")

    if not args.commit:
        print("\nDRY RUN — nothing written. Re-run with --commit.")
        return

    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    from sqlalchemy import create_engine
    from .vix_regime import ensure_vix_table, record_vix

    engine = create_engine(url)
    ensure_vix_table(engine)
    for d, v in rows:
        record_vix(engine, d, v)
    print(f"\nwrote {len(rows)} rows to sw_vix_daily")


if __name__ == "__main__":
    main()
