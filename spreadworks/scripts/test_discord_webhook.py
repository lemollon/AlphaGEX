"""Quick standalone test for Discord webhook — run locally before deploying.

Usage:
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... \
        python spreadworks/scripts/test_discord_webhook.py

The webhook URL MUST be supplied via the DISCORD_WEBHOOK_URL environment
variable. Never hard-code or commit a webhook URL — anyone with the URL can
post to your channel, and public scanners (E.O.S, GitHub secret scanning)
will detect and abuse it within minutes.
"""

import os
import sys
import requests

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
if not WEBHOOK_URL:
    print(
        "ERROR: DISCORD_WEBHOOK_URL is not set.\n"
        "Set it in your shell before running:\n"
        "    export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/<id>/<token>'\n"
        "Then re-run this script.",
        file=sys.stderr,
    )
    sys.exit(2)

embed = {
    "title": "\U0001f7e2 SPY DD · #1 DD",
    "color": 0x00E676,
    "fields": [
        {
            "name": "Strikes",
            "value": "LP `658.5` · SP `663.5` · SC `677` · LC `682`",
            "inline": False,
        },
        {"name": "Short Exp", "value": "2026-03-13", "inline": True},
        {"name": "Long Exp", "value": "2026-03-20", "inline": True},
        {"name": "DTE", "value": "4", "inline": True},
        {"name": "Entry Credit", "value": "+$343.54", "inline": True},
        {"name": "Current Value", "value": "$-3.4345", "inline": True},
        {"name": "Unrealized P&L", "value": "+$686.99 (+189.7%)", "inline": True},
        {"name": "Max Profit", "value": "$362.24", "inline": True},
        {"name": "Max Loss", "value": "$-771.32", "inline": True},
        {"name": "Contracts", "value": "1", "inline": True},
    ],
    "footer": {"text": "SpreadWorks · Opened 2026-03-09"},
}

# Print only the host + first segment, never the full token
print(f"Posting to: {WEBHOOK_URL.split('/')[2]}/.../<redacted>")
try:
    resp = requests.post(
        WEBHOOK_URL,
        json={"embeds": [embed]},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code in (200, 204):
        print("SUCCESS — check your Discord channel!")
    else:
        print(f"FAILED: {resp.text[:300]}")
        sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
