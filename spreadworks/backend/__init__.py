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
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Log at import time so we can see in Render logs
print(f"[SpreadWorks] __file__ = {__file__}")
print(f"[SpreadWorks] FRONTEND_DIST = {FRONTEND_DIST}")
print(f"[SpreadWorks] FRONTEND_DIST.exists() = {FRONTEND_DIST.exists()}")
if FRONTEND_DIST.exists():
    print(f"[SpreadWorks] dist contents: {list(FRONTEND_DIST.iterdir())}")


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


def _start_scheduler(app: FastAPI):
    """Start APScheduler for market open/close Discord posts (UTC times)."""
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

    scheduler = AsyncIOScheduler(timezone="UTC")

    def _is_trading_day() -> bool:
        """Check if today is a trading day (weekday + not holiday)."""
        if not content_loaded:
            from datetime import datetime as _dt
            return _dt.utcnow().weekday() < 5
        now = get_central_now()
        return now.weekday() < 5 and not is_market_holiday(now.date())

    def _rotation_index(items, offset=0) -> int:
        """Deterministic daily rotation based on day-of-year."""
        if content_loaded:
            day_of_year = get_central_now().timetuple().tm_yday
        else:
            from datetime import datetime as _dt
            day_of_year = _dt.utcnow().timetuple().tm_yday
        return (day_of_year + offset) % len(items)

    def _impact_color(impact: str) -> int:
        return {"HIGH": 0xFF1744, "MEDIUM": 0xFFD600, "LOW": 0x448AFF}.get(impact, 0x448AFF)

    async def _fire_market_open_message():
        """8:25 AM CT — Bible verse + spread trading tip."""
        if not content_loaded or not _is_trading_day():
            logger.info("[SpreadWorks] Skipping market open message (not trading day or no content)")
            return

        import asyncio
        now = get_central_now()
        verse = VERSES[_rotation_index(VERSES)]
        tip = TIPS[_rotation_index(TIPS, offset=37)]

        embed = {
            "title": "\U0001f305 MARKET OPENS IN 5 MINUTES",
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
        """8:30 AM CT — Economic event countdown."""
        if not content_loaded or not _is_trading_day():
            logger.info("[SpreadWorks] Skipping economic countdown (not trading day or no content)")
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
        """Market open post — 8:25 AM CT = 13:25 or 14:25 UTC depending on DST."""
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
        """Market close post — 3:05 PM CT = 20:05 or 21:05 UTC depending on DST."""
        logger.info("[SpreadWorks] Scheduler firing EOD Discord post")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                base = os.getenv("SPREADWORKS_INTERNAL_URL", "http://127.0.0.1:8000")
                resp = await client.post(f"{base}/api/spreadworks/discord/post-eod")
                logger.info(f"[SpreadWorks] EOD post response: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"[SpreadWorks] EOD Discord post failed: {e}")

    # Schedule using CT-equivalent UTC cron times
    # CT is UTC-6 (CST) or UTC-5 (CDT). Use both possible hours.

    # 8:25 CT — Bible verse + tip
    scheduler.add_job(_fire_market_open_message, "cron", hour="13,14", minute=25,
                      day_of_week="mon-fri", id="discord_market_open_msg")
    # 8:25 CT — Open positions summary (existing)
    scheduler.add_job(_fire_open_post, "cron", hour="13,14", minute=25, second=30,
                      day_of_week="mon-fri", id="discord_open")
    # 8:30 CT — Economic event countdown
    scheduler.add_job(_fire_economic_countdown, "cron", hour="13,14", minute=30,
                      day_of_week="mon-fri", id="discord_economic")
    # 15:00 CT — Market close reflection
    scheduler.add_job(_fire_market_close_message, "cron", hour="20,21", minute=0,
                      day_of_week="mon-fri", id="discord_market_close_msg")
    # 15:05 CT — EOD summary with AI commentary (existing)
    scheduler.add_job(_fire_eod_post, "cron", hour="20,21", minute=5,
                      day_of_week="mon-fri", id="discord_eod")

    scheduler.start()
    logger.info(
        "[SpreadWorks] APScheduler started — 5 jobs: "
        "market_open_msg (8:25), open_positions (8:25:30), "
        "economic (8:30), market_close_msg (15:00), eod (15:05) CT"
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
    if scheduler:
        scheduler.shutdown(wait=False)
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
