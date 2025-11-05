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
from config_and_database import STRATEGIES

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
            ORDER BY entry_date DESC, entry_time DESC
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

@app.get("/api/trader/positions")
async def get_open_positions():
    """Get currently open positions"""
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
        positions = pd.read_sql_query("""
            SELECT * FROM autonomous_positions
            WHERE status = 'OPEN'
            ORDER BY entry_date DESC, entry_time DESC
        """, conn)
        conn.close()

        positions_list = positions.to_dict('records') if not positions.empty else []

        return {
            "success": True,
            "data": positions_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/trade-log")
async def get_trade_log():
    """Get today's trade log"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd
        from datetime import datetime

        conn = sqlite3.connect(trader.db_path)

        # Get today's date in Central Time
        from intelligence_and_strategies import get_local_time
        today = get_local_time('US/Central').strftime('%Y-%m-%d')

        log_entries = pd.read_sql_query(f"""
            SELECT * FROM autonomous_trade_log
            WHERE date = '{today}'
            ORDER BY time DESC
        """, conn)
        conn.close()

        log_list = log_entries.to_dict('records') if not log_entries.empty else []

        return {
            "success": True,
            "data": log_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/price-history/{symbol}")
async def get_price_history(symbol: str, days: int = 90):
    """Get real price history for charting"""
    try:
        import yfinance as yf
        import pandas as pd

        symbol = symbol.upper()
        ticker = yf.Ticker(symbol)

        # Get historical data
        hist = ticker.history(period=f"{days}d")

        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

        # Convert to chart format
        chart_data = []
        for date, row in hist.iterrows():
            chart_data.append({
                "time": int(date.timestamp()),
                "value": float(row['Close'])
            })

        return {
            "success": True,
            "symbol": symbol,
            "data": chart_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/strategies")
async def get_strategy_stats():
    """Get real strategy statistics from trade database"""
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

        # Get all positions grouped by strategy
        query = """
            SELECT
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'CLOSED' THEN realized_pnl ELSE unrealized_pnl END) as total_pnl,
                MAX(entry_date) as last_trade_date
            FROM autonomous_positions
            GROUP BY strategy
        """

        strategies = pd.read_sql_query(query, conn)
        conn.close()

        strategy_list = []
        for _, row in strategies.iterrows():
            win_rate = (row['wins'] / row['total_trades'] * 100) if row['total_trades'] > 0 else 0
            strategy_list.append({
                "name": row['strategy'],
                "total_trades": int(row['total_trades']),
                "win_rate": float(win_rate),
                "total_pnl": float(row['total_pnl']) if row['total_pnl'] else 0,
                "last_trade_date": row['last_trade_date'],
                "status": "active"  # TODO: Determine from config or recent activity
            })

        return {
            "success": True,
            "data": strategy_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Multi-Symbol Scanner Endpoints (WITH DATABASE PERSISTENCE)
# ============================================================================

def init_scanner_database():
    """Initialize scanner database schema with tracking"""
    import sqlite3

    conn = sqlite3.connect('scanner_results.db')
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

@app.post("/api/scanner/scan")
async def scan_symbols(request: dict):
    """
    Scan multiple symbols for trading opportunities using ALL strategies

    Returns setups with SPECIFIC money-making instructions
    """
    import sqlite3
    import uuid
    import time

    try:
        symbols = request.get('symbols', ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA'])

        # Generate unique scan ID
        scan_id = str(uuid.uuid4())
        scan_start = time.time()

        results = []

        for symbol in symbols:
            try:
                # Get real GEX data
                gex_data = api_client.get_net_gamma(symbol)

                if not gex_data or gex_data.get('error'):
                    continue

                net_gex = gex_data.get('net_gex', 0)
                spot_price = gex_data.get('spot_price', 0)
                flip_point = gex_data.get('flip_point', 0)
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)

                # Check ALL strategies (not just Iron Condor!)
                for strategy_name, strategy_config in STRATEGIES.items():
                    confidence = 0
                    setup = None

                    # NEGATIVE GEX SQUEEZE - Directional Long Play
                    if strategy_name == 'NEGATIVE_GEX_SQUEEZE':
                        if net_gex < strategy_config['conditions']['net_gex_threshold']:
                            distance_to_flip = abs(spot_price - flip_point) / spot_price * 100
                            if distance_to_flip < strategy_config['conditions']['distance_to_flip']:
                                confidence = 0.75 if spot_price < flip_point else 0.85

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': call_wall,
                                    'stop_price': put_wall,
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in NEGATIVE GEX regime (${net_gex/1e9:.1f}B)
   - Price: ${spot_price:.2f} | Flip: ${flip_point:.2f}
   - This means: Market makers are SHORT gamma and must hedge aggressively

2. **THE TRADE** (Specific Actions):
   - BUY {symbol} ${(flip_point + 0.5):.2f} CALL (ATM or slightly OTM)
   - Entry: When price breaks ${flip_point:.2f} (flip point)
   - Quantity: Risk 1-2% of account (use Position Sizing tool)
   - Time: 0-3 DTE for max gamma, OR 7-14 DTE for less risk

3. **THE PROFIT** (Exit Strategy):
   - Target 1: ${(spot_price + (spot_price * 0.02)):.2f} (2% move) - Take 50% off
   - Target 2: ${call_wall:.2f} (Call Wall) - Take remaining 50% off
   - STOP LOSS: ${put_wall:.2f} (Put Wall breach) - Exit immediately
   - Expected Win Rate: {strategy_config['win_rate']*100:.0f}%

4. **WHY IT WORKS**:
   - Negative GEX = MMs chase price UP when it rises
   - Breaking flip point = Feedback loop begins
   - Call wall = Where MM hedging pressure stops
   - This setup wins {strategy_config['win_rate']*100:.0f}% historically

5. **TIMING**:
   - Best days: {', '.join(strategy_config['best_days'])}
   - Best time: First 30 min after flip break
   - Avoid: Last 15 min of day (low liquidity)
                                    """,
                                    'reasoning': f"Negative GEX ({net_gex/1e9:.1f}B) creates upside squeeze. Price ${distance_to_flip:.1f}% from flip point. Win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # POSITIVE GEX BREAKDOWN - Directional Short Play
                    elif strategy_name == 'POSITIVE_GEX_BREAKDOWN':
                        if net_gex > strategy_config['conditions']['net_gex_threshold']:
                            proximity = abs(spot_price - flip_point) / flip_point * 100
                            if proximity < strategy_config['conditions']['proximity_to_flip']:
                                confidence = 0.70

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': put_wall,
                                    'stop_price': call_wall,
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in POSITIVE GEX regime (${net_gex/1e9:.1f}B)
   - Price: ${spot_price:.2f} | Flip: ${flip_point:.2f}
   - This means: Market makers are LONG gamma and will fade moves

