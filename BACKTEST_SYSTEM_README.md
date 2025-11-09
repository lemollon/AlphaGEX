# AlphaGEX Comprehensive Backtesting System

**Date**: 2025-11-09
**Status**: Ready to Run

## 🎯 Overview

Complete backtesting framework for ALL AlphaGEX strategies with realistic transaction costs, position sizing, and performance metrics.

**What Gets Backtested:**
1. **Psychology Trap Detection** (13 patterns) - Already built
2. **GEX Strategies** (5 strategies) - NEW
3. **Options Strategies** (11 strategies) - NEW

**Total: 29 individual strategies tested**

---

## 📊 Available Backtests

### 1. Psychology Trap Detection Backtest

**File**: `psychology_backtest.py`

**Strategies Tested**:
- GAMMA_SQUEEZE_CASCADE
- FLIP_POINT_CRITICAL
- CAPITULATION_CASCADE
- LIBERATION_TRADE
- FALSE_FLOOR
- EXPLOSIVE_CONTINUATION
- POST_OPEX_REGIME_FLIP
- DEALER_PUMP
- DEALER_DUMP
- DEALER_COMPRESSION
- EXPLOSIVE_REVERSAL
- And more...

**Usage**:
```bash
python psychology_backtest.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

### 2. GEX Strategies Backtest

**File**: `backtest_gex_strategies.py`

**Strategies Tested**:
- Flip Point Breakout (bullish)
- Flip Point Breakdown (bearish)
- Call Wall Rejection (bearish)
- Put Wall Bounce (bullish)
- Negative GEX Squeeze (explosive moves)

**Usage**:
```bash
python backtest_gex_strategies.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

###3. Options Strategies Backtest

**File**: `backtest_options_strategies.py`

**Strategies Tested** (from STRATEGIES config):
- BULLISH_CALL_SPREAD
- BEARISH_PUT_SPREAD
- BULL_PUT_SPREAD
- BEAR_CALL_SPREAD
- IRON_CONDOR
- IRON_BUTTERFLY
- LONG_STRADDLE
- LONG_STRANGLE
- NEGATIVE_GEX_SQUEEZE
- POSITIVE_GEX_BREAKDOWN
- PREMIUM_SELLING
- CALENDAR_SPREAD

**Usage**:
```bash
python backtest_options_strategies.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

### 4. Master Backtest Runner (ALL Strategies)

**File**: `run_all_backtests.py`

Runs ALL backtests sequentially and generates comparison dashboard.

**Usage**:
```bash
python run_all_backtests.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

**Output**:
- Individual strategy results
- Comparison dashboard
- Profitability assessment
- Recommendations

---

## 📈 Key Metrics Tracked

For each strategy, we calculate:

### Win/Loss Metrics:
- **Total Trades**: Number of signals generated
- **Winning Trades**: Trades that made money
- **Losing Trades**: Trades that lost money
- **Win Rate**: % of winning trades

### Return Metrics:
- **Avg Win %**: Average gain on winning trades
- **Avg Loss %**: Average loss on losing trades
- **Largest Win %**: Best single trade
- **Largest Loss %**: Worst single trade
- **Total Return %**: Cumulative return over period

### Risk Metrics:
- **Expectancy %**: Expected profit per trade (CRITICAL METRIC)
- **Max Drawdown %**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted return
- **Avg Trade Duration**: How long positions are held

---

## 💰 Transaction Costs

**REALISTIC costs included** (most backtests ignore these):

### Default Costs:
- **Commission**: 0.05% per trade side (0.10% round trip for equities)
- **Slippage**: 0.10% per trade (realistic fill degradation)
- **Options Commission**: 0.10% per side (0.20% round trip)
- **Options Slippage**: 0.15% (wider spreads)

### Why This Matters:
Even a 55% win rate strategy can LOSE money if costs eat 0.3% per trade.

**Example**:
- Strategy shows 58% win rate, +1.2% avg win, -0.8% avg loss
- **Expectancy without costs**: +0.38% per trade (profitable!)
- **Expectancy with costs**: +0.08% per trade (barely profitable)
- **Real-world slippage**: -0.12% per trade (LOSING MONEY)

This is why we include costs - to see what ACTUALLY works.

---

## 🎯 Profitability Criteria

