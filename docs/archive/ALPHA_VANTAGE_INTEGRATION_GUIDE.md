# Alpha Vantage Integration Guide for AlphaGEX

## Current Status

✅ **Alpha Vantage API Key**: `IW5CSY60VSCU8TUJ`
❌ **Status**: Returning 403 Forbidden (needs activation)
✅ **Already integrated**: Your codebase has Alpha Vantage support in `flexible_price_data.py`

---

## What's Happening?

Your Alpha Vantage API key is returning **403 Forbidden** errors, which typically means:

1. **New API keys need 24-48 hours to activate**
2. **You may need to click an activation email**
3. **The key might not be registered yet**

---

## Option 1: Fix Your Alpha Vantage Key (Recommended as Backup)

### Step 1: Check Your Email
Look for an email from Alpha Vantage with an activation link.
- Check spam/junk folder
- Look for emails from `@alphavantage.co`

### Step 2: Wait for Activation
- New keys can take up to 24-48 hours to activate
- Try again tomorrow

### Step 3: Get a New Key (if needed)
1. Go to: https://www.alphavantage.co/support/#api-key
2. Fill out the form (takes < 20 seconds):
   - Email: Your email address
   - Organization: Personal/Trading
   - Use case: Stock market analysis
3. Check your email for the new key
4. Click activation link if provided
5. Update your `.env` file:
   ```bash
   ALPHA_VANTAGE_API_KEY=your_new_key_here
   ```

### Step 4: Test Your Key in Browser
Once you have a working key, test it:
```
https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=YOUR_KEY_HERE
```

Expected response (if working):
```json
{
    "Global Quote": {
        "01. symbol": "SPY",
        "05. price": "575.25",
        ...
    }
}
```

---

## Option 2: Use Yahoo Finance (yfinance) - FREE & NO API KEY

**Good news**: Your codebase already supports Yahoo Finance!

### Why Yahoo Finance?
- ✅ **Completely FREE**
- ✅ **No API key needed**
- ✅ **Unlimited requests**
- ✅ **Real-time data** (during market hours)
- ✅ **Already integrated** in your code

### How to Use It

Your `flexible_price_data.py` automatically uses Yahoo Finance as the primary source.

Just use it like this:

```python
from flexible_price_data import get_price_history

# Get SPY price data (will use yfinance automatically)
spy_data = get_price_history('SPY', period='5d')

if spy_data is not None:
    latest_price = spy_data['Close'].iloc[-1]
    print(f"SPY: ${latest_price:.2f}")
```

### Manual Installation (if needed)
```bash
pip install yfinance pandas requests
```

---

## How Your Code Handles Multiple Sources

Your `flexible_price_data.py` (lines 186-233) automatically tries sources in this order:

1. **yfinance** (Yahoo Finance) - Tries first
2. **alpha_vantage** - Tries if yfinance fails
3. **polygon** - Tries if alpha_vantage fails
4. **twelve_data** - Tries if polygon fails

This means **you're covered even if Alpha Vantage doesn't work!**

---

## API Limits Comparison

| Source | Free Tier | API Key Required? | Status |
|--------|-----------|-------------------|---------|
| **Yahoo Finance** (yfinance) | Unlimited | ❌ No | ✅ Recommended |
| **Alpha Vantage** | 500 calls/day | ✅ Yes | ⚠️ Needs activation |
| **Polygon.io** | 5 calls/min | ✅ Yes | Not configured |
| **Twelve Data** | 800 calls/day | ✅ Yes | Not configured |

---

## Configuration Files

### 1. Environment Variables (`.env`)
```bash
# Alpha Vantage (backup source)
ALPHA_VANTAGE_API_KEY=IW5CSY60VSCU8TUJ  # or your new key

# Optional: Other sources
# POLYGON_API_KEY=your_polygon_key
# TWELVE_DATA_API_KEY=your_twelve_data_key
```

### 2. Your Integration Code

Alpha Vantage is already integrated in:
- **File**: `flexible_price_data.py`
- **Lines**: 255-304 (Alpha Vantage fetcher)
- **Usage**: Automatic fallback system

---

## Testing Your Setup

### Test 1: Check which sources are working
```python
from flexible_price_data import get_health_status

health = get_health_status()
print(health)
```

### Test 2: Fetch SPY data
```python
from flexible_price_data import get_price_history

# This will automatically try all sources until one works
data = get_price_history('SPY', period='5d')

if data is not None:
    print(f"✅ Success! Got {len(data)} days of data")
    print(f"Latest close: ${data['Close'].iloc[-1]:.2f}")
else:
    print("❌ All sources failed")
```

### Test 3: Force Alpha Vantage specifically
```python
from flexible_price_data import price_data_fetcher

# Try Alpha Vantage directly
data = price_data_fetcher._fetch_alpha_vantage('SPY', '5d')

if data is not None:
    print("✅ Alpha Vantage is working!")
else:
    print("❌ Alpha Vantage failed")
```

---

##Troubleshooting

### Issue: "403 Forbidden" from Alpha Vantage
**Solution**:
1. Wait 24-48 hours for activation
2. Check email for activation link
3. Get new key at https://www.alphavantage.co/support/#api-key
4. Contact: [email protected]

### Issue: "Rate limit exceeded"
**Solution**:
- Free tier: 500 calls/day, 5 calls/minute
- Use caching (already enabled in your code)
- Switch to yfinance for unlimited calls

### Issue: "Invalid API key"
**Solution**:
1. Verify key in `.env` file
2. No spaces or quotes around the key
3. Get new key if needed

---

## Support & Documentation

- **Alpha Vantage Support**: https://www.alphavantage.co/support/
- **Alpha Vantage Docs**: https://www.alphavantage.co/documentation/
- **Alpha Vantage FAQ**: https://www.alphavantage.co/faq/
- **Email Support**: [email protected]

---

## Recommendation

### For Immediate Use:
✅ **Use Yahoo Finance (yfinance)** - It's free, unlimited, and requires no API key

### For Backup/Redundancy:
⚠️ **Fix Alpha Vantage** - Good to have as backup, wait for activation or get new key

### For Production:
Consider paid tiers if you need:
- More than 500 Alpha Vantage calls/day
- Real-time data from Polygon.io ($199/month)
- Premium endpoints

---

## Quick Start (Using Yahoo Finance)

```python
# In your AlphaGEX code, just use:
from flexible_price_data import get_price_history

# Automatically uses Yahoo Finance (no key needed!)
spy_data = get_price_history('SPY', period='30d')
print(spy_data.tail())
```

**That's it!** Your system is ready to use with Yahoo Finance right now.

---

## Files Modified

1. ✅ `.env` - Added ALPHA_VANTAGE_API_KEY
2. ✅ `backend/.env.example` - Added API key documentation
3. ✅ `flexible_price_data.py` - Already has all integrations
4. ✅ This guide - `ALPHA_VANTAGE_INTEGRATION_GUIDE.md`

---

## Summary

🎯 **Bottom Line**:
- Your Alpha Vantage key needs activation (24-48 hours)
- Meanwhile, use Yahoo Finance (yfinance) - it's free and unlimited
- Your code automatically handles both sources
- No changes needed to your application code!

✅ **You're ready to use AlphaGEX with Yahoo Finance right now!**
