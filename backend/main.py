"""
AlphaGEX FastAPI Backend
Main application entry point - Professional Options Intelligence Platform
"""

import os
import sys
import asyncio
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path to import existing AlphaGEX modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# Import route modules (refactored from monolithic main.py)
from backend.api.routes import (
    vix_routes,
    spx_routes,
    system_routes,
    trader_routes,
    backtest_routes,
    database_routes,
    gex_routes,
    gamma_routes,
    core_routes,
    optimizer_routes,
    ai_routes,
    probability_routes,
    notification_routes,
    misc_routes,
    alerts_routes,
    setups_routes,
    scanner_routes,
    autonomous_routes,
    psychology_routes,
    ai_intelligence_routes,
    wheel_routes,
    export_routes,
    ml_routes,
    spx_backtest_routes,
    jobs_routes,  # Background job system for long-running tasks
    regime_routes,  # Regime signals - 80+ columns of analysis data
    volatility_surface_routes,  # Volatility surface analysis (previously orphaned)
    zero_dte_backtest_routes,  # 0DTE Iron Condor hybrid scaling backtest
    fortress_routes,  # FORTRESS Aggressive Iron Condor bot endpoints
    faith_routes,  # FAITH 2DTE Paper Iron Condor bot endpoints
    grace_routes,  # GRACE 1DTE Paper Iron Condor bot endpoints (FAITH comparison)
    solomon_routes,  # SOLOMON Directional Spread bot endpoints
    gideon_routes,  # GIDEON Aggressive Directional Spread bot endpoints
    anchor_routes,  # ANCHOR SPX Iron Condor bot endpoints
    samson_routes,  # SAMSON Aggressive SPX Iron Condor bot endpoints
    logs_routes,  # Comprehensive logs API for ALL 22 logging tables
    scan_activity_routes,  # Scan Activity - EVERY scan with full reasoning for FORTRESS/SOLOMON
    discernment_routes,  # DISCERNMENT ML-powered scanner
    daily_manna_routes,  # Daily Manna - Economic news with faith-based devotionals
    watchtower_routes,  # WATCHTOWER - 0DTE Gamma Live real-time visualization
    glory_routes,  # GLORY - Weekly Gamma visualization for stocks/ETFs
    data_transparency_routes,  # Data Transparency - expose ALL hidden collected data
    docs_routes,  # Documentation - codebase search and source code retrieval
    proverbs_routes,  # PROVERBS - Feedback Loop Intelligence System for bot learning
    events_routes,  # Trading Events - auto-detected events for equity curves
    prophet_routes,  # PROPHET - ML Advisory System for strategy recommendations
    quant_routes,  # QUANT - ML Models Dashboard (Regime Classifier, Directional ML, Ensemble)
    math_optimizer_routes,  # Mathematical Optimization - HMM, Kalman, Thompson, Convex, HJB, MDP algorithms
    validation_routes,  # AutoValidation - ML model health monitoring, Thompson allocation, auto-retrain
    drift_routes,  # Drift Detection - Backtest vs Live performance comparison
    unified_metrics_routes,  # Unified Bot Metrics - Single source of truth for all bot stats
    bot_reports_routes,  # Bot Daily Reports - End-of-day analysis with Claude AI
    jubilee_routes,  # JUBILEE Box Spread - Synthetic Borrowing for IC Volume Scaling
    tastytrade_routes,  # Tastytrade API - VALOR futures bot integration
    valor_routes,  # VALOR - MES Futures Scalping Bot using GEX signals
    agape_routes,  # AGAPE - ETH Micro Futures (/MET) bot using crypto microstructure signals
    agape_spot_routes,  # AGAPE-SPOT - 24/7 Coinbase Spot ETH-USD trading
    agape_btc_routes,  # AGAPE-BTC - BTC Micro Futures (/MBT) bot using crypto microstructure signals
    agape_xrp_routes,  # AGAPE-XRP - XRP Futures (/XRP) bot using crypto microstructure signals
    agape_eth_perp_routes,  # AGAPE-ETH-PERP - ETH Perpetual Contract bot
    agape_btc_perp_routes,  # AGAPE-BTC-PERP - BTC Perpetual Contract bot
    agape_xrp_perp_routes,  # AGAPE-XRP-PERP - XRP Perpetual Contract bot
    agape_doge_perp_routes,  # AGAPE-DOGE-PERP - DOGE Perpetual Contract bot
    agape_shib_perp_routes,  # AGAPE-SHIB-PERP - SHIB Perpetual Contract bot
    omega_routes,  # OMEGA - Central Trading Decision Orchestrator (4-layer pipeline + gap implementations)
    bayesian_crypto_routes,  # Bayesian Crypto Performance Tracker - statistical edge detection for crypto strategies
)

# ============================================================================
# Import existing AlphaGEX logic with graceful fallbacks
# These imports are wrapped in try/except to prevent startup failures
# ============================================================================

# Core classes - critical for GEX data
TradingVolatilityAPI = None
MonteCarloEngine = None
BlackScholesPricer = None
try:
    from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
    print("✅ Backend: core_classes_and_engines loaded")
except ImportError as e:
    print(f"⚠️ Backend: core_classes_and_engines import failed: {e}")

# Intelligence and strategies
ClaudeIntelligence = None
MultiStrategyOptimizer = None
get_et_time = None
get_local_time = None
is_market_open = None
try:
    from core.intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open, MultiStrategyOptimizer
    print("✅ Backend: intelligence_and_strategies loaded")
except ImportError as e:
    print(f"⚠️ Backend: intelligence_and_strategies import failed: {e}")
    # Provide fallback functions so routes don't crash - ALL TIMES IN CENTRAL
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    def get_et_time():
        """Returns Central Time (legacy name for compatibility)"""
        return datetime.now(CENTRAL_TZ)
    def get_local_time(tz='America/Chicago'):
        return datetime.now(ZoneInfo(tz))
    def is_market_open():
        ct = datetime.now(CENTRAL_TZ)
        if ct.weekday() >= 5:
            return False
        market_open = ct.replace(hour=8, minute=30, second=0, microsecond=0)
        market_close = ct.replace(hour=15, minute=0, second=0, microsecond=0)
        return market_open <= ct < market_close

# Database configuration and initialization
STRATEGIES = {}
MM_STATES = {}
init_database = None
try:
    from db.config_and_database import STRATEGIES, init_database, MM_STATES, backfill_ai_intelligence_tables
    print("✅ Backend: config_and_database loaded")
except ImportError as e:
    print(f"⚠️ Backend: config_and_database import failed: {e}")

# Database adapter
get_connection = None
try:
    from database_adapter import get_connection
    print("✅ Backend: database_adapter loaded")
except ImportError as e:
    print(f"⚠️ Backend: database_adapter import failed: {e}")

# PostgreSQL - should always be available if psycopg2 is installed
import psycopg2
import psycopg2.extras

# Probability calculator
ProbabilityCalculator = None
try:
    from core.probability_calculator import ProbabilityCalculator
    print("✅ Backend: probability_calculator loaded")
except ImportError as e:
    print(f"⚠️ Backend: probability_calculator import failed: {e}")

# Notification manager
notification_manager = None
try:
    from monitoring.psychology_notifications import notification_manager
    print("✅ Backend: psychology_notifications loaded")
except ImportError as e:
    print(f"⚠️ Backend: psychology_notifications import failed: {e}")

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
UNIFIED_DATA_AVAILABLE = False
get_data_provider = None
get_quote = None
get_price = None
get_vix = None
try:
    from data.unified_data_provider import get_data_provider, get_quote, get_price, get_vix
    UNIFIED_DATA_AVAILABLE = True
    print("✅ Backend: Unified Data Provider (Tradier) integrated")
except ImportError as e:
    print(f"⚠️ Backend: Unified Data Provider not available: {e}")

# Initialize database schema on startup (if available)
if init_database:
    print("Initializing database schema...")
    try:
        init_database()
        print("✓ Database initialized")

        # Backfill AI Intelligence tables from historical data
        print("Backfilling AI Intelligence tables from historical data...")
        try:
            backfill_ai_intelligence_tables()
            print("✓ AI Intelligence tables backfilled")
        except Exception as e:
            print(f"⚠️ AI Intelligence backfill failed: {e}")

        # Initialize margin management tables
        try:
            from trading.margin.db_migration import create_margin_tables
            create_margin_tables()
            print("✓ Margin management tables initialized")
        except Exception as e:
            print(f"⚠️ Margin table initialization failed: {e}")

    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")
else:
    print("⚠️ Skipping database initialization - init_database not available")

