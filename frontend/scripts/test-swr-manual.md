# Manual SWR Caching Test Checklist

## Setup
1. Start the frontend: `npm run dev`
2. Open browser DevTools → Network tab
3. Clear cache and hard reload (Ctrl+Shift+R)

---

## Test 1: Dashboard Initial Load
- [ ] Go to `http://localhost:3000`
- [ ] Observe Network tab - should see API calls for:
  - `/api/ai-intelligence/market-commentary`
  - `/api/ai-intelligence/daily-trading-plan`
  - `/api/gamma/SPY/expiration-intel`
- [ ] All 3 dashboard sections should load and display data

## Test 2: Navigation Caching
- [ ] From Dashboard, click "GEX Analysis" in sidebar
- [ ] Wait for GEX page to load
- [ ] Click "Dashboard" to return
- [ ] **EXPECTED:** Dashboard loads INSTANTLY (no loading spinners)
- [ ] **CHECK:** Network tab should show NO new API calls for cached data

## Test 3: Background Refresh
- [ ] Stay on Dashboard for 5+ minutes
- [ ] **EXPECTED:** Data auto-refreshes in background (check Network tab)
- [ ] UI should NOT show loading spinners during background refresh

## Test 4: Manual Refresh
- [ ] Click refresh button (🔄) on Market Commentary section
- [ ] **EXPECTED:** Spinner appears briefly, then new data loads
- [ ] Network tab should show new API call

## Test 5: Symbol Switching (0DTE Widget)
- [ ] On Dashboard, click "QQQ" button in 0DTE widget
- [ ] Wait for QQQ data to load
- [ ] Click "SPY" button
- [ ] **EXPECTED:** SPY data loads from cache (instant, no spinner)
- [ ] Click "QQQ" again
- [ ] **EXPECTED:** QQQ data loads from cache (instant)

---

## Pages WITH SWR Caching ✅
| Component | Cache Duration | Auto-Refresh |
|-----------|---------------|--------------|
| MarketCommentary | 5 min | Every 5 min |
| DailyTradingPlan | 30 min | Every 30 min |
| GammaExpirationWidget | 5 min | Every 5 min |

## Pages WITHOUT SWR ❌ (Still fetch on every visit)
- `/gex` - GEX Analysis
- `/gex/history` - GEX History
- `/gamma` - Gamma Intelligence
- `/scanner` - Scanner
- `/ares` - ARES Bot
- `/solomon` - SOLOMON Bot
- All other pages...

---

## Browser Console Test
Open browser console and run:
```javascript
// Check SWR cache status
console.log('SWR Cache Keys:', Object.keys(localStorage).filter(k => k.includes('swr')))
```

---

## Quick Pass/Fail
- [ ] **PASS:** Dashboard sections load without repeated loading on navigation
- [ ] **PASS:** Returning to Dashboard is instant (< 500ms)
- [ ] **PASS:** No duplicate API calls when navigating back
- [ ] **FAIL:** If you see loading spinners every time you return to Dashboard
