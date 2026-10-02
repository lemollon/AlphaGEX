#!/usr/bin/env python3
"""
PERPS FRESH START

Gives the AGAPE perpetual bots a clean paper slate: every position (open and
closed) and every equity snapshot is MOVED into a timestamped archive table,
so trade count, win rate, P&L, and the equity curve all restart from the
configured starting capital. Nothing is deleted outright:

    agape_btc_perp_positions        -> agape_btc_perp_positions_archive_<TAG>
    agape_btc_perp_equity_snapshots -> agape_btc_perp_equity_snapshots_archive_<TAG>

Scan activity and the activity log are left alone (diagnostics, not stats).

Why: until 2026-09-27 CoinGlass funding data never reached the bots
(funding_regime UNKNOWN), so every trade was a degraded momentum-only paper
trade. Once the funding feed is live, the old book is not comparable.

Run from a Render shell with DATABASE_URL set, then RESTART the trader
service so in-memory state (loss streak, direction tracker, liquidation flag)
resets too.

Usage:
    python scripts/perps_fresh_start.py                 # dry run: counts only
    python scripts/perps_fresh_start.py --execute       # archive all 7 bots
    python scripts/perps_fresh_start.py BTC ETH --execute
    python scripts/perps_fresh_start.py --restore 20260927T011500 --execute
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOTS = ["btc", "eth", "xrp", "sol", "doge", "avax", "shib"]
TABLE_SUFFIXES = ["positions", "equity_snapshots"]
TAG_RE = re.compile(r"^\d{8}T\d{4}(\d{2})?$")


def _tables(bot: str) -> list[str]:
    return [f"agape_{bot}_perp_{suffix}" for suffix in TABLE_SUFFIXES]


def _exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", (table,))
    return cursor.fetchone()[0] is not None


def _count(cursor, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cursor.fetchone()[0])


def fresh_start(conn, bots: list[str], tag: str, execute: bool) -> list[str]:
    """Archive positions + equity snapshots for each bot in ONE transaction."""
    report = []
    cursor = conn.cursor()
    try:
        for bot in bots:
            for table in _tables(bot):
                if not _exists(cursor, table):
                    report.append(f"{table}: missing, skipped")
                    continue
                rows = _count(cursor, table)
                archive = f"{table}_archive_{tag}"
                if execute:
                    cursor.execute(f"CREATE TABLE {archive} AS SELECT * FROM {table}")
                    cursor.execute(f"DELETE FROM {table}")
                report.append(f"{table}: {rows} rows -> {archive}")
        if execute:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
    return report


def restore(conn, bots: list[str], tag: str, execute: bool) -> list[str]:
    """Copy archived rows back into the live tables (keeps any new rows)."""
    report = []
    cursor = conn.cursor()
    try:
        for bot in bots:
            for table in _tables(bot):
                archive = f"{table}_archive_{tag}"
                if not _exists(cursor, archive):
                    report.append(f"{archive}: missing, skipped")
                    continue
                rows = _count(cursor, archive)
                if execute:
                    cursor.execute(
                        f"INSERT INTO {table} SELECT * FROM {archive} ON CONFLICT DO NOTHING"
                    )
                report.append(f"{archive}: {rows} rows -> {table}")
        if execute:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bots", nargs="*", help="BTC ETH XRP SOL DOGE AVAX SHIB (default: all)")
    parser.add_argument("--execute", action="store_true", help="apply changes (default: dry run)")
    parser.add_argument("--restore", metavar="TAG", help="restore archive TAG (YYYYMMDDTHHMMSS)")
    args = parser.parse_args(argv)

    bots = [b.lower() for b in args.bots] or BOTS
    unknown = [b for b in bots if b not in BOTS]
    if unknown:
        parser.error(f"unknown bot(s): {', '.join(unknown)}")
    if args.restore and not TAG_RE.match(args.restore):
        parser.error("--restore TAG must look like 20260927T011500")

    from database_adapter import get_connection

    conn = get_connection()
    if conn is None:
        print("No database connection (is DATABASE_URL set?)")
        return 1
    try:
        if args.restore:
            report = restore(conn, bots, args.restore, args.execute)
        else:
            tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            report = fresh_start(conn, bots, tag, args.execute)
    finally:
        conn.close()

    mode = "APPLIED" if args.execute else "DRY RUN (nothing changed; add --execute)"
    print(mode)
    for line in report:
        print("  " + line)
    if args.execute and not args.restore:
        print("Next: restart the trader service so in-memory bot state resets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
