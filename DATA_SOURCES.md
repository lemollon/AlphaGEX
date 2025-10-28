# Data Sources for Paper Trader V2

## 📊 Real Market Data - No Mocks!

### 1. **GEX Data**: Trading Volatility API (Already Integrated)

**Source**: Your Trading Volatility API subscription
**Endpoint**: `https://stocks.tradingvolatility.net/api/gex/latest`
**What we get**:
- ✅ Net GEX (actual dealer gamma positioning)
- ✅ Flip Point (zero gamma level)
- ✅ Call Wall / Put Wall (if available)
- ✅ Put/Call Ratio
- ✅ Implied Volatility

**Code**: `core_classes_and_engines.py` → `TradingVolatilityAPI.get_net_gamma()`

```python
gex_data = api_client.get_net_gamma('SPY')
# Returns REAL data:
# {
#     'net_gex': -2.5e9,  # -$2.5B actual dealer position
#     'flip_point': 580.50,  # Real flip point
#     'spot_price': 575.25,  # Current SPY price
#     ...
# }
```

---

### 2. **Option Prices**: Yahoo Finance (FREE via yfinance)

**Source**: Yahoo Finance Options Chain API
**Library**: `yfinance` (already installed)
**What we get**:
- ✅ **Real Bid/Ask/Last prices** (NOT calculated, actual market prices!)
- ✅ **Volume & Open Interest** (actual trading activity)
- ✅ **Implied Volatility** (market-derived IV)
- ✅ **Delta, Gamma** (if available from Yahoo)
- ✅ **Contract Symbols** (actual tradeable contracts like "SPY250124C00575000")

**Code**: `paper_trader_v2.py` → `get_real_option_price()`

```python
# Example: Get REAL price for SPY $575 Call expiring 2025-01-24
option_data = get_real_option_price('SPY', 575.0, 'call', '2025-01-24')

# Returns REAL market data:
# {
#     'bid': 12.50,  # Real bid price
#     'ask': 12.65,  # Real ask price
#     'last': 12.58,  # Last traded price
#     'volume': 1250,  # Real volume
#     'open_interest': 8500,  # Real OI
#     'implied_volatility': 0.18,  # Market IV (18%)
#     'contract_symbol': 'SPY250124C00575000'  # Actual contract
# }
```

**Why Yahoo Finance?**
- ✅ **FREE** (no additional subscription needed)
- ✅ **Real-time** during market hours (15-min delay after hours)
- ✅ **Accurate** - same prices you see on broker platforms
- ✅ **Complete** - includes all strikes and expirations
- ✅ **Reliable** - used by millions of traders

---

### 3. **Spot Price**: Yahoo Finance

**Source**: Yahoo Finance ticker data
**What we get**:
- ✅ Current SPY price
- ✅ Intraday high/low
- ✅ Volume

**Code**: Already integrated via yfinance in options chain fetch

---

## 🔄 How It All Works Together

### Step 1: Daily Trade Finder Runs

```python
# 1. Get REAL GEX data from Trading Volatility
gex_data = api_client.get_net_gamma('SPY')
# → Returns: net_gex, flip_point, spot_price

# 2. Analyze market regime
if net_gex < -1e9 and spot < flip:
    strategy = "SQUEEZE LONG CALLS"  # Dealers short gamma below flip
elif net_gex > 2e9:
    strategy = "IRON CONDOR"  # High positive GEX = range-bound
# ... more logic
```

### Step 2: Get REAL Option Prices

```python
# 3. Calculate target strike based on GEX analysis
strike = round(flip_point / 5) * 5  # Round to $5 increment

# 4. Get REAL market prices from Yahoo Finance
option_data = get_real_option_price('SPY', strike, 'call', expiration)
# → Returns: REAL bid/ask/last prices

# 5. Use MID price for entry (bid + ask) / 2
entry_price = (option_data['bid'] + option_data['ask']) / 2
```

### Step 3: Execute Trade

```python
# 6. Calculate position size based on $1M capital
quantity = calculate_quantity(capital=1000000, max_pct=0.05, entry_price=entry_price)

# 7. Store position with REAL data
position = {
    'entry_price': entry_price,  # REAL mid price
    'entry_bid': option_data['bid'],  # REAL bid
    'entry_ask': option_data['ask'],  # REAL ask
    'contract_symbol': 'SPY250124C00575000',  # REAL contract
    'entry_iv': option_data['implied_volatility'],  # REAL IV
    'reasoning': detailed_analysis  # Why we made this trade
}
```

---

## 💡 Why This Is Better Than Mocks

### Old Way (V1 - Mocks):
```python
# ❌ Used Black-Scholes formula to ESTIMATE price
price = black_scholes_call(spot, strike, dte, iv, rate)
# Problems:
# - Not real market price
# - Doesn't account for bid/ask spread
# - IV is guessed, not market-derived
# - No actual contract to trade
```

