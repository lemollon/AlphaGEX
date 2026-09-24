#!/usr/bin/env python3
"""
Reset the 7 AGAPE perpetual PAPER accounts to a clean starting state.

Each bot's positions, scan activity, and equity snapshots are archived into
a dated `<table>_archive_20260924` table (CREATE TABLE ... AS SELECT *) and
then the live tables are cleared, so each account restarts at its
configured starting_capital with zero open positions and zero history.

SAFETY:
  - Refuses to touch ANY bot unless every one of the 7 bots' configured
    mode is PAPER (checked via autonomous_config `agape_<ticker>_perp_mode`,
    defaulting to PAPER when unset, matching AgapeXxxPerpConfig.mode's own
    default). A single bot armed LIVE aborts the whole run before any
    table is touched.
  - --dry-run (the default) only prints row counts; nothing is archived or
    deleted. Pass --execute to actually run it.
  - Each bot's archive + delete happens in ONE transaction, so a bot never
    ends up half-archived / half-deleted if something fails partway.
  - Positions/equity/scan-activity/activity-log tables are auto-discovered
    from each bot's own db.py `_ensure_tables()` (grepped for
    `CREATE TABLE IF NOT EXISTS agape_<ticker>_perp_...`), not hardcoded,
    so this stays correct if a bot ever adds a new per-bot table.

Usage:
    # Default: dry run, prints before/after counts, changes nothing.
    python scripts/reset_agape_perp_paper_accounts.py

    # Actually archive + reset (requires typing the mode check to pass).
    python scripts/reset_agape_perp_paper_accounts.py --execute
"""

import argparse
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")
ARCHIVE_SUFFIX = "archive_20260924"

# ticker -> (table prefix, bot_name used in autonomous_config keys, default starting_capital)
BOTS = {
    "BTC":  ("agape_btc_perp",  "AGAPE_BTC_PERP",  25000.0),
    "ETH":  ("agape_eth_perp",  "AGAPE_ETH_PERP",  12500.0),
    "SOL":  ("agape_sol_perp",  "AGAPE_SOL_PERP",   5000.0),
    "XRP":  ("agape_xrp_perp",  "AGAPE_XRP_PERP",   9000.0),
    "DOGE": ("agape_doge_perp", "AGAPE_DOGE_PERP",  2500.0),
    "AVAX": ("agape_avax_perp", "AGAPE_AVAX_PERP",  2500.0),
    "SHIB": ("agape_shib_perp", "AGAPE_SHIB_PERP",  1000.0),
}


def get_connection():
    try:
        from database_adapter import get_connection as _get_conn
        return _get_conn()
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)


def discover_tables(prefix: str):
    """Read the bot's own db.py to find every table it owns.

    Avoids hardcoding table names so this script stays correct if a bot
    adds a new per-bot table later.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "trading", f"{prefix}", "db.py")
    tables = []
    try:
        with open(db_path, encoding="utf-8") as f:
            src = f.read()
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)", src):
            name = m.group(1)
            if name.startswith(prefix) and name not in tables:
                tables.append(name)
    except FileNotFoundError:
        print(f"  WARNING: {db_path} not found, cannot discover tables for {prefix}")
    return tables


def get_configured_mode(cursor, bot_name: str) -> str:
    """PAPER unless autonomous_config explicitly says LIVE (matches
    AgapeXxxPerpConfig.mode's own PAPER default when unset)."""
    key = f"{bot_name.lower()}_mode"
    try:
        cursor.execute("SELECT value FROM autonomous_config WHERE key = %s", (key,))
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0]).strip().lower()
    except Exception as e:
        print(f"  WARNING: could not read {key}: {e}")
    return "paper"


def get_starting_capital(cursor, bot_name: str, default_capital: float) -> float:
    key = f"{bot_name.lower()}_starting_capital"
    try:
        cursor.execute("SELECT value FROM autonomous_config WHERE key = %s", (key,))
        row = cursor.fetchone()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return default_capital


def table_count(cursor, table: str) -> int:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except Exception:
        return -1  # table doesn't exist yet


def check_all_paper(cursor) -> bool:
    print("Checking every bot is configured PAPER before touching anything...")
    all_paper = True
    for ticker, (prefix, bot_name, _cap) in BOTS.items():
        mode = get_configured_mode(cursor, bot_name)
        ok = mode == "paper"
        print(f"  {ticker:5s} ({bot_name}): mode={mode} [{'OK' if ok else 'REFUSING - NOT PAPER'}]")
        if not ok:
            all_paper = False
    return all_paper


def run(execute: bool):
    conn = get_connection()
    cursor = conn.cursor()

    if not check_all_paper(cursor):
        print()
        print("ABORT: at least one bot is not configured PAPER. Refusing to reset")
        print("any account data. This script never touches a LIVE account.")
        cursor.close()
        conn.close()
        sys.exit(1)

    print()
    print("=" * 78)
    print(f"AGAPE PERP PAPER ACCOUNT RESET  ({'EXECUTE' if execute else 'DRY RUN - no changes'})")
    print(f"Archive suffix: _{ARCHIVE_SUFFIX}")
    print(f"Timestamp: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 78)

    for ticker, (prefix, bot_name, default_capital) in BOTS.items():
        tables = discover_tables(prefix)
        starting_capital = get_starting_capital(cursor, bot_name, default_capital)
        print(f"\n{ticker} ({bot_name}) - starting_capital=${starting_capital:,.2f}")
        if not tables:
            print("  No tables discovered - skipping.")
            continue

        before_counts = {t: table_count(cursor, t) for t in tables}
        for t, c in before_counts.items():
            print(f"  {t}: {c if c >= 0 else 'MISSING'} rows before")

        if not execute:
            print("  (dry run - would archive to *_"
                  f"{ARCHIVE_SUFFIX} and DELETE all rows from the tables above)")
            continue

        try:
            for t in tables:
                if before_counts.get(t, -1) < 0:
                    continue  # table doesn't exist, nothing to archive/delete
                archive_table = f"{t}_{ARCHIVE_SUFFIX}"
                cursor.execute(f"DROP TABLE IF EXISTS {archive_table}")
                cursor.execute(f"CREATE TABLE {archive_table} AS SELECT * FROM {t}")
                cursor.execute(f"DELETE FROM {t}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  ERROR - transaction rolled back for {ticker}: {e}")
            continue

        after_counts = {t: table_count(cursor, t) for t in tables}
        for t in tables:
            b = before_counts.get(t, -1)
            a = after_counts.get(t, -1)
            status = "OK" if a == 0 else "WARN"
            print(f"  {t}: BEFORE={b} -> AFTER={a} [{status}] (archived to {t}_{ARCHIVE_SUFFIX})")

    cursor.close()
    conn.close()

    print()
    print("=" * 78)
    if execute:
        print("RESET COMPLETE. Each account restarts at its configured starting_capital")
        print("with zero positions on the next scan cycle after a worker restart.")
    else:
        print("DRY RUN COMPLETE. Re-run with --execute to actually archive + reset.")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(
        description="Archive and reset the 7 AGAPE perpetual PAPER accounts",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually archive + delete rows. Without this flag, only prints counts.",
    )
    args = parser.parse_args()
    run(execute=args.execute)


if __name__ == "__main__":
    main()
