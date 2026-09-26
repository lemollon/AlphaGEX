"""AlphaGEX FastAPI application.

The active AlphaGEX product is intentionally scoped to:
- VALOR micro-futures trading
- Active AGAPE crypto perpetual bots

SpreadWorks and IronForge are separate protected projects and are not modified
or imported by this application.
"""

import asyncio
import concurrent.futures
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    tastytrade_routes,
    valor_routes,
    valor_research_routes,
    valor_microstructure_routes,
    spark_flame_research_routes,
    agape_eth_perp_routes,
    agape_sol_perp_routes,
    agape_avax_perp_routes,
    agape_btc_perp_routes,
    agape_xrp_perp_routes,
    agape_doge_perp_routes,
    agape_shib_perp_routes,
    agape_perpetuals_trades_routes,
    agape_perpetuals_data_health_routes,
    perp_exit_optimizer_routes,
    unified_metrics_routes,
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
app.include_router(valor_research_routes.router)
app.include_router(valor_microstructure_routes.router)
app.include_router(spark_flame_research_routes.router)
app.include_router(agape_eth_perp_routes.router)
app.include_router(agape_sol_perp_routes.router)
app.include_router(agape_avax_perp_routes.router)
app.include_router(agape_btc_perp_routes.router)
app.include_router(agape_xrp_perp_routes.router)
app.include_router(agape_doge_perp_routes.router)
app.include_router(agape_shib_perp_routes.router)
app.include_router(agape_perpetuals_trades_routes.router)
app.include_router(agape_perpetuals_data_health_routes.router)
app.include_router(perp_exit_optimizer_routes.router)
app.include_router(unified_metrics_routes.router)


@app.on_event("startup")
async def cap_default_executor_workers():
    """Cap the event loop's default thread pool so asyncio.to_thread callers
    (blocking psycopg2 DB calls and the Tastytrade HTTP calls) never try to
    open more concurrent DB connections than database_adapter.py's pool can
    serve (max=25). 20 workers leaves headroom under that cap since not every
    thread holds a DB connection for its full lifetime, and non-DB
    to_thread calls share this same worker pool.
    """
    loop = asyncio.get_event_loop()
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=20))


@app.on_event("startup")
async def start_active_trading_scheduler():
    """Start the single VALOR + crypto perpetual scheduler."""
    from scheduler.trader_scheduler import get_scheduler

    scheduler = get_scheduler()
    if not scheduler.is_running:
        scheduler.start()

    # Legacy VALOR research autoruns are intentionally disabled: the original
    # replay used overlapping horizon buckets and uncached paid downloads.
    # Research must never prevent the trading API from starting.
    try:
        from scripts.valor_cash_research_v8 import launch_if_enabled
        launch_if_enabled()
        from scripts.valor_mes_chopguard_v9 import launch_if_enabled as launch_mes_chopguard_v9
        launch_mes_chopguard_v9()
        from scripts.valor_mes_chopguard_v10 import launch_if_enabled as launch_mes_chopguard_v10
        launch_mes_chopguard_v10()
        from scripts.valor_mes_chopguard_v11 import launch_if_enabled as launch_mes_chopguard_v11
        launch_mes_chopguard_v11()
        from scripts.valor_mes_chopguard_v12 import launch_if_enabled as launch_mes_chopguard_v12
        launch_mes_chopguard_v12()
        from scripts.valor_mes_chopguard_v13 import launch_if_enabled as launch_mes_chopguard_v13
        launch_mes_chopguard_v13()
        from scripts.valor_mes_chopguard_v14 import launch_if_enabled as launch_mes_chopguard_v14
        launch_mes_chopguard_v14()
        from scripts.valor_mes_chopguard_v15 import launch_if_enabled as launch_mes_chopguard_v15
        launch_mes_chopguard_v15()
        from scripts.valor_mes_chopguard_v16 import launch_if_enabled as launch_mes_chopguard_v16
        launch_mes_chopguard_v16()
        from scripts.valor_mes_chopguard_v17 import launch_if_enabled as launch_mes_chopguard_v17
        launch_mes_chopguard_v17()
        from scripts.valor_mes_chopguard_v18 import launch_if_enabled as launch_mes_chopguard_v18
        launch_mes_chopguard_v18()
        from scripts.valor_mes_chopguard_v19 import launch_if_enabled as launch_mes_chopguard_v19
        launch_mes_chopguard_v19()
        from scripts.valor_mes_chopguard_v20 import launch_if_enabled as launch_mes_chopguard_v20
        launch_mes_chopguard_v20()
        from scripts.valor_mes_v21_clean_slate import launch_if_enabled as launch_mes_v21
        launch_mes_v21()
        from scripts.valor_mes_v22_event_driven import launch_if_enabled as launch_mes_v22
        launch_mes_v22()
        from scripts.valor_mes_v23_loss_clusters import launch_if_enabled as launch_mes_v23
        launch_mes_v23()
        from scripts.valor_mes_v24_cluster_router import launch_if_enabled as launch_mes_v24
        launch_mes_v24()
        from scripts.valor_mes_v25_rolling_edge_router import launch_if_enabled as launch_mes_v25
        launch_mes_v25()
        from scripts.valor_mes_v26_first_loss_breaker import launch_if_enabled as launch_mes_v26
        launch_mes_v26()
        from scripts.valor_mes_v28_multientry_selector import launch_if_enabled as launch_mes_v28
        launch_mes_v28()
        from scripts.valor_mes_dxlink_candle_probe import launch_if_enabled as launch_mes_candle_probe
        launch_mes_candle_probe()
        from scripts.valor_mes_v31_edge_map import launch_if_enabled as launch_mes_v31
        launch_mes_v31()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "VALOR research launch failed; trading scheduler unchanged"
        )
    spark_flame_research_routes.launch_autorun_if_enabled()
    spark_flame_research_routes.launch_optimizer_if_enabled()


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
            "AGAPE-SHIB-PERP",
        ],
    }
