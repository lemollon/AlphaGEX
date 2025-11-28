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
from api.routes import (
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
)

# Import existing AlphaGEX logic (DO NOT MODIFY THESE)
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open, MultiStrategyOptimizer
from config_and_database import STRATEGIES, init_database, MM_STATES
from database_adapter import get_connection
import psycopg2
import psycopg2.extras

# Import probability calculator (NEW - Phase 2 Self-Learning)
from probability_calculator import ProbabilityCalculator

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from unified_data_provider import get_data_provider, get_quote, get_price, get_vix
    UNIFIED_DATA_AVAILABLE = True
    print("✅ Backend: Unified Data Provider (Tradier) integrated")
except ImportError as e:
    UNIFIED_DATA_AVAILABLE = False
    print(f"⚠️ Backend: Unified Data Provider not available: {e}")

# Initialize database schema on startup
print("Initializing database schema...")
init_database()
print("✓ Database initialized")

# Create FastAPI app
app = FastAPI(
    title="AlphaGEX API",
    description="Professional Options Intelligence Platform - Backend API",
    version="2.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Custom CORS Middleware - Ensures headers are added to ALL responses
class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = JSONResponse(content={"status": "ok"}, status_code=200)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response

        # Process the request
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"

        return response

# Add custom CORS middleware FIRST
app.add_middleware(CORSHeaderMiddleware)

# CORS Configuration - Restrict to specific origins for security
# In production, this limits which domains can access the API
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Restricted to specific frontend origins
    allow_credentials=True,  # Allow credentials with specific origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],
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
print("✅ Route modules loaded: vix, spx, system, trader, backtest, database, gex, gamma, core, optimizer, ai, probability, notifications, misc, alerts, setups, scanner, autonomous, psychology")

# Initialize existing AlphaGEX components (singleton pattern)
api_client = TradingVolatilityAPI()
claude_ai = ClaudeIntelligence()
monte_carlo = MonteCarloEngine()
pricer = BlackScholesPricer()
strategy_optimizer = MultiStrategyOptimizer()

# Initialize probability calculator (NEW - Phase 2 Self-Learning)
probability_calc = ProbabilityCalculator()

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
                except:
                    pass  # If sending error fails, just continue
                await asyncio.sleep(10)

    except WebSocketDisconnect:
        pass  # Normal disconnect, cleanup in finally
    except Exception as e:
        print(f"Trader WebSocket error: {e}")
    finally:
        # Guaranteed cleanup - prevents memory leak
        if connection_id in _connection_subscriptions:
            del _connection_subscriptions[connection_id]
        try:
            manager.disconnect(websocket)
        except:
            pass  # Ignore disconnect errors

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
            ORDER BY exit_date DESC, exit_time DESC
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
        print(f"Positions WebSocket error: {e}")

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

@app.post("/api/position-sizing/calculate")
async def calculate_position_sizing(
    account_size: float,
    risk_percent: float,
    win_rate: float,
    risk_reward: float,
    option_premium: float,
    max_loss_per_contract: float = None
):
    """
    Calculate optimal position size using Kelly Criterion and Risk of Ruin

    Returns:
    - Kelly Criterion sizing
    - Optimal F sizing
    - Risk of Ruin probability
    - Recommended contracts
    """
    try:
        # Kelly Criterion: f* = (p*b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        p = win_rate / 100  # Convert percentage to decimal
        q = 1 - p
        b = risk_reward  # win/loss ratio

        kelly_pct = ((p * b) - q) / b if b > 0 else 0
        kelly_pct = max(0, min(kelly_pct, 1))  # Clamp between 0 and 1

        # Half Kelly (more conservative, recommended)
        half_kelly_pct = kelly_pct / 2

        # Quarter Kelly (very conservative)
        quarter_kelly_pct = kelly_pct / 4

        # Calculate actual dollar amounts
        kelly_dollars = account_size * kelly_pct
        half_kelly_dollars = account_size * half_kelly_pct
        quarter_kelly_dollars = account_size * quarter_kelly_pct

        # User's current risk amount
        user_risk_dollars = account_size * (risk_percent / 100)

        # Calculate contracts based on different methods
        max_loss = max_loss_per_contract if max_loss_per_contract else (option_premium * 100)

        kelly_contracts = max(1, int(kelly_dollars / max_loss))
        half_kelly_contracts = max(1, int(half_kelly_dollars / max_loss))
        quarter_kelly_contracts = max(1, int(quarter_kelly_dollars / max_loss))
        user_contracts = max(1, int(user_risk_dollars / max_loss))

        # Risk of Ruin calculation (simplified)
        # Probability of losing entire account with given win rate and risk per trade
        risk_of_ruin_kelly = calculate_risk_of_ruin(p, kelly_pct)
        risk_of_ruin_half_kelly = calculate_risk_of_ruin(p, half_kelly_pct)
        risk_of_ruin_user = calculate_risk_of_ruin(p, risk_percent / 100)

        # Optimal F (Ralph Vince method)
        # Simplified: f = 1 / biggest_loss_percentage
        # For options, assume biggest loss = 100% of premium
        optimal_f_pct = 1 / (max_loss / account_size) if max_loss > 0 else 0
        optimal_f_pct = min(optimal_f_pct, kelly_pct)  # Never exceed Kelly
        optimal_f_contracts = max(1, int((account_size * optimal_f_pct) / max_loss))

        return {
            "success": True,
            "kelly_criterion": {
                "full_kelly_pct": round(kelly_pct * 100, 2),
                "half_kelly_pct": round(half_kelly_pct * 100, 2),
                "quarter_kelly_pct": round(quarter_kelly_pct * 100, 2),
                "full_kelly_dollars": round(kelly_dollars, 2),
                "half_kelly_dollars": round(half_kelly_dollars, 2),
                "quarter_kelly_dollars": round(quarter_kelly_dollars, 2),
                "full_kelly_contracts": kelly_contracts,
                "half_kelly_contracts": half_kelly_contracts,
                "quarter_kelly_contracts": quarter_kelly_contracts,
                "risk_of_ruin": round(risk_of_ruin_kelly * 100, 2)
            },
            "optimal_f": {
                "optimal_f_pct": round(optimal_f_pct * 100, 2),
                "optimal_f_contracts": optimal_f_contracts,
                "optimal_f_dollars": round(account_size * optimal_f_pct, 2)
            },
            "user_sizing": {
                "user_risk_pct": risk_percent,
                "user_risk_dollars": round(user_risk_dollars, 2),
                "user_contracts": user_contracts,
                "risk_of_ruin": round(risk_of_ruin_user * 100, 2)
            },
            "recommendation": {
                "recommended_method": "Half Kelly" if half_kelly_pct < risk_percent / 100 else "Quarter Kelly",
                "recommended_contracts": half_kelly_contracts if half_kelly_pct < risk_percent / 100 else quarter_kelly_contracts,
                "recommended_dollars": round(half_kelly_dollars if half_kelly_pct < risk_percent / 100 else quarter_kelly_dollars, 2),
                "recommended_pct": round((half_kelly_pct if half_kelly_pct < risk_percent / 100 else quarter_kelly_pct) * 100, 2),
                "reasoning": "Half Kelly balances growth with safety" if half_kelly_pct < risk_percent / 100 else "Quarter Kelly recommended for higher risk setups"
            },
            "parameters": {
                "account_size": account_size,
                "risk_percent": risk_percent,
                "win_rate": win_rate,
                "risk_reward": risk_reward,
                "option_premium": option_premium,
                "max_loss_per_contract": max_loss
            }
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
    """Initialize scanner database schema with tracking"""

    conn = get_connection()
    c = conn.cursor()

    # Scanner runs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scanner_runs (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbols_scanned TEXT,
            total_symbols INTEGER,
            opportunities_found INTEGER,
            scan_duration_seconds REAL,
            user_notes TEXT
        )
    ''')

    # Scanner results table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scanner_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            confidence REAL,
            net_gex REAL,
            spot_price REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            risk_reward REAL,
            expected_move TEXT,
            reasoning TEXT,
            FOREIGN KEY (scan_id) REFERENCES scanner_runs(id)
        )
    ''')

    conn.commit()
    conn.close()

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
    """Initialize trade setups database schema"""

    conn = get_connection()
    c = conn.cursor()

    # Trade setups table
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            confidence REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            risk_reward REAL,
            position_size INTEGER,
            max_risk_dollars REAL,
            time_horizon TEXT,
            catalyst TEXT,
            ai_reasoning TEXT,
            money_making_plan TEXT,
            status TEXT DEFAULT 'active',
            actual_entry REAL,
            actual_exit REAL,
            actual_pnl REAL,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()

