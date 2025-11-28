# Psychology Trap Detection - Root Cause Analysis

**Date**: 2025-11-08
**Issue**: Psychology Trap Detection fails on first call
**Status**: ROOT CAUSE IDENTIFIED ✅

---

## 🎯 THE ROOT CAUSE

**Psychology endpoint makes ONLY ONE Trading Volatility API call** - it's NOT making multiple rapid calls.

**The real problem**: **Over-conservative rate limiting settings**

### Current Rate Limiter Settings

**File**: `core_classes_and_engines.py` line 1057

```python
_shared_min_request_interval = 20.0  # 20 SECONDS between requests
```

### The Math

- **Current setting**: 20 seconds between requests
- **Actual throughput**: 60 / 20 = **3 calls per minute**
- **API limit**: **20 calls per minute**
- **Utilization**: Only using 15% of available quota!

---

## 📊 Complete Flow Analysis

### When Psychology Page Loads:

```
1. User clicks Psychology Trap Detection
   ↓
2. Frontend calls: GET /api/psychology/current-regime?symbol=SPY
   ↓
3. Backend Psychology endpoint (backend/main.py:3102)
   ↓
4. Line 3120: gex_data = api_client.get_net_gamma(symbol)
   ↓
5. get_net_gamma (core_classes_and_engines.py:1269)
   ↓
6. Line 1280: Check cache (30 min TTL)
   ↓
7. IF CACHE MISS:
   ↓
8. Line 1288: _wait_for_rate_limit()
   ↓
9. WAITS 20 SECONDS if any call was made in last 20 seconds!
   ↓
10. Line 1291: Makes HTTP GET to Trading Volatility API /gex/latest
    ↓
11. Line 1344: Cache response for 30 minutes
    ↓
12. Lines 3165-3236: Fetch price data from Yahoo Finance (FREE, not Trading Volatility)
    ↓
13. Line 3345: Run psychology analysis (local computation)
    ↓
14. Return result to frontend
```

**Total Trading Volatility API Calls**: **ONLY 1** (if not cached)

**Total Yahoo Finance Calls**: 5 (one per timeframe - FREE, no quota)

---

## ❌ Why It Fails

### Scenario 1: User Navigating Between Pages

```
Time 0s:  User loads Dashboard
          → Calls get_net_gamma("SPY")
          → Success, cached for 30 min

Time 5s:  User clicks Psychology
          → Calls get_net_gamma("SPY")
          → Checks cache: HIT
          → Returns immediately
          → ✅ SUCCESS
```

**This works because cache is hit!**

### Scenario 2: Fresh Session (No Cache)

```
Time 0s:  User loads Psychology (fresh session, empty cache)
          → Calls get_net_gamma("SPY")
          → Cache MISS
          → _wait_for_rate_limit()
          → Last request was 0s ago
          → No wait needed
          → Makes API call
          → ✅ SUCCESS
```

**This works because it's the first call!**

### Scenario 3: Multiple Deployments + Multiple Users

```
VERCEL DEPLOYMENT (User A):
Time 0s:  Loads Dashboard → API call to get_net_gamma("SPY")

LOCAL DEPLOYMENT (You):
Time 2s:  Loads Psychology → API call to get_net_gamma("SPY")
          → BOTH deployments share the same API quota at Trading Volatility
          → If quota exhausted → 403 error
          → ❌ FAILS
```

**This fails because quota is shared across deployments!**

### Scenario 4: Scanner Running

```
Time 0s:  User runs Scanner on 10 symbols
          → Makes 10 API calls in sequence (20s interval each)
          → Total time: 10 × 20s = 200 seconds (3+ minutes)

Time 30s: User clicks Psychology while scanner running
          → Calls get_net_gamma("SPY")
          → _wait_for_rate_limit()
          → Last request was 10s ago
          → Must wait 10 more seconds
          → Then makes API call
          → Could timeout if frontend timeout < wait time
```

**This can fail due to slow response time!**

---

## 🔍 The Real Problem

### Issue #1: Over-Conservative Rate Limiting

```python
_shared_min_request_interval = 20.0  # TOO HIGH!
```

**Result**:
- Allows only 3 calls/min instead of 20 calls/min
- Wastes 85% of available quota
- Causes unnecessary delays

**Fix**: Reduce to 3-4 seconds for ~15-20 calls/min

### Issue #2: Shared Quota Across Deployments

- Trading Volatility API: 20 calls/min **TOTAL** across ALL deployments
- Vercel production: Uses quota
- Streamlit demo: Uses quota
- Local development: Uses quota
- **All compete for the same 20 calls/min**

**Current Status**:
- LOCAL: 0/20 calls/min (circuit breaker active)
- VERCEL: OFFLINE
- STREAMLIT: Unknown

**Fix**: Already implemented - aggressive caching (30 min)

### Issue #3: No Intelligent Fallback

When API quota is exhausted:
- Psychology returns error immediately
- No fallback to cached data (even if slightly stale)
- No queue system to retry

**Fix**: Already researched alternatives (Yahoo Finance), but user rejected mock data

---

## 📈 API Call Breakdown by Endpoint

### Psychology Trap Detection
- **Trading Volatility calls**: 1 (get_net_gamma)
- **Yahoo Finance calls**: 5 (price data, FREE)
- **Cache duration**: 30 minutes
- **Expected calls/hour**: 2 (if page reloaded every 30 min)

### Dashboard
- **Trading Volatility calls**: 1 (get_net_gamma)
- **Cache duration**: 30 minutes
- **Expected calls/hour**: 2

