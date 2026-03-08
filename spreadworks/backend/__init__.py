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
# Always register the SPA catch-all: if dist exists, serve files; otherwise
# return a helpful diagnostic page so we know what went wrong on deploy.

_has_frontend = FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists()

if _has_frontend:
    # Mount assets with proper caching
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve frontend SPA — all non-API routes return index.html."""
    if _has_frontend:
        file_path = FRONTEND_DIST / full_path
        # Security: don't allow path traversal
        try:
            file_path = file_path.resolve()
            if file_path.is_file() and str(file_path).startswith(str(FRONTEND_DIST.resolve())):
                return FileResponse(file_path)
        except (ValueError, OSError):
            pass
        return FileResponse(FRONTEND_DIST / "index.html")
    else:
        return HTMLResponse(
            f"<h1>SpreadWorks</h1>"
            f"<p>Backend is running. Frontend dist not found.</p>"
            f"<p>Expected path: <code>{FRONTEND_DIST}</code></p>"
            f"<p>Path exists: <code>{FRONTEND_DIST.exists()}</code></p>"
            f"<p><a href='/health'>/health</a> | "
            f"<a href='/api/spreadworks/expirations?symbol=SPY'>/api/spreadworks/expirations?symbol=SPY</a></p>",
            status_code=200,
        )
