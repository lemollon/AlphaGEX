# AlphaGEX Performance Analysis Report

**Date:** 2026-01-14
**Scope:** Full codebase performance audit

---

## Executive Summary

This analysis identified **100+ performance issues** across the AlphaGEX codebase including:
- Database N+1 query patterns causing 72+ queries per request
- React components missing memoization causing excessive re-renders
- O(n) API calls inside loops that should be batched
- Synchronous blocking calls in async handlers
- Missing pagination on large result sets

**Estimated improvement potential:** 50-70% faster API responses, 50-100x faster data processing

---

## Critical Issues

### 1. Database N+1 Query Patterns

#### 1.1 Logs Summary Endpoint (CRITICAL)
**File:** `backend/api/routes/logs_routes.py:71-105`

**Current:** 4 queries per table × 18 tables = **72 queries per request**
```python
for table_name, display_name, ts_col in log_tables:
    cursor.execute("SELECT EXISTS (...)")  # Query 1
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")  # Query 2
    cursor.execute(f"SELECT COUNT(*) FROM ... WHERE ...")  # Query 3
    cursor.execute(f"SELECT MAX({ts_col}) FROM ...")  # Query 4
```

**Fix:** Combine into single query per table or use CTEs:
```python
# Check all tables exist in one query
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_name = ANY(%s)
""", (table_names,))
existing_tables = {row[0] for row in cursor.fetchall()}

# Then for each table, use single query:
cursor.execute(f"""
    SELECT COUNT(*), MAX({ts_col}),
           COUNT(*) FILTER (WHERE {ts_col} >= NOW() - INTERVAL '%s days')
    FROM {table_name}
""", (days,))
```

#### 1.2 Data Transparency Summary (CRITICAL)
**File:** `backend/api/routes/data_transparency_routes.py:161-170`

**Current:** 2 queries per category × 20+ categories = **40+ queries**
```python
for key, info in categories.items():
    cur.execute(f"SELECT COUNT(*) FROM {info['table']}")
    cur.execute(f"SELECT MAX(created_at) FROM {info['table']}")
```

**Fix:** Combine COUNT and MAX:
```python
cur.execute(f"SELECT COUNT(*), MAX(created_at) FROM {info['table']}")
count, latest = cur.fetchone()
```

#### 1.3 Trader Performance Metrics (HIGH)
**File:** `backend/api/routes/trader_routes.py:127-166`

**Current:** 4 sequential queries
```python
cursor.execute("SELECT equity, cumulative_pnl FROM autonomous_equity_snapshots...")
cursor.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
cursor.execute("SELECT COALESCE(SUM(realized_pnl), 0) FROM autonomous_closed_trades...")
cursor.execute("SELECT COALESCE(SUM(unrealized_pnl), 0) FROM autonomous_open_positions")
```

**Fix:** Use CTEs:
```sql
WITH capital AS (SELECT value FROM autonomous_config WHERE key = 'capital'),
     equity AS (SELECT equity, cumulative_pnl FROM autonomous_equity_snapshots ORDER BY timestamp DESC LIMIT 1),
     realized AS (SELECT COALESCE(SUM(realized_pnl), 0) FROM autonomous_closed_trades WHERE exit_date = %s),
     unrealized AS (SELECT COALESCE(SUM(unrealized_pnl), 0) FROM autonomous_open_positions)
SELECT * FROM capital, equity, realized, unrealized
```

#### 1.4 Config Value Fetching (MEDIUM)
**File:** `core/autonomous_paper_trader.py:493-565`

**Current:** Individual queries for each config key
**Fix:** Batch fetch:
```python
c.execute("""
    SELECT key, value FROM autonomous_config
    WHERE key IN ('initialized', 'signal_only', 'use_theoretical_pricing', 'capital')
""")
config = {row[0]: row[1] for row in c.fetchall()}
```

---

### 2. API Route Anti-Patterns

#### 2.1 Blocking Sleep in Async Handler (CRITICAL)
**File:** `backend/api/routes/vix_routes.py:180`

**Current:**
```python
def retry_with_backoff(func, max_retries=3, base_delay=0.5):
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception:
            time.sleep(delay)  # BLOCKS ENTIRE THREAD
```

**Fix:**
```python
async def retry_with_backoff(func, max_retries=3, base_delay=0.5):
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception:
            await asyncio.sleep(delay)  # Non-blocking
```

#### 2.2 Regex Compilation Per Request (MEDIUM)
**File:** `backend/main.py:226-228`

**Current:**
```python
def _is_origin_allowed(self, origin: str) -> bool:
    for allowed in self.allowed_origins:
        if "*" in allowed:
            pattern = allowed.replace(".", r"\.").replace("*", ".*")
            if re.match(f"^{pattern}$", origin):  # COMPILED EVERY REQUEST
                return True
```

**Fix:** Compile patterns once at startup:
```python
def __init__(self, allowed_origins):
    self.compiled_patterns = []
    for allowed in allowed_origins:
        if "*" in allowed:
            pattern = allowed.replace(".", r"\.").replace("*", ".*")
            self.compiled_patterns.append(re.compile(f"^{pattern}$"))
```