### Scanner
- **Trading Volatility calls**: N (one per symbol)
- **Cache duration**: 30 minutes per symbol
- **Expected calls/hour**: Depends on watchlist size

**Example**: 10 symbol scan with 20s interval:
- Time: 10 × 20s = 200 seconds (3.3 minutes)
- Calls: 10
- After scan: All cached for 30 min

---

## ✅ The Solution

### Option 1: Reduce Rate Limit Interval (RECOMMENDED)

**Change** `core_classes_and_engines.py` line 1057:

```python
# BEFORE
_shared_min_request_interval = 20.0  # Only 3 calls/min

# AFTER
_shared_min_request_interval = 3.0   # ~20 calls/min (with safety margin)
```

**Benefits**:
- ✅ Uses full API quota
- ✅ Faster response times
- ✅ Psychology loads immediately (if not cached)
- ✅ Scanner completes 6x faster

**Risks**:
- ⚠️ Could hit rate limit if multiple rapid requests
- ⚠️ Shared quota still an issue with multiple deployments

**Mitigation**: Combine with Option 2

### Option 2: Integrate New Rate Limiter (BEST)

**Use** `rate_limiter.py` created earlier:

```python
from rate_limiter import trading_volatility_limiter, rate_limited

@rate_limited(limiter=trading_volatility_limiter, timeout=60)
def get_net_gamma(self, symbol: str) -> Dict:
    # existing code
```

**Benefits**:
- ✅ Intelligent queuing (waits only when needed)
- ✅ Uses 15 calls/min (75% of quota, safe margin)
- ✅ Automatic backoff when rate limited
- ✅ Statistics tracking
- ✅ Thread-safe across all requests

**This is the BEST solution!**

### Option 3: Disable Other Deployments

**Temporarily**:
- Keep Vercel OFFLINE (already done)
- Disable Streamlit
- Only use Local development

**Benefits**:
- ✅ Full 20 calls/min for local
- ✅ No competition for quota

**Downsides**:
- ❌ Production (Vercel) is offline
- ❌ Not a long-term solution

---

## 🎯 Immediate Action Plan

### Step 1: Integrate rate_limiter.py ⏰ (5 minutes)

**File**: `core_classes_and_engines.py`

Add at top:
```python
from rate_limiter import trading_volatility_limiter
```

Modify `get_net_gamma` (line 1269):
```python
def get_net_gamma(self, symbol: str) -> Dict:
    """Fetch net gamma exposure data with intelligent rate limiting"""

    # Check cache first (before rate limiting)
    cache_key = self._get_cache_key('gex/latest', symbol)
    cached_data = self._get_cached_response(cache_key)
    if cached_data:
        return cached_data

    # Wait for rate limit slot
    if not trading_volatility_limiter.wait_if_needed(timeout=60):
        return {'error': 'rate_limit'}

    # Make API call
    # ... rest of existing code
```

### Step 2: Test Psychology Page ⏰ (2 minutes)

```bash
# Start backend if not running
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Open browser
http://localhost:3000/psychology

# Should load successfully!
```

### Step 3: Monitor API Usage ⏰ (1 minute)

```bash
python3 deployment_monitor.py --mode monitor --duration 2
```

Expected result:
- ✅ Psychology loads < 5 seconds
- ✅ API calls stay under 15/min
- ✅ No rate limit errors

---

## 📊 Expected Performance After Fix

### Before (Current):
```
Psychology page load:
- First load: 2-5 seconds (cache miss)
- Reload within 30 min: < 1 second (cache hit)
- If other pages active: 20+ second wait
- API throughput: 3 calls/min (WASTED 85% of quota)
```

### After (With rate_limiter.py):
```
Psychology page load:
- First load: < 2 seconds (if quota available)
- Reload within 30 min: < 1 second (cache hit)
- If quota exhausted: Queues, waits max 60s
- API throughput: 15 calls/min (75% of quota, safe)
```

---

## 🔒 Long-Term Solutions

### 1. Request Additional API Keys from Trading Volatility
- Separate keys for production/staging/dev
- Each gets 20 calls/min quota
- **User rejected this option**

### 2. Switch to Alternative Data Source
- Yahoo Finance (FREE) + calculate GEX ourselves
- Polygon.io ($29/month, 500 calls/min)
- **User rejected Polygon.io option**
- **Yahoo Finance had dependency issues**

### 3. Keep Current Approach + Optimizations
- ✅ Aggressive caching (30 min) - DONE
- ✅ No auto-refresh on frontend - DONE
- ✅ Intelligent rate limiting - TO BE DONE
- ✅ Circuit breaker for protection - DONE

**This is the chosen approach!**

---

## ✅ Summary

**Question**: "Is it because the psychology page breaks the api limit on the first call?"

**Answer**: **NO** - Psychology makes ONLY ONE API call, not multiple rapid calls.

**The Real Issue**:
1. **Over-conservative rate limiting** (20s interval = only 3 calls/min instead of 20)
2. **Shared quota across deployments** (Vercel + Streamlit + Local all share 20 calls/min)
3. **When quota is exhausted** by other deployments/pages, Psychology gets 403 on first call

**The Fix**:
- Integrate `rate_limiter.py` with intelligent queuing
- Uses 15 calls/min (safe 75% of quota)
- Waits only when needed, queues requests properly
- Works across all endpoints

**Next Step**: Implement the fix (Step 1 above) and test!

---

**Created**: 2025-11-08
**Status**: Ready to implement fix
