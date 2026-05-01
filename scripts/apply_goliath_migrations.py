#!/usr/bin/env python3
"""Apply GOLIATH database migrations idempotently.

Reads ``DATABASE_URL`` from the environment (already set on every
alphagex-* Render service) so there is NO credential pasting. Just
shell into any Render service that has DB access and run:

    python scripts/apply_goliath_migrations.py

The script applies all ``db/migrations/0*_goliath_*.sql`` files in
sorted order. Migrations use ``CREATE TABLE IF NOT EXISTS`` /
``CREATE INDEX IF NOT EXISTS`` so re-running is safe -- already-applied
migrations are no-ops.

Per migration:
  - reads the .sql file
  - executes it inside a single transaction
  - prints a one-line summary
  - on error: rolls back, prints the error, continues to the next file

Exit code 0 if all migrations succeeded; 1 if any failed.

Usage:
    python scripts/apply_goliath_migrations.py
    python scripts/apply_goliath_migrations.py --only 032
    python scripts/apply_goliath_migrations.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = _REPO_ROOT / "db" / "migrations"


def _discover_migrations(only: Optional[str] = None) -> List[Path]:
    """Return GOLIATH migration files in sorted order. Filters to ``only``
    prefix when set (e.g. ``032`` matches ``032_goliath_paper_positions.sql``).
    """
    if not _MIGRATIONS_DIR.is_dir():
        print(f"FATAL: migrations dir not found at {_MIGRATIONS_DIR}", file=sys.stderr)
        return []

    candidates = sorted(_MIGRATIONS_DIR.glob("*_goliath_*.sql"))
    if only:
        candidates = [p for p in candidates if p.name.startswith(only)]
    return candidates


def _apply_one(conn, path: Path, dry_run: bool) -> bool:
    sql = path.read_text()
    label = path.name

    if dry_run:
        print(f"[dry-run] would apply {label} ({len(sql)} chars)")
        return True

    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        print(f"  applied {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"  FAILED {label}: {exc!r}", file=sys.stderr)
        return False
    finally:
        cur.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only",
        default=None,
        help="Apply only migrations whose filename starts with this prefix "
             "(e.g. '032' to apply just goliath_paper_positions).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List migrations that would be applied, but don't run them.",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print(
            "FATAL: DATABASE_URL not set. On Render, this is auto-provided "
            "by the alphagex-db blueprint binding. On local dev, export it "
            "explicitly before running.",
            file=sys.stderr,
        )
        return 1

    migrations = _discover_migrations(only=args.only)
    if not migrations:
        print(f"No migrations found (only={args.only!r}).")
        return 0

    print(f"Found {len(migrations)} GOLIATH migration(s):")
    for p in migrations:
        print(f"  - {p.name}")
    print()

    if args.dry_run:
        print("DRY-RUN: connection skipped, no migrations applied.")
        return 0

    try:
        import psycopg2  # type: ignore
    except ImportError as exc:
        print(f"FATAL: psycopg2 unavailable: {exc!r}", file=sys.stderr)
        return 1

    try:
        conn = psycopg2.connect(url, connect_timeout=30, sslmode="require")
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: connection failed: {exc!r}", file=sys.stderr)
        return 1

    failures = 0
    try:
        for path in migrations:
            if not _apply_one(conn, path, args.dry_run):
                failures += 1
    finally:
        conn.close()

    print()
    if failures == 0:
        print(f"OK: {len(migrations)} migration(s) applied (or already in place).")
        return 0
    print(f"FAIL: {failures}/{len(migrations)} migration(s) errored.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
