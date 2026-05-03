"""SpreadWorks backend — FastAPI application."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the spreadworks/ root (one level up from backend/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routes import router
from .db import engine, Base
from . import models  # noqa: F401 — register models with Base

logger = logging.getLogger("spreadworks")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Resolve frontend dist — try relative to __file__ first, then CWD fallback
_dist_candidates = [
    Path(__file__).resolve().parent.parent / "frontend" / "dist",
    Path.cwd() / "frontend" / "dist",
    Path("/opt/render/project/src/spreadworks/frontend/dist"),
]
FRONTEND_DIST = next((p for p in _dist_candidates if p.exists()), _dist_candidates[0])

# Log at import time so we can see in Render logs
print(f"[SpreadWorks] __file__ = {__file__}")
print(f"[SpreadWorks] CWD = {Path.cwd()}")
print(f"[SpreadWorks] FRONTEND_DIST = {FRONTEND_DIST}")
print(f"[SpreadWorks] FRONTEND_DIST.exists() = {FRONTEND_DIST.exists()}")
if FRONTEND_DIST.exists():
    contents = list(FRONTEND_DIST.iterdir())
    print(f"[SpreadWorks] dist contents: {contents}")
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        print(f"[SpreadWorks] assets contents: {list(assets.iterdir())}")
else:
    print(f"[SpreadWorks] WARNING: dist NOT found at any candidate path:")
    for p in _dist_candidates:
        print(f"[SpreadWorks]   {p} -> exists={p.exists()}")


def _send_webhook_sync(embed: dict) -> bool:
    """Send a single embed to Discord webhook (sync, for scheduler use)."""
    import requests as req

    url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        logger.warning("[SpreadWorks] DISCORD_WEBHOOK_URL not set — skipping")
        return False

    import time as _time
    for attempt in range(3):
        try:
            resp = req.post(url, json={"embeds": [embed]},
                            headers={"Content-Type": "application/json"}, timeout=15)
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                logger.warning(f"[SpreadWorks] Rate limited, waiting {retry_after}s")
                _time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[SpreadWorks] Webhook attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                _time.sleep(2 ** (attempt + 1))
    return False


_active_scheduler = None  # singleton guard — only one scheduler per process
_last_posted = {}  # in-process fast-path: {message_key: timestamp}


def _claim_post_slot_db(key: str, fire_date) -> bool:
    """Atomically claim a (key, fire_date) slot in the DB.

    Uses INSERT ... ON CONFLICT DO NOTHING so only ONE process — even across
    multiple uvicorn workers, multiple Render replicas, or overlapping
    deploys — successfully claims the slot. Returns True iff this caller
    inserted the row (i.e. is the unique poster for that day).

    Falls back to True if the DB is unavailable, so a misconfigured env
    doesn't silently kill all scheduled messages.
    """
    try:
        from .db import SessionLocal
        from sqlalchemy import text as sa_text
    except Exception:
        return True
    if SessionLocal is None:
        return True
    db = SessionLocal()
    try:
        result = db.execute(
            sa_text(
                "INSERT INTO discord_post_log (message_key, fire_date) "
                "VALUES (:k, :d) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "d": fire_date},
        )
        db.commit()
        # rowcount is 1 if we inserted, 0 if another process already had the slot
        claimed = (result.rowcount or 0) > 0
        if not claimed:
            logger.warning(
                f"[SpreadWorks] Dedup blocked (DB): another process already posted {key} for {fire_date}"
            )
        return claimed
    except Exception as e:
        # Don't crash the scheduler if the table is missing on first deploy
        logger.error(f"[SpreadWorks] Dedup DB claim failed for {key}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return True
    finally:
        db.close()


def _dedup_ok(key: str, cooldown_seconds: int = 300, fire_date=None) -> bool:
    """Return True if this message hasn't been posted recently AND we win
    the cross-process race for today's slot.

    Two-layer guard:
      1. In-memory cooldown — fast, prevents the same process from posting
         twice within `cooldown_seconds` (e.g. APScheduler misfire bursts).
      2. DB unique slot — survives restarts, multiple workers, and
         multi-replica deploys. THIS is what stops the duplicate-message
         bug we saw on the Sat 10:00 weekend playbook.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    last = _last_posted.get(key)
    if last and (now - last).total_seconds() < cooldown_seconds:
        logger.warning(
            f"[SpreadWorks] Dedup blocked (mem): {key} posted "
            f"{(now - last).total_seconds():.0f}s ago"
        )
        return False

    # Daily DB slot — default to today's CT date if caller didn't pass one
    if fire_date is None:
        try:
            from .economic_events import get_central_now
            fire_date = get_central_now().date()
        except Exception:
            from zoneinfo import ZoneInfo
            fire_date = datetime.now(ZoneInfo("America/Chicago")).date()

    if not _claim_post_slot_db(key, fire_date):
        return False

    _last_posted[key] = now
    return True


