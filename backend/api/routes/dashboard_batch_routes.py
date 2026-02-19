"""
Dashboard Batch API — collapse 50+ individual API calls into 1-3 requests.

The /live-trading page was making ~55 unique API calls on mount, overwhelming
Render's 15-connection DB pool and causing 1.5+ minute load times.

This module provides a single POST /api/v1/dashboard/batch endpoint that
accepts a list of sections to fetch and returns all data in one response.
Each section is fetched concurrently with asyncio.gather and per-section
error isolation (one failure doesn't block others).

Usage (frontend):
  POST /api/v1/dashboard/batch
  Body: { "sections": ["bot_statuses", "market_data", "equity_curves"] }
  → Returns all requested data keyed by section name.
"""

import asyncio
import time
import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Import handler functions from existing route modules.
# Every one of these is an async def returning a plain dict — no FastAPI
# request context needed, so we can just `await` them directly.
# ---------------------------------------------------------------------------
from backend.api.routes.fortress_routes import (
    get_fortress_status,
    get_live_pnl as fortress_live_pnl,
    get_fortress_positions,
    get_fortress_equity_curve,
)
from backend.api.routes.solomon_routes import (
    get_solomon_status,
    get_solomon_live_pnl,
    get_solomon_positions,
    get_solomon_equity_curve,
)
from backend.api.routes.gideon_routes import (
    get_gideon_status,
    get_gideon_live_pnl,
    get_gideon_positions,
    get_gideon_equity_curve,
)
from backend.api.routes.anchor_routes import (
    get_anchor_status,
    get_anchor_live_pnl,
    get_anchor_positions,
    get_anchor_equity_curve,
)
from backend.api.routes.samson_routes import (
    get_samson_status,
    get_samson_live_pnl,
    get_samson_positions,
    get_samson_equity_curve,
)
from backend.api.routes.jubilee_routes import (
    get_jubilee_status,
    get_ic_equity_curve as jubilee_ic_equity_curve,
)
from backend.api.routes.valor_routes import (
    get_valor_paper_equity_curve,
)
from backend.api.routes.agape_routes import (
    get_status as agape_status,
    get_equity_curve as agape_equity_curve,
)
from backend.api.routes.agape_spot_routes import (
    get_equity_curve as agape_spot_equity_curve,
)
from backend.api.routes.agape_btc_routes import (
    get_status as agape_btc_status,
    get_equity_curve as agape_btc_equity_curve,
)
from backend.api.routes.agape_xrp_routes import (
    get_status as agape_xrp_status,
    get_equity_curve as agape_xrp_equity_curve,
)
from backend.api.routes.agape_eth_perp_routes import (
    get_equity_curve as agape_eth_perp_equity_curve,
)
from backend.api.routes.agape_btc_perp_routes import (
    get_equity_curve as agape_btc_perp_equity_curve,
)
from backend.api.routes.agape_xrp_perp_routes import (
    get_equity_curve as agape_xrp_perp_equity_curve,
)
from backend.api.routes.agape_doge_perp_routes import (
    get_equity_curve as agape_doge_perp_equity_curve,
)
from backend.api.routes.agape_shib_perp_routes import (
    get_equity_curve as agape_shib_perp_equity_curve,
)
from backend.api.routes.gex_routes import get_gex_data
from backend.api.routes.vix_routes import get_vix_current
from backend.api.routes.prophet_routes import prophet_status
from backend.api.routes.ml_routes import get_wisdom_status, get_bot_ml_status
from backend.api.routes.quant_routes import quant_status, get_alerts
from backend.api.routes.math_optimizer_routes import (
    get_optimizer_status,
    get_live_dashboard as math_live_dashboard,
)
from backend.api.routes.core_routes import get_time
from backend.api.routes.daily_manna_routes import get_daily_manna_widget
from backend.api.routes.bot_reports_routes import get_today_report_summary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard Batch"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

VALID_SECTIONS = {
    "bot_statuses",       # 8 bot status endpoints
    "bot_live_pnl",       # 5 live PnL endpoints
    "bot_positions",      # 5 open position endpoints
    "bot_equity_curves",  # 16 equity curve endpoints
    "bot_reports",        # 5 report summary endpoints
    "market_data",        # GEX SPY + VIX + Prophet
    "ml_status",          # WISDOM + bot-ml + quant + alerts + optimizer
    "daily_manna",        # Daily manna widget
    "system",             # Time/sync
}


