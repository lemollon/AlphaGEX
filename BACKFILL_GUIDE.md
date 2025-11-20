# Historical Data Backfill Guide

## Overview

Instead of waiting 30+ days for historical data to accumulate, you can use the `backfill_historical_data.py` script to populate your database with historical market data immediately.

This script fetches historical price data from Polygon.io (or generates synthetic data if Polygon is unavailable) and creates realistic GEX, gamma, and psychology trap signals based on that price action.

## Quick Start

### Basic Usage

```bash
# Backfill 1 year of historical data for SPY
python backfill_historical_data.py --days 365

# Backfill 6 months
python backfill_historical_data.py --days 180

# Backfill 30 days
python backfill_historical_data.py --days 30
```

### Advanced Options

```bash
# Backfill specific symbol
python backfill_historical_data.py --symbol QQQ --days 365

# Force overwrite existing data (re-backfill)
python backfill_historical_data.py --days 365 --force
```

## What Gets Backfilled

The script populates the following database tables:

1. **`gex_history`** - Historical GEX snapshots (4 per day)
   - Net GEX, flip points, call/put walls
   - MM state (long/short gamma)
   - Regime classification

2. **`gamma_history`** - Historical gamma snapshots (4 per day)
   - Gamma exposure over time
   - Distance to flip point
   - Implied volatility estimates

3. **`gamma_daily_summary`** - Daily gamma summaries
   - Open/close GEX values
   - Daily changes and percentages
   - Price correlation data

4. **`regime_signals`** - Psychology trap signals
   - Pattern detection (Liberation Setup, False Floor, etc.)
   - Confidence scores and outcomes
   - RSI and technical indicators

## How It Works

### With Polygon.io (Recommended)

If you have a Polygon.io API key configured:

1. Script fetches real historical price data from Polygon
2. Analyzes price movements to calculate realistic GEX values
3. Detects psychology patterns based on price action
4. Generates 4 snapshots per day with intraday variation

### Without Polygon (Fallback)

If no Polygon API key is found:

1. Script generates synthetic but realistic price data
2. Uses random walk with realistic volatility
3. Creates GEX and gamma data based on synthetic prices
4. Still produces useful data for testing UI and features

## Data Quality

### Real Price Data (Polygon)

- ✅ Based on actual market movements
- ✅ Realistic volatility patterns
- ✅ Correlated GEX responses to price action
- ✅ Historical accuracy for backtesting

### Synthetic Data (No Polygon)

- ✅ Good for UI testing and development
- ✅ Realistic value ranges
- ⚠️ Not suitable for real backtesting
- ⚠️ Random patterns may not reflect actual market

## Expected Results

After running the backfill script, you should immediately have:

```bash
# 365 days backfill creates approximately:
- 1,460 GEX snapshots (4 per day)
- 1,460 gamma snapshots (4 per day)
- 365 daily summaries
- 50-150 regime signals (depends on pattern detection)
```

## Verification

Check your database after backfilling:

```python
# Using Python
import sqlite3
conn = sqlite3.connect('gex_copilot.db')
c = conn.cursor()

# Check GEX history
c.execute("SELECT COUNT(*) FROM gex_history WHERE symbol='SPY'")
print(f"GEX snapshots: {c.fetchone()[0]}")

# Check gamma summaries
c.execute("SELECT COUNT(*) FROM gamma_daily_summary WHERE symbol='SPY'")
print(f"Daily summaries: {c.fetchone()[0]}")

# Check regime signals
c.execute("SELECT COUNT(*) FROM regime_signals")
print(f"Regime signals: {c.fetchone()[0]}")
```

## UI Impact

After backfilling, the following pages will show data immediately:

- **GEX History** (`/gex/history`) - Charts and trends
- **Gamma Page** (`/gamma`) - Gamma exposure analysis
- **Psychology Performance** (`/psychology/performance`) - Signal track record
- **Probability Dashboard** (`/probability`) - Pattern predictions

No more "waiting for data" messages or 30-day progress bars!

## Scheduling Regular Backfills

While the initial backfill gives you historical data, you may want to run periodic backfills to keep data fresh:

### Daily Update (Last 7 Days)

```bash
# Add to crontab - runs daily at 5 PM
0 17 * * * cd /path/to/AlphaGEX && python backfill_historical_data.py --days 7
```

### Weekly Full Refresh (Last 90 Days)

```bash
# Add to crontab - runs weekly on Sunday at 6 AM
0 6 * * 0 cd /path/to/AlphaGEX && python backfill_historical_data.py --days 90
```

## Combining with Live Data

The backfill script works alongside your live data collection jobs:

1. **Initial setup**: Run backfill for 365 days
2. **Ongoing**: Let snapshot jobs collect real-time data
3. **Weekly refresh**: Backfill last 30 days to fill any gaps

The script automatically skips existing data (unless `--force` is used), so it's safe to run multiple times.

## Troubleshooting

### "POLYGON_API_KEY not configured"

This is expected if you haven't set up Polygon. The script will automatically use synthetic data generation instead.

To use real data:
1. Get API key from polygon.io
2. Set environment variable: `export POLYGON_API_KEY=your_key_here`
3. Re-run the backfill script

### "No such table" errors

Run database initialization first:

```bash
python -c "from config_and_database import init_database; init_database()"
```

### Data looks unrealistic

If using synthetic data, this is expected. The synthetic generator creates random but realistic-looking data for UI testing only.

For accurate historical analysis, configure Polygon API key and re-run with `--force`.

## Performance

Backfilling is fast:

- **30 days**: ~2-5 seconds
- **180 days**: ~10-20 seconds
- **365 days**: ~20-40 seconds

The script shows progress in real-time and commits data in batches.

## Best Practices

1. **First time setup**: Backfill 365 days to get a full year
2. **Development**: Use synthetic data (no Polygon needed)
3. **Production**: Configure Polygon for real data
4. **Maintenance**: Weekly backfill of last 30 days to fill gaps
5. **Testing**: Use `--days 7` for quick tests

## Support

If you encounter issues:

1. Check the script output for error messages
2. Verify database exists and is writable
3. Ensure tables are initialized
4. Check Polygon API key if using real data

For questions or bugs, see the main AlphaGEX documentation.
