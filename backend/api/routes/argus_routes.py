"""
ARGUS (0DTE Gamma Live) API Routes
====================================

API endpoints for the ARGUS real-time 0DTE gamma visualization system.
Provides gamma data, probabilities, alerts, commentary, and historical replay.

ARGUS - Named after the "all-seeing" giant with 100 eyes from Greek mythology.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from zoneinfo import ZoneInfo
import json
import time
import httpx

from database_adapter import get_connection

router = APIRouter(prefix="/api/argus", tags=["ARGUS"])
logger = logging.getLogger(__name__)

# ==================== CACHING ====================
# Simple in-memory cache with TTL
_cache: Dict[str, Any] = {}
_cache_times: Dict[str, float] = {}
CACHE_TTL_SECONDS = 30  # 30 second cache for gamma data
PRICE_CACHE_TTL = 15    # 15 second cache for prices


def get_cached(key: str, ttl: int = CACHE_TTL_SECONDS) -> Any:
    """Get cached value if not expired"""
    if key in _cache and key in _cache_times:
        if time.time() - _cache_times[key] < ttl:
            return _cache[key]
    return None


def set_cached(key: str, value: Any):
    """Set cache value with current time"""
    _cache[key] = value
    _cache_times[key] = time.time()

# Try to import ARGUS engine
ARGUS_AVAILABLE = False
try:
    from core.argus_engine import get_argus_engine, ArgusEngine
    ARGUS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ARGUS engine not available: {e}")

# Try to import Tradier data fetcher
TRADIER_AVAILABLE = False
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tradier data fetcher not available: {e}")


class CommentaryRequest(BaseModel):
    """Request body for generating commentary"""
    force: bool = False


def get_engine() -> Optional[ArgusEngine]:
    """Get the ARGUS engine instance"""
    if not ARGUS_AVAILABLE:
        return None
    try:
        return get_argus_engine()
    except Exception as e:
        logger.error(f"Failed to get ARGUS engine: {e}")
        return None


def get_tradier() -> Optional[TradierDataFetcher]:
    """Get the Tradier data fetcher instance"""
    if not TRADIER_AVAILABLE:
        return None
    try:
        return TradierDataFetcher()
    except Exception as e:
        logger.error(f"Failed to get Tradier fetcher: {e}")
        return None


async def fetch_gamma_data(expiration: str = None) -> dict:
    """
    Fetch gamma data from Tradier API with caching.

    Returns processed options chain with gamma data.
    """
    # Check cache first
    cache_key = f"gamma_data_{expiration or 'today'}"
    cached = get_cached(cache_key, CACHE_TTL_SECONDS)
    if cached:
        logger.debug(f"ARGUS: Returning cached gamma data for {expiration or 'today'}")
        return cached

    tradier = get_tradier()
    if not tradier:
        # Get real prices for mock data
        spot, vix = await get_real_prices()
        result = get_mock_gamma_data(spot, vix)
        set_cached(cache_key, result)
        return result

    try:
        # Get SPY quote
        quote = await tradier.get_quote('SPY')
        spot_price = quote.get('last', 0) or quote.get('close', 0)

        # Get VIX
        vix_quote = await tradier.get_quote('VIX')
        vix = vix_quote.get('last', 0) or 18.0

        # Get expiration (default to 0DTE)
        engine = get_engine()
        if not expiration and engine:
            expiration = engine.get_0dte_expiration()

        # Get options chain
        chain = await tradier.get_options_chain('SPY', expiration)

        # Process chain into strike data
        strikes = []
        for option in chain.get('options', []):
            strike = option.get('strike')
            if not strike:
                continue

            # Find call and put for this strike
            call_data = next((o for o in chain.get('options', [])
                             if o.get('strike') == strike and o.get('option_type') == 'call'), {})
            put_data = next((o for o in chain.get('options', [])
                            if o.get('strike') == strike and o.get('option_type') == 'put'), {})

            strikes.append({
                'strike': strike,
                'call_gamma': call_data.get('greeks', {}).get('gamma', 0) or 0,
                'put_gamma': put_data.get('greeks', {}).get('gamma', 0) or 0,
                'call_oi': call_data.get('open_interest', 0) or 0,
                'put_oi': put_data.get('open_interest', 0) or 0,
                'call_price': call_data.get('last', 0) or call_data.get('mid', 0) or 0,
                'put_price': put_data.get('last', 0) or put_data.get('mid', 0) or 0,
                'call_iv': call_data.get('greeks', {}).get('mid_iv', 0) or 0,
                'put_iv': put_data.get('greeks', {}).get('mid_iv', 0) or 0,
                'volume': (call_data.get('volume', 0) or 0) + (put_data.get('volume', 0) or 0)
            })

        # Deduplicate strikes
        unique_strikes = {}
        for s in strikes:
            if s['strike'] not in unique_strikes:
                unique_strikes[s['strike']] = s

        result = {
            'spot_price': spot_price,
            'vix': vix,
            'expiration': expiration,
            'strikes': list(unique_strikes.values())
        }

        # Cache the result
        set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching gamma data: {e}")
        spot, vix = await get_real_prices()
        result = get_mock_gamma_data(spot, vix)
        set_cached(cache_key, result)
        return result


async def get_real_prices() -> tuple:
    """Fetch real SPY and VIX prices from API"""
    cache_key = "real_prices"
    cached = get_cached(cache_key, PRICE_CACHE_TTL)
    if cached:
        return cached

    try:
        # Try to get real prices from our GEX endpoint
        async with httpx.AsyncClient(timeout=5.0) as client:
            spy_resp = await client.get("http://localhost:8000/api/gex/SPY")
            if spy_resp.status_code == 200:
                spy_data = spy_resp.json()
                spot = spy_data.get('data', {}).get('spot_price', 600.0)
            else:
                spot = 600.0  # Reasonable fallback

            vix_resp = await client.get("http://localhost:8000/api/vix/current")
            if vix_resp.status_code == 200:
                vix_data = vix_resp.json()
                vix = vix_data.get('data', {}).get('vix_spot', 18.0)
            else:
                vix = 18.0  # Reasonable fallback

        result = (spot, vix)
        set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch real prices: {e}")
        return (600.0, 18.0)  # Fallback values


def get_mock_gamma_data(spot: float = None, vix: float = None) -> dict:
    """Return mock gamma data for development/testing"""
    import random

    if spot is None:
        spot = 600.0
    if vix is None:
        vix = 18.0

    strikes = []
    base_strike = round(spot)

    for i in range(-5, 6):  # Fewer strikes, more realistic
        strike = base_strike + i
        distance = abs(i)

        # Simulate gamma distribution (higher near ATM)
        base_gamma = max(0, 0.05 - distance * 0.008)
        call_gamma = base_gamma * (1 + random.uniform(-0.2, 0.2))
        put_gamma = base_gamma * (1 + random.uniform(-0.2, 0.2))

        # Simulate OI - realistic values
        call_oi = int(max(500, 15000 - distance * 2000))
        put_oi = int(max(500, 15000 - distance * 2000))

        strikes.append({
            'strike': strike,
            'call_gamma': call_gamma,
            'put_gamma': put_gamma,
            'call_oi': call_oi,
            'put_oi': put_oi,
            'call_price': max(0.05, (spot - strike) + 2 if i < 0 else max(0.05, 2.0 - i * 0.4)),
            'put_price': max(0.05, (strike - spot) + 2 if i > 0 else max(0.05, 2.0 + i * 0.4)),
            'call_iv': 0.15 + abs(i) * 0.01,
            'put_iv': 0.17 + abs(i) * 0.01,
            'volume': int(max(100, 5000 - distance * 800))
        })

    return {
        'spot_price': spot,
        'vix': vix,
        'expiration': date.today().strftime('%Y-%m-%d'),
        'strikes': strikes
    }


@router.get("/gamma")
async def get_gamma_data(
    expiration: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD"),
    day: Optional[str] = Query(None, description="Day of week: mon, tue, wed, thu, fri")
):
    """
    Get current net gamma data by strike for SPY 0DTE.

    Returns:
    - Net gamma per strike
    - Probabilities
    - Rate of change
    - Magnets, pin, danger zones
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Determine expiration
        if day:
            expiration = engine.get_0dte_expiration(day)
        elif not expiration:
            expiration = engine.get_0dte_expiration('today')

        # Fetch raw data
        raw_data = await fetch_gamma_data(expiration)

        # Process through engine
        snapshot = engine.process_options_chain(
            raw_data,
            raw_data['spot_price'],
            raw_data['vix'],
            expiration
        )

        # Filter strikes to expected move ± 5
        filtered_strikes = engine.filter_strikes_by_expected_move(
            snapshot.strikes,
            snapshot.spot_price,
            snapshot.expected_move,
            extra_strikes=5
        )

        # Get expected move change data (pass spot_price to normalize for overnight gaps)
        em_change = await get_expected_move_change(snapshot.expected_move, raw_data['vix'], snapshot.spot_price)

        # Build response
        return {
            "success": True,
            "data": {
                "symbol": snapshot.symbol,
                "expiration_date": snapshot.expiration_date,
                "snapshot_time": snapshot.snapshot_time.isoformat(),
                "spot_price": snapshot.spot_price,
                "expected_move": snapshot.expected_move,
                "expected_move_change": em_change,
                "vix": snapshot.vix,
                "total_net_gamma": snapshot.total_net_gamma,
                "gamma_regime": snapshot.gamma_regime,
                "regime_flipped": snapshot.regime_flipped,
                "market_status": snapshot.market_status,
                "strikes": [s.to_dict() for s in filtered_strikes],
                "magnets": snapshot.magnets,
                "likely_pin": snapshot.likely_pin,
                "pin_probability": snapshot.pin_probability,
                "danger_zones": snapshot.danger_zones,
                "gamma_flips": snapshot.gamma_flips
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cache for prior day expected move
_em_cache: Dict[str, float] = {}


async def get_expected_move_change(current_em: float, current_vix: float, spot_price: float = None) -> dict:
    """
    Calculate expected move change from prior day.

    IMPORTANT: We compare EM as % of spot (not absolute $) to account for overnight gaps.
    This is essentially comparing implied volatility levels.

    Returns interpretation:
    - DOWN: Bearish (IV contracting)
    - UP: Bullish (IV expanding)
    - FLAT: Range-bound day expected
    - WIDEN: Big move coming (volatility expansion)
    """
    today = date.today().strftime('%Y-%m-%d')
    prior_key = f"em_prior_{today}"

    # Try to get prior day's close expected move AND spot from database
    prior_em = None
    prior_spot = None
    open_em = None
    open_spot = None

    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()

            # Get yesterday's final expected move AND spot price
            cursor.execute("""
                SELECT expected_move, spot_price
                FROM argus_snapshots
                WHERE DATE(snapshot_time) < CURRENT_DATE
                ORDER BY snapshot_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                prior_em = float(row[0])
                prior_spot = float(row[1]) if row[1] else None

            # Get today's opening expected move (first reading of the day)
            cursor.execute("""
                SELECT expected_move, spot_price
                FROM argus_snapshots
                WHERE DATE(snapshot_time) = CURRENT_DATE
                ORDER BY snapshot_time ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                open_em = float(row[0])
                open_spot = float(row[1]) if row[1] else None

            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch prior expected move: {e}")

    # Use cached/current values if DB not available
    if prior_em is None:
        prior_em = _em_cache.get(prior_key, current_em)
    if open_em is None:
        open_em = current_em

    # Store current as potential prior for next calculation
    if prior_key not in _em_cache:
        _em_cache[prior_key] = current_em

    # Calculate EM as % of spot (this normalizes for overnight gaps)
    # EM% = (Expected Move / Spot) * 100
    current_em_pct = (current_em / spot_price * 100) if spot_price and spot_price > 0 else 0
    prior_em_pct = (prior_em / prior_spot * 100) if prior_em and prior_spot and prior_spot > 0 else current_em_pct
    open_em_pct = (open_em / open_spot * 100) if open_em and open_spot and open_spot > 0 else current_em_pct

    # Calculate change in EM% (not absolute $ change)
    # This compares IV levels, not affected by spot price gaps
    pct_change_prior = ((current_em_pct - prior_em_pct) / prior_em_pct * 100) if prior_em_pct and prior_em_pct != 0 else 0

    # Also calculate absolute $ change for display
    change_from_prior = current_em - prior_em if prior_em else 0

    # Thresholds for classification
    FLAT_THRESHOLD = 3.0  # Less than 3% IV change = flat
    WIDEN_THRESHOLD = 12.0  # More than 12% IV expansion = widening

    # Use IV-normalized comparison for signal
    pct_change = pct_change_prior

    if abs(pct_change) < FLAT_THRESHOLD:
        signal = "FLAT"
        interpretation = "Expected move unchanged from prior day - anticipate range-bound price action"
        sentiment = "NEUTRAL"
    elif pct_change > WIDEN_THRESHOLD:
        signal = "WIDEN"
        interpretation = f"Expected move widened +{pct_change:.1f}% from prior day - big move likely coming, prepare for breakout"
        sentiment = "VOLATILE"
    elif pct_change > 0:
        signal = "UP"
        interpretation = f"Expected move UP +{pct_change:.1f}% from prior day - bullish signal"
        sentiment = "BULLISH"
    else:
        signal = "DOWN"
        interpretation = f"Expected move DOWN {pct_change:.1f}% from prior day - bearish signal"
        sentiment = "BEARISH"

    return {
        "current": round(current_em, 2),
        "current_pct": round(current_em_pct, 3),  # EM as % of spot
        "prior_day": round(prior_em, 2) if prior_em else None,
        "prior_day_pct": round(prior_em_pct, 3) if prior_em_pct else None,
        "at_open": round(open_em, 2) if open_em else None,
        "change_dollars": round(change_from_prior, 2),
        "pct_change_prior": round(pct_change_prior, 1),  # % change in IV
        "signal": signal,
        "sentiment": sentiment,
        "interpretation": interpretation
    }


@router.get("/history")
async def get_gamma_history(
    strike: Optional[float] = Query(None, description="Specific strike to get history for"),
    minutes: int = Query(30, description="Minutes of history to return")
):
    """
    Get historical gamma data for the last N minutes.

    Returns gamma values over time for sparkline display.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        history_data = {}

        if strike:
            # Get history for specific strike
            strike_history = engine.history.get(strike, [])
            history_data[strike] = [
                {"time": t.isoformat(), "gamma": g}
                for t, g in strike_history
            ]
        else:
            # Get history for all strikes
            for s, hist in engine.history.items():
                history_data[s] = [
                    {"time": t.isoformat(), "gamma": g}
                    for t, g in hist
                ]

        return {
            "success": True,
            "data": {
                "history": history_data,
                "minutes": minutes
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/probability")
async def get_probability_data():
    """
    Get ML-powered probability per strike.

    Returns hybrid probability (60% ML + 40% gamma-weighted distance).
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        if not engine.previous_snapshot:
            # No data yet, fetch fresh
            raw_data = await fetch_gamma_data()
            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                raw_data['expiration']
            )
        else:
            snapshot = engine.previous_snapshot

        probabilities = [
            {
                "strike": s.strike,
                "probability": s.probability,
                "is_magnet": s.is_magnet,
                "is_pin": s.is_pin
            }
            for s in snapshot.strikes
        ]

        # Sort by probability descending
        probabilities.sort(key=lambda x: x['probability'], reverse=True)

        return {
            "success": True,
            "data": {
                "probabilities": probabilities,
                "likely_pin": snapshot.likely_pin,
                "pin_probability": snapshot.pin_probability,
                "model_type": "hybrid_60ml_40distance"
            }
        }

    except Exception as e:
        logger.error(f"Error getting probability data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_alerts():
    """
    Get active alerts.

    Returns all unacknowledged alerts sorted by priority and time.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        alerts = engine.get_active_alerts()

        # Sort by priority (HIGH first) then by time (newest first)
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        alerts.sort(key=lambda a: (priority_order.get(a['priority'], 3), a['triggered_at']),
                   reverse=False)

        return {
            "success": True,
            "data": {
                "alerts": alerts,
                "count": len(alerts)
            }
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commentary")
async def get_commentary():
    """
    Get latest Claude AI commentary.

    Returns the most recent AI-generated market commentary.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "commentary": [],
                    "message": "Database not connected"
                }
            }

        cursor = conn.cursor()

        # Get latest commentary entries
        cursor.execute("""
            SELECT
                id,
                commentary_text,
                spot_price,
                top_magnet,
                likely_pin,
                pin_probability,
                danger_zones,
                vix,
                created_at
            FROM argus_commentary
            ORDER BY created_at DESC
            LIMIT 10
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        commentary = []
        for row in rows:
            commentary.append({
                "id": row[0],
                "text": row[1],
                "spot_price": float(row[2]) if row[2] else None,
                "top_magnet": float(row[3]) if row[3] else None,
                "likely_pin": float(row[4]) if row[4] else None,
                "pin_probability": float(row[5]) if row[5] else None,
                "danger_zones": row[6] if row[6] else [],
                "vix": float(row[7]) if row[7] else None,
                "timestamp": row[8].isoformat() if row[8] else None
            })

        return {
            "success": True,
            "data": {
                "commentary": commentary
            }
        }

    except Exception as e:
        logger.error(f"Error getting commentary: {e}")
        # Return empty commentary if table doesn't exist yet
        return {
            "success": True,
            "data": {
                "commentary": [],
                "message": "No commentary available yet"
            }
        }


@router.post("/commentary/generate")
async def generate_commentary(request: CommentaryRequest = None):
    """
    Trigger generation of new Claude AI commentary.

    This is called every 5 minutes by the scheduler or manually.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Get current snapshot
        if not engine.previous_snapshot:
            raw_data = await fetch_gamma_data()
            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                raw_data['expiration']
            )
        else:
            snapshot = engine.previous_snapshot

        # Generate commentary using Claude
        try:
            from core.argus_commentary import generate_argus_commentary
            commentary = await generate_argus_commentary(snapshot)
        except ImportError:
            # Fallback if commentary module not ready
            commentary = generate_fallback_commentary(snapshot)

        # Store in database
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO argus_commentary
                    (commentary_text, spot_price, top_magnet, likely_pin,
                     pin_probability, danger_zones, vix)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    commentary,
                    snapshot.spot_price,
                    snapshot.magnets[0]['strike'] if snapshot.magnets else None,
                    snapshot.likely_pin,
                    snapshot.pin_probability,
                    json.dumps(snapshot.danger_zones),
                    snapshot.vix
                ))
                conn.commit()
                cursor.close()
                conn.close()
        except Exception as db_error:
            logger.warning(f"Could not store commentary in DB: {db_error}")

        return {
            "success": True,
            "data": {
                "commentary": commentary,
                "generated_at": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error generating commentary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_fallback_commentary(snapshot) -> str:
    """Generate basic commentary without Claude API"""
    now = datetime.now(ZoneInfo("America/New_York"))
    time_str = now.strftime("%I:%M %p ET")

    # Build commentary
    lines = [f"🕐 {time_str} - 5-Minute Update", ""]

    # Gamma structure
    if snapshot.magnets:
        top_magnets = ", ".join([f"{m['strike']} ({m['probability']:.0f}%)"
                                 for m in snapshot.magnets[:3]])
        lines.append(f"📊 GAMMA STRUCTURE: Top magnets at {top_magnets}")
    else:
        lines.append(f"📊 GAMMA STRUCTURE: Net gamma is {snapshot.gamma_regime.lower()}")

    # Regime change
    if snapshot.regime_flipped:
        lines.append(f"⚡ REGIME CHANGE: Flipped from {snapshot.previous_regime} to {snapshot.gamma_regime}")

    # Gamma flips
    if snapshot.gamma_flips:
        flip_strikes = ", ".join([str(f['strike']) for f in snapshot.gamma_flips[:3]])
        lines.append(f"🔄 GAMMA FLIPS: Strikes {flip_strikes} changed sign")

    # Pin prediction
    if snapshot.likely_pin:
        lines.append(f"🎯 PIN PREDICTION: {snapshot.likely_pin} strike "
                    f"({snapshot.pin_probability:.0f}% probability)")

    # Danger zones
    if snapshot.danger_zones:
        dz_list = ", ".join([f"{d['strike']} ({d['danger_type']})"
                            for d in snapshot.danger_zones[:3]])
        lines.append(f"⚠️ DANGER ZONES: {dz_list}")

    # Market context
    lines.append(f"📈 CONTEXT: SPY ${snapshot.spot_price:.2f}, "
                f"VIX {snapshot.vix:.1f}, Expected move ±${snapshot.expected_move:.2f}")

    return "\n".join(lines)


@router.get("/bots")
async def get_bot_positions():
    """
    Get active bot positions for ARGUS context.

    Shows what ARES, ATHENA, PHOENIX are doing relative to gamma structure.
    """
    try:
        positions = []

        # Check ARES positions
        try:
            from backend.api.routes.ares_routes import get_ares_positions
            ares_data = await get_ares_positions()
            if ares_data.get('success') and ares_data.get('data', {}).get('positions'):
                for pos in ares_data['data']['positions']:
                    positions.append({
                        'bot': 'ARES',
                        'strategy': 'Iron Condor',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike')}/{pos.get('call_short_strike')}",
                        'safe': True  # Will be calculated based on magnets
                    })
        except Exception:
            pass

        # Check ATHENA positions
        try:
            from backend.api.routes.athena_routes import get_athena_positions
            athena_data = await get_athena_positions()
            if athena_data.get('success') and athena_data.get('data', {}).get('positions'):
                for pos in athena_data['data']['positions']:
                    positions.append({
                        'bot': 'ATHENA',
                        'strategy': pos.get('strategy', 'Directional'),
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', 'N/A')),
                        'safe': True
                    })
        except Exception:
            pass

        return {
            "success": True,
            "data": {
                "positions": positions,
                "count": len(positions)
            }
        }

    except Exception as e:
        logger.error(f"Error getting bot positions: {e}")
        return {
            "success": True,
            "data": {
                "positions": [],
                "count": 0
            }
        }


@router.get("/accuracy")
async def get_accuracy_metrics():
    """
    Get prediction accuracy metrics.

    Shows rolling accuracy for pin predictions, direction, magnet hit rate.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": get_default_accuracy()
            }

        cursor = conn.cursor()

        # Get latest accuracy metrics
        cursor.execute("""
            SELECT
                metric_date,
                pin_accuracy_7d,
                pin_accuracy_30d,
                direction_accuracy_7d,
                direction_accuracy_30d,
                magnet_hit_rate_7d,
                magnet_hit_rate_30d,
                total_predictions
            FROM argus_accuracy
            ORDER BY metric_date DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return {
                "success": True,
                "data": {
                    "date": row[0].isoformat() if row[0] else None,
                    "pin_accuracy_7d": float(row[1]) if row[1] else 0,
                    "pin_accuracy_30d": float(row[2]) if row[2] else 0,
                    "direction_accuracy_7d": float(row[3]) if row[3] else 0,
                    "direction_accuracy_30d": float(row[4]) if row[4] else 0,
                    "magnet_hit_rate_7d": float(row[5]) if row[5] else 0,
                    "magnet_hit_rate_30d": float(row[6]) if row[6] else 0,
                    "total_predictions": row[7] or 0
                }
            }
        else:
            return {
                "success": True,
                "data": get_default_accuracy()
            }

    except Exception as e:
        logger.error(f"Error getting accuracy metrics: {e}")
        return {
            "success": True,
            "data": get_default_accuracy()
        }


def get_default_accuracy() -> dict:
    """Return default accuracy metrics"""
    return {
        "date": None,
        "pin_accuracy_7d": 0,
        "pin_accuracy_30d": 0,
        "direction_accuracy_7d": 0,
        "direction_accuracy_30d": 0,
        "magnet_hit_rate_7d": 0,
        "magnet_hit_rate_30d": 0,
        "total_predictions": 0,
        "message": "No accuracy data available yet - predictions will be tracked over time"
    }


@router.get("/patterns")
async def get_pattern_matches():
    """
    Get pattern match analysis.

    Compares current gamma structure to historical patterns.
    """
    engine = get_engine()
    if not engine or not engine.previous_snapshot:
        return {
            "success": True,
            "data": {
                "patterns": [],
                "message": "No pattern data available yet"
            }
        }

    try:
        # This would use historical data to find similar patterns
        # For now, return placeholder
        return {
            "success": True,
            "data": {
                "patterns": [],
                "current_structure": {
                    "gamma_regime": engine.previous_snapshot.gamma_regime,
                    "top_magnet": engine.previous_snapshot.magnets[0]['strike']
                        if engine.previous_snapshot.magnets else None,
                    "likely_pin": engine.previous_snapshot.likely_pin
                },
                "message": "Pattern matching will be available after collecting more historical data"
            }
        }

    except Exception as e:
        logger.error(f"Error getting pattern matches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_data(
    format: str = Query("excel", description="Export format: excel, csv"),
    date: Optional[str] = Query(None, description="Date to export YYYY-MM-DD")
):
    """
    Export ARGUS data to Excel or CSV.

    Returns downloadable file with gamma data, commentary, and alerts.
    """
    # This would generate and return an Excel file
    # For now, return the data as JSON
    try:
        engine = get_engine()
        if not engine or not engine.previous_snapshot:
            raise HTTPException(status_code=404, detail="No data to export")

        snapshot = engine.previous_snapshot

        export_data = {
            "snapshot": snapshot.to_dict(),
            "alerts": engine.get_active_alerts(),
            "export_time": datetime.now().isoformat(),
            "format_requested": format
        }

        return {
            "success": True,
            "data": export_data,
            "message": "Excel export will be implemented - returning JSON for now"
        }

    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay")
async def get_replay_data(
    date: str = Query(..., description="Date to replay YYYY-MM-DD"),
    time: Optional[str] = Query(None, description="Time to get HH:MM")
):
    """
    Get historical replay data for a specific date/time.

    Returns gamma structure as it was at that point in time.
    """
    try:
        conn = get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="Database not connected")

        cursor = conn.cursor()

        # Build query based on whether time is specified
        if time:
            cursor.execute("""
                SELECT
                    s.id,
                    s.snapshot_time,
                    s.spot_price,
                    s.expected_move,
                    s.vix,
                    s.total_net_gamma,
                    s.gamma_regime
                FROM argus_snapshots s
                WHERE DATE(s.snapshot_time) = %s
                AND s.snapshot_time::time <= %s::time
                ORDER BY s.snapshot_time DESC
                LIMIT 1
            """, (date, time))
        else:
            cursor.execute("""
                SELECT
                    s.id,
                    s.snapshot_time,
                    s.spot_price,
                    s.expected_move,
                    s.vix,
                    s.total_net_gamma,
                    s.gamma_regime
                FROM argus_snapshots s
                WHERE DATE(s.snapshot_time) = %s
                ORDER BY s.snapshot_time DESC
                LIMIT 1
            """, (date,))

        snapshot = cursor.fetchone()

        if not snapshot:
            cursor.close()
            conn.close()
            return {
                "success": True,
                "data": None,
                "message": f"No data available for {date}"
            }

        snapshot_id = snapshot[0]

        # Get strikes for this snapshot
        cursor.execute("""
            SELECT
                strike,
                net_gamma,
                probability,
                is_magnet,
                magnet_rank,
                is_pin
            FROM argus_strikes
            WHERE snapshot_id = %s
            ORDER BY strike
        """, (snapshot_id,))

        strikes = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "snapshot_time": snapshot[1].isoformat() if snapshot[1] else None,
                "spot_price": float(snapshot[2]) if snapshot[2] else None,
                "expected_move": float(snapshot[3]) if snapshot[3] else None,
                "vix": float(snapshot[4]) if snapshot[4] else None,
                "total_net_gamma": float(snapshot[5]) if snapshot[5] else None,
                "gamma_regime": snapshot[6],
                "strikes": [
                    {
                        "strike": float(s[0]),
                        "net_gamma": float(s[1]) if s[1] else 0,
                        "probability": float(s[2]) if s[2] else 0,
                        "is_magnet": s[3],
                        "magnet_rank": s[4],
                        "is_pin": s[5]
                    }
                    for s in strikes
                ]
            }
        }

    except Exception as e:
        logger.error(f"Error getting replay data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay/dates")