2. **THE TRADE** (Specific Actions):
   - BUY {symbol} ${(flip_point - 0.5):.2f} PUT (ATM or slightly OTM)
   - Entry: When price breaks BELOW ${flip_point:.2f} (flip point)
   - Quantity: Risk 1-2% of account
   - Time: 0-3 DTE for max profit potential

3. **THE PROFIT** (Exit Strategy):
   - Target: ${put_wall:.2f} (Put Wall) - Exit 100% here
   - Stop: ${call_wall:.2f} (Call Wall breach) - Cut losses
   - Expected Win Rate: {strategy_config['win_rate']*100:.0f}%
   - Typical Move: {strategy_config['typical_move']}

4. **WHY IT WORKS**:
   - Positive GEX breakdown = MMs fade the move DOWN
   - Flip break triggers cascade
   - Put wall = Support level where MMs defend
   - Wins {strategy_config['win_rate']*100:.0f}% when setup is clean

5. **TIMING**:
   - Best days: {', '.join(strategy_config['best_days'])}
   - Best time: After rejection at call wall
   - Avoid: Before major news/earnings
                                    """,
                                    'reasoning': f"Positive GEX ({net_gex/1e9:.1f}B) near flip creates breakdown risk. Historical win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # IRON CONDOR - Range-Bound Income
                    elif strategy_name == 'IRON_CONDOR':
                        if net_gex > strategy_config['conditions']['net_gex_threshold']:
                            wall_distance_call = abs(call_wall - spot_price) / spot_price * 100
                            wall_distance_put = abs(put_wall - spot_price) / spot_price * 100

                            if wall_distance_call >= 2.0 and wall_distance_put >= 2.0:
                                confidence = 0.75

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': spot_price,  # Range bound
                                    'stop_price': None,  # Defined by strikes
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in POSITIVE GEX (${net_gex/1e9:.1f}B) = RANGE BOUND
   - Price: ${spot_price:.2f}
   - Call Wall: ${call_wall:.2f} ({wall_distance_call:.1f}% away)
   - Put Wall: ${put_wall:.2f} ({wall_distance_put:.1f}% away)
   - This means: Price likely stays in range

2. **THE TRADE** (Specific Actions):
   - SELL Iron Condor with 5-10 DTE:
     * Sell ${call_wall:.2f} Call
     * Buy ${(call_wall + 5):.2f} Call (protection)
     * Sell ${put_wall:.2f} Put
     * Buy ${(put_wall - 5):.2f} Put (protection)
   - Collect: ~$0.30-0.50 per contract
   - Max Risk: $5.00 per contract
   - Position Size: Risk max 5% of account total

3. **THE PROFIT** (Exit Strategy):
   - Target: 50% of credit collected (close early!)
   - If collect $40 → close at $20 remaining value
   - Time-based: Close at 2 DTE if not at 50%
   - STOP: If price breaches wall → close immediately
   - Win Rate: {strategy_config['win_rate']*100:.0f}%!

4. **WHY IT WORKS**:
   - Positive GEX pins price in range
   - Walls are natural support/resistance
   - High win rate, steady income
   - Compound small wins = big gains

5. **RISK MANAGEMENT**:
   - Never risk > 5% per trade
   - Close at 50% profit (greed kills)
   - Don't fight wall breaches
   - Best on: {', '.join(strategy_config['best_days'])}
                                    """,
                                    'reasoning': f"Strong positive GEX ({net_gex/1e9:.1f}B) with wide walls. Perfect IC setup. Win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # PREMIUM SELLING - Wall Rejection Play
                    elif strategy_name == 'PREMIUM_SELLING':
                        wall_strength_call = abs(call_wall - spot_price) / spot_price * 100
                        wall_strength_put = abs(put_wall - spot_price) / spot_price * 100

                        if net_gex > 0 and (wall_strength_call < 1.5 or wall_strength_put < 1.5):
                            confidence = 0.68

                            at_call_wall = wall_strength_call < 1.5

                            setup = {
                                'symbol': symbol,
                                'strategy': strategy_name,
                                'confidence': confidence,
                                'net_gex': net_gex,
                                'spot_price': spot_price,
                                'flip_point': flip_point,
                                'call_wall': call_wall,
                                'put_wall': put_wall,
                                'entry_price': spot_price,
                                'target_price': call_wall if at_call_wall else put_wall,
                                'stop_price': None,
                                'risk_reward': strategy_config['risk_reward'],
                                'expected_move': strategy_config['typical_move'],
                                'win_rate': strategy_config['win_rate'],
                                'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} at {'CALL' if at_call_wall else 'PUT'} WALL: ${call_wall if at_call_wall else put_wall:.2f}
   - Current Price: ${spot_price:.2f}
   - Wall Distance: {wall_strength_call if at_call_wall else wall_strength_put:.1f}%
   - This means: High probability of rejection at wall

2. **THE TRADE** (Specific Actions):
   - SELL {'CALL' if at_call_wall else 'PUT'} at ${(call_wall if at_call_wall else put_wall):.2f} strike
   - Time: 0-2 DTE (max theta decay)
   - Collect: $0.20-0.40 per contract
   - Quantity: Sell 1-2 contracts per $10K account
   - Delta: -0.30 to -0.40 (OTM but close)

3. **THE PROFIT** (Exit Strategy):
   - Target: 50-70% profit in 1 day
   - If collect $30 → close at $10 remaining
   - Time: Close before 4pm on expiration day
   - STOP: If wall breaks by >0.5% → exit immediately
   - Win Rate: {strategy_config['win_rate']*100:.0f}%

4. **WHY IT WORKS**:
   - Walls reject price {strategy_config['win_rate']*100:.0f}% of the time
   - Theta decay works for you (time = money)
   - Near expiration = max decay
   - Positive GEX = walls hold strong

5. **RISK MANAGEMENT**:
   - Only sell premium at walls
   - Max 2-3 contracts at once
   - Close winners early (don't be greedy!)
   - Best timing: {', '.join(strategy_config['best_days'])}
                                    """,
                                    'reasoning': f"Price near {'call' if at_call_wall else 'put'} wall. Premium selling setup with {strategy_config['win_rate']*100:.0f}% win rate."
                                }

                    # If setup was created, add it to results
                    if setup:
                        results.append(setup)

            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
                continue

        # Save scan to database
        scan_duration = time.time() - scan_start

        conn = sqlite3.connect('scanner_results.db')
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

@app.get("/api/scanner/history")
async def get_scanner_history(limit: int = 10):
    """Get scanner run history"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('scanner_results.db')

        runs = pd.read_sql_query(f"""
            SELECT * FROM scanner_runs
            ORDER BY timestamp DESC
            LIMIT {limit}
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": runs.to_dict('records') if not runs.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scanner/results/{scan_id}")
async def get_scan_results(scan_id: str):
    """Get results for a specific scan"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('scanner_results.db')

        results = pd.read_sql_query(f"""
            SELECT * FROM scanner_results
            WHERE scan_id = '{scan_id}'
            ORDER BY confidence DESC
        """, conn)

        conn.close()

        return {
            "success": True,
            "scan_id": scan_id,
            "data": results.to_dict('records') if not results.empty else []
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
