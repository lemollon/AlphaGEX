# Running the GEX Backtester Locally

## Quick Start

```bash
# Run a simple backtest for SPY over 3 months
python run_all_backtests.py --symbol SPY --start 2024-08-01 --end 2024-11-01

# Run individual strategy backtests
python backtest_gex_strategies.py --symbol SPY --start 2024-01-01 --end 2024-11-01
python backtest_options_strategies.py --symbol SPY --start 2024-01-01 --end 2024-11-01
```

## What Gets Tested

**GEX Strategies (5 total):**
- Flip Point Breakout (long when breaks above flip)
- Flip Point Breakdown (short when breaks below flip)  
- Call Wall Rejection (short when hits resistance)
- Put Wall Bounce (long when hits support)
- Negative GEX Squeeze (explosive moves in dealer short gamma)

**Options Strategies (11 total from config):**
- Uses real GEX conditions from Trading Volatility API
- Tests entry signals based on net GEX, flip point distance, walls, etc.

## Data Requirements

### ✅ Available Now (via Trading Volatility API):
- Current/latest GEX data (net GEX, flip point, walls)

### ❌ Currently Blocked in This Environment:
- Historical GEX data (`/gex/history` endpoint returns 403)
- Historical stock prices (yfinance blocked by Yahoo Finance)

### 💡 Run on Your Local Machine:
Since your scanner works locally (can access Trading Volatility), run the backtester there:

1. Your machine → Trading Volatility API ✅ Works
2. This environment → Trading Volatility API ❌ 403 blocked

## Results Storage

Results are saved to: `/home/user/AlphaGEX/gex_copilot.db`

Tables:
- `backtest_results` - Individual strategy performance
- `backtest_summary` - Comparison across categories

## Viewing Results

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('gex_copilot.db')

# Get all results
df = pd.read_sql('SELECT * FROM backtest_results ORDER BY expectancy_pct DESC', conn)
print(df[['strategy_name', 'total_trades', 'win_rate', 'expectancy_pct', 'total_return_pct']])

# Get summary
summary = pd.read_sql('SELECT * FROM backtest_summary ORDER BY timestamp DESC LIMIT 1', conn)
print(summary)

conn.close()
```

## Once You Have Real Data

The backtester is ready to use real GEX data once:
1. Trading Volatility historical endpoint works on your machine
2. Stock price data is available (IEX Cloud or Polygon.io)

Then you'll get real validation of whether GEX signals have actual predictive edge.
