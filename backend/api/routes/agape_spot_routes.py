"""
AGAPE-SPOT API Routes - Multi-ticker, long-only 24/7 Coinbase Spot trading.

Supports: ETH-USD, XRP-USD, SHIB-USD, DOGE-USD
LONG-ONLY: P&L = (current_price - entry_price) * quantity (always long).

All endpoints accept an optional ``?ticker=`` query param to filter by a
specific ticker (e.g. ``ETH-USD``).  When omitted the endpoint returns data
aggregated across ALL active tickers.

Standard bot endpoints:
  /tickers        - Supported tickers with per-coin config
  /summary        - Overview of all tickers: P&L, positions, win rate, price
  /status         - Bot health and config (per-ticker or combined)
  /positions      - Open positions with unrealized P&L
  /closed-trades  - Completed trade history
  /equity-curve   - Historical equity curve (optional ?ticker=, omit for combined)
  /equity-curve/intraday - Today's intraday equity (optional ?ticker=, omit for combined)
  /performance    - Win rate, P&L, statistics
  /logs           - Activity log
  /scan-activity  - Scan history (every cycle logged)
  /snapshot       - Current crypto market microstructure
  /signal         - Generate a signal (dry run)
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape-spot", tags=["AGAPE-SPOT"])

CENTRAL_TZ = ZoneInfo("America/Chicago")

# ---------------------------------------------------------------------------
# Graceful imports
# ---------------------------------------------------------------------------

AGAPE_SPOT_AVAILABLE = False
get_agape_spot_trader = None
create_agape_spot_trader = None
SPOT_TICKERS: Dict = {}

try:
    from trading.agape_spot.trader import get_agape_spot_trader, create_agape_spot_trader
    from trading.agape_spot.models import SPOT_TICKERS
    AGAPE_SPOT_AVAILABLE = True
    logger.info("AGAPE-SPOT Routes: AgapeSpotTrader loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SPOT Routes: AgapeSpotTrader not available: {e}")

CRYPTO_PROVIDER_AVAILABLE = False
get_crypto_data_provider = None
try:
    from data.crypto_data_provider import get_crypto_data_provider
    CRYPTO_PROVIDER_AVAILABLE = True
except ImportError:
    pass

# Database adapter (used by equity-curve raw SQL path)
get_connection = None
try:
    from database_adapter import get_connection
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_trader():
    """Get or lazily create the AGAPE-SPOT trader singleton."""
    if not AGAPE_SPOT_AVAILABLE:
        return None
    trader = get_agape_spot_trader()
    if trader is None:
        try:
            trader = create_agape_spot_trader()
        except Exception as e:
            logger.error(f"AGAPE-SPOT Routes: Failed to create trader: {e}")
    return trader


def _format_ct(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now(CENTRAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S CT")


_VALID_TICKERS = {"ETH-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"}


def _validate_ticker(ticker: Optional[str]) -> Optional[str]:
    """Validate a ticker string.  Returns the normalised ticker or None."""
    if ticker is None:
        return None
    ticker = ticker.strip().upper()
    if ticker not in _VALID_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker '{ticker}'. Supported: {sorted(_VALID_TICKERS)}",
        )
    return ticker


# ---------------------------------------------------------------------------
# Ticker & Summary endpoints (NEW)
# ---------------------------------------------------------------------------

@router.get("/tickers")
async def list_tickers():
    """List all supported tickers with their per-coin configuration.

    Returns capital allocation, display names, order sizing, etc.
    """
    trader = _get_trader()
    active_tickers: List[str] = []
    if trader:
        active_tickers = list(trader.config.tickers)

    live_tickers: List[str] = []
    if trader:
        live_tickers = list(trader.config.live_tickers)

    tickers_out = {}
    for ticker_key, cfg in SPOT_TICKERS.items():
        tickers_out[ticker_key] = {
            **cfg,
            "active": ticker_key in active_tickers,
            "mode": "live" if ticker_key in live_tickers else "paper",
        }

    return {
        "success": True,
        "data": tickers_out,
        "active_tickers": active_tickers,
        "live_tickers": live_tickers,
        "count": len(tickers_out),
        "fetched_at": _format_ct(),
    }


@router.get("/summary")
async def get_summary():
    """Overview of ALL tickers: per-ticker P&L, positions, win rate, current price.

    This is the primary multi-ticker dashboard endpoint.
    """
    trader = _get_trader()
    if not trader:
        return {
            "success": False,
            "data_unavailable": True,
            "reason": "AGAPE-SPOT trader not initialized",
            "message": "AGAPE-SPOT module not available",
        }

    try:
        tickers = trader.config.tickers
        per_ticker: Dict[str, Dict] = {}
        totals = {
            "starting_capital": 0.0,
            "current_balance": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_pnl": 0.0,
            "open_positions": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
        }

        for ticker in tickers:
            current_price = trader.executor.get_current_price(ticker)
            starting_capital = trader.config.get_starting_capital(ticker)

            open_positions = trader.db.get_open_positions(ticker=ticker)
            closed_trades = trader.db.get_closed_trades(ticker=ticker, limit=10000)

            # Unrealized P&L (long-only)
            unrealized_pnl = 0.0
            if current_price and open_positions:
                for pos in open_positions:
                    qty = pos.get("quantity", pos.get("eth_quantity", 0))
                    unrealized_pnl += (current_price - pos["entry_price"]) * qty

            realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades) if closed_trades else 0.0
            total_pnl = realized_pnl + unrealized_pnl
            current_balance = starting_capital + total_pnl

            wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0] if closed_trades else []
            losses_list = [t for t in closed_trades if (t.get("realized_pnl") or 0) <= 0] if closed_trades else []
            win_rate = round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None

            display_name = SPOT_TICKERS.get(ticker, {}).get("display_name", ticker)

            is_live = trader.config.is_live(ticker)

            # Bayesian win tracker data
            win_tracker_data = None
            if hasattr(trader, '_win_trackers'):
                wt = trader._win_trackers.get(ticker)
                if wt:
                    win_tracker_data = wt.to_dict()

            per_ticker[ticker] = {
                "ticker": ticker,
                "display_name": display_name,
                "mode": "live" if is_live else "paper",
                "current_price": current_price,
                "starting_capital": starting_capital,
                "current_balance": round(current_balance, 2),
                "realized_pnl": round(realized_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "total_pnl": round(total_pnl, 2),
                "return_pct": round(total_pnl / starting_capital * 100, 2) if starting_capital else 0,
                "open_positions": len(open_positions),
                "total_trades": len(closed_trades) if closed_trades else 0,
                "wins": len(wins),
                "losses": len(losses_list),
                "win_rate": win_rate,
                "win_tracker": win_tracker_data,
            }

            totals["starting_capital"] += starting_capital
            totals["current_balance"] += current_balance
            totals["realized_pnl"] += realized_pnl
            totals["unrealized_pnl"] += unrealized_pnl
            totals["total_pnl"] += total_pnl
            totals["open_positions"] += len(open_positions)
            totals["total_trades"] += len(closed_trades) if closed_trades else 0
            totals["wins"] += len(wins)
            totals["losses"] += len(losses_list)

        # Round totals
        for key in ("starting_capital", "current_balance", "realized_pnl",
                     "unrealized_pnl", "total_pnl"):
            totals[key] = round(totals[key], 2)
        totals["return_pct"] = (
            round(totals["total_pnl"] / totals["starting_capital"] * 100, 2)
            if totals["starting_capital"] else 0
        )
        totals["win_rate"] = (
            round(totals["wins"] / totals["total_trades"] * 100, 1)
            if totals["total_trades"] else None
        )

        return {
            "success": True,
            "data": {
                "tickers": per_ticker,
                "totals": totals,
            },
            "active_tickers": list(tickers),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Bot Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker (e.g. ETH-USD)"),
):
    """Get AGAPE-SPOT bot status, configuration, and open positions.

    If ``?ticker=`` is provided, returns status for that single ticker.
    Otherwise returns a combined summary across all tickers.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {
            "success": False,
            "data_unavailable": True,
            "reason": "AGAPE-SPOT trader not initialized",
            "message": "AGAPE-SPOT module not available",
        }

    try:
        status = trader.get_status(ticker=ticker)
        return {
            "success": True,
            "data": status,
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@router.get("/positions")
async def get_positions(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker (e.g. ETH-USD)"),
):
    """Get open AGAPE-SPOT positions with unrealized P&L.

    LONG-ONLY: P&L = (current_price - entry_price) * quantity.
    Each position dict includes a ``ticker`` field.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SPOT not available"}

    try:
        positions = trader.db.get_open_positions(ticker=ticker)

        # Compute unrealized P&L per position, grouping price lookups by ticker
        price_cache: Dict[str, Optional[float]] = {}
        for pos in positions:
            pos_ticker = pos.get("ticker", "ETH-USD")
            if pos_ticker not in price_cache:
                price_cache[pos_ticker] = trader.executor.get_current_price(pos_ticker)

            current_price = price_cache[pos_ticker]
            if current_price:
                qty = pos.get("quantity", pos.get("eth_quantity", 0))
                pnl = (current_price - pos["entry_price"]) * qty
                pos["unrealized_pnl"] = round(pnl, 2)
                pos["current_price"] = current_price
            else:
                pos["unrealized_pnl"] = 0
                pos["current_price"] = None

        return {
            "success": True,
            "data": positions,
            "count": len(positions),
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT positions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker (e.g. ETH-USD)"),
    limit: int = Query(default=50, le=500, description="Number of trades to return"),
):
    """Get closed/expired trade history, optionally filtered by ticker."""
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SPOT not available"}

    try:
        trades = trader.db.get_closed_trades(ticker=ticker, limit=limit)
        return {
            "success": True,
            "data": trades,
            "count": len(trades),
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT closed trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Equity Curve
# ---------------------------------------------------------------------------

@router.get("/equity-curve")
async def get_equity_curve(
    ticker: Optional[str] = Query(
        default=None,
        description="Ticker to build the equity curve for (e.g. ETH-USD). "
                    "Omit or pass 'ALL' for a combined curve across all coins.",
    ),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to return"),
):
    """Get historical equity curve built from closed trades.

    When ``?ticker=`` is a specific coin, returns that coin's equity curve.
    When omitted (ALL view), returns the combined equity curve across all coins.

    Format matches the standard MultiBotEquityCurve component:
    ``{ equity_curve: [...], points: N, days: N, timestamp: "..." }``
    """
    # Allow "ALL" as a special value
    if ticker and ticker.strip().upper() == "ALL":
        ticker = None
    else:
        ticker = _validate_ticker(ticker)

    is_combined = ticker is None

    # Determine starting capital
    trader = _get_trader()
    if is_combined:
        # Combined: sum of all tickers' starting_capital
        starting_capital = sum(
            tc.get("starting_capital", 1000.0) for tc in SPOT_TICKERS.values()
        )
        display_ticker = "ALL"
    else:
        if trader:
            starting_capital = trader.config.get_starting_capital(ticker)
        else:
            starting_capital = SPOT_TICKERS.get(ticker, {}).get("starting_capital", 1000.0)
        display_ticker = ticker

    now = datetime.now(CENTRAL_TZ)

    if not get_connection:
        return _equity_curve_empty(now, starting_capital, days, display_ticker)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if is_combined:
            # Combined: get ALL closed trades across all tickers
            cursor.execute("""
                SELECT
                    (close_time AT TIME ZONE 'America/Chicago')::date AS trade_date,
                    realized_pnl,
                    ticker,
                    position_id
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND close_time IS NOT NULL
                  AND realized_pnl IS NOT NULL
                ORDER BY close_time ASC
            """)
        else:
            # Single ticker
            cursor.execute("""
                SELECT
                    (close_time AT TIME ZONE 'America/Chicago')::date AS trade_date,
                    realized_pnl,
                    ticker,
                    position_id
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND close_time IS NOT NULL
                  AND realized_pnl IS NOT NULL
                  AND ticker = %s
                ORDER BY close_time ASC
            """, (ticker,))
        rows = cursor.fetchall()

        if not rows:
            return _equity_curve_empty(now, starting_capital, days, display_ticker)

        # Aggregate by day
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
                "return_pct": round(cumulative_pnl / starting_capital * 100, 2) if starting_capital else 0,
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
            "ticker": display_ticker,
            "points": len(equity_curve),
            "days": days,
            "timestamp": now.isoformat(),
        }

    except Exception as e:
        logger.error(f"AGAPE-SPOT equity curve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


def _equity_curve_empty(now: datetime, starting_capital: float, days: int, ticker: str):
    """Return a valid equity curve response when no trade data exists."""
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
        "ticker": ticker,
        "points": 1,
        "days": days,
        "timestamp": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Intraday Equity Curve
# ---------------------------------------------------------------------------

@router.get("/equity-curve/intraday")
async def get_equity_curve_intraday(
    ticker: Optional[str] = Query(
        default=None,
        description="Ticker for intraday equity (e.g. ETH-USD). Omit for combined.",
    ),
    date: Optional[str] = None,
):
    """Get today's intraday equity curve.

    When ``?ticker=`` is provided, returns per-ticker snapshots.
    When omitted (or ``ALL``), returns a combined view summing all tickers.

    Returns data_points[], snapshots_count, current_equity, day_pnl,
    starting_equity, high_of_day, low_of_day -- same format as FORTRESS/SAMSON.

    AGAPE-SPOT trades 24/7 so "day start" is midnight CT.
    """
    ticker = _validate_ticker(ticker)

    # Support "ALL" as explicit combined keyword
    if ticker and ticker.strip().upper() == "ALL":
        ticker = None

    # Combined intraday: aggregate all tickers
    if ticker is None:
        return await _get_combined_intraday_equity(date)

    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    # Starting capital for this ticker
    trader = _get_trader()
    if trader:
        starting_capital = trader.config.get_starting_capital(ticker)
    else:
        starting_capital = SPOT_TICKERS.get(ticker, {}).get("starting_capital", 1000.0)

    if not get_connection:
        return _intraday_fallback(today, now, current_time, starting_capital, ticker)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get intraday snapshots for this ticker
        cursor.execute("""
            SELECT timestamp, equity, unrealized_pnl,
                   realized_pnl_cumulative, open_positions, eth_price
            FROM agape_spot_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
              AND ticker = %s
            ORDER BY timestamp ASC
        """, (today, ticker))
        snapshots = cursor.fetchall()

        # Total realized P&L from all closed positions for this ticker up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND ticker = %s
              AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (ticker, today))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Today's closed positions P&L for this ticker
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND ticker = %s
              AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (ticker, today))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Today's closed trades with timestamps for accurate intraday cumulative
        cursor.execute("""
            SELECT COALESCE(close_time, open_time)::timestamptz, realized_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND ticker = %s
              AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY COALESCE(close_time, open_time) ASC
        """, (ticker, today))
        today_closes = cursor.fetchall()

        # Calculate unrealized P&L from open positions for this ticker
        # LONG-ONLY: P&L = (current - entry) * quantity
        unrealized_pnl = 0.0
        open_positions_count = 0

        cursor.execute("""
            SELECT position_id, quantity, entry_price
            FROM agape_spot_positions
            WHERE status = 'open' AND ticker = %s
        """, (ticker,))
        open_rows = cursor.fetchall()
        open_positions_count = len(open_rows)

        if open_rows:
            # Get current price from latest snapshot or trader
            current_ticker_price = None
            if snapshots:
                current_ticker_price = float(snapshots[-1][5]) if snapshots[-1][5] else None

            if not current_ticker_price and trader:
                try:
                    current_ticker_price = trader.executor.get_current_price(ticker)
                except Exception:
                    pass

            if current_ticker_price:
                for pos_row in open_rows:
                    quantity = float(pos_row[1]) if pos_row[1] else 0
                    entry_price = float(pos_row[2])
                    # Long-only P&L
                    pnl = (current_ticker_price - entry_price) * quantity
                    unrealized_pnl += pnl

        conn.close()
        conn = None

        # Build intraday data_points (frontend expects this format)
        data_points = []

        # Day start point (AGAPE-SPOT 24/7 -- midnight CT as day start)
        prev_day_realized = total_realized - today_realized
        market_open_equity = round(starting_capital + prev_day_realized, 2)
        data_points.append({
            "timestamp": f"{today}T00:00:00",
            "time": "00:00:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0,
        })

        all_equities = [market_open_equity]

        # Add snapshots with correct cumulative realized at each timestamp
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized_cum, open_count, price = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            # Cumulative realized at this snapshot's timestamp from actual trades
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
                "time": snap_time.strftime("%H:%M:%S"),
                "equity": snap_equity,
                "cumulative_pnl": round(snap_realized_val + snap_unrealized_val, 2),
                "open_positions": open_count or 0,
                "unrealized_pnl": round(snap_unrealized_val, 2),
            })

        # Add current live point
        current_equity = starting_capital + total_realized + unrealized_pnl
        if today == now.strftime("%Y-%m-%d"):
            total_pnl = total_realized + unrealized_pnl
            current_equity = starting_capital + total_pnl
            all_equities.append(round(current_equity, 2))

            data_points.append({
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": round(current_equity, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "open_positions": open_positions_count,
                "unrealized_pnl": round(unrealized_pnl, 2),
            })

        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "ticker": ticker,
            "bot": "AGAPE-SPOT",
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
            "open_positions_count": open_positions_count,
        }

    except Exception as e:
        logger.error(f"AGAPE-SPOT intraday equity error: {e}")
        import traceback
        traceback.print_exc()
        return _intraday_fallback(today, now, current_time, starting_capital, ticker, str(e))
    finally:
        if conn:
            conn.close()


async def _get_combined_intraday_equity(date: Optional[str] = None):
    """Aggregate intraday equity across ALL tickers for the combined view."""
    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    # Total starting capital across all tickers
    total_starting = sum(
        tc.get("starting_capital", 1000.0) for tc in SPOT_TICKERS.values()
    )

    if not get_connection:
        return _intraday_fallback(today, now, current_time, total_starting, "ALL")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all intraday snapshots across all tickers, bucketed by 5-min intervals
        cursor.execute("""
            SELECT
                date_trunc('minute', timestamp::timestamptz AT TIME ZONE 'America/Chicago')
                    - (EXTRACT(MINUTE FROM timestamp::timestamptz AT TIME ZONE 'America/Chicago')::int %% 5) * interval '1 minute'
                    AS bucket,
                SUM(equity) AS total_equity,
                SUM(COALESCE(unrealized_pnl, 0)) AS total_unrealized,
                SUM(COALESCE(realized_pnl_cumulative, 0)) AS total_realized_cum,
                SUM(COALESCE(open_positions, 0)) AS total_open
            FROM agape_spot_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
            GROUP BY bucket
            ORDER BY bucket ASC
        """, (today,))
        bucketed = cursor.fetchall()

        # Total realized P&L across all tickers up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time IS NOT NULL AND realized_pnl IS NOT NULL
              AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        row = cursor.fetchone()
        total_realized_all = float(row[0]) if row and row[0] else 0.0

        # Today's realized P&L across all tickers
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time IS NOT NULL AND realized_pnl IS NOT NULL
              AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        trow = cursor.fetchone()
        today_realized = float(trow[0]) if trow and trow[0] else 0.0
        today_closed_count = int(trow[1]) if trow and trow[1] else 0

        # Current open positions unrealized P&L across all tickers
        total_unrealized = 0.0
        total_open_count = 0
        trader = _get_trader()

        for t_ticker in _VALID_TICKERS:
            cursor.execute("""
                SELECT position_id, quantity, entry_price
                FROM agape_spot_positions
                WHERE status = 'open' AND ticker = %s
            """, (t_ticker,))
            open_rows = cursor.fetchall()
            total_open_count += len(open_rows)

            if open_rows and trader:
                try:
                    price = trader.executor.get_current_price(t_ticker)
                    if price:
                        for pos_row in open_rows:
                            qty = float(pos_row[1]) if pos_row[1] else 0
                            entry = float(pos_row[2])
                            total_unrealized += (price - entry) * qty
                except Exception:
                    pass

        conn.close()
        conn = None

        # Build data points
        prev_day_realized = total_realized_all - today_realized
        market_open_equity = round(total_starting + prev_day_realized, 2)

        data_points = [{
            "timestamp": f"{today}T00:00:00",
            "time": "00:00:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0,
        }]
        all_equities = [market_open_equity]

        for bucket_row in bucketed:
            bucket_ts, tot_eq, tot_unreal, tot_real_cum, tot_open = bucket_row
            eq_val = float(tot_eq) if tot_eq else market_open_equity
            all_equities.append(round(eq_val, 2))

            bucket_time = bucket_ts
            if hasattr(bucket_ts, 'strftime'):
                time_str = bucket_ts.strftime("%H:%M:%S")
                ts_str = bucket_ts.isoformat()
            else:
                time_str = str(bucket_ts)
                ts_str = str(bucket_ts)

            data_points.append({
                "timestamp": ts_str,
                "time": time_str,
                "equity": round(eq_val, 2),
                "cumulative_pnl": round(float(tot_real_cum or 0) + float(tot_unreal or 0), 2),
                "open_positions": int(tot_open or 0),
                "unrealized_pnl": round(float(tot_unreal or 0), 2),
            })

        # Live current point
        current_equity = round(total_starting + total_realized_all + total_unrealized, 2)
        if today == now.strftime("%Y-%m-%d"):
            all_equities.append(current_equity)
            data_points.append({
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": current_equity,
                "cumulative_pnl": round(total_realized_all + total_unrealized, 2),
                "open_positions": total_open_count,
                "unrealized_pnl": round(total_unrealized, 2),
            })

        high_of_day = max(all_equities) if all_equities else total_starting
        low_of_day = min(all_equities) if all_equities else total_starting
        day_pnl = today_realized + total_unrealized

        return {
            "success": True,
            "date": today,
            "ticker": "ALL",
            "bot": "AGAPE-SPOT",
            "data_points": data_points,
            "current_equity": current_equity,
            "day_pnl": round(day_pnl, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(total_unrealized, 2),
            "starting_equity": market_open_equity,
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(bucketed),
            "today_closed_count": today_closed_count,
            "open_positions_count": total_open_count,
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT combined intraday equity error: {e}")
        import traceback
        traceback.print_exc()
        return _intraday_fallback(today, now, current_time, total_starting, "ALL", str(e))
    finally:
        if conn:
            conn.close()


def _intraday_fallback(today, now, current_time, starting_capital, ticker, error=None):
    """Return a valid intraday response even when data is unavailable."""
    return {
        "success": error is None,
        "error": error,
        "date": today,
        "ticker": ticker,
        "bot": "AGAPE-SPOT",
        "data_points": [{
            "timestamp": now.isoformat(),
            "time": current_time,
            "equity": starting_capital,
            "cumulative_pnl": 0,
            "open_positions": 0,
            "unrealized_pnl": 0,
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
        "open_positions_count": 0,
    }


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

@router.get("/performance")
async def get_performance(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker (e.g. ETH-USD)"),
):
    """Get AGAPE-SPOT performance statistics.

    Returns win rate, total P&L, average win/loss, profit factor, etc.
    If ``?ticker=`` is provided, scoped to that ticker; otherwise all tickers.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "data": {}, "message": "AGAPE-SPOT not available"}

    try:
        perf = trader.get_performance(ticker=ticker)
        return {
            "success": True,
            "data": perf,
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Logs & Scan Activity
# ---------------------------------------------------------------------------

@router.get("/logs")
async def get_logs(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker"),
    limit: int = Query(default=50, le=200, description="Number of log entries"),
):
    """Get AGAPE-SPOT activity log, optionally filtered by ticker."""
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SPOT not available"}

    try:
        logs = trader.db.get_logs(ticker=ticker, limit=limit)
        return {
            "success": True,
            "data": logs,
            "count": len(logs),
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_scan_activity(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker"),
    limit: int = Query(default=50, le=200, description="Number of scans"),
):
    """Get AGAPE-SPOT scan history -- every cycle is logged.

    Shows what the bot saw, what it decided, and why.
    Includes crypto microstructure data, Prophet advice, and signal reasoning.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SPOT not available"}

    try:
        scans = trader.db.get_scan_activity(ticker=ticker, limit=limit)
        return {
            "success": True,
            "data": scans,
            "count": len(scans),
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT scan activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Market Snapshot (Crypto Microstructure)
# ---------------------------------------------------------------------------

@router.get("/snapshot")
async def get_crypto_snapshot(
    symbol: str = Query(default="ETH", description="Crypto symbol (e.g. ETH, XRP, DOGE, SHIB)"),
):
    """Get current crypto market microstructure snapshot.

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
        logger.error(f"AGAPE-SPOT snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Signal Generation (Dry Run)
# ---------------------------------------------------------------------------

@router.get("/signal")
async def generate_signal(
    ticker: Optional[str] = Query(
        default=None,
        description="Ticker to generate signal for (e.g. ETH-USD). "
                    "If omitted, generates for all active tickers.",
    ),
):
    """Generate a trade signal without executing (dry run).

    Returns the full signal with:
    - Crypto microstructure analysis
    - Prophet consultation result
    - Recommended action (LONG/WAIT)
    - Position sizing and risk levels

    If ``?ticker=`` provided, returns a single signal.
    Otherwise returns signals for ALL active tickers.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        return {"success": False, "message": "AGAPE-SPOT not available"}

    try:
        if ticker:
            signal = trader.signals.generate_signal(ticker=ticker)
            return {
                "success": True,
                "data": signal.to_dict() if signal else None,
                "is_tradeable": signal.is_valid if signal else False,
                "ticker": ticker,
                "fetched_at": _format_ct(),
            }

        # Generate for all active tickers
        all_signals = {}
        for t in trader.config.tickers:
            try:
                sig = trader.signals.generate_signal(ticker=t)
                all_signals[t] = {
                    "signal": sig.to_dict() if sig else None,
                    "is_tradeable": sig.is_valid if sig else False,
                }
            except Exception as e:
                all_signals[t] = {"signal": None, "is_tradeable": False, "error": str(e)}

        return {
            "success": True,
            "data": all_signals,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Bot Control
# ---------------------------------------------------------------------------

@router.post("/enable")
async def enable_bot():
    """Enable AGAPE-SPOT trading."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE-SPOT not available")
    trader.enable()
    return {"success": True, "message": "AGAPE-SPOT enabled"}


@router.post("/disable")
async def disable_bot():
    """Disable AGAPE-SPOT trading (positions still managed)."""
    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE-SPOT not available")
    trader.disable()
    return {"success": True, "message": "AGAPE-SPOT disabled"}


@router.get("/diagnostic")
async def diagnostic():
    """Diagnostic endpoint to troubleshoot data issues.

    Checks database connection, table structure, column existence,
    row counts, and trader initialization -- everything needed to
    figure out why the frontend shows empty data.
    """
    result = {
        "agape_spot_available": AGAPE_SPOT_AVAILABLE,
        "db_connection": False,
        "table_exists": False,
        "columns": [],
        "has_account_label": False,
        "has_quantity_column": False,
        "has_eth_quantity_column": False,
        "open_positions_count": 0,
        "closed_positions_count": 0,
        "equity_snapshots_count": 0,
        "scan_activity_count": 0,
        "trader_initialized": False,
        "trader_error": None,
        "sample_closed_trade": None,
        "query_tests": {},
    }

    # 1. Check database connection
    conn = None
    try:
        if get_connection:
            conn = get_connection()
            result["db_connection"] = conn is not None
    except Exception as e:
        result["db_connection"] = False
        result["trader_error"] = f"DB connection failed: {e}"

    # 2. Check table structure
    if conn:
        try:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'agape_spot_positions'
                )
            """)
            result["table_exists"] = cursor.fetchone()[0]

            if result["table_exists"]:
                # Get column names
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'agape_spot_positions'
                    ORDER BY ordinal_position
                """)
                columns = [row[0] for row in cursor.fetchall()]
                result["columns"] = columns
                result["has_account_label"] = "account_label" in columns
                result["has_quantity_column"] = "quantity" in columns
                result["has_eth_quantity_column"] = "eth_quantity" in columns

                # Row counts
                cursor.execute(
                    "SELECT COUNT(*) FROM agape_spot_positions WHERE status = 'open'"
                )
                result["open_positions_count"] = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM agape_spot_positions "
                    "WHERE status IN ('closed', 'expired', 'stopped')"
                )
                result["closed_positions_count"] = cursor.fetchone()[0]

                # Sample closed trade (most recent)
                cursor.execute("""
                    SELECT position_id, ticker, entry_price, close_price,
                           realized_pnl, close_reason, close_time
                    FROM agape_spot_positions
                    WHERE status IN ('closed', 'expired', 'stopped')
                      AND close_time IS NOT NULL
                    ORDER BY close_time DESC LIMIT 1
                """)
                sample = cursor.fetchone()
                if sample:
                    result["sample_closed_trade"] = {
                        "position_id": sample[0],
                        "ticker": sample[1],
                        "entry_price": float(sample[2]) if sample[2] else None,
                        "close_price": float(sample[3]) if sample[3] else None,
                        "realized_pnl": float(sample[4]) if sample[4] else None,
                        "close_reason": sample[5],
                        "close_time": sample[6].isoformat() if sample[6] else None,
                    }

                # Test the actual queries used by get_open_positions and get_closed_trades
                try:
                    cursor.execute("""
                        SELECT position_id, COALESCE(account_label, 'default')
                        FROM agape_spot_positions WHERE status = 'open' LIMIT 1
                    """)
                    result["query_tests"]["open_positions_query"] = "OK"
                except Exception as e:
                    result["query_tests"]["open_positions_query"] = f"FAILED: {e}"
                    conn.rollback()

                try:
                    cursor.execute("""
                        SELECT position_id, COALESCE(account_label, 'default')
                        FROM agape_spot_positions
                        WHERE status IN ('closed', 'expired', 'stopped') LIMIT 1
                    """)
                    result["query_tests"]["closed_trades_query"] = "OK"
                except Exception as e:
                    result["query_tests"]["closed_trades_query"] = f"FAILED: {e}"
                    conn.rollback()

                # Test equity curve query (no account_label)
                try:
                    cursor.execute("""
                        SELECT COUNT(*) FROM agape_spot_positions
                        WHERE status IN ('closed', 'expired', 'stopped')
                          AND close_time IS NOT NULL
                          AND realized_pnl IS NOT NULL
                    """)
                    result["query_tests"]["equity_curve_query"] = (
                        f"OK ({cursor.fetchone()[0]} rows)"
                    )
                except Exception as e:
                    result["query_tests"]["equity_curve_query"] = f"FAILED: {e}"
                    conn.rollback()

            # Check equity snapshots table
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM agape_spot_equity_snapshots"
                )
                result["equity_snapshots_count"] = cursor.fetchone()[0]
            except Exception:
                pass

            # Check scan activity table
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM agape_spot_scan_activity"
                )
                result["scan_activity_count"] = cursor.fetchone()[0]
            except Exception:
                pass

            cursor.close()
        except Exception as e:
            result["trader_error"] = f"Table check failed: {e}"
        finally:
            conn.close()

    # 3. Check trader initialization
    try:
        trader = _get_trader()
        result["trader_initialized"] = trader is not None
        if trader:
            result["trader_cycle_count"] = trader._cycle_count
            result["trader_enabled"] = trader._enabled
            result["trader_tickers"] = trader.config.tickers
            result["trader_live_tickers"] = trader.config.live_tickers
            result["coinbase_connected"] = trader.executor.has_any_client
    except Exception as e:
        result["trader_error"] = f"Trader init failed: {e}"

    return {"success": True, "diagnostic": result, "fetched_at": _format_ct()}