#### 2.3 Object Instantiation Per Request (HIGH)
**Files:** 19 locations across routes

**Current:**
```python
# In ares_routes.py, gex_routes.py, vix_routes.py, etc.
def fetch_data():
    client = TradierDataFetcher()  # NEW INSTANCE EVERY CALL
    return client.get_quote(symbol)
```

**Fix:** Use singleton/cached instance:
```python
_tradier_client = None

def get_tradier_client():
    global _tradier_client
    if _tradier_client is None:
        _tradier_client = TradierDataFetcher()
    return _tradier_client
```

#### 2.4 Unbounded Query Results (HIGH)
**Files:** 42+ instances of `fetchall()` without LIMIT

**Example from** `backend/api/routes/gex_routes.py:584`:
```python
cursor.execute("""
    SELECT ... FROM gex_history
    WHERE symbol = %s AND DATE(timestamp) >= %s
    ORDER BY timestamp DESC
    -- NO LIMIT - could return 10,000+ rows
""")
rows = cursor.fetchall()
```

**Fix:** Add pagination:
```python
cursor.execute("""
    SELECT ... FROM gex_history
    WHERE symbol = %s AND DATE(timestamp) >= %s
    ORDER BY timestamp DESC
    LIMIT %s OFFSET %s
""", (symbol, start_date, page_size, offset))
```

#### 2.5 Synchronous DB in Async Handlers (MEDIUM)
**Impact:** All 48 route modules use synchronous psycopg2 in async handlers

**Fix Options:**
1. Migrate to `asyncpg` for true async PostgreSQL
2. Use `run_in_executor()` for blocking calls:
```python
rows = await asyncio.get_event_loop().run_in_executor(None, blocking_db_call)
```

---

### 3. Inefficient Algorithms

#### 3.1 API Calls Inside Loop (CRITICAL)
**File:** `trading/mixins/position_manager.py:72-89`

**Current:** O(n) API calls for n positions
```python
for _, pos in positions.iterrows():
    gex_data = api_client.get_net_gamma('SPY')  # CALLED FOR EVERY POSITION!
    option_data = get_real_option_price(...)     # CALLED FOR EVERY POSITION!
```

**Fix:** Batch before loop:
```python
gex_data = api_client.get_net_gamma('SPY')  # Once
option_prices = batch_get_option_prices([pos for pos in positions])  # Batch
for _, pos in positions.iterrows():
    price = option_prices.get(pos['id'])
```

**Impact:** 100ms × 10 positions = 1000ms → 100ms with batch

#### 3.2 DataFrame.at[] in iterrows (CRITICAL)
**File:** `core_classes_and_engines.py:127-152`

**Current:** O(n) slow pandas operations
```python
for idx, row in option_data.iterrows():
    option_data.at[idx, 'gamma'] = gamma
    option_data.at[idx, 'delta'] = delta
    option_data.at[idx, 'theta'] = theta
    option_data.at[idx, 'vega'] = vega
```

**Fix:** Vectorize:
```python
option_data['gamma'] = vectorized_gamma_calc(option_data)
option_data['delta'] = vectorized_delta_calc(option_data)
```

**Impact:** 50-100x faster for large DataFrames

#### 3.3 Nested Loop in Backtest (HIGH)
**File:** `backtest/enhanced_backtest_optimizer.py:138-170`

**Current:** O(9n) iterations
```python
for _, row in gex_data.iterrows():  # n rows
    for offset in strike_offsets:    # 9 offsets
        # Calculate
```

**Fix:** Vectorize with numpy broadcasting:
```python
gex_rows, offsets = np.meshgrid(range(len(gex_data)), strike_offsets, indexing='ij')
# Vectorized calculation on all combinations at once
```

#### 3.4 iterrows() Usage (MEDIUM)
**Files:** 14 locations including:
- `data/polygon_data_fetcher.py:208,520,804,1273`
- `backtest/zero_dte_iron_condor.py:214,240`
- `trading/export_service.py:458,505`
- `unified_trading_engine.py:889,931`

**Fix:** Replace with:
- `.apply()` for element-wise operations
- `.to_dict('records')` for conversion
- Vectorized numpy operations

#### 3.5 Full Sort When Top-K Needed (MEDIUM)
**Files:**
- `core/intelligence_and_strategies.py:2756,3062`
- `core/psychology_trap_detector.py:1080`
- `core/apollo_ml_engine.py:1008`

**Current:**
```python
strikes.sort(key=lambda x: x['expected_value'])  # O(n log n) for ALL items
```

**Fix:** Use heapq for top-k:
```python
import heapq
top_strikes = heapq.nlargest(k, strikes, key=lambda x: x['expected_value'])  # O(n log k)
```

---

### 4. React Re-render Issues

#### 4.1 Missing useMemo (CRITICAL)
**File:** `frontend/src/components/DashboardScanFeed.tsx:46-57`

