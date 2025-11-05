"""
AlphaGEX FastAPI Backend
Main application entry point - Professional Options Intelligence Platform
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import existing AlphaGEX modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Import existing AlphaGEX logic (DO NOT MODIFY THESE)
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open

# Create FastAPI app
app = FastAPI(
    title="AlphaGEX API",
    description="Professional Options Intelligence Platform - Backend API",
    version="2.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# CORS Configuration - Allow frontend to connect
ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Local development
    "http://localhost:5173",  # Vite dev server
    "https://alphagex.vercel.app",  # Production frontend (update with actual URL)
    "https://*.vercel.app",  # All Vercel preview deployments
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize existing AlphaGEX components (singleton pattern)
api_client = TradingVolatilityAPI()
claude_ai = ClaudeIntelligence()
monte_carlo = MonteCarloEngine()
pricer = BlackScholesPricer()

# ============================================================================
# Health Check & Status Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "name": "AlphaGEX API",
        "version": "2.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    market_open = is_market_open()
    current_time_et = get_et_time()

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "market": {
            "open": market_open,
            "current_time_et": current_time_et.strftime("%Y-%m-%d %H:%M:%S %Z")
        },
        "services": {
            "api_client": "operational",
            "claude_ai": "operational",
            "database": "operational"  # Will update when PostgreSQL is connected
        }
    }

@app.get("/api/time")
async def get_time():
    """Get current market time and status"""
    et_time = get_et_time()
    ct_time = get_local_time('US/Central')
    market_open = is_market_open()

    return {
        "eastern_time": et_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "central_time": ct_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "market_open": market_open,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# GEX Data Endpoints
# ============================================================================

@app.get("/api/gex/{symbol}")
async def get_gex_data(symbol: str):
    """
    Get GEX (Gamma Exposure) data for a symbol

    Args:
        symbol: Stock symbol (e.g., SPY, QQQ, AAPL)

    Returns:
        GEX data including net_gex, spot_price, flip_point, levels, etc.
    """
    try:
        symbol = symbol.upper()

        # Use existing TradingVolatilityAPI (UNCHANGED)
        gex_data = api_client.get_net_gamma(symbol)

        if not gex_data or gex_data.get('error'):
            raise HTTPException(
                status_code=404,
                detail=f"GEX data not available for {symbol}"
            )

        return {
            "success": True,
            "symbol": symbol,
            "data": gex_data,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gex/{symbol}/levels")
async def get_gex_levels(symbol: str):
    """
    Get GEX support/resistance levels for a symbol

    Args:
        symbol: Stock symbol

    Returns:
        GEX levels (support, resistance, flip point, etc.)
    """
    try:
        symbol = symbol.upper()

        # Use existing API client
        levels = api_client.get_gex_levels(symbol)

        if not levels or levels.get('error'):
            raise HTTPException(
                status_code=404,
                detail=f"GEX levels not available for {symbol}"
            )

        return {
            "success": True,
            "symbol": symbol,
            "levels": levels,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Gamma Intelligence Endpoints
# ============================================================================

@app.get("/api/gamma/{symbol}/intelligence")
async def get_gamma_intelligence(symbol: str, vix: float = 0):
    """
    Get comprehensive gamma expiration intelligence (3 views)

    This is the CRITICAL endpoint that preserves ALL gamma analysis logic.
    NO MODIFICATIONS to calculation logic - only wrapping in API endpoint.

    Args:
        symbol: Stock symbol
        vix: Current VIX value (optional, for context-aware adjustments)

    Returns:
        3-view gamma intelligence:
        - View 1: Daily Impact (Today → Tomorrow)
        - View 2: Weekly Evolution (Monday → Friday)
        - View 3: Volatility Potential (Risk Calendar)
    """
    try:
        symbol = symbol.upper()

        # Use existing get_current_week_gamma_intelligence (UNCHANGED LOGIC)
        gamma_intel = api_client.get_current_week_gamma_intelligence(
            symbol,
            current_vix=vix
        )

        if not gamma_intel or not gamma_intel.get('success'):
            raise HTTPException(
                status_code=404,
                detail=f"Gamma intelligence not available for {symbol}"
            )

        return {
            "success": True,
            "symbol": symbol,
            "data": gamma_intel,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AI Copilot Endpoints
# ============================================================================

@app.post("/api/ai/analyze")
async def ai_analyze_market(request: dict):
    """
    Generate AI market analysis and trade recommendations

    Request body:
    {
        "symbol": "SPY",
        "query": "What's the best trade right now?",
        "market_data": {...},  # Optional GEX data
        "gamma_intel": {...}   # Optional gamma intelligence
    }

    Returns:
        Claude AI analysis and recommendations
    """
    try:
        symbol = request.get('symbol', 'SPY').upper()
        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # If no market data provided, fetch it
        if not market_data:
            gex_data = api_client.get_net_gamma(symbol)
            market_data = {
                'net_gex': gex_data.get('net_gex', 0),
                'spot_price': gex_data.get('spot_price', 0),
                'flip_point': gex_data.get('flip_point', 0),
                'symbol': symbol
            }

        # Use existing ClaudeIntelligence (UNCHANGED LOGIC)
        ai_response = claude_ai.analyze_market(
            market_data=market_data,
            user_query=query,
            gamma_intel=gamma_intel
        )

        return {
            "success": True,
            "symbol": symbol,
            "query": query,
            "response": ai_response,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            except:
                pass

manager = ConnectionManager()

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

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "Not found",
            "detail": str(exc.detail) if hasattr(exc, 'detail') else "Resource not found"
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc)
        }
    )

# ============================================================================
# Autonomous Trader Endpoints
# ============================================================================

# Initialize trader (if exists)
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    trader = AutonomousPaperTrader()
    trader_available = True
except:
    trader = None
    trader_available = False

@app.get("/api/trader/status")
async def get_trader_status():
    """Get autonomous trader status"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "is_active": False,
                "mode": "paper",
                "uptime": 0,
                "last_check": datetime.now().isoformat(),
                "strategies_active": 0,
                "total_trades_today": 0
            }
        }

    try:
        # Get real status from trader
        is_active = trader.get_config('is_active') == 'True' if trader else False
        mode = trader.get_config('mode') if trader else 'paper'

        return {
            "success": True,
            "data": {
                "is_active": is_active,
                "mode": mode,
                "uptime": 0,  # TODO: Calculate actual uptime
                "last_check": datetime.now().isoformat(),
                "strategies_active": 2,  # TODO: Get from trader config
                "total_trades_today": 0  # TODO: Calculate from database
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/performance")
async def get_trader_performance():
    """Get autonomous trader performance metrics"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "total_pnl": 0,
                "today_pnl": 0,
                "win_rate": 0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0
            }
        }

    try:
        perf = trader.get_performance()

        # Calculate additional metrics
        winning_trades = int(perf['total_trades'] * perf['win_rate'] / 100) if perf['total_trades'] > 0 else 0
        losing_trades = perf['total_trades'] - winning_trades

        return {
            "success": True,
            "data": {
                "total_pnl": perf['total_pnl'],
                "today_pnl": perf['unrealized_pnl'],  # Approximate
                "win_rate": perf['win_rate'],
                "total_trades": perf['total_trades'],
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "sharpe_ratio": 0,  # TODO: Calculate sharpe ratio
                "max_drawdown": 0  # TODO: Calculate max drawdown
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/trades")
async def get_trader_trades(limit: int = 10):
    """Get recent trades from autonomous trader"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect(trader.db_path)
        trades = pd.read_sql_query(f"""
            SELECT * FROM autonomous_positions
            ORDER BY timestamp DESC
            LIMIT {limit}
        """, conn)
        conn.close()

        trades_list = trades.to_dict('records') if not trades.empty else []

        return {
            "success": True,
            "data": trades_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    print("  - GET  /               Health check")
    print("  - GET  /docs           API documentation")
    print("  - GET  /api/gex/{symbol}              GEX data")
    print("  - GET  /api/gamma/{symbol}/intelligence   Gamma 3 views")
    print("  - POST /api/ai/analyze                AI Copilot")
    print("  - WS   /ws/market-data                Real-time updates")
    print("=" * 80)

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
