"""Quick standalone test for Discord webhook — run locally before deploying.

Usage:
    python spreadworks/scripts/test_discord_webhook.py
"""

import os
import sys
import requests

WEBHOOK_URL = (
    os.getenv("DISCORD_WEBHOOK_URL")
    or "https://discord.com/api/webhooks/1480368391817789656/sPPQs2n1VUQiBdolb2VRq3Db7a3T3ZmYrLML5ODKMlAsS5sodac839jeHIFqjix2g9Xd"
)

embed = {
    "title": "\U0001f7e2 SPY DD \u00b7 #1 DD",
    "color": 0x00E676,
    "fields": [
        {
            "name": "Strikes",
            "value": "LP `658.5` \u00b7 SP `663.5` \u00b7 SC `677` \u00b7 LC `682`",
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
    "footer": {"text": "SpreadWorks \u00b7 Opened 2026-03-09"},
}

print(f"Posting to: {WEBHOOK_URL[:60]}...")
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
