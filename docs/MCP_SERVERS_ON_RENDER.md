# MCP Servers on Render - Deployment Guide

## Overview

This guide explains how to deploy AlphaGEX's MCP (Model Context Protocol) server architecture on Render. MCP servers provide a modular, scalable way to expose AlphaGEX's capabilities as reusable tools for AI agents.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 ALPHAGEX ON RENDER                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  EXISTING SERVICES (MCP Clients)                        │
│  ├── alphagex-api (FastAPI)                            │
│  ├── alphagex-trader (Worker)                          │
│  └── alphagex-collector (Worker)                       │
│                                                         │
│          │                                              │
│          │ HTTP/SSE (JSON-RPC)                         │
│          ▼                                              │
│                                                         │
│  MCP SERVER LAYER (Tools & Resources)                  │
│  ├── alphagex-mcp-market-data                          │
│  │   └─ Tools: getTradingVolatilityGEX, getPolygonPrice│
│  │                                                      │
│  ├── alphagex-mcp-intelligence                         │
│  │   └─ Tools: analyzeMarket, recommendTrade           │
│  │                                                      │
│  ├── alphagex-mcp-execution                            │
│  │   └─ Tools: openPosition, closePosition             │
│  │                                                      │
│  └── alphagex-mcp-learning                             │
│      └─ Tools: trainMLModel, getBacktestResults        │
│                                                         │
│  SHARED DATABASE                                        │
│  └── alphagex-db (PostgreSQL)                          │
└─────────────────────────────────────────────────────────┘
```

## Why MCP Servers on Render?

### ✅ Benefits

1. **Service Isolation**: Each MCP server is independent, can be scaled separately
2. **HTTP/SSE Transport**: Works perfectly with Render's web services
3. **Health Checks**: Render monitors each service automatically
4. **Private Networking**: MCP servers can communicate internally (no public exposure needed)
5. **Auto-Deploy**: Git push triggers automatic deployment
6. **Cost-Effective**: Can use free tier or starter plan ($7/mo per service)

### 🆚 Alternative: Stdio Transport

**Why NOT Stdio on Render:**
- ❌ Stdio requires subprocess spawning (not supported in Render workers)
- ❌ Can't communicate across services (API → Worker → Collector)
- ❌ No health monitoring
- ❌ Designed for local Claude Desktop, not production servers

**HTTP/SSE is the right choice for Render deployment.**

---

## MCP Server Services

### 1. Market Data MCP Server
**Service:** `alphagex-mcp-market-data`
**URL:** `https://alphagex-mcp-market-data.onrender.com`

**Tools:**
- `getTradingVolatilityGEX` - Fetch gamma exposure data
- `getPolygonStockPrice` - Get stock prices (multi-timeframe)
- `getPolygonVIX` - Get VIX volatility index
- `getMarketSnapshot` - Comprehensive market snapshot
- `checkRateLimits` - API rate limit status

**Use Cases:**
- Autonomous trader fetching GEX data
- Data collector gathering market snapshots
- Real-time price feeds for API endpoints

---

### 2. Intelligence MCP Server
**Service:** `alphagex-mcp-intelligence` (TODO: Implement)
**URL:** `https://alphagex-mcp-intelligence.onrender.com`

**Tools (Planned):**
- `analyzeMarketRegime` - Detect psychology traps and GEX regimes
- `recommendTrade` - AI-powered trade recommendations
- `detectPsychologyTrap` - Pattern detection
- `evaluatePosition` - Position health analysis
- `coachTrader` - Psychological coaching

**Use Cases:**
- Autonomous trader decision-making
- Real-time market analysis
- Trade journal insights

---

### 3. Execution MCP Server
**Service:** `alphagex-mcp-execution` (TODO: Implement)
**URL:** `https://alphagex-mcp-execution.onrender.com`

