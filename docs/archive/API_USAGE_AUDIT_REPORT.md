# TradingVolatilityAPI Usage Audit Report
**Generated:** 2025-10-25
**Codebase:** AlphaGEX Trading System

---

## Executive Summary

This report provides a comprehensive audit of all TradingVolatilityAPI usage across the AlphaGEX codebase. The system makes **2-3 API calls per dashboard refresh** (optimized), but can make **10+ calls** during multi-symbol scans and **dozens of calls** when managing multiple positions.

### Current Rate Limiting
- **Rate limit:** 2 seconds between calls
- **Cache duration:** 30 seconds
- **Implementation:** `/home/user/AlphaGEX/core_classes_and_engines.py` lines 1027-1063

### Key Findings
✅ **Good:** Dashboard refresh is optimized (2-3 calls)
⚠️ **Concern:** Multi-symbol scanner makes 2 calls per symbol (10 calls for 5 symbols)
🚨 **Risk:** Position management makes 1 call per position (N×M calls across features)
✅ **Good:** Historical data is lazy-loaded (only on button click)

---

## Files That Call TradingVolatilityAPI

### 1. **core_classes_and_engines.py** (API Definition)
**Location:** `/home/user/AlphaGEX/core_classes_and_engines.py`

**API Methods Defined:**
- Line 1148: `get_net_gamma(symbol)` - Fetch aggregate GEX metrics
- Line 1240: `get_gex_profile(symbol)` - Fetch strike-level gamma data
- Line 1406: `get_historical_gamma(symbol, days_back)` - Fetch historical GEX
- Line 1516: `get_skew_data(symbol)` - Fetch skew/IV metrics
- Line 1573: `get_historical_skew(symbol, days_back)` - Fetch historical skew

**Rate Limiting Implementation:**
- Line 1035: `_wait_for_rate_limit()` - Enforces 2 second delay between calls
- Line 1047-1063: Cache system - 30 second cache duration

---

### 2. **gex_copilot.py (main.py)** - Main Dashboard
**Location:** `/home/user/AlphaGEX/gex_copilot.py`

**API Call Locations:**

#### Dashboard Refresh (Lines 246-297)
**Optimized flow:**
```python
# Line 250: Try gammaOI first
profile_data = api_client.get_gex_profile(symbol)

# Line 253-267: If gammaOI includes aggregate data, skip get_net_gamma!
if 'aggregate_from_gammaOI' in profile_data:
    # Use aggregate data - NO additional call needed!
    gex_data = {...aggregate data...}
else:
    # Line 270: Fallback to separate call
    gex_data = api_client.get_net_gamma(symbol)

# Line 280: Always fetch skew
skew_data = api_client.get_skew_data(symbol)
```
**Total: 2 calls (optimized) or 3 calls (fallback)**

#### Day-Over-Day Trends (Line 529) - LAZY LOADED
```python
# Only called when user clicks "Load Yesterday's Data" button
yesterday_data = api_client.get_yesterday_data(symbol)  # 1 call
```
**Total: 1 call (only when button clicked)**

#### Historical Charts (Lines 648-649) - LAZY LOADED
```python
# Only called when user clicks "Load Historical Data" button
gamma_history = api_client.get_historical_gamma(symbol, days_back=30)  # 1 call
skew_history = api_client.get_historical_skew(symbol, days_back=30)   # 1 call
```
**Total: 2 calls (only when button clicked)**

#### Trading Plan Generation (Line 970)
```python
plan_data = api_client.get_net_gamma(plan_symbol)  # 1 call
```
**Total: 1 call**

#### Open Position Updates (Line 220)
```python
# For each open paper trading position
gex_data = api_client.get_net_gamma(pos['symbol'])  # 1 call per position
```
**Total: 1 call × N positions**

#### Gamma Tracking Snapshot (Lines 458-459)
```python
gex_data = api_client.get_net_gamma(symbol)   # 1 call
skew_data = api_client.get_skew_data(symbol)  # 1 call
```
**Total: 2 calls (only when user clicks "Capture Snapshot")**

---

