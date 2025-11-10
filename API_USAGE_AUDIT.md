# Complete Trading Volatility API Usage Audit

## Rate Limits (From User)
```
Stocks+ Subscribers:
- Non-realtime calls (weekday): 20 per minute
- Realtime calls (during regular trading hours): 2 per minute
- Options Volume API calls (weekend): 1 per minute
- **All other API calls on weekend: 2 per minute** ← CRITICAL!
```

## Backend Endpoints That Call Trading Volatility API

### Endpoints calling `get_net_gamma()` (/gex/latest - aggregate data):
1. `/api/gex/{symbol}` (line 237)
2. `/api/gamma/{symbol}/intelligence` (line 619)
3. `/api/psychology/current-regime` (line 790)
4. `/api/psychology/rsi-analysis/{symbol}` (line 982, 1054)
5. `/api/psychology/liberation-setups` (line 1745)
6. `/api/psychology/false-floors` (line 1936)
7. `/api/psychology/trap/{symbol}` (line 2448, 2463)
8. `/api/scanner/quick-scan` (line 3106)
9. `/api/cached-price-data/{symbol}` (line 3542)

### Endpoints calling `get_gex_profile()` (/gex/gammaOI - strike-level data):
1. `/api/gex/{symbol}/levels` (line 498)
2. `/api/gamma/{symbol}/intelligence` (line 634)

## Frontend Pages and Their API Calls

### On Initial Site Load (homepage `/`):
- None directly, but may load components

### GEX Analysis Page (`/gex`):
**Per ticker on page load:**
- `GET /api/gex/SPY` → 1x get_net_gamma()
- User expands: `GET /api/gex/SPY/levels` → 1x get_gex_profile()

### Gamma Page (`/gamma`):
**On page load:**
- `GET /api/gamma/SPY/intelligence?vix=20` → 1x get_net_gamma() + 1x get_gex_profile()
- WebSocket connection opens: `ws://api/ws/market-data?symbol=SPY`

### Psychology Page (`/psychology`):
**On page load:**
- `GET /api/psychology/current-regime` → 1x get_net_gamma()
- `GET /api/psychology/rsi-analysis/SPY` → 2x get_net_gamma()
- `GET /api/psychology/liberation-setups` → 1x get_net_gamma()
- `GET /api/psychology/false-floors` → 1x get_net_gamma()
**Total: 5 API calls**

### Scanner Page (`/scanner`):
**On page load:**
- `GET /api/scanner/quick-scan` → 1x get_net_gamma() per ticker

## Background Processes

### Autonomous Trader (runs on backend startup):
- Checks every 5 minutes during market hours
- Calls `get_net_gamma()` for analysis
- **Estimate: 12 calls/hour during market hours**

### WebSocket Connections:
- Real-time market data
- May reconnect on page navigation
- Unknown call frequency

## CALCULATED TOTAL ON WEEKEND

### Scenario: User opens site and navigates to all pages

1. **GEX page load**: 1 call (get_net_gamma for SPY)
2. **Gamma page load**: 2 calls (get_net_gamma + get_gex_profile)
3. **Psychology page load**: 5 calls (various get_net_gamma)
4. **Scanner (3 tickers)**: 3 calls

**TOTAL: 11 API calls in ~30 seconds**

**Weekend limit: 2 calls/minute**
**Time needed: 11 calls ÷ 2/min = 5.5 minutes**

## THE PROBLEM

On weekend, the entire site needs 5.5 minutes to load because of the 2/min rate limit.

Every page navigation triggers new API calls. Circuit breaker activates after 2 calls, blocks for 60s+.

## ROOT CAUSE

**The application was designed for 20/min weekday limits, not 2/min weekend limits.**

Every endpoint independently calls the API without coordination. No global rate limiter tracks calls across all endpoints.

## SOLUTION NEEDED

1. **Global rate limiter** that tracks calls across ALL endpoints
2. **Request queue** that respects 2/min limit
3. **Aggressive caching** (hours, not minutes) on weekends
4. **Batch requests** where possible
5. **Disable background jobs** on weekends
