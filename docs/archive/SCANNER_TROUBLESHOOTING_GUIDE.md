# Multi-Symbol Scanner - Complete Setup & Troubleshooting Guide

**Date:** 2025-11-07
**Issue:** Multi-symbol scanner not returning results in Next.js frontend

---

## Overview

AlphaGEX has **TWO different scanner implementations**:

1. **Streamlit Scanner** - Works in `gex_copilot.py` (Streamlit app)
2. **Next.js Scanner** - Frontend at `/scanner` calling backend API

Both use the SAME core logic from `multi_symbol_scanner.py` and call `api_client.get_net_gamma(symbol)`.

---

## Architecture

### Streamlit Scanner (WORKING)
```
gex_copilot.py
  ↓ imports
multi_symbol_scanner.py::scan_symbols()
  ↓ calls
TradingVolatilityAPI::get_net_gamma()
  ↓ returns
GEX data → Display in Streamlit
```

### Next.js Scanner (NEEDS BACKEND RUNNING)
```
frontend/src/app/scanner/page.tsx
  ↓ calls
frontend/src/lib/api.ts::scanSymbols()
  ↓ POST to
backend/main.py::/api/scanner/scan
  ↓ calls
TradingVolatilityAPI::get_net_gamma()
  ↓ returns
GEX data → Display in React
```

---

## Why Scanner Might Not Work

### ❌ Backend Not Running
The Next.js scanner **REQUIRES** the FastAPI backend to be running. If backend is down:
- Frontend shows: "alert('Scan failed. Make sure the backend is running.')"
- No results appear
- Console shows connection errors

**Solution:** Start the backend!

### ❌ API Connection Issues
- Backend running on different port
- CORS issues
- Timeout issues

**Solution:** Check API_URL configuration

### ❌ API Key Not Configured
- TradingVolatility API key not set
- Backend can't fetch GEX data
- Returns errors for all symbols

**Solution:** Set `TRADING_VOLATILITY_API_KEY` environment variable

---

## How to Run the Scanner (Step by Step)

### Method 1: Streamlit Scanner (EASIEST)

```bash
cd /home/user/AlphaGEX
streamlit run gex_copilot.py
```

Then:
1. Navigate to "Multi-Symbol Scanner" in the sidebar
2. Select symbols from watchlist
3. Click "🔍 Scan Watchlist"
4. View results

**This works because:** Everything runs in one process, no API calls needed.

### Method 2: Next.js Scanner (REQUIRES BACKEND)

**Step 1: Start Backend**
```bash
cd /home/user/AlphaGEX
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Step 2: Start Frontend (separate terminal)**
```bash
cd /home/user/AlphaGEX/frontend
npm run dev
```

**Step 3: Use Scanner**
1. Open browser to http://localhost:3000/scanner
2. Select symbols (SPY, QQQ, etc.)
3. Click "Scan X Symbols"
4. View results

**This works because:** Backend API is running and accessible.

---

## Testing the Scanner

### Test 1: Verify Backend Scanner Endpoint

```bash
curl -X POST http://localhost:8000/api/scanner/scan \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["SPY", "QQQ"]}'
```

**Expected Response:**
```json
{
  "success": true,
  "scan_id": "uuid-here",
  "results": [
    {
      "symbol": "SPY",
      "strategy": "IRON_CONDOR",
      "confidence": 0.72,
      ...
    }
  ]
}
```

**If you get an error:**
- Backend not running → Start it
- API key not set → Set TRADING_VOLATILITY_API_KEY
- Connection refused → Check port 8000

### Test 2: Check API Connection from Frontend

Open browser console (F12) on http://localhost:3000/scanner and run:

```javascript
fetch('http://localhost:8000/health')
  .then(r => r.json())
  .then(console.log)
```

**Expected:** `{ status: "ok", ... }`

**If fails:** Backend not accessible from frontend

---

## Common Issues & Solutions

### Issue 1: "No results yet" after scanning

**Symptoms:**
- Click "Scan X Symbols"
- Loading spinner shows
- Then back to "No results yet"
- No error message

**Causes:**
1. Backend returned 0 opportunities (all symbols filtered out)
2. API timeout (scan took > 60 seconds)
3. All symbols returned errors

**Debug:**
1. Check backend logs while scanning
2. Look for `⚠️` warnings in backend output
3. Check if API is rate limiting

**Solution:**
```bash
# Check backend logs
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# In another terminal, trigger scan
curl -X POST http://localhost:8000/api/scanner/scan \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["SPY"]}'

