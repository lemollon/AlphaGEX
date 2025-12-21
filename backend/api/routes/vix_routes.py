"""
VIX Hedge Manager API routes.
With fallback data sources when VIX module is unavailable.

Features:
- Multi-source VIX data fetching with priority fallback
- Input validation and error handling
- Retry logic with exponential backoff
- Response caching with TTL
- Correlation ID tracking for request tracing
- Structured logging for operational visibility
"""

import logging
import os
import time
import uuid
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional, Callable, TypeVar, List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
import requests

# Configure logger with structured output
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - Unified thresholds (fixes inconsistency issue #20)
# ============================================================================

class VIXConfig:
    """Unified VIX configuration constants"""
    # Stress level thresholds (unified across routes and manager)
    THRESHOLD_LOW = 15.0
    THRESHOLD_ELEVATED = 20.0
    THRESHOLD_HIGH = 25.0
    THRESHOLD_EXTREME = 30.0

    # Position size multipliers
    MULTIPLIER_NORMAL = 1.0
    MULTIPLIER_ELEVATED = 0.75
    MULTIPLIER_HIGH = 0.50
    MULTIPLIER_EXTREME = 0.25

    # Default VIX value when all sources fail
    DEFAULT_VIX = 18.0

    # Cache TTL in seconds
    CACHE_TTL_CURRENT = 60  # 1 minute for current data
    CACHE_TTL_HISTORY = 300  # 5 minutes for history

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # seconds

    # API timeouts
    API_TIMEOUT = 10  # seconds


# ============================================================================
# CACHING LAYER (fixes issue #32)
# ============================================================================

class TTLCache:
    """Thread-safe cache with TTL expiration"""

    def __init__(self):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL"""
        with self._lock:
            self._cache[key] = (value, time.time() + ttl)

    def invalidate(self, key: str):
        """Remove key from cache"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()


# Global cache instance
_cache = TTLCache()


# ============================================================================
# CORRELATION ID TRACKING (fixes issue #8)
# ============================================================================

class RequestContext:
    """Thread-local request context for correlation ID tracking"""
    _context = threading.local()

    @classmethod
    def get_correlation_id(cls) -> str:
        """Get current correlation ID or generate one"""
        if not hasattr(cls._context, 'correlation_id'):
            cls._context.correlation_id = str(uuid.uuid4())[:8]
        return cls._context.correlation_id

    @classmethod
    def set_correlation_id(cls, correlation_id: str):
        """Set correlation ID for current request"""
        cls._context.correlation_id = correlation_id

    @classmethod
    def clear(cls):
        """Clear context after request"""
        if hasattr(cls._context, 'correlation_id'):
            delattr(cls._context, 'correlation_id')


def log_with_context(level: str, message: str, **kwargs):
    """Log message with correlation ID and structured data"""
    correlation_id = RequestContext.get_correlation_id()
    extra_data = ' '.join(f'{k}={v}' for k, v in kwargs.items())
    log_message = f"[{correlation_id}] {message}"
    if extra_data:
        log_message += f" | {extra_data}"

    getattr(logger, level)(log_message)


# ============================================================================
# RETRY LOGIC (fixes issue #14)
# ============================================================================

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = VIXConfig.MAX_RETRIES,
    base_delay: float = VIXConfig.RETRY_BASE_DELAY,
    operation_name: str = "operation"
) -> Optional[T]:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        operation_name: Name for logging

    Returns:
        Function result or None if all retries failed
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                log_with_context(
                    'warning',
                    f"{operation_name} failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s",
                    error=str(e)
                )
                time.sleep(delay)
            else:
                log_with_context(
                    'error',
                    f"{operation_name} failed after {max_retries + 1} attempts",
                    error=str(e)
                )

    return None


# ============================================================================
# METRICS COLLECTION (fixes issue #36)
# ============================================================================

