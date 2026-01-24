"""
AI Intelligence Enhancement Routes
Provides 7 advanced AI features for profitable trading with transparency and actionability.

Features:
1. Pre-Trade Safety Checklist - Validates trades before execution
2. Real-Time Trade Explainer - Explains WHY trades were taken with price targets
3. Daily Trading Plan Generator - Generates daily action plan at market open
4. Position Management Assistant - Live guidance for open positions
5. Market Commentary Widget - Real-time market narration
6. Strategy Comparison Engine - Compares available strategies
7. Option Greeks Explainer - Context-aware Greeks education
"""

import logging
from database_adapter import get_connection
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import psycopg2.extras
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# RESPONSE CACHE - Eliminates AI generation lag on page load
# ============================================================================
# Cache stores AI-generated responses with timestamps to avoid regenerating
# on every request. Significantly reduces page load time from ~5s to <100ms.

_response_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

# Cache TTL configuration (in seconds)
# Reduced from original values to provide fresher market data
CACHE_TTL = {
    'daily_trading_plan': 5 * 60,     # 5 minutes - fresh data for trading decisions
    'market_commentary': 2 * 60,       # 2 minutes - near real-time commentary
    'intelligence_feed': 2 * 60,       # 2 minutes - unified intelligence dashboard
}


def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if valid and not expired."""
    with _cache_lock:
        if cache_key not in _response_cache:
            return None

        cached = _response_cache[cache_key]
        cached_at = cached.get('cached_at')
        ttl = CACHE_TTL.get(cache_key, 300)

        if cached_at and (datetime.now() - cached_at).total_seconds() < ttl:
            logger.debug(f"[CACHE HIT] {cache_key} - returning cached response")
            return cached.get('response')

        logger.debug(f"[CACHE EXPIRED] {cache_key} - regenerating")
        return None


def set_cached_response(cache_key: str, response: Dict[str, Any]) -> None:
    """Store response in cache with timestamp."""
    with _cache_lock:
        _response_cache[cache_key] = {
            'response': response,
            'cached_at': datetime.now()
        }
        logger.debug(f"[CACHE SET] {cache_key} - stored for {CACHE_TTL.get(cache_key, 300)}s")


def get_gex_context(market_data: Dict[str, Any], gex: Dict[str, Any]) -> str:
    """
    Generate actionable GEX context based on current market positioning.
    Returns interpretation of GEX levels relative to spot price.
    """
    spot = float(market_data.get('spot_price') or 0)
    net_gex = float(market_data.get('net_gex') or 0)
    call_wall = float(gex.get('call_wall') or 0)
    put_wall = float(gex.get('put_wall') or 0)
    flip_point = float(gex.get('flip_point') or 0)

    if spot == 0:
        return "GEX data unavailable"

    # Calculate distances
    dist_to_call = ((call_wall - spot) / spot * 100) if call_wall > 0 else 0
    dist_to_put = ((spot - put_wall) / spot * 100) if put_wall > 0 else 0
    dist_to_flip = ((spot - flip_point) / spot * 100) if flip_point > 0 else 0

    # Determine GEX regime
    gex_billions = net_gex / 1e9
    if gex_billions > 2:
        gex_regime = "STRONGLY POSITIVE (dealers short gamma - will buy dips, sell rips = MEAN REVERSION)"
    elif gex_billions > 0:
        gex_regime = "POSITIVE (dealers will dampen moves = RANGE-BOUND, SELL PREMIUM)"
    elif gex_billions > -2:
        gex_regime = "NEGATIVE (dealers long gamma - will amplify moves = TRENDING)"
    else:
        gex_regime = "STRONGLY NEGATIVE (dealers will chase moves = HIGH VOLATILITY, DIRECTIONAL PLAYS)"

    # Position relative to flip point
    if spot > flip_point and flip_point > 0:
        flip_position = f"ABOVE flip point by {dist_to_flip:.1f}% - bullish dealer hedging"
    elif flip_point > 0:
        flip_position = f"BELOW flip point by {abs(dist_to_flip):.1f}% - bearish dealer hedging"
    else:
        flip_position = "Flip point data unavailable"

    # Key level proximity
    if dist_to_call < 0.5 and call_wall > 0:
        proximity = f"NEAR CALL WALL ({dist_to_call:.2f}% away) - expect resistance, potential reversal"
    elif dist_to_put < 0.5 and put_wall > 0:
        proximity = f"NEAR PUT WALL ({dist_to_put:.2f}% away) - expect support, potential bounce"
    elif call_wall > 0 and put_wall > 0:
        proximity = f"MID-RANGE: {dist_to_put:.1f}% above put wall, {dist_to_call:.1f}% below call wall"
    else:
        proximity = "Wall data unavailable"

    return f"""GEX INTERPRETATION:
• Regime: {gex_regime}
• Position: {flip_position}
• Proximity: {proximity}
• Call Wall Distance: {dist_to_call:.1f}% (${call_wall:.0f})
• Put Wall Distance: {dist_to_put:.1f}% (${put_wall:.0f})

TRADING IMPLICATIONS:
{_get_trading_implications(gex_billions, dist_to_call, dist_to_put, spot > flip_point)}"""


def _get_trading_implications(gex_b: float, dist_call: float, dist_put: float, above_flip: bool) -> str:
    """Generate specific trading implications based on GEX positioning."""
    implications = []

    # GEX-based strategy
    if gex_b > 2:
        implications.append("• SELL PREMIUM: High positive GEX = low volatility expected, iron condors/credit spreads favored")
        implications.append("• FADE MOVES: Mean reversion likely, sell rallies and buy dips")
    elif gex_b > 0:
        implications.append("• RANGE TRADING: Positive GEX dampens moves, trade between walls")
        implications.append("• THETA PLAYS: Reduced volatility benefits time decay strategies")
    elif gex_b > -2:
        implications.append("• DIRECTIONAL BIAS: Negative GEX amplifies trends, go with momentum")
        implications.append("• TIGHTER STOPS: Moves can accelerate, manage risk carefully")
    else:
        implications.append("• HIGH CONVICTION ONLY: Extreme negative GEX = violent moves possible")
        implications.append("• REDUCE SIZE: Volatility expansion likely, wider stops needed")

    # Wall proximity
    if dist_call < 1.0:
        implications.append(f"• RESISTANCE AHEAD: {dist_call:.1f}% to call wall, expect selling pressure")
    if dist_put < 1.0:
        implications.append(f"• SUPPORT NEARBY: {dist_put:.1f}% to put wall, expect buying support")

    # Flip point positioning
    if above_flip:
        implications.append("• BULLISH STRUCTURE: Above flip point, dealers hedge by buying")
    else:
        implications.append("• BEARISH STRUCTURE: Below flip point, dealers hedge by selling")

    return "\n".join(implications)


try:
    from ai.autonomous_ai_reasoning import AutonomousAIReasoning
except ImportError:
    AutonomousAIReasoning = None

try:
    from ai.ai_trade_advisor import AITradeAdvisor
except ImportError:
    AITradeAdvisor = None

try:
    from ai.langchain_prompts import (
        get_market_analysis_prompt,
        get_trade_recommendation_prompt,
        get_educational_prompt
    )
except ImportError:
    # Fallback if langchain_prompts doesn't exist
    get_market_analysis_prompt = lambda: ""
    get_trade_recommendation_prompt = lambda: ""
    get_educational_prompt = lambda: ""

try:
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    ChatAnthropic = None
    LANGCHAIN_AVAILABLE = False

# Import live data sources
TradingVolatilityAPI = None
try:
    from core_classes_and_engines import TradingVolatilityAPI
    logger.info("TradingVolatilityAPI loaded")
except ImportError as e:
    logger.debug(f"TradingVolatilityAPI import failed: {type(e).__name__}")

get_vix = None
get_price = None
try:
    from data.unified_data_provider import get_vix, get_price
    logger.info("Unified Data Provider loaded")
except ImportError as e:
    logger.debug(f"Unified Data Provider import failed: {type(e).__name__}")

router = APIRouter(prefix="/api/ai-intelligence", tags=["AI Intelligence"])


# ============================================================================
# LIVE DATA FETCHING HELPERS
# ============================================================================

def get_live_market_data(symbol: str = 'SPY') -> Dict[str, Any]:
    """
    Fetch LIVE market data from available sources.
    Returns dict with spot_price, vix, net_gex, call_wall, put_wall, flip_point
    """
    data = {
        'spot_price': 0,
        'vix': 15.0,
        'net_gex': 0,
        'call_wall': 0,
        'put_wall': 0,
        'flip_point': 0,
        'data_source': 'default'
    }

    # Try TradingVolatilityAPI for GEX data
    if TradingVolatilityAPI:
        try:
            api = TradingVolatilityAPI()
            gex_data = api.get_net_gamma(symbol)
            if gex_data and 'error' not in gex_data:
                data['spot_price'] = float(gex_data.get('spot_price') or 0)
                data['net_gex'] = float(gex_data.get('net_gex') or 0)
                data['call_wall'] = float(gex_data.get('call_wall') or 0)
                data['put_wall'] = float(gex_data.get('put_wall') or 0)
                data['flip_point'] = float(gex_data.get('flip_point') or 0)
                data['data_source'] = 'TradingVolatilityAPI'
                logger.debug(f"get_live_market_data: Got GEX from API - spot={data['spot_price']}")
        except Exception as e:
            logger.debug(f"get_live_market_data: TradingVolatilityAPI error: {type(e).__name__}")

    # Try Unified Data Provider for VIX
    if get_vix:
        try:
            vix_value = get_vix()
            if vix_value and vix_value > 0:
                data['vix'] = float(vix_value)
                logger.debug(f"get_live_market_data: Got VIX from Unified Provider - vix={data['vix']}")
        except Exception as e:
            logger.debug(f"get_live_market_data: get_vix error: {type(e).__name__}")

    # Fallback: Try gex_history database
    if data['data_source'] == 'default':
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT spot_price, net_gex, call_wall, put_wall, flip_point
                FROM gex_history
                WHERE symbol = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            conn.close()
            if row:
                data['spot_price'] = float(row.get('spot_price') or 0)
                data['net_gex'] = float(row.get('net_gex') or 0)
                data['call_wall'] = float(row.get('call_wall') or 0)
                data['put_wall'] = float(row.get('put_wall') or 0)
                data['flip_point'] = float(row.get('flip_point') or 0)
                data['data_source'] = 'gex_history_database'
                logger.debug(f"get_live_market_data: Got GEX from database - spot={data['spot_price']}")
        except Exception as e:
            logger.debug(f"get_live_market_data: Database fallback error: {type(e).__name__}")

    return data


def get_live_psychology_regime(symbol: str = 'SPY') -> Dict[str, Any]:
    """
    Determine market regime from GEX data.
    """
    regime_data = {
        'regime_type': 'UNKNOWN',
        'confidence': 50,
        'psychology_trap': None
    }

    market_data = get_live_market_data(symbol)
    net_gex = market_data.get('net_gex', 0)
    spot_price = market_data.get('spot_price', 0)
    flip_point = market_data.get('flip_point', 0)

    # Determine regime based on GEX
    if net_gex >= 3e9:
        regime_data['regime_type'] = 'POSITIVE_GAMMA_PINNING'
        regime_data['confidence'] = 85
    elif net_gex >= 1e9:
        regime_data['regime_type'] = 'MODERATE_POSITIVE'
        regime_data['confidence'] = 70
    elif net_gex <= -3e9:
        regime_data['regime_type'] = 'NEGATIVE_GAMMA_AMPLIFY'
        regime_data['confidence'] = 85
    elif net_gex <= -1e9:
        regime_data['regime_type'] = 'MODERATE_NEGATIVE'
        regime_data['confidence'] = 70
    else:
        regime_data['regime_type'] = 'NEUTRAL'
        regime_data['confidence'] = 60

    # Check for flip point proximity (potential trap)
    if flip_point > 0 and spot_price > 0:
        distance_to_flip = abs(spot_price - flip_point) / spot_price * 100
        if distance_to_flip < 0.5:  # Within 0.5% of flip
            regime_data['psychology_trap'] = 'FLIP_POINT_CRITICAL'

    return regime_data


# ============================================================================
# ENHANCED DATA FETCHING - Options Flow, Historical GEX, Skew, Momentum
# ============================================================================

def get_options_flow_data() -> Dict[str, Any]:
    """
    Fetch latest options flow data for smart money indicators.
    Updates every 5 minutes.
    """
    flow_data = {
        'put_call_ratio': 1.0,
        'unusual_call_volume': 0,
        'unusual_put_volume': 0,
        'unusual_strikes': [],
        'sentiment': 'NEUTRAL',
        'smart_money_signal': None,
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute("""
            SELECT put_call_ratio, unusual_call_volume, unusual_put_volume,
                   unusual_strikes, timestamp
            FROM options_flow
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = c.fetchone()

        if row:
            pc_ratio = float(row.get('put_call_ratio') or 1.0)
            flow_data['put_call_ratio'] = pc_ratio
            flow_data['unusual_call_volume'] = int(row.get('unusual_call_volume') or 0)
            flow_data['unusual_put_volume'] = int(row.get('unusual_put_volume') or 0)
            flow_data['unusual_strikes'] = row.get('unusual_strikes') or []
            flow_data['updated_at'] = row.get('timestamp').isoformat() if row.get('timestamp') else None

            # Interpret sentiment
            if pc_ratio > 1.3:
                flow_data['sentiment'] = 'BEARISH'
                flow_data['smart_money_signal'] = 'High put activity - institutions hedging or bearish'
            elif pc_ratio < 0.7:
                flow_data['sentiment'] = 'BULLISH'
                flow_data['smart_money_signal'] = 'High call activity - institutions positioning bullish'
            elif flow_data['unusual_call_volume'] > flow_data['unusual_put_volume'] * 2:
                flow_data['sentiment'] = 'BULLISH'
                flow_data['smart_money_signal'] = 'Unusual call volume detected'
            elif flow_data['unusual_put_volume'] > flow_data['unusual_call_volume'] * 2:
                flow_data['sentiment'] = 'BEARISH'
                flow_data['smart_money_signal'] = 'Unusual put volume detected'

        conn.close()
    except Exception as e:
        logger.debug(f"get_options_flow_data error: {e}")

    return flow_data


