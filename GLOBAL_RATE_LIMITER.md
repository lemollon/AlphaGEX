# Global Rate Limiter - Complete Solution

## Overview

The AlphaGEX application now has a **global rate limiter** that automatically detects weekends vs weekdays and applies the correct Trading Volatility API limits across ALL endpoints.

## The Problem (Before)

- Application was designed for weekday limits (20 calls/minute)
- On weekends, the API limit is **2 calls/minute** (10x stricter)
- Every page navigation triggered 5-11 API calls
- Site needed 5.5 minutes to fully load on weekends
- Circuit breaker activated repeatedly
- Site was effectively unusable on weekends

## The Solution (Now)

### 1. **Dynamic Rate Limiting**

The rate limiter now auto-detects:
- **Weekend (Sat/Sun)**: 2 calls/minute
- **Weekday trading hours (9:30am-4pm ET)**: 2 calls/minute (realtime data)
- **Weekday non-trading hours**: 18 calls/minute (safety margin from 20/min)

### 2. **Smart Caching Strategy**

Cache duration is now dynamic based on market status:
- **Weekend**: 24 hours (market closed, data doesn't change)
- **Weekday trading hours**: 5 minutes (active market, data changes frequently)
- **Weekday non-trading hours**: 4 hours (market closed, minimal changes)

### 3. **Global Coordination**

ALL Trading Volatility API calls go through a single global rate limiter instance:
- Thread-safe queue manages all requests
- No endpoint can exceed the limit
- Requests wait automatically if quota exceeded
- Circuit breaker prevents cascading failures

## How It Works

### Rate Limiter (`rate_limiter.py`)

```python
# Global instance with dynamic limits
trading_volatility_limiter = RateLimiter(
    dynamic_limits=True,       # Auto-detect weekend/weekday
    max_calls_per_hour=800     # Safety limit
)
```

**Auto-detection:**
1. Gets current time in Eastern Time (market timezone)
2. Checks day of week (0=Monday, 6=Sunday)
3. If Saturday/Sunday → 2 calls/minute
4. If weekday:
   - Trading hours (9:30am-4pm) → 2 calls/minute
   - Non-trading hours → 18 calls/minute

### Integration in `core_classes_and_engines.py`

Every API call in `TradingVolatilityAPI` uses the rate limiter:

```python
# Use intelligent rate limiter if available
if RATE_LIMITER_AVAILABLE:
    if not trading_volatility_limiter.wait_if_needed(timeout=60):
        print("❌ Rate limit timeout - circuit breaker active")
        return {'error': 'rate_limit'}
```

### Caching Strategy

```python
def _get_cache_duration(self) -> int:
    # Weekend: 24 hours
    if day_of_week >= 5:
        return 86400

    # Weekday trading hours: 5 minutes
    if market_open <= current_time < market_close:
        return 300

    # Weekday non-trading hours: 4 hours
    return 14400
```

## Current Status (Sunday, Nov 9, 2025)

```
=== Trading Volatility Rate Limiter Status ===
Current Time (ET): 2025-11-09 21:44:52 EST
Day: Sunday (day_of_week=6)
Is Weekend: True
Current Rate Limit: 2 calls/minute ✅
Cache Duration: 86400 seconds (24 hours) ✅
```

## Expected Behavior

### Weekend Navigation (Current)

**Scenario**: User opens site and navigates to all pages

1. **First page load**:
   - Makes 1-2 API calls
   - Rate limiter enforces 30-second wait between calls
   - User sees: `⏱️ Rate limit: waiting 30.0s | 2/2 calls/min | Sunday (WEEKEND - 2/min limit)`

2. **Subsequent pages**:
   - Data served from 24-hour cache
   - No new API calls needed
   - Pages load instantly

**Result**: Site is fully usable on weekends with proper expectations set

### Weekday Navigation (Off-Hours)

**Scenario**: User browses site at 8pm ET on Monday

1. **First navigation**: Makes API calls at 18/min rate (very fast)
2. **Cache**: 4-hour TTL means minimal refetching
3. **User experience**: Smooth, fast loading

### Weekday Navigation (Trading Hours)

**Scenario**: User browses site at 2pm ET on Monday

1. **Rate limit**: 2 calls/minute (same as weekend)
2. **Cache**: Only 5-minute TTL (fresher data during active market)
3. **Trade-off**: Slower page loads but fresher data

## Endpoints Using Rate Limiter

All endpoints that call Trading Volatility API are now coordinated:

### Aggregate Data (`get_net_gamma()`):
1. `/api/gex/{symbol}` (GEX Analysis)
2. `/api/gamma/{symbol}/intelligence` (Gamma Intelligence)
3. `/api/psychology/current-regime` (Psychology Regime)
4. `/api/psychology/rsi-analysis/{symbol}` (RSI Analysis)
5. `/api/psychology/liberation-setups` (Liberation Setups)
6. `/api/psychology/false-floors` (False Floors)
7. `/api/psychology/trap/{symbol}` (Psychology Trap)
8. `/api/scanner/quick-scan` (Scanner)
9. `/api/cached-price-data/{symbol}` (Price Data)

### Strike-Level Data (`get_gex_profile()`):
1. `/api/gex/{symbol}/levels` (GEX Levels - now manual expand only)
2. `/api/gamma/{symbol}/intelligence` (Gamma Intelligence)

## Monitoring

### View Rate Limiter Stats

```bash
curl http://localhost:8001/api/rate-limiter-stats
```

Returns:
```json
{
  "calls_last_minute": 2,
  "calls_last_hour": 15,
  "max_calls_per_minute": 2,
  "max_calls_per_hour": 800,
  "remaining_minute": 0,
  "remaining_hour": 785,
  "total_calls": 42,
  "total_blocked": 0,
  "total_delayed": 8,
  "utilization_minute": 100.0,
  "utilization_hour": 1.88
}
```

### Console Output

When rate limit is hit:
```
⏱️ Rate limit: waiting 30.0s | 2/2 calls/min | Sunday (WEEKEND - 2/min limit)
```

When cache is used:
```
✅ Using cached GEX data for SPY (cache TTL: 1440 min)
```

## Testing

Run the test suite:

```bash
python3 rate_limiter.py
```

Check current status:

```bash
python3 -c "
from rate_limiter import trading_volatility_limiter
import pytz
from datetime import datetime

limiter = trading_volatility_limiter
et_tz = pytz.timezone('America/New_York')
now_et = datetime.now(et_tz)

print(f'Day: {now_et.strftime(\"%A\")}')
print(f'Current Limit: {limiter.max_calls_per_minute} calls/minute')
print(f'Stats: {limiter.get_stats()}')
"
```

## Benefits

1. ✅ **No more circuit breaker spam** - Requests queue properly
2. ✅ **Weekend usability** - Aggressive caching = instant page loads
3. ✅ **Weekday optimization** - Higher limits when available
4. ✅ **Transparent operation** - Clear console messages
5. ✅ **Global coordination** - All endpoints respect same limits
6. ✅ **Automatic adaptation** - No manual configuration needed
7. ✅ **Trading hour awareness** - Appropriate limits during market hours

## Deployment

The rate limiter is already integrated and will automatically activate on Render:

1. **Rate limiter imports** in `core_classes_and_engines.py` (line 20)
2. **All API calls** use `trading_volatility_limiter.wait_if_needed()`
3. **Cache durations** adjust automatically based on day/time
4. **No environment variables** needed - works out of the box

## Future Enhancements

Potential improvements:
1. Priority queue (e.g., user requests > background jobs)
2. Request batching for multiple symbols
3. Predictive prefetching during low-traffic hours
4. Admin dashboard for real-time monitoring
5. Configurable limits via environment variables

## Summary

**Before**: Site unusable on weekends (11 calls needed, 2/min limit = 5.5 minutes)

**After**:
- First 2 API calls: 30 seconds
- Remaining pages: Instant (served from 24-hour cache)
- Total time: ~30 seconds vs 5.5 minutes

**Status**: ✅ **Global rate limiter fully operational**