Strategies are categorized as:

### ✅ PROFITABLE (Safe to paper trade):
- Expectancy > 0.5% per trade
- Win rate > 55%
- Total trades > 10

### ⚠️ MARGINAL (Proceed with caution):
- Expectancy 0-0.5% per trade
- Win rate 50-55%
- Needs improvement or careful execution

### ❌ LOSING (Do NOT trade):
- Expectancy < 0%
- Win rate < 50%
- Costs outweigh edge

---

## 📊 Database Storage

Results are saved to SQLite database (`alphagex.db`):

### Tables Created:

**backtest_results**:
```sql
- id
- timestamp
- strategy_name
- symbol
- start_date
- end_date
- total_trades
- winning_trades
- losing_trades
- win_rate
- avg_win_pct
- avg_loss_pct
- largest_win_pct
- largest_loss_pct
- expectancy_pct
- total_return_pct
- max_drawdown_pct
- sharpe_ratio
- avg_trade_duration_days
```

**backtest_summary**:
```sql
- id
- timestamp
- symbol
- start_date
- end_date
- psychology_trades
- psychology_win_rate
- psychology_expectancy
- gex_trades
- gex_win_rate
- gex_expectancy
- options_trades
- options_win_rate
- options_expectancy
```

---

## 🔌 API Endpoints

Access backtest results via REST API:

### 1. Get All Backtest Results
```
GET /api/backtests/results?strategy_name=GAMMA_SQUEEZE_CASCADE&limit=50
```

Returns all backtest runs for a strategy (or all strategies if no filter).

### 2. Get Backtest Summary
```
GET /api/backtests/summary
```

Returns latest summary comparing psychology, GEX, and options performance.

### 3. Get Best Strategies
```
GET /api/backtests/best-strategies?min_expectancy=0.5&min_win_rate=55
```

Returns only profitable strategies that meet criteria.

---

## 🚀 Quick Start Guide

### Step 1: Run All Backtests
```bash
cd /home/user/AlphaGEX
python run_all_backtests.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

**Expected Runtime**: 5-10 minutes

### Step 2: Review Results
Check terminal output for:
- Individual strategy performance
- Comparison dashboard
- Profitability recommendations

### Step 3: Query Database
```bash
sqlite3 alphagex.db
```

```sql
-- Get all profitable strategies
SELECT strategy_name, win_rate, expectancy_pct, total_return_pct
FROM backtest_results
WHERE expectancy_pct > 0.5 AND win_rate > 55
ORDER BY expectancy_pct DESC;

-- Get best psychology patterns
SELECT strategy_name, total_trades, win_rate, expectancy_pct
FROM backtest_results
WHERE strategy_name LIKE '%CASCADE%'
   OR strategy_name LIKE '%FLIP_POINT%'
ORDER BY expectancy_pct DESC;
```

### Step 4: Access via API
```bash
# Start backend
cd backend
python main.py

