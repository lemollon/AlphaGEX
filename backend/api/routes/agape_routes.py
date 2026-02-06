"""
AGAPE API Routes - ETH Micro Futures Trading Bot endpoints.

AGAPE (ἀγάπη) trades Micro Ether Futures (/MET) on CME via tastytrade,
using crypto market microstructure signals as GEX equivalents.

Endpoints follow the standard bot pattern:
  /status        - Bot health and config
  /positions     - Open positions with unrealized P&L
  /closed-trades - Completed trade history
  /equity-curve  - Historical equity curve
  /performance   - Win rate, P&L, statistics
  /logs          - Activity log
  /scan-activity - Scan history (every cycle logged)
  /snapshot      - Current crypto market microstructure
  /signal        - Generate a signal (dry run)
"""

import logging
from datetime import datetime
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape", tags=["AGAPE"])

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful imports
AGAPE_AVAILABLE = False
AgapeTrader = None
get_agape_trader = None
try:
    from trading.agape.trader import AgapeTrader, get_agape_trader, create_agape_trader
    AGAPE_AVAILABLE = True
    logger.info("AGAPE Routes: AgapeTrader loaded")
except ImportError as e:
    logger.warning(f"AGAPE Routes: AgapeTrader not available: {e}")

CRYPTO_PROVIDER_AVAILABLE = False
get_crypto_data_provider = None
try:
    from data.crypto_data_provider import get_crypto_data_provider
    CRYPTO_PROVIDER_AVAILABLE = True
except ImportError:
    pass

# Database adapter
get_connection = None
try:
    from database_adapter import get_connection
except ImportError:
    pass


def _get_trader():
    """Get or lazily create the AGAPE trader instance."""
    if not AGAPE_AVAILABLE:
        return None
    trader = get_agape_trader()
    if trader is None:
        try:
            trader = create_agape_trader()
        except Exception as e:
            logger.error(f"AGAPE Routes: Failed to create trader: {e}")
    return trader