**Tools (Planned):**
- `openPosition` - Open new paper trading position
- `closePosition` - Close existing position
- `calculatePositionSize` - Kelly Criterion sizing
- `validateRisk` - Risk management checks
- `getPortfolio` - Current portfolio state

**Use Cases:**
- Autonomous trader execution
- Multi-agent position management
- Risk validation before trades

---

### 4. Learning MCP Server
**Service:** `alphagex-mcp-learning` (TODO: Implement)
**URL:** `https://alphagex-mcp-learning.onrender.com`

**Tools (Planned):**
- `trainMLModel` - Train pattern learner
- `getBacktestResults` - Historical performance
- `analyzeSimilarTrades` - Find similar setups
- `updateStrategy` - Adapt strategy parameters
- `evaluateStrategyCompetition` - Strategy leaderboard

**Use Cases:**
- Continuous learning system
- Strategy evolution
- Performance optimization

---

## Deployment Steps

### Step 1: Prepare MCP Server Code

Each MCP server has this structure:
```
mcp-servers/
├── market-data/
│   ├── server.py          # FastAPI MCP server
│   ├── requirements.txt   # Python dependencies
│   └── start.sh          # Startup script
├── intelligence/
│   ├── server.py
│   ├── requirements.txt
│   └── start.sh
├── execution/
│   └── ...
└── learning/
    └── ...
```

### Step 2: Update Render Configuration

Use `render-mcp.yaml` instead of `render.yaml`:

```yaml
# Add MCP server as web service
- type: web
  name: alphagex-mcp-market-data
  runtime: python
  plan: starter
  rootDir: mcp-servers/market-data
  buildCommand: pip install --no-cache-dir -r requirements.txt
  startCommand: chmod +x start.sh && ./start.sh
  healthCheckPath: /health
  envVars:
    - key: PORT
      value: "8080"
    - key: TRADING_VOLATILITY_API_KEY
      sync: false
```

### Step 3: Deploy to Render

**Option A: Via Render Dashboard**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "Blueprint"
3. Connect your GitHub repo
4. Select `render-mcp.yaml` as blueprint file
5. Click "Apply"

**Option B: Via Git Push**
1. Ensure `render-mcp.yaml` is in repo root
2. Push to main branch:
   ```bash
   git add .
   git commit -m "Add MCP server layer"
   git push origin main
   ```
3. Render auto-deploys all services

### Step 4: Verify Deployment

Check each MCP server health:
```bash
curl https://alphagex-mcp-market-data.onrender.com/health
# Expected: {"status": "healthy", "service": "market-data-mcp", ...}

curl https://alphagex-mcp-intelligence.onrender.com/health
curl https://alphagex-mcp-execution.onrender.com/health
curl https://alphagex-mcp-learning.onrender.com/health
```

### Step 5: Test Tool Calls

```python
from mcp_client import get_market_data_client

# Connect to MCP server
client = get_market_data_client()

# Initialize
client.initialize()

# List tools
tools = client.list_tools()
print(f"Available tools: {[t['name'] for t in tools]}")

# Call tool
result = client.call_tool("getTradingVolatilityGEX", {
    "symbol": "SPY",
    "include_history": False
})
print(f"Net GEX: {result['net_gex']}")
print(f"Flip Point: {result['flip_point']}")
```

---

## Using MCP Clients in AlphaGEX Services

### In Autonomous Trader (`autonomous_paper_trader.py`)

```python
from mcp_client import get_market_data_client, get_intelligence_client, get_execution_client

class AutonomousPaperTrader:
    def __init__(self):
        # Initialize MCP clients
        self.market_data = get_market_data_client()
        self.intelligence = get_intelligence_client()
        self.execution = get_execution_client()

        # Initialize connections
        self.market_data.initialize()
        self.intelligence.initialize()
        self.execution.initialize()

    async def analyze_and_trade(self, symbol: str):
        # 1. Fetch market data via MCP
        market_snapshot = self.market_data.call_tool("getMarketSnapshot", {
            "symbol": symbol
        })

        # 2. Get AI recommendation via MCP
        recommendation = self.intelligence.call_tool("recommendTrade", {
            "symbol": symbol,
            "market_data": market_snapshot
        })

        # 3. Execute trade via MCP
        if recommendation["should_trade"]:
            result = self.execution.call_tool("openPosition", {
                "symbol": symbol,
                "strategy": recommendation["strategy"],
                "strike": recommendation["strike"],
                "position_size": recommendation["size"]
            })
            return result
```

