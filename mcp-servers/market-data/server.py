#!/usr/bin/env python3
"""
Market Data MCP Server for AlphaGEX
Provides unified access to Trading Volatility, Polygon, and Yahoo Finance data sources.
Deployed as Render web service with HTTP/SSE transport.
"""

import os
import sys
import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core_classes_and_engines import TradingVolatilityAPI
from polygon_data_fetcher import PolygonDataFetcher

# =============================================================================
# MCP Protocol Models
# =============================================================================

class MCPRequest(BaseModel):
    """MCP JSON-RPC request"""
    jsonrpc: str = "2.0"
    id: Optional[int | str] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    """MCP JSON-RPC response"""
    jsonrpc: str = "2.0"
    id: Optional[int | str] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class Tool(BaseModel):
    """MCP Tool definition"""
    name: str
    description: str
    inputSchema: Dict[str, Any]


# =============================================================================
# FastAPI App Setup
# =============================================================================

app = FastAPI(
    title="AlphaGEX Market Data MCP Server",
    description="Provides market data from Trading Volatility, Polygon, and Yahoo Finance",
    version="1.0.0"
)

# Initialize data sources
trading_volatility = TradingVolatilityAPI(
    api_key=os.getenv("TRADING_VOLATILITY_API_KEY"),
    tv_username=os.getenv("TV_USERNAME")
)

polygon = PolygonDataFetcher(
    api_key=os.getenv("POLYGON_API_KEY")
)

# =============================================================================
# MCP Tools Available
# =============================================================================

TOOLS = [
    Tool(
        name="getTradingVolatilityGEX",
        description="Fetch gamma exposure (GEX) data from Trading Volatility API. Returns net gamma, flip point, call/put walls, and dealer positioning.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., 'SPY', 'QQQ', 'AAPL')"
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Include historical GEX snapshots (last 30 days)",
                    "default": False
                }
            },
            "required": ["symbol"]
        }
    ),
    Tool(
        name="getPolygonStockPrice",
        description="Get current and historical stock price data from Polygon.io. Supports multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d).",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., 'SPY')"
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                    "description": "Timeframe for price data",
                    "default": "5m"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of candles to return (max 5000)",
                    "default": 100
                }
            },
            "required": ["symbol"]
        }
    ),
    Tool(
        name="getPolygonVIX",
        description="Get current VIX (volatility index) level from Polygon.io. Essential for understanding market fear/greed.",
        inputSchema={
            "type": "object",
            "properties": {
                "include_history": {
                    "type": "boolean",
                    "description": "Include VIX history (last 30 days)",
                    "default": False
                }
            },
            "required": []
        }
    ),
    Tool(
        name="getMarketSnapshot",
        description="Get a comprehensive market snapshot combining GEX data, stock price, VIX, and put/call ratio for a symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., 'SPY')"
                }
            },
            "required": ["symbol"]
        }
    ),
    Tool(
        name="checkRateLimits",
        description="Check current API rate limit status for all data sources (Trading Volatility, Polygon).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
]

# =============================================================================
# Tool Implementation Functions
# =============================================================================

async def get_trading_volatility_gex(symbol: str, include_history: bool = False) -> Dict[str, Any]:
    """Fetch GEX data from Trading Volatility API"""
    try:
        gex_data = trading_volatility.fetch_gex_profile(symbol)

        result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "net_gex": gex_data.get("net_gex"),
            "flip_point": gex_data.get("flip_point"),
            "call_wall": gex_data.get("call_wall"),
            "put_wall": gex_data.get("put_wall"),
            "current_price": gex_data.get("current_price"),
            "put_call_ratio": gex_data.get("put_call_ratio"),
            "dealer_positioning": "short_gamma" if gex_data.get("net_gex", 0) < 0 else "long_gamma",
            "data_source": "Trading Volatility API"
        }

        if include_history:
            # TODO: Fetch from database
            result["history_note"] = "History fetching from database not yet implemented"

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch GEX data: {str(e)}")


async def get_polygon_stock_price(symbol: str, timeframe: str = "5m", limit: int = 100) -> Dict[str, Any]:
    """Fetch stock price data from Polygon"""
    try:
        price_data = polygon.fetch_stock_price(symbol, timeframe=timeframe, limit=limit)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.now().isoformat(),
            "current_price": price_data[-1].get("close") if price_data else None,
            "candles": price_data,
            "data_source": "Polygon.io"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock price: {str(e)}")


