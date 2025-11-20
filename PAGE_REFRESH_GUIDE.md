# AlphaGEX Complete Page Refresh Guide

## All Pages Listed with Refresh Frequencies

### 📊 Main Dashboard Pages

| Page | URL | Data Source | Refresh Frequency | Auto-Refresh | Notes |
|------|-----|-------------|-------------------|--------------|-------|
| **Dashboard** | `/` | `gex_history`, `regime_signals` | Every 5 minutes | ✅ Yes | Main overview, shows current GEX |
| **GEX History** | `/gex/history` | `gex_history` | Every 5 minutes | ✅ Yes | Historical gamma exposure charts |
| **Gamma Analysis** | `/gamma` | `gamma_history`, `gamma_daily_summary` | Every 15 minutes | ✅ Yes | Multi-timeframe gamma analysis |
| **Psychology Detector** | `/psychology` | Live calculation | On demand | ❌ No | Real-time pattern detection |
| **Psychology Performance** | `/psychology/performance` | `regime_signals` | Every 30 minutes | ✅ Yes | Signal track record |
| **Recommendations** | `/recommendations` | `recommendations` | Every hour | ✅ Yes | AI-generated trades |
| **Probability Calculator** | `/probability` | `regime_signals` | Every 30 minutes | ✅ Yes | Pattern prediction accuracy |
| **Strategy Optimizer** | `/optimizer` | All tables | On demand | ❌ No | Custom strategy analysis |
| **Forward Magnets** | `/magnets` | `forward_magnets` | Every 15 minutes | ✅ Yes | Price magnet detection |
| **OI Trends** | `/oi/trends` | `historical_open_interest` | Daily at 4:30 PM ET | ❌ No | Open interest accumulation |
| **Autonomous Trader** | `/trader` | `autonomous_positions`, `autonomous_trade_log` | Every 5 minutes | ✅ Yes | Live trading dashboard |
| **Performance Metrics** | `/performance` | `performance`, `positions` | Daily at 4:15 PM ET | ❌ No | P&L, Sharpe ratio, metrics |
| **Settings** | `/settings` | Configuration | N/A | ❌ No | System configuration |

---

## Refresh Cadence by Data Type

### Real-Time (Every 1-5 Minutes)
**Updates during market hours only (9:30 AM - 4:00 PM ET)**

- ✅ **Spot Price** - Every 1 minute (from Polygon/TradingVolatility API)
- ✅ **Current VIX** - Every 1 minute (from Polygon API)
- ✅ **GEX Snapshots** - Every 5 minutes (calculated from options chain)
- ✅ **Autonomous Trader Status** - Every 5 minutes (position updates)

### Frequent (Every 15-30 Minutes)
**Updates during market hours**

- ✅ **Forward Magnets** - Every 15 minutes (recalculated from OI data)
- ✅ **Gamma Analysis** - Every 15 minutes (multi-timeframe calculations)
- ✅ **Psychology Signals** - Every 30 minutes (pattern detection)
- ✅ **Probability Updates** - Every 30 minutes (signal validation)

### Hourly
**Updates during market hours**

- ✅ **AI Recommendations** - Every hour (Claude API generates new trades)
- ✅ **Gamma Expiration Timeline** - Every hour (DTE tracking)
- ✅ **RSI Analysis** - Every hour (multi-timeframe RSI)

### Daily (After Market Close)
**Updates once per day at specific times**

