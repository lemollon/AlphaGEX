"""
AGAPE-SHIB-PERP API Routes - SHIB Perpetual Contract Trading Bot endpoints.

AGAPE-SHIB-PERP trades SHIB perpetual contracts using crypto market
microstructure signals as GEX equivalents. Perpetuals trade 24/7 with
no expiry - P&L is simply (current_price - entry_price) * quantity * direction.

Endpoints follow the standard bot pattern:
  /status        - Bot health and config
  /positions     - Open positions with unrealized P&L
  /closed-trades - Completed trade history
  /equity-curve  - Historical equity curve
  /equity-curve/intraday - Today's intraday equity
  /performance   - Win rate, P&L, statistics
  /logs          - Activity log
  /scan-activity - Scan history (every cycle logged)
  /snapshot      - Current crypto market microstructure
  /signal        - Generate a signal (dry run)
  /gex-mapping   - GEX -> Crypto signal mapping reference
  /enable        - Enable trading
  /disable       - Disable trading
"""

import logging
from datetime import datetime
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape-shib-perp", tags=["AGAPE-SHIB-PERP"])

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful imports
AGAPE_SHIB_PERP_AVAILABLE = False
AgapeShibPerpTrader = None
get_agape_shib_perp_trader = None
try:
    from trading.agape_shib_perp.trader import AgapeShibPerpTrader, get_agape_shib_perp_trader, create_agape_shib_perp_trader
    AGAPE_SHIB_PERP_AVAILABLE = True
    logger.info("AGAPE-SHIB-PERP Routes: AgapeShibPerpTrader loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SHIB-PERP Routes: AgapeShibPerpTrader not available: {e}")

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
    """Get or lazily create the AGAPE-SHIB-PERP trader instance."""
    if not AGAPE_SHIB_PERP_AVAILABLE:
        return None
    trader = get_agape_shib_perp_trader()
    if trader is None:
        try:
            trader = create_agape_shib_perp_trader()
        except Exception as e:
            logger.error(f"AGAPE-SHIB-PERP Routes: Failed to create trader: {e}")
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
    """Get AGAPE-SHIB-PERP bot status, configuration, and open positions.

    Returns:
    - Bot health (active/disabled)
    - Current SHIB price
    - Open position count and details
    - Configuration parameters
    """
    trader = _get_trader()
    if not trader:
        return {
            "success": False,
            "data_unavailable": True,
            "reason": "AGAPE-SHIB-PERP trader not initialized",
            "message": "AGAPE-SHIB-PERP module not available",
        }

    try:
        status = trader.get_status()
        return {
            "success": True,
            "data": status,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------

@router.get("/positions")
async def get_positions():
    """Get all open AGAPE-SHIB-PERP positions with unrealized P&L.

    Each position includes:
    - Entry details (price, side, quantity)
    - Market context at entry (funding, L/S, squeeze risk)
    - Prophet context (advice, win probability)
    - Current unrealized P&L: (current - entry) * quantity * direction
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SHIB-PERP not available"}

    try:
        positions = trader.db.get_open_positions()
        current_price = trader.executor.get_current_price()

        # Add unrealized P&L - Perpetual: no contract_size multiplier
        for pos in positions:
            if current_price:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * pos.get("quantity", 0) * direction
                pos["unrealized_pnl"] = round(pnl, 2)
                pos["current_price"] = current_price
            else:
                pos["unrealized_pnl"] = 0
                pos["current_price"] = None

        return {
            "success": True,
            "data": positions,
            "count": len(positions),
            "current_shib_price": current_price,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP positions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(
    limit: int = Query(default=50, le=500, description="Number of trades to return"),
):
    """Get closed/expired trade history."""
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SHIB-PERP not available"}

    try:
        trades = trader.db.get_closed_trades(limit=limit)
        return {
            "success": True,
            "data": trades,
            "count": len(trades),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP closed trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Equity Curve
# ------------------------------------------------------------------

@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to return"),
):
    """Get historical equity curve built from all closed trades.

    Returns EXACT same format as VALOR /paper-equity-curve so that
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
                    "equity": 1000.0,
                    "trades": 0,
                    "return_pct": 0.0,
                }],
                "starting_capital": 1000.0,
                "current_equity": 1000.0,
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

        # Get starting capital from config
        starting_capital = 1000.0
        try:
            cursor.execute(
                "SELECT value FROM autonomous_config WHERE key = 'agape_shib_perp_starting_capital'"
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
            FROM agape_shib_perp_positions
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
                "return_pct": round(cumulative_pnl / starting_capital * 100, 2),
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
        logger.error(f"AGAPE-SHIB-PERP equity curve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/equity-curve/intraday")
async def get_equity_curve_intraday(date: Optional[str] = None):
    """Get today's intraday equity curve matching standard bot format.

    Returns data_points[], snapshots_count, current_equity, day_pnl,
    starting_equity, high_of_day, low_of_day - same format as FORTRESS/SAMSON.
    """
    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    starting_capital = 1000.0

    if not get_connection:
        return _intraday_fallback(today, now, current_time, starting_capital)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config
        cursor.execute("SELECT value FROM autonomous_config WHERE key = 'agape_shib_perp_starting_capital'")
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get intraday snapshots for the requested date
        cursor.execute("""
            SELECT timestamp, equity, unrealized_pnl,
                   realized_pnl_cumulative, open_positions, shib_price
            FROM agape_shib_perp_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        """, (today,))
        snapshots = cursor.fetchall()

        # Get total realized P&L from all closed positions up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM agape_shib_perp_positions
            WHERE status IN ('closed', 'expired', 'stopped')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get today's closed positions P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM agape_shib_perp_positions
            WHERE status IN ('closed', 'expired', 'stopped')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Get today's closed trades with timestamps for accurate intraday cumulative calculation
        cursor.execute("""
            SELECT COALESCE(close_time, open_time)::timestamptz, realized_pnl
            FROM agape_shib_perp_positions
            WHERE status IN ('closed', 'expired', 'stopped')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY COALESCE(close_time, open_time) ASC
        """, (today,))
        today_closes = cursor.fetchall()

        # Calculate unrealized P&L from open positions
        # Perpetual: P&L = (current - entry) * quantity * direction
        unrealized_pnl = 0.0
        open_positions_count = 0

        cursor.execute("""
            SELECT position_id, side, quantity, entry_price
            FROM agape_shib_perp_positions
            WHERE status = 'open'
        """)
        open_rows = cursor.fetchall()
        open_positions_count = len(open_rows)

        if open_rows:
            # Get current SHIB price from latest snapshot or trader
            current_shib_price = None
            if snapshots:
                current_shib_price = float(snapshots[-1][5]) if snapshots[-1][5] else None

            if not current_shib_price:
                # Try from trader
                trader = _get_trader()
                if trader:
                    try:
                        current_shib_price = trader.executor.get_current_price()
                    except Exception:
                        pass

            if current_shib_price:
                for pos_row in open_rows:
                    side = pos_row[1]
                    quantity = float(pos_row[2])
                    entry_price = float(pos_row[3])
                    direction = 1 if side == 'long' else -1
                    pnl = (current_shib_price - entry_price) * quantity * direction
                    unrealized_pnl += pnl

        conn.close()
        conn = None

        # Build intraday data_points (frontend expects this format)
        data_points = []

        # Add market open point (perpetuals trade 24/7, use 00:00 for "day start")
        prev_day_realized = total_realized - today_realized
        market_open_equity = round(starting_capital + prev_day_realized, 2)
        data_points.append({
            "timestamp": f"{today}T00:00:00",
            "time": "00:00:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0
        })

        all_equities = [market_open_equity]

        # Add snapshots with correct cumulative realized at each timestamp
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized_cum, open_count, shib_price = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            # Calculate cumulative realized at this snapshot's timestamp from actual trades
            snap_realized_val = prev_day_realized
            for close_time, close_pnl in today_closes:
                close_time_ct = close_time.astimezone(CENTRAL_TZ) if close_time and close_time.tzinfo else close_time
                if close_time_ct and close_time_ct <= snap_time:
                    snap_realized_val += float(close_pnl or 0)

            snap_unrealized_val = float(snap_unrealized or 0)
            snap_equity = round(starting_capital + snap_realized_val + snap_unrealized_val, 2)
            all_equities.append(snap_equity)

            data_points.append({
                "timestamp": snap_time.isoformat(),
                "time": snap_time.strftime('%H:%M:%S'),
                "equity": snap_equity,
                "cumulative_pnl": round(snap_realized_val + snap_unrealized_val, 2),
                "open_positions": open_count or 0,
                "unrealized_pnl": round(snap_unrealized_val, 2)
            })

        # Add current live point
        current_equity = starting_capital + total_realized + unrealized_pnl
        if today == now.strftime('%Y-%m-%d'):
            total_pnl = total_realized + unrealized_pnl
            current_equity = starting_capital + total_pnl
            all_equities.append(round(current_equity, 2))

            data_points.append({
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": round(current_equity, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "open_positions": open_positions_count,
                "unrealized_pnl": round(unrealized_pnl, 2)
            })

        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "bot": "AGAPE-SHIB-PERP",
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(unrealized_pnl, 2),
            "starting_equity": market_open_equity,
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots),
            "today_closed_count": today_closed_count,
            "open_positions_count": open_positions_count
        }

    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP intraday equity error: {e}")
        import traceback
        traceback.print_exc()
        return _intraday_fallback(today, now, current_time, starting_capital, str(e))
    finally:
        if conn:
            conn.close()


