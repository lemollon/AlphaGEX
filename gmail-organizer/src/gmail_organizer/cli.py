"""Command-line interface for Gmail Organizer."""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .auth import get_gmail_service
from .organizer import GmailOrganizer
from .rules_loader import load_rules


def main():
    parser = argparse.ArgumentParser(
        description="Organize your Gmail inbox using configurable rules."
    )
    parser.add_argument(
        "--version", action="version", version=f"gmail-organizer {__version__}"
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("config/rules.yaml"),
        help="Path to rules YAML file (default: config/rules.yaml)",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path("config/credentials.json"),
        help="Path to OAuth2 credentials file (default: config/credentials.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without applying them",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of emails to process (default: 100)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("gmail_organizer")

    # Load rules
    rule_set = load_rules(args.rules)
    enabled_count = len(rule_set.get_enabled_rules())

    if enabled_count == 0:
        logger.warning("No enabled rules found. Nothing to do.")
        sys.exit(0)

    logger.info("Loaded %d enabled rules", enabled_count)

    # Authenticate
    try:
        service = get_gmail_service(credentials_path=args.credentials)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # Run organizer
    organizer = GmailOrganizer(service, rule_set)
    summary = organizer.organize(dry_run=args.dry_run)

    # Print summary
    total_matched = sum(v["matched"] for v in summary.values())
    total_acted = sum(len(v["actions"]) for v in summary.values())

    print(f"\n{'=' * 40}")
    print(f"Gmail Organizer - {'DRY RUN' if args.dry_run else 'COMPLETE'}")
    print(f"{'=' * 40}")

    for rule_name, result in summary.items():
        status = f"  {rule_name}: {result['matched']} matched"
        if not args.dry_run:
            status += f", {len(result['actions'])} processed"
        print(status)

    print(f"\nTotal: {total_matched} matched, {total_acted} processed")


if __name__ == "__main__":
    main()