### 3. **autonomous_paper_trader.py** - Autonomous Trader
**Location:** `/home/user/AlphaGEX/autonomous_paper_trader.py`

#### Daily Trade Search (Lines 235-236)
```python
gex_data = api_client.get_net_gamma('SPY')   # 1 call
skew_data = api_client.get_skew_data('SPY')  # 1 call
```
**Total: 2 calls (once per day)**

#### Position Management (Line 505)
```python
# For each open autonomous position
gex_data = api_client.get_net_gamma('SPY')  # 1 call per position check
```
**Total: 1 call × N positions × M checks per day**

---

### 4. **multi_symbol_scanner.py** - Multi-Symbol Scanner
**Location:** `/home/user/AlphaGEX/multi_symbol_scanner.py`

#### Scanner (Lines 106-107)
```python
# For each symbol in watchlist
gex_data = api_client.get_net_gamma(symbol)   # 1 call
skew_data = api_client.get_skew_data(symbol)  # 1 call
```
**Total: 2 calls × N symbols**

**Cache system:** 5 minute cache (Line 87)
**Delay between symbols:** 0.5 seconds (Line 138)

---

### 5. **position_management_agent.py** - Position Monitoring
**Location:** `/home/user/AlphaGEX/position_management_agent.py`

#### Monitor All Positions (Line 265)
```python
# For each active position
current_gex = api_client.get_net_gamma(symbol)  # 1 call per position
```
**Total: 1 call × N positions**

---

### 6. **paper_trader_v2.py** - Paper Trader V2
**Location:** `/home/user/AlphaGEX/paper_trader_v2.py`

#### Daily Trade Finder (Lines 464-465)
```python
gex_data = api_client.get_net_gamma('SPY')   # 1 call
skew_data = api_client.get_skew_data('SPY')  # 1 call
```
**Total: 2 calls**

---

### 7. **paper_trading_dashboard.py** - Paper Trading UI
**Location:** `/home/user/AlphaGEX/paper_trading_dashboard.py`

#### Update Position Values (Line 220)
```python
# For each open position
gex_data = api_client.get_net_gamma(pos['symbol'])  # 1 call per position
```
**Total: 1 call × N positions**

#### Gamma Snapshot (Lines 458-459)
```python
gex_data = api_client.get_net_gamma(symbol)   # 1 call
skew_data = api_client.get_skew_data(symbol)  # 1 call
```
**Total: 2 calls (only when button clicked)**

---

## Estimated API Calls by Workflow

### 1. Main Dashboard Refresh (Single Symbol)
**Trigger:** User clicks "Refresh" button in sidebar

| Call | Count | Cached? |
|------|-------|---------|
| `get_gex_profile()` | 1 | ✅ 30s |
| `get_net_gamma()` (fallback) | 0-1 | ✅ 30s |
| `get_skew_data()` | 1 | ✅ 30s |
| **TOTAL** | **2-3 calls** | |

**Cache benefit:** Subsequent refreshes within 30s = **0 calls**

---

### 2. Multi-Symbol Scanner
**Trigger:** User clicks "Scan Watchlist" button

**Default watchlist:** 5 symbols (SPY, QQQ, IWM, DIA, TSLA)

| Symbol | Calls | Notes |
|--------|-------|-------|
| SPY | 2 | `get_net_gamma()` + `get_skew_data()` |
| QQQ | 2 | `get_net_gamma()` + `get_skew_data()` |
| IWM | 2 | `get_net_gamma()` + `get_skew_data()` |
| DIA | 2 | `get_net_gamma()` + `get_skew_data()` |
| TSLA | 2 | `get_net_gamma()` + `get_skew_data()` |
| **TOTAL** | **10 calls** | |

**With cache:** If symbols scanned within 5 minutes = **0 calls** (cached)
**Delay between calls:** 0.5 seconds between symbols (total ~4.5s for 5 symbols)

**User watchlist expansion risk:**
- 10 symbols = 20 calls
- 20 symbols = 40 calls
- 50 symbols = 100 calls (⚠️ HIGH RISK!)

---