# Watch for output like:
# ⚠️ SPY returned error or no data, skipping...
```

If you see errors, check:
- API key configured?
- Rate limiting active?
- Network connectivity?

### Issue 2: "Scan failed. Make sure backend is running"

**Cause:** Frontend can't reach backend API

**Solution:**
1. Start backend: `python -m uvicorn backend.main:app --port 8000`
2. Verify it's running: `curl http://localhost:8000/health`
3. Check NEXT_PUBLIC_API_URL in frontend/.env.local

### Issue 3: API Rate Limiting

**Symptoms:**
- First few symbols scan fine
- Then all fail
- Backend shows: "API Rate Limit Hit"

**Cause:** TradingVolatility API has rate limits

**Solution:**
- Wait 60 seconds for rate limit reset
- Reduce number of symbols being scanned
- The API client has built-in rate limiting (20s between requests)

### Issue 4: Scanner Times Out

**Symptoms:**
- Scan starts but never finishes
- Loading spinner forever
- Eventually timeout error

**Cause:**
- Backend scanner has 2 minute total timeout
- Per-symbol timeout is 10 seconds
- If API is slow, symbols get skipped

**Solution:**
- Scan fewer symbols at once
- Check backend logs for timeout warnings
- Increase timeout in backend/main.py if needed

---

## Code Comparison: Streamlit vs Next.js

### Streamlit Scanner (multi_symbol_scanner.py)

```python
def scan_symbols(symbols: List[str], api_client, force_refresh: bool = False):
    results = []
    for symbol in symbols:
        gex_data = api_client.get_net_gamma(symbol)  # ← Same API call

        if gex_data and 'error' not in gex_data:
            # Process data
            strategy_engine = StrategyEngine()
            setups = strategy_engine.detect_setups(gex_data)

            scan_result = {
                'symbol': symbol,
                'net_gex': gex_data.get('net_gex', 0) / 1e9,
                'flip_point': gex_data.get('flip_point', 0),
                ...
            }
            results.append(scan_result)

    return pd.DataFrame(results)
```

### Backend Scanner (backend/main.py)

```python
@app.post("/api/scanner/scan")
async def scan_symbols(request: dict):
    symbols = request.get('symbols', ['SPY', 'QQQ', 'IWM'])
    results = []

    for symbol in symbols:
        gex_data = api_client.get_net_gamma(symbol)  # ← Same API call!

        if gex_data and not gex_data.get('error'):
            # Check ALL strategies
            for strategy_name, strategy_config in STRATEGIES.items():
                # Build setup with detailed money-making plan
                setup = {
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'net_gex': net_gex,
                    'spot_price': spot_price,
                    'flip_point': flip_point,
                    ...
                }
                results.append(setup)

    return {"success": True, "results": results}
```

**Key Difference:**
- Streamlit version uses `StrategyEngine` from visualization_and_plans.py
- Backend version has strategy detection logic inline
- **Both call the same `get_net_gamma()` method**
- **Both should work if API key is configured**

---

## Environment Variables Checklist

### Backend (.env or environment)
```bash
TRADING_VOLATILITY_API_KEY=your_api_key_here
ANTHROPIC_API_KEY=your_claude_key_here  # Optional, for AI features
```

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## Quick Diagnosis

Run this checklist:

- [ ] Backend is running (`curl http://localhost:8000/health`)
- [ ] API key is set (`echo $TRADING_VOLATILITY_API_KEY`)
- [ ] Frontend can reach backend (check console, look for CORS errors)
- [ ] Scanner endpoint works (`curl -X POST http://localhost:8000/api/scanner/scan -H "Content-Type: application/json" -d '{"symbols": ["SPY"]}'`)
- [ ] No rate limiting active (wait 60s if needed)
- [ ] Network connectivity OK

---

## Recommended Solution

**For immediate use:** Use Streamlit scanner
```bash
streamlit run gex_copilot.py
# Navigate to Multi-Symbol Scanner in sidebar
```

**For production use:** Fix Next.js scanner
1. Start backend: `python -m uvicorn backend.main:app --port 8000`
2. Verify API key is set
3. Start frontend: `cd frontend && npm run dev`
4. Test at http://localhost:3000/scanner

---

## Next Steps to Fix Next.js Scanner

1. **Add better error logging** to frontend scanner page
2. **Display backend errors** in UI instead of just "Scan failed"
3. **Add connection test** button to verify backend is reachable
4. **Show API rate limit status** in UI
5. **Add retry logic** for failed symbol scans

---

## Contact & Support

If scanner still doesn't work after following this guide:

1. Check backend console output for errors
2. Check frontend browser console (F12) for errors
3. Verify API key is valid
4. Test with single symbol first (SPY only)
5. Check if Streamlit scanner works (isolates API issues vs frontend issues)
