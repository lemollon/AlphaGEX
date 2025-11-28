# Unknown Failure Investigation Report

## Executive Summary

The "unknown failure" issue is caused by **inadequate error handling and logging** throughout the codebase, particularly in `backend/main.py`. When errors occur, they are caught by generic exception handlers that don't provide sufficient context for debugging.

## UPDATE: Specific Failure Identified (2025-11-10)

**Yahoo Finance API Failure - CONFIRMED**

Logs show yfinance is completely broken with JSON parsing errors:
```
Failed to get ticker 'SPY' reason: Expecting value: line 1 column 1 (char 0)
SPY: No price data found, symbol may be delisted (period=90d)
```

**Impact:**
- ❌ RSI calculations failing (needs historical price data)
- ❌ VIX level fetching failing
- ❌ 0DTE tracking "a week behind" (no price updates)
- ❌ All multi-timeframe analysis broken

**Root Cause:** Yahoo Finance changed their API or is blocking requests. This is a recurring issue with yfinance.

**Solution:** See "Yahoo Finance API Failure" section below for fixes.

## Root Causes Identified

### 1. Generic Exception Handling (PRIMARY ISSUE)

**Location**: `backend/main.py` - Found **87+ instances** of problematic exception handling

**Pattern**:
```python
except:  # Bare except - catches everything, logs nothing
    pass

except Exception as e:  # Generic handler
    print(f"Error: {e}")  # Minimal context
    raise HTTPException(status_code=500, detail=str(e))
```

**Problems**:
- No stack traces captured
- No request context logged (symbol, parameters, etc.)
- No timing information
- No distinction between different error types
- Silent failures in background operations

**Examples from code**:
- Lines 310, 322, 330, 338, 346: Bare `except:` for RSI calculations
- Lines 376, 439, 472-474: Generic exception handlers without proper logging
- Line 1260: Bare `except:` that silently disables autonomous trader
- Lines 1029-1030: Bare `except:` in WebSocket connections

### 2. Known External Failures

Based on documentation analysis:

#### Trading Volatility API (403 Errors)
- **Status**: CONFIRMED in IMMEDIATE_ACTION_PLAN.md
- **Impact**: GEX charts, Psychology Trap Detection, Gamma Intelligence
- **Cause**: API key rejected by server
- **Error Message**: Often generic "Unknown error" (line 175 in multi_symbol_scanner.py)

#### Langchain Dependency
- **Status**: Fixed in recent commits
- **Historical Issue**: "Install langchain" error from deprecated imports
- **Current Status**: Should be resolved after merge

#### Backtest Results
- **Status**: Expected behavior (no failure)
- **Cause**: Backtests never executed
- **Solution**: Documented in RUN_BACKTESTS_ON_RENDER.md

### 3. Rate Limiting Complexity

**System**: Global rate limiter with dynamic weekend/weekday detection
- Weekend: 2 calls/minute
- Weekday trading hours: 2 calls/minute
- Weekday off-hours: 18 calls/minute

**Potential Failure Points**:
1. Circuit breaker activation (not logged clearly)
2. Rate limit timeouts (60s timeout, may appear as "unknown" to frontend)
3. Cache invalidation issues
4. Timezone conversion errors

### 4. Error Message Propagation Issues

**Pattern**: Default error messages hide real causes
```python
# From verify_api_access.py:80
error_msg = data.get('error', 'Unknown error') if data else 'No data returned'

# From multi_symbol_scanner.py:175
raise Exception(gex_data.get('error', 'Unknown error') if gex_data else 'Failed to fetch data')

# From gex_copilot.py:1501
st.warning(f"⚠️ Could not load gamma intelligence: {gamma_intel.get('error', 'Unknown error')}")
```

## Specific Failure Scenarios

### Scenario A: Silent API Failure
```
User Action: Navigate to GEX Analysis page
Expected: Chart loads with data
Actual: Empty state or "Unknown error"
Root Cause: Trading Volatility API returns 403, caught by generic handler
Log Output: "❌ Unexpected error fetching GEX for SPY: 403"
Missing Info: Request details, cache state, retry attempts
```

