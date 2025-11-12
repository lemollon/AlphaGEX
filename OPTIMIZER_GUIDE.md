# Strategy Optimizer Guide

## Overview

The AI Strategy Optimizer uses Claude (via LangChain) to analyze your trading strategies and provide specific, actionable optimization recommendations based on REAL backtest data.

## Features

✅ **Dynamic Stats Integration** - Uses live win rates that auto-update from backtests
✅ **Specific Recommendations** - Not vague advice, actual parameter values
✅ **Profitability Ranking** - Identifies which strategies actually make money
✅ **Resource Allocation** - Tells you where to focus your effort
✅ **Real-Time Trade Recommendations** - AI suggests specific trades based on current market

## API Endpoints

### 1. Optimize Specific Strategy

```bash
GET /api/optimizer/analyze/{strategy_name}
```

**Example**:
```bash
curl http://localhost:8000/api/optimizer/analyze/BULLISH_CALL_SPREAD
```

**Response**:
```json
{
  "success": true,
  "strategy": "BULLISH_CALL_SPREAD",
  "optimization": {
    "live_stats": {
      "win_rate": 0.672,
      "expectancy": 1.23,
      "total_trades": 47,
      "last_updated": "2025-11-12T14:23:45",
      "source": "backtest"
    },
    "analysis": "AI analysis with specific recommendations...",
    "recent_changes": [...]
  }
}
```

### 2. Analyze All Strategies

```bash
GET /api/optimizer/analyze-all
```

**Example**:
```bash
curl http://localhost:8000/api/optimizer/analyze-all
```

**Returns**:
- Ranking of all strategies by expectancy
- Top 3 strategies to focus on
- Strategies to kill (losing money)
- Quick wins (easy improvements)
- Resource allocation recommendations

### 3. Get Trade Recommendation

```bash
POST /api/optimizer/recommend-trade
```

**Request Body**:
```json
{
  "symbol": "SPY",
  "price": 580.50,
  "net_gex": -2500000000,
  "vix": 18.5,
  "flip_point": 578.0,
  "call_wall": 585.0,
  "put_wall": 575.0
}
```

**Response**:
```json
{
  "success": true,
  "trade_recommendation": {
    "recommendation": "BUY call spread at 580/585...",
    "market_data": {...},
    "timestamp": "2025-11-12T15:30:00"
  }
}
```

## CLI Usage

### Optimize Specific Strategy

```bash
python ai_strategy_optimizer.py --strategy BULLISH_CALL_SPREAD
```

**Output**:
```
🤖 Optimizing 'BULLISH_CALL_SPREAD' with Claude AI...

================================================================================
AI STRATEGY OPTIMIZATION
================================================================================

CURRENT PERFORMANCE:
- Win Rate: 67.2% (from 47 real trades)
- Expectancy: +1.23%
- Last Updated: 2025-11-12 (auto-updated from backtest)

RECOMMENDATIONS:
1. [HIGH IMPACT, EASY] Tighten entry filter: Add VIX > 16 requirement
   - Expected improvement: +2-3% win rate
   - Reasoning: Analysis shows 80% win rate when VIX > 16 vs 60% when < 16

2. [MEDIUM IMPACT, EASY] Adjust stop loss from -15% to -12%
   - Expected improvement: +0.5% expectancy
   - Reasoning: Most losses exceed -12%, cutting earlier preserves capital

3. [HIGH IMPACT, MEDIUM] Add flip point distance filter: Only enter when price within 1% of flip
   - Expected improvement: +5% win rate
   - Reasoning: Highest win rate occurs near flip point transitions

VERDICT: IMPLEMENT - Strong strategy, minor tweaks will improve further
================================================================================
```

### Analyze All Strategies

```bash
python ai_strategy_optimizer.py --all
```

**Output**:
```
🤖 Analyzing all strategies with Claude AI...

================================================================================
AI ANALYSIS REPORT
================================================================================

STRATEGY RANKINGS (by expectancy):
1. BULLISH_CALL_SPREAD: +1.23% expectancy, 67% win rate ⭐
2. IRON_CONDOR: +0.87% expectancy, 74% win rate ⭐
3. PUT_CREDIT_SPREAD: +0.45% expectancy, 68% win rate
4. CALL_CREDIT_SPREAD: -0.12% expectancy, 52% win rate ❌
5. STRADDLE: -0.89% expectancy, 45% win rate ❌

TOP 3 STRATEGIES TO FOCUS ON:
1. BULLISH_CALL_SPREAD - Best overall, focus 40% of resources
2. IRON_CONDOR - Consistent winner, focus 30% of resources
3. PUT_CREDIT_SPREAD - Solid performer, focus 20% of resources

STRATEGIES TO KILL:
- CALL_CREDIT_SPREAD: Negative expectancy, poor risk/reward
- STRADDLE: 45% win rate, losing money consistently

QUICK WINS:
- BULLISH_CALL_SPREAD: Add VIX filter (+2-3% win rate)
- IRON_CONDOR: Widen wings by 1 strike (+0.5% expectancy)

RESOURCE ALLOCATION:
Focus 70% of effort on top 2 strategies. Kill the losers immediately.
================================================================================
```

