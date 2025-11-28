# AlphaGEX Data Refresh Cadence

## Overview

This document explains how data is collected, refreshed, and when pages update throughout the trading day.

## Data Collection Schedule

### During Market Hours (9:30 AM - 4:00 PM ET, Mon-Fri)

| Data Type | Refresh Frequency | Purpose |
|-----------|------------------|---------|
| **GEX Snapshots** | Every 5 minutes | Real-time gamma exposure tracking |
| **Forward Magnets** | Every 15 minutes | Detect price magnets from large OI |
| **Spot Price & VIX** | Every 1 minute | Live market data |
| **Psychology Traps** | Every 30 minutes | Pattern detection and signals |
| **Recommendations** | Every hour | AI-generated trade recommendations |
| **Gamma Expiration** | Every hour | Track gamma decay by DTE |

### After Market Close (4:00 PM - 5:00 PM ET)

| Data Type | Refresh Time | Purpose |
|-----------|-------------|---------|
| **OI Snapshots** | 4:30 PM ET | Daily open interest snapshot |
| **Daily Performance** | 4:15 PM ET | Calculate P&L, Sharpe ratio |
| **Position Reconciliation** | 4:10 PM ET | Update positions, mark closed trades |

### Daily (Anytime)

| Data Type | Frequency | Purpose |
|-----------|-----------|---------|
| **Backfill Check** | Once daily (6 AM ET) | Fill any missing data gaps |
| **Database Cleanup** | Once daily (2 AM ET) | Remove old data, optimize indexes |

## Page Load Behavior

### Pre-Loaded Pages (Instant Load)

These pages have data pre-cached and load instantly:

1. **Dashboard** - GEX overview, current regime
2. **GEX History** - Last 90 days of gamma exposure
3. **Recommendations** - Last 7 days of AI recommendations
4. **Psychology Performance** - Signal track record

**How it works:** Data is fetched and cached in the backend every 5-15 minutes. When you visit the page, it serves cached data instantly (< 100ms load time).

### Real-Time Pages (Fetch on Load)

These pages fetch fresh data when you visit:

1. **Probability Calculator** - Runs calculations on demand
2. **Strategy Optimizer** - Analyzes current market on request
3. **Live Trading Interface** - Always fetches latest data

**Why:** These pages require custom calculations based on user inputs or need the absolute latest data.

## Refresh Recommendations

### For Day Traders (Active Monitoring)

- **Keep tabs open:** Dashboard, GEX History, Recommendations
- **Auto-refresh:** Every 5 minutes (browser will fetch new data automatically)
- **Manual refresh:** Use refresh button on pages for instant update

### For Swing Traders (Less Frequent)

- **Check once per day:** Morning (9:45 AM ET) and close (4:00 PM ET)
- **Focus pages:** Psychology Performance, Recommendations, Forward Magnets
- **Data age:** Most data is < 1 hour old, perfectly fine for swing trading

### For Position Traders (Weekly Check-ins)

- **Check weekly:** Sunday evening or Monday morning
- **Review pages:** Performance metrics, historical trends, signal accuracy
- **Data age:** Historical analysis, not time-sensitive

## How to Populate Data

### Initial Setup (First Time)

```bash
# 1. Backfill historical data (1 year)
python backfill_historical_data.py --days 365

# 2. Initialize all tables
python initialize_all_data.py --days 30

# 3. Run first data collection
python run_all_data_collectors.py
```

**Time required:** ~3-5 minutes
**Result:** All pages fully populated with data

### Daily Maintenance (Automated)

On Render, the `alphagex-trader` worker service runs continuously and handles:
- Data collection during market hours
- End-of-day snapshots
- Performance calculations
- Recommendation generation

**No manual intervention needed!**

### Manual Refresh (If Needed)

```bash
# Refresh all data now
python run_all_data_collectors.py

# Refresh specific data
python gex_history_snapshot_job.py              # GEX snapshots
python historical_oi_snapshot_job.py SPY        # OI snapshots
python initialize_all_data.py --days 7          # Recommendations + metrics
```

## API Rate Limits

### Polygon.io

- **Free tier:** 5 calls/minute
- **Starter plan:** Unlimited calls
- **Our usage:** ~10-20 calls/hour during market hours

### TradingVolatility API

- **Rate limit:** Unknown (generally permissive)
- **Our usage:** ~12-24 calls/hour (every 5 minutes)

### Anthropic Claude API

- **Rate limit:** 50 requests/minute (Haiku)
- **Our usage:** ~1-2 calls/hour (recommendations only)

## Troubleshooting

### Pages Loading Slowly

**Symptom:** Spinner for 3-5 seconds before page loads

**Causes:**
1. Data collection job not running
2. Database tables empty
3. API rate limits hit

**Fix:**
```bash
# Check database
python -c "
import sqlite3
conn = sqlite3.connect('gex_copilot.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM recommendations')
print(f'Recommendations: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM gex_history')
print(f'GEX History: {c.fetchone()[0]}')
"

# If counts are 0, run initialization
python initialize_all_data.py --days 30
```

### Stale Data (Hours Old)

**Symptom:** Page shows old timestamp, data hasn't updated

**Causes:**
1. Data collector stopped running
2. API credentials expired
3. Market closed (normal - data won't update)

**Fix:**
```bash
# Manually run data collection
python run_all_data_collectors.py

# Check if collector is running
ps aux | grep autonomous_scheduler
```

### Missing Recommendations

**Symptom:** "No recommendations available"

**Causes:**
1. Recommendations table empty
2. AI API key not configured

**Fix:**
```bash
# Generate recommendations
python initialize_all_data.py --days 7

# Check API key
echo $ANTHROPIC_API_KEY | head -c 20
```

## Best Practices

1. **Run backfill once** when setting up (first time only)
2. **Let autonomous trader run** - it handles data collection automatically
3. **Check dashboard daily** - 30 seconds to see if data is updating
4. **Manually refresh** only if data is >2 hours old during market hours
5. **Don't spam refresh** - data updates every 5-15 minutes, refreshing faster doesn't help

## Performance Tips

### For Fastest Page Loads

1. Keep browser tabs open (caching works better)
2. Use Chrome/Firefox (better caching than Safari)
3. Don't clear browser cache frequently
4. Let autonomous trader run continuously

### For Lowest API Costs

1. Don't run backfill more than once
2. Use default refresh intervals (don't decrease)
3. Rely on cached data when possible
4. Only generate new recommendations when needed

## Summary

- **Most pages load instantly** - Data is pre-cached
- **Data updates every 5-15 minutes** during market hours
- **No manual intervention needed** - Autonomous trader handles everything
- **First-time setup:** Run backfill + initialization scripts once
- **After that:** Everything is automatic!

---

**Questions?** Check the logs: `logs/trader.log` or `logs/data_collector.log`