def get_historical_gex_context() -> Dict[str, Any]:
    """
    Fetch historical GEX for day-over-day comparison.
    Updates every 5 minutes.
    """
    history = {
        'yesterday_gex': 0,
        'today_gex': 0,
        'gex_change': 0,
        'gex_trend': 'FLAT',
        'flip_point_movement': 'STABLE',
        'yesterday_flip': 0,
        'today_flip': 0,
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get today's latest GEX
        c.execute("""
            SELECT net_gex, flip_point, timestamp
            FROM gex_history
            WHERE symbol = 'SPY' AND timestamp >= CURRENT_DATE
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        today_row = c.fetchone()

        # Get yesterday's closing GEX
        c.execute("""
            SELECT net_gex, flip_point, timestamp
            FROM gex_history
            WHERE symbol = 'SPY' AND timestamp < CURRENT_DATE
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        yesterday_row = c.fetchone()

        if today_row:
            history['today_gex'] = float(today_row.get('net_gex') or 0)
            history['today_flip'] = float(today_row.get('flip_point') or 0)
            history['updated_at'] = today_row.get('timestamp').isoformat() if today_row.get('timestamp') else None

        if yesterday_row:
            history['yesterday_gex'] = float(yesterday_row.get('net_gex') or 0)
            history['yesterday_flip'] = float(yesterday_row.get('flip_point') or 0)

        # Calculate changes
        if history['yesterday_gex'] != 0:
            history['gex_change'] = history['today_gex'] - history['yesterday_gex']
            change_pct = (history['gex_change'] / abs(history['yesterday_gex'])) * 100 if history['yesterday_gex'] else 0

            if change_pct > 20:
                history['gex_trend'] = 'STRONGLY_RISING'
            elif change_pct > 5:
                history['gex_trend'] = 'RISING'
            elif change_pct < -20:
                history['gex_trend'] = 'STRONGLY_FALLING'
            elif change_pct < -5:
                history['gex_trend'] = 'FALLING'

        # Flip point movement
        if history['yesterday_flip'] > 0 and history['today_flip'] > 0:
            flip_change = history['today_flip'] - history['yesterday_flip']
            if flip_change > 2:
                history['flip_point_movement'] = 'RISING'
            elif flip_change < -2:
                history['flip_point_movement'] = 'FALLING'

        conn.close()
    except Exception as e:
        logger.debug(f"get_historical_gex_context error: {e}")

    return history


def get_intraday_momentum() -> Dict[str, Any]:
    """
    Fetch intraday GEX momentum (change in last hour).
    Updates every 5 minutes.
    """
    momentum = {
        'gex_1h_ago': 0,
        'gex_current': 0,
        'gex_change_1h': 0,
        'momentum': 'STABLE',
        'speed': 'NORMAL',
        'direction': 'NEUTRAL',
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get current GEX
        c.execute("""
            SELECT net_gex, timestamp
            FROM gex_history
            WHERE symbol = 'SPY'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        current_row = c.fetchone()

        # Get GEX from ~1 hour ago
        c.execute("""
            SELECT net_gex, timestamp
            FROM gex_history
            WHERE symbol = 'SPY' AND timestamp <= NOW() - INTERVAL '55 minutes'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        hour_ago_row = c.fetchone()

        if current_row:
            momentum['gex_current'] = float(current_row.get('net_gex') or 0)
            momentum['updated_at'] = current_row.get('timestamp').isoformat() if current_row.get('timestamp') else None

        if hour_ago_row:
            momentum['gex_1h_ago'] = float(hour_ago_row.get('net_gex') or 0)

        # Calculate momentum
        if momentum['gex_1h_ago'] != 0:
            momentum['gex_change_1h'] = momentum['gex_current'] - momentum['gex_1h_ago']
            change_billions = momentum['gex_change_1h'] / 1e9

            if change_billions > 0.5:
                momentum['momentum'] = 'BUILDING'
                momentum['direction'] = 'BULLISH'
            elif change_billions > 0.2:
                momentum['momentum'] = 'RISING'
                momentum['direction'] = 'BULLISH'
            elif change_billions < -0.5:
                momentum['momentum'] = 'COLLAPSING'
                momentum['direction'] = 'BEARISH'
            elif change_billions < -0.2:
                momentum['momentum'] = 'FALLING'
                momentum['direction'] = 'BEARISH'

            # Speed assessment
            if abs(change_billions) > 1:
                momentum['speed'] = 'FAST'
            elif abs(change_billions) > 0.5:
                momentum['speed'] = 'MODERATE'

        conn.close()
    except Exception as e:
        logger.debug(f"get_intraday_momentum error: {e}")

    return momentum


def get_skew_data() -> Dict[str, Any]:
    """
    Fetch volatility skew data for directional bias.
    Updates every 5 minutes.
    """
    skew = {
        'put_call_skew': 0,
        'skew_trend': 'NEUTRAL',
        'iv_rank': 50,
        'directional_bias': 'NEUTRAL',
        'interpretation': None,
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        if TradingVolatilityAPI:
            api = TradingVolatilityAPI()
            skew_result = api.get_skew_data('SPY') if hasattr(api, 'get_skew_data') else None

            if skew_result and 'error' not in skew_result:
                skew['put_call_skew'] = float(skew_result.get('skew') or 0)
                skew['iv_rank'] = float(skew_result.get('iv_rank') or 50)
                skew['updated_at'] = datetime.now().isoformat()

                # Interpret skew
                if skew['put_call_skew'] > 1.1:
                    skew['skew_trend'] = 'PUT_HEAVY'
                    skew['directional_bias'] = 'BEARISH'
                    skew['interpretation'] = 'Market pricing in downside protection'
                elif skew['put_call_skew'] < 0.9:
                    skew['skew_trend'] = 'CALL_HEAVY'
                    skew['directional_bias'] = 'BULLISH'
                    skew['interpretation'] = 'Market pricing in upside potential'
                else:
                    skew['interpretation'] = 'Balanced sentiment, no strong directional bias'

    except Exception as e:
        logger.debug(f"get_skew_data error: {e}")

    return skew


def get_regime_pattern_performance() -> Dict[str, Any]:
    """
    Get pattern performance filtered by current market regime.
    Updates every 30 minutes.
    """
    performance = {
        'current_regime': 'UNKNOWN',
        'patterns': [],
        'best_pattern_today': None,
        'worst_pattern_today': None,
        'updated_at': None,
        'refresh_interval': '30 minutes'
    }

    try:
        # Get current regime
        psychology = get_live_psychology_regime('SPY')
        performance['current_regime'] = psychology.get('regime_type', 'UNKNOWN')

        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get pattern performance (simplified - would need regime tagging in real implementation)
        c.execute("""
            SELECT
                pattern_type,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(realized_pnl) as avg_pnl,
                MAX(realized_pnl) as best_trade,
                MIN(realized_pnl) as worst_trade
            FROM autonomous_closed_trades
            WHERE COALESCE(exit_date, entry_date) >= NOW() - INTERVAL '30 days'
            GROUP BY pattern_type
            HAVING COUNT(*) >= 3
            ORDER BY (SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*)) DESC
        """)

        patterns = []
        for row in c.fetchall():
            win_rate = (row['wins'] / row['total_trades'] * 100) if row['total_trades'] > 0 else 0
            patterns.append({
                'pattern': row['pattern_type'],
                'trades': row['total_trades'],
                'win_rate': round(win_rate, 1),
                'avg_pnl': round(float(row['avg_pnl'] or 0), 2),
                'best_trade': round(float(row['best_trade'] or 0), 2),
                'worst_trade': round(float(row['worst_trade'] or 0), 2)
            })

        performance['patterns'] = patterns
        performance['updated_at'] = datetime.now().isoformat()

        if patterns:
            performance['best_pattern_today'] = patterns[0] if patterns else None
            performance['worst_pattern_today'] = patterns[-1] if len(patterns) > 1 else None

        conn.close()
    except Exception as e:
        logger.debug(f"get_regime_pattern_performance error: {e}")

    return performance


def get_strike_clustering() -> Dict[str, Any]:
    """
    Analyze open interest concentration at strikes to identify
    institutional positioning and magnetic price levels.
    Updates every 5 minutes.
    """
    clustering = {
        'top_call_strikes': [],
        'top_put_strikes': [],
        'max_pain': 0,
        'highest_oi_strike': 0,
        'institutional_bias': 'NEUTRAL',
        'magnetic_levels': [],
        'interpretation': None,
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Try to get strike-level data from gamma analysis or options flow
        c.execute("""
            SELECT strike, call_oi, put_oi, call_volume, put_volume, timestamp
            FROM strike_analysis
            WHERE symbol = 'SPY' AND timestamp >= NOW() - INTERVAL '1 day'
            ORDER BY (call_oi + put_oi) DESC
            LIMIT 10
        """)
        rows = c.fetchall()

        if rows:
            call_strikes = []
            put_strikes = []
            total_call_oi = 0
            total_put_oi = 0

            for row in rows:
                strike = float(row.get('strike') or 0)
                call_oi = int(row.get('call_oi') or 0)
                put_oi = int(row.get('put_oi') or 0)

                total_call_oi += call_oi
                total_put_oi += put_oi

                if call_oi > 10000:
                    call_strikes.append({'strike': strike, 'oi': call_oi})
                if put_oi > 10000:
                    put_strikes.append({'strike': strike, 'oi': put_oi})

            clustering['top_call_strikes'] = sorted(call_strikes, key=lambda x: x['oi'], reverse=True)[:5]
            clustering['top_put_strikes'] = sorted(put_strikes, key=lambda x: x['oi'], reverse=True)[:5]
            clustering['updated_at'] = rows[0].get('timestamp').isoformat() if rows[0].get('timestamp') else None

            # Determine institutional bias
            if total_call_oi > total_put_oi * 1.3:
                clustering['institutional_bias'] = 'BULLISH'
                clustering['interpretation'] = 'Heavy call accumulation suggests institutional bullish positioning'
            elif total_put_oi > total_call_oi * 1.3:
                clustering['institutional_bias'] = 'BEARISH'
                clustering['interpretation'] = 'Heavy put accumulation suggests institutional hedging/bearish positioning'
            else:
                clustering['interpretation'] = 'Balanced positioning, no strong institutional directional bias'

            # Identify magnetic levels (highest combined OI)
            if rows:
                clustering['highest_oi_strike'] = float(rows[0].get('strike') or 0)
                clustering['magnetic_levels'] = [float(r.get('strike') or 0) for r in rows[:3]]

        conn.close()
    except Exception as e:
        logger.debug(f"get_strike_clustering error: {e}")
        # Fallback - use call/put walls as magnetic levels
        market_data = get_live_market_data('SPY')
        if market_data.get('call_wall'):
            clustering['magnetic_levels'] = [
                market_data.get('put_wall', 0),
                market_data.get('flip_point', 0),
                market_data.get('call_wall', 0)
            ]
            clustering['interpretation'] = 'Using GEX walls as magnetic levels (strike data unavailable)'
            clustering['updated_at'] = datetime.now().isoformat()

    return clustering


def get_vix_term_structure() -> Dict[str, Any]:
    """
    Analyze VIX term structure for contango/backwardation signals.
    Updates every 5 minutes.
    """
    structure = {
        'vix_spot': 0,
        'vix_1m': 0,
        'vix_3m': 0,
        'term_structure': 'UNKNOWN',
        'contango_pct': 0,
        'signal': 'NEUTRAL',
        'interpretation': None,
        'updated_at': None,
        'refresh_interval': '5 minutes'
    }

    try:
        # Get current VIX
        market_data = get_live_market_data('SPY')
        vix_spot = float(market_data.get('vix') or 0)
        structure['vix_spot'] = vix_spot

        # Try to get VIX futures from database or API
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute("""
            SELECT vix_1m, vix_3m, timestamp
            FROM vix_term_structure
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = c.fetchone()

        if row:
            structure['vix_1m'] = float(row.get('vix_1m') or 0)
            structure['vix_3m'] = float(row.get('vix_3m') or 0)
            structure['updated_at'] = row.get('timestamp').isoformat() if row.get('timestamp') else None
        else:
            # Estimate from spot VIX
            structure['vix_1m'] = vix_spot * 1.05  # Typical contango estimate
            structure['vix_3m'] = vix_spot * 1.10
            structure['updated_at'] = datetime.now().isoformat()

        conn.close()

        # Calculate term structure
        if structure['vix_spot'] > 0 and structure['vix_1m'] > 0:
            contango_pct = ((structure['vix_1m'] - structure['vix_spot']) / structure['vix_spot']) * 100
            structure['contango_pct'] = round(contango_pct, 2)

            if contango_pct > 5:
                structure['term_structure'] = 'STEEP_CONTANGO'
                structure['signal'] = 'BULLISH'
                structure['interpretation'] = 'Steep contango suggests market expects calm ahead - bullish for equities'
            elif contango_pct > 0:
                structure['term_structure'] = 'CONTANGO'
                structure['signal'] = 'NEUTRAL_BULLISH'
                structure['interpretation'] = 'Normal contango - typical market conditions'
            elif contango_pct > -5:
                structure['term_structure'] = 'FLAT'
                structure['signal'] = 'NEUTRAL'
                structure['interpretation'] = 'Flat term structure - market uncertainty'
            else:
                structure['term_structure'] = 'BACKWARDATION'
                structure['signal'] = 'BEARISH'
                structure['interpretation'] = 'Backwardation signals fear - expect volatility expansion'

    except Exception as e:
        logger.debug(f"get_vix_term_structure error: {e}")
        structure['interpretation'] = 'VIX term structure data unavailable'
        structure['updated_at'] = datetime.now().isoformat()

    return structure


def get_trading_windows() -> Dict[str, Any]:
    """
    Provide time-of-day context for optimal trading windows.
    Updates every minute.
    """
    now = datetime.now()
    ct_hour = now.hour  # Assuming server is in CT
    ct_minute = now.minute
    current_minutes = ct_hour * 60 + ct_minute

    windows = {
        'current_time': now.strftime('%I:%M %p CT'),
        'market_status': 'CLOSED',
        'current_window': None,
        'minutes_until_next': 0,
        'next_window': None,
        'recommendation': None,
        'avoid_trading': False,
        'updated_at': now.isoformat(),
        'refresh_interval': '1 minute'
    }

    # Market hours (CT): Pre-market 7:00, Open 8:30, Close 3:00, After 5:00
    market_open = 8 * 60 + 30   # 8:30 AM CT
    market_close = 15 * 60      # 3:00 PM CT
    power_hour = 14 * 60        # 2:00 PM CT

    # Define trading windows
    trading_windows = [
        {'name': 'PRE_MARKET', 'start': 7*60, 'end': 8*60+30, 'quality': 'LOW', 'note': 'Low liquidity, wide spreads'},
        {'name': 'OPENING_VOLATILITY', 'start': 8*60+30, 'end': 9*60, 'quality': 'RISKY', 'note': 'High volatility, wait for direction'},
        {'name': 'MORNING_SESSION', 'start': 9*60, 'end': 11*60, 'quality': 'HIGH', 'note': 'Best liquidity, trends establish'},
        {'name': 'LUNCH_CHOP', 'start': 11*60, 'end': 13*60, 'quality': 'LOW', 'note': 'Low volume, choppy action - avoid'},
        {'name': 'AFTERNOON_SESSION', 'start': 13*60, 'end': 14*60, 'quality': 'MEDIUM', 'note': 'Volume returns, prepare for power hour'},
        {'name': 'POWER_HOUR', 'start': 14*60, 'end': 15*60, 'quality': 'HIGH', 'note': 'High volume, strong moves - last chance'},
        {'name': 'AFTER_HOURS', 'start': 15*60, 'end': 17*60, 'quality': 'LOW', 'note': 'Market closed, limited trading'},
    ]

    # Determine market status
    if current_minutes < market_open:
        windows['market_status'] = 'PRE_MARKET'
    elif current_minutes < market_close:
        windows['market_status'] = 'OPEN'
    else:
        windows['market_status'] = 'CLOSED'

    # Find current window
    for window in trading_windows:
        if window['start'] <= current_minutes < window['end']:
            windows['current_window'] = window['name']
            windows['recommendation'] = window['note']
            if window['quality'] == 'LOW' or window['name'] == 'LUNCH_CHOP':
                windows['avoid_trading'] = True
            break

    # Find next window
    for window in trading_windows:
        if window['start'] > current_minutes:
            windows['next_window'] = window['name']
            windows['minutes_until_next'] = window['start'] - current_minutes
            break

    # Special recommendations based on time
    if windows['current_window'] == 'OPENING_VOLATILITY':
        windows['recommendation'] = 'Wait 15-30 min for direction to establish before entering'
    elif windows['current_window'] == 'POWER_HOUR':
        windows['recommendation'] = 'Last hour - close positions before 2:45 PM CT for 0DTE'
    elif current_minutes >= market_close:
        windows['recommendation'] = 'Market closed - plan for tomorrow'

    return windows


def get_key_events() -> Dict[str, Any]:
    """
    Check for key market events (Fed, earnings, economic data).
    Updates every 30 minutes.
    """
    events = {
        'today_events': [],
        'this_week_events': [],
        'high_impact_today': False,
        'fed_day': False,
        'triple_witching': False,
        'interpretation': None,
        'updated_at': datetime.now().isoformat(),
        'refresh_interval': '30 minutes'
    }

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check for events in economic calendar table
        c.execute("""
            SELECT event_name, event_time, impact, description
            FROM economic_calendar
            WHERE event_date = CURRENT_DATE
            ORDER BY event_time
        """)
        today_events = c.fetchall()

        if today_events:
            events['today_events'] = [dict(e) for e in today_events]
            high_impact = [e for e in today_events if e.get('impact') == 'HIGH']
            if high_impact:
                events['high_impact_today'] = True
                events['interpretation'] = f"High-impact event today: {high_impact[0].get('event_name')} - expect volatility"

        # Check for Fed days
        c.execute("""
            SELECT event_name FROM economic_calendar
            WHERE event_date = CURRENT_DATE
            AND (event_name ILIKE '%FOMC%' OR event_name ILIKE '%Fed%' OR event_name ILIKE '%Powell%')
        """)
        if c.fetchone():
            events['fed_day'] = True
            events['interpretation'] = 'Fed day - expect low volume before announcement, volatility after'

        conn.close()

        # Check for options expiration (monthly = 3rd Friday)
        today = datetime.now()
        if today.weekday() == 4:  # Friday
            day = today.day
            # Third Friday is between 15-21
            if 15 <= day <= 21:
                events['triple_witching'] = True
                if not events['interpretation']:
                    events['interpretation'] = 'Monthly options expiration - expect pinning action near max pain'

    except Exception as e:
        logger.debug(f"get_key_events error: {e}")
        events['interpretation'] = 'Event calendar unavailable'

    return events


# Get API key with fallback support (ANTHROPIC_API_KEY or CLAUDE_API_KEY)
api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

# Ensure ANTHROPIC_API_KEY is set for ChatAnthropic
if api_key and not os.getenv('ANTHROPIC_API_KEY'):
    os.environ['ANTHROPIC_API_KEY'] = api_key

# Initialize Claude for AI endpoints
# Will use ANTHROPIC_API_KEY from environment
llm = None
llm_init_error = None
if api_key and LANGCHAIN_AVAILABLE and ChatAnthropic:
    try:
        # Use Claude 3.5 Haiku for fast, cost-effective AI responses
        llm = ChatAnthropic(
            model="claude-3-5-haiku-latest",
            temperature=0.1,
            max_tokens=4096
        )
        logger.info("AI Intelligence: Claude 3.5 Haiku initialized successfully")
    except Exception as e:
        llm_init_error = str(e)
        logger.warning(f"AI Intelligence: Claude initialization failed: {e}")
        llm = None
else:
    if not api_key:
        logger.warning("AI Intelligence: No API key found (ANTHROPIC_API_KEY or CLAUDE_API_KEY)")
    if not LANGCHAIN_AVAILABLE:
        logger.warning("AI Intelligence: LangChain not installed")

# Initialize AI systems (if available)
ai_reasoning = AutonomousAIReasoning() if AutonomousAIReasoning else None
trade_advisor = AITradeAdvisor() if AITradeAdvisor else None

# Helper function to validate API key is configured
def require_api_key():
    """Raises HTTPException if API key is not configured or langchain unavailable"""
    logger.debug(f" require_api_key: LANGCHAIN_AVAILABLE={LANGCHAIN_AVAILABLE}, api_key={bool(api_key)}, llm={bool(llm)}")
    if not LANGCHAIN_AVAILABLE:
        logger.debug(" require_api_key: LangChain not available")
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable: LangChain not installed. Install with: pip install langchain-anthropic"
        )
    if not api_key:
        logger.debug(" require_api_key: No API key")
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable: Claude API key not configured. Set ANTHROPIC_API_KEY or CLAUDE_API_KEY environment variable."
        )
    if not llm:
        error_detail = f"AI service unavailable: Claude LLM initialization failed"
        if llm_init_error:
            error_detail += f" - {llm_init_error}"
        logger.debug(f" require_api_key: LLM not initialized - {error_detail}")
        raise HTTPException(
            status_code=503,
            detail=error_detail
        )
    logger.debug(" require_api_key: All checks passed")


# Helper function to safely get database connection
def get_safe_connection():
    """Get database connection or raise 503 if unavailable"""
    try:
        return get_connection()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database service unavailable: {type(e).__name__}"
        )


# ============================================================================
# 1. PRE-TRADE SAFETY CHECKLIST
# ============================================================================

class PreTradeChecklistRequest(BaseModel):
    symbol: str
    strike: float
    option_type: str  # CALL or PUT
    contracts: int
    cost_per_contract: float
    pattern_type: Optional[str] = None
    confidence: Optional[float] = None


@router.post("/pre-trade-checklist")
async def generate_pre_trade_checklist(request: PreTradeChecklistRequest):
    """
    Generates comprehensive pre-trade safety checklist with 20+ validations.
    Returns APPROVED/REJECTED with detailed reasoning.
    """
    require_api_key()

    try:
        logger.debug(" pre-trade-checklist: Starting...")
        conn = get_safe_connection()
        c = conn.cursor()

        # Get account info - with fallback
        logger.debug(" pre-trade-checklist: Querying account_state...")
        account_value = 10000
        try:
            c.execute("SELECT account_value FROM account_state ORDER BY timestamp DESC LIMIT 1")
            account_value_row = c.fetchone()
            account_value = account_value_row[0] if account_value_row else 10000
            logger.debug(f" pre-trade-checklist: account_value = {account_value}")
        except Exception as e:
            logger.debug(f" pre-trade-checklist: account_state error: {e}")

        # Get current positions - with fallback
        logger.debug(" pre-trade-checklist: Querying trades for exposure...")
        current_exposure = 0
        try:
            c.execute("SELECT SUM(ABS(contracts * entry_price * 100)) FROM trades WHERE status = 'OPEN'")
            current_exposure_row = c.fetchone()
            current_exposure = current_exposure_row[0] if current_exposure_row and current_exposure_row[0] else 0
            logger.debug(f" pre-trade-checklist: current_exposure = {current_exposure}")
        except Exception as e:
            logger.debug(f" pre-trade-checklist: trades exposure error: {e}")

        # Get today's P&L - with fallback
        logger.debug(" pre-trade-checklist: Querying trades for today PnL...")
        today_pnl = 0
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
            c.execute("""
                SELECT SUM(realized_pnl)
                FROM trades
                WHERE timestamp >= %s AND status = 'CLOSED'
            """, (today_start,))
            today_pnl_row = c.fetchone()
            today_pnl = today_pnl_row[0] if today_pnl_row and today_pnl_row[0] else 0
            logger.debug(f" pre-trade-checklist: today_pnl = {today_pnl}")
        except Exception as e:
            logger.debug(f" pre-trade-checklist: trades pnl error: {e}")

        # Get max drawdown - with fallback
        logger.debug(" pre-trade-checklist: Querying account_state for drawdown...")
        current_drawdown_pct = 0
        try:
            c.execute("""
                SELECT MIN(account_value) as min_val, MAX(account_value) as max_val
                FROM account_state
                WHERE timestamp >= NOW() - INTERVAL '30 days'
            """)
            dd_row = c.fetchone()
            if dd_row and dd_row[0] and dd_row[1]:
                current_drawdown_pct = ((dd_row[1] - account_value) / dd_row[1] * 100) if dd_row[1] > 0 else 0
            logger.debug(f" pre-trade-checklist: current_drawdown_pct = {current_drawdown_pct}")
        except Exception as e:
            logger.debug(f" pre-trade-checklist: account_state drawdown error: {e}")

        # Get win rate for pattern - with fallback
        pattern_win_rate = 0
        if request.pattern_type:
            logger.debug(f" pre-trade-checklist: Querying trades for pattern {request.pattern_type}...")
            try:
                c.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
                    FROM trades
                    WHERE pattern_type = %s AND status = 'CLOSED'
                """, (request.pattern_type,))
                pattern_row = c.fetchone()
                if pattern_row and pattern_row[0] and pattern_row[0] > 0:
                    pattern_win_rate = (pattern_row[1] / pattern_row[0] * 100) if pattern_row[0] > 0 else 0
                logger.debug(f" pre-trade-checklist: pattern_win_rate = {pattern_win_rate}")
            except Exception as e:
                logger.debug(f" pre-trade-checklist: trades pattern error: {e}")

        # Get current VIX and market data - with fallback
        logger.debug(" pre-trade-checklist: Querying market_data for VIX...")
        current_vix = 15.0
        try:
            c.execute("SELECT vix FROM market_data ORDER BY timestamp DESC LIMIT 1")
            vix_row = c.fetchone()
            current_vix = vix_row[0] if vix_row else 15.0
            logger.debug(f" pre-trade-checklist: current_vix = {current_vix}")
        except Exception as e:
            logger.debug(f" pre-trade-checklist: market_data vix error: {e}")

        conn.close()
        logger.debug(" pre-trade-checklist: Database queries complete")

        # Calculate trade metrics
        total_cost = request.contracts * request.cost_per_contract * 100
        position_size_pct = (total_cost / account_value * 100) if account_value > 0 else 0
        daily_loss_pct = abs(today_pnl / account_value * 100) if account_value > 0 else 0
        total_exposure_pct = ((current_exposure + total_cost) / account_value * 100) if account_value > 0 else 0

        # Generate comprehensive checklist using Claude
        prompt = f"""You are a professional options trading risk manager. Generate a comprehensive pre-trade safety checklist for this trade.

TRADE DETAILS:
• Symbol: {request.symbol}
• Strike: ${request.strike}
• Type: {request.option_type}
• Contracts: {request.contracts}
• Cost per contract: ${request.cost_per_contract}
• Total cost: ${total_cost:.2f}
• Pattern: {request.pattern_type or 'N/A'}
• Confidence: {request.confidence or 0}%

ACCOUNT STATUS:
• Account value: ${account_value:.2f}
• Current exposure: ${current_exposure:.2f} ({current_exposure / account_value * 100:.1f}% of account)
• Today's P&L: ${today_pnl:.2f}
• Current drawdown: {current_drawdown_pct:.1f}%
• VIX: {current_vix:.1f}

RISK METRICS FOR THIS TRADE:
• Position size: {position_size_pct:.1f}% of account
• Daily loss today: {daily_loss_pct:.1f}%
• Total exposure after trade: {total_exposure_pct:.1f}%
• Pattern win rate: {pattern_win_rate:.1f}%

RISK LIMITS:
• Max position size: 20% of account
• Max daily loss: 5% of account
• Max drawdown: 15%
• Max total exposure: 50%
• Min win rate for pattern: 60%
• Min confidence: 65%

Generate a detailed checklist with these sections:
1. RISK VALIDATION (4 checks) - Position size, daily loss, drawdown, exposure
2. PROBABILITY ANALYSIS (4 checks) - Win rate, confidence, expected value, historical performance
3. GREEKS VALIDATION (3 checks) - Theta decay, time to expiration, delta
4. MARKET CONDITIONS (3 checks) - VIX level, trend, timing
5. PSYCHOLOGY CHECKS (4 checks) - Revenge trading, FOMO, overconfidence, exit plan

For each check, return:
• Status: PASS or FAIL or WARNING
• Value: Current value
• Limit: Maximum allowed
• Comment: Brief explanation

Then provide:
• OVERALL VERDICT: APPROVED or REJECTED or PROCEED_WITH_CAUTION
• WARNINGS: List any yellow flags
• CRITICAL_RISKS: List any deal-breakers

Format as JSON."""

        checklist_result = llm.invoke(prompt)
        checklist_text = checklist_result.content

        # Parse the response (try to extract JSON, fallback to text)
        import json
        try:
            # Try to extract JSON from the response
            if '```json' in checklist_text:
                json_start = checklist_text.find('```json') + 7
                json_end = checklist_text.find('```', json_start)
                checklist_data = json.loads(checklist_text[json_start:json_end].strip())
            elif '{' in checklist_text:
                # Find JSON object
                json_start = checklist_text.find('{')
                json_end = checklist_text.rfind('}') + 1
                checklist_data = json.loads(checklist_text[json_start:json_end])
            else:
                # Fallback: structure it ourselves
                checklist_data = {
                    "verdict": "APPROVED" if position_size_pct < 20 and daily_loss_pct < 5 else "REJECTED",
                    "analysis": checklist_text
                }
        except (json.JSONDecodeError, TypeError, ValueError, IndexError) as e:
            # JSON parsing failed, use fallback structure
            checklist_data = {
                "verdict": "APPROVED" if position_size_pct < 20 and daily_loss_pct < 5 else "REJECTED",
                "analysis": checklist_text
            }

        return {
            'success': True,
            'data': {
                'checklist': checklist_data,
                'trade_metrics': {
                    'total_cost': total_cost,
                    'position_size_pct': position_size_pct,
                    'daily_loss_pct': daily_loss_pct,
                    'total_exposure_pct': total_exposure_pct,
                    'pattern_win_rate': pattern_win_rate
                },
                'account_status': {
                    'account_value': account_value,
                    'current_exposure': current_exposure,
                    'today_pnl': today_pnl,
                    'current_drawdown_pct': current_drawdown_pct
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate checklist: {str(e)}")


# ============================================================================
# 2. REAL-TIME TRADE EXPLAINER
# ============================================================================

@router.get("/trade-explainer/{trade_id}")
async def explain_trade(trade_id: str):
    """
    Generates comprehensive explanation of WHY a trade was taken.
    Includes strike selection, position sizing, price targets, Greeks, market mechanics.
    """
    require_api_key()

    try:
        logger.debug(f" trade-explainer: Starting for trade_id={trade_id}...")
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get trade details - with fallback
        logger.debug(" trade-explainer: Querying trades...")
        trade_dict = None
        try:
            c.execute("""
                SELECT * FROM trades WHERE id::text = %s OR timestamp::text = %s
            """, (trade_id, trade_id))
            trade = c.fetchone()
            if trade:
                trade_dict = dict(trade)
                logger.debug(f" trade-explainer: Found trade")
            else:
                logger.debug(f" trade-explainer: Trade not found")
        except Exception as e:
            logger.debug(f" trade-explainer: trades query error: {e}")

        if not trade_dict:
            conn.close()
            raise HTTPException(status_code=404, detail="Trade not found")

        # Get associated autonomous logs - with fallback
        logger.debug(" trade-explainer: Querying autonomous_trader_logs...")
        logs = []
        try:
            c.execute("""
                SELECT * FROM autonomous_trader_logs
                WHERE timestamp >= %s::timestamp - INTERVAL '5 minutes'
                AND timestamp <= %s::timestamp + INTERVAL '5 minutes'
                ORDER BY timestamp DESC
            """, (trade_dict['timestamp'], trade_dict['timestamp']))
            logs = [dict(row) for row in c.fetchall()]
            logger.debug(f" trade-explainer: Found {len(logs)} logs")
        except Exception as e:
            logger.debug(f" trade-explainer: autonomous_trader_logs error: {e}")

        # Get market context at time of trade - with fallback
        logger.debug(" trade-explainer: Querying market_data...")
        market_dict = {'spot_price': 0, 'vix': 15, 'net_gex': 0}
        try:
            c.execute("""
                SELECT * FROM market_data
                WHERE timestamp <= %s
                ORDER BY timestamp DESC LIMIT 1
            """, (trade_dict['timestamp'],))
            market_data = c.fetchone()
            market_dict = dict(market_data) if market_data else {'spot_price': 0, 'vix': 15, 'net_gex': 0}
            logger.debug(f" trade-explainer: market_data = {bool(market_data)}")
        except Exception as e:
            logger.debug(f" trade-explainer: market_data error: {e}")

        # Get GEX context - with fallback
        logger.debug(" trade-explainer: Querying gex_levels...")
        gex_dict = {'call_wall': 0, 'put_wall': 0, 'flip_point': 0}
        try:
            c.execute("""
                SELECT * FROM gex_levels
                WHERE timestamp <= %s
                ORDER BY timestamp DESC LIMIT 1
            """, (trade_dict['timestamp'],))
            gex_data = c.fetchone()
            gex_dict = dict(gex_data) if gex_data else {'call_wall': 0, 'put_wall': 0, 'flip_point': 0}
            logger.debug(f" trade-explainer: gex_levels = {bool(gex_data)}")
        except Exception as e:
            logger.debug(f" trade-explainer: gex_levels error: {e}")

        conn.close()
        logger.debug(" trade-explainer: Database queries complete")

        # Generate comprehensive explanation using Claude
        prompt = f"""You are an expert options trader explaining a trade to a student. Generate a DETAILED trade breakdown that explains EXACTLY why this trade was taken, with specific price targets and exit strategy.

TRADE EXECUTED:
• Symbol: {trade_dict.get('symbol') or 'SPY'}
• Strike: ${trade_dict.get('strike') or 0}
• Type: {trade_dict.get('option_type') or 'CALL'}
• Contracts: {trade_dict.get('contracts') or 0}
• Entry Price: ${trade_dict.get('entry_price') or 0}
• Total Cost: ${(trade_dict.get('contracts') or 0) * (trade_dict.get('entry_price') or 0) * 100:.2f}
• Pattern: {trade_dict.get('pattern_type') or 'N/A'}
• Confidence: {trade_dict.get('confidence_score') or 0}%
• Timestamp: {trade_dict.get('timestamp') or 'N/A'}

MARKET CONTEXT AT TRADE TIME:
• SPY Price: ${market_dict.get('spot_price') or 0}
• VIX: {market_dict.get('vix') or 0}
• Net GEX: ${(market_dict.get('net_gex') or 0)/1e9:.2f}B
• Call Wall: ${gex_dict.get('call_wall') or 0}
• Put Wall: ${gex_dict.get('put_wall') or 0}

AI REASONING LOGS:
{chr(10).join([f"• {log.get('log_type', 'N/A')}: {log.get('reasoning_summary', 'N/A')}" for log in logs[:5]])}

Generate a comprehensive trade explanation with these sections:

1. STRIKE SELECTION
   • Why this strike was chosen over alternatives (be specific about $$ alternatives)
   • Distance from current price
   • Relationship to gamma walls
   • Delta positioning (optimal for this setup)

2. POSITION SIZING
   • Kelly Criterion calculation
   • Why this many contracts
   • Risk percentage of account
   • Max loss calculation

3. PROFIT TARGETS (be SPECIFIC)
   • Target 1: $$ price and % profit (first resistance)
   • Target 2: $$ price and % profit (major resistance)
   • Stop Loss: $$ price and % loss (thesis invalidation point)

4. OPTION GREEKS BREAKDOWN
   • Delta: What it means for this trade
   • Theta: Daily decay and urgency
   • Days to expiration: Time pressure
   • Implied Volatility: What it tells us

5. TIME MANAGEMENT (exact times)
   • When to exit if no movement (theta protection)
   • When to hold if moving right (momentum)
   • Expiration urgency

6. MARKET MECHANICS (WHY this works)
   • What market makers must do
   • How gamma exposure drives price
   • Why this pattern has edge
   • Historical success rate

7. RISK FACTORS (what could go wrong)
   • VIX spike trigger
   • Thesis invalidation level
   • Theta decay threshold

8. EXPECTED OUTCOME
   • Probability of profit
   • Expected value
   • Max risk
   • Risk/reward ratio

Be extremely specific with dollar amounts, percentages, and times. This needs to be actionable."""

        explanation = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'trade': trade_dict,
                'explanation': explanation.content,
                'market_context': market_dict,
                'gex_context': gex_dict,
                'ai_logs': logs
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to explain trade: {str(e)}")


# ============================================================================
# 3. DAILY TRADING PLAN GENERATOR
# ============================================================================

@router.get("/daily-trading-plan")
async def generate_daily_trading_plan():
    """
    Generates comprehensive daily trading plan with top 3 opportunities,
    key price levels, psychology traps to avoid, risk allocation, and time-based actions.

    Caches responses for 30 minutes to eliminate page load lag.
    """
    require_api_key()

    try:
        # Check cache first - return immediately if valid cache exists
        cached = get_cached_response('daily_trading_plan')
        if cached:
            # Update generated_at to show when it was cached, add cache flag
            cached['data']['from_cache'] = True
            return cached

        logger.debug(" daily-trading-plan: Starting...")

        # =====================================================================
        # GET LIVE MARKET DATA (uses TradingVolatilityAPI, gex_history fallback)
        # =====================================================================
        logger.debug(" daily-trading-plan: Fetching LIVE market data...")
        market_data = get_live_market_data('SPY')
        logger.debug(f" daily-trading-plan: LIVE data source = {market_data.get('data_source')}")
        logger.debug(f" daily-trading-plan: spot_price = {market_data.get('spot_price')}, vix = {market_data.get('vix')}")

        # Get psychology regime from live data
        logger.debug(" daily-trading-plan: Computing psychology regime...")
        psychology = get_live_psychology_regime('SPY')
        logger.debug(f" daily-trading-plan: regime = {psychology.get('regime_type')}, confidence = {psychology.get('confidence')}")

        # GEX levels from live data
        gex = {
            'call_wall': market_data.get('call_wall', 0),
            'put_wall': market_data.get('put_wall', 0),
            'flip_point': market_data.get('flip_point', 0)
        }
        logger.debug(f" daily-trading-plan: call_wall={gex['call_wall']}, put_wall={gex['put_wall']}")

        # =====================================================================
        # DATABASE QUERIES (for account/trades - these have real data)
        # =====================================================================
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get account status - try autonomous_config first (has real capital)
        logger.debug(" daily-trading-plan: Querying autonomous_config for capital...")
        account_value = 10000
        try:
            c.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
            config_row = c.fetchone()
            if config_row and config_row['value']:
                account_value = float(config_row['value'])
            logger.debug(f" daily-trading-plan: account_value = {account_value}")
        except Exception as e:
            logger.debug(f" daily-trading-plan: autonomous_config error: {e}")

        # Get recent performance from autonomous_closed_trades (has real data)
        logger.debug(" daily-trading-plan: Querying autonomous_closed_trades for performance...")
        performance = {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0}
        try:
            c.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(realized_pnl) as avg_pnl
                FROM autonomous_closed_trades
                WHERE COALESCE(exit_date, entry_date) >= NOW() - INTERVAL '7 days'
            """)
            perf_row = c.fetchone()
            if perf_row and perf_row['total']:
                performance = {
                    'total_trades': perf_row['total'],
                    'win_rate': (perf_row['wins'] / perf_row['total'] * 100) if perf_row['total'] > 0 else 0,
                    'avg_pnl': perf_row['avg_pnl'] or 0
                }
            logger.debug(f" daily-trading-plan: performance = {performance}")
        except Exception as e:
            logger.debug(f" daily-trading-plan: trades table error: {e}")

        # Get top patterns - with fallback for missing table
        logger.debug(" daily-trading-plan: Querying trades for patterns...")
        top_patterns = []
        try:
            c.execute("""
                SELECT
                    pattern_type,
                    COUNT(*) as trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                    AVG(realized_pnl) as avg_pnl
                FROM trades
                WHERE status = 'CLOSED' AND timestamp >= NOW() - INTERVAL '30 days'
                GROUP BY pattern_type
                HAVING COUNT(*) >= 3
                ORDER BY win_rate DESC, avg_pnl DESC
                LIMIT 3
            """)
            top_patterns = [dict(row) for row in c.fetchall()]
            logger.debug(f" daily-trading-plan: top_patterns count = {len(top_patterns)}")
        except Exception as e:
            logger.debug(f" daily-trading-plan: trades patterns error: {e}")

        conn.close()

        # Generate GEX context for better AI understanding
        gex_context = get_gex_context(market_data, gex)

        # Generate daily plan using Claude
        today = datetime.now().strftime("%B %d, %Y")
        current_time = datetime.now().strftime("%I:%M %p CT")
        prompt = f"""You are an expert options trader specializing in GEX-based strategies. Generate a precise, actionable daily trading plan based on current dealer positioning.

TODAY: {today} | TIME: {current_time}

═══════════════════════════════════════════════════════════════
LIVE MARKET DATA
═══════════════════════════════════════════════════════════════
SPY SPOT: ${market_data.get('spot_price') or 0}
VIX: {market_data.get('vix') or 0}
Net GEX: ${(market_data.get('net_gex') or 0)/1e9:.2f}B

{gex_context}

═══════════════════════════════════════════════════════════════
PSYCHOLOGY & REGIME
═══════════════════════════════════════════════════════════════
Market Regime: {psychology.get('regime_type', 'UNKNOWN')}
Confidence: {psychology.get('confidence') or 0}%
Psychology Trap: {psychology.get('psychology_trap', 'NONE')}

═══════════════════════════════════════════════════════════════
ACCOUNT & PERFORMANCE
═══════════════════════════════════════════════════════════════
Balance: ${account_value:.2f}
7-Day Win Rate: {performance.get('win_rate') or 0:.1f}%
Recent Trades: {performance.get('total_trades') or 0}

Top Patterns (30d):
{chr(10).join([f"• {p.get('pattern_type', 'N/A')}: {(p.get('win_rate') or 0)*100:.0f}% win, ${float(p.get('avg_pnl') or 0):.2f} avg" for p in top_patterns]) or '• No pattern data available'}

═══════════════════════════════════════════════════════════════
GENERATE YOUR DAILY PLAN
═══════════════════════════════════════════════════════════════

Based on the GEX positioning above, provide:

1. TODAY'S STRATEGY (based on GEX regime)
   State the ONE primary strategy for today based on dealer positioning.
   Example: "SELL PREMIUM - positive GEX favors theta decay" or "DIRECTIONAL CALLS - negative GEX amplifies upside"

2. PRIMARY TRADE SETUP
   • Direction: CALLS/PUTS/NEUTRAL
   • Strike: Based on wall distances
   • Entry trigger: Specific price level
   • Target: Based on nearest wall
   • Stop: Below/above flip point
   • Size: Based on account (max 5% risk)
   • Why: Connect to GEX data

3. BACKUP TRADE (if primary fails)
   • Alternative setup with entry conditions

4. CRITICAL LEVELS TODAY
   • RESISTANCE: Call wall at ${gex.get('call_wall') or 0}
   • SUPPORT: Put wall at ${gex.get('put_wall') or 0}
   • PIVOT: Flip point at ${gex.get('flip_point') or 0}
   • NO-TRADE ZONE: Define price range to avoid

5. TIME WINDOWS (CT)
   • Best entry window based on GEX
   • Avoid times (e.g., first 15 min, power hour)
   • Hard stop time for new positions

6. RISK RULES FOR TODAY
   • Max loss per trade: $
   • Max daily loss: $
   • Position sizing based on VIX

Keep it concise and actionable. Every recommendation must connect back to the GEX data provided."""

        plan = llm.invoke(prompt)

        # Log the actual data being returned for debugging
        logger.debug(f"[RESPONSE] daily-trading-plan returning:")
        logger.debug(f"  - data_source: {market_data.get('data_source')}")
        logger.debug(f"  - spot_price: ${market_data.get('spot_price', 0)}")
        logger.debug(f"  - net_gex: ${(market_data.get('net_gex', 0) or 0)/1e9:.2f}B")
        logger.debug(f"  - call_wall: ${market_data.get('call_wall', 0)}")
        logger.debug(f"  - put_wall: ${market_data.get('put_wall', 0)}")
        logger.debug(f"  - regime: {psychology.get('regime_type')}")

        response = {
            'success': True,
            'data': {
                'plan': plan.content,
                'market_data': market_data,
                'psychology': psychology,
                'gex': gex,
                'account_value': account_value,
                'performance': performance,
                'top_patterns': top_patterns,
                'generated_at': datetime.now().isoformat(),
                'from_cache': False,
                '_data_sources': {
                    'market_data': market_data.get('data_source', 'unknown'),
                    'account': 'autonomous_config',
                    'performance': 'autonomous_closed_trades',
                    'is_live': market_data.get('data_source') != 'default'
                }
            }
        }

        # Cache the response for subsequent requests
        set_cached_response('daily_trading_plan', response)

        return response

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] daily-trading-plan failed: {type(e).__name__}: {str(e)}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate daily plan: {type(e).__name__}: {str(e)}")


# ============================================================================
# 4. POSITION MANAGEMENT ASSISTANT
# ============================================================================

@router.get("/position-guidance/{trade_id}")
async def get_position_guidance(trade_id: str):
    """
    Provides live guidance for an open position:
    - Next actions (partial profit, add, exit)
    - Stop loss adjustments
    - Exit triggers
    - Greeks updates
    - Time decay watch
    """
    require_api_key()

    try:
        logger.debug(f" position-guidance: Starting for trade_id={trade_id}...")
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get trade - with fallback
        logger.debug(" position-guidance: Querying trades...")
        trade = None
        try:
            c.execute("SELECT * FROM trades WHERE (id::text = %s OR timestamp::text = %s) AND status = 'OPEN'", (trade_id, trade_id))
            trade_row = c.fetchone()
            if trade_row:
                trade = dict(trade_row)
                logger.debug(f" position-guidance: Found trade")
        except Exception as e:
            logger.debug(f" position-guidance: trades query error: {e}")

        if not trade:
            conn.close()
            raise HTTPException(status_code=404, detail="Open position not found")

        # Get current market price - with fallback
        logger.debug(" position-guidance: Querying market_data...")
        current_spy = 0
        current_vix = 15
        try:
            c.execute("SELECT spot_price, vix FROM market_data ORDER BY timestamp DESC LIMIT 1")
            market_row = c.fetchone()
            current_spy = market_row['spot_price'] if market_row else 0
            current_vix = market_row['vix'] if market_row else 15
            logger.debug(f" position-guidance: current_spy={current_spy}, current_vix={current_vix}")
        except Exception as e:
            logger.debug(f" position-guidance: market_data error: {e}")

        # Get current option price (estimate based on intrinsic value + time value)
        strike = trade.get('strike', 0) or 0
        entry_price = trade.get('entry_price', 0) or 0
        option_type = trade.get('option_type', 'CALL')

        # Simple estimate: intrinsic value + 50% of remaining time value
        if option_type == 'CALL':
            intrinsic = max(0, current_spy - strike)
        else:  # PUT
            intrinsic = max(0, strike - current_spy)

        # Estimate current option price (rough approximation)
        current_price = intrinsic + (entry_price - max(0, intrinsic)) * 0.7

        # Calculate P&L
        pnl_per_contract = (current_price - entry_price) * 100
        contracts = trade.get('contracts', 1) or 1
        total_pnl = pnl_per_contract * contracts
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        # Calculate time to expiration (rough estimate based on entry price)
        time_held = 0
        try:
            trade_timestamp = trade.get('timestamp')
            if trade_timestamp:
                if isinstance(trade_timestamp, str):
                    entry_time = datetime.fromisoformat(trade_timestamp.replace('Z', '+00:00'))
                else:
                    entry_time = trade_timestamp
                time_held = (datetime.now() - entry_time.replace(tzinfo=None)).total_seconds() / 3600  # hours
        except Exception as e:
            logger.debug(f" position-guidance: timestamp parse error: {e}")

        # Get GEX walls - with fallback
        logger.debug(" position-guidance: Querying gex_levels...")
        call_wall = strike + 10
        put_wall = strike - 10
        try:
            c.execute("SELECT call_wall, put_wall FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
            gex_row = c.fetchone()
            call_wall = gex_row['call_wall'] if gex_row and gex_row['call_wall'] else strike + 10
            put_wall = gex_row['put_wall'] if gex_row and gex_row['put_wall'] else strike - 10
            logger.debug(f" position-guidance: call_wall={call_wall}, put_wall={put_wall}")
        except Exception as e:
            logger.debug(f" position-guidance: gex_levels error: {e}")

        conn.close()
        logger.debug(" position-guidance: Database queries complete")

        # Generate position guidance
        prompt = f"""You are a professional position manager providing real-time guidance for an open options trade. Provide SPECIFIC next actions with exact prices and times.

CURRENT POSITION:
• Symbol: {trade.get('symbol') or 'SPY'}
• Strike: ${strike}
• Type: {option_type}
• Contracts: {trade.get('contracts') or 0}
• Entry Price: ${entry_price:.2f}
• Current Price (est): ${current_price:.2f}
• P&L: ${total_pnl:.2f} ({pnl_pct:+.1f}%)
• Time Held: {time_held:.1f} hours
• Entry: {trade.get('timestamp') or 'N/A'}

CURRENT MARKET:
• SPY: ${current_spy}
• VIX: {current_vix}
• Call Wall: ${call_wall}
• Put Wall: ${put_wall}
• Current Time: {datetime.now().strftime('%I:%M %p')}

ORIGINAL TRADE PLAN:
• Pattern: {trade.get('pattern_type') or 'N/A'}
• Expected Target: Estimate based on strike
• Original Stop: Estimate

Provide specific position management guidance:

1. CURRENT STATUS
   • Winning/Losing and by how much
   • Whether thesis is still valid
   • How close to target

2. NEXT ACTIONS (prioritized, specific)
   • Should I take partial profit NOW? How many contracts?
   • Should I add to winner? How many contracts?
   • Should I exit completely? Why?
   • Should I wait? Until when?

3. STOP LOSS ADJUSTMENT
   • Original stop loss
   • Recommended new stop (move to breakeven?)
   • Why adjust now

4. EXIT TRIGGERS (exact conditions)
   • Exit immediately if: (VIX level, SPY price)
   • Take profit if: (SPY price, time)
   • Cut loss if: (thesis broken)

5. GREEKS UPDATE
   • Estimated theta decay per day
   • Time urgency (days/hours left)
   • Delta exposure

6. TIME DECAY WATCH
   • Current time
   • Theta burn acceleration time
   • Recommended exit time if no movement

7. OPPORTUNITY ASSESSMENT
   • Should I add more contracts?
   • What's the risk/reward of adding?
   • What's the best-case scenario now?

Be extremely specific with prices, times, and contract quantities. Make this ACTIONABLE and URGENT."""

        guidance = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'trade': trade,
                'current_status': {
                    'current_price': current_price,
                    'total_pnl': total_pnl,
                    'pnl_pct': pnl_pct,
                    'time_held_hours': time_held
                },
                'market_context': {
                    'spy_price': current_spy,
                    'vix': current_vix,
                    'call_wall': call_wall,
                    'put_wall': put_wall
                },
                'guidance': guidance.content,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate position guidance: {str(e)}")


# ============================================================================
# 5. MARKET COMMENTARY WIDGET
# ============================================================================

@router.get("/market-commentary")
async def get_market_commentary():
    """
    Generates real-time market narration explaining what's happening NOW
    and what action to take IMMEDIATELY.

    Caches responses for 5 minutes to eliminate page load lag.
    """
    require_api_key()

    try:
        # Check cache first - return immediately if valid cache exists
        cached = get_cached_response('market_commentary')
        if cached:
            # Add cache flag
            cached['data']['from_cache'] = True
            return cached

        logger.debug(" market-commentary: Starting...")

        # =====================================================================
        # GET LIVE MARKET DATA (uses TradingVolatilityAPI, gex_history fallback)
        # =====================================================================
        logger.debug(" market-commentary: Fetching LIVE market data...")
        current_market = get_live_market_data('SPY')
        logger.debug(f" market-commentary: LIVE data source = {current_market.get('data_source')}")
        logger.debug(f" market-commentary: spot_price = {current_market.get('spot_price')}, vix = {current_market.get('vix')}")

        # Get psychology regime from live data
        logger.debug(" market-commentary: Computing psychology regime...")
        psychology = get_live_psychology_regime('SPY')
        logger.debug(f" market-commentary: regime = {psychology.get('regime_type')}, confidence = {psychology.get('confidence')}")

        # GEX levels from live data
        gex = {
            'call_wall': current_market.get('call_wall', 0),
            'put_wall': current_market.get('put_wall', 0),
            'flip_point': current_market.get('flip_point', 0)
        }
        logger.debug(f" market-commentary: call_wall={gex['call_wall']}, put_wall={gex['put_wall']}")

        # =====================================================================
        # DATABASE QUERIES (for positions - use autonomous_positions)
        # =====================================================================
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get open positions from autonomous_positions (has real data)
        logger.debug(" market-commentary: Querying autonomous_positions...")
        open_positions = 0
        try:
            c.execute("SELECT COUNT(*) as count FROM autonomous_positions WHERE status = 'OPEN'")
            result = c.fetchone()
            open_positions = result['count'] if result else 0
            logger.debug(f" market-commentary: open_positions = {open_positions}")
        except Exception as e:
            logger.debug(f" market-commentary: autonomous_positions error: {e}")

        # Get recent trade from autonomous_trade_log (has real data)
        logger.debug(" market-commentary: Querying autonomous_trade_log...")
        recent_trade = None
        try:
            c.execute("SELECT * FROM autonomous_trade_log ORDER BY timestamp DESC LIMIT 1")
            recent_trade_row = c.fetchone()
            recent_trade = dict(recent_trade_row) if recent_trade_row else None
            logger.debug(f" market-commentary: recent_trade = {bool(recent_trade)}")
        except Exception as e:
            logger.debug(f" market-commentary: autonomous_trade_log error: {e}")

        conn.close()
        logger.debug(" market-commentary: Data collection complete, generating AI response...")

        # Generate GEX context for better AI understanding
        gex_context = get_gex_context(current_market, gex)

        # Calculate key metrics for commentary
        spot = float(current_market.get('spot_price') or 0)
        call_wall = float(gex.get('call_wall') or 0)
        put_wall = float(gex.get('put_wall') or 0)
        flip_point = float(gex.get('flip_point') or 0)

        dist_to_call = ((call_wall - spot) / spot * 100) if spot > 0 and call_wall > 0 else 0
        dist_to_put = ((spot - put_wall) / spot * 100) if spot > 0 and put_wall > 0 else 0
        above_flip = spot > flip_point if flip_point > 0 else True

        # Generate commentary
        current_time = datetime.now().strftime('%I:%M %p CT')
        prompt = f"""You are a GEX-focused market analyst providing real-time trading intelligence. Speak directly to the trader with actionable insights based on dealer positioning.

TIME: {current_time}

═══════════════════════════════════════════════════════════════
CURRENT POSITIONING
═══════════════════════════════════════════════════════════════
SPY: ${spot:.2f}
VIX: {current_market.get('vix') or 0}
Net GEX: ${(current_market.get('net_gex') or 0)/1e9:.2f}B

DEALER LEVELS:
• Call Wall: ${call_wall:.0f} ({dist_to_call:.1f}% above spot)
• Put Wall: ${put_wall:.0f} ({dist_to_put:.1f}% below spot)
• Flip Point: ${flip_point:.0f} ({'ABOVE' if above_flip else 'BELOW'} current price)

{gex_context}

REGIME: {psychology.get('regime_type') or 'UNKNOWN'} ({psychology.get('confidence') or 0}% confidence)
TRAP WARNING: {psychology.get('psychology_trap') or 'NONE'}

POSITIONS: {open_positions} open
{f"Last: {recent_trade.get('symbol')} ${recent_trade.get('strike')} {recent_trade.get('option_type')}" if recent_trade else ""}

═══════════════════════════════════════════════════════════════
PROVIDE COMMENTARY
═══════════════════════════════════════════════════════════════

Give a brief, punchy market update (100-150 words) covering:

1. DEALER FLOW: What are market makers doing right now based on GEX? Are they buying or selling to hedge?

2. KEY LEVEL: What's the most important price level RIGHT NOW? (nearest wall, flip point, or breakout level)

3. ACTION CALL: ONE specific thing to do or watch in the next 30 minutes. Be precise with the price trigger.

4. RISK: What invalidates this setup? At what price should the trader step aside?

Write in short, punchy sentences. No fluff. Every word must add value. Reference specific prices from the data above."""

        commentary = llm.invoke(prompt)

        # Log the actual data being returned for debugging
        logger.debug(f"[RESPONSE] market-commentary returning:")
        logger.debug(f"  - data_source: {current_market.get('data_source')}")
        logger.debug(f"  - spot_price: ${current_market.get('spot_price', 0)}")
        logger.debug(f"  - net_gex: ${(current_market.get('net_gex', 0) or 0)/1e9:.2f}B")
        logger.debug(f"  - regime: {psychology.get('regime_type')}")

        response = {
            'success': True,
            'data': {
                'commentary': commentary.content,
                'market_data': current_market,
                'psychology': psychology,
                'gex': gex,
                'open_positions': open_positions,
                'generated_at': datetime.now().isoformat(),
                'from_cache': False,
                '_data_sources': {
                    'market_data': current_market.get('data_source', 'unknown'),
                    'positions': 'autonomous_positions',
                    'is_live': current_market.get('data_source') != 'default'
                }
            }
        }

        # Cache the response for subsequent requests
        set_cached_response('market_commentary', response)

        return response

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] market-commentary failed: {type(e).__name__}: {str(e)}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate commentary: {type(e).__name__}: {str(e)}")


# ============================================================================
# 5.5 UNIFIED INTELLIGENCE FEED - All data in one endpoint
# ============================================================================

@router.get("/intelligence-feed")
async def get_intelligence_feed():
    """
    Unified intelligence feed providing all market data in one call.
    Designed for the news feed style dashboard with expandable cards.

    Returns structured data for:
    - Market snapshot (live GEX, price, VIX)
    - Options flow (smart money indicators)
    - Historical context (day-over-day GEX)
    - Intraday momentum
    - Pattern performance
    - AI commentary

    Each section includes timestamps and refresh intervals.
    Cached for 2 minutes.
    """
    try:
        # Check cache first
        cached = get_cached_response('intelligence_feed')
        if cached:
            cached['data']['from_cache'] = True
            return cached

        logger.debug("[intelligence-feed] Fetching all data sources...")

        # Fetch all data in parallel conceptually (Python will execute sequentially but fast)
        market_data = get_live_market_data('SPY')
        psychology = get_live_psychology_regime('SPY')
        options_flow = get_options_flow_data()
        historical_gex = get_historical_gex_context()
        intraday = get_intraday_momentum()
        skew = get_skew_data()
        patterns = get_regime_pattern_performance()
        strike_clustering = get_strike_clustering()
        vix_structure = get_vix_term_structure()
        trading_windows = get_trading_windows()
        key_events = get_key_events()

        # Build GEX context
        gex = {
            'call_wall': market_data.get('call_wall', 0),
            'put_wall': market_data.get('put_wall', 0),
            'flip_point': market_data.get('flip_point', 0)
        }
        gex_context = get_gex_context(market_data, gex)

        # Calculate key metrics
        spot = float(market_data.get('spot_price') or 0)
        call_wall = float(gex.get('call_wall') or 0)
        put_wall = float(gex.get('put_wall') or 0)
        flip_point = float(gex.get('flip_point') or 0)
        net_gex = float(market_data.get('net_gex') or 0)

        dist_to_call = ((call_wall - spot) / spot * 100) if spot > 0 and call_wall > 0 else 0
        dist_to_put = ((spot - put_wall) / spot * 100) if spot > 0 and put_wall > 0 else 0
        above_flip = spot > flip_point if flip_point > 0 else True

        # Determine overall market bias
        bullish_signals = 0
        bearish_signals = 0

        if net_gex > 0: bullish_signals += 1
        else: bearish_signals += 1

        if above_flip: bullish_signals += 1
        else: bearish_signals += 1

        if options_flow['sentiment'] == 'BULLISH': bullish_signals += 1
        elif options_flow['sentiment'] == 'BEARISH': bearish_signals += 1

        if intraday['direction'] == 'BULLISH': bullish_signals += 1
        elif intraday['direction'] == 'BEARISH': bearish_signals += 1

        if historical_gex['gex_trend'] in ['RISING', 'STRONGLY_RISING']: bullish_signals += 1
        elif historical_gex['gex_trend'] in ['FALLING', 'STRONGLY_FALLING']: bearish_signals += 1

        if bullish_signals > bearish_signals + 1:
            overall_bias = 'BULLISH'
        elif bearish_signals > bullish_signals + 1:
            overall_bias = 'BEARISH'
        else:
            overall_bias = 'NEUTRAL'

        current_time = datetime.now()

        response = {
            'success': True,
            'data': {
                'generated_at': current_time.isoformat(),
                'from_cache': False,

                # Overall market bias summary
                'market_bias': {
                    'direction': overall_bias,
                    'bullish_signals': bullish_signals,
                    'bearish_signals': bearish_signals,
                    'confidence': max(bullish_signals, bearish_signals) / 5 * 100,
                    'updated_at': current_time.isoformat(),
                    'refresh_interval': '2 minutes'
                },

                # Live market snapshot
                'market_snapshot': {
                    'spy_price': spot,
                    'vix': market_data.get('vix', 0),
                    'net_gex': net_gex,
                    'net_gex_billions': round(net_gex / 1e9, 2),
                    'call_wall': call_wall,
                    'put_wall': put_wall,
                    'flip_point': flip_point,
                    'dist_to_call_pct': round(dist_to_call, 2),
                    'dist_to_put_pct': round(dist_to_put, 2),
                    'above_flip': above_flip,
                    'regime': psychology.get('regime_type', 'UNKNOWN'),
                    'regime_confidence': psychology.get('confidence', 50),
                    'psychology_trap': psychology.get('psychology_trap'),
                    'data_source': market_data.get('data_source', 'unknown'),
                    'updated_at': current_time.isoformat(),
                    'refresh_interval': '2 minutes'
                },

                # Options flow / smart money
                'options_flow': {
                    'put_call_ratio': options_flow['put_call_ratio'],
                    'sentiment': options_flow['sentiment'],
                    'unusual_call_volume': options_flow['unusual_call_volume'],
                    'unusual_put_volume': options_flow['unusual_put_volume'],
                    'unusual_strikes': options_flow['unusual_strikes'],
                    'smart_money_signal': options_flow['smart_money_signal'],
                    'updated_at': options_flow['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # Historical GEX context
                'gex_history': {
                    'yesterday_gex_billions': round(historical_gex['yesterday_gex'] / 1e9, 2),
                    'today_gex_billions': round(historical_gex['today_gex'] / 1e9, 2),
                    'gex_change_billions': round(historical_gex['gex_change'] / 1e9, 2),
                    'gex_trend': historical_gex['gex_trend'],
                    'flip_point_movement': historical_gex['flip_point_movement'],
                    'yesterday_flip': historical_gex['yesterday_flip'],
                    'today_flip': historical_gex['today_flip'],
                    'updated_at': historical_gex['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # Intraday momentum
                'intraday_momentum': {
                    'gex_1h_ago_billions': round(intraday['gex_1h_ago'] / 1e9, 2),
                    'gex_current_billions': round(intraday['gex_current'] / 1e9, 2),
                    'gex_change_1h_billions': round(intraday['gex_change_1h'] / 1e9, 2),
                    'momentum': intraday['momentum'],
                    'speed': intraday['speed'],
                    'direction': intraday['direction'],
                    'updated_at': intraday['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # Volatility skew
                'volatility_skew': {
                    'put_call_skew': skew['put_call_skew'],
                    'skew_trend': skew['skew_trend'],
                    'iv_rank': skew['iv_rank'],
                    'directional_bias': skew['directional_bias'],
                    'interpretation': skew['interpretation'],
                    'updated_at': skew['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # Pattern performance
                'pattern_performance': {
                    'current_regime': patterns['current_regime'],
                    'patterns': patterns['patterns'][:5],  # Top 5 patterns
                    'best_pattern': patterns['best_pattern_today'],
                    'updated_at': patterns['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '30 minutes'
                },

                # Strike clustering / OI concentration
                'strike_clustering': {
                    'institutional_bias': strike_clustering['institutional_bias'],
                    'magnetic_levels': strike_clustering['magnetic_levels'],
                    'highest_oi_strike': strike_clustering['highest_oi_strike'],
                    'top_call_strikes': strike_clustering['top_call_strikes'][:3],
                    'top_put_strikes': strike_clustering['top_put_strikes'][:3],
                    'interpretation': strike_clustering['interpretation'],
                    'updated_at': strike_clustering['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # VIX term structure
                'vix_term_structure': {
                    'vix_spot': vix_structure['vix_spot'],
                    'vix_1m': vix_structure['vix_1m'],
                    'term_structure': vix_structure['term_structure'],
                    'contango_pct': vix_structure['contango_pct'],
                    'signal': vix_structure['signal'],
                    'interpretation': vix_structure['interpretation'],
                    'updated_at': vix_structure['updated_at'] or current_time.isoformat(),
                    'refresh_interval': '5 minutes'
                },

                # Trading windows
                'trading_windows': {
                    'current_time': trading_windows['current_time'],
                    'market_status': trading_windows['market_status'],
                    'current_window': trading_windows['current_window'],
                    'next_window': trading_windows['next_window'],
                    'minutes_until_next': trading_windows['minutes_until_next'],
                    'recommendation': trading_windows['recommendation'],
                    'avoid_trading': trading_windows['avoid_trading'],
                    'updated_at': trading_windows['updated_at'],
                    'refresh_interval': '1 minute'
                },

                # Key events
                'key_events': {
                    'high_impact_today': key_events['high_impact_today'],
                    'fed_day': key_events['fed_day'],
                    'triple_witching': key_events['triple_witching'],
                    'today_events': key_events['today_events'][:3],
                    'interpretation': key_events['interpretation'],
                    'updated_at': key_events['updated_at'],
                    'refresh_interval': '30 minutes'
                },

                # GEX interpretation context (for AI display)
                'gex_interpretation': gex_context,

                # Refresh schedule info
                '_refresh_schedule': {
                    'market_snapshot': '2 minutes',
                    'options_flow': '5 minutes',
                    'gex_history': '5 minutes',
                    'intraday_momentum': '5 minutes',
                    'volatility_skew': '5 minutes',
                    'pattern_performance': '30 minutes',
                    'strike_clustering': '5 minutes',
                    'vix_term_structure': '5 minutes',
                    'trading_windows': '1 minute',
                    'key_events': '30 minutes'
                }
            }
        }

        # Cache the response
        set_cached_response('intelligence_feed', response)

        logger.debug("[intelligence-feed] Response generated successfully")
        return response

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] intelligence-feed failed: {type(e).__name__}: {str(e)}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate intelligence feed: {type(e).__name__}: {str(e)}")


# ============================================================================
# 6. STRATEGY COMPARISON ENGINE
# ============================================================================

@router.get("/compare-strategies")
async def compare_strategies():
    """
    Compares all available trading strategies for current market conditions.
    Shows directional, iron condor, wait options with head-to-head comparison.
    """
    require_api_key()

    try:
        logger.debug(" compare-strategies: Starting...")

        # =====================================================================
        # GET LIVE MARKET DATA (uses TradingVolatilityAPI, gex_history fallback)
        # =====================================================================
        logger.debug(" compare-strategies: Fetching LIVE market data...")
        market = get_live_market_data('SPY')
        logger.debug(f" compare-strategies: LIVE data source = {market.get('data_source')}")
        logger.debug(f" compare-strategies: spot_price = {market.get('spot_price')}, vix = {market.get('vix')}")

        # Get psychology regime from live data
        logger.debug(" compare-strategies: Computing psychology regime...")
        psychology = get_live_psychology_regime('SPY')
        logger.debug(f" compare-strategies: regime = {psychology.get('regime_type')}, confidence = {psychology.get('confidence')}")

        # GEX levels from live data
        gex = {
            'call_wall': market.get('call_wall', 0),
            'put_wall': market.get('put_wall', 0),
            'flip_point': market.get('flip_point', 0)
        }
        logger.debug(f" compare-strategies: call_wall={gex['call_wall']}, put_wall={gex['put_wall']}")

        # =====================================================================
        # DATABASE QUERIES (for account/performance - use existing tables)
        # =====================================================================
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get account value from autonomous_config
        logger.debug(" compare-strategies: Querying autonomous_config for capital...")
        account_value = 10000
        try:
            c.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
            config_row = c.fetchone()
            if config_row and config_row['value']:
                account_value = float(config_row['value'])
            logger.debug(f" compare-strategies: account_value = {account_value}")
        except Exception as e:
            logger.debug(f" compare-strategies: autonomous_config error: {e}")

        # Get pattern performance from backtest results if available
        logger.debug(" compare-strategies: Querying backtest_summary for pattern performance...")
        pattern_performance = []
        try:
            c.execute("""
                SELECT
                    strategy_name as pattern_type,
                    total_trades as trades,
                    win_rate,
                    avg_profit_per_trade as avg_pnl
                FROM backtest_summary
                ORDER BY win_rate DESC
                LIMIT 5
            """)
            pattern_performance = [dict(row) for row in c.fetchall()]
            logger.debug(f" compare-strategies: pattern_performance count = {len(pattern_performance)}")
        except Exception as e:
            logger.debug(f" compare-strategies: trades pattern error: {e}")

        conn.close()
        logger.debug(" compare-strategies: Database queries complete")

        # Generate strategy comparison
        prompt = f"""You are a professional trader comparing available strategies for the current market. Provide a detailed head-to-head comparison with specific trade setups.

CURRENT MARKET:
• SPY: ${market.get('spot_price') or 0}
• VIX: {market.get('vix') or 0}
• Net GEX: ${(market.get('net_gex') or 0)/1e9:.2f}B
• Regime: {psychology.get('regime_type', 'UNKNOWN')}
• Confidence: {psychology.get('confidence') or 0}%
• Call Wall: ${gex.get('call_wall') or 0}
• Put Wall: ${gex.get('put_wall') or 0}

ACCOUNT:
• Balance: ${account_value:.2f}

RECENT PATTERN PERFORMANCE (30 days):
{chr(10).join([f"• {p.get('pattern_type', 'N/A')}: {(p.get('win_rate') or 0)*100:.0f}% win rate" for p in pattern_performance])}

Compare these 3 strategies for RIGHT NOW:

OPTION 1: DIRECTIONAL TRADE (Aggressive)
• Exact strike and type (CALL/PUT)
• Cost per contract and total
• Probability of profit
• Expected value
• Max loss
• Best if: Specific condition
• Pros: 3 bullet points
• Cons: 3 bullet points

OPTION 2: IRON CONDOR (Conservative)
• Exact strikes (sell and buy)
• Credit collected
• Probability of profit
• Expected value
• Max loss
• Best if: Specific condition
• Pros: 3 bullet points
• Cons: 3 bullet points

OPTION 3: WAIT FOR BETTER SETUP
• What you're waiting for
• What invalidates current setup
• Expected timeline
• Pros: 2 bullet points
• Cons: 2 bullet points

Then provide:

HEAD-TO-HEAD COMPARISON TABLE:
                    Directional | Iron Condor | Wait
Profit Potential        ⭐⭐⭐   |     ⭐⭐     |  -
Risk Level             🔴🔴🔴  |    🟡🟡    | 🟢
Win Probability           X%    |      Y%    | N/A
Expected Value          $XXX    |     $XX    | $0
Time Sensitivity         HIGH   |     LOW    | -

AI RECOMMENDATION: Choose one and explain why in 2-3 sentences with specific reasoning based on current market regime and confidence.

ALTERNATIVE: If trader prefers different risk profile, what's the alternative?

DON'T WAIT IF: Explain why waiting would be a mistake (if applicable).

Be specific with all dollar amounts, strikes, and probabilities."""

        comparison = llm.invoke(prompt)

        # Log the actual data being returned for debugging
        logger.debug(f"[RESPONSE] compare-strategies returning:")
        logger.debug(f"  - data_source: {market.get('data_source')}")
        logger.debug(f"  - spot_price: ${market.get('spot_price', 0)}")
        logger.debug(f"  - regime: {psychology.get('regime_type')}")

        return {
            'success': True,
            'data': {
                'comparison': comparison.content,
                'market': market,
                'psychology': psychology,
                'gex': gex,
                'account_value': account_value,
                'pattern_performance': pattern_performance,
                'generated_at': datetime.now().isoformat(),
                '_data_sources': {
                    'market_data': market.get('data_source', 'unknown'),
                    'account': 'autonomous_config',
                    'patterns': 'backtest_summary',
                    'is_live': market.get('data_source') != 'default'
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare strategies: {str(e)}")


# ============================================================================
# 7. OPTION GREEKS EXPLAINER
# ============================================================================

class GreeksExplainerRequest(BaseModel):
    greek: str  # delta, theta, gamma, vega
    value: float
    strike: float
    current_price: float
    contracts: int
    option_type: str
    days_to_expiration: Optional[int] = 3


@router.post("/explain-greek")
async def explain_greek(request: GreeksExplainerRequest):
    """
    Provides context-aware explanation of a specific Greek for the trader's position.
    """
    require_api_key()

    try:
        # Generate contextual explanation
        prompt = f"""You are teaching an options trader about Greeks in the context of THEIR actual trade. Explain this Greek with specific examples using THEIR numbers.

THEIR POSITION:
• Strike: ${request.strike}
• Current Price: ${request.current_price}
• Type: {request.option_type}
• Contracts: {request.contracts}
• {request.greek.upper()}: {request.value}
• Days to Expiration: {request.days_to_expiration}

Explain {request.greek.upper()} with:

1. WHAT THIS MEANS (simple definition)
   • What this Greek measures
   • Why it matters for options

2. FOR YOUR TRADE SPECIFICALLY
   • What {request.value} means in dollars
   • Impact on your {request.contracts} contracts
   • Examples with SPY price movements

3. EXAMPLE SCENARIOS (use their numbers)
   • If SPY moves +$1/$5/$10
   • If SPY moves -$1/$5/$10
   • Dollar impact on their position

4. WHY THIS VALUE IS GOOD/BAD
   • Is {request.value} optimal for this trade type?
   • Too high/low? What's ideal?
   • Sweet spot for directional plays

5. ACTIONABLE ADVICE
   • What this Greek tells you to DO
   • Time urgency (if applicable)
   • When to exit based on this Greek

Keep it under 200 words but be specific with dollar amounts and examples using THEIR trade."""

        explanation = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'greek': request.greek,
                'value': request.value,
                'explanation': explanation.content,
                'position_context': {
                    'strike': request.strike,
                    'current_price': request.current_price,
                    'contracts': request.contracts,
                    'option_type': request.option_type,
                    'days_to_expiration': request.days_to_expiration
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to explain Greek: {str(e)}")


# Health check
@router.get("/health")
async def health_check():
    """Health check for AI intelligence endpoints"""
    return {
        'success': True,
        'status': 'All AI intelligence systems operational',
        'features': [
            'Pre-Trade Safety Checklist',
            'Real-Time Trade Explainer',
            'Daily Trading Plan Generator',
            'Position Management Assistant',
            'Market Commentary Widget',
            'Strategy Comparison Engine',
            'Option Greeks Explainer'
        ]
    }


# ============================================================================
# DATA SOURCE DIAGNOSTIC ENDPOINT
# ============================================================================

@router.get("/data-sources")
async def get_data_sources():
    """
    DIAGNOSTIC: Shows EXACTLY what data is available from each source.
    Returns row counts, latest timestamps, and sample values.
    This proves where data comes from and if it's real/current.
    """
    diagnostic = {
        'timestamp': datetime.now().isoformat(),
        'live_api_status': {},
        'database_tables': {},
        'data_flow_summary': {}
    }

    # =========================================================================
    # 1. CHECK LIVE API SOURCE (TradingVolatilityAPI)
    # =========================================================================
    logger.debug("[DIAGNOSTIC] Checking TradingVolatilityAPI...")
    if TradingVolatilityAPI:
        try:
            api = TradingVolatilityAPI()
            gex_data = api.get_net_gamma('SPY')
            if gex_data and 'error' not in gex_data:
                diagnostic['live_api_status']['TradingVolatilityAPI'] = {
                    'status': 'WORKING',
                    'spot_price': float(gex_data.get('spot_price') or 0),
                    'net_gex': float(gex_data.get('net_gex') or 0),
                    'call_wall': float(gex_data.get('call_wall') or 0),
                    'put_wall': float(gex_data.get('put_wall') or 0),
                    'flip_point': float(gex_data.get('flip_point') or 0),
                    'data_timestamp': gex_data.get('timestamp', 'unknown')
                }
            else:
                diagnostic['live_api_status']['TradingVolatilityAPI'] = {
                    'status': 'ERROR',
                    'error': str(gex_data.get('error', 'Unknown error'))
                }
        except Exception as e:
            diagnostic['live_api_status']['TradingVolatilityAPI'] = {
                'status': 'EXCEPTION',
                'error': str(e)
            }
    else:
        diagnostic['live_api_status']['TradingVolatilityAPI'] = {
            'status': 'NOT_LOADED',
            'error': 'Module not imported'
        }

    # =========================================================================
    # 2. CHECK UNIFIED DATA PROVIDER (VIX, Price)
    # =========================================================================
    logger.debug("[DIAGNOSTIC] Checking Unified Data Provider...")
    if get_vix:
        try:
            vix_value = get_vix()
            diagnostic['live_api_status']['UnifiedDataProvider_VIX'] = {
                'status': 'WORKING' if vix_value else 'NO_DATA',
                'vix': float(vix_value) if vix_value else None
            }
        except Exception as e:
            diagnostic['live_api_status']['UnifiedDataProvider_VIX'] = {
                'status': 'EXCEPTION',
                'error': str(e)
            }
    else:
        diagnostic['live_api_status']['UnifiedDataProvider_VIX'] = {
            'status': 'NOT_LOADED'
        }

    if get_price:
        try:
            price_value = get_price('SPY')
            diagnostic['live_api_status']['UnifiedDataProvider_Price'] = {
                'status': 'WORKING' if price_value else 'NO_DATA',
                'spy_price': float(price_value) if price_value else None
            }
        except Exception as e:
            diagnostic['live_api_status']['UnifiedDataProvider_Price'] = {
                'status': 'EXCEPTION',
                'error': str(e)
            }
    else:
        diagnostic['live_api_status']['UnifiedDataProvider_Price'] = {
            'status': 'NOT_LOADED'
        }

    # =========================================================================
    # 3. CHECK DATABASE TABLES
    # =========================================================================
    logger.debug("[DIAGNOSTIC] Checking database tables...")
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Tables to check with their key columns - ALL 42 TABLES
        tables_to_check = [
            # Core GEX tables
            ('gex_history', 'timestamp', ['spot_price', 'net_gex', 'call_wall', 'put_wall', 'flip_point']),
            ('market_data', 'timestamp', ['spot_price', 'vix', 'net_gex', 'data_source']),
            ('gex_levels', 'timestamp', ['call_wall', 'put_wall', 'flip_point', 'net_gex']),
            # Psychology tables
            ('psychology_analysis', 'timestamp', ['regime_type', 'confidence', 'psychology_trap']),
            ('regime_signals', 'timestamp', ['primary_regime_type', 'confidence_score', 'spy_price']),
            ('psychology_notifications', 'timestamp', ['notification_type', 'regime_type', 'message']),
            # Account tables
            ('account_state', 'timestamp', ['account_value', 'cash_balance']),
            ('autonomous_config', None, ['key', 'value']),
            # Trade tables
            ('trades', 'timestamp', ['symbol', 'strike', 'status', 'realized_pnl']),
            ('autonomous_positions', 'entry_date', ['symbol', 'strike', 'status', 'entry_price']),
            ('autonomous_closed_trades', 'exit_date', ['symbol', 'strike', 'realized_pnl']),
            ('autonomous_open_positions', 'entry_date', ['symbol', 'strike', 'status']),
            ('autonomous_trade_log', 'date', ['action', 'details']),
            ('autonomous_trade_activity', 'timestamp', ['action', 'symbol', 'reason']),
            ('autonomous_trader_logs', 'timestamp', ['log_type', 'symbol', 'pattern_detected']),
            # Equity tracking
            ('autonomous_equity_snapshots', 'timestamp', ['equity', 'cash', 'daily_pnl']),
            ('autonomous_live_status', 'timestamp', ['status', 'positions_open', 'daily_pnl']),
            # Backtest tables
            ('backtest_results', 'timestamp', ['strategy_name', 'win_rate', 'total_trades']),
            ('backtest_summary', 'timestamp', ['symbol', 'psychology_win_rate']),
            # Scanner/alerts
            ('scanner_history', 'timestamp', ['symbols_scanned', 'scan_type']),
            ('alerts', 'created_at', ['symbol', 'alert_type', 'active']),
            ('alert_history', 'timestamp', ['alert_type', 'triggered_value']),
            # Setups/strategies
            ('trade_setups', 'created_at', ['symbol', 'setup_type', 'status']),
            ('strategy_config', None, ['strategy_name', 'enabled']),
            # Probability
            ('probability_outcomes', 'timestamp', ['prediction_type', 'actual_outcome']),
            ('probability_weights', None, ['factor_name', 'weight']),
            ('calibration_history', 'timestamp', ['calibration_type', 'after_accuracy']),
            # SPX tables
            ('spx_institutional_positions', 'timestamp', ['symbol', 'status']),
            ('spx_debug_logs', 'timestamp', ['category', 'message']),
            # ML tables
            ('ml_models', 'created_at', ['model_name', 'accuracy', 'status']),
            ('ml_predictions', 'timestamp', ['prediction_type', 'confidence']),
            # Other
            ('conversations', 'timestamp', ['user_message', 'ai_response']),
            ('recommendations', 'timestamp', ['symbol', 'strategy', 'confidence']),
            ('positions', 'opened_at', ['symbol', 'status', 'pnl']),
            ('performance', 'date', ['total_trades', 'win_rate']),
        ]

        for table_name, timestamp_col, sample_cols in tables_to_check:
            try:
                # Get row count
                c.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                count_result = c.fetchone()
                row_count = count_result['count'] if count_result else 0

                table_info = {
                    'row_count': row_count,
                    'has_data': row_count > 0
                }

                if row_count > 0:
                    # Get latest row
                    if timestamp_col:
                        c.execute(f"SELECT * FROM {table_name} ORDER BY {timestamp_col} DESC LIMIT 1")
                    else:
                        c.execute(f"SELECT * FROM {table_name} LIMIT 1")
                    latest_row = c.fetchone()

                    if latest_row:
                        table_info['latest_row'] = {}
                        for col in sample_cols:
                            if col in latest_row:
                                val = latest_row[col]
                                # Convert to serializable format
                                if hasattr(val, 'isoformat'):
                                    val = val.isoformat()
                                table_info['latest_row'][col] = val

                        if timestamp_col and timestamp_col in latest_row:
                            ts = latest_row[timestamp_col]
                            if hasattr(ts, 'isoformat'):
                                table_info['latest_timestamp'] = ts.isoformat()
                            else:
                                table_info['latest_timestamp'] = str(ts)

                diagnostic['database_tables'][table_name] = table_info

            except Exception as e:
                diagnostic['database_tables'][table_name] = {
                    'status': 'ERROR',
                    'error': str(e)
                }

        conn.close()

    except Exception as e:
        diagnostic['database_tables']['connection_error'] = str(e)

    # =========================================================================
    # 4. SUMMARIZE DATA FLOW FOR AI INTELLIGENCE ENDPOINTS
    # =========================================================================
    logger.debug("[DIAGNOSTIC] Generating data flow summary...")

    # Get live market data to show what endpoints will actually use
    live_data = get_live_market_data('SPY')
    live_psychology = get_live_psychology_regime('SPY')

    diagnostic['data_flow_summary'] = {
        'daily_trading_plan': {
            'market_data_source': live_data.get('data_source', 'unknown'),
            'spot_price': live_data.get('spot_price', 0),
            'vix': live_data.get('vix', 0),
            'net_gex': live_data.get('net_gex', 0),
            'call_wall': live_data.get('call_wall', 0),
            'put_wall': live_data.get('put_wall', 0),
            'flip_point': live_data.get('flip_point', 0),
            'regime': live_psychology.get('regime_type', 'UNKNOWN'),
            'regime_confidence': live_psychology.get('confidence', 0)
        },
        'market_commentary': {
            'uses_same_as': 'daily_trading_plan',
            'data_is_live': live_data.get('data_source') != 'default'
        },
        'compare_strategies': {
            'uses_same_as': 'daily_trading_plan',
            'data_is_live': live_data.get('data_source') != 'default'
        },
        'pre_trade_checklist': {
            'account_data_from': 'account_state or autonomous_config',
            'trade_history_from': 'trades table'
        },
        'trade_explainer': {
            'trade_data_from': 'trades table',
            'market_context_from': 'market_data table'
        },
        'position_guidance': {
            'position_from': 'trades table (status=OPEN)',
            'market_context_from': 'market_data + gex_levels'
        }
    }

    # Data freshness assessment
    is_data_fresh = (
        live_data.get('data_source') != 'default' and
        live_data.get('spot_price', 0) > 0
    )

    diagnostic['overall_status'] = {
        'live_api_working': live_data.get('data_source') in ['TradingVolatilityAPI', 'gex_history_database'],
        'data_is_fresh': is_data_fresh,
        'spot_price_available': live_data.get('spot_price', 0) > 0,
        'gex_data_available': live_data.get('net_gex', 0) != 0 or live_data.get('call_wall', 0) > 0,
        'recommendation': 'DATA READY' if is_data_fresh else 'CHECK API CONNECTIONS'
    }

    return {
        'success': True,
        'diagnostic': diagnostic
    }
