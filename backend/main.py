"""AlphaGEX FastAPI application.

The active AlphaGEX product is intentionally scoped to:
- VALOR micro-futures trading
- Active AGAPE crypto perpetual bots

SpreadWorks and IronForge are separate protected projects and are not modified
or imported by this application.
"""

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    tastytrade_routes,
    valor_routes,
    agape_eth_perp_routes,
    agape_sol_perp_routes,
    agape_avax_perp_routes,
    agape_btc_perp_routes,
    agape_xrp_perp_routes,
    agape_doge_perp_routes,
    agape_perpetuals_trades_routes,
    perp_exit_optimizer_routes,
)


def _maybe_reset_perp_paper_accounts():
    """One-shot reset for the six active perpetual PAPER accounts only."""
    if os.getenv("PERP_RESET_ON_START", "") != "CONFIRM_PERP_PAPER_RESET":
        return

    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "reset_perpetual_bots.py"

    print("PERP_RESET_ON_START confirmed: resetting active perpetual PAPER accounts")
    for args in (["--reset", "--confirm"], ["--verify"]):
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=True,
        )
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)
    print("PERP paper reset completed and verified")


_maybe_reset_perp_paper_accounts()


app = FastAPI(
    title="AlphaGEX API",
    description="VALOR futures and crypto perpetual trading platform",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

origins = [
    value.strip()
    for value in os.getenv(
        "CORS_ORIGINS",
        os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001"),
    ).split(",")
    if value.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app" if any("*" in o for o in origins) else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tastytrade_routes.router)
app.include_router(valor_routes.router)
app.include_router(agape_eth_perp_routes.router)
app.include_router(agape_sol_perp_routes.router)
app.include_router(agape_avax_perp_routes.router)
app.include_router(agape_btc_perp_routes.router)
app.include_router(agape_xrp_perp_routes.router)
app.include_router(agape_doge_perp_routes.router)
app.include_router(agape_perpetuals_trades_routes.router)
app.include_router(perp_exit_optimizer_routes.router)


@app.get("/")
async def root():
    return {
        "service": "AlphaGEX",
        "scope": ["VALOR", "crypto_perpetuals"],
        "status": "online",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "alphagex-api",
        "active_systems": [
            "VALOR",
            "AGAPE-BTC-PERP",
            "AGAPE-ETH-PERP",
            "AGAPE-SOL-PERP",
            "AGAPE-AVAX-PERP",
            "AGAPE-XRP-PERP",
            "AGAPE-DOGE-PERP",
        ],
    }
