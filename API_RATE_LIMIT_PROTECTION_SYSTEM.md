# API Rate Limit Protection System

## Problem Statement

**Trading Volatility API Limit**: 20 calls/minute (shared across ALL users and deployments)

**Current Issues**:
- Multiple users hitting refresh simultaneously
- Auto-refresh timers violating limits
- No coordination between Vercel, Streamlit, and local deployments
- Each user unaware of others' API usage
- Scanner batch operations consuming entire quota

**Result**: Circuit breaker activating, Psychology Trap Detection fails

---

## Solution: Multi-Layer Protection System

### Layer 1: Frontend - Eliminate Auto-Refresh

#### Remove All Auto-Refresh Timers
```typescript
// ❌ BAD - Auto-refresh every 30s
useEffect(() => {
  const interval = setInterval(() => {
    fetchData()  // Violates rate limit!
  }, 30000)
  return () => clearInterval(interval)
}, [])

// ✅ GOOD - Manual refresh only
<button onClick={fetchData}>
  Refresh Data
</button>
```

#### Implement Manual Refresh with Cooldown
```typescript
const [canRefresh, setCanRefresh] = useState(true)
const [cooldownSeconds, setCooldownSeconds] = useState(0)

const handleRefresh = async () => {
  if (!canRefresh) return

  setCanRefresh(false)
  setCooldownSeconds(60)

  await fetchData()

  // 60-second cooldown per user
  const timer = setInterval(() => {
    setCooldownSeconds(prev => {
      if (prev <= 1) {
        clearInterval(timer)
        setCanRefresh(true)
        return 0
      }
      return prev - 1
    })
  }, 1000)
}

// UI
<button disabled={!canRefresh} onClick={handleRefresh}>
  {canRefresh ? 'Refresh' : `Wait ${cooldownSeconds}s`}
</button>
```

### Layer 2: Backend - Request Queue System

#### Implementation Plan

**File: `api_request_queue.py`**
```python
import time
import threading
from queue import PriorityQueue
from typing import Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(order=True)
class APIRequest:
    priority: int
    timestamp: float = field(compare=False)
    user_id: str = field(compare=False)
    endpoint: str = field(compare=False)
    params: Dict = field(compare=False)
    callback: Callable = field(compare=False)

class APIRequestQueue:
    """
    Global request queue for Trading Volatility API
    Enforces 20 calls/minute limit across ALL users
    """

    def __init__(self):
        self.queue = PriorityQueue()
        self.lock = threading.Lock()

        # Rate limiting
        self.calls_per_minute = 20
        self.min_seconds_between_calls = 3  # 20 calls/min = 1 call per 3s
        self.last_call_time = 0
        self.calls_this_minute = []

        # Circuit breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_until = 0

        # Per-user limits
        self.user_last_request = {}
        self.user_min_interval = 10  # Min 10s between requests per user

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def enqueue(self, user_id: str, endpoint: str, params: Dict,
                priority: int = 5, callback: Callable = None):
        """
        Add request to queue
        Priority: 1 (highest) to 10 (lowest)
        - 1-3: High (Psychology, critical user-facing)
        - 4-6: Medium (GEX data, gamma intelligence)
        - 7-10: Low (scanner, historical data)
        """

        # Check per-user rate limit
        if user_id in self.user_last_request:
            time_since_last = time.time() - self.user_last_request[user_id]
            if time_since_last < self.user_min_interval:
                wait_time = self.user_min_interval - time_since_last
                return {
                    'queued': False,
                    'error': f'Per-user rate limit. Wait {wait_time:.0f}s',
                    'retry_after': wait_time
                }

        request = APIRequest(
            priority=priority,
            timestamp=time.time(),
            user_id=user_id,
            endpoint=endpoint,
            params=params,
            callback=callback
        )

        self.queue.put(request)
        queue_position = self.queue.qsize()

        return {
            'queued': True,
            'position': queue_position,
            'estimated_wait': queue_position * 3  # 3 seconds per request
        }

    def _process_queue(self):
        """Worker thread - processes queue respecting rate limits"""
        while True:
            try:
                # Check circuit breaker
                if self.circuit_breaker_active:
                    if time.time() < self.circuit_breaker_until:
                        time.sleep(1)
                        continue
                    else:
                        self.circuit_breaker_active = False

                # Get next request
                request = self.queue.get(timeout=1)

                # Enforce rate limit
                current_time = time.time()

                # Clean old calls from tracking
                self.calls_this_minute = [
                    t for t in self.calls_this_minute
                    if current_time - t < 60
                ]

                # Check if we're at limit
                if len(self.calls_this_minute) >= self.calls_per_minute:
                    # Wait until oldest call is > 60s old
                    oldest_call = min(self.calls_this_minute)
                    wait_time = 60 - (current_time - oldest_call)
                    if wait_time > 0:
                        print(f"⚠️ Rate limit reached. Waiting {wait_time:.0f}s")
                        time.sleep(wait_time)

                # Wait minimum time between calls
                time_since_last = current_time - self.last_call_time
                if time_since_last < self.min_seconds_between_calls:
                    time.sleep(self.min_seconds_between_calls - time_since_last)

                # Make the API call
                self._execute_request(request)

                # Track the call
                self.last_call_time = time.time()
                self.calls_this_minute.append(self.last_call_time)
                self.user_last_request[request.user_id] = self.last_call_time

            except Exception as e:
                if "Empty" not in str(e):  # Ignore queue.Empty timeout
                    print(f"Queue worker error: {e}")
                time.sleep(0.1)

    def _execute_request(self, request: APIRequest):
        """Execute the API request"""
        try:
            # Import here to avoid circular dependency
            from core_classes_and_engines import TradingVolatilityAPI

            api = TradingVolatilityAPI()

            if 'gex/latest' in request.endpoint:
                result = api.get_net_gamma(request.params.get('symbol', 'SPY'))
            # ... handle other endpoints

            if request.callback:
                request.callback(result)

        except Exception as e:
            print(f"Error executing request: {e}")
            if "403" in str(e) or "rate limit" in str(e).lower():
                self._activate_circuit_breaker()

    def _activate_circuit_breaker(self):
        """Activate circuit breaker on rate limit"""
        self.circuit_breaker_active = True
        self.circuit_breaker_until = time.time() + 60
        print(f"🚨 Circuit breaker activated for 60s")

    def get_status(self):
        """Get current queue status"""
        current_time = time.time()
        self.calls_this_minute = [
            t for t in self.calls_this_minute
            if current_time - t < 60
        ]

        return {
            'queue_size': self.queue.qsize(),
            'calls_this_minute': len(self.calls_this_minute),
            'remaining_quota': self.calls_per_minute - len(self.calls_this_minute),
            'circuit_breaker_active': self.circuit_breaker_active,
            'estimated_wait_seconds': self.queue.qsize() * 3
        }

# Global instance
request_queue = APIRequestQueue()
```