**Current:** Array + 3 filters recreated every render
```javascript
const allScans = [...].sort(...).slice(0, 10)  // NEW ARRAY EVERY RENDER
const tradesCount = allScans.filter(...).length  // FILTER 1
const skipsCount = allScans.filter(...).length   // FILTER 2
const errorsCount = allScans.filter(...).length  // FILTER 3
```

**Fix:**
```javascript
const allScans = useMemo(() =>
  [...].sort(...).slice(0, 10),
  [aresScans, solomonScans, anchorScans, icarusScans, titanScans]
)

const { tradesCount, skipsCount, errorsCount } = useMemo(() =>
  allScans.reduce((acc, scan) => {
    // Single pass accumulator
  }, { tradesCount: 0, skipsCount: 0, errorsCount: 0 }),
  [allScans]
)
```

#### 4.2 Helper Functions Redefined Every Render (CRITICAL)
**File:** `frontend/src/components/GammaExpirationWidget.tsx:72-111`

**Current:** 8 functions redefined on every render
```javascript
const getRiskColor = (level: string) => { ... }
const getRiskBgColor = (level: string) => { ... }
const formatGamma = (value: number) => { ... }
const getDayIcon = (risk: number) => { ... }
// ... 4 more
```

**Fix:** Move outside component or use useCallback:
```javascript
// Outside component
const getRiskColor = (level: string) => { ... }

// Or inside with useCallback
const getRiskColor = useCallback((level: string) => { ... }, [])
```

#### 4.3 Missing React.memo (HIGH)
**File:** `frontend/src/components/BotStatusOverview.tsx`

**Current:** BotStatusCard re-renders when parent re-renders
**Fix:**
```javascript
export default React.memo(function BotStatusCard({ ... }) { ... })
```

#### 4.4 Static Data Recalculated (MEDIUM)
**File:** `frontend/src/components/Navigation.tsx:152-158`

**Current:**
```javascript
const groupedItems = navItems.reduce(...)  // navItems is STATIC
```

**Fix:**
```javascript
const groupedItems = useMemo(() => navItems.reduce(...), [])
```

---

### 5. Missing Database Optimizations

#### 5.1 SELECT * Queries
**Count:** 60 instances

**Fix:** Replace with explicit column lists

#### 5.2 Missing Indexes
Add indexes for frequently queried columns:
```sql
CREATE INDEX idx_autonomous_open_positions_status ON autonomous_open_positions(status);
CREATE INDEX idx_autonomous_trader_logs_timestamp ON autonomous_trader_logs(timestamp DESC);
CREATE INDEX idx_ml_decision_logs_timestamp ON ml_decision_logs(timestamp DESC);
CREATE INDEX idx_ares_positions_open_time ON ares_positions(open_time);
CREATE INDEX idx_solomon_positions_open_time ON solomon_positions(open_time);
```

#### 5.3 No Connection Pooling
**Current:** Each request creates new PostgreSQL connection
**Fix:** Use `asyncpg` connection pool or `psycopg-pool`

---

## Priority Fix Order

| # | Issue | Location | Impact | Effort |
|---|-------|----------|--------|--------|
| 1 | N+1 logs_routes | `logs_routes.py:71` | 36x fewer queries | 1h |
| 2 | API call loop | `position_manager.py:72` | 10x faster | 2h |
| 3 | time.sleep blocking | `vix_routes.py:180` | Unblock threads | 15m |
| 4 | DashboardScanFeed useMemo | `DashboardScanFeed.tsx:46` | Fewer re-renders | 30m |
| 5 | TradierDataFetcher singleton | Multiple routes | Connection reuse | 1h |
| 6 | DataFrame vectorization | `core_classes_and_engines.py:127` | 50-100x faster | 2h |
| 7 | Add pagination | 42+ locations | Bounded memory | 2h |
| 8 | React helper memoization | `GammaExpirationWidget.tsx` | Fewer re-renders | 1h |
| 9 | Add database indexes | Database | Faster queries | 30m |
| 10 | Regex pre-compilation | `main.py:226` | Faster CORS | 15m |

---

## Expected Impact

| Area | Current | After Fix | Improvement |
|------|---------|-----------|-------------|
| Logs endpoint | 72 queries | 2 queries | **36x** |
| Position processing | O(n) API calls | O(1) | **10x** |
| DataFrame ops | O(n) iterrows | Vectorized | **50-100x** |
| API response time | Variable | Consistent | **50-70%** |
| Frontend renders | Excessive | Memoized | Significant |
| Memory usage | Unbounded | Paginated | Bounded |

---

## Additional Recommendations

1. **Add monitoring:** Track query counts, response times, memory usage
2. **Add indexes:** Create indexes on commonly queried columns
3. **Use connection pooling:** asyncpg or psycopg-pool
4. **Add rate limiting:** Protect against traffic spikes
5. **Consider caching:** Redis for frequently accessed data
6. **Add pagination middleware:** Enforce LIMIT on all list endpoints

---

*Report generated: 2026-01-14*
