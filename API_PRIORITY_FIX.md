# Trading Volatility API - Priority Queue Fix

## Problem Identified

Multiple AlphaGEX deployments (Vercel + Streamlit + local) are sharing the same API key `I-RWFNBLR2S1DP` and competing for the **20 calls/minute** limit.

### API Usage Audit Results:
- **19 API call sites** in backend alone
- Scanner: 1 call per symbol
- Strategies: 3 calls per comparison
- Gamma intelligence: 2 calls per symbol
- Psychology: 1 call per analysis

**Result**: Rate limit exceeded, circuit breaker activating, Psychology can't run.

## Immediate Solutions

### Option 1: Increase Cache Duration (Quick Win)
**Current**: 5 minutes
**Recommended**: 15-30 minutes for most endpoints

```python
# In core_classes_and_engines.py line 1067
_shared_cache_duration = 1800  # 30 minutes instead of 300
```

**Impact**: Reduces API calls by 6x for repeated requests

### Option 2: Implement Priority Levels
Create tiered priority for endpoints:
- **HIGH**: Psychology Trap Detection (user-facing, time-sensitive)
- **MEDIUM**: GEX analysis, Gamma intelligence
- **LOW**: Scanner, historical data, comparisons

### Option 3: Request Queue System
Implement FIFO queue with priority:
```python
class APIRequestQueue:
    def __init__(self):
        self.high_priority = []
        self.medium_priority = []
        self.low_priority = []

    def enqueue(self, request, priority='medium'):
        # Psychology gets high priority
        # Scanner gets low priority

    def process_queue(self):
        # Process high first, respect rate limits
```

### Option 4: Separate API Keys Per Deployment
Get multiple API keys from Trading Volatility:
- **Production (Vercel)**: Key A
- **Development (Streamlit)**: Key B
- **Local/Testing**: Key C

Each gets its own 20 calls/minute quota.

### Option 5: Treat 403 as Rate Limit
Update detection to treat any 403 after successful auth as rate limit:

```python
# In get_net_gamma(), line 1302
if response.status_code == 403:
    # Could be rate limit OR auth issue
    # If we've had successful calls before, assume rate limit
    if TradingVolatilityAPI._shared_api_call_count > 0:
        print(f"⚠️ 403 after successful calls - assuming rate limit")
        self._handle_rate_limit_error()
        return {'error': 'rate_limit'}
```

## Recommended Implementation Order

### Phase 1: Immediate (5 minutes)
1. ✅ Increase cache duration to 30 minutes
2. ✅ Treat 403 as potential rate limit after first successful call
3. ✅ Add rate limit headers to responses

### Phase 2: Short-term (1 hour)
1. ⏳ Implement priority queue
2. ⏳ Reserve 5 calls/minute for high-priority (psychology)
3. ⏳ Add queue status endpoint

### Phase 3: Long-term (1 day)
1. ⏳ Request additional API keys from Trading Volatility
2. ⏳ Implement per-deployment key routing
3. ⏳ Add API usage dashboard

## Testing Plan

```bash
# Test 1: Verify cache is working
curl http://localhost:8000/api/gex/SPY  # Call 1 - hits API
curl http://localhost:8000/api/gex/SPY  # Call 2 - from cache
curl http://localhost:8000/api/gex/SPY  # Call 3 - from cache

# Test 2: Verify priority works
# Start scanner (low priority, should queue)
# Call psychology (high priority, should skip queue)

# Test 3: Monitor rate limit handling
# Watch logs for circuit breaker messages
```

## Code Changes Needed

### File: `core_classes_and_engines.py`

**Change 1: Increase cache (line 1067)**
```python
_shared_cache_duration = 1800  # 30 minutes
```

**Change 2: Detect 403 as rate limit (line 1302)**
```python
if response.status_code == 403:
    if TradingVolatilityAPI._shared_api_call_count > 0:
        print(f"⚠️ 403 - treating as rate limit")
        self._handle_rate_limit_error()
        return {'error': 'rate_limit'}
```

**Change 3: Add priority parameter (line 1269)**
```python
def get_net_gamma(self, symbol: str, priority: str = 'medium') -> Dict:
    # Store priority for queue
    self._current_request_priority = priority
```

### File: `backend/main.py`

**Change: Mark psychology as high priority (line 3105)**
```python
gex_data = api_client.get_net_gamma(symbol, priority='high')
```

## Monitoring

Add these endpoints to track API health:

```python
@app.get("/api/rate-limit-status")
async def get_rate_limit_status():
    return {
        "calls_this_minute": TradingVolatilityAPI._shared_api_call_count_minute,
        "limit": 20,
        "remaining": 20 - TradingVolatilityAPI._shared_api_call_count_minute,
        "circuit_breaker_active": TradingVolatilityAPI._shared_circuit_breaker_active,
        "cache_size": len(TradingVolatilityAPI._shared_response_cache)
    }
```

---

**Created**: 2025-11-08
**Priority**: HIGH
**Impact**: Fixes Psychology Trap Detection + Scanner + All endpoints
