# Alternative Data Sources for AlphaGEX

**Current**: Trading Volatility API ($99-299/month, 20 calls/min)
**Need**: GEX data, options flow, market data

---

## 🎯 What Data We Actually Need

### **Critical (Must Have)**:
1. **GEX Data** (Gamma Exposure by strike)
   - Net GEX, call GEX, put GEX
   - Strike-by-strike gamma
   - Flip point calculation

2. **Options Data**:
   - Open Interest by strike
   - Implied Volatility
   - Greeks (delta, gamma, vanna, charm)

3. **Price Data**:
   - Current spot price
   - Historical OHLCV
   - Multi-timeframe data for RSI

---

## 💰 Alternative Data Providers

### **1. Yahoo Finance (yfinance)** ✅ FREE
**What we can get**:
- ✅ Real-time stock prices
- ✅ Historical OHLCV data (all timeframes)
- ✅ Options chain data (strikes, OI, IV, Greeks)
- ✅ Volume data
- ❌ **NO GEX calculation** (but we can calculate ourselves!)

**Cost**: FREE
**Rate Limit**: ~2000 requests/hour (reasonable)
**Python**: `pip install yfinance`

**We're ALREADY using this** for RSI calculation!

```python
import yfinance as yf
ticker = yf.Ticker("SPY")
options = ticker.option_chain(expiry_date)  # Get OI, strikes, greeks
hist = ticker.history(period="1d", interval="5m")  # Intraday data
```

**Can Calculate GEX From**:
- Open Interest × Gamma × Contract Multiplier
- We just need gamma calculation formula

---

### **2. CBOE DataShop** 💵 Paid but Cheaper
**What they have**:
- Official options data
- Accurate OI and volume
- Historical options data
- VIX data

**Cost**:
- Individual products: $50-200/month
- Much cheaper than Trading Volatility
- Pay only for what you need

**API**: REST API, good documentation
**Website**: https://datashop.cboe.com/

---

### **3. Polygon.io** 💵 Paid
**What they have**:
- Options data including Greeks
- Real-time and historical
- WebSocket support
- Stock data

**Cost**:
- Starter: $29/month (500 calls/min)
- Developer: $99/month (unlimited)
- **Much better rate limits**

**API**: Excellent, modern REST + WebSocket
**Website**: https://polygon.io/pricing

---

### **4. Unusual Whales** 💵 Paid
**What they have**:
- Options flow data
- Gamma exposure calculations
- Dark pool data
- Greeksflow live

**Cost**:
- Hacker: $50/month
- Trader: $150/month

**API**: REST API available
**Website**: https://unusualwhales.com/

---

### **5. Calculate GEX Ourselves** ✅ FREE (using Yahoo Finance)

**Formula**:
```
GEX = Open Interest × Gamma × Stock Price × 100
```

**What we need**:
1. ✅ Open Interest (Yahoo Finance)
2. ✅ Current Price (Yahoo Finance)
3. ✅ Gamma calculation (Black-Scholes formula)

**Python libraries**:
```bash
pip install yfinance scipy numpy
```

**Implementation**:
```python
from scipy.stats import norm
import numpy as np

def black_scholes_gamma(S, K, T, r, sigma):
    """Calculate gamma using Black-Scholes"""
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# Get options chain from Yahoo Finance
ticker = yf.Ticker("SPY")
options = ticker.option_chain('2024-12-20')

# Calculate GEX for each strike
for strike in options.calls:
    gamma = black_scholes_gamma(spot, strike, dte, rate, iv)
    gex = strike.openInterest * gamma * spot * 100
```

