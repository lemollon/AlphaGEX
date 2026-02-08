# SOLOMON & ICARUS Directional Bot Analysis

## Executive Summary

Both directional bots are losing money due to several structural issues that need to be fixed.

---

## Critical Issues Identified

### 1. ASYMMETRIC RISK/REWARD (MAJOR ISSUE)

**Current Settings:**
| Bot | Profit Target | Stop Loss | Effective R:R |
|-----|--------------|-----------|---------------|
| SOLOMON | 50% of max profit | 50% of max loss | 1:1 |
| ICARUS | 40% of max profit | 60% of max loss | 0.67:1 |

**Why This Is A Problem:**
- At 50% win rate with SOLOMON's 1:1 R:R: `0.50 * $100 - 0.50 * $100 = $0` (breakeven)
- At 50% win rate with ICARUS's 0.67:1 R:R: `0.50 * $80 - 0.50 * $120 = -$20` (NET LOSS!)

**ICARUS is mathematically designed to lose money at 50% win rate!**

### 2. MAGNET THEORY INVERSION (Trading Backwards!)

The optimizer script (`scripts/optimize_solomon_strategy.py`) documents:
```
MAGNET THEORY (KEY INSIGHT):
- High put GEX = price pulled DOWN toward puts = BEARISH
- High call GEX = price pulled UP toward calls = BULLISH
```

**Current Implementation (WRONG):**
- Near put wall = BULLISH (expecting bounce from support)
- Near call wall = BEARISH (expecting rejection from resistance)

**This is the OPPOSITE of MAGNET theory!** The bots are trading against the gamma-induced price movement.

### 3. ATM STRIKE SELECTION (High Theta Decay)

Both bots use ATM strikes for the long leg:
```python
# Current SOLOMON code
long_strike = round(spot_price)      # ATM
short_strike = round(spot_price) + 2 # $2 OTM
```

**Problems:**
- ATM 0DTE options have maximum theta decay
- Most of the option value is lost by afternoon
- Late entries (after 12 PM) have minimal edge

### 4. ENTRY TIMING TOO WIDE

**Current Window:** 8:35 AM - 2:30 PM CT (6 hours)

**Problem:** Late-day entries have:
- Minimal time premium remaining
- Gamma exposure without theta compensation
- Higher probability of max loss

### 5. ORACLE OVERRIDE IS TOO AGGRESSIVE

When Oracle says TRADE, ALL filters are bypassed:
```python
oracle_says_trade = oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')
if oracle_says_trade:
    # VIX check bypassed
    # Wall proximity bypassed
    # GEX ratio bypassed
```

**Problem:** If Oracle model is stale or miscalibrated, bad trades get through.

### 6. BACKTEST PARAMETERS DON'T MATCH LIVE

| Parameter | Backtest Optimal | SOLOMON Live | ICARUS Live |
|-----------|-----------------|-------------|-------------|
| VIX Range | 15-25 | 12-35 | 12-30 |
| Wall Proximity | 3% | 1% | 1% |
| Hold Days | 1 (0DTE) | 0DTE | 0DTE |

---

## Performance Math

For a directional spread bot to be profitable, this equation must be positive:

```
Expected Value = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
```

**SOLOMON Example (1:1 R:R):**
- Need >50% win rate to profit
- At 45% WR: `0.45 * $100 - 0.55 * $100 = -$10` per trade

**ICARUS Example (0.67:1 R:R):**
- Need >60% win rate to profit!
- At 50% WR: `0.50 * $67 - 0.50 * $100 = -$16.50` per trade
- At 55% WR: `0.55 * $67 - 0.45 * $100 = -$8.15` per trade (STILL LOSING!)
- At 60% WR: `0.60 * $67 - 0.40 * $100 = $0.20` per trade (barely breakeven)

---

## Recommended Fixes

### Fix 1: Invert Risk/Reward (CRITICAL)

**ICARUS:** Change from 40/60 to 60/50 (or 70/50)
```python
# OLD (LOSING)
profit_target_pct: float = 40.0  # Take profit at 40%
stop_loss_pct: float = 60.0       # Stop at 60%

# NEW (WINNING)
profit_target_pct: float = 70.0   # Take profit at 70%
stop_loss_pct: float = 50.0       # Stop at 50%
```

**SOLOMON:** Consider 60/40 for positive expectancy
```python
profit_target_pct: float = 60.0   # Take profit at 60%
stop_loss_pct: float = 40.0       # Stop at 40%
```

### Fix 2: Implement MAGNET Theory Correctly

```python
# CURRENT (WRONG - trading against gamma flow)
if dist_to_put_wall < filter:
    direction = "BULLISH"  # Expecting bounce UP

# CORRECT (trading WITH gamma flow)
if dist_to_put_wall < filter:
    direction = "BEARISH"  # Price pulled DOWN toward puts
```

### Fix 3: Add VIX Filter (Match Backtest)

```python
# Only trade in optimal VIX range
min_vix: float = 15.0  # Skip low vol (no premium)
max_vix: float = 25.0  # Skip extreme vol (too risky)
```

### Fix 4: Limit Entry Window

```python
# Stop trading earlier to preserve edge
entry_end: str = "12:00"  # Was 14:30 - stop at noon
```

### Fix 5: Add Oracle Confidence Floor

```python
# Even when Oracle says TRADE, require minimum confidence
if oracle_says_trade and oracle_confidence >= 0.60:
    # Proceed with trade
else:
    # Skip even if Oracle said trade
```

### Fix 6: Add Daily Loss Circuit Breaker

```python
# Stop trading after 2 consecutive losses
max_consecutive_losses: int = 2
# Stop trading after daily loss exceeds threshold
max_daily_loss_pct: float = 5.0
```

---

## Implementation Priority

1. **CRITICAL:** Fix ICARUS profit/stop ratio (biggest impact)
2. **HIGH:** Add VIX filter 15-25 (match backtest optimal)
3. **HIGH:** Limit entry window to morning
4. **MEDIUM:** Implement MAGNET theory direction
5. **MEDIUM:** Add Oracle confidence floor
6. **LOW:** Add daily loss circuit breaker

---

## Success Metrics

After fixes, expect:
- **Win Rate:** 50-55% (improved direction)
- **Profit Factor:** >1.2 (positive expectancy)
- **Max Drawdown:** <15% (better risk management)
- **Sharpe Ratio:** >1.0 (good risk-adjusted returns)

---

## Testing Plan

1. Backtest with new parameters on 2024-2025 data
2. Paper trade for 2 weeks
3. Review metrics and adjust
4. Go live with reduced size
5. Scale up as confidence builds

---

*Analysis Date: 2026-02-01*
*Analyst: Claude Code*
