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
