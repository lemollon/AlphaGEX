# Historical Open Interest (OI) Snapshot Setup Guide

## Overview

The Historical OI Snapshot job captures daily snapshots of options Open Interest to track accumulation rates. This data powers the **Forward GEX Magnet** detection system, identifying where big money is positioning for future expirations.

## Why This Matters

- **OI Accumulation = Smart Money Positioning**: Rapid OI growth at specific strikes signals institutional buildup
- **Forward Magnet Detection**: Identifies price levels with gravitational pull
- **Trap Avoidance**: Reveals when "support" is temporary vs. persistent

## Quick Start

### 1. Test the Job

```bash
# Test mode (no database writes)
python historical_oi_snapshot_job.py --test

# Snapshot specific symbols
python historical_oi_snapshot_job.py SPY QQQ --test

# Full run (writes to database)
python historical_oi_snapshot_job.py
```

### 2. Schedule Daily Snapshots

The job should run **daily after market close** (4:30 PM ET) on trading days.

#### Option A: Using Cron (Linux/Mac)

```bash
# Create logs directory
mkdir -p /home/user/AlphaGEX/logs

# Edit crontab
crontab -e

# Add this line (runs Mon-Fri at 4:30 PM ET)
30 16 * * 1-5 cd /home/user/AlphaGEX && /usr/bin/python3 historical_oi_snapshot_job.py >> logs/oi_snapshot.log 2>&1
```

**Note:** Adjust timezone if your server isn't set to ET:
```bash
# If server is in UTC (5 hours ahead of ET)
30 21 * * 1-5 cd /home/user/AlphaGEX && /usr/bin/python3 historical_oi_snapshot_job.py >> logs/oi_snapshot.log 2>&1
```

#### Option B: Using Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Name: "AlphaGEX OI Snapshot"
4. Trigger: Daily at 4:30 PM
5. Action: Start a program
   - Program: `python`
   - Arguments: `historical_oi_snapshot_job.py`
   - Start in: `C:\Users\YourUser\AlphaGEX`
6. Conditions: Only run if connected to internet

#### Option C: Using Python Scheduler (Cross-platform)

Add to your main app startup:

```python
import schedule
import time
from datetime import datetime

def run_oi_snapshot():
    """Run OI snapshot if it's a weekday"""
    if datetime.now().weekday() < 5:  # Monday = 0, Friday = 4
        os.system("python historical_oi_snapshot_job.py")

# Schedule for 4:30 PM ET
schedule.every().day.at("16:30").do(run_oi_snapshot)

# Run in background thread
while True:
    schedule.run_pending()
    time.sleep(60)
```

### 3. Monitor Execution

```bash
# View today's snapshot log
tail -f logs/oi_snapshot.log

# Check if snapshots are running
ls -lh logs/oi_snapshot.log

# Verify database population
sqlite3 gex_copilot.db "SELECT date, symbol, COUNT(*) as strikes FROM historical_open_interest GROUP BY date, symbol ORDER BY date DESC LIMIT 10;"
```

## Configuration

### Default Symbols Tracked

The job tracks these symbols by default:
```python
DEFAULT_SYMBOLS = [
    'SPY', 'QQQ', 'IWM',           # Major ETFs
    'AAPL', 'MSFT', 'NVDA',        # Tech
    'TSLA', 'AMZN', 'GOOGL', 'META' # Growth
]
```

### Add More Symbols

```bash
# Snapshot additional symbols
python historical_oi_snapshot_job.py SPY QQQ AMD COIN ARKK

# Or edit DEFAULT_SYMBOLS in the script
```

### Timeframe

The job captures **next 60 days** of expirations by default. This covers:
- Weekly expirations
- Monthly OPEX
- Quarterly expirations (if within 60 days)

## Data Usage

### Query OI Accumulation

```python
from historical_oi_snapshot_job import calculate_oi_accumulation

# Check if $580 strike is accumulating
result = calculate_oi_accumulation(
    symbol='SPY',
    strike=580.0,
    expiration='2025-12-20',
    days_back=5
)

print(f"OI Change: {result['oi_change']:,} contracts ({result['oi_change_pct']:.1f}%)")
print(f"Accumulation Rate: {result['accumulation_rate']}")
# Output: RAPID (>50% growth in 5 days)
```

### Identify Top Accumulation Strikes