### Scenario B: Rate Limiter Timeout
```
User Action: Quick navigation through multiple pages
Expected: Data loads (possibly delayed)
Actual: Some endpoints return 500 errors
Root Cause: Rate limiter wait_if_needed() times out after 60s
Log Output: "❌ Rate limit timeout - circuit breaker active"
Missing Info: Queue depth, which endpoint triggered limit, user context
```

### Scenario C: Background Task Failure
```
System Action: Autonomous trader attempts daily trade
Expected: Trade executed and logged
Actual: No trade, status shows "UNKNOWN"
Root Cause: Exception in find_and_execute_daily_trade(), caught by bare except
Log Output: None (silent failure)
Missing Info: Everything
```

### Scenario D: Yahoo Finance API Failure (CONFIRMED 2025-11-10)
```
User Action: Navigate to any page requiring historical price data
Expected: RSI, VIX, and price charts display
Actual: Missing data, stale data, or empty charts
Root Cause: yfinance library getting empty/invalid responses from Yahoo
Log Output: "Failed to get ticker 'SPY' reason: Expecting value: line 1 column 1 (char 0)"
           "SPY: No price data found, symbol may be delisted (period=90d)"
Impact: RSI calculations fail, VIX unavailable, 0DTE tracker outdated
Affected Code: backend/main.py lines 306, 314, 326, 332, 340, 403
```

## Impact Analysis

### User Experience Impact
- **High**: Users see generic "Unknown error" messages
- **Medium**: Some failures are silent (autonomous trader, websockets)
- **Low**: Console logs provide minimal debugging context

### Development Impact
- **High**: Debugging requires extensive code review
- **Medium**: No centralized error tracking
- **Low**: Manual log analysis required

### Production Impact
- **Critical**: No structured logging for monitoring
- **High**: No alerting on specific error types
- **Medium**: Difficult to track failure rates

## Recommendations

### Immediate Actions (High Priority)

1. **Add Structured Logging**
```python
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

# Replace generic exception handlers with:
except HTTPException:
    raise
except Exception as e:
    logger.error(
        f"Error in endpoint_name",
        extra={
            'endpoint': request.url.path,
            'symbol': symbol,
            'error_type': type(e).__name__,
            'error_message': str(e),
            'stack_trace': traceback.format_exc(),
            'timestamp': datetime.utcnow().isoformat(),
            'user_agent': request.headers.get('user-agent', 'unknown')
        }
    )
    raise HTTPException(
        status_code=500,
        detail={
            'error': type(e).__name__,
            'message': str(e),
            'context': 'endpoint_name',
            'timestamp': datetime.utcnow().isoformat()
        }
    )
```

2. **Fix Bare Exception Handlers**
   - Replace all `except:` with specific exception types
   - At minimum use `except Exception as e:` with proper logging
   - Never use bare `except:` with `pass`

3. **Add Error Context to API Client**
```python
# In TradingVolatilityAPI class
def _make_request(self, endpoint, params):
    start_time = time.time()
    try:
        response = self._request(endpoint, params)
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"TradingVolatilityAPI request failed",
            extra={
                'endpoint': endpoint,
                'params': params,
                'duration_ms': int(duration * 1000),
                'error': str(e),
                'rate_limiter_stats': trading_volatility_limiter.get_stats() if RATE_LIMITER_AVAILABLE else None
            }
        )
        raise
```

4. **Improve Frontend Error Display**
```typescript
// Instead of generic "Unknown error"
interface ApiError {
  error: string;
  message: string;
  context: string;
  timestamp: string;
  retry_after?: number;
}

// Show specific error types to users:
- RateLimitError → "API rate limit reached. Please wait 30 seconds."
- AuthenticationError → "API key invalid. Please check configuration."
- TimeoutError → "Request timed out. Please try again."
- NetworkError → "Connection failed. Please check your internet."
```

