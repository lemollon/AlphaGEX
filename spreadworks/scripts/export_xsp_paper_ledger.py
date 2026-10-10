"""Read-only CSV export of EMBER XSP Flow's paper ledger (ember_xsp_paper_ledger).

Usage:
    cd spreadworks && python scripts/export_xsp_paper_ledger.py --out /tmp/xsp_paper_ledger.csv --days 60

DATABASE_URL must point at the same Postgres the paper-logging scheduler jobs
write to (Render sets this already; locally, export it yourself before
running). This script only SELECTs -- it never writes, arms, or touches a
broker.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # put `backend` on sys.path

from backend.db import engine  # noqa: E402
from backend.ember import xsp_paper_ledger  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="xsp_paper_ledger.csv", help="output CSV path")
    parser.add_argument("--days", type=int, default=60, help="lookback window on trade_date")
    args = parser.parse_args()

    if engine is None:
        print("DATABASE_URL is not configured -- nothing to export", file=sys.stderr)
        return 2

    n = xsp_paper_ledger.export_csv(engine, args.out, days=args.days)
    if n == 0:
        print("no rows exported (empty table, or export failed -- see the warning log above)")
        return 0
    print(f"exported {n} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