### In Data Collector (`automated_data_collector.py`)

```python
from mcp_client import get_market_data_client

collector = get_market_data_client()
collector.initialize()

# Collect GEX data for multiple symbols
symbols = ["SPY", "QQQ", "IWM", "AAPL", "TSLA"]

for symbol in symbols:
    gex_data = collector.call_tool("getTradingVolatilityGEX", {
        "symbol": symbol,
        "include_history": False
    })

    # Save to database
    save_to_db(symbol, gex_data)
```

### In FastAPI Backend (`backend/main.py`)

```python
from mcp_client import get_market_data_client, get_intelligence_client

# Initialize MCP clients on startup
@app.on_event("startup")
async def startup_event():
    app.state.market_data_mcp = get_market_data_client()
    app.state.intelligence_mcp = get_intelligence_client()

    app.state.market_data_mcp.initialize()
    app.state.intelligence_mcp.initialize()

# Use in endpoints
@app.get("/api/gamma/{symbol}")
async def get_gamma_data(symbol: str, request: Request):
    mcp_client = request.app.state.market_data_mcp

    result = mcp_client.call_tool("getTradingVolatilityGEX", {
        "symbol": symbol,
        "include_history": True
    })

    return result
```

---

## Environment Variables

### Required for All MCP Servers

```bash
# Render auto-provides
PORT=8080

# Python version
PYTHON_VERSION=3.11.0

# Environment
ENVIRONMENT=production
```

### Market Data MCP Server

```bash
TRADING_VOLATILITY_API_KEY=your_tv_api_key
TV_USERNAME=your_tv_username
POLYGON_API_KEY=your_polygon_key
MCP_API_KEY=optional_auth_key  # For securing endpoints
```

### Intelligence MCP Server

```bash
CLAUDE_API_KEY=your_anthropic_key
ANTHROPIC_API_KEY=your_anthropic_key
DATABASE_URL=postgresql://...  # From alphagex-db
MCP_API_KEY=optional_auth_key
```

### Execution MCP Server

```bash
DATABASE_URL=postgresql://...
MCP_API_KEY=optional_auth_key
```

### Learning MCP Server

```bash
DATABASE_URL=postgresql://...
MCP_API_KEY=optional_auth_key
```

---

## Cost Analysis

### Current AlphaGEX on Render (4 services)

| Service | Type | Plan | Cost/Month |
|---------|------|------|------------|
| alphagex-api | Web | Starter | $7 |
| alphagex-app | Web | Starter | $7 |
| alphagex-trader | Worker | Starter | $7 |
| alphagex-collector | Worker | Starter | $7 |
| alphagex-db | Database | Starter | Free |
| **TOTAL** | | | **$28/mo** |

### With MCP Servers (8 services)

| Service | Type | Plan | Cost/Month |
|---------|------|------|------------|
| Existing (4 services) | | | $28 |
| alphagex-mcp-market-data | Web | Starter | $7 |
| alphagex-mcp-intelligence | Web | Starter | $7 |
| alphagex-mcp-execution | Web | Starter | $7 |
| alphagex-mcp-learning | Web | Starter | $7 |
| **TOTAL** | | | **$56/mo** |

### Cost Optimization Strategies

1. **Use Free Tier for Low-Traffic MCP Servers**
   - Free tier: 750 hours/month (shared)
   - Good for: learning, execution (low request volume)

