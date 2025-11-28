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
print("✅ Route modules loaded: vix, spx, system, trader, backtest, database, gex, gamma, core, optimizer, ai, probability, notifications, misc, alerts, setups, scanner, autonomous")

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

):
    """Check if a proposed SPX trade passes risk limits"""
    try:
        from spx_institutional_trader import get_spx_trader_100m

        trader = get_spx_trader_100m()

        proposed_trade = {
            'contracts': contracts,
            'entry_price': entry_price,
            'delta': delta
        }

        can_trade, reason = trader.check_risk_limits(proposed_trade)

        return {
            "success": True,
            "data": {
                "can_trade": can_trade,
                "reason": reason,
                "proposed_trade": proposed_trade
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    from autonomous_paper_trader import AutonomousPaperTrader
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

Target: ${target_strike:.0f} | Stop: ${put_wall:.0f}
Risk ${(sell_strike - buy_strike):.0f} to make ${(target_strike - buy_strike):.0f}
Best with 3-14 DTE""",
                        'reasoning': f"Bullish setup. GEX: ${net_gex/1e9:.1f}B. {distance_to_flip:.1f}% from flip."
                    })

                # 2. BEARISH PUT SPREAD
                if net_gex > 1e9 or spot_price < flip_point:
                    buy_strike = round_strike(min(spot_price, flip_point + spread_width/2))
                    sell_strike = round_strike(buy_strike - spread_width)
                    target_strike = round_strike(max(put_wall, sell_strike - spread_width))

                    confidence = 0.62
                    if net_gex > 2e9:
                        confidence += 0.08

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BEARISH_PUT_SPREAD',
                        'confidence': min(confidence, 0.80),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': buy_strike,
                        'target_price': target_strike,
                        'stop_price': call_wall,
                        'risk_reward': 2.0,
                        'expected_move': '2-4% down',
                        'win_rate': 0.62,
                        'money_making_plan': f"""BUY {buy_strike:.0f} PUT / SELL {sell_strike:.0f} PUT

Target: ${target_strike:.0f} | Stop: ${call_wall:.0f}
Risk ${(buy_strike - sell_strike):.0f} to make ${(buy_strike - target_strike):.0f}
Best with 3-14 DTE""",
                        'reasoning': f"Bearish setup. GEX: ${net_gex/1e9:.1f}B. Below flip."
                    })

                # 3. BULL PUT SPREAD (Credit)
                if net_gex > 0.5e9 and distance_to_put_wall >= 2.0:
                    sell_strike = round_strike(put_wall)
                    buy_strike = round_strike(sell_strike - spread_width)

                    confidence = 0.70
                    if distance_to_put_wall > 3.0:
                        confidence += 0.05

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BULL_PUT_SPREAD',
                        'confidence': min(confidence, 0.80),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': sell_strike,
                        'stop_price': buy_strike,
                        'risk_reward': 0.4,
                        'expected_move': 'Flat to +2%',
                        'win_rate': 0.70,
                        'money_making_plan': f"""SELL {sell_strike:.0f} PUT / BUY {buy_strike:.0f} PUT

Credit spread at support. Collect premium, close at 50%
Best with 5-21 DTE | Target: 50% profit in 3-5 days""",
                        'reasoning': f"Credit spread. Put wall support at ${put_wall:.0f} ({distance_to_put_wall:.1f}% away)."
                    })

                # 4. BEAR CALL SPREAD (Credit)
                if net_gex > 0.5e9 and distance_to_call_wall >= 2.0:
                    sell_strike = round_strike(call_wall)
                    buy_strike = round_strike(sell_strike + spread_width)

                    confidence = 0.68
                    if distance_to_call_wall > 3.0:
                        confidence += 0.05

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BEAR_CALL_SPREAD',
                        'confidence': min(confidence, 0.78),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': sell_strike,
                        'stop_price': buy_strike,
                        'risk_reward': 0.4,
                        'expected_move': 'Flat to -2%',
                        'win_rate': 0.68,
                        'money_making_plan': f"""SELL {sell_strike:.0f} CALL / BUY {buy_strike:.0f} CALL

Credit spread at resistance. Collect premium, close at 50%
Best with 5-21 DTE | Target: 50% profit in 3-5 days""",
                        'reasoning': f"Credit spread. Call wall resistance at ${call_wall:.0f} ({distance_to_call_wall:.1f}% away)."
                    })

                # 5. IRON CONDOR
                if net_gex > 1e9 and distance_to_call_wall >= 2.0 and distance_to_put_wall >= 2.0:
                    call_short = round_strike(call_wall)
                    call_long = round_strike(call_short + spread_width)
                    put_short = round_strike(put_wall)
                    put_long = round_strike(put_short - spread_width)

                    confidence = 0.72
                    if distance_to_call_wall > 3.0 and distance_to_put_wall > 3.0:
                        confidence += 0.08

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'IRON_CONDOR',
                        'confidence': min(confidence, 0.85),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': spot_price,
                        'stop_price': None,
                        'risk_reward': 0.3,
                        'expected_move': 'Range bound',
                        'win_rate': 0.72,
                        'money_making_plan': f"""SELL {call_short:.0f}/{call_long:.0f} CALL SPREAD + {put_short:.0f}/{put_long:.0f} PUT SPREAD

Range: ${put_wall:.0f} - ${call_wall:.0f}
Premium collection. Close at 50% profit or 2 DTE
Best with 5-10 DTE""",
                        'reasoning': f"Strong positive GEX (${net_gex/1e9:.1f}B) with wide walls. Perfect IC setup."
                    })

                # 6. NEGATIVE GEX SQUEEZE
                if net_gex < -1e9 and distance_to_flip < 2.0:
                    entry_strike = round_strike(flip_point + 0.5)

                    confidence = 0.75 if spot_price < flip_point else 0.85

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'NEGATIVE_GEX_SQUEEZE',
                        'confidence': confidence,
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': entry_strike,
                        'target_price': call_wall,
                        'stop_price': put_wall,
                        'risk_reward': 3.0,
                        'expected_move': '2-3% up',
                        'win_rate': 0.68,
                        'money_making_plan': f"""BUY {entry_strike:.0f} CALL when price breaks ${flip_point:.0f}

Negative GEX squeeze play. MMs chase price UP.
Target: ${call_wall:.0f} | Stop: ${put_wall:.0f}
Best with 0-5 DTE""",
                        'reasoning': f"Negative GEX (${net_gex/1e9:.1f}B) creates upside squeeze. {distance_to_flip:.1f}% from flip."
                    })

                # 7. LONG STRADDLE (High volatility expected)
                if net_gex < -2e9:
                    atm_strike = round_strike(spot_price)

                    confidence = 0.55
                    if net_gex < -3e9:
                        confidence += 0.10

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'LONG_STRADDLE',
                        'confidence': min(confidence, 0.70),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': None,
                        'stop_price': None,
                        'risk_reward': 3.0,
                        'expected_move': '5%+ either direction',
                        'win_rate': 0.55,
                        'money_making_plan': f"""BUY {atm_strike:.0f} CALL + BUY {atm_strike:.0f} PUT

Extreme negative GEX = big move coming
Exit at either wall: ${call_wall:.0f} or ${put_wall:.0f}
Best with 0-7 DTE, before major events""",
                        'reasoning': f"Extreme negative GEX (${net_gex/1e9:.1f}B). Expect large move."
                    })

                # ALWAYS INCLUDE: Fallback strategy if nothing else fits
                if len(symbol_setups) == 0:
                    # Default to a simple directional play based on GEX
                    if net_gex < 0:
                        # Bullish fallback
                        buy_strike = round_strike(spot_price)
                        sell_strike = round_strike(buy_strike + spread_width)

                        symbol_setups.append({
                            'symbol': symbol,
                            'strategy': 'BULLISH_CALL_SPREAD',
                            'confidence': 0.55,
                            'net_gex': net_gex,
                            'spot_price': spot_price,
                            'flip_point': flip_point,
                            'call_wall': call_wall,
                            'put_wall': put_wall,
                            'entry_price': buy_strike,
                            'target_price': call_wall,
                            'stop_price': put_wall,
                            'risk_reward': 2.0,
                            'expected_move': '1-3% up',
                            'win_rate': 0.55,
                            'money_making_plan': f"""BUY {buy_strike:.0f} CALL / SELL {sell_strike:.0f} CALL

Fallback bullish play. Target: ${call_wall:.0f}""",
                            'reasoning': f"Negative GEX suggests bullish bias."
                        })
                    else:
                        # Range-bound fallback
                        call_short = round_strike(call_wall)
                        call_long = round_strike(call_short + spread_width)
                        put_short = round_strike(put_wall)
                        put_long = round_strike(put_short - spread_width)

                        symbol_setups.append({
                            'symbol': symbol,
                            'strategy': 'IRON_CONDOR',
                            'confidence': 0.60,
                            'net_gex': net_gex,
                            'spot_price': spot_price,
                            'flip_point': flip_point,
                            'call_wall': call_wall,
                            'put_wall': put_wall,
                            'entry_price': spot_price,
                            'target_price': spot_price,
                            'stop_price': None,
                            'risk_reward': 0.3,
                            'expected_move': 'Range bound',
                            'win_rate': 0.60,
                            'money_making_plan': f"""SELL {call_short:.0f}/{call_long:.0f} CALL SPREAD + {put_short:.0f}/{put_long:.0f} PUT SPREAD

Fallback range play. Positive GEX suggests range-bound action.""",
                            'reasoning': f"Positive GEX (${net_gex/1e9:.1f}B) suggests range trading."
                        })

                # Add ALL strategies above confidence threshold (65%)
                MIN_CONFIDENCE = 0.65

                if symbol_setups:
                    # Filter for strategies meeting minimum confidence
                    viable_setups = [s for s in symbol_setups if s['confidence'] >= MIN_CONFIDENCE]

                    if viable_setups:
                        # Return ALL viable strategies (not just the best one)
                        results.extend(viable_setups)
                    else:
                        # If nothing meets threshold, return the best strategy anyway
                        best_setup = max(symbol_setups, key=lambda x: x['confidence'])
                        results.append(best_setup)

            except Exception as e:
                print(f"❌ Error scanning {symbol}: {e}")
                # Continue with next symbol - don't let one failure stop the whole scan
                continue

        # Save scan to database
        scan_duration = time.time() - scan_start

        # Log scan completion
        print(f"✅ Scanner completed: {len(results)} strategies found across {len(symbols)} symbols in {scan_duration:.1f}s")

        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO scanner_runs (id, symbols_scanned, total_symbols, opportunities_found, scan_duration_seconds)
            VALUES (?, ?, ?, ?, ?)
        """, (scan_id, ','.join(symbols), len(symbols), len(results), scan_duration))

        # Save each result
        for result in results:
            c.execute("""
                INSERT INTO scanner_results (
                    scan_id, symbol, strategy, confidence, net_gex, spot_price,
                    flip_point, call_wall, put_wall, entry_price, target_price,
                    stop_price, risk_reward, expected_move, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id, result['symbol'], result['strategy'], result['confidence'],
                result['net_gex'], result['spot_price'], result['flip_point'],
                result['call_wall'], result['put_wall'], result['entry_price'],
                result['target_price'], result.get('stop_price'), result['risk_reward'],
                result['expected_move'], result['reasoning']
            ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "scan_id": scan_id,
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(symbols),
            "opportunities_found": len(results),
            "scan_duration_seconds": scan_duration,
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

🎯 AI-GENERATED TRADE SETUP - {setup_type}

1. **THE EXACT TRADE** (Copy This):
   - BUY {option_symbol} (expires in 0-3 DTE)
   - Cost: ${actual_cost:.0f} ({position_size} contracts @ ${option_cost:.2f} each)
   - Target: ${potential_profit:.0f} (+{(potential_profit/actual_cost*100):.0f}%)
   - Win Rate: {confidence*100:.0f}%
   - Hold: {hold_period}

2. **MARKET CONTEXT** (Why Now):
   - {symbol} at ${spot_price:.2f}
   - Net GEX: ${net_gex/1e9:.1f}B ({  'NEGATIVE - MMs forced to hedge' if net_gex < 0 else 'POSITIVE - MMs stabilizing'})
   - Flip Point: ${flip_point:.2f} ({'ABOVE' if spot_price > flip_point else 'BELOW'} current price)
   - Call Wall: ${call_wall:.2f} | Put Wall: ${put_wall:.2f}

3. **WHY THIS WORKS**:
   - {catalyst}
   - {regime_info.get('description', 'Market regime favorable for this setup') if regime_info else 'Market conditions favor this setup'}

4. **ENTRY CRITERIA** (When to Buy):
   - IMMEDIATE: Market is in optimal regime NOW
   - Confirmation: Price action respecting ${flip_point:.2f} flip point
   - Best execution: First 30 min after market open
   - Strike: {option_symbol}

4. **EXIT STRATEGY** (How to Take Profits):
   - Target 1: ${(entry_price + (target_price-entry_price)*0.5):.2f} - Take 50% off here
   - Target 2: ${target_price:.2f} - Take final 50% off
   - STOP LOSS: ${stop_price:.2f} - NO EXCEPTIONS, cut losses fast
   - Time Stop: Exit EOD if no movement (avoid overnight risk)
   - Expected R:R: {risk_reward:.1f}:1

5. **WHY THIS WORKS** (The Edge):
   - {catalyst}
   - Historical Win Rate: {confidence*100:.0f}% in this regime
   - MM Hedging Flow: {'Buying pressure above flip' if net_gex < 0 and spot_price < flip_point else 'Selling pressure' if net_gex < 0 else 'Range compression'}
   - Key Level: {'Break above flip triggers squeeze' if net_gex < 0 and spot_price < flip_point else 'Walls contain movement' if net_gex > 0 else 'Premium decay favorable'}

⏰ TIMING: Execute this setup within the next 2 hours for optimal edge.
💰 PROFIT POTENTIAL: ${max_risk * risk_reward:.2f} on ${max_risk:.2f} risk ({risk_reward:.1f}:1)
"""

            setup = {
                'symbol': symbol,
                'setup_type': setup_type,
                'confidence': confidence,
                'win_rate': confidence,  # ✅ Include win_rate from STRATEGIES (same as confidence)
                'expected_risk_reward': expected_risk_reward,  # ✅ From STRATEGIES config
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_price': stop_price,
                'risk_reward': risk_reward,
                'position_size': position_size,
                'max_risk_dollars': max_risk,
                'time_horizon': '0-3 DTE',
                'best_days': strategy_config['best_days'],  # ✅ From STRATEGIES
                'entry_rule': strategy_config['entry'],  # ✅ From STRATEGIES
                'exit_rule': strategy_config['exit'],  # ✅ From STRATEGIES
                'catalyst': catalyst,
                'money_making_plan': money_making_plan,
                'market_data': {
                    'net_gex': net_gex,
                    'spot_price': spot_price,
                    'flip_point': flip_point,
                    'call_wall': call_wall,
                    'put_wall': put_wall
                },
                # ✅ NEW: Regime information
                'regime': regime_info if regime_info else {
                    'primary_type': 'NEUTRAL',
                    'confidence': 50,
                    'description': 'Standard market conditions',
                    'trade_direction': 'DIRECTIONAL',
                    'risk_level': 'MEDIUM'
                },
                # ✅ NEW: Specific option details
                'option_details': {
                    'option_type': option_type,
                    'strike_price': strike_price if strike_price else entry_price,
                    'option_symbol': option_symbol,
                    'option_cost': option_cost,
                    'bid': option_details.get('bid', 0) if option_details else 0,
                    'ask': option_details.get('ask', 0) if option_details else 0,
                    'volume': option_details.get('volume', 0) if option_details else 0,
                    'open_interest': option_details.get('openInterest', 0) if option_details else 0
                },
                # ✅ NEW: Greeks
                'greeks': option_greeks,
                # ✅ NEW: Cost and profit calculations
                'actual_cost': actual_cost,
                'potential_profit': potential_profit,
                'hold_period': hold_period,
                'generated_at': datetime.now().isoformat()
            }

            setups.append(setup)

        # Filter to only show setups with >50% win rate (evidence-based threshold)
        filtered_setups = [s for s in setups if s['win_rate'] >= 0.50]

        # Sort by win_rate (highest first) - Iron Condor (72%) should be highlighted
        sorted_setups = sorted(filtered_setups, key=lambda x: x['win_rate'], reverse=True)

        return {
            "success": True,
            "setups": sorted_setups,  # ✅ Sorted by win rate, filtered to >50%
            "total_setups_found": len(setups),
            "high_probability_setups": len(sorted_setups),  # Count of >50% setups
            "account_size": account_size,
            "risk_pct": risk_pct,
            "max_risk_per_trade": max_risk,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
# Position Sizing Calculator - Kelly Criterion
# ============================================================================

@app.post("/api/position-sizing/calculate")
async def calculate_position_size(request: dict):
    """
    Calculate optimal position size using Kelly Criterion
    Request body:
    {
        "account_size": 50000,
        "win_rate": 0.65,         // 65%
        "avg_win": 300,           // Average win in $
        "avg_loss": 150,          // Average loss in $
        "current_price": 580,     // Stock/option price
        "risk_per_trade_pct": 2.0 // Max risk as % of account
    }
    """
    try:
        account_size = request.get('account_size', 50000)
        win_rate = request.get('win_rate', 0.65)
        avg_win = request.get('avg_win', 300)
        avg_loss = request.get('avg_loss', 150)
        current_price = request.get('current_price', 100)
        risk_per_trade_pct = request.get('risk_per_trade_pct', 2.0)

        # Validate inputs
        if not (0 < win_rate < 1):
            raise HTTPException(status_code=400, detail="Win rate must be between 0 and 1")

        # Calculate Kelly Criterion
        # Kelly % = W - [(1 - W) / R]
        # Where: W = win rate, R = avg win / avg loss (reward-to-risk ratio)
        reward_to_risk = avg_win / avg_loss if avg_loss > 0 else 1
        kelly_pct = win_rate - ((1 - win_rate) / reward_to_risk)

        # Kelly can be negative (don't take the bet) or > 100% (very aggressive)
        # We cap it at reasonable levels
        kelly_pct_capped = max(0, min(kelly_pct, 0.25))  # Cap at 25% of account

        # Calculate position sizes
        max_risk_dollars = account_size * (risk_per_trade_pct / 100)
        kelly_position_dollars = account_size * kelly_pct_capped
        kelly_contracts = int(kelly_position_dollars / (current_price * 100)) if current_price > 0 else 0

        # Conservative position (half Kelly)
        half_kelly_pct = kelly_pct_capped / 2
        half_kelly_position_dollars = account_size * half_kelly_pct
        half_kelly_contracts = int(half_kelly_position_dollars / (current_price * 100)) if current_price > 0 else 0

        # Fixed risk position
        fixed_risk_contracts = int(max_risk_dollars / (current_price * 100)) if current_price > 0 else 0

        # Calculate expected value
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        expected_value_pct = (expected_value / avg_loss * 100) if avg_loss > 0 else 0

        # Generate money-making guide
        recommendation = "FULL KELLY" if kelly_pct_capped > 0.15 else "HALF KELLY" if kelly_pct_capped > 0.08 else "FIXED RISK"

        money_making_guide = f"""
💰 POSITION SIZING GUIDE - HOW TO SIZE YOUR TRADES

═══════════════════════════════════════════════════════════════

📊 YOUR STATS:
   - Account Size: ${account_size:,.2f}
   - Win Rate: {win_rate*100:.1f}%
   - Average Win: ${avg_win:.2f}
   - Average Loss: ${avg_loss:.2f}
   - Reward:Risk Ratio: {reward_to_risk:.2f}:1
   - Expected Value per Trade: ${expected_value:.2f} ({expected_value_pct:+.1f}%)

═══════════════════════════════════════════════════════════════

🎯 KELLY CRITERION ANALYSIS:

   Raw Kelly %: {kelly_pct*100:.1f}% of account
   {'⚠️ This is AGGRESSIVE - we cap at 25%' if kelly_pct > 0.25 else '✅ Within reasonable limits'}

   RECOMMENDATION: {recommendation}

═══════════════════════════════════════════════════════════════

💡 THREE POSITION SIZING STRATEGIES:

1. 🔥 FULL KELLY (Aggressive - Max Growth)
   ├─ Position Size: ${kelly_position_dollars:,.2f} ({kelly_pct_capped*100:.1f}% of account)
   ├─ Contracts: {kelly_contracts} contracts
   ├─ Risk per Trade: ${kelly_position_dollars:,.2f}
   └─ Use When: High confidence, proven edge, good win rate >65%

2. ✅ HALF KELLY (Recommended - Balanced)
   ├─ Position Size: ${half_kelly_position_dollars:,.2f} ({half_kelly_pct*100:.1f}% of account)
   ├─ Contracts: {half_kelly_contracts} contracts
   ├─ Risk per Trade: ${half_kelly_position_dollars:,.2f}
   └─ Use When: Standard setups, normal market conditions

3. 🛡️ FIXED RISK (Conservative - Capital Preservation)
   ├─ Position Size: ${max_risk_dollars:,.2f} ({risk_per_trade_pct:.1f}% of account)
   ├─ Contracts: {fixed_risk_contracts} contracts
   ├─ Risk per Trade: ${max_risk_dollars:,.2f}
   └─ Use When: Learning, uncertain conditions, or small account

═══════════════════════════════════════════════════════════════

📈 EXPECTED OUTCOMES (per 100 trades):

   Full Kelly Strategy:
   - Wins: {int(win_rate*100)} @ ${avg_win:.2f} = ${win_rate*100*avg_win:,.2f}
   - Losses: {int((1-win_rate)*100)} @ ${avg_loss:.2f} = ${(1-win_rate)*100*avg_loss:,.2f}
   - Net Expected: ${expected_value*100:,.2f}
   - ROI: {expected_value_pct*100:.1f}%

   Account Growth Projection:
   - Starting: ${account_size:,.2f}
   - After 100 trades: ${account_size + (expected_value*100):,.2f}
   - Gain: {((expected_value*100)/account_size)*100:+.1f}%

═══════════════════════════════════════════════════════════════

⚠️ RISK MANAGEMENT RULES:

1. NEVER risk more than {risk_per_trade_pct}% on a single trade
2. STOP trading after 3 consecutive losses (reevaluate edge)
3. Reduce position size by 50% during drawdowns >10%
4. Keep win rate above {win_rate*100-10:.0f}% or adjust strategy
5. Track EVERY trade to validate your win rate & R:R assumptions

═══════════════════════════════════════════════════════════════

🎓 HOW TO USE THIS:

1. Start with HALF KELLY until you prove your edge
2. Track actual win rate and R:R over 30+ trades
3. Adjust inputs monthly based on real performance
4. If actual results differ by >10%, recalculate immediately
5. Scale up position size only after consistent profitability

{'✅ POSITIVE EDGE: Your system has positive expectancy - keep trading!' if expected_value > 0 else '❌ NEGATIVE EDGE: DO NOT TRADE - fix strategy first!'}

═══════════════════════════════════════════════════════════════
"""

        return {
            "success": True,
            "calculations": {
                "kelly_percentage": kelly_pct,
                "kelly_percentage_capped": kelly_pct_capped,
                "reward_to_risk_ratio": reward_to_risk,
                "expected_value": expected_value,
                "expected_value_pct": expected_value_pct,
                "recommendation": recommendation
            },
            "positions": {
                "full_kelly": {
                    "dollars": kelly_position_dollars,
                    "contracts": kelly_contracts,
                    "percentage": kelly_pct_capped * 100
                },
                "half_kelly": {
                    "dollars": half_kelly_position_dollars,
                    "contracts": half_kelly_contracts,
                    "percentage": half_kelly_pct * 100
                },
                "fixed_risk": {
                    "dollars": max_risk_dollars,
                    "contracts": fixed_risk_contracts,
                    "percentage": risk_per_trade_pct
                }
            },
            "money_making_guide": money_making_guide,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PSYCHOLOGY TRAP DETECTION ENDPOINTS
# ============================================================================

from psychology_trap_detector import (
    analyze_current_market_complete,
    save_regime_signal_to_db,
    calculate_mtf_rsi_score
)
from psychology_trading_guide import get_trading_guide
from psychology_performance import performance_tracker
from psychology_notifications import notification_manager

# Import autonomous trader routes
from backend.autonomous_routes import router as autonomous_router

# Import AI intelligence enhancement routes
from backend.ai_intelligence_routes import router as ai_intelligence_router

# Include autonomous trader routes
app.include_router(autonomous_router)

# Include AI intelligence enhancement routes
app.include_router(ai_intelligence_router)

# ==============================================================================
# POLYGON.IO PRICE DATA CACHING - Psychology page fetches once per day
# ==============================================================================
_polygon_price_cache = {}
_polygon_price_cache_ttl = 86400  # 24 hours cache (psychology updates once per day)

def get_cached_price_data(symbol: str, current_price: float):
    """
    Get price data for symbol with caching using Polygon.io API
    Cache TTL: 24 hours (86400 seconds)

    Psychology page design: Fetch once per day, manual refresh only

    This function makes 5 Polygon.io API calls:
    - 90d daily data
    - 30d 4-hour data
    - 14d hourly data
    - 7d 15-minute data
    - 3d 5-minute data

    With 24h caching: 5 API calls per day (only on first load or manual refresh)
    """
    cache_key = f"price_data_{symbol}"
    now = datetime.now()

    # Check if we have cached data that's still fresh
    if cache_key in _polygon_price_cache:
        cached_data, cache_time = _polygon_price_cache[cache_key]
        age_seconds = (now - cache_time).total_seconds()

        if age_seconds < _polygon_price_cache_ttl:
            print(f"✅ Using cached price data (age: {age_seconds:.0f}s)")
            return cached_data
        else:
            print(f"⏰ Cache expired (age: {age_seconds:.0f}s > {_polygon_price_cache_ttl}s)")

    # Cache miss or expired - fetch fresh data from Polygon.io
    print(f"🔄 Fetching fresh price data from Polygon.io (5 API calls)")

    polygon_key = os.getenv("POLYGON_API_KEY")
    if not polygon_key:
        print(f"❌ No POLYGON_API_KEY configured in environment")
        print(f"❌ Available env vars: {', '.join([k for k in os.environ.keys() if 'POLYGON' in k or 'API' in k])}")
        raise HTTPException(
            status_code=503,
            detail=f"Polygon.io API key not configured. Cannot fetch price data for psychology analysis."
        )

    print(f"✅ POLYGON_API_KEY is set (length: {len(polygon_key)} chars)")
    print(f"✅ API key starts with: {polygon_key[:8]}...")

    try:
        import pandas as pd

        def fetch_polygon_bars(symbol, multiplier, timespan, days_back):
            """Fetch price bars from Polygon.io"""
            try:
                to_date = datetime.now().strftime('%Y-%m-%d')
                from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

                url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
                params = {"apiKey": polygon_key, "sort": "asc", "limit": 50000}

                print(f"    🌐 Calling Polygon.io: {url}")
                print(f"    📅 Date range: {from_date} to {to_date}")

                response = requests.get(url, params=params, timeout=10)

                print(f"    📡 Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '')
                    results_count = data.get('resultsCount', 0)

                    print(f"    📊 Polygon status: {status}")
                    print(f"    📊 Results count: {results_count}")

                    if status in ['OK', 'DELAYED'] and data.get('results'):
                        results = data['results']
                        print(f"    ✅ Got {len(results)} bars")
                        return [
                            {
                                'close': bar['c'],
                                'high': bar['h'],
                                'low': bar['l'],
                                'volume': bar['v']
                            }
                            for bar in results
                        ]
                    else:
                        print(f"    ⚠️ Polygon.io status: {status}, results: {results_count}")
                        print(f"    ⚠️ Full response: {data}")
                        return []
                elif response.status_code == 401:
                    print(f"    ❌ Polygon.io 401 Unauthorized - API key is invalid")
                    print(f"    ❌ Response: {response.text}")
                    return []
                elif response.status_code == 403:
                    print(f"    ❌ Polygon.io 403 Forbidden - API key may not have access to this data")
                    print(f"    ❌ Response: {response.text}")
                    return []
                elif response.status_code == 429:
                    print(f"    ❌ Polygon.io 429 Rate Limit - too many requests")
                    print(f"    ❌ Response: {response.text}")
                    return []
                else:
                    print(f"    ⚠️ Polygon.io HTTP {response.status_code}")
                    print(f"    ⚠️ Response: {response.text[:500]}")
                    return []
            except Exception as e:
                print(f"    ❌ Polygon.io error: {e}")
                import traceback
                traceback.print_exc()
                return []

        price_data = {}

        # Daily data (90 days for RSI calculation)
        print(f"  🔄 Fetching 1d data...")
        price_data['1d'] = fetch_polygon_bars(symbol, 1, 'day', 90)
        print(f"  📊 1d data: {len(price_data['1d'])} bars")

        # 4-hour data (30 days)
        print(f"  🔄 Fetching 4h data...")
        price_data['4h'] = fetch_polygon_bars(symbol, 4, 'hour', 30)
        print(f"  📊 4h data: {len(price_data['4h'])} bars")

        # 1-hour data (14 days)
        print(f"  🔄 Fetching 1h data...")
        price_data['1h'] = fetch_polygon_bars(symbol, 1, 'hour', 14)
        print(f"  📊 1h data: {len(price_data['1h'])} bars")

        # 15-minute data (7 days)
        print(f"  🔄 Fetching 15m data...")
        price_data['15m'] = fetch_polygon_bars(symbol, 15, 'minute', 7)
        print(f"  📊 15m data: {len(price_data['15m'])} bars")

        # 5-minute data (3 days)
        print(f"  🔄 Fetching 5m data...")
        price_data['5m'] = fetch_polygon_bars(symbol, 5, 'minute', 3)
        print(f"  📊 5m data: {len(price_data['5m'])} bars")

        # CRITICAL: Validate that we got actual data
        if len(price_data['1d']) == 0:
            print(f"❌ Polygon.io returned EMPTY data for {symbol}")
            print(f"   This usually means API key is invalid or rate limit exceeded")
            raise ValueError(f"Polygon.io returned no data for {symbol}. Check API key and rate limits.")

        # Cache the result only if we have valid data
        _polygon_price_cache[cache_key] = (price_data, now)
        print(f"✅ Cached fresh price data for {_polygon_price_cache_ttl}s (24 hours)")

        return price_data

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # NO FALLBACK - Never use mock data
        print(f"❌ Could not fetch price data from Polygon.io: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch price data for {symbol}. Polygon.io API error: {str(e)}"
        )

@app.get("/api/psychology/current-regime")
async def get_current_regime(symbol: str = "SPY"):
    """
    Get current psychology trap regime analysis

    Returns complete analysis with:
    - Multi-timeframe RSI
    - Current gamma walls
    - Gamma expiration timeline
    - Forward GEX magnets
    - Regime detection with psychology traps
    """
    try:
        print(f"\n{'='*60}")
        print(f"Psychology Trap Detection - Starting analysis for {symbol}")
        print(f"{'='*60}\n")

        # Get current price and gamma data using get_net_gamma
        gex_data = api_client.get_net_gamma(symbol)

        print(f"1. GEX Data fetched: {type(gex_data)}")

        # Try to use cached data from database if live API fails
        if not gex_data or 'error' in gex_data:
            error_type = gex_data.get('error', 'unknown') if gex_data else 'no_data'
            print(f"⚠️ Live GEX API unavailable: {error_type}")
            print("📊 Attempting to use cached data from database...")

            # Try to get the most recent cached regime data
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT spy_price, net_gamma, primary_regime_type, secondary_regime_type,
                           confidence_score, trade_direction, risk_level, description,
                           rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d, timestamp
                    FROM regime_signals
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                cached_row = cursor.fetchone()
                conn.close()

                if cached_row:
                    print(f"✅ Using cached data from {cached_row[13]}")
                    # Build response from cached data
                    cached_response = {
                        "analysis": {
                            "timestamp": str(cached_row[13]),
                            "spy_price": cached_row[0] or 590.0,
                            "regime": {
                                "primary_type": cached_row[2] or "NEUTRAL",
                                "secondary_type": cached_row[3],
                                "confidence": cached_row[4] or 0.7,
                                "description": cached_row[7] or "Cached analysis from database",
                                "detailed_explanation": f"Data cached at {cached_row[13]}. Live API unavailable.",
                                "trade_direction": cached_row[5] or "NEUTRAL",
                                "risk_level": cached_row[6] or "MEDIUM",
                                "timeline": None,
                                "price_targets": {},
                                "psychology_trap": None,
                                "supporting_factors": ["Using cached data - live API unavailable"]
                            },
                            "rsi_analysis": {
                                "score": 50,
                                "individual_rsi": {
                                    "5m": cached_row[8],
                                    "15m": cached_row[9],
                                    "1h": cached_row[10],
                                    "4h": cached_row[11],
                                    "1d": cached_row[12]
                                },
                                "aligned_count": {"overbought": 0, "oversold": 0, "extreme_overbought": 0, "extreme_oversold": 0},
                                "coiling_detected": False
                            },
                            "current_walls": {"call_wall": None, "put_wall": None},
                            "expiration_analysis": {},
                            "forward_gex": {},
                            "volume_ratio": 1.0,
                            "alert_level": {"level": "info", "reason": "Using cached data"}
                        },
                        "market_status": {
                            "is_open": False,
                            "timestamp": str(datetime.now()),
                            "status_text": "Using cached data - API unavailable",
                            "data_age_minutes": 0
                        },
                        "trading_guide": None,
                        "ai_recommendation": None,
                        "historical_comparison": None,
                        "backtest_stats": None,
                        "_cached": True,
                        "_cache_time": str(cached_row[13])
                    }
                    return JSONResponse(cached_response)
            except Exception as cache_err:
                print(f"❌ Failed to retrieve cached data: {cache_err}")

            # No cached data available - return proper error
            if error_type == 'rate_limit':
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate Limit Exceeded",
                        "message": "Trading Volatility API rate limit hit. Circuit breaker is active.",
                        "solution": "Wait 30-60 seconds and try again. System manages rate limits automatically."
                    }
                )
            elif error_type == 'api_key':
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Service Unavailable",
                        "message": "Trading Volatility API key not configured.",
                        "solution": "Configure 'tv_username' environment variable with your Trading Volatility API key"
                    }
                )
            else:
                # Generic error
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Service Unavailable",
                        "message": f"Failed to fetch GEX data: {error_type}",
                        "solution": "Check API configuration and network connectivity"
                    }
                )

        current_price = gex_data.get('spot_price', 0)
        print(f"2. Current price: ${current_price}")

        # Get price data with caching (prevents excessive API calls)
        price_data = get_cached_price_data(symbol, current_price)
        print(f"3. Price data prepared with {len(price_data)} timeframes")

        # Calculate volume ratio (using daily data)
        if len(price_data['1d']) >= 20:
            recent_volume = price_data['1d'][-1]['volume']
            avg_volume = sum(d['volume'] for d in price_data['1d'][-20:]) / 20
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        else:
            volume_ratio = 1.0

        # Format gamma data for psychology trap detector
        # Need to structure with expirations
        gamma_data_formatted = {
            'net_gamma': gex_data.get('net_gex', 0),
            'expirations': []
        }

        # Parse expiration data from gex_data
        # The TradingVolatility API returns strikes by expiration
        if 'expirations' in gex_data:
            for exp_date_str, exp_data in gex_data['expirations'].items():
                try:
                    # Parse expiration date
                    exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d')
                    dte = (exp_date - datetime.now()).days

                    # Determine expiration type
                    if dte == 0:
                        exp_type = '0dte'
                    elif dte <= 7:
                        exp_type = 'weekly'
                    else:
                        # Check if it's monthly (3rd Friday)
                        # For simplicity, treat all > 7 DTE as monthly
                        exp_type = 'monthly'

                    call_strikes = []
                    put_strikes = []

                    if 'strikes' in exp_data:
                        for strike_data in exp_data['strikes']:
                            strike = strike_data.get('strike', 0)

                            if 'call_gamma' in strike_data:
                                call_strikes.append({
                                    'strike': strike,
                                    'gamma_exposure': strike_data['call_gamma'],
                                    'open_interest': strike_data.get('call_oi', 0)
                                })

                            if 'put_gamma' in strike_data:
                                put_strikes.append({
                                    'strike': strike,
                                    'gamma_exposure': strike_data['put_gamma'],
                                    'open_interest': strike_data.get('put_oi', 0)
                                })

                    gamma_data_formatted['expirations'].append({
                        'expiration_date': exp_date,
                        'dte': dte,
                        'expiration_type': exp_type,
                        'call_strikes': call_strikes,
                        'put_strikes': put_strikes
                    })

                except Exception as e:
                    print(f"Error parsing expiration {exp_date_str}: {e}")
                    continue
        else:
            # Fallback: create single expiration from call/put walls
            call_wall = gex_data.get('call_wall', current_price * 1.02)
            put_wall = gex_data.get('put_wall', current_price * 0.98)

            gamma_data_formatted['expirations'] = [{
                'expiration_date': datetime.now() + timedelta(days=7),
                'dte': 7,
                'expiration_type': 'weekly',
                'call_strikes': [{
                    'strike': call_wall,
                    'gamma_exposure': gex_data.get('net_gex', 0) / 2,
                    'open_interest': 1000
                }],
                'put_strikes': [{
                    'strike': put_wall,
                    'gamma_exposure': gex_data.get('net_gex', 0) / 2,
                    'open_interest': 1000
                }]
            }]

        print(f"4. Gamma data formatted with {len(gamma_data_formatted.get('expirations', []))} expirations")
        print(f"5. Volume ratio: {volume_ratio:.2f}")
        print(f"\nCalling analyze_current_market_complete...")

        # Run complete psychology trap analysis
        try:
            print(f"  DEBUG: Calling analyze_current_market_complete with:")
            print(f"    - current_price: {current_price}")
            print(f"    - price_data keys: {list(price_data.keys())}")
            print(f"    - price_data['1d'] length: {len(price_data.get('1d', []))}")
            print(f"    - gamma_data keys: {list(gamma_data_formatted.keys())}")
            print(f"    - volume_ratio: {volume_ratio}")

            analysis = analyze_current_market_complete(
                current_price=current_price,
                price_data=price_data,
                gamma_data=gamma_data_formatted,
                volume_ratio=volume_ratio
            )
            print(f"✅ Analysis complete!")
        except Exception as analysis_error:
            print(f"❌ Error in analyze_current_market_complete:")
            print(f"❌ Error type: {type(analysis_error).__name__}")
            print(f"❌ Error message: {str(analysis_error)}")
            import traceback
            import sys
            traceback.print_exc()
            sys.stdout.flush()  # Force flush to ensure error appears in logs

            # Re-raise with more context
            raise HTTPException(
                status_code=500,
                detail=f"Psychology analysis failed: {type(analysis_error).__name__}: {str(analysis_error)}"
            )

        # Save to database
        try:
            signal_id = save_regime_signal_to_db(analysis)
            analysis['signal_id'] = signal_id
            print(f"6. Saved to database with ID: {signal_id}")
        except Exception as e:
            print(f"⚠️  Warning: Could not save regime signal: {e}")

        print(f"\n{'='*60}")
        print(f"Psychology Trap Detection - Analysis Complete")
        print(f"{'='*60}\n")

        # Generate trading guide
        trading_guide = get_trading_guide(
            regime_type=analysis['regime']['primary_type'],
            current_price=current_price,
            regime_data=analysis['regime']
        )

        # Generate AI-powered trade recommendation
        try:
            from ai_trade_recommendations import get_ai_recommendation
            ai_recommendation = get_ai_recommendation(symbol, analysis)
            print(f"✅ AI recommendation generated")
        except Exception as ai_error:
            print(f"⚠️  AI recommendation failed: {ai_error}")
            ai_recommendation = None

        # Save daily gamma snapshot and get historical comparison
        historical_comparison = None
        backtest_stats = None
        try:
            from historical_tracking import save_daily_gamma_snapshot, get_historical_comparison, calculate_regime_backtest_statistics

            # Save snapshot for historical tracking (non-blocking)
            try:
                save_daily_gamma_snapshot(symbol, gamma_data_formatted, current_price)
            except Exception as snap_err:
                print(f"⚠️  Snapshot save failed (non-critical): {snap_err}")

            # Get historical comparison (non-blocking)
            try:
                current_net_gamma = gamma_data_formatted.get('net_gamma', 0)
                historical_comparison = get_historical_comparison(symbol, current_net_gamma)
            except Exception as comp_err:
                print(f"⚠️  Historical comparison failed (non-critical): {comp_err}")

            # Get backtest statistics for current regime (non-blocking)
            try:
                regime_type = analysis['regime']['primary_type']
                backtest_stats = calculate_regime_backtest_statistics(regime_type)
            except Exception as stats_err:
                print(f"⚠️  Backtest stats failed (non-critical): {stats_err}")

            if historical_comparison or backtest_stats:
                print(f"✅ Historical tracking updated")
        except ImportError as import_err:
            print(f"⚠️  Historical tracking not available (module not found): {import_err}")
        except Exception as hist_error:
            print(f"⚠️  Historical tracking failed: {hist_error}")
            import traceback
            traceback.print_exc()

        # Add market status and metadata
        import pytz
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        market_open = now.weekday() < 5 and 9 <= now.hour < 16  # Simple check

        market_status = {
            'is_open': market_open,
            'timestamp': now.isoformat(),
            'market_time': now.strftime('%I:%M %p ET'),
            'status_text': 'OPEN' if market_open else 'CLOSED',
            'data_age_minutes': 0 if market_open else int((now.hour - 16) * 60) if now.hour >= 16 else 0
        }

        # Convert numpy types to Python native types for JSON serialization
        def convert_numpy_types(obj):
            """Recursively convert numpy types to Python native types"""
            import numpy as np
            if isinstance(obj, dict):
                return {k: convert_numpy_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return obj

        # Convert all data before returning
        analysis = convert_numpy_types(analysis)
        trading_guide = convert_numpy_types(trading_guide)
        if ai_recommendation:
            ai_recommendation = convert_numpy_types(ai_recommendation)
        if historical_comparison:
            historical_comparison = convert_numpy_types(historical_comparison)
        if backtest_stats:
            backtest_stats = convert_numpy_types(backtest_stats)

        return {
            "success": True,
            "symbol": symbol,
            "analysis": analysis,
            "trading_guide": trading_guide,
            "ai_recommendation": ai_recommendation,
            "market_status": market_status,
            "historical_comparison": historical_comparison,
            "backtest_stats": backtest_stats
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/api/psychology/history")
async def get_regime_history(limit: int = 50, regime_type: str = None):
    """
    Get historical regime signals

    Args:
        limit: Number of recent signals to return
        regime_type: Filter by specific regime type (optional)
    """
    try:
        
        conn = get_connection()
        c = conn.cursor()

        if regime_type:
            c.execute('''
                SELECT * FROM regime_signals
                WHERE primary_regime_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (regime_type, limit))
        else:
            c.execute('''
                SELECT * FROM regime_signals
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        signals = []
        for row in rows:
            signal = dict(zip(columns, row))
            signals.append(signal)

        conn.close()

        return {
            "success": True,
            "count": len(signals),
            "signals": signals
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/liberation-setups")
async def get_liberation_setups():
    """
    Get active liberation trade setups
    Returns walls that are about to expire and release price
    """
    try:
        
        conn = get_connection()
        c = conn.cursor()

        # Get recent signals with liberation setups
        c.execute('''
            SELECT * FROM regime_signals
            WHERE liberation_setup_detected = 1
            AND liberation_expiry_date >= date('now')
            ORDER BY liberation_expiry_date ASC
            LIMIT 10
        ''')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        setups = []
        for row in rows:
            setup = dict(zip(columns, row))
            setups.append(setup)

        conn.close()

        return {
            "success": True,
            "count": len(setups),
            "liberation_setups": setups
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/false-floors")
async def get_false_floors():
    """
    Get active false floor warnings
    Returns support levels that are temporary and will disappear
    """
    try:
        
        conn = get_connection()
        c = conn.cursor()

        # Get recent signals with false floor warnings
        c.execute('''
            SELECT * FROM regime_signals
            WHERE false_floor_detected = 1
            AND false_floor_expiry_date >= date('now')
            ORDER BY false_floor_expiry_date ASC
            LIMIT 10
        ''')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        floors = []
        for row in rows:
            floor = dict(zip(columns, row))
            floors.append(floor)

        conn.close()

        return {
            "success": True,
            "count": len(floors),
            "false_floors": floors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/statistics")
async def get_sucker_statistics():
    """
    Get statistics on how often newbie logic fails
    Shows historical success/failure rates for different scenarios

    Returns:
        {
            "success": bool,
            "count": int,
            "statistics": List[dict],
            "summary": {
                "total_scenarios": int,
                "avg_failure_rate": float,
                "most_dangerous_trap": str,
                "safest_fade": str
            }
        }
    """
    try:
        
        conn = get_connection()
        c = conn.cursor()

        # Get sucker statistics
        c.execute('SELECT * FROM sucker_statistics ORDER BY failure_rate DESC')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        stats = []
        for row in rows:
            stat = dict(zip(columns, row))
            stats.append(stat)

        conn.close()

        # Calculate summary statistics
        summary = {
            "total_scenarios": len(stats),
            "avg_failure_rate": 0,
            "most_dangerous_trap": "N/A",
            "safest_fade": "N/A"
        }

        if stats:
            # Average failure rate
            summary["avg_failure_rate"] = sum(s.get('failure_rate', 0) for s in stats) / len(stats)

            # Most dangerous trap (highest failure rate)
            most_dangerous = max(stats, key=lambda x: x.get('failure_rate', 0))
            summary["most_dangerous_trap"] = most_dangerous.get('scenario_type', 'N/A')

            # Safest fade (lowest failure rate)
            safest = min(stats, key=lambda x: x.get('failure_rate', 0))
            summary["safest_fade"] = safest.get('scenario_type', 'N/A')

        return {
            "success": True,
            "count": len(stats),
            "statistics": stats,
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/performance/overview")
async def get_performance_overview(days: int = 30):
    """
    Get overall performance metrics for psychology trap detection

    Args:
        days: Number of days to analyze (default 30)

    Returns:
        Overall metrics including total signals, win rate, avg confidence, etc.
    """
    try:
        metrics = performance_tracker.get_overview_metrics(days)
        return {
            "success": True,
            "metrics": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/performance/by-pattern")
async def get_pattern_performance(days: int = 90):
    """
    Get performance metrics for each pattern type

    Args:
        days: Number of days to analyze (default 90)

    Returns:
        List of pattern performance data with win rates, expectancy, etc.
    """
    try:
        patterns = performance_tracker.get_pattern_performance(days)
        return {
            "success": True,
            "count": len(patterns),
            "patterns": patterns
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/performance/signals")
async def get_historical_signals(limit: int = 100, pattern_type: str = None):
    """
    Get historical signals with full details and outcomes

    Args:
        limit: Maximum number of signals to return (default 100)
        pattern_type: Filter by specific pattern type (optional)

    Returns:
        List of historical signals with timestamps, patterns, outcomes, etc.
    """
    try:
        signals = performance_tracker.get_historical_signals(limit, pattern_type)
        return {
            "success": True,
            "count": len(signals),
            "signals": signals
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/performance/chart-data")
async def get_chart_data(days: int = 90):
    """
    Get time series data for performance charts

    Args:
        days: Number of days of data (default 90)

    Returns:
        Dict with daily_signals, win_rate_timeline, and pattern_timeline
    """
    try:
        chart_data = performance_tracker.get_chart_data(days)
        return {
            "success": True,
            "chart_data": chart_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/performance/vix-correlation")
async def get_vix_correlation(days: int = 90):
    """
    Analyze correlation between VIX levels and pattern performance

    Args:
        days: Number of days to analyze (default 90)

    Returns:
        Performance data by VIX level and spike status
    """
    try:
        correlation = performance_tracker.get_vix_correlation(days)
        return {
            "success": True,
            "correlation": correlation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/notifications/stream")
async def notification_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time notifications

    Streams critical psychology trap pattern alerts to connected clients.
    Critical patterns: GAMMA_SQUEEZE_CASCADE, FLIP_POINT_CRITICAL, CAPITULATION_CASCADE
    """
    async def event_generator():
        # Subscribe to notifications
        queue = await notification_manager.subscribe()

        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Notification stream connected'})}\n\n"

            # Stream notifications
            while True:
                try:
                    # Wait for notification with timeout
                    notification = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Send notification as SSE
                    yield f"data: {json.dumps(notification)}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive ping every 30 seconds
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            await notification_manager.unsubscribe(queue)
            raise
        except Exception as e:
            print(f"Error in notification stream: {e}")
            await notification_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )

@app.get("/api/psychology/notifications/history")
async def get_notification_history(limit: int = 50):
    """
    Get recent notification history

    Args:
        limit: Maximum number of notifications to return (default 50)

    Returns:
        List of recent notifications
    """
    try:
        history = notification_manager.get_notification_history(limit)
        return {
            "success": True,
            "count": len(history),
            "notifications": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/notifications/stats")
async def get_notification_stats():
    """
    Get notification statistics

    Returns:
        Stats including total notifications, critical count, active subscribers, etc.
    """
    try:
        stats = notification_manager.get_notification_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# PUSH NOTIFICATION ENDPOINTS (Browser Push API)
# ==============================================================================

@app.get("/api/psychology/rsi-analysis/{symbol}")
async def get_rsi_analysis(symbol: str = "SPY"):
    """
    Get multi-timeframe RSI analysis only using Polygon.io
    Useful for quick RSI checks without full regime analysis
    """
    try:
        # Get current price from GEX data
        gex_data = api_client.get_net_gamma(symbol)
        current_price = gex_data.get('spot_price', 0)

        # Use Polygon.io for price data (with caching)
        price_data = get_cached_price_data(symbol, current_price)

        # Calculate RSI
        rsi_analysis = calculate_mtf_rsi_score(price_data)

        return {
            "success": True,
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "rsi_analysis": rsi_analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/psychology/quick-check/{symbol}")
async def get_quick_psychology_check(symbol: str = "SPY"):
    """
    Quick psychology trap check for scanners using Polygon.io (lightweight version)
    Returns only regime type, confidence, and trade direction
    """
    try:
        # Get current price from GEX data
        gex_data = api_client.get_net_gamma(symbol)
        current_price = gex_data.get('spot_price', 0)

        # Use Polygon.io for price data (with caching)
        price_data = get_cached_price_data(symbol, current_price)

        # Calculate RSI only
        rsi_analysis = calculate_mtf_rsi_score(price_data)

        # Simple regime determination
        regime_type = 'NEUTRAL'
        confidence = 50
        trade_direction = 'wait'

        # Check for obvious extremes
        if rsi_analysis['aligned_count']['overbought'] >= 3:
            regime_type = 'OVERBOUGHT_EXTREME'
            confidence = 60 + rsi_analysis['aligned_count']['overbought'] * 5
            trade_direction = 'fade' if rsi_analysis['score'] > 70 else 'momentum'
        elif rsi_analysis['aligned_count']['oversold'] >= 3:
            regime_type = 'OVERSOLD_EXTREME'
            confidence = 60 + rsi_analysis['aligned_count']['oversold'] * 5
            trade_direction = 'bounce' if rsi_analysis['score'] < -70 else 'breakdown'

        return {
            "success": True,
            "symbol": symbol,
            "regime_type": regime_type,
            "confidence": confidence,
            "trade_direction": trade_direction,
            "rsi_score": rsi_analysis['score'],
            "overbought_tfs": rsi_analysis['aligned_count']['overbought'],
            "oversold_tfs": rsi_analysis['aligned_count']['oversold'],
            "current_price": float(current_price)
        }

    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "regime_type": "ERROR",
            "confidence": 0,
            "trade_direction": "wait",
            "error": str(e)
        }

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

# AlphaGEX Autonomous Trader - Auto-start on boot
@reboot {alphagex_dir}/auto_start_trader.sh

# AlphaGEX Autonomous Trader - Watchdog (checks every minute, restarts if crashed)
* * * * * {alphagex_dir}/trader_watchdog.sh
"""

        # Remove old entries if they exist (to avoid duplicates)
        lines = current_crontab.split('\n')
        filtered_lines = [l for l in lines if 'auto_start_trader.sh' not in l and 'trader_watchdog.sh' not in l]
        updated_crontab = '\n'.join(filtered_lines) + new_entries

        # Update crontab
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=updated_crontab.encode())

        if process.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to update crontab: {stderr.decode()}"
            }

        return {
            "success": True,
            "message": "Auto-start enabled successfully! Trader will start on boot and auto-restart if crashed.",
            "already_enabled": False
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

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
