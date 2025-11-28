# 🚀 Multi-Timeframe RSI Deployment Guide

## ✅ What's Implemented

The AlphaGEX backend now uses **Polygon.io exclusively** for ALL market data:
- **Multi-timeframe RSI** (1D, 4H, 1H, 15M, 5M)
- **VIX data**
- **Historical price data** for Psychology Trap analysis

### Recent Changes
- **Latest**: Replaced Yahoo Finance with Polygon.io for psychology analysis (price data)
- **Commit dee6392**: Simplified to use ONLY Polygon.io for all RSI timeframes and VIX
- **Removed**: Yahoo Finance and Alpha Vantage dependencies completely
- **Current Status**: All features require Polygon.io API key (RSI, VIX, Psychology Analysis)

---

## 🔑 REQUIRED: Polygon.io API Key

### Why Polygon.io?
- ✅ **All timeframes supported**: Daily + Intraday (5m, 15m, 1h, 4h)
- ✅ **Reliable from cloud**: No IP blocking issues
- ✅ **High rate limits**: Sufficient for production use
- ✅ **Official API**: Stable and well-documented

### Get Your API Key

**Free Tier (Delayed Data)**
1. Go to: https://polygon.io/
2. Click **"Get Free API Key"**
3. Sign up with your email
4. Copy your API key from the dashboard
5. **Free Tier Limits**: Delayed data (15 min), 5 API calls/minute

**Paid Tier (Recommended - $29/month Starter)**
1. Go to: https://polygon.io/pricing
2. Select **"Starter"** plan ($29/month)
3. **Features**:
   - ✅ Real-time market data
   - ✅ Unlimited API calls
   - ✅ All timeframes (1m to 1D)
   - ✅ Historical data access
4. Copy your API key from dashboard

---

## 📋 DEPLOYMENT STEPS

### STEP 1: Add API Key to Render (CRITICAL)

1. Go to: https://dashboard.render.com
2. Click on **`alphagex-api`** service
3. Click **Environment** tab (left sidebar)
4. Click **"Add Environment Variable"**
5. Add:
   - **Key**: `POLYGON_API_KEY`
   - **Value**: `<your_polygon_api_key>`
   - **Secret**: ✅ Check this box
6. Click **"Save Changes"**

⏱️ Render will auto-redeploy in 5-10 minutes.

---

### STEP 2: Verify Deployment

#### Check Render Logs

1. Dashboard → alphagex-api → **Logs** tab
2. Look for successful RSI fetches:

```
✅ Polygon.io API key configured
📊 Fetching multi-timeframe RSI for SPY...
  📥 1d: Fetched 90 bars from Polygon.io
  ✅ 1d RSI: 54.3
  📥 4h: Fetched 180 bars from Polygon.io
  ✅ 4h RSI: 52.1
  📥 1h: Fetched 336 bars from Polygon.io
  ✅ 1h RSI: 48.7
  📥 15m: Fetched 672 bars from Polygon.io
  ✅ 15m RSI: 45.2
  📥 5m: Fetched 576 bars from Polygon.io
  ✅ 5m RSI: 43.8
📊 RSI Summary: 5/5 timeframes successful
```

#### Check the App

1. Open: https://alphagex.onrender.com/gex
2. Look for **"Multi-Timeframe RSI"** section
3. **With API key**: All timeframes show values (e.g., "54.3")
4. **Without API key**: Section won't appear (returns null)

---

## 🧪 TEST LOCALLY (Optional)

```bash
# Set your API key
export POLYGON_API_KEY="your_polygon_api_key_here"

# Start backend
cd backend
python main.py

# Test endpoint
curl "http://localhost:8000/api/gex/SPY" | jq '.data.rsi'
```

Expected output:
```json
{
  "5m": 43.8,
  "15m": 45.2,
  "1h": 48.7,
  "4h": 52.1,
  "1d": 54.3
}
```

If API key not set:
```json
null
```

---

## 📊 CURRENT DATA SOURCES

| Timeframe | Data Source | Status |
|-----------|-------------|--------|
| **1D** | Polygon.io | ✅ Requires API key |
| **4H** | Polygon.io | ✅ Requires API key |
| **1H** | Polygon.io | ✅ Requires API key |
| **15M** | Polygon.io | ✅ Requires API key |
| **5M** | Polygon.io | ✅ Requires API key |
| **VIX** | Polygon.io | ✅ Requires API key |

---

## ⚠️ TROUBLESHOOTING

### RSI Not Showing in App

**Symptom**: Multi-Timeframe RSI section doesn't appear in GEX page

**Cause**: `POLYGON_API_KEY` not configured in Render

**Fix**:
1. Check Render dashboard → alphagex-api → Environment
2. Verify `POLYGON_API_KEY` exists and has correct value
3. Check logs for: `⚠️ No Polygon.io API key - RSI calculation will fail`
4. If key is missing, add it (see STEP 1 above)

### Getting "403 Forbidden" Errors

**Symptom**: Logs show `⚠️ Polygon.io HTTP 403`

**Causes**:
- API key is invalid or expired
- Accessing real-time data with free tier key
- Rate limit exceeded

**Fix**:
1. Verify API key is correct
2. Check your Polygon.io dashboard for key status
3. If using free tier, expect 15-minute delays
4. Consider upgrading to paid tier

### Getting "---" for Some Timeframes

**Symptom**: 1D RSI shows value, but 4H/1H/15M/5M show "---"

**Causes**:
- Free tier key (doesn't support intraday data)
- Rate limits exceeded
- Weekend/market closed (not enough recent data)

**Fix**:
1. Upgrade to Starter plan ($29/month) for intraday data
2. Check Polygon.io rate limits
3. Wait for market open if testing on weekend

### Backend Crashes

**Symptom**: Backend returns 500 errors

**This should NOT happen** - the code gracefully handles missing RSI:
- Missing API key → Returns `rsi: null`
- API error → Returns `rsi: null`
- Frontend → Hides RSI section when `null`

If crashing, check logs for Python exceptions and report as bug.

---

## 🎯 QUICK START CHECKLIST

- [ ] Get Polygon.io API key (free or paid)
- [ ] Add `POLYGON_API_KEY` to Render environment
- [ ] Wait for Render to redeploy (5-10 min)
- [ ] Check logs for successful RSI fetches
- [ ] Open app and verify RSI values appear
- [ ] ✅ Done!

---

## 💰 COST BREAKDOWN

**Option 1: Free Tier**
- Cost: $0/month
- Data: 15-minute delayed
- Rate Limit: 5 calls/minute
- Use Case: Testing, development

**Option 2: Starter Plan (RECOMMENDED)**
- Cost: $29/month
- Data: Real-time
- Rate Limit: Unlimited
- Use Case: Production trading app

---

## 📞 SUPPORT

**If RSI still not showing:**

1. ✅ Check `POLYGON_API_KEY` is set in Render
2. ✅ Check Render logs for error messages
3. ✅ Test API key directly:
   ```bash
   curl "https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/2025-01-01/2025-12-31?apiKey=YOUR_KEY"
   ```
4. ✅ Verify you're on correct plan (Starter for intraday)

**API Documentation**:
- https://polygon.io/docs/stocks/getting-started

**Polygon.io Support**:
- Email: support@polygon.io
- Dashboard: https://polygon.io/dashboard

---

**Last Updated**: 2025-11-13
**Code Fix**: Backend now returns `null` when RSI unavailable (graceful degradation)
**Required Action**: Add `POLYGON_API_KEY` to Render environment variables