- ✅ **OI Snapshots** - 4:30 PM ET (after options close)
- ✅ **Daily Performance** - 4:15 PM ET (calculate day's P&L)
- ✅ **Position Reconciliation** - 4:10 PM ET (mark positions)
- ✅ **Performance Metrics** - 4:15 PM ET (Sharpe, win rate, drawdown)

### On Demand (Manual Refresh Required)
**Data calculated when you click "Analyze" or visit page**

- ⚠️ **Psychology Detector** - Click "Analyze Current Market"
- ⚠️ **Strategy Optimizer** - Click "Optimize Strategy"
- ⚠️ **Probability Calculator** - Enter parameters and calculate
- ⚠️ **Backtest Results** - Run backtest manually

---

## Page Load Performance

### Instant Load (< 100ms)
**Data pre-cached, no API calls needed**

- Dashboard
- GEX History
- Gamma Analysis
- Psychology Performance
- Recommendations
- Probability
- Forward Magnets
- Performance Metrics

**Why:** These pages load from database cache. The autonomous trader pre-populates all data every 5-30 minutes.

### Fast Load (< 500ms)
**Single API call or database query**

- OI Trends
- Autonomous Trader
- Settings

**Why:** These pages make one database query or API call to fetch latest data.

### Slow Load (1-3 seconds)
**Multiple API calls or heavy calculations**

- Psychology Detector (live)
- Strategy Optimizer (on demand)
- Probability Calculator (with custom params)

**Why:** These pages run real-time analysis requiring multiple API calls or complex calculations.

---

## Timestamp Display on Each Page

Each page will show **"Last updated: X minutes ago"** in the top-right corner:

```
┌─────────────────────────────────────┐
│ GEX History                         │
│                  Last updated: 2m ago │
└─────────────────────────────────────┘
```

**Color coding:**
- 🟢 **Green** (< 5 min old) - Fresh data
- 🟡 **Yellow** (5-15 min old) - Recent data
- 🔴 **Red** (> 15 min old) - Stale data (may need refresh)

---

## Auto-Refresh Behavior

### Pages with Auto-Refresh ✅

These pages automatically fetch new data in the background:

1. **Dashboard** - Every 5 minutes
2. **GEX History** - Every 5 minutes
3. **Gamma Analysis** - Every 15 minutes
4. **Psychology Performance** - Every 30 minutes
5. **Recommendations** - Every hour
6. **Probability** - Every 30 minutes
7. **Forward Magnets** - Every 15 minutes
8. **Autonomous Trader** - Every 5 minutes

**How it works:** React hooks poll the API at intervals. When new data arrives, the page updates automatically without full reload.

**Visual indicator:** You'll see a small spinning icon when data is refreshing.

### Pages without Auto-Refresh ❌

These pages require manual refresh or only update on demand:

1. **OI Trends** - Click refresh button (data updates daily)
2. **Performance Metrics** - Click refresh button (updates daily)
3. **Settings** - Configuration only, no data refresh
4. **Psychology Detector** - Click "Analyze" to run detection
5. **Strategy Optimizer** - Click "Optimize" to run analysis

**Why no auto-refresh:** These pages either:
- Update once per day (no need for frequent refresh)
- Require user input (on-demand calculation)
- Display static configuration

---

## Data Freshness by Time of Day

### During Market Hours (9:30 AM - 4:00 PM ET)

All pages show **live, up-to-date data**:
- Spot Price/VIX: 1 minute old
- GEX data: 5 minutes old
- Forward Magnets: 15 minutes old
- Recommendations: 1 hour old

**Expected behavior:** Data stays fresh all day as autonomous trader collects continuously.

### After Market Close (4:00 PM - 9:30 AM ET)

Most pages show **latest market close data**:
- Spot Price/VIX: From 4:00 PM ET close
- GEX data: From 4:00 PM ET close
- OI Snapshots: From 4:30 PM ET daily job
- Performance: From 4:15 PM ET calculation

**Expected behavior:** Data doesn't update until market reopens. This is normal - markets are closed!

### Weekends

All data is **from Friday's close**:
- No new data collected (markets closed)
- All timestamps show Friday 4:00 PM ET
- Pages still load instantly with Friday's data

**Expected behavior:** Browse historical data, plan strategies, review performance. No live updates until Monday 9:30 AM ET.

---

## Manual Refresh When Needed

### When to Manually Refresh

❗ **Refresh manually if:**
1. Timestamp shows > 15 minutes old during market hours
2. Data looks stale (price hasn't moved in 30+ minutes)
3. You just deployed new code
4. Autonomous trader was restarted

### How to Manually Refresh

**Option 1: Browser refresh**
```
Press F5 or Ctrl+R (Cmd+R on Mac)
```

**Option 2: Page refresh button**
```
Look for 🔄 icon in top-right corner of each page
Click to fetch latest data
```

**Option 3: Force refresh (clear cache)**
```
Press Ctrl+Shift+R (Cmd+Shift+R on Mac)
Clears cache and fetches all new data
```

---

## Troubleshooting Stale Data

### Problem: "Last updated: 45 minutes ago" during market hours

**Likely causes:**
1. Autonomous trader stopped running
2. API rate limits hit
3. Database connection issue

**Fix:**
```bash
# Check if trader is running
ps aux | grep autonomous_scheduler

# Restart if needed
python autonomous_scheduler.py --mode continuous --interval 5 &

# Check logs
tail -50 logs/trader.log
```

### Problem: "Last updated: 3 hours ago" and market is open

**Likely causes:**
1. Data collection jobs failed
2. API keys expired
3. Render service paused (free tier sleeps after 15 min)

**Fix:**
```bash
# Manually run data collection
python run_all_data_collectors.py

# Check API keys
echo $POLYGON_API_KEY | head -c 20
echo $TRADING_VOLATILITY_API_KEY | head -c 20
```

### Problem: All timestamps show Friday's date (on Monday-Friday)

**Likely causes:**
1. Autonomous trader not running
2. Market holiday (check calendar)
3. Render worker service stopped

**Fix:**
1. Check Render dashboard → `alphagex-trader` service
2. Restart service if stopped
3. Check logs for errors

---

## API Rate Limit Impact on Refresh

### Polygon.io Free Tier (5 calls/minute)

**Impact on refresh:**
- Can update 5 different pages per minute
- GEX + Spot Price + VIX + Recommendations + Gamma = 5 calls
- No issues with default refresh cadence

**What happens if limit hit:**
- New data fetch waits 1 minute before retrying
- Timestamp shows "Refreshing..." status
- Old data still displayed until new data arrives

### TradingVolatility API (Unknown limit, but generous)

**Impact on refresh:**
- Primary source for GEX data
- Polls every 5 minutes with no issues observed
- Rarely hits limits

**What happens if limit hit:**
- Falls back to local calculation
- Slightly less accurate GEX values
- Page shows "Calculated (not live)" indicator

### Anthropic Claude API (50 requests/minute)

**Impact on refresh:**
- Only used for AI recommendations (1/hour)
- Never hits rate limits with default usage
- Can handle manual "Generate Recommendation" clicks

**What happens if limit hit:**
- Recommendation generation queued
- Shows "Generating..." status
- Usually completes within 30 seconds

---

## Summary: What You Need to Know

1. **Most pages load instantly** (< 100ms) - Data is pre-cached
2. **Auto-refresh every 5-30 minutes** during market hours - No manual action needed
3. **Timestamps show data age** - Green = fresh, Red = stale
4. **Manual refresh available** - F5 or 🔄 button on each page
5. **After hours, data is static** - This is normal, markets are closed
6. **Autonomous trader handles everything** - Runs continuously on Render

**TL;DR:** Data stays fresh automatically. Check timestamps to confirm. If > 15 min old during market hours, manually refresh or check if trader is running.
