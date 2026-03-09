"""SpreadWorks backend — FastAPI application."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

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


def _start_scheduler(app: FastAPI):
    """Start APScheduler for market open/close Discord posts (UTC times)."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("[SpreadWorks] apscheduler not installed — Discord scheduler disabled")
        return None

    scheduler = AsyncIOScheduler(timezone="UTC")

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
    # 8:25 CT = 13:25 UTC (CDT) or 14:25 UTC (CST)
    scheduler.add_job(_fire_open_post, "cron", hour="13,14", minute=25,
                      day_of_week="mon-fri", id="discord_open")
    # 15:05 CT = 20:05 UTC (CDT) or 21:05 UTC (CST)
    scheduler.add_job(_fire_eod_post, "cron", hour="20,21", minute=5,
                      day_of_week="mon-fri", id="discord_eod")

    scheduler.start()
    logger.info("[SpreadWorks] APScheduler started — discord_open and discord_eod jobs registered")
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables if engine is configured
    if engine is not None:
        try:
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