### Layer 3: Backend - Batch Loading with Delays

#### Implement Incremental Loading

**Scanner Example:**
```python
@app.post("/api/scanner/scan-incremental")
async def scan_symbols_incremental(symbols: list[str]):
    """
    Scan symbols incrementally with rate limit protection
    Returns results as they come in via SSE (Server-Sent Events)
    """

    async def generate():
        for i, symbol in enumerate(symbols):
            # Queue the request with position
            queue_status = request_queue.enqueue(
                user_id=request.client.host,
                endpoint='/gex/latest',
                params={'symbol': symbol},
                priority=7  # Low priority for scanner
            )

            if queue_status['queued']:
                yield f"data: {json.dumps({
                    'symbol': symbol,
                    'status': 'queued',
                    'position': i + 1,
                    'total': len(symbols),
                    'estimated_wait': queue_status['estimated_wait']
                })}\n\n"

                # Wait for result (simplified - use callback in production)
                time.sleep(queue_status['estimated_wait'])

                # Get result and send
                # ...
            else:
                yield f"data: {json.dumps({
                    'symbol': symbol,
                    'status': 'rate_limited',
                    'error': queue_status['error']
                })}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Layer 4: Frontend - Progressive Loading UI

**React Component with SSE:**
```typescript
const ScannerWithQueue = () => {
  const [results, setResults] = useState<ScanResult[]>([])
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)

  const startScan = async (symbols: string[]) => {
    const eventSource = new EventSource(`/api/scanner/scan-incremental?symbols=${symbols.join(',')}`)

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.status === 'queued') {
        setQueueStatus({
          current: data.position,
          total: data.total,
          estimatedWait: data.estimated_wait
        })
      } else if (data.status === 'completed') {
        setResults(prev => [...prev, data.result])
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
    }
  }

  return (
    <div>
      {queueStatus && (
        <ProgressBar
          value={queueStatus.current}
          max={queueStatus.total}
          label={`Scanning ${queueStatus.current}/${queueStatus.total} - Est. ${queueStatus.estimatedWait}s`}
        />
      )}

      {results.map(result => (
        <ResultCard key={result.symbol} data={result} />
      ))}
    </div>
  )
}
```

### Layer 5: Cross-Deployment Coordination

**Use Redis for Shared State (if available):**
```python
import redis