def _format_ct(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now(CENTRAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S CT")


# ------------------------------------------------------------------
# Bot Status
# ------------------------------------------------------------------

@router.get("/status")
async def get_status():
    """Get AGAPE bot status, configuration, and open positions.

    Returns:
    - Bot health (active/disabled)
    - Current ETH price
    - Open position count and details
    - Configuration parameters
    """
    trader = _get_trader()
    if not trader:
        return {
            "success": False,
            "data_unavailable": True,
            "reason": "AGAPE trader not initialized",
            "message": "AGAPE module not available",
        }

    try:
        status = trader.get_status()
        return {
            "success": True,
            "data": status,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------

@router.get("/positions")
async def get_positions():
    """Get all open AGAPE positions with unrealized P&L.

    Each position includes:
    - Entry details (price, side, contracts)
    - Market context at entry (funding, L/S, squeeze risk)
    - Oracle context (advice, win probability)
    - Current unrealized P&L
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE not available"}

    try:
        positions = trader.db.get_open_positions()
        current_price = trader.executor.get_current_price()

        # Add unrealized P&L
        for pos in positions:
            if current_price:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * 0.1 * direction * pos.get("contracts", 1)
                pos["unrealized_pnl"] = round(pnl, 2)
                pos["current_price"] = current_price
            else:
                pos["unrealized_pnl"] = 0
                pos["current_price"] = None

        return {
            "success": True,
            "data": positions,
            "count": len(positions),
            "current_eth_price": current_price,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE positions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(
    limit: int = Query(default=50, le=500, description="Number of trades to return"),
):
    """Get closed/expired trade history."""
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE not available"}

    try:
        trades = trader.db.get_closed_trades(limit=limit)
        return {
            "success": True,
            "data": trades,
            "count": len(trades),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE closed trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Equity Curve
# ------------------------------------------------------------------

@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to return"),
):
    """Get historical equity curve built from all closed trades.

    Returns EXACT same format as HERACLES /paper-equity-curve so that
    MultiBotEquityCurve component can render it without any adaptation.

    Format: { equity_curve: [...], points: N, days: N, timestamp: "..." }
    """
    if not get_connection:
        now = datetime.now(CENTRAL_TZ)
        return {
            "success": True,
            "data": {
                "equity_curve": [{
                    "date": now.strftime("%Y-%m-%d"),
                    "daily_pnl": 0.0,
                    "cumulative_pnl": 0.0,
                    "equity": 5000.0,
                    "trades": 0,
                    "return_pct": 0.0,
                }],
                "starting_capital": 5000.0,
                "current_equity": 5000.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
            },
            "points": 1,
            "days": days,
            "timestamp": now.isoformat(),
        }

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config (key/value schema with agape_ prefix)
        starting_capital = 5000.0
        try:
            cursor.execute(
                "SELECT value FROM autonomous_config WHERE key = 'agape_starting_capital'"
            )
            row = cursor.fetchone()
            if row and row[0]:
                starting_capital = float(row[0])
        except Exception:
            pass

        # Get ALL closed trades ordered chronologically (no date filter on SQL)
        cursor.execute("""
            SELECT
                (close_time AT TIME ZONE 'America/Chicago')::date as trade_date,
                realized_pnl,
                position_id
            FROM agape_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time IS NOT NULL
              AND realized_pnl IS NOT NULL
            ORDER BY close_time ASC
        """)
        rows = cursor.fetchall()

        if not rows:
            now = datetime.now(CENTRAL_TZ)
            return {
                "success": True,
                "data": {
                    "equity_curve": [{
                        "date": now.strftime("%Y-%m-%d"),
                        "daily_pnl": 0.0,
                        "cumulative_pnl": 0.0,
                        "equity": starting_capital,
                        "trades": 0,
                        "return_pct": 0.0,
                    }],
                    "starting_capital": starting_capital,
                    "current_equity": starting_capital,
                    "total_pnl": 0.0,
                    "total_return_pct": 0.0,
                },
                "points": 1,
                "days": days,
                "timestamp": now.isoformat(),
            }

        # Aggregate by day
        from collections import defaultdict
        daily: Dict = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
        for row in rows:
            trade_date = str(row[0])
            pnl = float(row[1]) if row[1] else 0.0
            daily[trade_date]["pnl"] += pnl
            daily[trade_date]["trades"] += 1

        # Build equity curve chronologically
        sorted_dates = sorted(daily.keys())
        cumulative_pnl = 0.0
        equity_curve = []

        for d in sorted_dates:
            day_pnl = daily[d]["pnl"]
            day_trades = daily[d]["trades"]
            cumulative_pnl += day_pnl
            equity = starting_capital + cumulative_pnl

            equity_curve.append({
                "date": d,
                "daily_pnl": round(day_pnl, 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "equity": round(equity, 2),
                "trades": day_trades,
                "return_pct": round(cumulative_pnl / starting_capital, 4),
            })

        # Filter to requested days (output filter only, not SQL)
        if days < 365 and len(equity_curve) > days:
            equity_curve = equity_curve[-days:]

        current_equity = equity_curve[-1]["equity"] if equity_curve else starting_capital
        total_pnl = equity_curve[-1]["cumulative_pnl"] if equity_curve else 0.0

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "total_pnl": round(total_pnl, 2),
                "total_return_pct": round(total_pnl / starting_capital * 100, 2),
            },
            "points": len(equity_curve),
            "days": days,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
        }

    except Exception as e:
        logger.error(f"AGAPE equity curve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/equity-curve/intraday")
async def get_equity_curve_intraday():
    """Get today's intraday equity snapshots."""
    if not get_connection:
        return {"success": False, "data": [], "message": "Database not available"}

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, equity, unrealized_pnl,
                   realized_pnl_cumulative, open_positions, eth_price, funding_rate
            FROM agape_equity_snapshots
            WHERE timestamp::date = (NOW() AT TIME ZONE 'America/Chicago')::date
            ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()
        data = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "equity": float(row[1]),
                "unrealized_pnl": float(row[2]) if row[2] else 0,
                "realized_pnl_cumulative": float(row[3]) if row[3] else 0,
                "open_positions": row[4],
                "eth_price": float(row[5]) if row[5] else None,
                "funding_rate": float(row[6]) if row[6] else None,
            }
            for row in rows
        ]
        return {
            "success": True,
            "data": data,
            "count": len(data),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE intraday equity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ------------------------------------------------------------------
# Performance
# ------------------------------------------------------------------

@router.get("/performance")
async def get_performance():
    """Get AGAPE performance statistics.

    Returns win rate, total P&L, average win/loss, profit factor, etc.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": {}, "message": "AGAPE not available"}

    try:
        perf = trader.get_performance()
        return {
            "success": True,
            "data": perf,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Logs & Scan Activity
# ------------------------------------------------------------------

@router.get("/logs")
async def get_logs(
    limit: int = Query(default=50, le=200, description="Number of log entries"),
):
    """Get AGAPE activity log."""
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE not available"}

    try:
        logs = trader.db.get_logs(limit=limit)
        return {
            "success": True,
            "data": logs,
            "count": len(logs),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_scan_activity(
    limit: int = Query(default=50, le=200, description="Number of scans"),
):
    """Get AGAPE scan history - every cycle is logged.

    Shows what the bot saw, what it decided, and why.
    Includes crypto microstructure data, Oracle advice, and signal reasoning.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE not available"}

    try:
        scans = trader.db.get_scan_activity(limit=limit)
        return {
            "success": True,
            "data": scans,
            "count": len(scans),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE scan activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Market Snapshot (Crypto Microstructure)
# ------------------------------------------------------------------

@router.get("/snapshot")
async def get_crypto_snapshot(
    symbol: str = Query(default="ETH", description="Crypto symbol"),
):
    """Get current crypto market microstructure snapshot.

    Returns the crypto equivalent of ARGUS's gamma snapshot:
    - Funding rate and regime (→ gamma regime)
    - Liquidation clusters (→ gamma walls)
    - Long/Short ratio (→ directional bias)
    - Options OI and max pain (→ flip point)
    - Crypto GEX from Deribit (→ net GEX)
    - Combined signal and confidence
    """
    if not CRYPTO_PROVIDER_AVAILABLE:
        return {
            "success": False,
            "data_unavailable": True,
            "reason": "CryptoDataProvider not available",
        }

    try:
        provider = get_crypto_data_provider()
        snapshot = provider.get_snapshot(symbol)

        data = {
            "symbol": snapshot.symbol,
            "spot_price": snapshot.spot_price,
            "timestamp": snapshot.timestamp.isoformat(),
            # Funding Rate (→ Gamma Regime)
            "funding": {
                "rate": snapshot.funding_rate.rate if snapshot.funding_rate else None,
                "predicted": snapshot.funding_rate.predicted_rate if snapshot.funding_rate else None,
                "regime": snapshot.funding_regime,
                "annualized": snapshot.funding_rate.annualized_rate if snapshot.funding_rate else None,
                "gex_equivalent": "Replaces gamma regime (POSITIVE/NEGATIVE)",
            },
            # Liquidations (→ Gamma Walls / Magnets)
            "liquidations": {
                "nearest_long_liq": snapshot.nearest_long_liq,
                "nearest_short_liq": snapshot.nearest_short_liq,
                "cluster_count": len(snapshot.liquidation_clusters),
                "top_clusters": [
                    {
                        "price": c.price_level,
                        "long_usd": c.long_liquidation_usd,
                        "short_usd": c.short_liquidation_usd,
                        "intensity": c.intensity,
                        "distance_pct": round(c.distance_pct, 2),
                    }
                    for c in snapshot.liquidation_clusters[:10]
                ],
                "gex_equivalent": "Replaces gamma walls and price magnets",
            },
            # L/S Ratio (→ Directional Bias)
            "long_short": {
                "ratio": snapshot.ls_ratio.ratio if snapshot.ls_ratio else None,
                "long_pct": snapshot.ls_ratio.long_pct if snapshot.ls_ratio else None,
                "short_pct": snapshot.ls_ratio.short_pct if snapshot.ls_ratio else None,
                "bias": snapshot.ls_ratio.bias if snapshot.ls_ratio else "NEUTRAL",
                "gex_equivalent": "Replaces GEX directional bias",
            },
            # OI / Max Pain (→ Flip Point)
            "options": {
                "max_pain": snapshot.max_pain,
                "oi_levels_count": len(snapshot.oi_levels),
                "gex_equivalent": "Replaces GEX flip point",
            },
            # Crypto GEX (→ Direct GEX equivalent)
            "crypto_gex": {
                "net_gex": snapshot.crypto_gex.net_gex if snapshot.crypto_gex else None,
                "regime": snapshot.crypto_gex.gamma_regime if snapshot.crypto_gex else "NEUTRAL",
                "call_gex": snapshot.crypto_gex.call_gex if snapshot.crypto_gex else None,
                "put_gex": snapshot.crypto_gex.put_gex if snapshot.crypto_gex else None,
                "flip_point": snapshot.crypto_gex.flip_point if snapshot.crypto_gex else None,
                "gex_equivalent": "Direct crypto GEX from Deribit options",
            },
            # Combined Signals
            "signals": {
                "leverage_regime": snapshot.leverage_regime,
                "directional_bias": snapshot.directional_bias,
                "volatility_regime": snapshot.volatility_regime,
                "squeeze_risk": snapshot.squeeze_risk,
                "combined_signal": snapshot.combined_signal,
                "combined_confidence": snapshot.combined_confidence,
            },
        }

        return {
            "success": True,
            "data": data,
            "fetched_at": _format_ct(),
        }

    except Exception as e:
        logger.error(f"AGAPE snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Signal Generation (Dry Run)
# ------------------------------------------------------------------

@router.get("/signal")
async def generate_signal():
    """Generate a trade signal without executing (dry run).

    Returns the full signal with:
    - Crypto microstructure analysis
    - Oracle consultation result
    - Recommended action (LONG/SHORT/WAIT)
    - Position sizing and risk levels
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "message": "AGAPE not available"}

    try:
        signal = trader.signals.generate_signal()
        return {
            "success": True,
            "data": signal.to_dict(),
            "is_tradeable": signal.is_valid,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# GEX Mapping Reference
# ------------------------------------------------------------------

@router.get("/gex-mapping")
async def get_gex_mapping():
    """Returns the GEX → Crypto signal mapping reference.

    Educational endpoint showing how equity GEX concepts translate
    to crypto market microstructure signals used by AGAPE.
    """
    return {
        "success": True,
        "data": {
            "title": "AGAPE: GEX → Crypto Signal Mapping",
            "description": (
                "AGAPE uses crypto market microstructure signals as equivalents "
                "to the GEX-based analysis used by equity bots (ARES, ARGUS, etc.)"
            ),
            "mappings": [
                {
                    "gex_concept": "Gamma Regime (POSITIVE/NEGATIVE)",
                    "crypto_equivalent": "Funding Rate Regime",
                    "explanation": (
                        "High positive funding = overleveraged longs = NEGATIVE GAMMA equivalent. "
                        "Near zero = balanced = POSITIVE GAMMA (mean reversion). "
                        "High negative = overleveraged shorts = squeeze risk."
                    ),
                    "data_source": "CoinGlass (aggregated across exchanges)",
                    "thresholds": {
                        "balanced": "|funding| < 0.5%",
                        "mild_bias": "0.5% - 1%",
                        "overleveraged": "1% - 3%",
                        "extreme": "> 3%",
                    },
                },
                {
                    "gex_concept": "Gamma Walls (Call/Put)",
                    "crypto_equivalent": "Liquidation Clusters",
                    "explanation": (
                        "Where leveraged positions get force-closed, creating price "
                        "magnets just like gamma walls. Long liquidations below price "
                        "act like put walls; short liquidations above like call walls."
                    ),
                    "data_source": "CoinGlass liquidation heatmap",
                },
                {
                    "gex_concept": "GEX Flip Point",
                    "crypto_equivalent": "Max Pain Level",
                    "explanation": (
                        "The price where most options expire worthless. Price gravitates "
                        "toward max pain near expiry, similar to how price gravitates "
                        "to the GEX flip point."
                    ),
                    "data_source": "Deribit options OI by strike",
                },
                {
                    "gex_concept": "Net GEX Value",
                    "crypto_equivalent": "Crypto GEX (Deribit)",
                    "explanation": (
                        "Actual gamma exposure calculated from Deribit ETH options. "
                        "Less reliable than equity GEX due to different market structure "
                        "(no designated market makers), but provides similar signals."
                    ),
                    "data_source": "Deribit public API (options book summaries)",
                },
                {
                    "gex_concept": "Directional Bias",
                    "crypto_equivalent": "Long/Short Ratio",
                    "explanation": (
                        "Shows which side of the market is crowded. Extreme ratios "
                        "signal overcrowding, similar to extreme GEX readings "
                        "predicting reversals. AGAPE uses contrarian logic."
                    ),
                    "data_source": "CoinGlass (aggregated L/S ratio)",
                },
                {
                    "gex_concept": "ARGUS Market Structure (9 signals)",
                    "crypto_equivalent": "Combined Crypto Signals (6 inputs)",
                    "explanation": (
                        "Funding regime + L/S ratio + Liquidation proximity + "
                        "Options OI + Crypto GEX + Squeeze risk → Combined signal "
                        "(LONG / SHORT / RANGE_BOUND / WAIT)"
                    ),
                },
            ],
            "trade_instrument": {
                "symbol": "/MET (Micro Ether Futures)",
                "exchange": "CME Globex",
                "broker": "tastytrade",
                "contract_size": "0.1 ETH",
                "tick_value": "$0.05",
                "margin": "~$125-225 per contract",
            },
        },
    }


# ------------------------------------------------------------------
# Bot Control
# ------------------------------------------------------------------

@router.post("/enable")
async def enable_bot():
    """Enable AGAPE trading."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE not available")
    trader.enable()
    return {"success": True, "message": "AGAPE enabled"}


@router.post("/disable")
async def disable_bot():
    """Disable AGAPE trading (positions still managed)."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE not available")
    trader.disable()
    return {"success": True, "message": "AGAPE disabled"}
