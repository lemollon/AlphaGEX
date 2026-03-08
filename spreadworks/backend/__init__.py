"""SpreadWorks backend — FastAPI application."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routes import router

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Log at import time so we can see in Render logs
print(f"[SpreadWorks] __file__ = {__file__}")
print(f"[SpreadWorks] FRONTEND_DIST = {FRONTEND_DIST}")
print(f"[SpreadWorks] FRONTEND_DIST.exists() = {FRONTEND_DIST.exists()}")
if FRONTEND_DIST.exists():
    print(f"[SpreadWorks] dist contents: {list(FRONTEND_DIST.iterdir())}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=15.0)
    yield
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
    return {
        "status": "ok",
        "service": "spreadworks",
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