### 3. Autonomous Trader - Finding Daily Trade
**Trigger:** Once per day (automated)

| Call | Count | Cached? |
|------|-------|---------|
| `get_net_gamma('SPY')` | 1 | ✅ 30s |
| `get_skew_data('SPY')` | 1 | ✅ 30s |
| **TOTAL** | **2 calls** | |

**Frequency:** Once per trading day

---

### 4. Autonomous Trader - Managing Positions
**Trigger:** Every time "auto_manage_positions()" is called

**Per position check:**
- `get_net_gamma('SPY')` - 1 call
- Real option price fetch (yfinance, not Trading Volatility) - 0 calls

| Open Positions | Calls per Check | Daily Calls (4 checks/day) |
|----------------|-----------------|----------------------------|
| 1 | 1 | 4 |
| 3 | 3 | 12 |
| 5 | 5 | 20 |
| 10 | 10 | 40 |

**⚠️ Risk:** If user has 10 open positions and checks 4 times/day = **40 calls/day**

---

### 5. Position Management Agent - Monitor All
**Trigger:** User clicks "Check All Now" button

**Per active position:**
- `get_net_gamma(symbol)` - 1 call

| Active Positions | API Calls |
|------------------|-----------|
| 1 | 1 |
| 5 | 5 |
| 10 | 10 |

**Note:** This can monitor positions across multiple symbols (SPY, QQQ, etc.)

---

### 6. Paper Trading Dashboard - Update Positions
**Trigger:** Automatically when viewing "Open Positions" tab

**Per open position:**
- `get_net_gamma(symbol)` - 1 call

| Open Positions | API Calls |
|----------------|-----------|
| 1 | 1 |
| 5 | 5 |
| 10 | 10 |

**Cache benefit:** 30s cache reduces repeated calls

---

### 7. Historical Data Load (Lazy)
**Trigger:** User clicks "Load Historical Data" button

| Call | Count | Cached? |
|------|-------|---------|
| `get_historical_gamma(symbol, 30)` | 1 | ✅ 30s |
| `get_historical_skew(symbol, 30)` | 1 | ✅ 30s |
| **TOTAL** | **2 calls** | |

**Note:** This is lazy-loaded (button-click only), so it doesn't impact normal usage

---

## Potential API Limit Issues

### 🚨 HIGH RISK: Multi-Symbol Scanner with Large Watchlist
**Current behavior:**
- 2 calls per symbol × N symbols
- No delay between API endpoints (only between symbols)
- 5-minute cache helps but doesn't prevent initial burst

**Problem scenario:**
```
User adds 20 symbols to watchlist
→ Clicks "Scan Watchlist"
→ 20 symbols × 2 calls = 40 API calls in ~10 seconds
→ Even with 2-second rate limit, this takes 80 seconds minimum
→ User experience: Very slow scan
```

**Recommendation:**
- ✅ ALREADY IMPLEMENTED: 5-minute cache reduces repeated scans
- ✅ ALREADY IMPLEMENTED: 0.5s delay between symbols
- ⚠️ MISSING: No limit on watchlist size
- ⚠️ MISSING: No warning when scanning >10 symbols

---

### ⚠️ MEDIUM RISK: Position Management with Many Positions
**Current behavior:**
- 1 call per position per check
- Autonomous trader checks positions automatically
- Paper trading dashboard updates on tab view
- Position management agent checks on button click

**Problem scenario:**
```
User has 10 open positions
→ Autonomous trader checks 4 times/day = 40 calls
→ Paper trading updates on view = 10 calls
→ Position monitoring check = 10 calls
→ Total daily: 60+ calls just for position management
```

**Recommendation:**
- Batch position checks (check all positions at once, use same GEX data)
- Reduce auto-check frequency (4x/day → 2x/day)
- Add rate limiting between position checks

---

### ⚠️ MEDIUM RISK: Rapid Dashboard Refreshes
**Current behavior:**
- User can click "Refresh" repeatedly
- 2-3 calls per refresh
- 30-second cache helps

