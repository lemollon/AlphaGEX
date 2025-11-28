# Realistic Option Pricing Implementation

## Overview

This implementation replaces the simplified directional option pricing model with realistic Black-Scholes pricing, including Greeks calculations, bid/ask spreads, and time decay modeling.

## What Changed

### Previous (Simplified) Model
```python
# Simplified directional logic
if price_change_pct > 2.0:
    return +100  # Max gain
elif price_change_pct < -1.0:
    return -100  # Max loss
else:
    return price_change_pct * 30  # Linear interpolation
```

**Problems:**
- No actual strike selection
- No Greeks tracking
- No time decay modeling
- No bid/ask spreads
- Fixed P&L ratios regardless of spread width
- Assumes theoretical fills every time

### New (Realistic) Model
```python
# Realistic Black-Scholes pricing
spread = create_bullish_call_spread(
    spot_price=400.0,
    volatility=0.25,
    dte=30,
    target_delta=0.30,  # Select 30-delta strikes
    spread_width_pct=5.0
)

pnl = spread_pricer.calculate_spread_pnl(
    spread_details=spread,
    current_price=420.0,
    days_held=10,
    entry_volatility=0.25,
    exit_volatility=0.28
)
```

**Features:**
- Real strike selection based on delta/moneyness
- Greeks: delta, gamma, theta, vega
- Intrinsic and time value separation
- Bid/ask spread: 4% typical
- Multi-leg slippage: 1.5%
- Time decay properly modeled
- IV impact on P&L

## Implementation Details

### Files Added

#### `realistic_option_pricing.py`
Core pricing module with three main classes:

**BlackScholesOption:**
- Full Black-Scholes implementation
- Greeks calculations (delta, gamma, theta, vega)
- Handles calls and puts
- Risk-free rate: 5% default

**StrikeSelector:**
- `select_strike_by_delta()`: Choose strikes based on target delta (e.g., 30-delta)
- `select_strike_by_moneyness()`: Choose strikes based on % OTM/ITM
- `get_available_strikes()`: Generate realistic $5 strike intervals

**SpreadPricer:**
- `price_vertical_spread()`: Price bull/bear spreads with bid/ask
- `calculate_spread_pnl()`: Calculate P&L with time decay and IV changes
- Includes slippage for multi-leg orders

**Convenience Functions:**
- `create_bullish_call_spread()`: Easy debit spread creation
- `create_bearish_put_spread()`: Easy debit spread creation

#### `test_realistic_pricing_integration.py`
Validation tests to ensure integration works correctly.

### Files Modified

#### `backtest_options_strategies.py`

**New Parameters:**
- `use_realistic_pricing`: Flag to enable realistic pricing (default: True)
- `spread_pricer`: SpreadPricer instance for calculations
- `strike_selector`: StrikeSelector instance for strike selection

**New Methods:**
- `estimate_iv_from_vol_rank()`: Maps vol_rank (0-100) to IV (10%-40%)
- `simulate_option_pnl_realistic()`: Black-Scholes pricing for spreads
- `simulate_option_pnl_simplified()`: Renamed old method for fallback

**Modified Logic:**
- Uses realistic pricing for vertical spreads: BULLISH_CALL_SPREAD, BEARISH_PUT_SPREAD, BULL_PUT_SPREAD, BEAR_CALL_SPREAD
- Falls back to simplified pricing for complex strategies: IRON_CONDOR, IRON_BUTTERFLY, LONG_STRADDLE, LONG_STRANGLE, etc.
- Stores Greeks and spread details in trade notes

## Strategy-Specific Pricing

### Vertical Spreads (Realistic)

**BULLISH_CALL_SPREAD:**
- Long call: 30-delta (slightly OTM)
- Short call: 5% higher strike
- Typical spread width: $20 on SPY $400
- Includes bid/ask spread and slippage

**BEARISH_PUT_SPREAD:**
- Long put: 30-delta (slightly OTM)
- Short put: 5% lower strike
- Similar structure to bull call spread

**BULL_PUT_SPREAD (Credit):**
- Sell put spread 5% below market
- 20-delta short put
- Collect credit (debit inverted)

**BEAR_CALL_SPREAD (Credit):**
- Sell call spread 5% above market
- 20-delta short call
- Collect credit (debit inverted)

### Complex Strategies (Simplified)

These strategies still use simplified pricing because they involve:
- Multiple legs (4+ legs for iron condor)
- Complex P&L profiles
- Volatility sensitivity that's harder to model

