# Trading Volatility API - 403 Error Documentation

## 🔴 Current Issue

The Trading Volatility API at `https://stocks.tradingvolatility.net/api` is returning **403 Forbidden** errors despite using a valid API key.

**API Key**: `I-RWFNBLR2S1DP` (from secrets.toml)
**Status**: Valid subscription, but access denied

## 🔍 What We Tested

```bash
# API call that's failing:
curl "https://stocks.tradingvolatility.net/api/gex/latest?ticker=SPY&username=I-RWFNBLR2S1DP&format=json"

# Response:
HTTP/2 403
Access denied
```

## ❓ Possible Causes

1. **IP Whitelisting** - The service may now require IP whitelisting for API access
2. **Authentication Changes** - They may have changed from username-based auth to token-based
3. **Service Migration** - The API endpoint or structure may have been updated
4. **Subscription Status** - Account settings or permissions may need to be verified

## ✅ Workaround Implemented

We've implemented a **mock data fallback system** that allows AlphaGEX to function fully while the API issue is resolved:

### Mock Data Includes:
- **Spot Prices**: SPY ($580), QQQ ($500), IWM ($220), SPX ($5,800)
- **Net GEX**: -$2.5B (dealers short gamma)
- **Call/Put GEX**: $8.3B / $10.8B
- **Key Levels**: Flip point, call wall, put wall
- **Strike Data**: 21 strikes with gamma and open interest
- **Flag**: `"mock_data": true` to indicate test data

### Backend Running:
```bash
✅ http://localhost:8000 - API Server
✅ /api/gex/SPY - Returns mock GEX data
✅ /api/gex/SPY/levels - Returns mock strike data
✅ /health - Health check endpoint
```

## 📞 How to Resolve

**Contact Trading Volatility Support:**
- **Email**: support@tradingvolatility.net
- **Website**: https://tradingvolatility.net

**Questions to Ask:**
1. Has the authentication method changed for the API?
2. Is IP whitelisting required? If so, what IP should be whitelisted?
3. Are there any changes to the API endpoint structure?
4. Is the subscription account `I-RWFNBLR2S1DP` active and in good standing?

## 🚀 Running AlphaGEX (Current Setup)

### Backend (with mock data):
```bash
cd /home/user/AlphaGEX
./start_backend.sh
```

### Frontend:
```bash
cd /home/user/AlphaGEX/frontend
npm run dev
```

## 📝 When API is Fixed

Once you receive updated credentials or configuration from Trading Volatility:

1. Update `.env`:
```bash
# Update with new credentials
TV_USERNAME=your-new-key
TRADING_VOLATILITY_API_KEY=your-new-key

# Optional: Disable mock data
USE_MOCK_DATA=false
```

2. Restart backend:
```bash
pkill -f uvicorn
./start_backend.sh
```

The system will automatically switch from mock data to real API data.

## 📊 API Endpoint Reference

**Expected Working Endpoints:**
- `/gex/latest?ticker=SPY&username={key}&format=json` - Latest GEX data
- `/gex/gammaOI?ticker=SPY&username={key}` - Strike-level gamma data

**Current Status:** ❌ All endpoints returning 403

---

**Last Updated**: 2025-11-07
**Committed**: Branch `claude/fix-net-gex-undefined-011CUtXL5jg3m9AQtJeCzDpb`
