"""Read-only CSV export of EMBER TVBook's forward call log (ember_tv_call_log).

Usage:
    cd spreadworks && python scripts/export_tv_call_log.py --out /tmp/tv_call_log.csv --days 30

DATABASE_URL must point at the same Postgres the scanner writes to (Render
sets this already; locally, export it yourself before running). This script
only SELECTs — it never writes, arms, or touches a broker.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # put `backend` on sys.path

from backend.db import engine  # noqa: E402
from backend.ember import tv_call_log  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="tv_call_log.csv", help="output CSV path")
    parser.add_argument("--days", type=int, default=30, help="lookback window on scan_date")
    args = parser.parse_args()

    if engine is None:
        print("DATABASE_URL is not configured -- nothing to export", file=sys.stderr)
        return 2

    n = tv_call_log.export_csv(engine, args.out, days=args.days)
    if n == 0:
        print("no rows exported (empty table, or export failed -- see the warning log above)")
        return 0
    print(f"exported {n} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
