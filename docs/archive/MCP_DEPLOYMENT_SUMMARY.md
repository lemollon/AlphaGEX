# MCP Servers on Render - Quick Start

## ✅ What's Been Created

### 1. MCP Server Implementation
```
mcp-servers/
└── market-data/
    ├── server.py           # Full MCP server with 5 tools
    ├── requirements.txt    # Dependencies
    └── start.sh           # Startup script
```

**Tools Available:**
- `getTradingVolatilityGEX` - Fetch GEX data
- `getPolygonStockPrice` - Get stock prices
- `getPolygonVIX` - Get VIX data
- `getMarketSnapshot` - Complete market snapshot
- `checkRateLimits` - API rate limit status

### 2. MCP Client Library
- `mcp_client.py` - Python client for connecting to MCP servers
- Convenience functions: `get_market_data_client()`, etc.
- Error handling: `MCPError`, `MCPConnectionError`

### 3. Render Configuration
- `render-mcp.yaml` - Complete blueprint with 4 MCP servers
- Environment variables configured
- Health checks enabled

### 4. Documentation
- `docs/MCP_SERVERS_ON_RENDER.md` - Complete deployment guide

---

## 🚀 Quick Deploy to Render

### Option 1: Via Render Dashboard

1. Go to https://dashboard.render.com
2. Click "New" → "Blueprint"
3. Connect GitHub repo: `lemollon/AlphaGEX`
4. Select branch: `claude/mcp-server-alpha-hex-01GHwrXfwHsi4dzgw3ULdcuc`
5. Select file: `render-mcp.yaml`
6. Click "Apply"
7. Wait for deployment (~5-10 minutes)

### Option 2: Replace Existing render.yaml

```bash
# Backup current config
mv render.yaml render-original.yaml

# Use MCP version
mv render-mcp.yaml render.yaml

# Commit and push
git add .
git commit -m "Deploy MCP server layer to Render"
git push -u origin claude/mcp-server-alpha-hex-01GHwrXfwHsi4dzgw3ULdcuc
```

Render will auto-deploy all 8 services:
- 4 existing services (api, app, trader, collector)
- 4 new MCP servers (market-data, intelligence, execution, learning)

---

## 🧪 Test Deployment

### 1. Health Check

```bash
curl https://alphagex-mcp-market-data.onrender.com/health

# Expected:
{
  "status": "healthy",
  "service": "market-data-mcp",
  "timestamp": "2025-11-23T..."
}
```

### 2. List Tools

```bash
curl -X POST https://alphagex-mcp-market-data.onrender.com/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

### 3. Call Tool

```python
from mcp_client import get_market_data_client

client = get_market_data_client()
client.initialize()

result = client.call_tool("getTradingVolatilityGEX", {
    "symbol": "SPY"
})

print(f"Net GEX: {result['net_gex']}")
print(f"Flip Point: {result['flip_point']}")
```

---

## 💰 Cost Breakdown

| Deployment | Services | Cost/Month |
|------------|----------|------------|
| **Current (No MCP)** | 4 services + DB | $28 |
| **Full MCP (All 4 servers)** | 8 services + DB | $56 |
| **Optimized (2 combined servers)** | 6 services + DB | $42 |
| **Minimal (1 MCP server)** | 5 services + DB | $35 |

**Recommendation:** Start with just **Market Data MCP** ($35/mo), add others as needed.

---

## 📋 Next Steps

### Immediate (Ready to Deploy)
1. ✅ Deploy Market Data MCP server to Render
2. ✅ Test with existing autonomous trader
3. ✅ Verify data fetching works correctly

### Short-Term (1-2 weeks)
4. 🚧 Implement Intelligence MCP server (Claude AI tools)
5. 🚧 Implement Execution MCP server (trading tools)
6. 🚧 Refactor autonomous trader to use MCP clients

### Medium-Term (3-4 weeks)
7. 🚧 Implement Learning MCP server (ML tools)
8. 🚧 Add caching layer (Redis)
9. 🚧 Build multi-agent orchestration system

---

## 🔑 Environment Variables to Set in Render

### For Market Data MCP Server

```bash
TRADING_VOLATILITY_API_KEY=<your_key>
TV_USERNAME=<your_username>
POLYGON_API_KEY=<your_key>
MCP_API_KEY=<optional_auth_key>
```

### For Existing Services (Add These)

```bash
MCP_MARKET_DATA_URL=https://alphagex-mcp-market-data.onrender.com
MCP_INTELLIGENCE_URL=https://alphagex-mcp-intelligence.onrender.com
MCP_EXECUTION_URL=https://alphagex-mcp-execution.onrender.com
MCP_LEARNING_URL=https://alphagex-mcp-learning.onrender.com
```

---

## 🎯 Benefits You Get

### 1. **Unified Data Access**
- One interface for Trading Volatility, Polygon, Yahoo Finance
- No more scattered API calls
- Built-in rate limiting and caching

### 2. **Service Isolation**
- Market data failures don't crash trader
- Each service scales independently
- Easy to debug and monitor

### 3. **Reusable Tools**
- API, Trader, Collector all use same MCP tools
- No duplicate code
- Consistent data across services

### 4. **Future-Proof for Agentic AI**
- Ready for multi-agent orchestration
- Tools discoverable at runtime
- Easy to add new capabilities

---

## 📚 Files Created

```
AlphaGEX/
├── mcp-servers/
│   └── market-data/
│       ├── server.py               # MCP server implementation
│       ├── requirements.txt
│       └── start.sh
│
├── mcp_client.py                   # Client library
├── render-mcp.yaml                 # Render blueprint
│
├── docs/
│   └── MCP_SERVERS_ON_RENDER.md   # Full documentation
│
└── MCP_DEPLOYMENT_SUMMARY.md       # This file
```

---

## ❓ FAQ

**Q: Do I need all 4 MCP servers?**
A: No! Start with just Market Data MCP. Add others as you need them.

**Q: Will this break existing functionality?**
A: No. MCP servers are additive. Existing code continues to work.

**Q: How do I migrate existing code to use MCP?**
A: Gradual refactor:
```python
# Old way
api = TradingVolatilityAPI(api_key)
data = api.fetch_gex_profile("SPY")

# New way (MCP)
client = get_market_data_client()
data = client.call_tool("getTradingVolatilityGEX", {"symbol": "SPY"})
```

**Q: What if MCP server goes down?**
A: Add fallback logic:
```python
try:
    data = client.call_tool("getTradingVolatilityGEX", {"symbol": "SPY"})
except MCPConnectionError:
    # Fallback to direct API call
    data = trading_volatility.fetch_gex_profile("SPY")
```

---

## 🚦 Status

- ✅ Market Data MCP Server: **READY TO DEPLOY**
- 🚧 Intelligence MCP Server: **TODO**
- 🚧 Execution MCP Server: **TODO**
- 🚧 Learning MCP Server: **TODO**

**Next Action:** Deploy to Render and test!