def _start_scheduler(app: FastAPI):
    """Start APScheduler for market open/close Discord posts (Central Time)."""
    global _active_scheduler
    if _active_scheduler is not None:
        logger.warning("[SpreadWorks] Scheduler already running — skipping duplicate start")
        return _active_scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("[SpreadWorks] apscheduler not installed — Discord scheduler disabled")
        return None

    # Import content modules
    try:
        from .verses import VERSES
        from .tips import TIPS
        from .close_messages import CLOSE_MESSAGES
        from .economic_events import (
            get_central_now, is_market_holiday,
            get_todays_events, get_upcoming_events,
            format_countdown, format_event_time,
        )
        content_loaded = True
        logger.info(f"[SpreadWorks] Content loaded: {len(VERSES)} verses, {len(TIPS)} tips, {len(CLOSE_MESSAGES)} close messages")
    except ImportError as e:
        logger.warning(f"[SpreadWorks] Content modules not found — rich posts disabled: {e}")
        content_loaded = False

    scheduler = AsyncIOScheduler(timezone="America/Chicago")

    def _is_trading_day() -> bool:
        """Check if today is a trading day (weekday + not holiday)."""
        if not content_loaded:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo as _ZI
            return _dt.now(_ZI("America/Chicago")).weekday() < 5
        now = get_central_now()
        return now.weekday() < 5 and not is_market_holiday(now.date())

    def _rotation_index(items, offset=0) -> int:
        """Deterministic daily rotation based on day-of-year."""
        if content_loaded:
            day_of_year = get_central_now().timetuple().tm_yday
        else:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo as _ZI
            day_of_year = _dt.now(_ZI("America/Chicago")).timetuple().tm_yday
        return (day_of_year + offset) % len(items)

    def _impact_color(impact: str) -> int:
        return {"HIGH": 0xFF1744, "MEDIUM": 0xFFD600, "LOW": 0x448AFF}.get(impact, 0x448AFF)

    async def _fire_market_open_message():
        """8:00 AM CT — Bible verse + spread trading tip (30 min before open)."""
        if not content_loaded or not _is_trading_day():
            logger.info("[SpreadWorks] Skipping market open message (not trading day or no content)")
            return
        if not _dedup_ok("market_open_msg"):
            return

        import asyncio
        now = get_central_now()
        verse = VERSES[_rotation_index(VERSES)]
        tip = TIPS[_rotation_index(TIPS, offset=37)]

        embed = {
            "title": "\U0001f305 MARKET OPENS IN 30 MINUTES",
            "color": 0x00E676,
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
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Market open message {'sent' if ok else 'FAILED'}")

    async def _fire_economic_countdown():
        """8:05 AM CT — Economic event countdown."""
        if not content_loaded or not _is_trading_day():
            logger.info("[SpreadWorks] Skipping economic countdown (not trading day or no content)")
            return
        if not _dedup_ok("economic_countdown"):
            return

        import asyncio
        now = get_central_now()
        today_date = now.date()

        # Check for events TODAY
        todays_events = get_todays_events(today_date)
        if todays_events:
            for event in todays_events:
                event_time = format_event_time(event["datetime"])
                embed = {
                    "title": "\u26a1 ECONOMIC EVENT TODAY",
                    "color": _impact_color(event["impact"]),
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
                    "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"},
                    "timestamp": now.isoformat(),
                }
                await asyncio.to_thread(_send_webhook_sync, embed)
            logger.info(f"[SpreadWorks] Posted {len(todays_events)} today's economic event(s)")
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
                "color": _impact_color(upcoming[0]["impact"]),
                "fields": fields,
                "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"},
                "timestamp": now.isoformat(),
            }
            await asyncio.to_thread(_send_webhook_sync, embed)
            logger.info(f"[SpreadWorks] Posted upcoming events countdown ({len(upcoming)} events)")
        else:
            logger.info("[SpreadWorks] No economic events within 7 days — skipping")

    async def _fire_open_post():
        """Market open post — 8:00 AM CT = 13:00 or 14:00 UTC depending on DST."""
        if not _dedup_ok("open_post"):
            return
        logger.info("[SpreadWorks] Scheduler firing market open Discord post")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")
                resp = await client.post(f"{base}/api/spreadworks/discord/post-open")
                logger.info(f"[SpreadWorks] Open post response: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"[SpreadWorks] Market open Discord post failed: {e}")

    async def _fire_market_close_message():
        """3:00 PM CT — Market close reflection."""
        if not content_loaded or not _is_trading_day():
            logger.info("[SpreadWorks] Skipping market close message (not trading day or no content)")
            return
        if not _dedup_ok("market_close_msg"):
            return

        import asyncio
        now = get_central_now()
        close_msg = CLOSE_MESSAGES[_rotation_index(CLOSE_MESSAGES, offset=71)]

        embed = {
            "title": "\U0001f514 MARKET CLOSED",
            "color": 0x448AFF,
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
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Market close message {'sent' if ok else 'FAILED'}")

    async def _fire_eod_post():
        """Market close post — 3:00 PM CT = 20:00 or 21:00 UTC depending on DST."""
        if not _dedup_ok("eod_post"):
            return
        logger.info("[SpreadWorks] Scheduler firing EOD Discord post")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")
                resp = await client.post(f"{base}/api/spreadworks/discord/post-eod")
                logger.info(f"[SpreadWorks] EOD post response: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"[SpreadWorks] EOD Discord post failed: {e}")

    # ------------------------------------------------------------------
    # NEW: GEX Briefing — 8:30 AM CT (market open)
    # ------------------------------------------------------------------
    async def _fire_gex_briefing():
        """8:30 AM CT — Morning GEX Briefing with engagement prompt."""
        if not _is_trading_day():
            return
        if not _dedup_ok("gex_briefing"):
            return

        import asyncio
        now = get_central_now() if content_loaded else __import__("datetime").datetime.now(
            __import__("zoneinfo").ZoneInfo("America/Chicago")
        )

        # Fetch GEX from internal API
        gex = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")
                resp = await client.get(f"{base}/api/spreadworks/gex", params={"symbol": "SPY"})
                if resp.status_code == 200:
                    gex = resp.json()
        except Exception as e:
            logger.error(f"[SpreadWorks] GEX briefing fetch failed: {e}")
            return

        if not gex or gex.get("error"):
            logger.info("[SpreadWorks] GEX data unavailable — skipping briefing")
            return

        fp = gex.get("flip_point")
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        regime = gex.get("gamma_regime", "UNKNOWN")
        spot = gex.get("spot_price")
        vix = gex.get("vix")

        # Regime color: green for positive (mean-reverting), red for negative (trending)
        regime_color = 0x00E676 if regime == "POSITIVE" else 0xFF1744 if regime == "NEGATIVE" else 0xFFD600
        regime_emoji = "\U0001f7e2" if regime == "POSITIVE" else "\U0001f534" if regime == "NEGATIVE" else "\U0001f7e1"
        regime_desc = {
            "POSITIVE": "Mean-reverting — dealers dampen moves. ICs are safer.",
            "NEGATIVE": "Momentum — dealers amplify moves. Directional plays favored.",
        }.get(regime, "Neutral — mixed dealer positioning.")

        fields = []
        if spot:
            fields.append({"name": "\U0001f4b0 SPY Spot", "value": f"**${spot:.2f}**", "inline": True})
        if vix is not None:
            vix_label = "LOW" if vix < 15 else "NORMAL" if vix < 22 else "ELEVATED" if vix < 28 else "HIGH"
            fields.append({"name": "\U0001f4ca VIX", "value": f"**{vix:.1f}** ({vix_label})", "inline": True})
        fields.append({"name": f"{regime_emoji} Gamma Regime", "value": f"**{regime}**\n{regime_desc}", "inline": False})
        if fp:
            direction = ""
            if spot and fp:
                diff = spot - fp
                direction = f" (spot {'above' if diff > 0 else 'below'} by ${abs(diff):.1f})"
            fields.append({"name": "\u2696\ufe0f Flip Point", "value": f"**${fp:.0f}**{direction}", "inline": True})
        if cw:
            fields.append({"name": "\U0001f7e2 Call Wall", "value": f"**${cw:.0f}**", "inline": True})
        if pw:
            fields.append({"name": "\U0001f534 Put Wall", "value": f"**${pw:.0f}**", "inline": True})

        # Engagement prompt
        fields.append({
            "name": "\U0001f4ac What's your read today?",
            "value": "React below: \U0001f402 Bull \u2022 \U0001f43b Bear \u2022 \U0001f980 Chop",
            "inline": False,
        })

        embed = {
            "title": "\U0001f4ca MORNING GEX BRIEFING",
            "color": regime_color,
            "fields": fields,
            "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Market Open"},
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] GEX briefing {'sent' if ok else 'FAILED'}")

    # ------------------------------------------------------------------
    # NEW: Midday Pulse Check — 12:00 PM CT
    # ------------------------------------------------------------------
    async def _fire_midday_pulse():
        """12:00 PM CT — Midday market pulse with position P&L and engagement."""
        if not _is_trading_day():
            return
        if not _dedup_ok("midday_pulse"):
            return

        import asyncio
        now = get_central_now() if content_loaded else __import__("datetime").datetime.now(
            __import__("zoneinfo").ZoneInfo("America/Chicago")
        )
        base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")

        # Fetch spot price + GEX
        spot = None
        gex = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                gex_resp = await client.get(f"{base}/api/spreadworks/gex", params={"symbol": "SPY"})
                if gex_resp.status_code == 200:
                    gex = gex_resp.json()
                    spot = gex.get("spot_price")
        except Exception as e:
            logger.error(f"[SpreadWorks] Midday pulse GEX fetch failed: {e}")

        # Fetch position summary
        summary = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/api/spreadworks/positions/summary")
                if resp.status_code == 200:
                    summary = resp.json()
        except Exception as e:
            logger.error(f"[SpreadWorks] Midday pulse summary fetch failed: {e}")

        # Fetch candle data for daily change
        open_price = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/api/spreadworks/candles", params={"symbol": "SPY", "interval": "15min"})
                if resp.status_code == 200:
                    candle_data = resp.json()
                    candles = candle_data.get("candles", [])
                    if candles:
                        open_price = candles[0].get("open")
        except Exception:
            pass

        fields = []
        if spot:
            change_str = ""
            if open_price and spot:
                chg = spot - open_price
                chg_pct = (chg / open_price) * 100
                arrow = "\u2B06\ufe0f" if chg >= 0 else "\u2B07\ufe0f"
                change_str = f"\n{arrow} **{'+' if chg >= 0 else ''}{chg:.2f}** ({chg_pct:+.2f}%) since open"
            fields.append({
                "name": "\U0001f4b0 SPY Midday",
                "value": f"**${spot:.2f}**{change_str}",
                "inline": False,
            })

        if gex:
            regime = gex.get("gamma_regime", "?")
            fp = gex.get("flip_point")
            regime_emoji = "\U0001f7e2" if regime == "POSITIVE" else "\U0001f534" if regime == "NEGATIVE" else "\U0001f7e1"
            fp_str = f" \u2022 Flip: ${fp:.0f}" if fp else ""
            fields.append({
                "name": "\U0001f30a GEX Regime",
                "value": f"{regime_emoji} **{regime}**{fp_str}",
                "inline": True,
            })

        if summary:
            open_ct = summary.get("open_count", 0)
            unrealized = summary.get("total_unrealized", 0)
            pnl_color = "\U0001f7e2" if unrealized >= 0 else "\U0001f534"
            fields.append({
                "name": "\U0001f4bc Open Positions",
                "value": f"**{open_ct}** position{'s' if open_ct != 1 else ''}\n{pnl_color} Unrealized: **{'+'if unrealized >= 0 else ''}${unrealized:,.0f}**",
                "inline": True,
            })

        fields.append({
            "name": "\U0001f4ac Holding through lunch or taking profits?",
            "value": "Drop your play below \u2935\ufe0f",
            "inline": False,
        })

        color = 0x448AFF
        if spot and open_price:
            color = 0x00E676 if spot >= open_price else 0xFF1744

        embed = {
            "title": "\u2615 MIDDAY PULSE CHECK",
            "color": color,
            "fields": fields,
            "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Halftime"},
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Midday pulse {'sent' if ok else 'FAILED'}")

    # ------------------------------------------------------------------
    # NEW: Position Scoreboard — 3:05 PM CT (after close)
    # ------------------------------------------------------------------
    async def _fire_scoreboard():
        """3:05 PM CT — Weekly scoreboard with win/loss record and streaks."""
        if not _is_trading_day():
            return
        if not _dedup_ok("scoreboard"):
            return

        import asyncio
        from datetime import timedelta
        now = get_central_now() if content_loaded else __import__("datetime").datetime.now(
            __import__("zoneinfo").ZoneInfo("America/Chicago")
        )
        base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")

        # Fetch all closed positions
        closed = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/api/spreadworks/positions", params={"status": "closed"})
                if resp.status_code == 200:
                    data = resp.json()
                    closed = data if isinstance(data, list) else data.get("positions", [])
        except Exception as e:
            logger.error(f"[SpreadWorks] Scoreboard positions fetch failed: {e}")
            return

        if not closed:
            logger.info("[SpreadWorks] No closed positions — skipping scoreboard")
            return

        # Compute stats
        total_pnl = sum(p.get("realized_pnl", 0) or 0 for p in closed)
        wins = [p for p in closed if (p.get("realized_pnl") or 0) > 0]
        losses = [p for p in closed if (p.get("realized_pnl") or 0) <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / len(closed) * 100) if closed else 0

        # This week's trades (Mon-Fri of current week)
        week_start = (now - timedelta(days=now.weekday())).date()
        week_trades = [p for p in closed if p.get("close_date") and str(p["close_date"]) >= str(week_start)]
        week_pnl = sum(p.get("realized_pnl", 0) or 0 for p in week_trades)
        week_wins = len([p for p in week_trades if (p.get("realized_pnl") or 0) > 0])
        week_total = len(week_trades)

        # Current streak (most recent trades)
        sorted_closed = sorted(closed, key=lambda p: p.get("close_date", ""), reverse=True)
        streak = 0
        streak_type = None
        for p in sorted_closed:
            pnl = p.get("realized_pnl") or 0
            current_type = "W" if pnl > 0 else "L"
            if streak_type is None:
                streak_type = current_type
            if current_type == streak_type:
                streak += 1
            else:
                break
        streak_str = f"{'🔥' if streak_type == 'W' else '🧊'} **{streak} {'Win' if streak_type == 'W' else 'Loss'}{'s' if streak > 1 else ''} in a row**"

        # Best & worst trade
        best = max(closed, key=lambda p: p.get("realized_pnl") or 0)
        worst = min(closed, key=lambda p: p.get("realized_pnl") or 0)
        best_pnl = best.get("realized_pnl") or 0
        worst_pnl = worst.get("realized_pnl") or 0

        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        week_emoji = "\U0001f7e2" if week_pnl >= 0 else "\U0001f534"

        fields = [
            {
                "name": "\U0001f4c5 This Week",
                "value": f"**{week_wins}/{week_total}** trades won\n{week_emoji} Week P&L: **{'+'if week_pnl >= 0 else ''}${week_pnl:,.0f}**",
                "inline": True,
            },
            {
                "name": "\U0001f3af All-Time Record",
                "value": f"**{win_count}W / {loss_count}L** ({win_rate:.0f}% WR)\n{pnl_emoji} Total: **{'+'if total_pnl >= 0 else ''}${total_pnl:,.0f}**",
                "inline": True,
            },
            {
                "name": "\U0001f525 Current Streak",
                "value": streak_str,
                "inline": False,
            },
            {
                "name": "\U0001f3c6 Best Trade",
                "value": f"**+${best_pnl:,.0f}** ({best.get('strategy', '?')})",
                "inline": True,
            },
            {
                "name": "\U0001f4a9 Worst Trade",
                "value": f"**-${abs(worst_pnl):,.0f}** ({worst.get('strategy', '?')})",
                "inline": True,
            },
        ]

        embed = {
            "title": "\U0001f3c6 POSITION SCOREBOARD",
            "color": 0x00E676 if total_pnl >= 0 else 0xFF1744,
            "fields": fields,
            "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Market Closed"},
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Scoreboard {'sent' if ok else 'FAILED'}")

    # ------------------------------------------------------------------
    # NEW: Weekend Playbook — Saturday 10:00 AM CT
    # ------------------------------------------------------------------
    async def _fire_weekend_playbook():
        """Saturday 10:00 AM CT — Next week's economic calendar + engagement."""
        if not content_loaded:
            return
        if not _dedup_ok("weekend_playbook"):
            return

        import asyncio
        now = get_central_now()

        # Only fire on Saturday
        if now.weekday() != 5:
            return

        upcoming = get_upcoming_events(days=7, count=5)
        if not upcoming:
            logger.info("[SpreadWorks] No events next week — skipping weekend playbook")
            return

        fields = []
        high_count = 0
        for event in upcoming:
            impact = event.get("impact", "LOW")
            if impact == "HIGH":
                high_count += 1
            emoji = "\U0001f534" if impact == "HIGH" else "\U0001f7e1" if impact == "MEDIUM" else "\U0001f535"
            event_time = format_event_time(event["datetime"])
            fields.append({
                "name": f"{emoji} {event['name']}",
                "value": f"\U0001f4c6 {event['datetime'].strftime('%A, %b %-d')} at {event_time}\nImpact: **{impact}** \u2022 {event['description']}",
                "inline": False,
            })

        # Engagement: ask what they're watching
        fields.append({
            "name": "\U0001f4ac Which event are you watching?",
            "value": "What's your play going into next week? Reply below \u2935\ufe0f",
            "inline": False,
        })

        # Headline color based on week severity
        color = 0xFF1744 if high_count >= 2 else 0xFFD600 if high_count >= 1 else 0x448AFF

        embed = {
            "title": f"\U0001f4cb NEXT WEEK PLAYBOOK \u2022 {high_count} HIGH impact event{'s' if high_count != 1 else ''}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"SpreadWorks \u2022 Week of {now.strftime('%B %d, %Y')} \u2022 Plan your trades, trade your plan."},
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Weekend playbook {'sent' if ok else 'FAILED'}")

    # ------------------------------------------------------------------
    # NEW: Daily One-Month Outlook — every weekday 7:30 AM CT
    # ------------------------------------------------------------------
    async def _fire_monthly_outlook():
        """7:30 AM CT weekdays — rolling 30-day market-moving event outlook.

        Groups upcoming HIGH/MEDIUM events into weekly buckets so traders
        can see the full month at a glance. Complements the Saturday
        weekend playbook (which only covers the next 7 days).
        """
        if not content_loaded or not _is_trading_day():
            return
        if not _dedup_ok("monthly_outlook"):
            return

        import asyncio
        from datetime import timedelta

        now = get_central_now()
        # Pull a generous window of upcoming events (HIGH + MEDIUM only)
        upcoming = get_upcoming_events(days=30, count=40)
        upcoming = [e for e in upcoming if e.get("impact") in ("HIGH", "MEDIUM")]

        if not upcoming:
            logger.info("[SpreadWorks] No upcoming events in 30-day window — skipping monthly outlook")
            return

        # Bucket events by week-of (Monday-anchored, in CT)
        def _week_start(d):
            return (d - timedelta(days=d.weekday())).date()

        buckets = {}
        high_total = 0
        for event in upcoming:
            ws = _week_start(event["datetime"])
            buckets.setdefault(ws, []).append(event)
            if event.get("impact") == "HIGH":
                high_total += 1

        # Pick out THE marquee event (next HIGH-impact catalyst)
        next_high = next((e for e in upcoming if e.get("impact") == "HIGH"), None)

        fields = []
        if next_high:
            countdown = format_countdown(next_high["datetime"])
            fields.append({
                "name": "\U0001f3af Next Major Catalyst",
                "value": (
                    f"**{next_high['name']}**\n"
                    f"\U0001f4c6 {next_high['datetime'].strftime('%A, %b %-d')} at {format_event_time(next_high['datetime'])}\n"
                    f"⏱️ {countdown}\n"
                    f"→ {next_high['description']}"
                ),
                "inline": False,
            })

        # Render up to 4 weekly buckets (covers ~1 month)
        sorted_weeks = sorted(buckets.keys())[:4]
        for ws in sorted_weeks:
            events = buckets[ws]
            week_label = f"Week of {ws.strftime('%b %-d')}"
            lines = []
            for e in events[:6]:  # cap per-week to keep embed under Discord limits
                emoji = "\U0001f534" if e["impact"] == "HIGH" else "\U0001f7e1"
                day = e["datetime"].strftime("%a %-m/%-d")
                t = format_event_time(e["datetime"])
                lines.append(f"{emoji} **{day}** {t} — {e['name']}")
            if len(events) > 6:
                lines.append(f"_+{len(events) - 6} more this week_")
            fields.append({
                "name": f"\U0001f4c5 {week_label}  ({len(events)} event{'s' if len(events) != 1 else ''})",
                "value": "\n".join(lines),
                "inline": False,
            })

        fields.append({
            "name": "\U0001f4a1 Positioning Tip",
            "value": (
                "Long DTE spreads through HIGH events get vol-crushed on release. "
                "Either close before the print or size for a 2x expected move. "
                "Light-week MEDIUM-only stretches are the cleanest theta windows."
            ),
            "inline": False,
        })

        # Color reflects how loaded the next 30 days are
        if high_total >= 4:
            color = 0xFF1744  # red — heavy month
        elif high_total >= 2:
            color = 0xFFD600  # yellow — moderate
        else:
            color = 0x00E676  # green — light

        embed = {
            "title": f"\U0001f5d3️ 30-DAY MARKET OUTLOOK • {high_total} HIGH-impact catalyst{'s' if high_total != 1 else ''}",
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"SpreadWorks • {now.strftime('%A, %B %d, %Y')} • Plan the month, trade the day."
            },
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] Monthly outlook {'sent' if ok else 'FAILED'} ({high_total} HIGH, {len(upcoming)} total)")

    # ------------------------------------------------------------------
    # NEW: GEX Shift Alert — every 5 min during market hours
    # ------------------------------------------------------------------
    _last_flip_point = {"SPY": None}  # in-memory state for comparison

    async def _fire_gex_shift_check():
        """Every 5 min during market hours — check for significant flip point moves."""
        if not _is_trading_day():
            return

        import asyncio
        now = get_central_now() if content_loaded else __import__("datetime").datetime.now(
            __import__("zoneinfo").ZoneInfo("America/Chicago")
        )

        # Only check during market hours (8:30 AM - 3:00 PM CT)
        ct_minutes = now.hour * 60 + now.minute
        if ct_minutes < 510 or ct_minutes > 900:  # 8:30=510, 15:00=900
            return

        base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")
        gex = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/api/spreadworks/gex", params={"symbol": "SPY"})
                if resp.status_code == 200:
                    gex = resp.json()
        except Exception as e:
            logger.error(f"[SpreadWorks] GEX shift check fetch failed: {e}")
            return

        if not gex or gex.get("error"):
            return

        fp = gex.get("flip_point")
        spot = gex.get("spot_price")
        regime = gex.get("gamma_regime")
        if fp is None:
            return

        # Save snapshot to DB for historical tracking
        try:
            from .db import SessionLocal
            from .models import GexSnapshot
            if SessionLocal:
                db = SessionLocal()
                try:
                    snap = GexSnapshot(
                        symbol="SPY",
                        flip_point=fp,
                        call_wall=gex.get("call_wall"),
                        put_wall=gex.get("put_wall"),
                        gamma_regime=regime,
                        spot_price=spot,
                        vix=gex.get("vix"),
                        source=gex.get("source"),
                    )
                    db.add(snap)
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.error(f"[SpreadWorks] GEX snapshot save failed: {e}")

        # Compare with last known flip point
        prev_fp = _last_flip_point.get("SPY")
        _last_flip_point["SPY"] = fp

        if prev_fp is None:
            # First check of the day — no comparison yet
            logger.info(f"[SpreadWorks] GEX shift: initial flip point ${fp:.0f}")
            return

        delta = fp - prev_fp
        if abs(delta) < 3.0:
            return  # Normal movement, no alert

        # Significant shift detected!
        direction = "UP" if delta > 0 else "DOWN"
        arrow = "\u2B06\ufe0f" if delta > 0 else "\u2B07\ufe0f"
        urgency = "\U0001f6a8" if abs(delta) >= 5 else "\u26a0\ufe0f"

        # What it means for trading
        if delta > 0 and regime == "POSITIVE":
            implication = "Dealers shifting higher — resistance moved up. Bullish grind likely."
        elif delta > 0 and regime == "NEGATIVE":
            implication = "Flip rising in negative gamma — could accelerate upward breakout."
        elif delta < 0 and regime == "POSITIVE":
            implication = "Dealers shifting lower — support dropped. Watch for mean-reversion down."
        elif delta < 0 and regime == "NEGATIVE":
            implication = "Flip falling in negative gamma — downside momentum building."
        else:
            implication = "Significant dealer repositioning — reassess your strikes."

        fields = [
            {
                "name": f"{arrow} Flip Point Moved {direction} ${abs(delta):.1f}",
                "value": f"**${prev_fp:.0f}** → **${fp:.0f}**",
                "inline": True,
            },
            {
                "name": "\U0001f4b0 SPY Spot",
                "value": f"**${spot:.2f}**" if spot else "--",
                "inline": True,
            },
            {
                "name": "\U0001f30a Regime",
                "value": f"**{regime or '?'}**",
                "inline": True,
            },
            {
                "name": "\U0001f4a1 What This Means",
                "value": implication,
                "inline": False,
            },
        ]

        color = 0x00E676 if delta > 0 else 0xFF1744

        embed = {
            "title": f"{urgency} GEX SHIFT ALERT \u2022 Flip {direction} ${abs(delta):.1f}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%I:%M %p CT')} \u2022 Check your positions"},
            "timestamp": now.isoformat(),
        }
        ok = await asyncio.to_thread(_send_webhook_sync, embed)
        logger.info(f"[SpreadWorks] GEX SHIFT ALERT: flip {direction} ${abs(delta):.1f} ({'sent' if ok else 'FAILED'})")

    # ==================================================================
    # SCHEDULE ALL JOBS
    # ==================================================================

    # Schedule using direct CT hours — APScheduler handles DST automatically
    # since the scheduler timezone is set to America/Chicago.

    # --- Morning block ---
    # 8:00 CT — Bible verse + tip (30 min before open)
    scheduler.add_job(_fire_market_open_message, "cron", hour=8, minute=0,
                      day_of_week="mon-fri", id="discord_market_open_msg", replace_existing=True)
    # 8:00:30 CT — Open positions summary
    scheduler.add_job(_fire_open_post, "cron", hour=8, minute=0, second=30,
                      day_of_week="mon-fri", id="discord_open", replace_existing=True)
    # 8:05 CT — Economic event countdown
    scheduler.add_job(_fire_economic_countdown, "cron", hour=8, minute=5,
                      day_of_week="mon-fri", id="discord_economic", replace_existing=True)
    # 8:30 CT — GEX Briefing (market open)
    scheduler.add_job(_fire_gex_briefing, "cron", hour=8, minute=30,
                      day_of_week="mon-fri", id="discord_gex_briefing", replace_existing=True)

    # --- Intraday ---
    # 12:00 CT — Midday Pulse Check
    scheduler.add_job(_fire_midday_pulse, "cron", hour=12, minute=0,
                      day_of_week="mon-fri", id="discord_midday_pulse", replace_existing=True)
    # Every 5 min 8:30-15:00 CT — GEX shift detection + snapshot
    scheduler.add_job(_fire_gex_shift_check, "cron", minute="*/5",
                      hour="8-14", day_of_week="mon-fri", id="discord_gex_shift", replace_existing=True)

    # --- Close block ---
    # 15:00 CT — Market close reflection
    scheduler.add_job(_fire_market_close_message, "cron", hour=15, minute=0,
                      day_of_week="mon-fri", id="discord_market_close_msg", replace_existing=True)
    # 15:00:30 CT — EOD summary with AI commentary (right at close)
    scheduler.add_job(_fire_eod_post, "cron", hour=15, minute=0, second=30,
                      day_of_week="mon-fri", id="discord_eod", replace_existing=True)
    # 15:05 CT — Position Scoreboard
    scheduler.add_job(_fire_scoreboard, "cron", hour=15, minute=5,
                      day_of_week="mon-fri", id="discord_scoreboard", replace_existing=True)

    # --- Weekend ---
    # Saturday 10:00 AM CT — Weekend Playbook
    scheduler.add_job(_fire_weekend_playbook, "cron", hour=10, minute=0,
                      day_of_week="sat", id="discord_weekend_playbook", replace_existing=True)

    # --- Daily 30-day outlook ---
    # 7:30 AM CT weekdays — rolling 30-day market-moving event outlook
    scheduler.add_job(_fire_monthly_outlook, "cron", hour=7, minute=30,
                      day_of_week="mon-fri", id="discord_monthly_outlook", replace_existing=True)

    scheduler.start()
    _active_scheduler = scheduler
    logger.info(
        "[SpreadWorks] APScheduler started — 12 jobs: "
        "monthly_outlook (7:30), market_open_msg (8:00), open_positions (8:00:30), "
        "economic (8:05), gex_briefing (8:30), "
        "midday_pulse (12:00), gex_shift (*/5 min), "
        "market_close_msg (15:00), eod (15:00:30), "
        "scoreboard (15:05), weekend_playbook (Sat 10:00) CT"
    )
    return scheduler


def _ensure_schema(eng):
    """Ensure positions/daily_marks tables match the current SQLAlchemy model.

    Uses ALTER TABLE ADD COLUMN IF NOT EXISTS so existing data is never lost.
    Also creates tables from scratch if they don't exist yet.
    """
    from sqlalchemy import text as sa_text

    try:
        with eng.connect() as conn:
            result = conn.execute(sa_text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'positions' AND table_schema = 'public'"
            ))
            existing_cols = {row[0] for row in result}

        if not existing_cols:
            print("[SpreadWorks] Schema: positions table not found, will be created by create_all()")
            return

        print(f"[SpreadWorks] Schema: positions has {len(existing_cols)} columns: {sorted(existing_cols)}")

        # Define every column the model expects with its SQL type and default
        expected_cols = {
            "id":             None,  # PK, always exists
            "symbol":         "VARCHAR(10) NOT NULL DEFAULT 'SPY'",
            "strategy":       "VARCHAR(30) NOT NULL DEFAULT 'double_diagonal'",
            "label":          "VARCHAR(100)",
            "long_put":       "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "short_put":      "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "short_call":     "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "long_call":      "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "short_exp":      "DATE NOT NULL DEFAULT CURRENT_DATE",
            "long_exp":       "DATE",
            "contracts":      "INTEGER NOT NULL DEFAULT 1",
            "entry_credit":   "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "entry_price":    "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "entry_date":     "DATE NOT NULL DEFAULT CURRENT_DATE",
            "entry_spot":     "DOUBLE PRECISION",
            "max_profit":     "DOUBLE PRECISION",
            "max_loss":       "DOUBLE PRECISION",
            "breakeven_low":  "DOUBLE PRECISION",
            "breakeven_high": "DOUBLE PRECISION",
            "notes":          "TEXT",
            "status":         "VARCHAR(10) NOT NULL DEFAULT 'open'",
            "close_date":     "DATE",
            "close_price":    "DOUBLE PRECISION",
            "realized_pnl":   "DOUBLE PRECISION",
            "created_at":     "TIMESTAMPTZ DEFAULT NOW()",
            "updated_at":     "TIMESTAMPTZ DEFAULT NOW()",
        }

        missing = []
        for col_name, col_def in expected_cols.items():
            if col_name not in existing_cols and col_def is not None:
                missing.append((col_name, col_def))

        if not missing:
            print("[SpreadWorks] Schema: positions table has all expected columns ✓")
            return

        print(f"[SpreadWorks] Schema: adding {len(missing)} missing columns: {[m[0] for m in missing]}")
        with eng.begin() as conn:
            for col_name, col_def in missing:
                sql = f"ALTER TABLE positions ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
                print(f"[SpreadWorks] Schema:   {sql}")
                conn.execute(sa_text(sql))
        print(f"[SpreadWorks] Schema: all {len(missing)} columns added successfully ✓")

    except Exception as e:
        print(f"[SpreadWorks] Schema migration error: {e}")
        import traceback
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables if engine is configured
    if engine is not None:
        try:
            # Ensure existing tables have all expected columns (non-destructive)
            _ensure_schema(engine)
            Base.metadata.create_all(bind=engine)
            print("[SpreadWorks] Database tables created/verified")
        except Exception as e:
            print(f"[SpreadWorks] DB table creation failed (non-fatal): {e}")
    else:
        print("[SpreadWorks] DATABASE_URL not set — running without database")

    app.state.http = httpx.AsyncClient(timeout=15.0)

    # Start scheduler for Discord notifications (inside lifespan, not module-level)
    scheduler = _start_scheduler(app)

    yield

    # Shutdown
    global _active_scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        _active_scheduler = None
        logger.info("[SpreadWorks] APScheduler shut down")
    await app.state.http.aclose()