async def get_polygon_vix(include_history: bool = False) -> Dict[str, Any]:
    """Fetch VIX data from Polygon"""
    try:
        vix_data = polygon.fetch_vix()

        result = {
            "symbol": "VIX",
            "timestamp": datetime.now().isoformat(),
            "current_value": vix_data.get("current_vix"),
            "regime": "high_volatility" if vix_data.get("current_vix", 0) > 20 else "normal_volatility",
            "data_source": "Polygon.io"
        }

        if include_history:
            result["history"] = vix_data.get("history", [])

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch VIX: {str(e)}")


async def get_market_snapshot(symbol: str) -> Dict[str, Any]:
    """Get comprehensive market snapshot"""
    try:
        # Fetch all data in parallel
        gex_task = get_trading_volatility_gex(symbol, include_history=False)
        price_task = get_polygon_stock_price(symbol, timeframe="5m", limit=10)
        vix_task = get_polygon_vix(include_history=False)

        gex, price, vix = await asyncio.gather(gex_task, price_task, vix_task)

        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "snapshot": {
                "gex": gex,
                "price": price,
                "vix": vix
            },
            "summary": {
                "current_price": price.get("current_price"),
                "net_gex": gex.get("net_gex"),
                "flip_point": gex.get("flip_point"),
                "vix": vix.get("current_value"),
                "dealer_positioning": gex.get("dealer_positioning"),
                "volatility_regime": vix.get("regime")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch market snapshot: {str(e)}")


async def check_rate_limits() -> Dict[str, Any]:
    """Check API rate limit status"""
    return {
        "timestamp": datetime.now().isoformat(),
        "rate_limits": {
            "trading_volatility": {
                "limit": "20 calls/minute",
                "status": "ok",  # TODO: Implement actual rate limit tracking
                "note": "Circuit breaker active with 4-second intervals"
            },
            "polygon": {
                "limit": "Varies by plan (Starter/Developer tier)",
                "status": "ok",
                "note": "Rate limiting handled by Polygon client"
            }
        }
    }

# =============================================================================
# MCP Protocol Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    return {
        "status": "healthy",
        "service": "market-data-mcp",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint - returns server info"""
    return {
        "name": "AlphaGEX Market Data MCP Server",
        "version": "1.0.0",
        "protocol": "MCP over HTTP/SSE",
        "tools": len(TOOLS),
        "endpoints": {
            "sse": "POST /sse",
            "message": "POST /message",
            "health": "GET /health"
        }
    }


@app.post("/message")
async def handle_message(request: MCPRequest) -> MCPResponse:
    """Handle MCP JSON-RPC messages"""

    # List available tools
    if request.method == "tools/list":
        return MCPResponse(
            id=request.id,
            result={
                "tools": [tool.dict() for tool in TOOLS]
            }
        )

    # Call a tool
    elif request.method == "tools/call":
        tool_name = request.params.get("name")
        tool_args = request.params.get("arguments", {})

        try:
            # Route to appropriate tool implementation
            if tool_name == "getTradingVolatilityGEX":
                result = await get_trading_volatility_gex(**tool_args)
            elif tool_name == "getPolygonStockPrice":
                result = await get_polygon_stock_price(**tool_args)
            elif tool_name == "getPolygonVIX":
                result = await get_polygon_vix(**tool_args)
            elif tool_name == "getMarketSnapshot":
                result = await get_market_snapshot(**tool_args)
            elif tool_name == "checkRateLimits":
                result = await check_rate_limits()
            else:
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                )

            return MCPResponse(
                id=request.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            )

        except Exception as e:
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": f"Tool execution failed: {str(e)}"
                }
            )

    # Initialize connection
    elif request.method == "initialize":
        return MCPResponse(
            id=request.id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "market-data-mcp",
                    "version": "1.0.0"
                }
            }
        )

    # Unknown method
    else:
        return MCPResponse(
            id=request.id,
            error={
                "code": -32601,
                "message": f"Method not found: {request.method}"
            }
        )


@app.post("/sse")
async def sse_endpoint(request: Request):
    """Server-Sent Events endpoint for streaming MCP messages"""

    async def event_generator():
        """Generate SSE events"""
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # Keep connection alive
        while True:
            await asyncio.sleep(30)  # Send keepalive every 30 seconds
            yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.now().isoformat()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# =============================================================================
# Server Startup
# =============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))

    print(f"🚀 Starting Market Data MCP Server on port {port}")
    print(f"📊 Available tools: {len(TOOLS)}")
    print(f"🔧 Data sources: Trading Volatility, Polygon.io")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