Strategies using simplified pricing:
- IRON_CONDOR
- IRON_BUTTERFLY
- LONG_STRADDLE
- LONG_STRANGLE
- NEGATIVE_GEX_SQUEEZE
- POSITIVE_GEX_BREAKDOWN
- PREMIUM_SELLING
- CALENDAR_SPREAD

**Future Enhancement:** These could be upgraded to realistic pricing with additional development.

## Expected Changes in Results

### More Conservative P&L
Realistic pricing will likely show:
- **Lower win rates**: Bid/ask spreads and slippage reduce profitability
- **More realistic max profits**: Not every winning trade hits max profit
- **Theta decay impact**: Long options decay faster, credit spreads benefit
- **IV impact**: Changes in IV affect P&L (vega)

### Example Comparison

**Simplified Model (Previous):**
```
BULLISH_CALL_SPREAD: 62.4% win rate, +6.69% expectancy
```

**Realistic Model (Expected):**
```
BULLISH_CALL_SPREAD: ~55-60% win rate, +2-4% expectancy
```

The realistic model should show:
- Lower expectancy due to bid/ask spreads (4%) + slippage (1.5%)
- More accurate representation of time decay
- Better handling of small moves (not just max gain/loss)

## Greeks in Trade Notes

Each trade now includes detailed information:

**Example Trade Note:**
```
DTE: 10, Strikes: $420/$440, Debit: $3.61, Delta: 0.170, Theta: $-0.08/day
```

This allows analysis of:
- Which delta ranges perform best
- Theta decay impact on profitability
- Strike selection effectiveness

## IV Estimation

Since we don't have real option chain data yet, IV is estimated from vol_rank:

```python
vol_rank = 0   → IV = 10%  (low volatility)
vol_rank = 50  → IV = 25%  (medium volatility)
vol_rank = 100 → IV = 40%  (high volatility)
```

**Future Enhancement:** Fetch real IV from option chain data via Polygon.io or similar.

## Running the Backtest

### Quick Test
```bash
python backtest_options_strategies.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

### Comparison Script
```bash
./run_backtest_comparison.sh
```

This will:
1. Run full backtest with realistic pricing
2. Save results to PostgreSQL
3. Show summary statistics

### Check Results
```sql
-- View strategy results
SELECT
    strategy_name,
    total_trades,
    win_rate,
    avg_pnl_pct,
    expectancy_pct,
    max_drawdown_pct
FROM backtest_results
WHERE run_date >= CURRENT_DATE
ORDER BY expectancy_pct DESC;

-- View individual trades with Greeks
SELECT
    entry_date,
    strategy,
    pnl_percent,
    notes
FROM backtest_trades
WHERE entry_date >= '2022-01-01'
    AND strategy = 'BULLISH_CALL_SPREAD'
ORDER BY entry_date DESC
LIMIT 10;
```

## Next Steps

### 1. Run Full Backtest
Deploy and run the backtest to see realistic results:
```bash
./run_backtest_comparison.sh
```

### 2. Analyze Results
Compare realistic vs simplified pricing:
- Which strategies benefit from realistic pricing?
- How much do bid/ask spreads impact profitability?
- Is theta decay significant over the holding period?

### 3. Future Enhancements

**Short Term:**
- Add realistic pricing for iron condors and iron butterflies
- Implement straddle/strangle realistic pricing
- Better IV estimation (historical IV data)

**Medium Term:**
- Fetch real option chain data from Polygon.io
- Use actual bid/ask spreads from market data
- Track real Greeks from market data

**Long Term:**
- Implement volatility surface modeling
- Add early exit logic based on Greeks
- Optimize strike selection based on backtest results
- Add position sizing based on delta exposure

## Dependencies

**New Dependency:**
- `scipy`: For statistical functions (norm.cdf, norm.pdf)

Already installed via:
```bash
pip install scipy
```

## Validation

Run validation tests:
```bash
python test_realistic_pricing_integration.py
```

Expected output:
```
✅ ALL VALIDATION TESTS PASSED
```

## Summary

This implementation brings AlphaGEX closer to reality by:
1. Using actual option pricing models (Black-Scholes)
2. Tracking Greeks for position management
3. Modeling real market frictions (bid/ask, slippage)
4. Separating intrinsic and time value
5. Accounting for IV changes

The results should be more conservative but more accurate, giving a better picture of what to expect in live trading.

**Key Insight:** If strategies still show positive expectancy with realistic pricing, they're more likely to work in production. If they only work with simplified pricing, they were probably never viable.