# Create FastAPI app
app = FastAPI(
    title="AlphaGEX API",
    description="Professional Options Intelligence Platform - Backend API",
    version="2.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Custom CORS Middleware - Handles ALL CORS including wildcard origins
# This replaces the built-in CORSMiddleware which doesn't support wildcards
import re as regex_module  # PERFORMANCE FIX: Import once at module level

class CORSHeaderMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Parse allowed origins from environment, supporting wildcards
        origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
        self.allowed_origins = [o.strip() for o in origins_str.split(",") if o.strip()]
        # Check if we should allow all origins (for development)
        self.allow_all = "*" in self.allowed_origins or os.getenv("ENVIRONMENT") == "development"

        # PERFORMANCE FIX: Pre-compile wildcard patterns at startup (not per-request)
        self._compiled_patterns = []
        for allowed in self.allowed_origins:
            if "*" in allowed:
                # Convert https://*.vercel.app to regex pattern
                pattern = allowed.replace(".", r"\.").replace("*", ".*")
                self._compiled_patterns.append(regex_module.compile(f"^{pattern}$"))

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed, supporting wildcard patterns"""
        if not origin:
            return True  # Allow requests without Origin header
        if self.allow_all:
            return True
        # Check exact matches first (fast path)
        if origin in self.allowed_origins:
            return True
        # PERFORMANCE FIX: Use pre-compiled patterns (was compiling on every request)
        for pattern in self._compiled_patterns:
            if pattern.match(origin):
                return True
        return True  # Default to allowing for API accessibility

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = JSONResponse(content={"status": "ok"}, status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response

        # Process the request
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "*"

        return response

# Add custom CORS middleware - handles everything including wildcards
app.add_middleware(CORSHeaderMiddleware)

# Also add FastAPI's built-in CORS as backup for reliability
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules (modular API structure)
app.include_router(vix_routes.router)
app.include_router(spx_routes.router)
app.include_router(system_routes.router)
app.include_router(trader_routes.router)
app.include_router(backtest_routes.router)
app.include_router(database_routes.router)
app.include_router(gex_routes.router)
app.include_router(gamma_routes.router)
app.include_router(core_routes.router)
app.include_router(optimizer_routes.router)
app.include_router(ai_routes.router)
app.include_router(probability_routes.router)
app.include_router(notification_routes.router)
app.include_router(misc_routes.router)
app.include_router(alerts_routes.router)
app.include_router(setups_routes.router)
app.include_router(scanner_routes.router)
app.include_router(autonomous_routes.router)
app.include_router(psychology_routes.router)
app.include_router(ai_intelligence_routes.router)
app.include_router(wheel_routes.router)
app.include_router(export_routes.router)
app.include_router(ml_routes.router)
app.include_router(spx_backtest_routes.router)
app.include_router(jobs_routes.router)
app.include_router(regime_routes.router)
app.include_router(volatility_surface_routes.router)
app.include_router(zero_dte_backtest_routes.router)
app.include_router(fortress_routes.router)
app.include_router(faith_routes.router)
app.include_router(grace_routes.router)
app.include_router(solomon_routes.router)
app.include_router(gideon_routes.router)
app.include_router(anchor_routes.router)
app.include_router(samson_routes.router)
app.include_router(logs_routes.router)
app.include_router(scan_activity_routes.router)
app.include_router(discernment_routes.router)
app.include_router(daily_manna_routes.router)
app.include_router(watchtower_routes.router)
app.include_router(glory_routes.router)
app.include_router(data_transparency_routes.router)
app.include_router(docs_routes.router)
app.include_router(proverbs_routes.router)
app.include_router(events_routes.router)
app.include_router(prophet_routes.router)
app.include_router(prophet_routes.metrics_router)
app.include_router(quant_routes.router)
app.include_router(math_optimizer_routes.router)
app.include_router(validation_routes.router)
app.include_router(drift_routes.router)
app.include_router(unified_metrics_routes.router)
app.include_router(bot_reports_routes.router)
app.include_router(jubilee_routes.router)
app.include_router(tastytrade_routes.router)
app.include_router(valor_routes.router)
app.include_router(agape_routes.router)
app.include_router(agape_spot_routes.router)
app.include_router(agape_btc_routes.router)
app.include_router(agape_xrp_routes.router)
app.include_router(agape_eth_perp_routes.router)
app.include_router(agape_btc_perp_routes.router)
app.include_router(agape_xrp_perp_routes.router)
app.include_router(agape_doge_perp_routes.router)
app.include_router(agape_shib_perp_routes.router)
app.include_router(omega_routes.router)
app.include_router(bayesian_crypto_routes.router)
print("✅ Route modules loaded: vix, spx, system, trader, backtest, database, gex, gamma, core, optimizer, ai, probability, notifications, misc, alerts, setups, scanner, autonomous, psychology, ai-intelligence, wheel, export, ml, spx-backtest, jobs, regime, volatility-surface, fortress, daily-manna, jubilee, watchtower, docs, proverbs, events, prophet, math-optimizer, validation, drift, bot-reports, tastytrade, valor, agape, agape-spot, agape-btc, agape-xrp, agape-eth-perp, agape-btc-perp, agape-xrp-perp, agape-doge-perp, agape-shib-perp, omega, bayesian-crypto")

# Initialize existing AlphaGEX components (singleton pattern)
# Only instantiate if import succeeded
api_client = TradingVolatilityAPI() if TradingVolatilityAPI else None
claude_ai = ClaudeIntelligence() if ClaudeIntelligence else None
monte_carlo = MonteCarloEngine() if MonteCarloEngine else None
pricer = BlackScholesPricer() if BlackScholesPricer else None
strategy_optimizer = MultiStrategyOptimizer() if MultiStrategyOptimizer else None

# Initialize probability calculator (NEW - Phase 2 Self-Learning)
probability_calc = ProbabilityCalculator() if ProbabilityCalculator else None

# RSI Data Cache - Prevent Polygon.io rate limit (5 calls/min on free tier)
# Cache RSI data for 5 minutes to avoid repeated API calls
import threading
_rsi_cache = {}
_rsi_cache_ttl = 300  # 5 minutes in seconds
_rsi_cache_max_size = 100  # Maximum number of cached symbols to prevent unbounded growth
_rsi_cache_lock = threading.Lock()  # Thread safety for concurrent requests

def _cleanup_rsi_cache():
    """Remove expired entries and enforce max size limit. Must be called with lock held."""
    now = datetime.now()
    # Remove expired entries
    expired_keys = [
        key for key, entry in _rsi_cache.items()
        if (now - entry['timestamp']).total_seconds() > _rsi_cache_ttl
    ]
    for key in expired_keys:
        del _rsi_cache[key]

    # If still over max size, remove oldest entries
    if len(_rsi_cache) > _rsi_cache_max_size:
        # Sort by timestamp, oldest first
        sorted_entries = sorted(_rsi_cache.items(), key=lambda x: x[1]['timestamp'])
        # Remove oldest entries to get back under limit
        for key, _ in sorted_entries[:len(_rsi_cache) - _rsi_cache_max_size]:
            del _rsi_cache[key]

def _get_cached_rsi(cache_key: str) -> dict | None:
    """Thread-safe cache read"""
    with _rsi_cache_lock:
        if cache_key in _rsi_cache:
            cached_entry = _rsi_cache[cache_key]
            cache_age = (datetime.now() - cached_entry['timestamp']).total_seconds()
            if cache_age < _rsi_cache_ttl:
                return cached_entry['data'].copy()
    return None

def _set_cached_rsi(cache_key: str, data: dict):
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

def validate_symbol(symbol: str) -> tuple[bool, str]:
    """
    Validate stock symbol parameter to prevent injection attacks and API errors.

    Returns:
        (is_valid, cleaned_symbol or error_message)
    """
    if not symbol:
        return False, "Symbol cannot be empty"

    # Clean and normalize
    symbol = symbol.strip().upper()

    # Check length (stock symbols are typically 1-5 characters)
    if len(symbol) > 5:
        return False, f"Symbol too long: {len(symbol)} characters (max 5)"

    # Check for valid characters (alphanumeric only)
    if not symbol.isalnum():
        return False, "Symbol must contain only alphanumeric characters"

    # Block obvious injection attempts
    blocked_patterns = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', '--', ';', '/*']
    for pattern in blocked_patterns:
        if pattern in symbol:
            return False, f"Invalid symbol: contains blocked pattern"

    return True, symbol


def get_cached_price_data(symbol: str, current_price: float = 0) -> dict:
    """
    Get price data for multi-timeframe analysis.

    Returns dict with timeframe keys ('1d', '1h', etc.) containing OHLCV data.
    Used by psychology trap detector for volume and price analysis.
    """
    price_data = {
        '5m': [],
        '15m': [],
        '1h': [],
        '4h': [],
        '1d': []
    }

    # Try to get historical data from Polygon
    polygon_key = os.getenv('POLYGON_API_KEY')
    if not polygon_key:
        # Return basic structure with current price
        return price_data

    try:
        # Fetch daily bars for volume analysis (last 30 days)
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "asc", "limit": 50}

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                for bar in data['results']:
                    price_data['1d'].append({
                        'timestamp': bar['t'],
                        'open': bar['o'],
                        'high': bar['h'],
                        'low': bar['l'],
                        'close': bar['c'],
                        'volume': bar.get('v', 0)
                    })
    except Exception as e:
        print(f"Warning: Could not fetch price data from Polygon: {e}")

    return price_data

def fetch_vix_with_metadata(polygon_key: str = None) -> dict:
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
    if UNIFIED_DATA_AVAILABLE:
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
        # Get last trading day's VIX close
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

# ============================================================================
# WebSocket - Real-Time Market Data
# ============================================================================

class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except (RuntimeError, ConnectionError, Exception) as e:
                # Connection likely closed, will be cleaned up on next disconnect
                pass

manager = ConnectionManager()

# Track subscriptions per connection
_connection_subscriptions: dict = {}

@app.websocket("/ws/market-data")
async def websocket_market_data(websocket: WebSocket, symbol: str = "SPY"):
    """
    WebSocket endpoint for real-time market data updates

    Query params:
        symbol: Stock symbol to monitor (default: SPY)

    Sends updates every 30 seconds during market hours
    """
    await manager.connect(websocket)
    symbol = symbol.upper()

    try:
        import asyncio

        while True:
            # Check if market is open
            if is_market_open():
                # Fetch latest GEX data
                gex_data = api_client.get_net_gamma(symbol)

                # Send update to client
                await websocket.send_json({
                    "type": "market_update",
                    "symbol": symbol,
                    "data": gex_data,
                    "timestamp": datetime.now().isoformat()
                })

                # Wait 30 seconds
                await asyncio.sleep(30)
            else:
                # Market closed - send status and wait longer
                await websocket.send_json({
                    "type": "market_closed",
                    "message": "Market is currently closed",
                    "timestamp": datetime.now().isoformat()
                })

                # Wait 5 minutes when market is closed
                await asyncio.sleep(300)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        # Only log non-empty errors (empty usually means client disconnected normally)
        if str(e):
            print(f"WebSocket error: {e}")

@app.websocket("/ws/trader")
async def websocket_trader(websocket: WebSocket):
    """
    WebSocket endpoint for real-time trader updates

    Streams:
    - Trader status updates
    - Position updates with P&L
    - Trade executions
    - Risk alerts

    Update frequency: Every 10 seconds during market hours
    """
    await manager.connect(websocket)
    connection_id = id(websocket)
    _connection_subscriptions[connection_id] = {'symbols': ['SPY', 'SPX']}

    try:
        import asyncio

        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "connected",
            "message": "Trader WebSocket connected",
            "timestamp": datetime.now().isoformat()
        })

        while True:
            try:
                # Check for incoming messages (subscriptions, commands)
                # Use wait_for with timeout to allow periodic updates
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.1
                    )
                    # Handle subscription changes
                    if message.get('type') == 'subscribe':
                        symbols = message.get('symbols', ['SPY'])
                        # Validate symbols: only alphanumeric, max 5 chars each
                        validated_symbols = []
                        for s in symbols[:10]:  # Max 10 symbols
                            if isinstance(s, str) and s.isalnum() and len(s) <= 5:
                                validated_symbols.append(s.upper())
                        if validated_symbols:
                            _connection_subscriptions[connection_id]['symbols'] = validated_symbols
                        await websocket.send_json({
                            "type": "subscribed",
                            "symbols": _connection_subscriptions[connection_id]['symbols'],
                            "timestamp": datetime.now().isoformat()
                        })
                except asyncio.TimeoutError:
                    pass  # No message, continue with updates

                # Send comprehensive update
                update_data = await _get_trader_update_data()
                await websocket.send_json(update_data)

                # Wait 10 seconds before next update
                await asyncio.sleep(10)

            except Exception as e:
                # Send error but continue
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)[:200],  # Truncate error message
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception:
                    pass  # If sending error fails, just continue
                await asyncio.sleep(10)

    except WebSocketDisconnect:
        pass  # Normal disconnect, cleanup in finally
    except Exception as e:
        # Only log non-empty errors (empty usually means client disconnected normally)
        if str(e):
            print(f"Trader WebSocket error: {e}")
    finally:
        # Guaranteed cleanup - prevents memory leak
        if connection_id in _connection_subscriptions:
            del _connection_subscriptions[connection_id]
        try:
            manager.disconnect(websocket)
        except Exception:
            pass  # Ignore disconnect errors - connection already closed

async def _get_trader_update_data() -> dict:
    """
    Gather all trader data for WebSocket update.

    Returns comprehensive update including:
    - Trader status
    - Open positions with real-time P&L
    - Recent trades
    - Risk metrics
    - Market data
    """
    update = {
        "type": "trader_update",
        "timestamp": datetime.now().isoformat(),
        "market_open": is_market_open()
    }

    try:
        conn = get_connection()
        import pandas as pd

        # Get trader status
        cursor = conn.cursor()
        cursor.execute("""
            SELECT key, value FROM autonomous_config
            WHERE key IN ('capital', 'auto_execute', 'last_trade_date', 'mode', 'signal_only')
        """)
        config = {row[0]: row[1] for row in cursor.fetchall()}
        update['config'] = config

        # Get live status
        cursor.execute("""
            SELECT status, current_action, market_analysis, last_decision, timestamp, next_check_time
            FROM autonomous_live_status
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        status_row = cursor.fetchone()
        if status_row:
            update['status'] = {
                'status': status_row[0],
                'current_action': status_row[1],
                'market_analysis': status_row[2],
                'last_decision': status_row[3],
                'last_updated': status_row[4] if status_row[4] else None,
                'next_check_time': status_row[5] if status_row[5] else None
            }

        # Get open positions with current P&L (including Greeks and GEX context)
        positions_df = pd.read_sql_query("""
            SELECT id, symbol, strategy, action, strike, option_type,
                   expiration_date, contracts, entry_price, entry_spot_price,
                   current_price, current_spot_price, unrealized_pnl,
                   unrealized_pnl_pct, confidence, entry_date, entry_time,
                   entry_iv, entry_delta, current_iv, current_delta,
                   entry_bid, entry_ask, gex_regime, entry_net_gex,
                   entry_flip_point, trade_reasoning, contract_symbol
            FROM autonomous_open_positions
            ORDER BY entry_date DESC, entry_time DESC
        """, conn)

        update['positions'] = positions_df.to_dict(orient='records') if not positions_df.empty else []

        # Get recent closed trades (last 10)
        trades_df = pd.read_sql_query("""
            SELECT id, symbol, strategy, action, strike, option_type,
                   entry_date, exit_date, entry_price, exit_price,
                   realized_pnl, realized_pnl_pct, exit_reason
            FROM autonomous_closed_trades
            ORDER BY COALESCE(exit_date, entry_date) DESC, COALESCE(exit_time, entry_time) DESC
            LIMIT 10
        """, conn)

        update['recent_trades'] = trades_df.to_dict(orient='records') if not trades_df.empty else []

        # Calculate performance metrics
        cursor.execute("SELECT COALESCE(SUM(realized_pnl), 0) FROM autonomous_closed_trades")
        total_realized = float(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COALESCE(SUM(unrealized_pnl), 0) FROM autonomous_open_positions")
        total_unrealized = float(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE realized_pnl > 0")
        winners = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE realized_pnl <= 0")
        losers = cursor.fetchone()[0] or 0

        total_trades = winners + losers
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

        starting_capital = float(config.get('capital', 1000000))
        current_equity = starting_capital + total_realized + total_unrealized

        update['performance'] = {
            'starting_capital': starting_capital,
            'current_equity': current_equity,
            'total_realized_pnl': total_realized,
            'total_unrealized_pnl': total_unrealized,
            'net_pnl': total_realized + total_unrealized,
            'return_pct': ((total_realized + total_unrealized) / starting_capital * 100) if starting_capital > 0 else 0,
            'total_trades': total_trades,
            'winning_trades': winners,
            'losing_trades': losers,
            'win_rate': win_rate,
            'open_positions': len(positions_df)
        }

        # Risk alerts
        alerts = []
        drawdown_pct = ((starting_capital - current_equity) / starting_capital * 100) if starting_capital > 0 and current_equity < starting_capital else 0
        if drawdown_pct > 10:
            alerts.append({
                'level': 'critical',
                'message': f'Drawdown alert: {drawdown_pct:.1f}% from starting capital'
            })
        elif drawdown_pct > 5:
            alerts.append({
                'level': 'warning',
                'message': f'Drawdown warning: {drawdown_pct:.1f}% from starting capital'
            })

        if len(positions_df) > 5:
            alerts.append({
                'level': 'info',
                'message': f'High position count: {len(positions_df)} open positions'
            })

        update['alerts'] = alerts

        # Market data snapshot
        try:
            gex_data = api_client.get_net_gamma('SPY')
            if gex_data and not gex_data.get('error'):
                update['market'] = {
                    'symbol': 'SPY',
                    'spot_price': gex_data.get('spot_price', 0),
                    'net_gex': gex_data.get('net_gex', 0),
                    'flip_point': gex_data.get('flip_point', 0),
                    'call_wall': gex_data.get('call_wall', 0),
                    'put_wall': gex_data.get('put_wall', 0)
                }
        except (KeyError, TypeError, AttributeError, Exception) as e:
            update['market'] = None

        conn.close()

    except Exception as e:
        update['error'] = str(e)

    return update

@app.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    """
    WebSocket endpoint for position-only updates (lightweight)

    Streams position P&L updates every 5 seconds
    """
    await manager.connect(websocket)

    try:
        import asyncio

        while True:
            try:
                conn = get_connection()
                import pandas as pd

                positions_df = pd.read_sql_query("""
                    SELECT id, symbol, strategy, strike, option_type,
                           expiration_date, contracts, entry_price,
                           current_price, unrealized_pnl, unrealized_pnl_pct
                    FROM autonomous_open_positions
                    ORDER BY unrealized_pnl DESC
                """, conn)
                conn.close()

                await websocket.send_json({
                    "type": "positions_update",
                    "positions": positions_df.to_dict(orient='records') if not positions_df.empty else [],
                    "count": len(positions_df),
                    "total_unrealized": float(positions_df['unrealized_pnl'].sum()) if not positions_df.empty else 0,
                    "timestamp": datetime.now().isoformat()
                })

                await asyncio.sleep(5)

            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        # Only log non-empty errors (empty usually means client disconnected normally)
        if str(e):
            print(f"Positions WebSocket error: {e}")


# ============================================================================
# LIVE CHART WebSocket - Real-Time Price Streaming for Intraday Charts
# ============================================================================

class LiveChartManager:
    """Manage live chart WebSocket connections with per-symbol tracking"""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}  # symbol -> connections

    async def connect(self, websocket: WebSocket, symbol: str):
        await websocket.accept()
        if symbol not in self.connections:
            self.connections[symbol] = []
        self.connections[symbol].append(websocket)

    def disconnect(self, websocket: WebSocket, symbol: str):
        if symbol in self.connections:
            try:
                self.connections[symbol].remove(websocket)
            except ValueError:
                pass
            if not self.connections[symbol]:
                del self.connections[symbol]

    async def broadcast(self, symbol: str, message: dict):
        if symbol not in self.connections:
            return
        dead = []
        for ws in self.connections[symbol]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, symbol)

live_chart_manager = LiveChartManager()

# ── Shared httpx client (Section 5: avoid creating a new client per call) ──
_httpx_client = None  # type: ignore


async def _get_httpx_client():
    """Get or create a shared async HTTP client with connection pooling."""
    global _httpx_client
    import httpx as _httpx
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = _httpx.AsyncClient(
            timeout=5.0,
            limits=_httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _httpx_client

# ── GEX level cache (Section 3: decouple DB queries from WS loop) ──
_gex_level_cache: dict = {}       # symbol -> levels dict
_gex_level_cache_times: dict = {} # symbol -> unix timestamp
_GEX_CACHE_TTL = 30               # seconds


def _get_cached_gex_levels(symbol: str):
    import time as _time
    if symbol in _gex_level_cache and symbol in _gex_level_cache_times:
        if _time.time() - _gex_level_cache_times[symbol] < _GEX_CACHE_TTL:
            return _gex_level_cache[symbol]
    return None


def _set_cached_gex_levels(symbol: str, levels: dict):
    import time as _time
    _gex_level_cache[symbol] = levels
    _gex_level_cache_times[symbol] = _time.time()


class _LiveCandleTracker:
    """Track the forming candle from quote ticks"""

    def __init__(self, interval_minutes: int = 5):
        self.interval = interval_minutes
        self.current_candle: dict | None = None
        self.candle_start: datetime | None = None

    def _candle_time(self, dt: datetime) -> datetime:
        minute = (dt.minute // self.interval) * self.interval
        return dt.replace(minute=minute, second=0, microsecond=0)

    def update(self, price: float, volume: int = 0, ts: datetime | None = None):
        """Feed a price tick. Returns the completed candle if a new period started, else None."""
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = ts or datetime.now(CENTRAL_TZ)
        ct = self._candle_time(now)

        if self.candle_start != ct:
            completed = self.current_candle
            self.current_candle = {
                "time": ct.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
            }
            self.candle_start = ct
            return completed

        if self.current_candle:
            self.current_candle["high"] = max(self.current_candle["high"], price)
            self.current_candle["low"] = min(self.current_candle["low"], price)
            self.current_candle["close"] = price
            self.current_candle["volume"] += volume
        return None


# Per-symbol candle trackers
_candle_trackers: dict[str, _LiveCandleTracker] = {}


@app.websocket("/ws/live-chart")
async def websocket_live_chart(websocket: WebSocket, symbol: str = "SPY"):
    """
    Real-time chart streaming for intraday candlestick + GEX overlays.

    On connect: session data for instant render.
    Market hours: ~1.5s fixed-interval tick loop (quote + forming candle),
      completed candles verified against Tradier timesales (Section 1),
      GEX levels refreshed by background task every ~30s (Section 3).
    Market closed: keepalive every 60s.
    """
    import asyncio

    symbol = symbol.upper()
    await live_chart_manager.connect(websocket, symbol)

    if symbol not in _candle_trackers:
        _candle_trackers[symbol] = _LiveCandleTracker(interval_minutes=5)
    tracker = _candle_trackers[symbol]

    # Section 3: background GEX refresh task, scoped to this connection
    gex_refresh_task = None

    try:
        # --- Send initial session data for instant chart render ---
        session_payload = await _get_session_data(symbol)
        await websocket.send_json({
            "type": "session_data",
            "symbol": symbol,
            "market_open": is_market_open() if is_market_open else False,
            **session_payload,
        })

        # Section 3: background coroutine refreshes GEX cache every 30s
        async def _gex_refresh_loop():
            while True:
                try:
                    levels = await _fetch_gex_levels_uncached(symbol)
                    if levels:
                        _set_cached_gex_levels(symbol, levels)
                except Exception as exc:
                    print(f"GEX refresh error: {exc}")
                await asyncio.sleep(30)

        gex_refresh_task = asyncio.create_task(_gex_refresh_loop())

        # Also seed cache immediately so first reads don't miss
        try:
            seed = await _fetch_gex_levels_uncached(symbol)
            if seed:
                _set_cached_gex_levels(symbol, seed)
        except Exception:
            pass

        while True:
            market_is_open = is_market_open() if is_market_open else False

            if market_is_open:
                # Section 7: record start for fixed-interval sleep
                loop_start = asyncio.get_event_loop().time()

                # --- Fetch latest quote (shared client) ---
                quote_data = await _fetch_tradier_quote_async(symbol)
                if quote_data and quote_data.get("price"):
                    price = quote_data["price"]
                    volume = quote_data.get("volume", 0)

                    from zoneinfo import ZoneInfo
                    CENTRAL_TZ = ZoneInfo("America/Chicago")
                    now = datetime.now(CENTRAL_TZ)

                    completed = tracker.update(price, volume, now)

                    # Send forming candle update
                    await websocket.send_json({
                        "type": "candle_update",
                        "symbol": symbol,
                        "candle": tracker.current_candle,
                        "price": price,
                        "bid": quote_data.get("bid"),
                        "ask": quote_data.get("ask"),
                        "timestamp": now.isoformat(),
                    })

                    # Section 1: verify completed candle against Tradier before sending
                    if completed:
                        verified = await _verify_completed_candle(symbol, completed)
                        await websocket.send_json({
                            "type": "completed_candle",
                            "symbol": symbol,
                            "candle": verified,
                        })

                # Section 3: read GEX levels from cache (non-blocking)
                cached_levels = _get_cached_gex_levels(symbol)
                if cached_levels:
                    await websocket.send_json({
                        "type": "gex_levels",
                        "symbol": symbol,
                        **cached_levels,
                    })

                # Section 7: fixed-interval sleep (subtract elapsed time)
                elapsed = asyncio.get_event_loop().time() - loop_start
                await asyncio.sleep(max(0.1, 1.5 - elapsed))
            else:
                # Market closed - keepalive
                await websocket.send_json({
                    "type": "keepalive",
                    "market_open": False,
                    "timestamp": datetime.now().isoformat(),
                })
                await asyncio.sleep(60)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        if str(e):
            print(f"Live chart WebSocket error: {e}")
    finally:
        # Section 5: cancel background task on disconnect
        if gex_refresh_task and not gex_refresh_task.done():
            gex_refresh_task.cancel()
            try:
                await gex_refresh_task
            except asyncio.CancelledError:
                pass
        live_chart_manager.disconnect(websocket, symbol)


async def _fetch_tradier_quote_async(symbol: str) -> dict | None:
    """Fetch latest quote from Tradier using shared async HTTP client (Section 5)."""
    try:
        from unified_config import APIConfig
        api_key = APIConfig.TRADIER_API_KEY or APIConfig.TRADIER_SANDBOX_API_KEY
        if not api_key:
            return None

        is_sandbox = not APIConfig.TRADIER_API_KEY
        base_url = "https://sandbox.tradier.com" if is_sandbox else "https://api.tradier.com"

        client = await _get_httpx_client()
        resp = await client.get(
            f"{base_url}/v1/markets/quotes",
            params={"symbols": symbol, "greeks": "false"},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        quotes = data.get("quotes", {})
        quote = quotes.get("quote", {})
        if isinstance(quote, list):
            quote = quote[0] if quote else {}

        return {
            "price": float(quote.get("last", 0)),
            "bid": float(quote.get("bid", 0)),
            "ask": float(quote.get("ask", 0)),
            "volume": int(quote.get("volume", 0)),
            "change": float(quote.get("change", 0)),
            "change_pct": float(quote.get("change_percentage", 0)),
        }
    except Exception as e:
        print(f"Tradier quote fetch error: {e}")
        return None


async def _verify_completed_candle(symbol: str, tracker_candle: dict) -> dict:
    """
    Section 1: On candle close, fetch the official bar from Tradier timesales
    and overwrite the tracker's OHLC with authoritative values. Falls back to
    tracker data if the fetch fails.
    """
    try:
        from unified_config import APIConfig
        api_key = APIConfig.TRADIER_API_KEY or APIConfig.TRADIER_SANDBOX_API_KEY
        if not api_key:
            return tracker_candle

        is_sandbox = not APIConfig.TRADIER_API_KEY
        base_url = "https://sandbox.tradier.com" if is_sandbox else "https://api.tradier.com"

        candle_time = datetime.fromisoformat(tracker_candle["time"])
        start_str = candle_time.strftime('%Y-%m-%d %H:%M')
        end_time = candle_time + timedelta(minutes=5)
        end_str = end_time.strftime('%Y-%m-%d %H:%M')

        client = await _get_httpx_client()
        resp = await client.get(
            f"{base_url}/v1/markets/timesales",
            params={
                "symbol": symbol,
                "interval": "5min",
                "start": start_str,
                "end": end_str,
                "session_filter": "open",
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        if resp.status_code != 200:
            return tracker_candle

        series = resp.json().get("series", {})
        if not series or series == "null":
            return tracker_candle

        raw = series.get("data", [])
        if isinstance(raw, dict):
            raw = [raw]
        if not raw:
            return tracker_candle

        bar = raw[0]
        return {
            "time": tracker_candle["time"],
            "open": round(float(bar.get("open", tracker_candle["open"])), 2),
            "high": round(float(bar.get("high", tracker_candle["high"])), 2),
            "low": round(float(bar.get("low", tracker_candle["low"])), 2),
            "close": round(float(bar.get("close", tracker_candle["close"])), 2),
            "volume": int(bar.get("volume", tracker_candle["volume"])),
        }
    except Exception as e:
        print(f"Candle verification error (falling back to tracker): {e}")
        return tracker_candle


async def _fetch_gex_levels_uncached(symbol: str) -> dict | None:
    """
    Section 3: Fetch GEX levels from DB. Called by background task, NOT inline
    with the WS loop. Uses DB spot_price for ±1SD (avoids extra Tradier call).
    """
    try:
        conn = get_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("""
            SELECT flip_point, call_wall, put_wall, expected_move, vix,
                   total_net_gamma, gamma_regime, spot_price
            FROM watchtower_snapshots
            WHERE symbol = %s
            ORDER BY snapshot_time DESC
            LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return None

        flip, cw, pw, em, vix_val, net_gamma, regime, spot = row
        upper_1sd = None
        lower_1sd = None
        if spot and em:
            upper_1sd = round(float(spot) * (1 + float(em)), 2)
            lower_1sd = round(float(spot) * (1 - float(em)), 2)

        return {
            "flip_point": round(float(flip), 2) if flip else None,
            "call_wall": round(float(cw), 2) if cw else None,
            "put_wall": round(float(pw), 2) if pw else None,
            "expected_move": round(float(em), 4) if em else None,
            "upper_1sd": upper_1sd,
            "lower_1sd": lower_1sd,
            "vix": round(float(vix_val), 2) if vix_val else None,
            "net_gamma": round(float(net_gamma), 2) if net_gamma else None,
            "gamma_regime": regime,
        }
    except Exception as e:
        print(f"GEX levels fetch error: {e}")
        return None


async def _get_session_data(symbol: str) -> dict:
    """
    Get session data for initial chart render.
    Returns bars + GEX levels for the last trading session.
    """
    bars = []
    gex_levels = {}
    gex_ticks = []
    session_date = None

    try:
        conn = get_connection()
        if not conn:
            return {"bars": bars, "gex_levels": gex_levels, "gex_ticks": gex_ticks, "session_date": session_date}

        cursor = conn.cursor()

        # Find the most recent day with snapshots
        cursor.execute("""
            SELECT DISTINCT snapshot_time::date AS d
            FROM watchtower_snapshots
            WHERE symbol = %s
            ORDER BY d DESC
            LIMIT 5
        """, (symbol,))
        dates = [r[0] for r in cursor.fetchall()]

        if dates:
            session_date = dates[0].isoformat()

            # Get GEX ticks for that day
            cursor.execute("""
                SELECT
                    date_trunc('hour', snapshot_time) +
                        (floor(extract(minute FROM snapshot_time) / 5) * 5 || ' minutes')::interval
                        AS tick_time,
                    AVG(spot_price) AS spot_price,
                    AVG(total_net_gamma) AS total_net_gamma,
                    AVG(vix) AS vix,
                    AVG(expected_move) AS expected_move,
                    MODE() WITHIN GROUP (ORDER BY gamma_regime) AS gamma_regime,
                    AVG(flip_point) AS flip_point,
                    AVG(call_wall) AS call_wall,
                    AVG(put_wall) AS put_wall
                FROM watchtower_snapshots
                WHERE symbol = %s AND snapshot_time::date = %s
                ORDER BY tick_time ASC
            """, (symbol, dates[0]))

            for row in cursor.fetchall():
                tick_time, spot, ng, vix_val, em, regime, fp, cw, pw = row
                gex_ticks.append({
                    "time": tick_time.isoformat() if tick_time else None,
                    "spot_price": round(float(spot), 2) if spot else None,
                    "net_gamma": round(float(ng), 2) if ng else None,
                    "vix": round(float(vix_val), 2) if vix_val else None,
                    "expected_move": round(float(em), 4) if em else None,
                    "gamma_regime": regime,
                    "flip_point": round(float(fp), 2) if fp else None,
                    "call_wall": round(float(cw), 2) if cw else None,
                    "put_wall": round(float(pw), 2) if pw else None,
                })

            # Latest GEX levels
            cursor.execute("""
                SELECT flip_point, call_wall, put_wall, expected_move, vix,
                       total_net_gamma, gamma_regime, spot_price
                FROM watchtower_snapshots
                WHERE symbol = %s AND snapshot_time::date = %s
                ORDER BY snapshot_time DESC
                LIMIT 1
            """, (symbol, dates[0]))
            level_row = cursor.fetchone()
            if level_row:
                fp, cw, pw, em, vix_val, ng, regime, spot = level_row
                upper_1sd = None
                lower_1sd = None
                if spot and em:
                    upper_1sd = round(float(spot) * (1 + float(em)), 2)
                    lower_1sd = round(float(spot) * (1 - float(em)), 2)
                gex_levels = {
                    "flip_point": round(float(fp), 2) if fp else None,
                    "call_wall": round(float(cw), 2) if cw else None,
                    "put_wall": round(float(pw), 2) if pw else None,
                    "expected_move": round(float(em), 4) if em else None,
                    "upper_1sd": upper_1sd,
                    "lower_1sd": lower_1sd,
                    "vix": round(float(vix_val), 2) if vix_val else None,
                    "net_gamma": round(float(ng), 2) if ng else None,
                    "gamma_regime": regime,
                }

        # Fetch OHLCV bars from Tradier for the session date
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            from unified_config import APIConfig
            api_key = APIConfig.TRADIER_API_KEY or APIConfig.TRADIER_SANDBOX_API_KEY
            if api_key and session_date:
                is_sandbox = not APIConfig.TRADIER_API_KEY
                base_url = "https://sandbox.tradier.com" if is_sandbox else "https://api.tradier.com"

                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{base_url}/v1/markets/timesales",
                        params={
                            "symbol": symbol,
                            "interval": "5min",
                            "start": f"{session_date} 08:30",
                            "end": f"{session_date} 15:15",
                            "session_filter": "open",
                        },
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Accept": "application/json",
                        },
                    )
                    if resp.status_code == 200:
                        series = resp.json().get("series", {})
                        if series and series != "null":
                            raw = series.get("data", [])
                            if isinstance(raw, dict):
                                raw = [raw]
                            for bar in raw:
                                bars.append({
                                    "time": bar.get("time", ""),
                                    "open": round(float(bar.get("open", 0)), 2),
                                    "high": round(float(bar.get("high", 0)), 2),
                                    "low": round(float(bar.get("low", 0)), 2),
                                    "close": round(float(bar.get("close", 0)), 2),
                                    "volume": int(bar.get("volume", 0)),
                                })
        except Exception as e:
            print(f"Session bars fetch error: {e}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Session data fetch error: {e}")

    return {
        "bars": bars,
        "gex_levels": gex_levels,
        "gex_ticks": gex_ticks,
        "session_date": session_date,
        "available_dates": [d.isoformat() for d in dates] if 'dates' in dir() else [],
    }


# ============================================================================
# CHRONICLES WebSocket - Real-Time Backtest Progress and GEX Updates
# ============================================================================

class ChroniclesConnectionManager:
    """Manage CHRONICLES WebSocket connections for backtest progress and GEX data"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}  # job_id -> connections
        self.gex_subscribers: list[WebSocket] = []

    async def connect(self, websocket: WebSocket, job_id: str = None):
        await websocket.accept()
        if job_id:
            if job_id not in self.active_connections:
                self.active_connections[job_id] = []
            self.active_connections[job_id].append(websocket)
        else:
            self.gex_subscribers.append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str = None):
        if job_id and job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
        if websocket in self.gex_subscribers:
            self.gex_subscribers.remove(websocket)

    async def broadcast_job_update(self, job_id: str, data: dict):
        """Send job update to all subscribers of a specific job"""
        if job_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(data)
                except Exception:
                    dead_connections.append(connection)
            # Clean up dead connections
            for conn in dead_connections:
                self.active_connections[job_id].remove(conn)

    async def broadcast_gex_update(self, data: dict):
        """Send GEX update to all GEX subscribers"""
        dead_connections = []
        for connection in self.gex_subscribers:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)
        # Clean up dead connections
        for conn in dead_connections:
            self.gex_subscribers.remove(conn)


chronicles_manager = ChroniclesConnectionManager()


@app.websocket("/ws/chronicles/job/{job_id}")
async def websocket_chronicles_job(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time CHRONICLES backtest progress updates.

    Clients subscribe to a specific job_id to receive progress updates.
    Much faster than SSE or polling for high-frequency updates.
    """
    await chronicles_manager.connect(websocket, job_id)

    try:
        # Import job store
        try:
            from backend.services.chronicles_infrastructure import job_store
        except ImportError:
            job_store = None

        while True:
            # Wait for client messages or send updates
            try:
                # Check for ping/pong or disconnect
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if message == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass

            # Get job status and send update
            if job_store:
                job = job_store.get(job_id)
                if job:
                    await websocket.send_json({
                        "type": "job_update",
                        "job_id": job_id,
                        "status": job.status,
                        "progress": job.progress,
                        "progress_message": job.progress_message,
                        "timestamp": datetime.now().isoformat()
                    })

                    if job.status in ("completed", "failed"):
                        # Send final result and close
                        await websocket.send_json({
                            "type": "job_complete",
                            "job_id": job_id,
                            "status": job.status,
                            "result": job.result if job.status == "completed" else None,
                            "error": job.error if job.status == "failed" else None
                        })
                        break
            else:
                # Fallback: check in-memory jobs from routes
                from backend.api.routes import zero_dte_backtest_routes
                if hasattr(zero_dte_backtest_routes, '_jobs') and job_id in zero_dte_backtest_routes._jobs:
                    job_data = zero_dte_backtest_routes._jobs[job_id]
                    await websocket.send_json({
                        "type": "job_update",
                        "job_id": job_id,
                        "status": job_data.get("status"),
                        "progress": job_data.get("progress", 0),
                        "progress_message": job_data.get("progress_message", ""),
                        "timestamp": datetime.now().isoformat()
                    })

                    if job_data.get("status") in ("completed", "failed"):
                        await websocket.send_json({
                            "type": "job_complete",
                            "job_id": job_id,
                            "status": job_data.get("status"),
                            "result": job_data.get("result") if job_data.get("status") == "completed" else None,
                            "error": job_data.get("error") if job_data.get("status") == "failed" else None
                        })
                        break

            await asyncio.sleep(0.5)  # Update frequency

    except WebSocketDisconnect:
        chronicles_manager.disconnect(websocket, job_id)
    except Exception as e:
        chronicles_manager.disconnect(websocket, job_id)
        if str(e):
            print(f"CHRONICLES WebSocket error: {e}")


@app.websocket("/ws/chronicles/gex")
async def websocket_chronicles_gex(websocket: WebSocket):
    """
    WebSocket endpoint for real-time GEX data updates.

    Clients receive live GEX calculations as they're computed.
    Useful for the CHRONICLES dashboard to show current market gamma exposure.
    """
    await chronicles_manager.connect(websocket, None)

    try:
        while True:
            # Wait for client messages
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if message == "ping":
                    await websocket.send_text("pong")
                elif message == "get_gex":
                    # Fetch and send current GEX data
                    try:
                        from quant.chronicles_gex_calculator import ChroniclesGEXCalculator
                        calculator = ChroniclesGEXCalculator()
                        gex_data = calculator.calculate_gex_for_date(datetime.now().strftime('%Y-%m-%d'))
                        if gex_data:
                            await websocket.send_json({
                                "type": "gex_data",
                                "data": {
                                    "net_gex": gex_data.net_gex,
                                    "call_wall": gex_data.call_wall,
                                    "put_wall": gex_data.put_wall,
                                    "flip_point": gex_data.flip_point,
                                    "regime": gex_data.regime,
                                    "normalized": gex_data.normalized_gex,
                                },
                                "timestamp": datetime.now().isoformat()
                            })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Failed to fetch GEX: {str(e)}"
                        })
            except asyncio.TimeoutError:
                # Send heartbeat in Central Time
                await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(CENTRAL_TZ).isoformat()})

    except WebSocketDisconnect:
        chronicles_manager.disconnect(websocket, None)
    except Exception as e:
        chronicles_manager.disconnect(websocket, None)
        if str(e):
            print(f"CHRONICLES GEX WebSocket error: {e}")


@app.get("/api/chronicles/infrastructure")
async def get_chronicles_infrastructure_status():
    """Get status of CHRONICLES infrastructure components"""
    try:
        from backend.services.chronicles_infrastructure import get_infrastructure_status
        return {
            "success": True,
            "infrastructure": get_infrastructure_status(),
            "websocket_connections": {
                "job_subscriptions": {k: len(v) for k, v in chronicles_manager.active_connections.items()},
                "gex_subscribers": len(chronicles_manager.gex_subscribers)
            }
        }
    except ImportError:
        return {
            "success": True,
            "infrastructure": {
                "job_store": {"type": "memory", "note": "chronicles_infrastructure not loaded"},
                "connection_pool": {"available": False},
                "orat_cache": {"hits": 0, "misses": 0},
            },
            "websocket_connections": {
                "job_subscriptions": {k: len(v) for k, v in chronicles_manager.active_connections.items()},
                "gex_subscribers": len(chronicles_manager.gex_subscribers)
            }
        }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    response = JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "Not found",
            "detail": str(exc.detail) if hasattr(exc, 'detail') else "Resource not found"
        }
    )
    # Add CORS headers to error responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    response = JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc)
        }
    )
    # Add CORS headers to error responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ============================================================================
# ============================================================================
# Position Sizing Endpoints
# ============================================================================

from pydantic import BaseModel
from typing import Optional

class PositionSizingRequest(BaseModel):
    """Request body for position sizing calculation - matches frontend"""
    account_size: float
    win_rate: float  # decimal (0.65 = 65%)
    avg_win: float
    avg_loss: float
    current_price: float  # option premium per share
    risk_per_trade_pct: float

@app.post("/api/position-sizing/calculate")
async def calculate_position_sizing(request: PositionSizingRequest):
    """
    Calculate optimal position size using Kelly Criterion and Risk of Ruin

    Accepts JSON body matching frontend's PositionSizingRequest
    """
    try:
        account_size = request.account_size
        win_rate = request.win_rate  # already decimal
        avg_win = request.avg_win
        avg_loss = request.avg_loss
        current_price = request.current_price
        risk_per_trade_pct = request.risk_per_trade_pct

        # Reward to risk ratio
        risk_reward = avg_win / avg_loss if avg_loss > 0 else 1

        # Kelly Criterion: f* = (p*b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        p = win_rate
        q = 1 - p
        b = risk_reward

        kelly_pct = ((p * b) - q) / b if b > 0 else 0
        kelly_pct = max(0, min(kelly_pct, 1))  # Clamp between 0 and 1

        # Capped Kelly (never risk more than 25%)
        kelly_capped = min(kelly_pct, 0.25)

        # Half Kelly (more conservative, recommended)
        half_kelly_pct = kelly_pct / 2

        # Expected value calculation
        expected_value = (p * avg_win) - (q * avg_loss)
        expected_value_pct = expected_value / avg_loss * 100 if avg_loss > 0 else 0

        # Calculate actual dollar amounts
        kelly_dollars = account_size * kelly_pct
        half_kelly_dollars = account_size * half_kelly_pct

        # Fixed risk based on user's risk_per_trade_pct
        fixed_risk_dollars = account_size * (risk_per_trade_pct / 100)

        # Calculate contracts (assuming 100 shares per contract)
        max_loss_per_contract = current_price * 100

        full_kelly_contracts = max(1, int(kelly_dollars / max_loss_per_contract)) if max_loss_per_contract > 0 else 1
        half_kelly_contracts = max(1, int(half_kelly_dollars / max_loss_per_contract)) if max_loss_per_contract > 0 else 1
        fixed_risk_contracts = max(1, int(fixed_risk_dollars / max_loss_per_contract)) if max_loss_per_contract > 0 else 1

        # Determine recommendation
        if kelly_pct > 0.15:
            recommendation = "HALF KELLY"
        elif kelly_pct > 0:
            recommendation = "FULL KELLY"
        else:
            recommendation = "NO EDGE - PASS"

        # Money making guide
        guide = f"With a {win_rate*100:.0f}% win rate and {risk_reward:.1f}:1 reward/risk, "
        if expected_value > 0:
            guide += f"you have positive expectancy of ${expected_value:.2f} per trade. "
            guide += f"Half Kelly ({half_kelly_pct*100:.1f}% risk) is recommended for steady growth."
        else:
            guide += "the math doesn't favor this trade. Consider passing or adjusting your strategy."

        return {
            "success": True,
            "calculations": {
                "kelly_percentage": round(kelly_pct * 100, 2),
                "kelly_percentage_capped": round(kelly_capped * 100, 2),
                "reward_to_risk_ratio": round(risk_reward, 2),
                "expected_value": round(expected_value, 2),
                "expected_value_pct": round(expected_value_pct, 2),
                "recommendation": recommendation
            },
            "positions": {
                "full_kelly": {
                    "dollars": round(kelly_dollars, 2),
                    "contracts": full_kelly_contracts,
                    "percentage": round(kelly_pct * 100, 2)
                },
                "half_kelly": {
                    "dollars": round(half_kelly_dollars, 2),
                    "contracts": half_kelly_contracts,
                    "percentage": round(half_kelly_pct * 100, 2)
                },
                "fixed_risk": {
                    "dollars": round(fixed_risk_dollars, 2),
                    "contracts": fixed_risk_contracts,
                    "percentage": risk_per_trade_pct
                }
            },
            "money_making_guide": guide
        }

    except Exception as e:
        print(f"❌ Error in position sizing calculation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def calculate_risk_of_ruin(win_rate: float, risk_per_trade: float) -> float:
    """
    Calculate probability of ruin (losing entire account)

    Simplified formula based on gambler's ruin problem
    """
    if win_rate >= 1.0 or risk_per_trade <= 0:
        return 0.0

    if win_rate <= 0.0:
        return 1.0

    # Simplified: higher risk per trade and lower win rate = higher ruin probability
    # This is an approximation
    ruin_prob = (1 - win_rate) / win_rate * risk_per_trade * 10
    return min(1.0, max(0.0, ruin_prob))

# ============================================================================
# Autonomous Trader Endpoints
# ============================================================================
# ============================================================================

# Initialize trader (if exists)
try:
    from core.autonomous_paper_trader import AutonomousPaperTrader
    trader = AutonomousPaperTrader()
    trader_available = True
    print("✅ SPY Autonomous Trader initialized successfully")
except Exception as e:
    trader = None
    trader_available = False
    print(f"⚠️ SPY Autonomous Trader not available: {e}")
    import traceback
    traceback.print_exc()

@app.get("/api/market/price-history/{symbol}")
async def get_price_history(symbol: str, days: int = 90):
    """
    Get price history for charting using Polygon.io

    Returns daily OHLCV data for the specified period
    """
    try:
        symbol = symbol.upper()

        print(f"📊 Fetching {days}-day price history for {symbol} from Polygon.io")

        polygon_key = os.getenv("POLYGON_API_KEY")
        if not polygon_key:
            raise HTTPException(
                status_code=503,
                detail="Polygon.io API key not configured"
            )

        # Calculate date range
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')

        # Fetch daily bars from Polygon.io
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "asc", "limit": 50000}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                results = data['results']

                # Convert to chart format
                chart_data = []
                for bar in results:
                    chart_data.append({
                        "time": bar['t'] // 1000,  # Convert milliseconds to seconds
                        "value": bar['c']  # Close price
                    })

                print(f"✅ Successfully fetched {len(chart_data)} data points from Polygon.io")

                return {
                    "success": True,
                    "symbol": symbol,
                    "data": chart_data,
                    "points": len(chart_data),
                    "source": "polygon.io"
                }
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Polygon.io returned no data for {symbol}"
                )
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Polygon.io API error: {response.status_code}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching price history: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price history: {str(e)}"
        )

# ============== AUTONOMOUS TRADER ADVANCED ENDPOINTS ==============

@app.get("/api/strategies/compare")
async def compare_all_strategies(symbol: str = "SPY"):
    """
    Multi-Strategy Optimizer - Compare ALL strategies side-by-side
    Shows which strategy has the best win rate for current conditions
    Includes entry timing optimization
    """
    try:
        # Fetch current market data
        gex_data = api_client.get_net_gamma(symbol)

        # Debug logging - DETAILED
        print(f"\n{'='*60}")
        print(f"DEBUG: Strategy Optimizer - GEX Data Check")
        print(f"{'='*60}")
        print(f"Type of gex_data: {type(gex_data)}")
        print(f"gex_data keys: {gex_data.keys() if isinstance(gex_data, dict) else 'NOT A DICT'}")
        print(f"gex_data value (first 500 chars): {str(gex_data)[:500]}")
        print(f"{'='*60}\n")

        # Check if we got valid data
        if not gex_data:
            raise HTTPException(
                status_code=503,
                detail="No GEX data available. API might be rate-limited or unavailable."
            )

        if not isinstance(gex_data, dict):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid GEX data type: {type(gex_data)}. Expected dict, got: {str(gex_data)[:200]}"
            )

        # Check for API error
        if 'error' in gex_data:
            error_msg = gex_data['error']
            if error_msg == 'rate_limit':
                raise HTTPException(
                    status_code=429,
                    detail="Trading Volatility API rate limit hit. Please wait a few minutes and try again."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Trading Volatility API Error: {error_msg}"
                )

        # Validate required fields
        required_fields = ['spot_price', 'net_gex', 'flip_point', 'call_wall', 'put_wall']
        missing_fields = [field for field in required_fields if field not in gex_data]
        if missing_fields:
            print(f"⚠️  Missing fields in gex_data: {missing_fields}")
            print(f"Available keys: {list(gex_data.keys())}")

        # Get VIX data for additional context using Polygon.io
        polygon_key = os.getenv('POLYGON_API_KEY')
        vix = 15.0  # Default fallback

        try:
            print(f"  🔄 Fetching VIX from Polygon.io...")
            if polygon_key:
                try:
                    import requests
                    from datetime import datetime, timedelta

                    # Get last trading day's VIX close
                    to_date = datetime.now().strftime('%Y-%m-%d')
                    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

                    url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
                    params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

                    response = requests.get(url, params=params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('status') == 'OK' and data.get('results'):
                            vix = float(data['results'][0]['c'])  # 'c' is close price
                            print(f"  ✅ VIX from Polygon.io: {vix}")
                        else:
                            print(f"  ⚠️ Polygon.io returned no VIX data")
                    else:
                        print(f"  ⚠️ Polygon.io HTTP {response.status_code}")
                except Exception as polygon_error:
                    print(f"  ⚠️ Polygon.io VIX fetch failed: {polygon_error}")
            else:
                print(f"  ⚠️ No Polygon.io API key - using default VIX")
        except Exception as vix_error:
            print(f"Warning: Could not fetch VIX: {vix_error}, using default {vix}")

        # Prepare market data for optimizer
        # Use the correct keys from get_net_gamma response
        # CRITICAL: Handle None values properly - use 'or 0' to provide defaults
        market_data = {
            'spot_price': float(gex_data.get('spot_price') or 0),
            'net_gex': float(gex_data.get('net_gex') or 0),
            'flip_point': float(gex_data.get('flip_point') or 0),
            'call_wall': float(gex_data.get('call_wall') or 0),
            'put_wall': float(gex_data.get('put_wall') or 0),
            'call_wall_gamma': float(gex_data.get('call_wall') or 0),
            'put_wall_gamma': float(gex_data.get('put_wall') or 0),
            'vix': float(vix or 15.0)
        }

        print(f"Market data prepared: {market_data}")

        # Get comprehensive strategy comparison
        try:
            comparison = strategy_optimizer.compare_all_strategies(market_data)
            print(f"✅ Strategy comparison completed successfully")
        except Exception as optimizer_error:
            print(f"❌ Error in strategy_optimizer.compare_all_strategies:")
            print(f"Error type: {type(optimizer_error)}")
            print(f"Error message: {str(optimizer_error)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Strategy optimizer failed: {str(optimizer_error)}"
            )

        return {
            "success": True,
            "symbol": symbol,
            "data": comparison
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ Error in compare_all_strategies endpoint:")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to compare strategies: {str(e)}")

# ============================================================================
# Multi-Symbol Scanner Endpoints (WITH DATABASE PERSISTENCE)
# ============================================================================

def init_scanner_database():
    """
    Verify scanner tables exist.
    NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
    Tables expected: scanner_runs, scanner_results
    """
    # Tables created by main schema - no action needed
    pass

# Initialize scanner database on startup
try:
    init_scanner_database()
except Exception as e:
    print(f"Scanner DB init warning: {e}")

# NOTE: Orphaned scanner setup code removed (was corrupted/incomplete).
# Scanner setups 2-7 below remain functional.

# ============================================================================
# Trade Setups - AI-Generated Trade Recommendations
# ============================================================================

def init_trade_setups_database():
    """
    Verify trade_setups table exists.
    NOTE: Table is now defined in db/config_and_database.py (single source of truth).
    """
    # Tables created by main schema - no action needed
    pass

# Initialize trade setups database on startup
init_trade_setups_database()


# ============================================================================
# Alerts System - Price & GEX Threshold Notifications
# ============================================================================

def init_alerts_database():
    """
    Verify alerts tables exist.
    NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
    Tables expected: alerts, alert_history
    """
    # Tables created by main schema - no action needed
    pass

# Initialize alerts database on startup
init_alerts_database()

# ============================================================================
# Startup & Shutdown Events
# ============================================================================

def validate_required_env_vars():
    """
    Validate all required environment variables at startup.
    Fails fast if critical configuration is missing.
    """
    required_vars = {
        'DATABASE_URL': 'PostgreSQL connection string (required)',
    }

    recommended_vars = {
        'TRADING_VOLATILITY_API_KEY': 'GEX data from TradingVolatility',
        'TRADIER_API_KEY': 'Live options data and trading',
        'POLYGON_API_KEY': 'Historical market data',
    }

    errors = []
    warnings = []

    # Check required vars
    for var, description in required_vars.items():
        if not os.getenv(var):
            errors.append(f"❌ MISSING REQUIRED: {var} - {description}")

    # Check recommended vars
    for var, description in recommended_vars.items():
        if not os.getenv(var):
            warnings.append(f"⚠️  Missing recommended: {var} - {description}")

    # Print results
    print("\n" + "=" * 60)
    print("🔐 ENVIRONMENT VARIABLE VALIDATION")
    print("=" * 60)

    if errors:
        for error in errors:
            print(error)
        print("\n❌ STARTUP BLOCKED: Fix missing required environment variables")
        raise RuntimeError("Missing required environment variables. Check logs above.")

    print("✅ All required environment variables configured")

    if warnings:
        for warning in warnings:
            print(warning)
    else:
        print("✅ All recommended environment variables configured")

    # Validate API key formats
    tradier_key = os.getenv('TRADIER_API_KEY', '')
    if tradier_key and len(tradier_key) < 10:
        print("⚠️  TRADIER_API_KEY appears invalid (too short)")

    polygon_key = os.getenv('POLYGON_API_KEY', '')
    if polygon_key and len(polygon_key) < 10:
        print("⚠️  POLYGON_API_KEY appears invalid (too short)")

    print("=" * 60 + "\n")


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("=" * 80)
    print("🚀 AlphaGEX API Starting...")
    print("=" * 80)

    # Validate environment variables FIRST
    validate_required_env_vars()

    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"Market Open: {is_market_open()}")
    print(f"Current Time (ET): {get_et_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 80)
    print("📊 Available Endpoints:")
    print("  - GET  /                                  Health check")
    print("  - GET  /docs                              API documentation")
    print("  - GET  /api/gex/{symbol}                  GEX data")
    print("  - GET  /api/gamma/{symbol}/intelligence   Gamma 3 views")
    print("  - POST /api/ai/analyze                    AI Copilot")
    print("  - WS   /ws/market-data                    Real-time updates")
    print("\n🧠 Psychology Trap Detection:")
    print("  - GET  /api/psychology/current-regime     Current regime analysis")
    print("  - GET  /api/psychology/rsi-analysis/{symbol}  Multi-TF RSI")
    print("  - GET  /api/psychology/liberation-setups  Liberation trades")
    print("  - GET  /api/psychology/false-floors       False floor warnings")
    print("  - GET  /api/psychology/history            Historical signals")
    print("  - GET  /api/psychology/statistics         Sucker statistics")
    print("=" * 80)

    # =========================================================================
    # DATABASE MIGRATION: Rename old Greek bot tables to new Biblical names
    # The bots were renamed (ARES->FORTRESS, TITAN->SAMSON, etc.) but the
    # database tables still have the old names. Migrate them before anything
    # else creates empty tables with the new names.
    # =========================================================================
    print("\n🔄 Checking bot table migrations (Greek -> Biblical names)...")
    try:
        from database_adapter import get_connection as _get_migration_conn

        _bot_table_renames = {
            # old_prefix -> new_prefix
            'ares': ('fortress', ['positions', 'signals', 'daily_perf', 'logs', 'equity_snapshots']),
            'titan': ('samson', ['positions', 'signals', 'daily_perf', 'logs', 'equity_snapshots']),
            'athena': ('solomon', ['positions', 'signals', 'daily_perf', 'logs', 'equity_snapshots']),
            'pegasus': ('anchor', ['positions', 'signals', 'daily_perf', 'logs', 'equity_snapshots']),
            'icarus': ('gideon', ['positions', 'signals', 'daily_perf', 'logs', 'equity_snapshots']),
            'prometheus': ('jubilee', [
                'positions', 'signals', 'capital_deployments', 'rate_analysis',
                'daily_briefings', 'roll_decisions', 'config', 'logs',
                'equity_snapshots', 'ic_positions', 'ic_closed_trades',
                'ic_signals', 'ic_config', 'ic_equity_snapshots',
            ]),
            'heracles': ('valor', [
                'positions', 'closed_trades', 'signals', 'equity_snapshots',
                'config', 'win_tracker', 'logs', 'daily_perf',
                'paper_account', 'scan_activity',
            ]),
        }

        _mig_conn = _get_migration_conn()
        _mig_cur = _mig_conn.cursor()
        _migrated_count = 0

        for old_prefix, (new_prefix, suffixes) in _bot_table_renames.items():
            for suffix in suffixes:
                old_name = f"{old_prefix}_{suffix}"
                new_name = f"{new_prefix}_{suffix}"
                try:
                    # Check if old table exists
                    _mig_cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
                        (old_name,)
                    )
                    if not _mig_cur.fetchone()[0]:
                        continue

                    # Check if new table exists
                    _mig_cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
                        (new_name,)
                    )
                    new_exists = _mig_cur.fetchone()[0]

                    if new_exists:
                        _mig_cur.execute(f"SELECT COUNT(*) FROM {new_name}")
                        if _mig_cur.fetchone()[0] > 0:
                            continue  # Both have data, skip
                        _mig_cur.execute(f"DROP TABLE {new_name}")

                    _mig_cur.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
                    print(f"  Migrated table: {old_name} -> {new_name}")
                    _migrated_count += 1
                except Exception as _te:
                    print(f"  Warning: {old_name} migration: {_te}")

            # Migrate config keys for this bot
            try:
                _old_prefix_len = len(old_prefix) + 1  # +1 for underscore
                _mig_cur.execute(f"""
                    UPDATE autonomous_config
                    SET key = '{new_prefix}_' || SUBSTRING(key FROM {_old_prefix_len + 1})
                    WHERE key LIKE '{old_prefix}_%'
                      AND NOT EXISTS (
                          SELECT 1 FROM autonomous_config ac2
                          WHERE ac2.key = '{new_prefix}_' || SUBSTRING(autonomous_config.key FROM {_old_prefix_len + 1})
                      )
                """)
                if _mig_cur.rowcount > 0:
                    print(f"  Migrated {_mig_cur.rowcount} config keys: {old_prefix}_* -> {new_prefix}_*")
                    _migrated_count += _mig_cur.rowcount
            except Exception as _ce:
                print(f"  Warning: config key migration {old_prefix} -> {new_prefix}: {_ce}")

        _mig_conn.commit()
        _mig_conn.close()

        if _migrated_count > 0:
            print(f"  Database migration complete: {_migrated_count} items migrated")
        else:
            print("  No migrations needed (tables already have correct names)")
    except Exception as e:
        print(f"  Migration check skipped: {e}")

    # Auto-initialize database with historical data on first startup
    print("\n🔄 Checking database initialization...")
    try:
        import sys
        sys.path.insert(0, str(parent_dir))
        from scripts.startup_init import initialize_on_startup
        initialize_on_startup()
    except Exception as e:
        print(f"⚠️  Initialization check failed: {e}")
        print("📊 App will create tables as needed during operation")

    # Initialize WATCHTOWER engine with ML models pre-loaded for faster first request
    print("\n👁️  Initializing WATCHTOWER engine...")
    try:
        from core.watchtower_engine import initialize_watchtower_engine
        initialize_watchtower_engine()
        print("✅ WATCHTOWER engine initialized with ML models pre-loaded")
    except Exception as e:
        print(f"⚠️  WATCHTOWER initialization warning: {e}")
        print("   WATCHTOWER will lazy-load on first request")

    # Pre-check Math Optimizer availability (lazy initialization, but check dependencies)
    print("\n🧮 Checking Math Optimizer dependencies...")
    try:
        import numpy as np
        print(f"✅ NumPy version: {np.__version__}")
        # Try to import the module (doesn't initialize singleton yet)
        from core.math_optimizers import MathOptimizerOrchestrator
        print("✅ Math Optimizer module loaded - will initialize on first request")
    except ImportError as e:
        print(f"⚠️  Math Optimizer import warning: {e}")
        print("   Math Optimizer page will show degraded mode")
    except Exception as e:
        print(f"⚠️  Math Optimizer check warning: {e}")
        print("   Math Optimizer page will show degraded mode")

    # Auto-run AUTONOMOUS backtests on startup IF database is empty
    print("\n🔄 Checking backtest results...")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM backtest_results")
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            print("⚠️  No backtest results found. Auto-running AUTONOMOUS backtests in background...")
            import threading

            def run_autonomous_backtests_async():
                """Run autonomous backtest engine and save to backtest_results table"""
                try:
                    import sys
                    sys.path.insert(0, str(parent_dir))
                    from backtest.autonomous_backtest_engine import get_backtester

                    print("🔄 Initializing autonomous backtest engine...")
                    backtester = get_backtester()

                    # Run backtests and save to database (90 days default)
                    print("🚀 Running pattern backtests (90 days)...")
                    results = backtester.backtest_all_patterns_and_save(lookback_days=90, save_to_db=True)

                    patterns_with_data = sum(1 for r in results if r.get('total_signals', 0) > 0)
                    print(f"✅ Autonomous backtests completed - {patterns_with_data} patterns saved to backtest_results")
                except Exception as e:
                    print(f"❌ Error running autonomous backtests: {e}")
                    import traceback
                    traceback.print_exc()

            # Run in background thread so startup doesn't block
            thread = threading.Thread(target=run_autonomous_backtests_async, daemon=True)
            thread.start()
            print("✅ Autonomous backtests started in background thread")
        else:
            print(f"✅ Found {count} existing backtest results")
    except Exception as e:
        print(f"⚠️  Could not check backtest results: {e}")

    # =========================================================================
    # START THREAD WATCHDOG - Auto-restarts crashed background threads
    # =========================================================================
    print("\n" + "=" * 80)
    print("🐕 STARTING THREAD WATCHDOG")
    print("=" * 80)
    print("Watchdog monitors all background threads and auto-restarts them if they crash")
    print("Check interval: 30 seconds | Max restarts: 10/hour per thread")
    print("")

    try:
        from services.thread_watchdog import get_watchdog

        watchdog = get_watchdog()

        # Register Autonomous Trader
        try:
            from scheduler.autonomous_scheduler import run_continuous_scheduler
            watchdog.register(
                name="AutonomousTrader",
                target=run_continuous_scheduler,
                kwargs={'check_interval_minutes': 5},
                max_restarts=10
            )
            print("✅ Registered: AutonomousTrader (trades every 5 min during market hours)")
        except ImportError as e:
            print(f"⚠️  Could not register AutonomousTrader: {e}")

        # Register Automated Data Collector
        try:
            from data.automated_data_collector import run_scheduler as run_data_collector
            watchdog.register(
                name="AutomatedDataCollector",
                target=run_data_collector,
                kwargs={},
                max_restarts=10
            )
            print("✅ Registered: AutomatedDataCollector (GEX snapshots every 5 min)")
        except Exception as e:
            print(f"⚠️  Could not register AutomatedDataCollector: {e}")
            import traceback
            traceback.print_exc()

        # =====================================================================
        # Register FORTRESS + CORNERSTONE Scheduler (APScheduler-based trading bots)
        # FORTRESS: Aggressive Iron Condor - 8:30 AM - 3:30 PM CT, every 5 min ($200K)
        # CORNERSTONE: SPX Wheel Strategy - 9:05 AM CT daily ($400K)
        # =====================================================================
        try:
            def run_fortress_cornerstone_scheduler():
                """
                Run FORTRESS and CORNERSTONE trading bots via APScheduler.
                This function runs continuously and manages both bots.

                CRITICAL: Includes health monitoring to detect zombie scheduler states.
                If the APScheduler internal thread crashes but is_running stays True,
                this function will detect the unhealthy state and raise an exception
                so the watchdog can restart the thread.
                """
                import time
                from scheduler.trader_scheduler import get_scheduler

                print("🚀 Starting FORTRESS + CORNERSTONE Scheduler...")
                scheduler = get_scheduler()

                if not scheduler.is_running:
                    scheduler.start()
                    print("✅ FORTRESS + CORNERSTONE Scheduler started successfully")
                else:
                    print("ℹ️  FORTRESS + CORNERSTONE Scheduler already running")

                # Health monitoring variables
                consecutive_unhealthy = 0
                max_unhealthy_before_restart = 3  # Restart after 3 consecutive failures (3 min)

                # Keep thread alive - APScheduler runs in background
                while True:
                    time.sleep(60)

                    # CRITICAL: Health check to detect zombie scheduler state
                    # The APScheduler internal thread can crash while is_running stays True.
                    # is_scheduler_healthy() checks:
                    # 1. If APScheduler's _thread is alive
                    # 2. If jobs are actually executing (not stale >15 min)
                    if scheduler.is_running:
                        is_healthy = scheduler.is_scheduler_healthy()
                        status = scheduler.get_status()

                        if is_healthy:
                            consecutive_unhealthy = 0  # Reset counter on healthy check
                            if status.get('market_open'):
                                print(f"📊 FORTRESS/CORNERSTONE Status: Market OPEN | FORTRESS={scheduler.fortress_execution_count}, SOLOMON={getattr(scheduler, 'solomon_execution_count', 0)}, ANCHOR={getattr(scheduler, 'anchor_execution_count', 0)}")
                        else:
                            consecutive_unhealthy += 1
                            print(f"⚠️ SCHEDULER UNHEALTHY ({consecutive_unhealthy}/{max_unhealthy_before_restart})")
                            print(f"   is_running={scheduler.is_running}, scheduler_healthy={status.get('scheduler_healthy')}")

                            if consecutive_unhealthy >= max_unhealthy_before_restart:
                                # CRITICAL: Raise exception so watchdog can restart this thread
                                # This is the FIX for the 6:05 AM issue - scheduler was in zombie state
                                raise RuntimeError(
                                    f"Scheduler unhealthy for {consecutive_unhealthy} consecutive checks. "
                                    f"APScheduler internal thread may have crashed. Forcing restart via watchdog."
                                )
                    else:
                        # scheduler.is_running is False - try to restart
                        print("⚠️ Scheduler not running - attempting restart...")
                        try:
                            scheduler.start()
                            print("✅ Scheduler restarted")
                            consecutive_unhealthy = 0
                        except Exception as e:
                            print(f"❌ Failed to restart scheduler: {e}")
                            consecutive_unhealthy += 1
                            if consecutive_unhealthy >= max_unhealthy_before_restart:
                                raise RuntimeError(f"Failed to restart scheduler after {consecutive_unhealthy} attempts: {e}")

            watchdog.register(
                name="FORTRESS_CORNERSTONE_Scheduler",
                target=run_fortress_cornerstone_scheduler,
                kwargs={},
                max_restarts=10
            )
            print("✅ Registered: FORTRESS_CORNERSTONE_Scheduler")
            print("   • FORTRESS (Aggressive Iron Condor): 8:30 AM - 3:30 PM CT, every 5 min, $200K capital")
            print("   • CORNERSTONE (SPX Wheel): 9:05 AM CT daily, $400K capital")
        except Exception as e:
            print(f"⚠️  Could not register FORTRESS_CORNERSTONE_Scheduler: {e}")
            import traceback
            traceback.print_exc()

        # Start the watchdog (this starts all registered threads + monitoring)
        watchdog.start()

        print("")
        print("🐕 Watchdog started! All threads are now monitored and will auto-restart.")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"❌ Failed to start watchdog: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80 + "\n")

    # Start Psychology Trap Notification Monitor (async task, not thread)
    try:
        print("🔔 Starting Psychology Trap Notification Monitor...")
        print("⚡ Critical patterns: GAMMA_SQUEEZE_CASCADE, FLIP_POINT_CRITICAL")
        print("⏰ Check interval: 60 seconds")

        # Start notification monitor as background task
        asyncio.create_task(notification_manager.monitor_and_notify(interval_seconds=60))

        print("✅ Notification Monitor started successfully!")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not start Notification Monitor: {e}")
        print("   (Notifications will not be sent)")
        print("=" * 80 + "\n")

    # =========================================================================
    # STARTUP SUMMARY - Show what's running
    # =========================================================================
    print("\n" + "=" * 80)
    print("🎯 ALPHAGEX AUTONOMOUS SYSTEM STATUS")
    print("=" * 80)
    print("✅ Thread Watchdog: ACTIVE (auto-restarts crashed threads)")
    print("✅ LAZARUS Trader: MONITORED (0DTE options, every 5 min)")
    print("✅ FORTRESS Trader: MONITORED (Iron Condor, 8:30 AM - 3:30 PM CT, $200K)")
    print("✅ CORNERSTONE Trader: MONITORED (SPX Wheel, 9:05 AM CT daily, $400K)")
    print("✅ Data Collector: MONITORED (GEX snapshots every 5 min)")
    print("✅ Notification Monitor: RUNNING (checks every 60 sec)")
    print("✅ Database: INITIALIZED")
    print("")
    print("📊 TRADING BOTS (ALL AUTOMATED):")
    print("   • LAZARUS: 0DTE SPY/SPX options - every 5 min during market hours")
    print("   • FORTRESS: Aggressive Iron Condor - 8:30 AM - 3:30 PM CT (targets 10% monthly)")
    print("   • CORNERSTONE: SPX Cash-Secured Put Wheel - 9:05 AM CT daily")
    print("   • Prophet AI: Provides recommendations to FORTRESS for trade decisions")
    print("")
    print("💰 CAPITAL ALLOCATION:")
    print("   • LAZARUS: $300,000 (30%)")
    print("   • CORNERSTONE:   $400,000 (40%)")
    print("   • FORTRESS:    $200,000 (20%)")
    print("   • Reserve: $100,000 (10%)")
    print("")
    print("🔄 AUTO-RECOVERY:")
    print("   • All bots auto-restart within 30 seconds if they crash")
    print("   • Max 10 restarts per hour per bot (rate limited)")
    print("   • State persisted to database (survives full restarts)")
    print("=" * 80 + "\n")

    # =========================================================================
    # MARK SERVICE AS READY (for zero-downtime deployments)
    # =========================================================================
    try:
        from backend.services.graceful_shutdown import get_shutdown_manager, setup_signal_handlers
        manager = get_shutdown_manager()

        # Register watchdog for graceful shutdown
        if thread_watchdog:
            manager.register_component('watchdog', thread_watchdog)

        # Setup signal handlers for SIGTERM/SIGINT
        setup_signal_handlers()

        # Mark service as ready to accept traffic
        manager.set_ready(True)
        print("✅ Service marked as READY (graceful shutdown enabled)")
    except ImportError as e:
        print(f"ℹ️  Graceful shutdown manager not available: {e}")
    except Exception as e:
        print(f"⚠️  Could not initialize graceful shutdown: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Run on application shutdown - Graceful shutdown for zero-downtime deployments.

    Shutdown sequence:
    1. Mark service as not ready (load balancer stops sending traffic)
    2. Drain in-flight requests (wait up to 30s)
    3. Close database connections
    4. Stop background threads
    5. Log open positions state
    """
    print("🛑 AlphaGEX API Shutting down...")
    print("   Initiating graceful shutdown sequence...")

    try:
        from backend.services.graceful_shutdown import get_shutdown_manager
        manager = get_shutdown_manager()

        # Register thread watchdog for cleanup
        if thread_watchdog:
            manager.register_component('watchdog', thread_watchdog)

        # Execute graceful shutdown
        await manager.shutdown()

        print("✅ Graceful shutdown complete")

    except ImportError as e:
        print(f"⚠️  Graceful shutdown manager not available: {e}")
        # Fallback: close database pool directly
        try:
            from database_adapter import close_pool
            close_pool()
            print("✅ Database pool closed (fallback)")
        except Exception as db_err:
            print(f"⚠️  Database pool close failed: {db_err}")
    except Exception as e:
        print(f"❌ Graceful shutdown error: {e}")
        import traceback
        traceback.print_exc()

# ============================================================================
# Run Server (for local development)
# ============================================================================

if __name__ == "__main__":
    # Run with: python main.py
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info",
        ws="none"  # Disable websockets to avoid version conflicts
    )