### URGENT: Fix Yahoo Finance API Failure (HIGH PRIORITY)

**Problem:** yfinance is getting empty responses from Yahoo Finance, causing JSON parsing errors.

**Immediate Solutions:**

1. **Update yfinance to latest version**
```bash
pip install --upgrade yfinance
```

Current version in requirements.txt: `yfinance>=0.2.28`
Latest version: 0.2.52+ (as of Nov 2025)

2. **Add retry logic with exponential backoff**
```python
# In backend/main.py, add helper function:
import time
from functools import wraps

def retry_yfinance(max_retries=3, delay=1):
    """Retry decorator for yfinance calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    error_str = str(e).lower()
                    if 'expecting value' in error_str or 'json' in error_str:
                        wait_time = delay * (2 ** attempt)
                        print(f"⚠️ yfinance error (attempt {attempt+1}/{max_retries}): {e}")
                        print(f"   Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
        return wrapper
    return decorator

# Apply to ticker.history calls:
@retry_yfinance(max_retries=3, delay=2)
def fetch_price_history(ticker, period, interval="1d"):
    data = ticker.history(period=period, interval=interval)
    if data.empty:
        raise ValueError(f"No data returned for period={period}")
    return data
```

3. **Add better error handling**
```python
# Replace lines 306, 314, 326, 332, 340, 403 in backend/main.py:
try:
    ticker = yf.Ticker(symbol)
    df_1d = fetch_price_history(ticker, period="90d", interval="1d")
    rsi_1d = calculate_rsi(df_1d)
    if rsi_1d is not None:
        rsi_data['1d'] = round(float(rsi_1d), 1)
except ValueError as e:
    print(f"⚠️ No data available for RSI calculation: {e}")
    rsi_data['1d'] = None
except Exception as e:
    print(f"❌ yfinance error fetching 1d data: {type(e).__name__}: {e}")
    rsi_data['1d'] = None
```

4. **Consider alternative data sources as fallback**
```python
# Option A: Use Alpha Vantage (free tier: 25 calls/day)
import requests

def fetch_price_alpha_vantage(symbol, api_key):
    url = f"https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": api_key
    }
    response = requests.get(url, params=params)
    return response.json()

# Option B: Use Polygon.io (free tier: 5 calls/minute)
# Option C: Use Twelve Data (free tier: 800 calls/day)
```

5. **Add caching for price data**
```python
# Cache historical data to reduce yfinance calls
price_history_cache = {}
PRICE_CACHE_TTL = 3600  # 1 hour

def get_cached_price_history(symbol, period, interval="1d"):
    cache_key = f"{symbol}_{period}_{interval}"
    now = time.time()

    if cache_key in price_history_cache:
        data, timestamp = price_history_cache[cache_key]
        if now - timestamp < PRICE_CACHE_TTL:
            return data

    # Fetch new data
    ticker = yf.Ticker(symbol)
    data = fetch_price_history(ticker, period, interval)
    price_history_cache[cache_key] = (data, now)
    return data
```

**Quick Fix (Deploy Immediately):**

Update `requirements.txt`:
```
yfinance>=0.2.52
```

Then redeploy on Render. This alone may fix the issue if Yahoo changed their API format.

### Short-Term Actions (Medium Priority)

1. **Add Health Check Endpoint**
```python
@app.get("/api/health/detailed")
async def detailed_health():
    return {
        "api_keys": {
            "trading_volatility": api_key_configured,
            "anthropic": bool(os.getenv('ANTHROPIC_API_KEY'))
        },
        "rate_limiter": trading_volatility_limiter.get_stats(),
        "autonomous_trader": trader_available,
        "database": check_database_connection(),
        "external_apis": {
            "trading_volatility": test_api_connection(),
            "yahoo_finance": test_yahoo_connection()
        }
    }
```

2. **Add Error Tracking Service**
   - Integrate Sentry or similar service
   - Capture all uncaught exceptions
   - Group errors by type and context
   - Alert on error rate spikes