def _intraday_fallback(today, now, current_time, starting_capital, error=None):
    """Return a valid intraday response even when data is unavailable."""
    return {
        "success": error is None,
        "error": error,
        "date": today,
        "bot": "AGAPE-SHIB-PERP",
        "data_points": [{
            "timestamp": now.isoformat(),
            "time": current_time,
            "equity": starting_capital,
            "cumulative_pnl": 0,
            "open_positions": 0,
            "unrealized_pnl": 0
        }],
        "current_equity": starting_capital,
        "day_pnl": 0,
        "day_realized": 0,
        "day_unrealized": 0,
        "starting_equity": starting_capital,
        "high_of_day": starting_capital,
        "low_of_day": starting_capital,
        "snapshots_count": 0,
        "today_closed_count": 0,
        "open_positions_count": 0
    }


# ------------------------------------------------------------------
# Performance
# ------------------------------------------------------------------

@router.get("/performance")
async def get_performance():
    """Get AGAPE-SHIB-PERP performance statistics.

    Returns win rate, total P&L, average win/loss, profit factor, etc.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": {}, "message": "AGAPE-SHIB-PERP not available"}

    try:
        perf = trader.get_performance()
        return {
            "success": True,
            "data": perf,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Logs & Scan Activity
# ------------------------------------------------------------------

@router.get("/logs")
async def get_logs(
    limit: int = Query(default=50, le=200, description="Number of log entries"),
):
    """Get AGAPE-SHIB-PERP activity log."""
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SHIB-PERP not available"}

    try:
        logs = trader.db.get_logs(limit=limit)
        return {
            "success": True,
            "data": logs,
            "count": len(logs),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_scan_activity(
    limit: int = Query(default=50, le=200, description="Number of scans"),
):
    """Get AGAPE-SHIB-PERP scan history - every cycle is logged.

    Shows what the bot saw, what it decided, and why.
    Includes crypto microstructure data, Prophet advice, and signal reasoning.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SHIB-PERP not available"}

    try:
        scans = trader.db.get_scan_activity(limit=limit)
        return {
            "success": True,
            "data": scans,
            "count": len(scans),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP scan activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Market Snapshot (Crypto Microstructure)
# ------------------------------------------------------------------

@router.get("/snapshot")
async def get_crypto_snapshot(
    symbol: str = Query(default="SHIB", description="Crypto symbol"),
):
    """Get current crypto market microstructure snapshot for SHIB.

    Returns the crypto equivalent of WATCHTOWER's gamma snapshot:
    - Funding rate and regime (-> gamma regime)
    - Liquidation clusters (-> gamma walls)
    - Long/Short ratio (-> directional bias)
    - Options OI and max pain (-> flip point)
    - Crypto GEX from Deribit (-> net GEX)
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
            # Funding Rate (-> Gamma Regime)
            "funding": {
                "rate": snapshot.funding_rate.rate if snapshot.funding_rate else None,
                "predicted": snapshot.funding_rate.predicted_rate if snapshot.funding_rate else None,
                "regime": snapshot.funding_regime,
                "annualized": snapshot.funding_rate.annualized_rate if snapshot.funding_rate else None,
                "gex_equivalent": "Replaces gamma regime (POSITIVE/NEGATIVE)",
            },
            # Liquidations (-> Gamma Walls / Magnets)
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
            # L/S Ratio (-> Directional Bias)
            "long_short": {
                "ratio": snapshot.ls_ratio.ratio if snapshot.ls_ratio else None,
                "long_pct": snapshot.ls_ratio.long_pct if snapshot.ls_ratio else None,
                "short_pct": snapshot.ls_ratio.short_pct if snapshot.ls_ratio else None,
                "bias": snapshot.ls_ratio.bias if snapshot.ls_ratio else "NEUTRAL",
                "gex_equivalent": "Replaces GEX directional bias",
            },
            # OI / Max Pain (-> Flip Point)
            "options": {
                "max_pain": snapshot.max_pain,
                "oi_levels_count": len(snapshot.oi_levels),
                "gex_equivalent": "Replaces GEX flip point",
            },
            # Crypto GEX (-> Direct GEX equivalent)
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
        logger.error(f"AGAPE-SHIB-PERP snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Signal Generation (Dry Run)
# ------------------------------------------------------------------

@router.get("/signal")
async def generate_signal():
    """Generate a trade signal without executing (dry run).

    Returns the full signal with:
    - Crypto microstructure analysis
    - Prophet consultation result
    - Recommended action (LONG/SHORT/WAIT)
    - Position sizing and risk levels
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "message": "AGAPE-SHIB-PERP not available"}

    try:
        signal = trader.signals.generate_signal()
        return {
            "success": True,
            "data": signal.to_dict(),
            "is_tradeable": signal.is_valid,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SHIB-PERP signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# GEX Mapping Reference
# ------------------------------------------------------------------

@router.get("/gex-mapping")
async def get_gex_mapping():
    """Returns the GEX -> Crypto signal mapping reference for SHIB perpetuals.

    Educational endpoint showing how equity GEX concepts translate
    to crypto market microstructure signals used by AGAPE-SHIB-PERP.
    """
    return {
        "success": True,
        "data": {
            "title": "AGAPE-SHIB-PERP: GEX -> Crypto Signal Mapping",
            "description": (
                "AGAPE-SHIB-PERP uses crypto market microstructure signals as equivalents "
                "to the GEX-based analysis used by equity bots (FORTRESS, WATCHTOWER, etc.)"
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
                        "Actual gamma exposure calculated from Deribit SHIB options. "
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
                        "predicting reversals. AGAPE-SHIB-PERP uses contrarian logic."
                    ),
                    "data_source": "CoinGlass (aggregated L/S ratio)",
                },
                {
                    "gex_concept": "WATCHTOWER Market Structure (9 signals)",
                    "crypto_equivalent": "Combined Crypto Signals (6 inputs)",
                    "explanation": (
                        "Funding regime + L/S ratio + Liquidation proximity + "
                        "Options OI + Crypto GEX + Squeeze risk -> Combined signal "
                        "(LONG / SHORT / RANGE_BOUND / WAIT)"
                    ),
                },
            ],
            "trade_instrument": {
                "symbol": "SHIB-PERP (Perpetual)",
                "exchange": "Perpetual Contract Exchange",
                "type": "Perpetual Contract",
                "contract_size": "N/A - quantity based",
                "pnl_formula": "(current_price - entry_price) * quantity * direction",
                "margin": "Varies by exchange and leverage",
            },
        },
    }


# ------------------------------------------------------------------
# Bot Control
# ------------------------------------------------------------------

@router.post("/enable")
async def enable_bot():
    """Enable AGAPE-SHIB-PERP trading."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE-SHIB-PERP not available")
    trader.enable()
    return {"success": True, "message": "AGAPE-SHIB-PERP enabled"}


@router.post("/disable")
async def disable_bot():
    """Disable AGAPE-SHIB-PERP trading (positions still managed)."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE-SHIB-PERP not available")
    trader.disable()
    return {"success": True, "message": "AGAPE-SHIB-PERP disabled"}
