"""CLI for GOLIATH management actions (T6 material-news flag).

Per Leron Q5 (2026-04-29): material-news flagging is a manual CLI
action on the Render shell. This module is the user-facing surface.

Usage:
    python -m trading.goliath.management.cli flag-news TSLA --reason "FDA news"
    python -m trading.goliath.management.cli unflag-news TSLA
    python -m trading.goliath.management.cli list-flags

The CLI talks to news_flag_store (Postgres-backed). Exit 0 on success,
1 on DB unavailability or unknown command.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure repo root is on sys.path when invoked as `python -m`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.management import news_flag_store  # noqa: E402


def _cmd_flag(args: argparse.Namespace) -> int:
    ok = news_flag_store.flag_ticker(
        ticker=args.ticker.upper(),
        reason=args.reason or "",
        flagged_by=args.by or "cli",
    )
    if not ok:
        print(f"FAIL: could not flag {args.ticker} (DB unavailable?)", file=sys.stderr)
        return 1
    print(f"OK flagged {args.ticker.upper()}")
    return 0


def _cmd_unflag(args: argparse.Namespace) -> int:
    deleted = news_flag_store.unflag_ticker(args.ticker.upper())
    if deleted:
        print(f"OK unflagged {args.ticker.upper()}")
        return 0
    print(f"NOOP no active flag for {args.ticker.upper()}")
    return 0  # not an error; idempotent


def _cmd_list(_args: argparse.Namespace) -> int:
    rows = news_flag_store.list_flagged_tickers()
    if not rows:
        print("(no active flags)")
        return 0
    print(json.dumps(rows, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goliath.management.cli",
        description="GOLIATH management CLI (material-news flag).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    flag = sub.add_parser("flag-news", help="Set material-news flag on a ticker")
    flag.add_argument("ticker", help="Underlying ticker (e.g. TSLA)")
    flag.add_argument("--reason", default="", help="Optional reason text")
    flag.add_argument("--by", default="cli", help="Audit field for who flagged")
    flag.set_defaults(func=_cmd_flag)

    un = sub.add_parser("unflag-news", help="Clear flag on a ticker")
    un.add_argument("ticker")
    un.set_defaults(func=_cmd_unflag)

    lst = sub.add_parser("list-flags", help="Show all active flags")
    lst.set_defaults(func=_cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