app = FastAPI(title="SpreadWorks", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    from sqlalchemy import text as sa_text
    db_status = "no engine"
    if engine is not None:
        try:
            with engine.connect() as conn:
                conn.execute(sa_text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {e}"
    return {
        "status": "ok",
        "service": "spreadworks",
        "db_status": db_status,
        "db_url_set": bool(os.getenv("DATABASE_URL")),
        "frontend_dist": str(FRONTEND_DIST),
        "frontend_exists": FRONTEND_DIST.exists(),
        "frontend_contents": [str(p.name) for p in FRONTEND_DIST.iterdir()] if FRONTEND_DIST.exists() else [],
    }


# --- Serve frontend static files ---
# Mount /assets if directory exists at startup
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static")


def _frontend_index() -> Path | None:
    """Return path to index.html if it exists (checked at request time)."""
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return index
    return None


@app.get("/", include_in_schema=False)
async def serve_root():
    """Explicit root route — serves index.html or diagnostic page."""
    index = _frontend_index()
    if index:
        return FileResponse(index, media_type="text/html")
    return HTMLResponse(
        "<h1>SpreadWorks</h1>"
        "<p>Backend is running. Frontend dist not found.</p>"
        f"<p>Expected path: <code>{FRONTEND_DIST}</code></p>"
        f"<p>Path exists: <code>{FRONTEND_DIST.exists()}</code></p>"
        "<p><a href='/health'>/health</a> | "
        "<a href='/api/spreadworks/expirations?symbol=SPY'>/api/spreadworks/expirations?symbol=SPY</a></p>",
        status_code=200,
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """SPA catch-all — serve matching file or fall back to index.html."""
    index = _frontend_index()
    if not index:
        return HTMLResponse("<h1>SpreadWorks</h1><p>Frontend not found.</p>", status_code=200)

    # Try serving the exact file requested (e.g. favicon.ico, robots.txt)
    if full_path:
        file_path = (FRONTEND_DIST / full_path).resolve()
        # Security: only serve files inside FRONTEND_DIST
        if file_path.is_file() and str(file_path).startswith(str(FRONTEND_DIST.resolve())):
            return FileResponse(file_path)

    # SPA fallback — return index.html for all other routes
    return FileResponse(index, media_type="text/html")