# In another terminal
curl http://localhost:8000/api/backtests/summary
curl http://localhost:8000/api/backtests/best-strategies
```

---

## 📝 Interpretation Guide

### Example Output:
```
BACKTEST RESULTS: GAMMA_SQUEEZE_CASCADE
===============================================================================
Period: 2022-01-01 to 2024-12-31
Total Trades: 47
Win Rate: 68.1% (32W / 15L)
Avg Win: +2.85%
Avg Loss: -1.32%
Expectancy: +1.54% per trade
Total Return: +72.38%
Max Drawdown: -8.24%
Sharpe Ratio: 1.87
Avg Duration: 2.3 days
===============================================================================
✅ PROFITABLE STRATEGY - Has positive edge
===============================================================================
```

**What This Means**:
- **68% win rate**: Very good (above 60% threshold)
- **Expectancy +1.54%**: Excellent (well above 0.5% minimum)
- **Total Return +72%**: Strong performance over 3 years
- **Max Drawdown -8%**: Manageable risk
- **Sharpe 1.87**: Good risk-adjusted returns
- **Verdict**: SAFE TO PAPER TRADE

### Red Flags to Watch For:
```
BACKTEST RESULTS: FALSE_FLOOR
===============================================================================
Total Trades: 23
Win Rate: 47.8% (11W / 12L)
Expectancy: -0.23% per trade
Total Return: -5.29%
Max Drawdown: -15.67%
===============================================================================
❌ LOSING STRATEGY - Do not trade this
===============================================================================
```

**What This Means**:
- Win rate below 50%
- Negative expectancy
- Losing money overall
- **Verdict**: DO NOT TRADE

---

## ⚠️ Important Limitations

### 1. Simulated Data
**GEX and options backtests use SIMULATED data**:
- GEX calculations are approximations
- Options pricing is simplified
- Real data will differ

**For production**: Replace simulations with real GEX and option chain data.

### 2. Survivorship Bias
We're only testing SPY (which survived). Doesn't account for:
- Market regime changes
- Black swan events
- Structural market shifts

### 3. Overfitting Risk
29 strategies tested = higher chance some look good by luck.

**Solution**:
- Focus on strategies with 50+ trades
- Paper trade before live trading
- Combine multiple profitable strategies

### 4. Execution Assumptions
Assumes perfect execution at calculated prices. Reality:
- Slippage can be worse
- Fills may not occur at target prices
- Market impact from larger sizes

---

## 🎓 Next Steps After Backtesting

### Phase 1: Review Results (Done after running backtests)
- Identify strategies with expectancy > 0.5%
- Note win rates above 55%
- Check total trades > 20 for statistical significance

### Phase 2: Paper Trading (90 days MINIMUM)
- Trade ONLY the top 2-3 strategies
- Use real-time data
- Track every signal
- Compare actual results vs backtest

### Phase 3: Start Micro-Trading
**IF paper trading confirms profitability**:
- Start with $100-200 per trade
- Trade 1 contract, not 10
- Run for 50 trades minimum
- Re-evaluate

### Phase 4: Scale Gradually
**IF micro-trading is profitable for 100+ trades**:
- Increase size by 50% every 50 profitable trades
- Never risk more than 2% of capital per trade
- Keep tracking performance vs backtest

### Phase 5: Continuous Monitoring
- Re-run backtests every quarter
- Update strategies as market changes
- Kill strategies that stop working

---

## 💡 Pro Tips

### 1. Don't Chase Best Results
The #1 performing strategy in backtest often fails live (overfit).

**Better approach**: Trade top 3-5 strategies as a portfolio.

### 2. Focus on Expectancy, Not Win Rate
- 70% win rate with 0.2% expectancy = Barely profitable
- 55% win rate with 1.5% expectancy = Very profitable

**Expectancy is king.**

### 3. Sample Size Matters
- 10 trades = Could be luck
- 50 trades = Starting to be meaningful
- 200+ trades = Statistically significant

### 4. Costs Kill Edge
A strategy with 0.8% expectancy becomes unprofitable if:
- Your commissions are higher
- Slippage is worse
- You miss fills

Always assume worse costs than backtested.

### 5. Market Regimes Change
A strategy that worked 2022-2024 might fail in 2025 if:
- Volatility regime shifts
- Fed policy changes
- Market structure evolves

**Stay adaptive.**

---

## 📚 File Structure

```
/home/user/AlphaGEX/
├── backtest_framework.py           # Base classes & utilities
├── backtest_gex_strategies.py      # GEX strategy backtest
├── backtest_options_strategies.py  # Options strategy backtest
├── psychology_backtest.py          # Psychology pattern backtest
├── run_all_backtests.py           # Master runner
├── alphagex.db                     # Results database
└── BACKTEST_SYSTEM_README.md      # This file
```

---

## 🐛 Troubleshooting

### Error: "No module named 'yfinance'"
```bash
pip install yfinance pandas numpy
```

### Error: "No data fetched for SPY"
- Check internet connection
- Verify date range is valid
- Try different date range

### Database locked error
- Close any open database connections
- Make sure only one backtest runs at a time

### Backtest runs but shows 0 trades
- Check date range (need 2+ years minimum)
- Verify strategy conditions aren't too strict
- Check if price data was fetched successfully

---

## 📞 Support

**Questions?** Check:
1. This README first
2. Code comments in backtest files
3. API endpoint documentation in backend/main.py

**Found a bug?** Note it and continue - backtests are tools for guidance, not gospel.

---

**Remember**: Backtest results are HYPOTHETICAL. Paper trade for 90 days before risking real money.

**Good luck!** 🚀