### New Way (V2 - Real Data):
```python
# ✅ Get ACTUAL market price from Yahoo Finance
price_data = yfinance.get_option_price(...)
entry_price = (price_data['bid'] + price_data['ask']) / 2
# Benefits:
# - REAL bid/ask spread
# - REAL market IV
# - Actual tradeable contract
# - Matches what you'd pay on broker
```

---

## 📋 Data Sources Summary Table

| Data Type | Source | API | Cost | Update Frequency |
|-----------|--------|-----|------|------------------|
| **GEX** | Trading Volatility | Your subscription | Paid | Daily (pre-market) |
| **Option Prices** | Yahoo Finance | yfinance library | FREE | Real-time (15-min delay) |
| **Spot Price** | Yahoo Finance | yfinance library | FREE | Real-time |
| **IV** | Yahoo Finance | Options chain | FREE | Real-time |
| **Volume/OI** | Yahoo Finance | Options chain | FREE | Real-time |

---

## 🔧 No Additional APIs Needed!

You already have everything:
- ✅ Trading Volatility API (already configured in `st.secrets`)
- ✅ Yahoo Finance (via `yfinance` library, already installed)
- ✅ SPY data (available on Yahoo Finance for free)

**Total additional cost**: $0

---

## 📖 Example: Full Trade Flow with Real Data

```python
# Morning: Find daily trade

# 1. Get GEX (Trading Volatility API)
gex = api_client.get_net_gamma('SPY')
# → net_gex: -2.1B, flip: 580, spot: 576

# Analysis: Negative GEX below flip = SQUEEZE potential

# 2. Get REAL option prices (Yahoo Finance)
strike = 580  # At flip point
exp_date = '2025-01-24'  # Next Friday

option = get_real_option_price('SPY', 580, 'call', exp_date)
# → {
#     'bid': 4.20,
#     'ask': 4.35,
#     'last': 4.28,
#     'volume': 2500,
#     'open_interest': 12000,
#     'iv': 0.16,
#     'contract': 'SPY250124C00580000'
# }

# 3. Entry price = mid
entry = (4.20 + 4.35) / 2 = $4.275

# 4. Position size
capital = $1,000,000
max_position = 5% = $50,000
cost_per_contract = $4.275 * 100 = $427.50
quantity = $50,000 / $427.50 = 116 contracts

# 5. Execute
# Buy 116 SPY 01/24/25 $580 Calls @ $4.275
# Total cost: $49,995
# Contract: SPY250124C00580000

# 6. Reasoning stored:
"""
TRADE THESIS:
Dealers SHORT gamma (-$2.1B). When SPY moves up toward flip ($580),
dealers must BUY stock to hedge → accelerates rally.

TECHNICAL:
Net GEX: -$2.1B (NEGATIVE)
Spot: $576
Flip: $580 (+0.7% away)

TARGET: $580 (flip point)
STOP: $574 (-0.3%)

REAL ENTRY: $4.275 mid (bid: $4.20, ask: $4.35)
CONTRACT: SPY250124C00580000
IV: 16%
"""
```

---

## ✅ Data Accuracy Verification

To verify data is real, check:

1. **Option Prices**: Compare with TD Ameritrade, Robinhood, or any broker
   - Yahoo prices should match within $0.05 (bid/ask spread)

2. **Contract Symbols**: Search on any options platform
   - Example: "SPY250124C00580000" is a real, tradeable contract

3. **GEX Data**: Cross-reference with tradingvolatility.net dashboard
   - Values should match exactly

---

## 🚀 Ready to Use!

All data sources are configured and ready:
- No additional API keys needed
- No additional subscriptions required
- Just run the Daily Trade Finder!

**Code files**:
- `paper_trader_v2.py` - Engine with real data integration
- `paper_trading_dashboard_v2.py` - UI to display and execute trades
- Data sources: Trading Volatility API + Yahoo Finance (yfinance)

**Total setup time**: 0 minutes (everything already works!)

---

## ⚠️ Yahoo Finance Rate Limiting & Alternative Data Sources

### Current Rate Limiting Issues

Yahoo Finance (via yfinance) has rate limits that can cause issues during:
- Multi-symbol scanning
- Rapid consecutive requests
- Peak market hours

**Current Implementation** (`intelligence_and_strategies.py` lines 100-158):
- Max retries: 3 attempts
- Exponential backoff: 2s → 5s → 10s
- 5-minute response cache
- Error detection for HTTP 429 (Too Many Requests)

### Alternative Options Data Providers

If you experience persistent rate limiting, consider these alternatives:

#### 1. **Interactive Brokers (IBKR) API**
**Cost**: Free with IBKR account (requires margin account)
**Data Quality**: Excellent (direct from exchange)
**Rate Limits**: Generous for account holders
**Setup Complexity**: Medium (requires TWS/Gateway running)

**Pros**:
- Real-time data with no delays
- Very accurate bid/ask spreads
- Low rate limits for account holders
- Can execute actual trades