# Initialize trade setups database on startup
init_trade_setups_database()


# ============================================================================
# Alerts System - Price & GEX Threshold Notifications
# ============================================================================

def init_alerts_database():
    """Initialize alerts database schema"""

    conn = get_connection()
    c = conn.cursor()

    # Alerts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'active',
            triggered_at DATETIME,
            triggered_value REAL,
            notes TEXT
        )
    ''')

    # Alert history table (for triggered alerts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            actual_value REAL NOT NULL,
            message TEXT,
            FOREIGN KEY (alert_id) REFERENCES alerts(id)
        )
    ''')

    conn.commit()
    conn.close()

# Initialize alerts database on startup
init_alerts_database()

# ============================================================================
# Startup & Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("=" * 80)
    print("🚀 AlphaGEX API Starting...")
    print("=" * 80)
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

    # Auto-initialize database with historical data on first startup
    print("\n🔄 Checking database initialization...")
    try:
        import sys
        sys.path.insert(0, str(parent_dir))
        from startup_init import initialize_on_startup
        initialize_on_startup()
    except Exception as e:
        print(f"⚠️  Initialization check failed: {e}")
        print("📊 App will create tables as needed during operation")

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
                    from autonomous_backtest_engine import get_backtester

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

    # Start Autonomous Trader in background thread
    try:
        import threading
        from autonomous_scheduler import run_continuous_scheduler

        print("\n🤖 Starting Autonomous Trader...")
        print("⏰ Check interval: 5 minutes (optimized for max responsiveness)")
        print("📈 Will trade daily during market hours (9:30am-4pm ET, Mon-Fri)")
        print("🎯 GUARANTEED: Makes at least 1 trade per day (directional or Iron Condor)")

        # Start autonomous trader in daemon thread
        trader_thread = threading.Thread(
            target=run_continuous_scheduler,
            kwargs={'check_interval_minutes': 5},
            daemon=True,
            name="AutonomousTrader"
        )
        trader_thread.start()

        print("✅ Autonomous Trader started successfully!")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not start Autonomous Trader: {e}")
        print("   (Trader can still be run manually via autonomous_scheduler.py)")
        print("=" * 80 + "\n")

    # Start Psychology Trap Notification Monitor
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
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    print("🛑 AlphaGEX API Shutting down...")

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
        log_level="info"
    )
