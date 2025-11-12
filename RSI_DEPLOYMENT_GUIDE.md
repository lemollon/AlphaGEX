# 🚀 Multi-Timeframe RSI Deployment Guide

## ✅ What Was Fixed (Commit: d2bd47a)

### ROOT CAUSE
- Yahoo Finance is blocking all requests (403 errors)
- No price data = No RSI calculation = Shows "---" in UI
- Previous attempt referenced non-existent `flexible_price_data.py`

### THE FIX
- Added **direct Alpha Vantage API fallback** for 1D RSI
- Fallback chain: yfinance (try first) → Alpha Vantage (fallback) → "---" (graceful failure)
- Already configured your API key: `IW5CSY60VSCU8TUJ`

---

## 🔑 YOUR ALPHA VANTAGE API KEY

**Key:** `IW5CSY60VSCU8TUJ`  
**Status:** ⚠️ Currently returns 403 (may need activation)  
**Free Tier:** 500 calls/day, 5 calls/minute

---

## 📋 DEPLOYMENT STEPS (5 Minutes)

### STEP 1: Add API Key to Render

1. Go to: https://dashboard.render.com
2. Click on **`alphagex-api`** service
3. Click **Environment** tab (left sidebar)
4. Click **"Add Environment Variable"**
5. Add:
   - **Key**: `ALPHA_VANTAGE_API_KEY`
   - **Value**: `IW5CSY60VSCU8TUJ`
   - **Secret**: ✅ Check this box
6. Click **"Save Changes"**

Render will auto-redeploy (5-10 minutes).

---

### STEP 2: Activate Your Alpha Vantage Key (If Needed)

If you still see "---" after deployment:

1. **Check your email** for activation link from Alpha Vantage
   - Subject: "Activate your Alpha Vantage API Key"
   - From: `support@alphavantage.co` or similar
2. **Click the activation link** in the email
3. **Wait 5-10 minutes** for activation to propagate
4. **Test the key** in your browser:
   ```
   https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=IW5CSY60VSCU8TUJ
   ```
   - ✅ Should return JSON with SPY price data
   - ❌ If 403/error: Key needs activation or is expired

---

### STEP 3 (Alternative): Get New Free Key

If the old key doesn't work, get a fresh one:

1. Go to: https://www.alphavantage.co/support/#api-key
2. Enter your email
3. Click **"GET FREE API KEY"**
4. Copy the new key
5. **Update on Render:**
   - Dashboard → alphagex-api → Environment
   - Edit `ALPHA_VANTAGE_API_KEY`
   - Paste new key
   - Save (triggers redeploy)

---

## 🧪 VERIFY IT WORKS

### Check Render Logs

1. Dashboard → alphagex-api → **Logs** tab
2. Look for:
   ```
   ✅ Alpha Vantage API key configured - will use as fallback
   📊 Fetching multi-timeframe RSI for SPY...
   📥 1d: Fetched 0 bars from yfinance
   🔄 yfinance failed, trying Alpha Vantage fallback...
   📥 1d: Fetched 90 bars from Alpha Vantage
   ✅ 1d RSI: 54.3
   ```

### Expected Results in UI

**With Working Alpha Vantage Key:**
- ✅ **1D RSI**: Shows real value (e.g., "54.3")
- ⚠️ **Intraday RSI (4H, 1H, 15M, 5M)**: Still shows "---" (Alpha Vantage free tier doesn't support intraday)

**Without Alpha Vantage Key:**
- ❌ **All RSI**: Shows "---" (both daily and intraday fail)

---

## 📊 CURRENT STATUS

| Timeframe | Data Source | Status |
|-----------|-------------|--------|
| **1D** | yfinance → Alpha Vantage | ✅ Will work with key |
| **4H** | yfinance only | ⚠️ Shows "---" (blocked) |
| **1H** | yfinance only | ⚠️ Shows "---" (blocked) |
| **15M** | yfinance only | ⚠️ Shows "---" (blocked) |
| **5M** | yfinance only | ⚠️ Shows "---" (blocked) |

---

## 🚀 TO GET ALL TIMEFRAMES WORKING

If you want **all 5 timeframes** (including intraday), you need a paid service:

### Option: Polygon.io (Recommended for Intraday)

1. **Sign up**: https://polygon.io/
2. **Pricing**: $29/month (Starter plan)
3. **Features**: 
   - Daily data ✅
   - Intraday data (1m, 5m, 15m, 1h, 4h) ✅
   - Unlimited API calls
4. **Add to Render**:
   - Key: `POLYGON_API_KEY`
   - Value: Your Polygon API key

The backend will automatically detect and use Polygon for intraday RSI if the key is present.

---

## ⚠️ IMPORTANT NOTES

### Alpha Vantage Free Tier Limits
- **500 calls/day**
- **5 calls/minute**
- **Daily data only** (no intraday)

If you exceed limits, you'll see:
```json
{"Note": "Thank you for using Alpha Vantage! Our standard API rate limit is 5 requests per minute..."}
```

### System Behavior
- ✅ **Never crashes** - always degrades gracefully to "---"
- ✅ **Automatic fallback** - tries yfinance first, then Alpha Vantage
- ✅ **Detailed logging** - all attempts logged in Render logs

---

## 📞 SUPPORT

**If RSI still shows "---" after configuration:**

1. Check Render logs for exact error messages
2. Test Alpha Vantage key in browser (link above)
3. Verify environment variable is set correctly
4. Check if API limit exceeded (wait 1 minute and try again)

**Quick Debug:**
```bash
# Test in Render Shell
curl "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=IW5CSY60VSCU8TUJ"
```

---

**Last Updated:** 2025-11-12  
**Commit:** d2bd47a  
**Status:** ✅ Code deployed to feature branch, awaiting Render environment configuration