**Problem scenario:**
```
User refreshes 10 times in 2 minutes
→ First refresh: 2-3 calls
→ Next 9 refreshes within 30s: 0 calls (cached)
→ After 30s, another refresh: 2-3 calls
→ Reasonable behavior, cache works well
```

**Status:** ✅ WELL HANDLED by current cache

---

### ✅ LOW RISK: Historical Data Loading
**Current behavior:**
- Lazy-loaded (button click only)
- 2 calls per load
- 30-second cache

**Status:** ✅ WELL HANDLED - Users rarely click this

---

## Cache Effectiveness Analysis

### Current Cache Implementation
**Location:** `/home/user/AlphaGEX/core_classes_and_engines.py` lines 1047-1063

```python
def _get_cached_response(self, cache_key: str):
    """Get cached response if still valid"""
    if cache_key in self.response_cache:
        cached_data, timestamp = self.response_cache[cache_key]
        if time.time() - timestamp < self.cache_duration:  # 30 seconds
            return cached_data
    return None
```

### Cache Keys Used
- `gex/latest_{symbol}` - For `get_net_gamma()`
- `gex/gammaOI_{symbol}` - For `get_gex_profile()`
- `skew/latest_{symbol}` - For `get_skew_data()`

### Cache Duration Analysis
| Duration | Pros | Cons |
|----------|------|------|
| **Current: 30s** | Good for rapid refreshes | May show stale data in volatile markets |
| Proposed: 60s | Fewer API calls | More stale data |
| Proposed: 15s | Fresher data | More API calls |