3. **Add Request ID Tracking**
```python
# Middleware to add request ID to all logs
import uuid

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    with logging_context(request_id=request_id):
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        return response
```

### Long-Term Actions (Low Priority)

1. **Implement Error Budget**
   - Track error rates by endpoint
   - Alert when thresholds exceeded
   - Display on monitoring dashboard

2. **Add Distributed Tracing**
   - OpenTelemetry integration
   - Track request flow through system
   - Identify bottlenecks

3. **Create Error Playbook**
   - Document common errors
   - Provide resolution steps
   - Include runbook for each error type

## Verification Steps

To identify the specific "unknown failure":

1. **Add debug logging to all exception handlers**:
```bash
# In backend/main.py, add at the top:
import logging
logging.basicConfig(level=logging.DEBUG)
```

2. **Monitor backend logs during failure**:
```bash
# If running locally:
tail -f backend.log | grep -i "error\|exception\|fail"

# If on Render:
# Go to Render dashboard → Service → Logs tab
# Filter for "ERROR" level
```

3. **Test each known failure point**:
```bash
# Test Trading Volatility API
curl "https://stocks.tradingvolatility.net/api/gex/latest?ticker=SPY&username=I-RWFNBLR2S1DP"

# Test Yahoo Finance / yfinance
python3 -c "
import yfinance as yf
ticker = yf.Ticker('SPY')
data = ticker.history(period='5d')
if not data.empty:
    print('✅ yfinance works')
else:
    print('❌ yfinance returns empty data')
"

# Test langchain import
python3 -c "from langchain_anthropic import ChatAnthropic; print('✅ langchain works')"

# Test database
python3 query_databases.py
```

4. **Check rate limiter status**:
```bash
curl http://localhost:8001/api/rate-limiter-stats
```

5. **Review frontend console**:
- Open browser DevTools
- Check Console tab for JavaScript errors
- Check Network tab for failed API requests
- Look for response body details

## Conclusion

The "unknown failure" has multiple root causes:

### 1. **Specific Failure Identified (2025-11-10)**: Yahoo Finance API Breakdown
   - **Status**: CONFIRMED - yfinance returning empty/invalid responses
   - **Impact**: RSI calculations, VIX data, 0DTE tracking all broken
   - **Fix**: Update yfinance to v0.2.52+, add retry logic, implement caching
   - **Priority**: **URGENT** - Deploy today

### 2. **Systemic Issue**: Inadequate Error Handling
   - **Status**: ONGOING - 87+ generic exception handlers hide real errors
   - **Impact**: Makes all failures appear "unknown"
   - **Fix**: Structured logging, fix bare `except:` statements
   - **Priority**: HIGH - Implement this week

### Immediate Action Plan

**TODAY (Critical):**
1. 🔥 Update `requirements.txt`: `yfinance>=0.2.52`
2. 🔥 Deploy to Render (auto-deploy on commit)
3. 🔥 Test RSI and VIX endpoints after deployment

**THIS WEEK (High Priority):**
1. ✅ Add retry logic for yfinance calls
2. ✅ Implement price data caching
3. ✅ Add structured logging to top 10 exception handlers
4. ✅ Fix bare `except:` in RSI calculation code (lines 310, 322, 330, 338, 346)

**THIS MONTH (Medium Priority):**
1. ✅ Fix all remaining bare `except:` statements (87+ instances)
2. ✅ Implement error tracking service (Sentry)
3. ✅ Add health check endpoint
4. ✅ Improve frontend error messages

**ONGOING:**
1. Monitor error rates by endpoint
2. Improve error messages based on user feedback
3. Document common errors in playbook

Once these improvements are in place, future failures will be **identifiable, debuggable, and resolvable** within minutes instead of requiring extensive investigation.

### Success Metrics

After fixes are deployed, you should see:
- ✅ RSI data loading correctly
- ✅ VIX levels displaying
- ✅ 0DTE tracker up to date
- ✅ No more "Expecting value: line 1 column 1" errors
- ✅ Clear, actionable error messages when failures occur