2. **Combine MCP Servers**
   - Merge intelligence + learning into one service
   - Merge execution + market-data into one service
   - Reduces to 2 MCP servers = $14/mo instead of $28/mo

3. **On-Demand Scaling**
   - Keep MCP servers in free tier
   - Upgrade to Starter only if hitting rate limits

**Recommended:** Start with combined approach ($42/mo total), separate later if needed.

---

## Security Considerations

### 1. API Key Authentication

```python
# In MCP server
from fastapi import Header, HTTPException

async def verify_api_key(authorization: str = Header(None)):
    expected_key = os.getenv("MCP_API_KEY")

    if not expected_key:
        return  # No auth required

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")

    provided_key = authorization.replace("Bearer ", "")
    if provided_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

# Apply to endpoints
@app.post("/message", dependencies=[Depends(verify_api_key)])
async def handle_message(request: MCPRequest):
    ...
```

### 2. Private Services (Render Pro)

If on Render Pro plan, use private services:

```yaml
- type: web
  name: alphagex-mcp-market-data
  plan: starter
  privateAccess: true  # Only accessible to other Render services
```

### 3. Rate Limiting

```python
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/message")
@limiter.limit("60/minute")  # 60 requests per minute
async def handle_message(request: Request, mcp_request: MCPRequest):
    ...
```

---

## Monitoring & Debugging

### Health Checks

Each MCP server has `/health` endpoint:
```bash
curl https://alphagex-mcp-market-data.onrender.com/health

# Response:
{
  "status": "healthy",
  "service": "market-data-mcp",
  "timestamp": "2025-11-23T10:30:00Z"
}
```

### Logs

View logs in Render Dashboard:
1. Go to service (e.g., `alphagex-mcp-market-data`)
2. Click "Logs" tab
3. Filter by timestamp, log level

### Testing MCP Protocol

```bash
# Test tool listing
curl -X POST https://alphagex-mcp-market-data.onrender.com/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'

# Test tool call
curl -X POST https://alphagex-mcp-market-data.onrender.com/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "getTradingVolatilityGEX",
      "arguments": {
        "symbol": "SPY",
        "include_history": false
      }
    }
  }'
```

---

## Troubleshooting

### Issue: MCP server not responding

**Check:**
1. Service status in Render dashboard
2. Health check endpoint: `/health`
3. Environment variables set correctly
4. Build logs for errors

### Issue: Tool call returns error

**Debug:**
```python
try:
    result = client.call_tool("getTradingVolatilityGEX", {"symbol": "SPY"})
except MCPError as e:
    print(f"MCP Error {e.code}: {e.message}")
except MCPConnectionError as e:
    print(f"Connection failed: {e}")
```

### Issue: Rate limits exceeded

**Solutions:**
1. Implement caching in MCP server
2. Use Redis for shared cache across services
3. Batch requests when possible

---

## Next Steps

1. ✅ **Deploy Market Data MCP Server** (DONE)
   - `mcp-servers/market-data/` implemented
   - Ready to deploy

2. 🚧 **Implement Intelligence MCP Server**
   - Extract logic from `intelligence_and_strategies.py`
   - Create tools for Claude AI analysis

3. 🚧 **Implement Execution MCP Server**
   - Extract logic from `autonomous_paper_trader.py`
   - Create tools for position management

4. 🚧 **Implement Learning MCP Server**
   - Extract logic from `autonomous_ml_pattern_learner.py`
   - Create tools for ML training and backtesting

5. 🚧 **Update Existing Services to Use MCP Clients**
   - Refactor autonomous trader
   - Refactor data collector
   - Update API endpoints

---

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Render Documentation](https://render.com/docs)
- [AlphaGEX Architecture](./ARCHITECTURE.md)

---

**Status:** Market Data MCP Server ready to deploy. Other servers pending implementation.

**Next Action:** Deploy to Render and test market data MCP server with existing services.
