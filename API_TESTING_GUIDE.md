# AlphaGEX API - Testing & Usage Guide

## 🎉 Your API is Live!

**Base URL:** `https://alphagex-api.onrender.com`

---

## Quick Start: Test the API

### 1. Health Check (Browser or curl)

**Browser:** Open this URL in your browser:
```
https://alphagex-api.onrender.com/health
```

**curl:**
```bash
curl https://alphagex-api.onrender.com/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-29T...",
  "market": {
    "open": true/false,
    "current_time_et": "2025-10-29 ..."
  },
  "services": {
    "api_client": "operational",
    "claude_ai": "operational",
    "database": "operational"
  }
}
```

### 2. Root Endpoint

**Browser:**
```
https://alphagex-api.onrender.com/
```

**Expected Response:**
```json
{
  "name": "AlphaGEX API",
  "version": "2.0.0",
  "status": "operational",
  "timestamp": "...",
  "docs": "/docs",
  "redoc": "/redoc"
}
```

### 3. Interactive API Documentation

**Swagger UI (Interactive):**
```
https://alphagex-api.onrender.com/docs
```

**ReDoc (Clean Documentation):**
```
https://alphagex-api.onrender.com/redoc
```

---

## Available API Endpoints

### 📊 Core Endpoints

#### 1. Get Market Time
```
GET /api/time
```
Returns current market time in ET and CT, plus market open/closed status.

**Example:**
```bash
curl https://alphagex-api.onrender.com/api/time
```

#### 2. Get GEX Data for Symbol
```
GET /api/gex/{symbol}
```
Returns Gamma Exposure data for a stock symbol.

**Example:**
```bash
curl https://alphagex-api.onrender.com/api/gex/SPY
curl https://alphagex-api.onrender.com/api/gex/QQQ
curl https://alphagex-api.onrender.com/api/gex/AAPL
```

**Response:**
```json
{
  "success": true,
  "symbol": "SPY",
  "data": {
    "net_gex": -1500000000,
    "spot_price": 450.25,
    "flip_point": 452.0,
    "call_wall": 455.0,
    "put_wall": 448.0,
    ...
  },
  "timestamp": "..."
}
```

#### 3. Get GEX Levels (Support/Resistance)
```
GET /api/gex/{symbol}/levels
```
Returns key support and resistance levels based on GEX.

**Example:**
```bash
curl https://alphagex-api.onrender.com/api/gex/SPY/levels
```

#### 4. Get Gamma Intelligence (3 Views)
```
GET /api/gamma/{symbol}/intelligence?vix={vix}
```
Returns comprehensive gamma expiration intelligence.

**Parameters:**
- `symbol` (required): Stock symbol (e.g., SPY)
- `vix` (optional): Current VIX value for context-aware adjustments

**Example:**
```bash
curl "https://alphagex-api.onrender.com/api/gamma/SPY/intelligence?vix=15.5"
```

**Response:** Returns 3 views:
- View 1: Daily Impact (Today → Tomorrow)
- View 2: Weekly Evolution (Monday → Friday)
- View 3: Volatility Potential (Risk Calendar)

### 🤖 AI Copilot Endpoint

#### 5. AI Market Analysis
```
POST /api/ai/analyze
```
Generate AI-powered market analysis and trade recommendations.

**Request Body:**
```json
{
  "symbol": "SPY",
  "query": "What's the best trade setup right now?",
  "market_data": {
    "net_gex": -1500000000,
    "spot_price": 450.25,
    "flip_point": 452.0
  },
  "gamma_intel": { ... }
}
```

**Example with curl:**
```bash
curl -X POST https://alphagex-api.onrender.com/api/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "query": "Should I buy calls or puts?",
    "market_data": {
      "net_gex": -1500000000,
      "spot_price": 450.25
    }
  }'
```

### 🔌 WebSocket Endpoint

#### 6. Real-Time Market Data
```
WS /ws/market-data?symbol=SPY
```
WebSocket connection for real-time market data updates (every 30 seconds during market hours).

**JavaScript Example:**
```javascript
const ws = new WebSocket('wss://alphagex-api.onrender.com/ws/market-data?symbol=SPY');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Market Update:', data);
};
```

---

## Testing with JavaScript (Frontend)

### Fetch API Example
```javascript
// Get GEX data
const response = await fetch('https://alphagex-api.onrender.com/api/gex/SPY');
const data = await response.json();
console.log(data);

// AI Analysis
const aiResponse = await fetch('https://alphagex-api.onrender.com/api/ai/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    symbol: 'SPY',
    query: 'What should I trade today?'
  })
});
const analysis = await aiResponse.json();
console.log(analysis);
```

### Axios Example
```javascript
import axios from 'axios';

const baseURL = 'https://alphagex-api.onrender.com';

// Get GEX data
const gexData = await axios.get(`${baseURL}/api/gex/SPY`);
console.log(gexData.data);

// AI Analysis
const aiAnalysis = await axios.post(`${baseURL}/api/ai/analyze`, {
  symbol: 'SPY',
  query: 'Best trade setup?'
});
console.log(aiAnalysis.data);
```

---

## CORS Configuration

The API is configured to accept requests from:
- `http://localhost:3000` (Local development)
- `http://localhost:5173` (Vite dev server)
- `https://alphagex.vercel.app` (Production frontend)
- `https://*.vercel.app` (All Vercel preview deployments)

If you need to add more origins, update the `ALLOWED_ORIGINS` in Render dashboard environment variables.

---

## Environment Variables (Render Dashboard)

The following environment variables should be set in Render:

### Required:
- `ENVIRONMENT=production`
- `PYTHON_VERSION=3.11.0`

### Optional (for full functionality):
- `CLAUDE_API_KEY` - For AI Copilot features
- `TRADING_VOLATILITY_API_KEY` - For GEX data
- `TV_USERNAME` - Trading Volatility username
- `ENDPOINT` - Custom API endpoint (optional)

---

## Monitoring & Logs

### View Logs
1. Go to Render Dashboard: https://dashboard.render.com/web/srv-d413d9vgi27c73d4r1fg
2. Click "Logs" in the left sidebar
3. Watch real-time logs

### Check Status
```bash
curl https://alphagex-api.onrender.com/health
```

---

## Common Issues & Solutions

### 1. "Market data not available"
**Cause:** Trading Volatility API credentials not set or rate limited.
**Solution:** Set `TV_USERNAME` and `TRADING_VOLATILITY_API_KEY` in Render dashboard.

### 2. CORS errors from frontend
**Cause:** Your frontend domain is not in allowed origins.
**Solution:** Add your domain to `ALLOWED_ORIGINS` environment variable in Render.

### 3. AI Copilot not working
**Cause:** Claude API key not set.
**Solution:** Set `CLAUDE_API_KEY` in Render dashboard environment variables.

---

## Next Steps

1. ✅ **Test the API** - Try the health check and GEX endpoints
2. 📖 **Explore the Docs** - Visit `/docs` for interactive API documentation
3. 🔗 **Connect Frontend** - Integrate the API with your React/Next.js frontend
4. 🔑 **Set API Keys** - Add Claude and Trading Volatility API keys for full functionality
5. 📊 **Monitor** - Watch the Render logs for any issues

---

## Support

- **API Documentation:** https://alphagex-api.onrender.com/docs
- **Service Dashboard:** https://dashboard.render.com/web/srv-d413d9vgi27c73d4r1fg
- **Issues:** Report at https://github.com/lemollon/AlphaGEX/issues

---

**Congratulations! Your AlphaGEX API is live and ready to use!** 🚀
