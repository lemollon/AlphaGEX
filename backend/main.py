"""AlphaGEX FastAPI application.

The active AlphaGEX product is intentionally scoped to:
- VALOR micro-futures trading
- Active AGAPE crypto perpetual bots

SpreadWorks and IronForge are separate protected projects and are not modified
or imported by this application.
"""

import os

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



@app.on_event("startup")
async def start_active_trading_scheduler():
    """Start the single VALOR + crypto perpetual scheduler."""
    from scheduler.trader_scheduler import get_scheduler

    scheduler = get_scheduler()
    if not scheduler.is_running:
        scheduler.start()


@app.on_event("shutdown")
async def stop_active_trading_scheduler():
    """Stop the active trading scheduler during graceful shutdown."""
    from scheduler.trader_scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler.is_running:
        scheduler.stop()


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