class VIXMetrics:
    """Simple metrics collector for VIX operations"""

    _lock = threading.Lock()
    _metrics = {
        'requests_total': 0,
        'requests_success': 0,
        'requests_fallback': 0,
        'requests_error': 0,
        'source_hits': {},
        'avg_response_time_ms': 0,
        'last_vix_value': None,
        'last_vix_source': None,
        'last_update': None,
    }

    @classmethod
    def record_request(cls, success: bool, fallback: bool, source: str,
                       vix_value: float, response_time_ms: float):
        """Record a VIX request"""
        with cls._lock:
            cls._metrics['requests_total'] += 1

            if success:
                cls._metrics['requests_success'] += 1
            else:
                cls._metrics['requests_error'] += 1

            if fallback:
                cls._metrics['requests_fallback'] += 1

            # Track source hits
            cls._metrics['source_hits'][source] = cls._metrics['source_hits'].get(source, 0) + 1

            # Update rolling average response time
            total = cls._metrics['requests_total']
            old_avg = cls._metrics['avg_response_time_ms']
            cls._metrics['avg_response_time_ms'] = old_avg + (response_time_ms - old_avg) / total

            cls._metrics['last_vix_value'] = vix_value
            cls._metrics['last_vix_source'] = source
            cls._metrics['last_update'] = datetime.now().isoformat()

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Get current metrics"""
        with cls._lock:
            return cls._metrics.copy()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_last_trading_day() -> str:
    """Get the last trading day date"""
    now = datetime.now()
    if now.weekday() == 5:  # Saturday
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    elif now.weekday() == 6:  # Sunday
        return (now - timedelta(days=2)).strftime('%Y-%m-%d')
    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
        # Before market open
        if now.weekday() == 0:  # Monday
            return (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')


def get_stress_level(vix: float) -> tuple[str, float]:
    """
    Get stress level and position multiplier from VIX value.
    Uses unified thresholds from VIXConfig.

    Returns:
        Tuple of (stress_level, position_multiplier)
    """
    if vix >= VIXConfig.THRESHOLD_EXTREME:
        return ('extreme', VIXConfig.MULTIPLIER_EXTREME)
    elif vix >= VIXConfig.THRESHOLD_HIGH:
        return ('high', VIXConfig.MULTIPLIER_HIGH)
    elif vix >= VIXConfig.THRESHOLD_ELEVATED:
        return ('elevated', VIXConfig.MULTIPLIER_ELEVATED)
    else:
        return ('normal', VIXConfig.MULTIPLIER_NORMAL)


def calculate_fallback_iv_percentile(vix: float) -> float:
    """
    Calculate IV percentile estimate based on VIX value.
    Uses historical VIX distribution (fixes issue #16).

    Historical VIX distribution (1990-2024):
    - Mean: ~19.5
    - Median: ~17.5
    - 10th percentile: ~12
    - 25th percentile: ~14
    - 75th percentile: ~22
    - 90th percentile: ~28
    - 95th percentile: ~33
    """
    if vix < 12:
        return 5.0
    elif vix < 14:
        return 15.0
    elif vix < 16:
        return 30.0
    elif vix < 18:
        return 45.0
    elif vix < 20:
        return 55.0
    elif vix < 22:
        return 65.0
    elif vix < 25:
        return 75.0
    elif vix < 28:
        return 82.0
    elif vix < 33:
        return 90.0
    elif vix < 40:
        return 95.0
    else:
        return 99.0


def calculate_fallback_realized_vol(vix: float) -> float:
    """
    Calculate realized volatility estimate based on VIX.
    Uses historical IV-RV relationship (fixes issue #17).

    Historical analysis shows:
    - IV typically trades at 2-5 point premium to RV
    - Premium expands during high vol periods
    - Can invert during vol spikes (RV > IV briefly)
    """
    # Base estimate: VIX minus typical IV premium
    # Premium scales with VIX level
    if vix < 15:
        premium = 2.0  # Low vol: small premium
    elif vix < 20:
        premium = 3.0  # Normal: typical premium
    elif vix < 25:
        premium = 4.0  # Elevated: larger premium
    elif vix < 30:
        premium = 5.0  # High: significant premium
    else:
        premium = 6.0  # Extreme: large premium

    realized_vol = max(vix - premium, vix * 0.7)  # Floor at 70% of VIX
    return round(realized_vol, 2)


def calculate_term_structure(vix_spot: float) -> Dict[str, Any]:
    """
    Calculate estimated VIX term structure.
    Returns M1, M2 estimates and structure type.
    """
    # Dynamic contango estimation based on VIX level
    if vix_spot >= 35:
        # Panic/crisis - often backwardation or flat
        contango_m1 = -0.02  # -2% (backwardation)
        contango_m2 = -0.01  # Slight backwardation
    elif vix_spot >= 25:
        # High stress - reduced contango
        contango_m1 = 0.02  # 2%
        contango_m2 = 0.04  # 4%
    elif vix_spot >= 20:
        # Elevated - normal contango
        contango_m1 = 0.05  # 5%
        contango_m2 = 0.08  # 8%
    elif vix_spot >= 15:
        # Normal - typical contango
        contango_m1 = 0.05  # 5%
        contango_m2 = 0.08  # 8%
    else:
        # Low/complacent - steep contango
        contango_m1 = 0.07  # 7%
        contango_m2 = 0.12  # 12%

    vix_m1 = vix_spot * (1 + contango_m1)
    vix_m2 = vix_spot * (1 + contango_m2)

    term_structure_m1 = contango_m1 * 100
    term_structure_m2 = contango_m2 * 100

    if term_structure_m1 > 1:
        structure_type = "contango"
    elif term_structure_m1 < -1:
        structure_type = "backwardation"
    else:
        structure_type = "flat"

    return {
        'vix_m1': round(vix_m1, 2),
        'vix_m2': round(vix_m2, 2),
        'term_structure_m1_pct': round(term_structure_m1, 2),
        'term_structure_m2_pct': round(term_structure_m2, 2),
        'structure_type': structure_type
    }


# ============================================================================
# VIX DATA FETCHERS WITH RETRY LOGIC
# ============================================================================

def fetch_vix_from_tradier() -> Optional[Dict[str, Any]]:
    """Fetch VIX from Tradier API with retry.

    NOTE: Respects TRADIER_SANDBOX env setting. $VIX.X quotes work in both
    sandbox and production modes. Using proper credentials for each mode.
    """
    def _fetch():
        from data.tradier_data_fetcher import TradierDataFetcher
        # Let TradierDataFetcher handle sandbox/production selection based on env
        # This ensures correct API key is used for the mode
        tradier = TradierDataFetcher()  # Respects TRADIER_SANDBOX env var
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            source = 'tradier_sandbox' if tradier.sandbox else 'tradier_production'
            return {
                'vix_spot': float(vix_quote['last']),
                'vix_source': source,
                'is_estimated': False
            }
        return None

    return retry_with_backoff(_fetch, max_retries=2, operation_name="Tradier VIX fetch")


def fetch_vix_from_unified_provider() -> Optional[Dict[str, Any]]:
    """Fetch VIX from unified data provider"""
    try:
        from data.unified_data_provider import get_vix
        vix_value = get_vix()
        if vix_value:
            if isinstance(vix_value, (int, float)) and vix_value > 0:
                return {
                    'vix_spot': float(vix_value),
                    'vix_source': 'unified_provider',
                    'is_estimated': False
                }
            elif isinstance(vix_value, dict) and vix_value.get('value', 0) > 0:
                return {
                    'vix_spot': float(vix_value['value']),
                    'vix_source': vix_value.get('source', 'unified_provider'),
                    'is_estimated': False
                }
    except Exception as e:
        log_with_context('debug', "Unified provider VIX fetch failed", error=str(e))
    return None


def fetch_vix_from_yahoo() -> Optional[Dict[str, Any]]:
    """Fetch VIX from Yahoo Finance (FREE - no API key needed)"""
    def _fetch():
        import yfinance as yf
        vix_ticker = yf.Ticker("^VIX")

        # Method 1: Try info dict
        try:
            info = vix_ticker.info
            price = info.get('regularMarketPrice') or info.get('previousClose') or info.get('open', 0)
            if price and price > 0:
                return {
                    'vix_spot': float(price),
                    'vix_source': 'yahoo',
                    'is_estimated': False
                }
        except Exception:
            pass

        # Method 2: Try history
        hist = vix_ticker.history(period='5d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            if price > 0:
                return {
                    'vix_spot': price,
                    'vix_source': 'yahoo',
                    'is_estimated': False
                }

        return None

    return retry_with_backoff(_fetch, max_retries=2, operation_name="Yahoo Finance VIX fetch")


def fetch_vix_from_polygon() -> Optional[Dict[str, Any]]:
    """Fetch VIX from Polygon API"""
    polygon_key = os.getenv('POLYGON_API_KEY')
    if not polygon_key:
        return None

    def _fetch():
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

        response = requests.get(url, params=params, timeout=VIXConfig.API_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK' and data.get('results'):
                return {
                    'vix_spot': float(data['results'][0]['c']),
                    'vix_source': 'polygon',
                    'is_estimated': False
                }
        return None

    return retry_with_backoff(_fetch, max_retries=2, operation_name="Polygon VIX fetch")


def fetch_vvix_from_polygon() -> Optional[float]:
    """Fetch VVIX from Polygon API"""
    polygon_key = os.getenv('POLYGON_API_KEY')
    if not polygon_key:
        return None

    try:
        from data.polygon_data_fetcher import polygon_fetcher
        vvix = polygon_fetcher.get_current_price('I:VVIX')
        if vvix and vvix > 0:
            return vvix
    except Exception as e:
        log_with_context('debug', "VVIX fetch failed", error=str(e))

    return None


def get_vix_fallback_data() -> Dict[str, Any]:
    """Get VIX data."""
    from data.vix_fetcher import get_vix_with_source

    vix_spot, vix_source = get_vix_with_source()

    vix_data = {
        'vix_spot': vix_spot,
        'vix_source': vix_source,
        'is_estimated': False,
        'vix_m1': 0,
        'vix_m2': 0,
        'term_structure_m1_pct': 0,
        'term_structure_m2_pct': 0,
        'structure_type': 'unknown',
        'vvix': None,
        'vvix_source': 'none',
        'vix_stress_level': 'normal',
        'position_size_multiplier': 1.0
    }

    log_with_context('info', f"VIX fetched successfully",
                    source=vix_source, value=vix_spot)

    # Try to get VVIX
    vvix = fetch_vvix_from_polygon()
    if vvix:
        vix_data['vvix'] = vvix
        vix_data['vvix_source'] = 'polygon'

    # Calculate term structure
    term_data = calculate_term_structure(vix_data['vix_spot'])
    vix_data.update(term_data)

    # Calculate stress level
    stress_level, multiplier = get_stress_level(vix_data['vix_spot'])
    vix_data['vix_stress_level'] = stress_level
    vix_data['position_size_multiplier'] = multiplier

    # Record metrics
    response_time_ms = (time.time() - start_time) * 1000
    VIXMetrics.record_request(
        success=vix_data['vix_source'] != 'default',
        fallback=True,
        source=vix_data['vix_source'],
        vix_value=vix_data['vix_spot'],
        response_time_ms=response_time_ms
    )

    return vix_data


# ============================================================================
# API ROUTER
# ============================================================================

router = APIRouter(prefix="/api/vix", tags=["VIX"])


@router.get("/hedge-signal")
async def get_vix_hedge_signal(
    portfolio_delta: float = Query(
        default=0,
        ge=-10000000,  # Max $10M short delta
        le=10000000,   # Max $10M long delta
        description="Current portfolio delta exposure in dollars"
    ),
    portfolio_value: float = Query(
        default=100000,
        ge=0,          # Non-negative
        le=100000000,  # Max $100M portfolio
        description="Total portfolio value in dollars"
    )
):
    """
    Generate a VIX-based hedge signal for portfolio protection.

    This is a SIGNAL GENERATOR only - does not auto-execute trades.
    Falls back to basic signal when vix_hedge_manager is unavailable.

    Args:
        portfolio_delta: Current portfolio delta exposure (-10M to +10M)
        portfolio_value: Total portfolio value (0 to 100M)

    Returns:
        Hedge signal with confidence, reasoning, and recommended action
    """
    RequestContext.set_correlation_id(str(uuid.uuid4())[:8])
    start_time = time.time()

    try:
        log_with_context('info', "Hedge signal request received",
                        portfolio_delta=portfolio_delta, portfolio_value=portfolio_value)

        # Try vix_hedge_manager first
        try:
            from core.vix_hedge_manager import get_vix_hedge_manager

            manager = get_vix_hedge_manager()
            signal = manager.generate_hedge_signal(
                portfolio_delta=portfolio_delta,
                portfolio_value=portfolio_value
            )

            # Convert confidence to percentage for consistency
            confidence_pct = signal.confidence if signal.confidence > 1 else signal.confidence * 100

            response_time_ms = (time.time() - start_time) * 1000
            VIXMetrics.record_request(
                success=True, fallback=False,
                source='vix_hedge_manager',
                vix_value=signal.metrics.get('vix_spot', 0),
                response_time_ms=response_time_ms
            )

            log_with_context('info', "Hedge signal generated",
                           signal_type=signal.signal_type.value,
                           confidence=confidence_pct)

            return {
                "success": True,
                "data": {
                    "timestamp": signal.timestamp.isoformat(),
                    "signal_type": signal.signal_type.value,
                    "confidence": confidence_pct,  # Always percentage
                    "vol_regime": signal.vol_regime.value,
                    "reasoning": signal.reasoning,
                    "recommended_action": signal.recommended_action,
                    "risk_warning": signal.risk_warning,
                    "metrics": signal.metrics,
                    "fallback_mode": False
                }
            }
        except ImportError as e:
            log_with_context('debug', "VIX hedge manager not available, using fallback", error=str(e))
        except Exception as e:
            log_with_context('warning', "VIX hedge manager error, using fallback", error=str(e))

        # FALLBACK: Generate basic signal from VIX level
        vix_data = get_vix_fallback_data()
        vix_spot = vix_data['vix_spot']

        # Determine signal based on VIX level (using unified thresholds)
        if vix_spot >= VIXConfig.THRESHOLD_EXTREME:
            signal_type = 'hedge_recommended'
            confidence = 80.0
            vol_regime = 'extreme'
            reasoning = f"VIX at {vix_spot:.1f} indicates extreme volatility. Consider hedging."
            recommended_action = "Add protective puts or reduce position sizes"
            risk_warning = "High volatility environment - expect large price swings"
        elif vix_spot >= VIXConfig.THRESHOLD_HIGH:
            signal_type = 'monitor_closely'
            confidence = 60.0
            vol_regime = 'high'
            reasoning = f"VIX at {vix_spot:.1f} indicates elevated volatility. Monitor closely."
            recommended_action = "Consider reducing position sizes"
            risk_warning = "Elevated risk - prepare hedge strategy"
        elif vix_spot >= VIXConfig.THRESHOLD_ELEVATED:
            signal_type = 'no_action'
            confidence = 50.0
            vol_regime = 'elevated'
            reasoning = f"VIX at {vix_spot:.1f} is slightly elevated. Normal caution."
            recommended_action = "Maintain current positions with stops"
            risk_warning = None
        else:
            signal_type = 'no_action'
            confidence = 70.0
            vol_regime = 'normal'
            reasoning = f"VIX at {vix_spot:.1f} indicates low volatility. No hedging needed."
            recommended_action = "Normal trading conditions"
            risk_warning = None

        response_time_ms = (time.time() - start_time) * 1000
        VIXMetrics.record_request(
            success=True, fallback=True,
            source=vix_data.get('vix_source', 'fallback'),
            vix_value=vix_spot,
            response_time_ms=response_time_ms
        )

        log_with_context('info', "Fallback hedge signal generated",
                        signal_type=signal_type, confidence=confidence)

        return {
            "success": True,
            "data": {
                "timestamp": datetime.now().isoformat(),
                "signal_type": signal_type,
                "confidence": confidence,  # Always percentage
                "vol_regime": vol_regime,
                "reasoning": reasoning,
                "recommended_action": recommended_action,
                "risk_warning": risk_warning,
                "metrics": {
                    "vix_spot": vix_spot,
                    "vix_source": vix_data.get('vix_source', 'fallback')
                },
                "fallback_mode": True
            }
        }
    except Exception as e:
        log_with_context('error', "Hedge signal generation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Hedge signal error: {str(e)}")
    finally:
        RequestContext.clear()


@router.get("/signal-history")
async def get_vix_signal_history(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days of history to retrieve"
    )
):
    """
    Get historical VIX hedge signals.

    Args:
        days: Number of days of history (1-365)

    Returns:
        List of historical signals with timestamp, type, VIX level, and action
    """
    RequestContext.set_correlation_id(str(uuid.uuid4())[:8])

    # Check cache first
    cache_key = f"signal_history_{days}"
    cached = _cache.get(cache_key)
    if cached:
        log_with_context('debug', "Returning cached signal history", days=days)
        return cached

    try:
        log_with_context('info', "Signal history request", days=days)

        try:
            from core.vix_hedge_manager import get_vix_hedge_manager

            manager = get_vix_hedge_manager()
            history = manager.get_signal_history(days)

            if history.empty:
                response = {"success": True, "data": [], "fallback_mode": False}
                _cache.set(cache_key, response, VIXConfig.CACHE_TTL_HISTORY)
                return response

            formatted_data = []
            for _, row in history.iterrows():
                try:
                    date_str = str(row.get('signal_date', ''))
                    time_str = str(row.get('signal_time', '00:00:00'))
                    timestamp = f"{date_str}T{time_str}"
                except Exception:
                    timestamp = None

                # Normalize confidence to percentage
                raw_confidence = row.get('confidence', 0)
                confidence = float(raw_confidence) if raw_confidence else None
                if confidence and confidence <= 1:
                    confidence *= 100

                formatted_data.append({
                    "timestamp": timestamp,
                    "signal_type": row.get('signal_type', 'no_action'),
                    "vix_level": float(row.get('vix_spot', 0)) if row.get('vix_spot') else None,
                    "confidence": confidence,
                    "action_taken": row.get('recommended_action', 'Monitored')
                })

            response = {"success": True, "data": formatted_data, "fallback_mode": False}
            _cache.set(cache_key, response, VIXConfig.CACHE_TTL_HISTORY)

            log_with_context('info', "Signal history retrieved", count=len(formatted_data))
            return response

        except ImportError as e:
            log_with_context('debug', "VIX hedge manager not available for history", error=str(e))
            return {
                "success": True,
                "data": [],
                "fallback_mode": True,
                "message": "Signal history unavailable - module not loaded"
            }
    except Exception as e:
        log_with_context('error', "Signal history retrieval failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        RequestContext.clear()


@router.get("/current")
async def get_vix_current():
    """
    Get current VIX data and analysis with VVIX and stress indicators.

    Falls back to direct API calls if vix_hedge_manager is unavailable.
    Response includes fallback_mode flag to indicate data source quality.

    Returns:
        Current VIX data including spot, term structure, IV percentile,
        realized vol, stress level, and position size multiplier
    """
    RequestContext.set_correlation_id(str(uuid.uuid4())[:8])
    start_time = time.time()

    # Check cache first
    cache_key = "vix_current"
    cached = _cache.get(cache_key)
    if cached:
        log_with_context('debug', "Returning cached VIX current data")
        return cached

    try:
        log_with_context('info', "Current VIX data request")

        # Try to use vix_hedge_manager first
        try:
            from core.vix_hedge_manager import get_vix_hedge_manager
            manager = get_vix_hedge_manager()

            vix_data = manager.get_vix_data()
            vix_spot = vix_data.get('vix_spot', VIXConfig.DEFAULT_VIX)

            iv_percentile = manager.calculate_iv_percentile(vix_spot)
            realized_vol = manager.calculate_realized_vol('SPY')
            vol_regime = manager.get_vol_regime(vix_spot)

            response_time_ms = (time.time() - start_time) * 1000
            VIXMetrics.record_request(
                success=True, fallback=False,
                source=vix_data.get('vix_source', 'vix_hedge_manager'),
                vix_value=vix_spot,
                response_time_ms=response_time_ms
            )

            response = {
                "success": True,
                "data": {
                    "vix_spot": vix_spot,
                    "vix_source": vix_data.get('vix_source', 'unknown'),
                    "vix_m1": vix_data.get('vix_m1', 0),
                    "vix_m2": vix_data.get('vix_m2', 0),
                    "is_estimated": vix_data.get('is_estimated', True),
                    "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                    "term_structure_m2_pct": vix_data.get('term_structure_m2_pct', 0),
                    "structure_type": vix_data.get('structure_type', 'unknown'),
                    "vvix": vix_data.get('vvix'),
                    "vvix_source": vix_data.get('vvix_source', 'none'),
                    "iv_percentile": iv_percentile,
                    "realized_vol_20d": realized_vol,
                    "iv_rv_spread": round(vix_spot - realized_vol, 2),
                    "vol_regime": vol_regime.value,
                    "vix_stress_level": vix_data.get('vix_stress_level', 'unknown'),
                    "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                    "data_date": get_last_trading_day(),
                    "timestamp": datetime.now().isoformat(),
                    "fallback_mode": False
                }
            }

            _cache.set(cache_key, response, VIXConfig.CACHE_TTL_CURRENT)
            log_with_context('info', "VIX current data retrieved",
                           vix_spot=vix_spot, source=vix_data.get('vix_source'))
            return response

        except ImportError as e:
            log_with_context('debug', "VIX hedge manager not available, using fallback", error=str(e))
        except Exception as e:
            log_with_context('warning', "VIX hedge manager error, using fallback", error=str(e))

        # FALLBACK: Use direct API calls when vix_hedge_manager is unavailable
        vix_data = get_vix_fallback_data()
        vix_spot = vix_data['vix_spot']

        # Use improved fallback calculations
        iv_percentile = calculate_fallback_iv_percentile(vix_spot)
        realized_vol = calculate_fallback_realized_vol(vix_spot)
        iv_rv_spread = round(vix_spot - realized_vol, 2)

        # Estimate vol regime from VIX level
        if vix_spot >= VIXConfig.THRESHOLD_EXTREME:
            vol_regime = 'extreme'
        elif vix_spot >= VIXConfig.THRESHOLD_HIGH:
            vol_regime = 'high'
        elif vix_spot >= VIXConfig.THRESHOLD_ELEVATED:
            vol_regime = 'elevated'
        elif vix_spot >= VIXConfig.THRESHOLD_LOW:
            vol_regime = 'normal'
        else:
            vol_regime = 'low'

        response_time_ms = (time.time() - start_time) * 1000
        VIXMetrics.record_request(
            success=True, fallback=True,
            source=vix_data.get('vix_source', 'fallback'),
            vix_value=vix_spot,
            response_time_ms=response_time_ms
        )

        response = {
            "success": True,
            "data": {
                "vix_spot": vix_spot,
                "vix_source": vix_data.get('vix_source', 'fallback'),
                "vix_m1": vix_data.get('vix_m1', 0),
                "vix_m2": vix_data.get('vix_m2', 0),
                "is_estimated": vix_data.get('is_estimated', True),
                "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                "term_structure_m2_pct": vix_data.get('term_structure_m2_pct', 0),
                "structure_type": vix_data.get('structure_type', 'unknown'),
                "vvix": vix_data.get('vvix'),
                "vvix_source": vix_data.get('vvix_source', 'none'),
                "iv_percentile": iv_percentile,
                "realized_vol_20d": realized_vol,
                "iv_rv_spread": iv_rv_spread,
                "vol_regime": vol_regime,
                "vix_stress_level": vix_data.get('vix_stress_level', 'normal'),
                "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                "data_date": get_last_trading_day(),
                "timestamp": datetime.now().isoformat(),
                "fallback_mode": True
            }
        }

        _cache.set(cache_key, response, VIXConfig.CACHE_TTL_CURRENT)
        log_with_context('info', "Fallback VIX current data retrieved",
                        vix_spot=vix_spot, source=vix_data.get('vix_source'))
        return response

    except Exception as e:
        log_with_context('error', "VIX current data retrieval failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"VIX data error (fallback also failed): {type(e).__name__}: {str(e)}"
        )
    finally:
        RequestContext.clear()


@router.get("/metrics")
async def get_vix_metrics():
    """
    Get VIX API metrics for monitoring.

    Returns request counts, error rates, source distribution,
    average response times, and last known values.
    """
    return {
        "success": True,
        "data": VIXMetrics.get_metrics()
    }


@router.post("/cache/clear")
async def clear_vix_cache():
    """
    Clear VIX data cache.

    Use this to force fresh data retrieval on next request.
    """
    _cache.clear()
    log_with_context('info', "VIX cache cleared")
    return {
        "success": True,
        "message": "VIX cache cleared"
    }


@router.get("/debug")
async def get_vix_debug():
    """
    VIX debugging endpoint - shows all VIX-related data and sources.

    Provides detailed information for troubleshooting VIX data issues.
    """
    RequestContext.set_correlation_id(str(uuid.uuid4())[:8])

    try:
        log_with_context('info', "VIX debug request")

        try:
            from core.vix_hedge_manager import get_vix_hedge_manager

            manager = get_vix_hedge_manager()
            vix_data = manager.get_vix_data()
            vix_spot = vix_data.get('vix_spot', VIXConfig.DEFAULT_VIX)

            iv_percentile = manager.calculate_iv_percentile(vix_spot)
            realized_vol = manager.calculate_realized_vol('SPY')
            vol_regime = manager.get_vol_regime(vix_spot)

            raw_sources = {}

            try:
                from data.unified_data_provider import get_vix as unified_get_vix
                raw_sources['unified_provider'] = unified_get_vix()
            except Exception as e:
                raw_sources['unified_provider'] = f"Error: {e}"

            try:
                from data.polygon_data_fetcher import polygon_fetcher
                raw_sources['polygon'] = polygon_fetcher.get_current_price('I:VIX')
            except Exception as e:
                raw_sources['polygon'] = f"Error: {e}"

            return {
                "success": True,
                "data": {
                    "vix_data": vix_data,
                    "raw_sources": raw_sources,
                    "calculated_metrics": {
                        "iv_percentile": iv_percentile,
                        "realized_vol_20d": realized_vol,
                        "iv_rv_spread": vix_spot - realized_vol,
                        "vol_regime": vol_regime.value
                    },
                    "trading_impact": {
                        "stress_level": vix_data.get('vix_stress_level', 'unknown'),
                        "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                        "should_reduce_risk": vix_data.get('vix_stress_level') in ['high', 'extreme'],
                        "vvix_available": vix_data.get('vvix') is not None
                    },
                    "config": {
                        "thresholds": {
                            "low": VIXConfig.THRESHOLD_LOW,
                            "elevated": VIXConfig.THRESHOLD_ELEVATED,
                            "high": VIXConfig.THRESHOLD_HIGH,
                            "extreme": VIXConfig.THRESHOLD_EXTREME
                        },
                        "multipliers": {
                            "normal": VIXConfig.MULTIPLIER_NORMAL,
                            "elevated": VIXConfig.MULTIPLIER_ELEVATED,
                            "high": VIXConfig.MULTIPLIER_HIGH,
                            "extreme": VIXConfig.MULTIPLIER_EXTREME
                        }
                    },
                    "metrics": VIXMetrics.get_metrics(),
                    "timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            # Even on error, return useful debug info
            return {
                "success": False,
                "error": str(e),
                "fallback_data": get_vix_fallback_data(),
                "config": {
                    "thresholds": {
                        "low": VIXConfig.THRESHOLD_LOW,
                        "elevated": VIXConfig.THRESHOLD_ELEVATED,
                        "high": VIXConfig.THRESHOLD_HIGH,
                        "extreme": VIXConfig.THRESHOLD_EXTREME
                    }
                },
                "metrics": VIXMetrics.get_metrics(),
                "timestamp": datetime.now().isoformat()
            }
    finally:
        RequestContext.clear()


@router.get("/test-sources")
async def test_vix_sources():
    """
    Detailed VIX source testing - shows exactly what each source returns.

    Use this to debug VIX data issues and verify API connectivity.
    """
    RequestContext.set_correlation_id(str(uuid.uuid4())[:8])

    results = {
        "polygon_api_key_set": bool(os.getenv('POLYGON_API_KEY')),
        "polygon_key_prefix": os.getenv('POLYGON_API_KEY', '')[:8] + '...' if os.getenv('POLYGON_API_KEY') else None,
        "tradier_api_key_set": bool(os.getenv('TRADIER_API_KEY')),
        "sources": {},
        "timestamp": datetime.now().isoformat()
    }

    log_with_context('info', "VIX source test request")

    # Test 1: Direct Polygon API call for I:VIX
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            # Test the prev endpoint
            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/prev"
            params = {"apiKey": polygon_key}

            response = requests.get(url, params=params, timeout=VIXConfig.API_TIMEOUT)
            results['sources']['polygon_prev_endpoint'] = {
                'url': url.replace(polygon_key, 'API_KEY'),
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else response.text[:500]
            }

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    results['sources']['polygon_prev_endpoint']['extracted_vix'] = float(data['results'][0]['c'])
        except Exception as e:
            results['sources']['polygon_prev_endpoint'] = {'error': str(e)}

        # Test range endpoint
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/range/1/day/{from_date}/{to_date}"
            params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

            response = requests.get(url, params=params, timeout=VIXConfig.API_TIMEOUT)
            results['sources']['polygon_range_endpoint'] = {
                'url': url.replace(polygon_key, 'API_KEY'),
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else response.text[:500]
            }

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    results['sources']['polygon_range_endpoint']['extracted_vix'] = float(data['results'][0]['c'])
        except Exception as e:
            results['sources']['polygon_range_endpoint'] = {'error': str(e)}
    else:
        results['sources']['polygon_prev_endpoint'] = {'error': 'POLYGON_API_KEY not set'}
        results['sources']['polygon_range_endpoint'] = {'error': 'POLYGON_API_KEY not set'}

    # Test 2: polygon_fetcher.get_current_price
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        vix_via_fetcher = polygon_fetcher.get_current_price('I:VIX')
        results['sources']['polygon_fetcher_get_current_price'] = {
            'value': vix_via_fetcher,
            'success': vix_via_fetcher is not None and vix_via_fetcher > 0
        }
    except Exception as e:
        results['sources']['polygon_fetcher_get_current_price'] = {'error': str(e)}

    # Test 3: unified_data_provider.get_vix
    try:
        from data.unified_data_provider import get_vix as unified_get_vix
        vix_unified = unified_get_vix()
        results['sources']['unified_provider_get_vix'] = {
            'value': vix_unified,
            'success': vix_unified is not None and vix_unified > 0
        }
    except Exception as e:
        results['sources']['unified_provider_get_vix'] = {'error': str(e)}

    # Test 4: vix_hedge_manager.get_vix_data
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager
        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()
        results['sources']['vix_hedge_manager'] = {
            'vix_spot': vix_data.get('vix_spot'),
            'vix_source': vix_data.get('vix_source'),
            'is_estimated': vix_data.get('is_estimated', True),
            'success': vix_data.get('vix_spot', 0) > 0 and vix_data.get('vix_source') != 'default'
        }
    except Exception as e:
        results['sources']['vix_hedge_manager'] = {'error': str(e)}

    # Test 5: Tradier VIX
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)
        results['sources']['tradier_sandbox_mode'] = use_sandbox

        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            vix = float(vix_quote['last'])
            results['sources']['tradier_$VIX.X'] = {
                'value': vix,
                'success': True,
                'raw_response': vix_quote
            }
        else:
            results['sources']['tradier_$VIX.X'] = {
                'value': None,
                'success': False,
                'raw_response': vix_quote,
                'note': 'vix_quote is None or has no last price'
            }
    except Exception as e:
        results['sources']['tradier_$VIX.X'] = {'error': str(e)}

    # Test other Tradier symbols
    tradier_api_key = os.getenv('TRADIER_API_KEY')
    if tradier_api_key:
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
            tradier = TradierDataFetcher(sandbox=use_sandbox)

            for symbol in ['VIX', 'VIXW']:
                try:
                    data = tradier.get_quote(symbol)
                    if data:
                        price = float(data.get('last', 0) or data.get('close', 0) or 0)
                        results['sources'][f'tradier_{symbol}'] = {
                            'value': price,
                            'raw_response': data,
                            'success': price > 0
                        }
                    else:
                        results['sources'][f'tradier_{symbol}'] = {
                            'value': None,
                            'success': False,
                            'note': 'get_quote returned None'
                        }
                except Exception as e:
                    results['sources'][f'tradier_{symbol}'] = {'error': str(e)}
        except Exception as e:
            results['sources']['tradier'] = {'error': str(e)}
    else:
        results['sources']['tradier'] = {'error': 'TRADIER_API_KEY not set'}

    # Test 6: Yahoo Finance
    try:
        import yfinance as yf
        vix_ticker = yf.Ticker("^VIX")

        # Test info dict
        try:
            info = vix_ticker.info
            info_price = info.get('regularMarketPrice') or info.get('previousClose') or info.get('open', 0)
            results['sources']['yahoo_info'] = {
                'value': float(info_price) if info_price else None,
                'regularMarketPrice': info.get('regularMarketPrice'),
                'previousClose': info.get('previousClose'),
                'success': info_price is not None and info_price > 0
            }
        except Exception as e:
            results['sources']['yahoo_info'] = {'error': str(e)}

        # Test history
        try:
            hist = vix_ticker.history(period='5d')
            if not hist.empty:
                hist_price = float(hist['Close'].iloc[-1])
                results['sources']['yahoo_history'] = {
                    'value': hist_price,
                    'data_points': len(hist),
                    'success': hist_price > 0
                }
            else:
                results['sources']['yahoo_history'] = {'error': 'Empty history'}
        except Exception as e:
            results['sources']['yahoo_history'] = {'error': str(e)}

    except ImportError:
        results['sources']['yahoo'] = {'error': 'yfinance not installed'}
    except Exception as e:
        results['sources']['yahoo'] = {'error': str(e)}

    # Summary
    successful_sources = [k for k, v in results['sources'].items() if isinstance(v, dict) and v.get('success')]
    results['summary'] = {
        'working_sources': successful_sources,
        'total_sources_tested': len(results['sources']),
        'any_source_working': len(successful_sources) > 0
    }

    log_with_context('info', "VIX source test completed",
                    working_sources=len(successful_sources),
                    total_sources=len(results['sources']))

    RequestContext.clear()
    return results