async def get_available_replay_dates():
    """
    Get list of dates available for historical replay.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "dates": [],
                    "message": "Database not connected"
                }
            }

        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT DATE(snapshot_time) as date
            FROM argus_snapshots
            ORDER BY date DESC
            LIMIT 90
        """)

        dates = [row[0].isoformat() for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "dates": dates,
                "count": len(dates)
            }
        }

    except Exception as e:
        logger.error(f"Error getting replay dates: {e}")
        return {
            "success": True,
            "data": {
                "dates": [],
                "message": "No historical data available yet"
            }
        }


@router.get("/context")
async def get_market_context():
    """
    Get additional market context from regime analysis.

    Returns:
    - IV Rank & Percentile
    - Gamma wall proximity
    - Psychology trap alerts
    - VIX context with spike detection
    - Multi-timeframe RSI alignment
    - Monthly magnets
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": get_default_context(),
                "message": "Database not connected"
            }

        cursor = conn.cursor()

        # Get latest regime signal with full context
        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                -- Gamma Walls
                nearest_call_wall,
                call_wall_distance_pct,
                call_wall_strength,
                nearest_put_wall,
                put_wall_distance_pct,
                put_wall_strength,
                net_gamma_regime,
                -- Psychology Traps
                psychology_trap,
                liberation_setup_detected,
                liberation_target_strike,
                false_floor_detected,
                false_floor_strike,
                path_of_least_resistance,
                polr_confidence,
                -- VIX
                vix_current,
                vix_spike_detected,
                volatility_regime,
                -- RSI
                rsi_5m,
                rsi_15m,
                rsi_1h,
                rsi_4h,
                rsi_1d,
                rsi_aligned_overbought,
                rsi_aligned_oversold,
                -- Monthly Magnets
                monthly_magnet_above,
                monthly_magnet_below,
                -- Regime
                primary_regime_type,
                confidence_score,
                trade_direction,
                risk_level
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {
                "success": True,
                "data": get_default_context(),
                "message": "No regime data available"
            }

        return {
            "success": True,
            "data": {
                "timestamp": row[0].isoformat() if row[0] else None,
                "spy_price": float(row[1]) if row[1] else None,
                "gamma_walls": {
                    "call_wall": float(row[2]) if row[2] else None,
                    "call_wall_distance": float(row[3]) if row[3] else None,
                    "call_wall_strength": row[4],
                    "put_wall": float(row[5]) if row[5] else None,
                    "put_wall_distance": float(row[6]) if row[6] else None,
                    "put_wall_strength": row[7],
                    "net_gamma_regime": row[8]
                },
                "psychology_traps": {
                    "active_trap": row[9],
                    "liberation_setup": row[10] or False,
                    "liberation_target": float(row[11]) if row[11] else None,
                    "false_floor": row[12] or False,
                    "false_floor_strike": float(row[13]) if row[13] else None,
                    "polr": row[14],
                    "polr_confidence": float(row[15]) if row[15] else None
                },
                "vix_context": {
                    "current": float(row[16]) if row[16] else None,
                    "spike_detected": row[17] or False,
                    "volatility_regime": row[18]
                },
                "rsi_alignment": {
                    "rsi_5m": float(row[19]) if row[19] else None,
                    "rsi_15m": float(row[20]) if row[20] else None,
                    "rsi_1h": float(row[21]) if row[21] else None,
                    "rsi_4h": float(row[22]) if row[22] else None,
                    "rsi_1d": float(row[23]) if row[23] else None,
                    "aligned_overbought": row[24] or False,
                    "aligned_oversold": row[25] or False
                },
                "monthly_magnets": {
                    "above": float(row[26]) if row[26] else None,
                    "below": float(row[27]) if row[27] else None
                },
                "regime": {
                    "type": row[28],
                    "confidence": float(row[29]) if row[29] else None,
                    "direction": row[30],
                    "risk_level": row[31]
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting market context: {e}")
        return {
            "success": True,
            "data": get_default_context(),
            "message": f"Error: {str(e)}"
        }


def get_default_context() -> dict:
    """Return default context when data unavailable"""
    return {
        "gamma_walls": {
            "call_wall": None,
            "call_wall_distance": None,
            "put_wall": None,
            "put_wall_distance": None
        },
        "psychology_traps": {
            "active_trap": None,
            "liberation_setup": False,
            "false_floor": False
        },
        "vix_context": {
            "current": None,
            "spike_detected": False
        },
        "rsi_alignment": {},
        "monthly_magnets": {},
        "regime": {}
    }


@router.get("/expirations")
async def get_expirations():
    """
    Get available 0DTE expirations for the week.

    SPY has 0DTE every day (Mon-Fri).
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        today = date.today()
        expirations = []

        for day in ['mon', 'tue', 'wed', 'thu', 'fri']:
            exp_date = engine.get_0dte_expiration(day)
            exp_date_obj = datetime.strptime(exp_date, '%Y-%m-%d').date()

            expirations.append({
                'day': day.upper(),
                'date': exp_date,
                'is_today': exp_date_obj == today,
                'is_past': exp_date_obj < today,
                'is_future': exp_date_obj > today
            })

        return {
            "success": True,
            "data": {
                "expirations": expirations,
                "today": today.strftime('%Y-%m-%d')
            }
        }

    except Exception as e:
        logger.error(f"Error getting expirations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