class BatchRequest(BaseModel):
    sections: List[str] = Field(
        default=list(VALID_SECTIONS),
        description="Which data sections to fetch. Omit for all.",
    )
    equity_curve_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Days of history for equity curves.",
    )


# ---------------------------------------------------------------------------
# Safe wrapper — isolates per-task errors so one failure doesn't kill the batch
# ---------------------------------------------------------------------------

async def _safe(label: str, coro):
    """Await *coro*; on failure return an error dict instead of raising."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("batch: %s failed: %s", label, exc)
        return {"_error": str(exc)}


# ---------------------------------------------------------------------------
# Section fetchers
# ---------------------------------------------------------------------------

async def _fetch_bot_statuses() -> dict:
    """Fetch status for all 8 bots displayed on the dashboard."""
    results = await asyncio.gather(
        _safe("fortress_status", get_fortress_status()),
        _safe("solomon_status", get_solomon_status()),
        _safe("gideon_status", get_gideon_status()),
        _safe("anchor_status", get_anchor_status()),
        _safe("samson_status", get_samson_status()),
        _safe("jubilee_status", get_jubilee_status()),
        _safe("agape_status", agape_status()),
        _safe("agape_btc_status", agape_btc_status()),
        _safe("agape_xrp_status", agape_xrp_status()),
    )
    return {
        "fortress": results[0],
        "solomon": results[1],
        "gideon": results[2],
        "anchor": results[3],
        "samson": results[4],
        "jubilee": results[5],
        "agape": results[6],
        "agape_btc": results[7],
        "agape_xrp": results[8],
    }


async def _fetch_bot_live_pnl() -> dict:
    """Fetch live PnL for the 5 core bots + jubilee."""
    results = await asyncio.gather(
        _safe("fortress_pnl", fortress_live_pnl()),
        _safe("solomon_pnl", get_solomon_live_pnl()),
        _safe("gideon_pnl", get_gideon_live_pnl()),
        _safe("anchor_pnl", get_anchor_live_pnl()),
        _safe("samson_pnl", get_samson_live_pnl()),
    )
    return {
        "fortress": results[0],
        "solomon": results[1],
        "gideon": results[2],
        "anchor": results[3],
        "samson": results[4],
    }


async def _fetch_bot_positions() -> dict:
    """Fetch open positions for the 5 core bots."""
    results = await asyncio.gather(
        _safe("fortress_pos", get_fortress_positions()),
        _safe("solomon_pos", get_solomon_positions()),
        _safe("gideon_pos", get_gideon_positions()),
        _safe("anchor_pos", get_anchor_positions()),
        _safe("samson_pos", get_samson_positions()),
    )
    return {
        "fortress": results[0],
        "solomon": results[1],
        "gideon": results[2],
        "anchor": results[3],
        "samson": results[4],
    }


async def _fetch_equity_curves(days: int) -> dict:
    """Fetch equity curves for all 16 bots shown in MultiBotEquityCurve."""
    results = await asyncio.gather(
        _safe("fortress_eq", get_fortress_equity_curve(days)),
        _safe("solomon_eq", get_solomon_equity_curve(days)),
        _safe("gideon_eq", get_gideon_equity_curve(days)),
        _safe("anchor_eq", get_anchor_equity_curve(days)),
        _safe("samson_eq", get_samson_equity_curve(days)),
        _safe("jubilee_eq", jubilee_ic_equity_curve()),
        _safe("valor_eq", get_valor_paper_equity_curve(days)),
        _safe("agape_eq", agape_equity_curve(days)),
        _safe("agape_spot_eq", agape_spot_equity_curve(None, days)),
        _safe("agape_btc_eq", agape_btc_equity_curve(days)),
        _safe("agape_xrp_eq", agape_xrp_equity_curve(days)),
        _safe("agape_eth_perp_eq", agape_eth_perp_equity_curve(days)),
        _safe("agape_btc_perp_eq", agape_btc_perp_equity_curve(days)),
        _safe("agape_xrp_perp_eq", agape_xrp_perp_equity_curve(days)),
        _safe("agape_doge_perp_eq", agape_doge_perp_equity_curve(days)),
        _safe("agape_shib_perp_eq", agape_shib_perp_equity_curve(days)),
    )
    return {
        "fortress": results[0],
        "solomon": results[1],
        "gideon": results[2],
        "anchor": results[3],
        "samson": results[4],
        "jubilee": results[5],
        "valor": results[6],
        "agape": results[7],
        "agape_spot": results[8],
        "agape_btc": results[9],
        "agape_xrp": results[10],
        "agape_eth_perp": results[11],
        "agape_btc_perp": results[12],
        "agape_xrp_perp": results[13],
        "agape_doge_perp": results[14],
        "agape_shib_perp": results[15],
    }


async def _fetch_bot_reports() -> dict:
    """Fetch today's report summary for the 5 core bots."""
    bots = ["fortress", "solomon", "gideon", "anchor", "samson"]
    results = await asyncio.gather(
        *[_safe(f"{b}_report", get_today_report_summary(b)) for b in bots]
    )
    return dict(zip(bots, results))


