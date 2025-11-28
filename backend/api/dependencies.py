"""
Shared dependencies for AlphaGEX API routes.

This module contains all shared instances, utilities, and helper functions
that are used across multiple route modules.
"""

import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, TypedDict

import requests


class VIXDataDict(TypedDict, total=False):
    """Type definition for VIX data response"""
    value: float
    source: str
    is_live: bool
    timestamp: str
    error: str


class RSICacheEntry(TypedDict):
    """Type definition for RSI cache entry"""
    data: Dict[str, Any]
    timestamp: datetime

# Add parent directories to path for module imports
backend_dir = Path(__file__).parent.parent
parent_dir = backend_dir.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(backend_dir))

# Import existing AlphaGEX logic
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from core.intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open, MultiStrategyOptimizer
from db.config_and_database import STRATEGIES, MM_STATES
from database_adapter import get_connection
from core.probability_calculator import ProbabilityCalculator

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from unified_data_provider import get_data_provider, get_quote, get_price, get_vix
    UNIFIED_DATA_AVAILABLE = True
except ImportError:
    UNIFIED_DATA_AVAILABLE = False
    get_data_provider = None
    get_quote = None
    get_price = None
    get_vix = None

# ============================================================================
# Singleton Instances (shared across all routes)
# ============================================================================

api_client = TradingVolatilityAPI()
claude_ai = ClaudeIntelligence()
monte_carlo = MonteCarloEngine()
pricer = BlackScholesPricer()
strategy_optimizer = MultiStrategyOptimizer()
probability_calc = ProbabilityCalculator()

# ============================================================================
# RSI Cache (thread-safe)
# ============================================================================

_rsi_cache: Dict[str, RSICacheEntry] = {}
_rsi_cache_ttl: int = 300  # 5 minutes
_rsi_cache_max_size: int = 100
_rsi_cache_lock: threading.Lock = threading.Lock()


def _cleanup_rsi_cache() -> None:
    """Remove expired entries and enforce max size limit. Must be called with lock held."""
    now = datetime.now()
    expired_keys = [
        key for key, entry in _rsi_cache.items()
        if (now - entry['timestamp']).total_seconds() > _rsi_cache_ttl
    ]
    for key in expired_keys:
        del _rsi_cache[key]

    if len(_rsi_cache) > _rsi_cache_max_size:
        sorted_entries = sorted(_rsi_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_entries[:len(_rsi_cache) - _rsi_cache_max_size]:
            del _rsi_cache[key]


def get_cached_rsi(cache_key: str) -> Optional[dict]:
    """Thread-safe cache read"""
    with _rsi_cache_lock:
        if cache_key in _rsi_cache:
            cached_entry = _rsi_cache[cache_key]
            cache_age = (datetime.now() - cached_entry['timestamp']).total_seconds()
            if cache_age < _rsi_cache_ttl:
                return cached_entry['data'].copy()
    return None


def set_cached_rsi(cache_key: str, data: dict) -> None:
    """Thread-safe cache write with cleanup"""
    with _rsi_cache_lock:
        _cleanup_rsi_cache()
        _rsi_cache[cache_key] = {
            'data': data.copy(),
            'timestamp': datetime.now()
        }


# ============================================================================
# Helper Functions
# ============================================================================

def validate_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Validate stock symbol parameter to prevent injection attacks and API errors.

    Returns:
        (is_valid, cleaned_symbol or error_message)
    """
    if not symbol:
        return False, "Symbol cannot be empty"

    symbol = symbol.strip().upper()

    if len(symbol) > 5:
        return False, f"Symbol too long: {len(symbol)} characters (max 5)"

    if not symbol.isalnum():
        return False, "Symbol must contain only alphanumeric characters"

    blocked_patterns = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', '--', ';', '/*']
    for pattern in blocked_patterns:
        if pattern in symbol:
            return False, "Invalid symbol: contains blocked pattern"

    return True, symbol


def fetch_vix_with_metadata(polygon_key: Optional[str] = None) -> VIXDataDict:
    """
    Fetch VIX with metadata - Tradier (live) or Polygon (fallback).

    Returns dict with:
    - value: VIX value (float)
    - source: 'tradier' | 'polygon' | 'default'
    - is_live: True if from real API, False if default
    - timestamp: ISO timestamp of data
    - error: Error message if fetch failed (optional)
    """
    vix_data = {
        'value': 18.0,
        'source': 'default',
        'is_live': False,
        'timestamp': datetime.now().isoformat()
    }

    # Try Tradier first (real-time)
    if UNIFIED_DATA_AVAILABLE and get_vix:
        try:
            vix_value = get_vix()
            if vix_value and vix_value > 0:
                vix_data['value'] = float(vix_value)
                vix_data['source'] = 'tradier'
                vix_data['is_live'] = True
                return vix_data
        except Exception as e:
            print(f"Tradier VIX fetch failed: {e}")

    # Fallback to Polygon
    if not polygon_key:
        vix_data['error'] = 'No Polygon.io API key configured'
        return vix_data

    try:
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK' and data.get('results'):
                vix_data['value'] = float(data['results'][0]['c'])
                vix_data['source'] = 'polygon'
                vix_data['is_live'] = True
                if 'error' in vix_data:
                    del vix_data['error']
            else:
                vix_data['error'] = f"Polygon.io returned no VIX data: {data.get('status', 'unknown')}"
        else:
            vix_data['error'] = f"Polygon.io HTTP {response.status_code}"
    except Exception as e:
        vix_data['error'] = f"VIX fetch failed: {str(e)}"

    return vix_data