class DistributedRateLimiter:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379)
        self.key = 'trading_volatility_api_calls'

    def check_and_increment(self):
        """Check if we can make a call, increment if yes"""
        pipe = self.redis.pipeline()

        # Get calls in last 60s
        now = time.time()
        pipe.zremrangebyscore(self.key, 0, now - 60)
        pipe.zcard(self.key)
        pipe.zadd(self.key, {str(now): now})
        pipe.expire(self.key, 60)

        results = pipe.execute()
        call_count = results[1]

        return call_count < 20
```

**Alternative: Designate Primary Instance:**
- Mark one deployment (e.g., Vercel) as "primary"
- Others query primary for data instead of hitting API directly
- Primary manages the rate limit centrally

---

## Implementation Priority

### Phase 1: Immediate (Today)
1. ✅ Remove all auto-refresh timers from frontend
2. ✅ Add manual refresh with 60s cooldown
3. ✅ Show "Loading from cache" indicators
4. ✅ Add queue status display

### Phase 2: Backend Queue (Tomorrow)
1. ⏳ Implement APIRequestQueue class
2. ⏳ Update all endpoints to use queue
3. ⏳ Add /api/queue-status endpoint
4. ⏳ Test with multiple simultaneous users

### Phase 3: Incremental Loading (Week 1)
1. ⏳ Implement SSE for scanner
2. ⏳ Add progressive loading UI
3. ⏳ Show real-time queue position
4. ⏳ Add "pause/resume" controls

### Phase 4: Multi-Deployment (Week 2)
1. ⏳ Set up Redis (or alternate coordination)
2. ⏳ Implement distributed rate limiter
3. ⏳ Configure primary/secondary pattern
4. ⏳ Add deployment health monitoring

---

## Quick Wins (Can Implement Right Now)

### 1. Disable Auto-Refresh Everywhere
```bash
# Find all auto-refresh code
grep -r "setInterval\|setTimeout.*fetch" frontend/src/
grep -r "useEffect.*interval" frontend/src/
```

### 2. Add "Last Updated" Timestamp
```typescript
<div className="text-sm text-gray-500">
  Last updated: {lastUpdate.toLocaleTimeString()}
  <button onClick={refresh}>Refresh</button>
</div>
```

### 3. Show Cache Status
```typescript
<Badge color={isCached ? 'green' : 'yellow'}>
  {isCached ? 'From Cache (30min)' : 'Fresh Data'}
</Badge>
```

### 4. Add Request Budget Display
```typescript
const [budget, setBudget] = useState<RateLimitStatus | null>(null)

useEffect(() => {
  fetch('/api/rate-limit-status')
    .then(r => r.json())
    .then(setBudget)
}, [])

return (
  <div className="rate-limit-indicator">
    API Quota: {budget?.remaining}/20 calls remaining
    {budget?.remaining < 5 && <Alert>Low API quota!</Alert>}
  </div>
)
```

---

## Monitoring & Alerts

### Add Logging
```python
# Log every API call with user info
logger.info(f"API call: {endpoint} | User: {user_id} | Queue: {queue_size} | Quota: {remaining}/20")
```

### Create Dashboard
```
/api/admin/rate-limit-dashboard
- Real-time call rate graph
- Per-user usage breakdown
- Queue size over time
- Circuit breaker events
- Cache hit rate
```

---

## User Communication

### Add Banner When Rate Limited
```typescript
{rateLimitActive && (
  <Banner type="warning">
    ⚠️ API rate limit reached. Your request is queued (position #{queuePosition}).
    Estimated wait: {estimatedWait}s. Please avoid refreshing.
  </Banner>
)}
```

### Add "API Health" Indicator
```typescript
<StatusIndicator status={apiHealth}>
  {apiHealth === 'healthy' && '🟢 API: Healthy'}
  {apiHealth === 'rate_limited' && '🟡 API: Rate Limited'}
  {apiHealth === 'down' && '🔴 API: Down'}
</StatusIndicator>
```

---

## Testing Plan

### Simulate Multiple Users
```python
import threading

def simulate_user(user_id):
    for i in range(10):
        response = requests.get(f'/api/gex/SPY?user_id={user_id}')
        print(f"User {user_id} call {i}: {response.status_code}")
        time.sleep(5)

# Simulate 5 users
threads = [threading.Thread(target=simulate_user, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
```

### Verify Queue Works
```bash
# Make 25 requests rapidly (exceeds 20/min limit)
for i in {1..25}; do
  curl "http://localhost:8000/api/gex/SPY?user_id=test$i" &
done
wait

# Check queue status
curl http://localhost:8000/api/queue-status
```

---

**Created**: 2025-11-08
**Priority**: CRITICAL
**Owner**: Engineering Team
**Status**: Design Complete - Ready for Implementation
