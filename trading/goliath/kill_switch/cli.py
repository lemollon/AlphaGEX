"""CLI for GOLIATH kill-switch manual override.

Per kickoff prompt: manual override requires --confirm-leron-override
(paranoia flag) so an accidental keystroke can't unkill production.

Usage:
    python -m trading.goliath.kill_switch.cli list-kills
    python -m trading.goliath.kill_switch.cli override-kill \\
        --scope INSTANCE --instance GOLIATH-MSTU \\
        --by leron --confirm-leron-override
    python -m trading.goliath.kill_switch.cli override-kill \\
        --scope PLATFORM --by leron --confirm-leron-override
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.kill_switch import (  # noqa: E402
    KillScope,
    clear_kill,
    list_active_kills,
)


def _cmd_list(_args: argparse.Namespace) -> int:
    rows = list_active_kills()
    if not rows:
        print("(no active kills)")
        return 0
    print(json.dumps(rows, indent=2, default=str))
    return 0


def _cmd_override(args: argparse.Namespace) -> int:
    if not args.confirm_leron_override:
        print(
            "REFUSED: --confirm-leron-override is required for manual kill override "
            "(paranoia gate; spec section 6).",
            file=sys.stderr,
        )
        return 2

    scope = args.scope.upper()
    if scope not in (KillScope.INSTANCE.value, KillScope.PLATFORM.value):
        print(f"Invalid scope: {args.scope}", file=sys.stderr)
        return 2

    instance_name = args.instance.upper() if args.instance else None
    if scope == "INSTANCE" and not instance_name:
        print("--instance required when --scope INSTANCE", file=sys.stderr)
        return 2
    if scope == "PLATFORM" and instance_name:
        print("--instance not allowed when --scope PLATFORM", file=sys.stderr)
        return 2

    cleared = clear_kill(scope, instance_name, cleared_by=args.by)
    if not cleared:
        print(
            f"NOOP: no active kill on {scope}"
            + (f"/{instance_name}" if instance_name else ""),
        )
        return 0
    print(
        f"OK cleared {scope}"
        + (f"/{instance_name}" if instance_name else "")
        + f" by {args.by}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="goliath.kill_switch.cli",
        description="GOLIATH kill-switch manual override CLI.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-kills").set_defaults(func=_cmd_list)

    ov = sub.add_parser("override-kill", help="Clear an active kill (manual)")
    ov.add_argument("--scope", required=True, choices=["INSTANCE", "PLATFORM",
                                                        "instance", "platform"])
    ov.add_argument("--instance", default=None,
                    help="LETF instance (e.g. GOLIATH-MSTU); required for INSTANCE scope")
    ov.add_argument("--by", required=True, help="Audit field for who is overriding")
    ov.add_argument(
        "--confirm-leron-override",
        action="store_true",
        help="Required paranoia flag; without it the override is refused.",
    )
    ov.set_defaults(func=_cmd_override)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