@router.get("/accounts")
async def get_accounts():
    """List all connected Coinbase accounts with status.

    Shows default account, per-ticker dedicated accounts, and which
    tickers are live vs paper.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": [], "message": "AGAPE-SPOT not available"}

    try:
        accounts = []
        for ticker in trader.config.tickers:
            is_live = trader.config.is_live(ticker)
            has_client = trader.executor._get_client(ticker) is not None
            has_dedicated = ticker in trader.executor._ticker_clients
            cfg = SPOT_TICKERS.get(ticker, {})

            accounts.append({
                "ticker": ticker,
                "display_name": cfg.get("display_name", ticker),
                "mode": "live" if is_live else "paper",
                "coinbase_connected": has_client,
                "account_type": "dedicated" if has_dedicated else "default",
                "live_capital": cfg.get("live_capital", cfg.get("starting_capital", 0)),
                "starting_capital": cfg.get("starting_capital", 0),
            })

        return {
            "success": True,
            "data": accounts,
            "has_default_client": trader.executor._client is not None,
            "dedicated_tickers": list(trader.executor._ticker_clients.keys()),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT accounts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account-balances")
async def get_account_balances():
    """Get real Coinbase account balances (USD + crypto holdings).

    Returns balances from all connected accounts (default + dedicated).
    Only available when Coinbase API is connected.
    """
    trader = _get_trader()
    if not trader:
        return {"success": False, "data": {}, "message": "AGAPE-SPOT not available"}

    try:
        balances = trader.executor.get_all_account_balances()
        return {
            "success": True,
            "data": balances,
            "accounts_queried": len(balances),
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT account balances error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution-quality")
async def get_execution_quality(
    ticker: Optional[str] = Query(default=None, description="Filter by ticker"),
    limit: int = Query(default=100, le=500, description="Number of trades to analyze"),
):
    """Analyze execution quality: slippage, fees, and fill performance.

    Shows entry/exit slippage distribution, total fees paid, and
    average execution quality across recent trades.
    """
    ticker = _validate_ticker(ticker)

    if not get_connection:
        return {"success": False, "data": {}, "message": "No database connection"}

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Query trades with execution details
        sql = """
            SELECT
                position_id, ticker, entry_price, close_price,
                entry_slippage_pct, exit_slippage_pct,
                entry_fee_usd, exit_fee_usd,
                coinbase_order_id, coinbase_sell_order_id,
                realized_pnl, close_time, account_label
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time IS NOT NULL
        """
        params: list = []
        if ticker:
            sql += " AND ticker = %s"
            params.append(ticker)
        sql += " ORDER BY close_time DESC LIMIT %s"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        trades = []
        total_entry_slippage = 0.0
        total_exit_slippage = 0.0
        total_fees = 0.0
        slippage_count = 0
        fee_count = 0
        has_order_id_count = 0

        for row in rows:
            entry_slip = float(row[4]) if row[4] is not None else None
            exit_slip = float(row[5]) if row[5] is not None else None
            entry_fee = float(row[6]) if row[6] is not None else None
            exit_fee = float(row[7]) if row[7] is not None else None
            has_order = row[8] is not None

            trade = {
                "position_id": row[0],
                "ticker": row[1],
                "entry_price": float(row[2]) if row[2] else None,
                "close_price": float(row[3]) if row[3] else None,
                "entry_slippage_pct": entry_slip,
                "exit_slippage_pct": exit_slip,
                "entry_fee_usd": entry_fee,
                "exit_fee_usd": exit_fee,
                "has_coinbase_order_id": has_order,
                "has_coinbase_sell_order_id": row[9] is not None,
                "realized_pnl": float(row[10]) if row[10] else None,
                "close_time": row[11].isoformat() if row[11] else None,
                "account_label": row[12] or "default",
            }
            trades.append(trade)

            if entry_slip is not None:
                total_entry_slippage += abs(entry_slip)
                slippage_count += 1
            if exit_slip is not None:
                total_exit_slippage += abs(exit_slip)
                slippage_count += 1
            if entry_fee is not None:
                total_fees += entry_fee
                fee_count += 1
            if exit_fee is not None:
                total_fees += exit_fee
                fee_count += 1
            if has_order:
                has_order_id_count += 1

        avg_entry_slippage = (
            round(total_entry_slippage / slippage_count, 4)
            if slippage_count > 0 else None
        )

        return {
            "success": True,
            "data": {
                "trades": trades,
                "summary": {
                    "total_trades_analyzed": len(trades),
                    "trades_with_order_id": has_order_id_count,
                    "trades_with_slippage_data": slippage_count,
                    "avg_slippage_pct": avg_entry_slippage,
                    "total_fees_usd": round(total_fees, 2),
                    "avg_fee_per_trade": (
                        round(total_fees / fee_count, 2)
                        if fee_count > 0 else None
                    ),
                },
            },
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT execution quality error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/force-close")
async def force_close_positions(
    ticker: Optional[str] = Query(default=None, description="Close positions for this ticker only"),
    reason: str = Query(default="MANUAL_CLOSE", description="Close reason"),
):
    """Force-close all open positions, optionally filtered by ticker.

    LONG-ONLY: P&L = (exit_price - entry_price) * quantity.
    """
    ticker = _validate_ticker(ticker)

    trader = _get_trader()
    if not trader:
        raise HTTPException(status_code=503, detail="AGAPE-SPOT not available")

    try:
        result = trader.force_close_all(ticker=ticker, reason=reason)
        return {
            "success": True,
            "data": result,
            "ticker_filter": ticker,
            "fetched_at": _format_ct(),
        }
    except Exception as e:
        logger.error(f"AGAPE-SPOT force-close error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