**Benefits**:
- ✅ FREE
- ✅ No rate limits (just Yahoo's 2000/hour)
- ✅ Full control over calculations
- ✅ Can customize exactly what we need

---

## 🚀 Recommended Solution

### **Hybrid Approach** (Best Cost/Benefit)

**For FREE** (immediate):
1. **Yahoo Finance** for:
   - Price data (all timeframes)
   - Options chain (OI, strikes, IV)
   - Historical data for backtesting

2. **Calculate GEX ourselves**:
   - Use Black-Scholes for gamma
   - Calculate GEX from Yahoo's OI data
   - Store in our database

3. **Keep Trading Volatility** for:
   - Validation/comparison
   - When we need guaranteed accuracy
   - Production critical operations

**For Paid** (if budget allows):
- **Polygon.io Starter ($29/month)**: 500 calls/min, unlimited stocks
  - Much better rate limits than Trading Volatility
  - More data for less money

**OR**

- **CBOE DataShop ($50-100/month)**: Official exchange data
  - Most accurate OI and volume
  - Direct from the source

---

## 📊 Data Breakdown: What to Use Where

### **Price Data** → Yahoo Finance (FREE)
```python
ticker = yf.Ticker("SPY")
data = ticker.history(period="1d", interval="5m")  # Intraday
```

### **Multi-Timeframe RSI** → Yahoo Finance (FREE)
```python
# Already implemented in Psychology endpoint!
df_5m = ticker.history(period="5d", interval="5m")
df_15m = ticker.history(period="5d", interval="15m")
# etc...
```

### **Options Chain** → Yahoo Finance (FREE)
```python
options = ticker.option_chain(expiry_date)
calls = options.calls  # Has OI, IV, strike
puts = options.puts
```

### **GEX Calculation** → Our Own (FREE)
```python
# Calculate gamma using Black-Scholes
# Multiply by OI from Yahoo Finance
# Store in database
```

### **Validation** → Trading Volatility (Paid, when needed)
- Use sparingly for validation
- Critical production data
- When we need guaranteed accuracy

---

## 💡 Rate Limiting Strategy

### **Current Problem**:
- Trading Volatility: 20 calls/min shared
- 3 deployments competing
- Frequent rate limit failures

### **Solution 1: Use Yahoo Finance (FREE)**
- 2000 requests/hour = ~33/min
- Much higher limits
- Can support all 3 deployments easily

### **Solution 2: Implement Request Queue**
- Queue all API requests
- Process at safe rate (15/min for Trading Volatility)
- Prevent simultaneous requests from multiple users

### **Solution 3: Aggressive Caching**
- Cache GEX data for 1+ hours
- Calculate GEX once, serve many times
- Refresh only when actually needed

---

## 🛠️ Implementation Plan

### **Phase 1: Add Yahoo Finance Fallback** (Immediate, FREE)
1. When Trading Volatility rate limited:
   - Fetch options chain from Yahoo Finance
   - Calculate GEX ourselves
   - Return real calculated data

2. Cache calculations for 30+ minutes

3. No impact on API quota

### **Phase 2: Make Yahoo Finance Primary** (1-2 weeks)
1. Switch to Yahoo Finance as primary source
2. Calculate all GEX in-house
3. Use Trading Volatility only for validation

4. Benefits:
   - ✅ FREE
   - ✅ Higher rate limits
   - ✅ Full control

### **Phase 3: Add Polygon.io** (Optional, if budget)
1. $29/month for 500 calls/min
2. Professional-grade data
3. Better than Trading Volatility for the price

---

## 📝 Code Examples

### **Fetch Options Data from Yahoo Finance**:
```python
import yfinance as yf
from datetime import datetime

def get_options_data_yahoo(symbol="SPY"):
    """Get options chain from Yahoo Finance - FREE"""
    ticker = yf.Ticker(symbol)

    # Get nearest expiration
    expirations = ticker.options
    if not expirations:
        return None

    expiry = expirations[0]  # Nearest expiration

    # Get options chain
    chain = ticker.option_chain(expiry)

    return {
        'calls': chain.calls.to_dict('records'),
        'puts': chain.puts.to_dict('records'),
        'expiry': expiry,
        'spot_price': ticker.info.get('regularMarketPrice')
    }
```

### **Calculate GEX from Options Data**:
```python
def calculate_gex(options_data):
    """Calculate GEX from options chain"""
    from scipy.stats import norm
    import numpy as np

    def black_scholes_gamma(S, K, T, r, sigma):
        d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return gamma

    S = options_data['spot_price']
    strikes_gex = []

    for call in options_data['calls']:
        K = call['strike']
        T = calculate_dte(options_data['expiry']) / 365
        sigma = call['impliedVolatility']
        oi = call['openInterest']

        gamma = black_scholes_gamma(S, K, T, 0.05, sigma)
        gex = oi * gamma * S * 100

        strikes_gex.append({
            'strike': K,
            'call_gex': gex,
            'call_oi': oi
        })

    # Same for puts...

    return strikes_gex
```

---

## ✅ Immediate Action Items

1. **Verify yfinance is already installed**:
   ```bash
   pip show yfinance
   ```

2. **Test Yahoo Finance options data**:
   ```python
   import yfinance as yf
   spy = yf.Ticker("SPY")
   print(spy.option_chain(spy.options[0]))
   ```

3. **Implement GEX calculation**:
   - Add Black-Scholes gamma function
   - Calculate GEX from Yahoo data
   - Compare with Trading Volatility (when available)

4. **Add to backend as fallback**:
   - When Trading Volatility rate limited
   - Calculate GEX from Yahoo Finance
   - Cache aggressively (1+ hour)

---

## 💰 Cost Comparison

| Source | Cost/Month | Calls/Min | GEX Data | Options | Price Data |
|--------|-----------|-----------|----------|---------|-----------|
| **Yahoo Finance** | FREE | ~33 | Calculate | ✅ | ✅ |
| **Trading Volatility** | $99-299 | 20 | ✅ | ✅ | ✅ |
| **Polygon.io** | $29 | 500 | Calculate | ✅ | ✅ |
| **CBOE DataShop** | $50-200 | Varies | Calculate | ✅ | ✅ |
| **Unusual Whales** | $50-150 | Varies | ✅ | ✅ | ✅ |

**Recommendation**:
1. Start with Yahoo Finance (FREE)
2. Calculate GEX ourselves (FREE)
3. Keep Trading Volatility for validation
4. If need more, add Polygon.io ($29/month)

---

**Next Steps**: Should I implement Yahoo Finance + GEX calculation as alternative source?