## Setup

### 1. Install Dependencies

```bash
pip install langchain-anthropic
```

### 2. Set API Key

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
# or
export CLAUDE_API_KEY="your-api-key-here"
```

### 3. Run Backtests First

The optimizer needs real backtest data to analyze:

```bash
python backtest_gex_strategies.py
```

This will:
1. Run backtests for all strategies
2. Auto-save results to `.strategy_stats/strategy_stats.json`
3. Make stats available to optimizer

## How It Works

### 1. Dynamic Stats Integration

The optimizer pulls **live, auto-updated** win rates from `strategy_stats.py`:

```python
from strategy_stats import get_strategy_stats

live_stats = get_strategy_stats()
# Returns: {'BULLISH_CALL_SPREAD': {'win_rate': 0.672, ...}}
```

**Advantages**:
- Always uses latest backtest results
- No hardcoded win rates
- Shows when data was last updated
- Includes expectancy, Sharpe ratio, etc.

### 2. AI Analysis

Claude analyzes the data and provides:
- **Specific** recommendations (exact numbers, not vague advice)
- **Impact assessment** (High/Medium/Low)
- **Difficulty estimate** (Easy/Medium/Hard)
- **Expected improvement** (quantified)

### 3. Auto-Update Visibility

The optimizer shows recent automatic updates:

```json
"recent_changes": [
  {
    "timestamp": "2025-11-12T14:23:45",
    "item": "BULLISH_CALL_SPREAD",
    "old_value": "win_rate=65.0%",
    "new_value": "win_rate=67.2%",
    "reason": "Updated from backtest (47 trades)"
  }
]
```

## Example Workflow

### Step 1: Run Backtests

```bash
python backtest_gex_strategies.py
```

**Output**:
```
Running backtest for BULLISH_CALL_SPREAD...
Completed: 47 trades, 67.2% win rate

📊 AUTO-UPDATE: STRATEGY_STATS > BULLISH_CALL_SPREAD
   Old: win_rate=65.0% → New: win_rate=67.2%
   Saved to .strategy_stats/strategy_stats.json
```

### Step 2: Optimize Strategies

```bash
# Optimize specific strategy
curl http://localhost:8000/api/optimizer/analyze/BULLISH_CALL_SPREAD

# Or analyze all
curl http://localhost:8000/api/optimizer/analyze-all
```

### Step 3: Implement Recommendations

Based on AI analysis:
1. Update strategy parameters in `config_and_database.py`
2. Re-run backtests to validate
3. Stats auto-update if improved

### Step 4: Get Real-Time Trade Recommendations

```bash
curl -X POST http://localhost:8000/api/optimizer/recommend-trade \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "price": 580.50,
    "net_gex": -2500000000,
    "vix": 18.5
  }'
```

**Response**:
```json
{
  "recommendation": "BUY CALL_SPREAD 580/585",
  "entry": 580.50,
  "stop": 578.00,
  "target": 585.00,
  "confidence": 75,
  "reasoning": "Negative GEX suggests upside momentum..."
}
```

## Troubleshooting

### Error: "ANTHROPIC_API_KEY not set"

**Solution**:
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### Error: "No backtest results found"

**Solution**: Run backtests first:
```bash
python backtest_gex_strategies.py
```

### Error: "langchain-anthropic not installed"

**Solution**:
```bash
pip install langchain-anthropic
```

### Error: "Strategy not found in dynamic stats"

**Solution**: Check available strategies:
```bash
python -c "from strategy_stats import get_strategy_stats; print(get_strategy_stats().keys())"
```

## Advanced Usage

### Custom Optimization Prompts

Modify prompts in `ai_strategy_optimizer.py` to focus on specific aspects:

```python
# In optimize_with_dynamic_stats():
prompt = f"""Analyze '{strategy_name}' focusing on:
1. Risk management (stop losses, position sizing)
2. Entry timing (reduce false signals)
3. Exit optimization (maximize winners)
...
"""
```

### Batch Optimization

Optimize all strategies in one go:

```bash
for strategy in BULLISH_CALL_SPREAD IRON_CONDOR PUT_CREDIT_SPREAD; do
    curl http://localhost:8000/api/optimizer/analyze/$strategy
done
```

### Integration with Paper Trading

Use trade recommendations in your paper trading bot:

```python
# In your paper trader:
import requests

# Get current market data
market_data = get_current_market_data()

# Get AI recommendation
response = requests.post(
    "http://localhost:8000/api/optimizer/recommend-trade",
    json=market_data
)

recommendation = response.json()['trade_recommendation']

if recommendation['action'] == 'BUY' and recommendation['confidence'] > 70:
    execute_trade(recommendation)
```

## Benefits

✅ **Data-Driven** - Uses real backtest results, not guesses
✅ **Specific** - Exact parameters, not vague suggestions
✅ **Automatic** - Integrates with auto-updating stats system
✅ **Transparent** - Shows reasoning for every recommendation
✅ **Practical** - Focuses on actionable improvements
✅ **Profitable** - Identifies what actually makes money

---

Last Updated: 2025-11-12
Version: 1.0.0