**Recommendation:** Keep 30s cache for most endpoints, but consider:
- Historical data: 5-minute cache (data doesn't change frequently)
- Position monitoring: 60s cache (positions don't need sub-minute updates)

---

## Recommendations for Rate Limiting Strategy

### 1. ✅ Keep Current Rate Limiting (GOOD)
**Current implementation is sound:**
- 2-second delay between API calls
- 30-second response cache
- Cache-first approach

**No changes needed here.**

---

### 2. 🔧 Add Watchlist Size Limit
**Problem:** Users can add unlimited symbols → scanner makes 2N calls

**Proposed solution:**
```python
# In multi_symbol_scanner.py display_watchlist_manager()
MAX_WATCHLIST_SIZE = 20

if len(st.session_state.watchlist) >= MAX_WATCHLIST_SIZE:
    st.warning(f"⚠️ Watchlist limit reached ({MAX_WATCHLIST_SIZE} symbols)")
    st.info("💡 Large watchlists make many API calls. Remove symbols to add new ones.")
    # Disable "Add" button
else:
    # Allow adding symbols
```

**Benefit:** Prevents users from creating 50+ symbol watchlists that trigger 100 API calls per scan

---

### 3. 🔧 Batch Position Monitoring
**Problem:** Checking 10 positions = 10 separate API calls

**Proposed solution:**
```python
def auto_manage_positions(self, api_client):
    """Batch all positions using same API call"""

    # Group positions by symbol
    positions_by_symbol = {}
    for pos in open_positions:
        symbol = pos['symbol']
        if symbol not in positions_by_symbol:
            positions_by_symbol[symbol] = []
        positions_by_symbol[symbol].append(pos)

    # One API call per unique symbol (not per position!)
    for symbol, positions in positions_by_symbol.items():
        gex_data = api_client.get_net_gamma(symbol)  # 1 call for ALL positions in this symbol

        # Update all positions for this symbol
        for pos in positions:
            self._check_and_update_position(pos, gex_data)
```

**Benefit:** 10 SPY positions = 1 API call (instead of 10)

---

### 4. 🔧 Add API Call Budget UI
**Problem:** Users don't know how many API calls they're making

**Proposed solution:**
Add to sidebar:
```python
st.sidebar.divider()
st.sidebar.subheader("📊 API Usage")

# Show estimated calls for current session
estimated_calls = calculate_session_calls()
st.sidebar.metric("API Calls This Session", estimated_calls)
st.sidebar.caption("💡 Rate limit: 2s between calls")
st.sidebar.caption(f"💡 Cache duration: 30s")

# Show what triggers calls
with st.sidebar.expander("What uses API calls?"):
    st.markdown("""
    - **Dashboard refresh:** 2-3 calls
    - **Scanner (5 symbols):** 10 calls
    - **Position check:** 1 call per position
    - **Historical load:** 2 calls
    """)
```

**Benefit:** User awareness prevents accidental API abuse

---

### 5. 🔧 Increase Cache for Historical Data
**Problem:** Historical data doesn't change frequently but uses same 30s cache

**Proposed solution:**
```python
# In TradingVolatilityAPI.__init__()
self.cache_duration = 30  # Default 30s
self.historical_cache_duration = 300  # 5 minutes for historical data

def get_historical_gamma(self, symbol: str, days_back: int = 5):
    cache_key = self._get_cache_key('gex/history', symbol)

    # Check cache with LONGER duration
    if cache_key in self.response_cache:
        cached_data, timestamp = self.response_cache[cache_key]
        if time.time() - timestamp < self.historical_cache_duration:  # 5 min instead of 30s
            return cached_data

    # ... rest of implementation
```

**Benefit:** Historical charts can be loaded multiple times without hitting API

---

### 6. 🔧 Add Progressive Rate Limiting
**Problem:** Rapid successive calls can still hit API even with 2s delay

**Proposed solution:**
```python
class TradingVolatilityAPI:
    def __init__(self):
        # ... existing code ...
        self.call_count_window = []  # Track recent calls
        self.max_calls_per_minute = 20  # Budget: 20 calls/minute

    def _check_rate_budget(self):
        """Check if we're within our rate budget"""
        import time
        current_time = time.time()

        # Remove calls older than 1 minute
        self.call_count_window = [t for t in self.call_count_window if current_time - t < 60]

        # Check if we've hit our budget
        if len(self.call_count_window) >= self.max_calls_per_minute:
            wait_time = 60 - (current_time - self.call_count_window[0])
            raise Exception(f"⚠️ API rate budget exceeded. Please wait {wait_time:.0f} seconds.")

        # Record this call
        self.call_count_window.append(current_time)

    def get_net_gamma(self, symbol: str):
        self._check_rate_budget()  # Check budget before call
        self._wait_for_rate_limit()  # Existing rate limit
        # ... rest of implementation
```

**Benefit:** Hard limit prevents runaway API usage even if user clicks rapidly

---

### 7. 🔧 Add Scanner Throttling
**Problem:** Scanner can make 40+ calls when scanning large watchlist

**Proposed solution:**
```python
# In multi_symbol_scanner.py scan_symbols()

# Add adaptive delay based on watchlist size
def scan_symbols(symbols: List[str], api_client, force_refresh: bool = False):
    # Calculate delay to stay under 20 calls/minute
    total_calls_needed = len(symbols) * 2
    safe_delay = max(0.5, (60 / 20))  # 3 seconds per symbol to stay under 20 calls/min

    st.info(f"💡 Scanning {len(symbols)} symbols ({total_calls_needed} API calls). This will take ~{len(symbols) * safe_delay / 60:.1f} minutes.")

    for idx, symbol in enumerate(symbols):
        # ... existing scan logic ...

        # Adaptive delay (longer for large watchlists)
        if len(symbols) > 10:
            time.sleep(safe_delay)  # 3s delay for >10 symbols
        else:
            time.sleep(0.5)  # 0.5s delay for small watchlists
```

**Benefit:** Large scans are slower but don't hit rate limits

---

## Summary of Recommendations

| Priority | Recommendation | Benefit | Effort |
|----------|---------------|---------|--------|
| 🔴 HIGH | Add watchlist size limit (20 symbols max) | Prevents 100+ call scans | Low |
| 🔴 HIGH | Batch position monitoring (1 call per symbol, not per position) | Reduces position checks by 90% | Medium |
| 🟡 MEDIUM | Add API call budget UI | User awareness | Low |
| 🟡 MEDIUM | Increase historical cache to 5 minutes | Reduces historical loads | Low |
| 🟡 MEDIUM | Add progressive rate limiting (20 calls/min hard limit) | Prevents runaway usage | Medium |
| 🟢 LOW | Add scanner throttling for large watchlists | Improves UX for large scans | Low |

---

## Current Rate Limiting Settings

### Rate Limit Configuration
**File:** `/home/user/AlphaGEX/core_classes_and_engines.py`

```python
# Line 1029: Minimum time between API calls
self.min_request_interval = 2.0  # 2 seconds between requests

# Line 1033: Response cache duration
self.cache_duration = 30  # Cache responses for 30 seconds
```

### Assessment
✅ **2-second rate limit is GOOD** - Reasonable for most use cases
✅ **30-second cache is GOOD** - Balances freshness vs API load
⚠️ **No per-minute budget** - Could still make 30 calls/minute if cache misses
⚠️ **No watchlist limit** - Users can trigger 100+ calls with large watchlists

---

## Estimated Daily API Usage (Typical User)

**Assumptions:**
- 1 user
- 5 symbols in watchlist
- 3 open positions
- Normal usage pattern

| Activity | Frequency | Calls per Activity | Daily Total |
|----------|-----------|-------------------|-------------|
| Dashboard refresh | 10 times/day | 2-3 calls | 25 calls |
| Multi-symbol scan | 3 times/day | 10 calls | 30 calls |
| Autonomous trader daily search | 1 time/day | 2 calls | 2 calls |
| Autonomous trader position checks | 4 times/day | 3 calls (3 positions) | 12 calls |
| Historical data load | 1 time/day | 2 calls | 2 calls |
| **TOTAL DAILY** | | | **~71 calls** |

**With cache working optimally:** ~50 calls/day

**Heavy user (10 positions, 20 symbols, 20 refreshes):** ~200 calls/day

---

## Conclusion

### Current State Assessment
✅ **Dashboard is well-optimized** - 2-3 calls with good caching
✅ **Historical data is lazy-loaded** - Low impact
✅ **Rate limiting exists** - 2s delay and 30s cache
⚠️ **Multi-symbol scanner needs limits** - Can trigger 100+ calls
⚠️ **Position management is inefficient** - N calls for N positions instead of batching

### Top Priorities
1. **Add watchlist size limit (20 max)** - Prevents API abuse
2. **Batch position monitoring** - Massive efficiency gain
3. **Add API usage UI** - User awareness prevents issues

### API Limit Risk Score
**Overall Risk:** 🟡 **MEDIUM**

**Risk breakdown:**
- Normal usage: ✅ LOW RISK (~50 calls/day)
- Power usage: ⚠️ MEDIUM RISK (~200 calls/day)
- Abuse scenario: 🚨 HIGH RISK (1000+ calls/day if user scans 50 symbols repeatedly)

**With recommended changes:** ✅ LOW RISK across all scenarios

---

## Files Reference

All API calls are made through `TradingVolatilityAPI` class defined in:
- `/home/user/AlphaGEX/core_classes_and_engines.py` (lines 1007-1620)

Files that make API calls:
1. `/home/user/AlphaGEX/gex_copilot.py` - Main dashboard (6 calls in various workflows)
2. `/home/user/AlphaGEX/autonomous_paper_trader.py` - Autonomous trading (3 calls)
3. `/home/user/AlphaGEX/multi_symbol_scanner.py` - Scanner (2 calls per symbol)
4. `/home/user/AlphaGEX/position_management_agent.py` - Position monitoring (1 call per position)
5. `/home/user/AlphaGEX/paper_trader_v2.py` - Paper trading (2 calls)
6. `/home/user/AlphaGEX/paper_trading_dashboard.py` - Paper trading UI (3 calls)

Total: **6 files** making **18 total API call occurrences** across all workflows

---

## Next Steps

1. Review this report with development team
2. Prioritize HIGH priority recommendations
3. Implement watchlist size limit (quick win)
4. Refactor position monitoring to batch calls (bigger impact)
5. Add API usage monitoring UI (user education)
6. Test with heavy usage scenarios
7. Monitor actual API usage in production

**End of Report**