async def _fetch_market_data() -> dict:
    """Fetch GEX SPY, VIX current, and Prophet status."""
    results = await asyncio.gather(
        _safe("gex_spy", get_gex_data("SPY")),
        _safe("vix", get_vix_current()),
        _safe("prophet", prophet_status()),
    )
    return {
        "gex_spy": results[0],
        "vix": results[1],
        "prophet": results[2],
    }


async def _fetch_ml_status() -> dict:
    """Fetch ML/quant system status."""
    results = await asyncio.gather(
        _safe("wisdom", get_wisdom_status()),
        _safe("bot_ml", get_bot_ml_status()),
        _safe("quant", quant_status()),
        _safe("alerts", get_alerts()),
        _safe("optimizer", get_optimizer_status()),
        _safe("optimizer_live", math_live_dashboard()),
    )
    return {
        "wisdom": results[0],
        "bot_ml": results[1],
        "quant": results[2],
        "alerts": results[3],
        "optimizer": results[4],
        "optimizer_live": results[5],
    }


async def _fetch_daily_manna() -> dict:
    """Fetch daily manna widget."""
    return await _safe("daily_manna", get_daily_manna_widget())


async def _fetch_system() -> dict:
    """Fetch time/sync status."""
    return await _safe("time", get_time())


# ---------------------------------------------------------------------------
# Map section names → fetcher functions
# ---------------------------------------------------------------------------

SECTION_FETCHERS = {
    "bot_statuses": lambda days: _fetch_bot_statuses(),
    "bot_live_pnl": lambda days: _fetch_bot_live_pnl(),
    "bot_positions": lambda days: _fetch_bot_positions(),
    "bot_equity_curves": lambda days: _fetch_equity_curves(days),
    "bot_reports": lambda days: _fetch_bot_reports(),
    "market_data": lambda days: _fetch_market_data(),
    "ml_status": lambda days: _fetch_ml_status(),
    "daily_manna": lambda days: _fetch_daily_manna(),
    "system": lambda days: _fetch_system(),
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/api/v1/dashboard/batch")
async def dashboard_batch(req: BatchRequest):
    """
    Batch endpoint for the /live-trading dashboard.

    Accepts a list of section names and returns all requested data in a single
    response. Each section is fetched concurrently — a failure in one section
    does not affect others.

    Sections:
    - bot_statuses: Status for all 9 bots (FORTRESS, SOLOMON, GIDEON, ANCHOR, SAMSON, JUBILEE, AGAPE, AGAPE_BTC, AGAPE_XRP)
    - bot_live_pnl: Live P&L for 5 core bots
    - bot_positions: Open positions for 5 core bots
    - bot_equity_curves: Equity curves for all 16 bots (configurable days)
    - bot_reports: Today's report summary for 5 core bots
    - market_data: GEX SPY + VIX + Prophet
    - ml_status: WISDOM + bot ML + quant + alerts + optimizer
    - daily_manna: Daily manna widget
    - system: Time/sync

    Returns ~50 underlying DB queries in 1 HTTP round-trip.
    """
    t0 = time.time()

    # Filter to valid sections only
    sections = [s for s in req.sections if s in SECTION_FETCHERS]
    if not sections:
        sections = list(SECTION_FETCHERS.keys())

    # Fire all requested sections concurrently
    tasks = [SECTION_FETCHERS[s](req.equity_curve_days) for s in sections]
    results = await asyncio.gather(*tasks)

    data = dict(zip(sections, results))
    elapsed_ms = round((time.time() - t0) * 1000)

    return {
        "success": True,
        "data": data,
        "meta": {
            "sections_requested": sections,
            "elapsed_ms": elapsed_ms,
        },
    }