```sql
-- Find strikes with highest OI growth in last 5 days
SELECT
    symbol,
    strike,
    expiration_date,
    (call_oi + put_oi) as current_oi,
    LAG(call_oi + put_oi, 5) OVER (PARTITION BY symbol, strike, expiration_date ORDER BY date) as oi_5d_ago,
    ((call_oi + put_oi) - LAG(call_oi + put_oi, 5) OVER (PARTITION BY symbol, strike, expiration_date ORDER BY date)) as oi_change
FROM historical_open_interest
WHERE date >= date('now', '-7 days')
    AND (call_oi + put_oi) > 1000  -- Significant size
ORDER BY oi_change DESC
LIMIT 20;
```

## Integration with Psychology Trap Detector

The `psychology_trap_detector.py` uses this data in `analyze_forward_gex()`:

```python
# Calculate OI growth rate (accumulation factor)
oi_factor = calculate_oi_growth_rate(symbol, strike, expiration)

# Magnet strength formula includes OI accumulation
magnet_strength = (gamma_size / 1e9) * oi_factor * dte_multiplier * monthly_weight

# RAPID accumulation (>50% growth) = 3x multiplier
# MODERATE (20-50%) = 2x
# SLOW (0-20%) = 1x
```

## Expected Output

### Successful Run
```
################################################################################
# HISTORICAL OPEN INTEREST SNAPSHOT JOB
# Date: 2025-11-14
# Symbols: 10
# Test Mode: NO
################################################################################

============================================================
📸 Snapshotting SPY - 2025-11-14
============================================================
   Found 42 expirations
   Processing 8 near-term expirations (next 60 days)
   • 2025-11-15 (1 DTE)... ✅ 87 calls, 92 puts
   • 2025-11-22 (8 DTE)... ✅ 156 calls, 143 puts
   • 2025-12-20 (36 DTE)... ✅ 312 calls, 298 puts
   ...

   ✅ SPY complete: 8 expirations, 2,431 strikes

================================================================================
📊 SUMMARY
================================================================================
   Date: 2025-11-14
   Symbols processed: 10/10
   Total strikes captured: 18,492
   Test mode: NO
   Database: ./gex_copilot.db
================================================================================
```

## Troubleshooting

### No Data Returned

**Problem:** "No expirations available"
**Solution:** Check if symbol has options:
```python
import yfinance as yf
ticker = yf.Ticker("SPY")
print(ticker.options)  # Should return list of dates
```

### Database Errors

**Problem:** "UNIQUE constraint failed"
**Solution:** Snapshot already exists for today. To re-run:
```sql
DELETE FROM historical_open_interest WHERE date = date('now');
```

### Rate Limiting

**Problem:** Yahoo Finance blocking requests
**Solution:** Add delays between symbols:
```python
import time
time.sleep(5)  # 5 seconds between symbols
```

## Performance

- **Time per symbol:** ~15-30 seconds (depends on # of expirations)
- **Total runtime (10 symbols):** ~3-5 minutes
- **Database growth:** ~2-5 MB per day (10 symbols, 60-day window)
- **Annual data size:** ~1-2 GB

## Data Retention

### Keep Last 90 Days

```sql
-- Delete snapshots older than 90 days
DELETE FROM historical_open_interest WHERE date < date('now', '-90 days');
```

### Archive Old Data

```bash
# Export to CSV
sqlite3 -header -csv gex_copilot.db "SELECT * FROM historical_open_interest WHERE date < date('now', '-90 days')" > archive/oi_$(date +%Y).csv

# Then delete from database
sqlite3 gex_copilot.db "DELETE FROM historical_open_interest WHERE date < date('now', '-90 days')"
```

## Next Steps

1. **Run first snapshot manually** to verify setup
2. **Schedule daily job** using cron/Task Scheduler
3. **Backfill historical data** (optional but recommended):
   ```bash
   python backfill_historical_data.py --days 365
   ```
   This eliminates the 5-7 day waiting period by populating historical data immediately.
4. **Test OI accumulation calculations** using historical data
5. **Integrate with Forward GEX** analysis

## Support

For issues or questions:
- Check logs: `logs/oi_snapshot.log`
- Test query: `python historical_oi_snapshot_job.py --test`
- Database check: `sqlite3 gex_copilot.db "SELECT COUNT(*) FROM historical_open_interest"`