**Cons**:
- Requires IBKR account
- Must run TWS or IB Gateway locally
- More complex API authentication

**Implementation**: Use `ib_insync` library
```python
pip install ib_insync

from ib_insync import IB, Stock, Option
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # TWS paper trading port

# Get option chain
contract = Stock('SPY', 'SMART', 'USD')
chains = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
```

---

#### 2. **Polygon.io**
**Cost**: $29-$199/month (options data on Premium+ plan)
**Data Quality**: Excellent (aggregated from multiple exchanges)
**Rate Limits**: Generous (100+ requests/min on paid plans)
**Setup Complexity**: Easy (REST API)

**Pros**:
- Professional-grade data
- Historical data included
- Good rate limits
- Simple REST API

**Cons**:
- Monthly subscription cost
- Options data requires Premium+ plan ($199/mo)

**Implementation**:
```python
pip install polygon-api-client

from polygon import RESTClient
client = RESTClient(api_key="YOUR_API_KEY")

# Get option contract
snapshot = client.get_snapshot_option(
    "SPY",
    option_contract="O:SPY250124C00580000"
)
```

---

#### 3. **Alpaca Markets**
**Cost**: Free tier available, Unlimited plan $99/month
**Data Quality**: Good (consolidated from multiple sources)
**Rate Limits**: 200 requests/min (free), unlimited (paid)
**Setup Complexity**: Easy (REST API)

**Pros**:
- Free tier available
- Good documentation
- Can execute trades
- WebSocket streaming available

**Cons**:
- Free tier has limited historical data
- Options data quality varies

**Implementation**:
```python
pip install alpaca-trade-api

import alpaca_trade_api as tradeapi
api = tradeapi.REST('YOUR_API_KEY', 'YOUR_SECRET_KEY', base_url='https://paper-api.alpaca.markets')

# Get option chain
options = api.list_options_contracts(underlying_symbol='SPY')
```

---

#### 4. **CBOE DataShop**
**Cost**: Varies (enterprise pricing)
**Data Quality**: Excellent (direct from CBOE)
**Rate Limits**: High (enterprise-grade)
**Setup Complexity**: High (requires enterprise agreement)

**Pros**:
- Highest quality data (direct from CBOE)
- Official exchange data
- Historical data available

**Cons**:
- Expensive (enterprise pricing)
- Complex onboarding
- Overkill for most retail traders

---

### Recommended Approach: Hybrid Fallback System

For the best reliability, implement a fallback system:

**Priority Order**:
1. **Yahoo Finance** (free, try first)
2. **IBKR API** (if available and connected)
3. **Polygon.io** (if API key configured)
4. **Alpaca** (if API key configured)

**Implementation Pseudocode**:
```python
def get_options_chain_with_fallback(symbol):
    # Try Yahoo Finance first (free)
    try:
        return get_yahoo_options(symbol)
    except RateLimitError:
        st.warning("Yahoo Finance rate limited, trying IBKR...")

        # Try IBKR if connected
        if ibkr_is_connected():
            try:
                return get_ibkr_options(symbol)
            except Exception as e:
                st.warning(f"IBKR failed: {e}")

        # Try Polygon if API key exists
        if polygon_api_key:
            try:
                return get_polygon_options(symbol)
            except Exception as e:
                st.warning(f"Polygon failed: {e}")

        # Try Alpaca as last resort
        if alpaca_api_key:
            return get_alpaca_options(symbol)

        # All failed
        raise Exception("All options data sources failed")
```

---

### Rate Limiting Best Practices

To minimize rate limiting with Yahoo Finance:

1. **Increase cache duration** (current: 5 minutes)
   ```python
   # In intelligence_and_strategies.py line 96
   cache_duration = 300  # Increase to 600 (10 minutes) or 900 (15 minutes)
   ```

2. **Batch requests** - Request multiple expirations at once instead of individual strikes

3. **Add request throttling** - Enforce minimum delay between requests
   ```python
   import time
   last_request_time = 0
   min_delay = 1.0  # 1 second between requests

   def throttled_request():
       global last_request_time
       elapsed = time.time() - last_request_time
       if elapsed < min_delay:
           time.sleep(min_delay - elapsed)
       last_request_time = time.time()
       return make_request()
   ```

4. **Use session-wide caching** - Store results in `st.session_state` to avoid re-fetching

5. **Limit concurrent users** - If self-hosting, rate limiting affects all users sharing the same IP

---

### Current Status

✅ **Implemented**: Yahoo Finance with retry logic and caching
⚠️ **Not Implemented**: Alternative data sources (IBKR, Polygon, Alpaca)
💡 **Recommendation**: For production use with multiple users, consider adding Polygon.io or IBKR as fallback

**Files to Modify for Fallback**:
- `intelligence_and_strategies.py` - `RealOptionsChainFetcher` class (line 83+)
- `config_and_database.py` - Add API keys for alternative sources
- `.streamlit/secrets.toml` - Store API credentials securely
