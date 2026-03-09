"""
SpreadWorks Discord Daily Bot
Posts daily market open/close messages + economic event countdowns to Discord.

Schedule (US Central, DST-aware via TZ=America/Chicago):
  8:25 AM CT  — Market Open message (Bible verse + spread trading tip)
  8:30 AM CT  — Economic event countdown
  3:00 PM CT  — Market Close message

Usage:
  python main.py           # Run scheduler (production)
  python main.py --test    # Fire all 3 posts immediately (testing)

Environment:
  DISCORD_WEBHOOK_URL  — Discord webhook URL (required)
  TZ                   — Must be set to America/Chicago on Render
"""

import os
import sys
import time
import json
import logging
import argparse
import requests
import pytz
import schedule
from datetime import datetime

# Add script directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verses import VERSES
from tips import TIPS
from close_messages import CLOSE_MESSAGES
from economic_events import (
    ECONOMIC_EVENTS_2026,
    MARKET_HOLIDAYS_2026,
    get_central_now,
    get_todays_events,
    get_next_event,
    get_upcoming_events,
    format_countdown,
    format_event_time,
    is_market_holiday,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://spreadworks-backend.onrender.com")

CT = pytz.timezone("America/Chicago")

# Embed colors
COLOR_GREEN = 0x00E676   # Market open
COLOR_BLUE = 0x448AFF    # Market close
COLOR_RED = 0xFF1744     # HIGH impact event
COLOR_YELLOW = 0xFFD600  # MEDIUM impact event
COLOR_LIGHT_BLUE = 0x448AFF  # LOW impact event

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("spreadworks-bot")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_weekday():
    """True if today is Mon-Fri in Central time."""
    return get_central_now().weekday() < 5


def is_trading_day():
    """True if today is a weekday and not a market holiday."""
    now = get_central_now()
    return now.weekday() < 5 and not is_market_holiday(now.date())


def get_rotation_index(items, offset=0):
    """
    Deterministic daily rotation based on day-of-year.
    Same day always returns the same index. Cycles through all items
    before repeating (modulo len).
    """
    day_of_year = get_central_now().timetuple().tm_yday
    return (day_of_year + offset) % len(items)


def send_webhook(embed: dict):
    """Send a single embed to Discord webhook. Retries on network errors."""
    if not WEBHOOK_URL:
        log.error("DISCORD_WEBHOOK_URL not set — skipping send")
        return False

    payload = {"embeds": [embed]}
    retries = 3
    for attempt in range(retries):
        try:
            resp = requests.post(
                WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 429:
                # Rate limited — wait and retry
                retry_after = resp.json().get("retry_after", 5)
                log.warning(f"Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            log.info(f"Webhook sent successfully (status {resp.status_code})")
            return True
        except requests.RequestException as e:
            log.error(f"Webhook attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))  # Exponential backoff: 2, 4s
    return False


def impact_color(impact: str) -> int:
    """Return embed color based on event impact level."""
    return {
        "HIGH": COLOR_RED,
        "MEDIUM": COLOR_YELLOW,
        "LOW": COLOR_LIGHT_BLUE,
    }.get(impact, COLOR_BLUE)


# ---------------------------------------------------------------------------
# Post Functions
# ---------------------------------------------------------------------------

def post_market_open():
    """8:25 AM CT — Bible verse + spread trading tip."""
    if not is_trading_day():
        log.info("Not a trading day — skipping market open post")
        return

    now = get_central_now()
    verse = VERSES[get_rotation_index(VERSES)]
    tip = TIPS[get_rotation_index(TIPS, offset=37)]

    embed = {
        "title": "\U0001f305 MARKET OPENS IN 5 MINUTES",
        "color": COLOR_GREEN,
        "fields": [
            {
                "name": f"\U0001f4d6 {verse['reference']}",
                "value": f"*\"{verse['text']}\"*",
                "inline": False,
            },
            {
                "name": "\U0001f4ca SPREAD TRADER TIP",
                "value": tip,
                "inline": False,
            },
        ],
        "footer": {
            "text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Good luck today. Trade with discipline."
        },
        "timestamp": now.isoformat(),
    }
    send_webhook(embed)
    log.info("Market open post sent")


def post_economic_countdown():
    """8:30 AM CT — Economic event countdown."""
    if not is_trading_day():
        log.info("Not a trading day — skipping economic countdown post")
        return

    now = get_central_now()
    today_date = now.date()

    # Check for events TODAY
    todays_events = get_todays_events(today_date)
    if todays_events:
        for event in todays_events:
            event_time = format_event_time(event["datetime"])
            embed = {
                "title": "\u26a1 ECONOMIC EVENT TODAY",
                "color": impact_color(event["impact"]),
                "fields": [
                    {
                        "name": f"\U0001f4c5 {event['name']}",
                        "value": f"**{event_time}**\n{event['description']}",
                        "inline": False,
                    },
                    {
                        "name": f"Impact: **{event['impact']}**",
                        "value": "\U0001f4a1 Consider closing or hedging positions before this event.\nIV often spikes 30 min before major releases.",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"
                },
                "timestamp": now.isoformat(),
            }
            send_webhook(embed)
        log.info(f"Posted {len(todays_events)} today's event(s)")
        return

    # Check for events within next 7 days
    upcoming = get_upcoming_events(days=7, count=3)
    if upcoming:
        fields = []
        for event in upcoming:
            countdown = format_countdown(event["datetime"])
            event_time = format_event_time(event["datetime"])
            fields.append({
                "name": f"\U0001f4c5 {event['name']}",
                "value": (
                    f"\U0001f4c6 {event['datetime'].strftime('%A, %b %-d')} at {event_time}\n"
                    f"\u23f3 **{countdown}**\n"
                    f"Impact: **{event['impact']}**"
                ),
                "inline": False,
            })

        embed = {
            "title": "\U0001f4c5 NEXT MAJOR ECONOMIC EVENTS",
            "color": impact_color(upcoming[0]["impact"]),
            "fields": fields,
            "footer": {
                "text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"
            },
            "timestamp": now.isoformat(),
        }
        send_webhook(embed)
        log.info(f"Posted upcoming events countdown ({len(upcoming)} events)")
    else:
        # No events within 7 days — skip post entirely
        log.info("No economic events within 7 days — skipping countdown post")


def post_open_positions_summary():
    """8:25 AM CT — Post open positions summary if any exist."""
    if not is_trading_day():
        return
    try:
        resp = requests.post(f"{BACKEND_URL}/api/spreadworks/discord/post-open", timeout=15)
        if resp.ok:
            data = resp.json()
            log.info(f"Open positions summary posted ({data.get('positions', 0)} positions)")
        else:
            log.info("No open positions or post failed")
    except Exception as e:
        log.error(f"Failed to post open positions summary: {e}")


def mark_all_positions():
    """3:00 PM CT — EOD mark all open positions."""
    if not is_trading_day():
        return
    try:
        resp = requests.post(f"{BACKEND_URL}/api/spreadworks/positions/mark", timeout=30)
        if resp.ok:
            data = resp.json()
            log.info(f"Marked {data.get('marked', 0)} positions at ${data.get('spot_price', '?')}")
        else:
            log.warning(f"Position mark failed: {resp.status_code}")
    except Exception as e:
        log.error(f"Failed to mark positions: {e}")


def post_eod_update():
    """3:05 PM CT — Post EOD summary with AI commentary."""
    if not is_trading_day():
        return
    try:
        resp = requests.post(f"{BACKEND_URL}/api/spreadworks/discord/post-eod", timeout=60)
        if resp.ok:
            data = resp.json()
            log.info(
                f"EOD update posted ({data.get('positions', 0)} positions, "
                f"unrealized: ${data.get('total_unrealized', 0):+,.2f})"
            )
        else:
            log.info("No open positions or EOD post failed")
    except Exception as e:
        log.error(f"Failed to post EOD update: {e}")


def post_market_close():
    """3:00 PM CT — Market close reflection."""
    if not is_trading_day():
        log.info("Not a trading day — skipping market close post")
        return

    now = get_central_now()
    close_msg = CLOSE_MESSAGES[get_rotation_index(CLOSE_MESSAGES, offset=71)]

    embed = {
        "title": "\U0001f514 MARKET CLOSED",
        "color": COLOR_BLUE,
        "fields": [
            {
                "name": "\U0001f4ad Closing Thought",
                "value": close_msg,
                "inline": False,
            },
            {
                "name": "\U0001f4cb End of Day Checklist",
                "value": (
                    "\u2022 Review your positions and open orders\n"
                    "\u2022 Log your trades in your journal\n"
                    "\u2022 Check tomorrow's economic calendar\n"
                    "\u2022 Set alerts for key levels\n"
                    "\u2022 Rest well \u2014 tomorrow is a new day"
                ),
                "inline": False,
            },
        ],
        "footer": {
            "text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Rest up. Trade tomorrow."
        },
        "timestamp": now.isoformat(),
    }
    send_webhook(embed)
    log.info("Market close post sent")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def setup_schedule():
    """
    Configure the daily schedule.

    IMPORTANT: The `schedule` library uses local system time.
    On Render, set TZ=America/Chicago so system clock = Central Time.
    This makes schedule times automatically DST-aware.
    """
    schedule.every().day.at("08:25").do(post_market_open)
    schedule.every().day.at("08:25").do(post_open_positions_summary)
    schedule.every().day.at("08:30").do(post_economic_countdown)
    schedule.every().day.at("15:00").do(mark_all_positions)
    schedule.every().day.at("15:00").do(post_market_close)
    schedule.every().day.at("15:05").do(post_eod_update)
    log.info("Schedule configured: 08:25 (open+positions), 08:30 (events), 15:00 (close+mark), 15:05 (EOD) CT")


def run_test():
    """Fire all 3 posts immediately for testing."""
    log.info("=== TEST MODE: Firing all posts now ===")
    log.info(f"Current Central time: {get_central_now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info(f"Verses loaded: {len(VERSES)}")
    log.info(f"Tips loaded: {len(TIPS)}")
    log.info(f"Close messages loaded: {len(CLOSE_MESSAGES)}")
    log.info(f"Economic events loaded: {len(ECONOMIC_EVENTS_2026)}")
    log.info("")

    log.info("--- Sending Market Open ---")
    post_market_open()
    time.sleep(1)  # Small delay between posts

    log.info("--- Sending Economic Countdown ---")
    post_economic_countdown()
    time.sleep(1)

    log.info("--- Sending Market Close ---")
    post_market_close()

    log.info("=== TEST COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(description="SpreadWorks Discord Daily Bot")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Fire all 3 posts immediately (test mode)",
    )
    args = parser.parse_args()

    if not WEBHOOK_URL:
        log.error("DISCORD_WEBHOOK_URL environment variable is not set!")
        log.error("Set it with: export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'")
        sys.exit(1)

    log.info(f"SpreadWorks Discord Bot starting...")
    log.info(f"  Timezone: {get_central_now().strftime('%Z')} (America/Chicago)")
    log.info(f"  Verses:   {len(VERSES)}")
    log.info(f"  Tips:     {len(TIPS)}")
    log.info(f"  Close:    {len(CLOSE_MESSAGES)}")
    log.info(f"  Events:   {len(ECONOMIC_EVENTS_2026)}")

    if args.test:
        run_test()
        return

    setup_schedule()
    log.info("Bot running. Waiting for scheduled times...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
