# Alpha Vantage API Setup Guide

## Current Status
❌ API Key: `IW5CSY60VSCU8TUJ` is returning 403 Forbidden errors

## Steps to Fix

### Option 1: Get a New Free API Key

1. **Get your free API key**: https://www.alphavantage.co/support/#api-key
2. **Fill out the form**:
   - Enter your email
   - Organization: Personal/Trading
   - Use case: Stock market analysis
3. **Check your email** - You'll receive your API key immediately
4. **Claim/Activate** - Some keys need to be activated via email link

### Option 2: Verify Current API Key

1. Go to: https://www.alphavantage.co/
2. Check if you received an activation email
3. Make sure you clicked the activation link

### Option 3: Test API Key Manually

Test your key in a browser:
```
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=YOUR_KEY_HERE
```

Replace `YOUR_KEY_HERE` with your actual API key.

**Expected Response (if working)**:
```json
{
    "Meta Data": {
        "1. Information": "Intraday (5min) open, high, low, close prices and volume",
        ...
    },
    "Time Series (5min)": {
        ...
    }
}
```

**Error Response (if not working)**:
```json
{
    "Error Message": "Invalid API call..."
}
```

Or HTTP 403 Forbidden (key not activated/invalid)

## Alternative FREE Data Sources (Already Configured!)

Good news: Your codebase already has these alternatives ready to use:

### 1. Yahoo Finance (yfinance) - Completely FREE ✅
- **No API key needed**
- **Already working** in your code
- **Unlimited requests**
- Real-time stock & option prices
- Usage in your code: `flexible_price_data.py` line 243-253

### 2. Polygon.io - Free Tier Available
- **Free tier**: 5 API calls/minute
- **Paid tier**: $199/month for real-time
- Get key at: https://polygon.io/
- Set: `POLYGON_API_KEY=your_key`

### 3. Twelve Data - Free Tier
- **Free tier**: 800 calls/day
- Get key at: https://twelvedata.com/
- Set: `TWELVE_DATA_API_KEY=your_key`

## Current Setup in Your Code

Your `flexible_price_data.py` already auto-falls back between sources:

```python
# Priority order (from flexible_price_data.py:187-188):
sources = ['yfinance', 'alpha_vantage', 'polygon', 'twelve_data']
```

### What This Means:
1. Tries **yfinance** first (FREE, no key needed)
2. Falls back to **alpha_vantage** if yfinance fails
3. Falls back to **polygon** if alpha_vantage fails
4. Falls back to **twelve_data** if polygon fails

## Recommendation

**For now, just use yfinance (Yahoo Finance)**:
- ✅ It's already installed
- ✅ No API key needed
- ✅ Works perfectly for your use case
- ✅ Real-time data during market hours

You can still fix Alpha Vantage as a backup, but yfinance should work fine!

## Testing Your Data Sources

Run this to test all sources:
```bash
cd /home/user/AlphaGEX
python3 test_data_sources.py
```

## Environment Variables

Update your `.env` file:
```bash
# Alpha Vantage (if you get a valid key)
ALPHA_VANTAGE_API_KEY=your_new_key_here

# Yahoo Finance - No key needed! Already works
# (uses yfinance library)

# Optional: Polygon.io
# POLYGON_API_KEY=your_polygon_key

# Optional: Twelve Data
# TWELVE_DATA_API_KEY=your_twelve_data_key
```

## Next Steps

1. **For now**: Your code will use yfinance (Yahoo Finance) automatically
2. **Optional**: Get a new Alpha Vantage key if you want a backup source
3. **Test**: Run the data source health check

## Support

- Alpha Vantage Support: https://www.alphavantage.co/support/
- Alpha Vantage FAQ: https://www.alphavantage.co/faq/
