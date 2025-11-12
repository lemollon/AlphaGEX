# Dynamic Statistics System - Complete Guide

## Overview

AlphaGEX now features a **fully automatic** statistics system that eliminates all hardcoded probabilities and win rates. The system updates itself based on real backtest data and logs all changes.

**No manual work required** - everything happens automatically!

## What Changed

### ❌ Before: Hardcoded Guesses

```python
STRATEGIES = {
    'BULLISH_CALL_SPREAD': {
        'win_rate': 0.65,  # ❌ Made up number!
        'confidence': 85,   # ❌ Arbitrary guess!
    }
}

MM_STATES = {
    'PANICKING': {
        'threshold': -3e9,  # ❌ Fixed threshold
        'confidence': 90     # ❌ Hardcoded confidence
    }
}
```

###✅ After: Fully Dynamic

```python
# Win rates AUTO-UPDATE from backtests
strategy_stats = get_strategy_stats()
# Returns: {'BULLISH_CALL_SPREAD': {'win_rate': 0.67, 'last_updated': '2025-11-12', 'source': 'backtest'}}

# Confidence CALCULATED from actual GEX data
mm_confidence = calculate_mm_confidence(net_gex=-2.5e9, spot_price=580, flip_point=578)
# Returns: {'state': 'PANICKING', 'confidence': 87.3, 'reason': 'calculated from GEX strength'}

# Thresholds ADAPT to market conditions
thresholds = get_gex_thresholds('SPY', avg_gex=5e9)
# Returns adaptive thresholds that scale with average GEX
```

## How It Works

### 1. Strategy Win Rates (Auto-Updated from Backtests)

**File**: `strategy_stats.py`

**Flow**:
```
Backtest runs → Results calculated → Auto-saved to .strategy_stats/strategy_stats.json
                                   ↓
                              Change logged with timestamp
                                   ↓
                         Next API call uses updated win rate
```

**Example**:
```bash
# Run a backtest
python backtest_gex_strategies.py

# Output:
# 📊 AUTO-UPDATE: STRATEGY_STATS > BULLISH_CALL_SPREAD
#    Old: win_rate=65.0% → New: win_rate=67.2%, expectancy=1.23%
#    Reason: Updated from backtest (47 trades, 2024-01-01 to 2024-12-31)
#    Logged: 2025-11-12T14:23:45
```

**Requirements**:
- Minimum 10 trades before auto-update (prevents noise)
- Logs timestamp, old value, new value, reason
- Stores expectancy, Sharpe ratio, avg win/loss

**Storage**: `.strategy_stats/strategy_stats.json`

### 2. MM Confidence (Calculated Dynamically)

**File**: `strategy_stats.py` - `calculate_mm_confidence()`

**Inputs**:
- `net_gex`: Current gamma exposure (e.g., -$2.5B)
- `spot_price`: Current stock price
- `flip_point`: Gamma flip level

**Calculation Logic**:
```python
confidence = 50.0  # Start at neutral

# How far beyond threshold?
if net_gex < thresholds['extreme_negative']:
    excess = abs(net_gex) - abs(threshold)
    boost = (excess / threshold) * 40  # Up to +40%
    confidence += boost

# Distance from flip point
distance_pct = abs((spot_price - flip_point) / flip_point * 100)
if distance_pct > 2.0:
    confidence += min(10, distance_pct / 2)  # Up to +10%

# Cap at 95% (never 100% certain in markets)
confidence = min(95.0, confidence)
```

**Example**:
```
GEX: -$3.2B (extreme negative)
Threshold: -$3.0B
Excess: -$200M (6.7% beyond threshold)
Base boost: +2.7%

Spot: $582, Flip: $578
Distance: 0.69%
Flip boost: +0.35%

Total confidence: 50% + 2.7% + 0.35% = 53.05%
```

**Result**: Confidence reflects actual GEX strength, not arbitrary guess!

### 3. Adaptive GEX Thresholds

**File**: `config.py` - `get_gex_thresholds()`

**Old System**:
```python
if net_gex < -1e9:  # Always -$1B
    state = "HUNTING"
```

**New System**:
```python
thresholds = get_gex_thresholds('SPY', avg_gex=5e9)
# Returns: {'moderate_negative': -1e9}  # 20% of $5B

# If avg changes to $10B:
thresholds = get_gex_thresholds('SPY', avg_gex=10e9)
# Returns: {'moderate_negative': -2e9}  # 20% of $10B (auto-scaled!)
```

**Multipliers** (config.py):
```python
ADAPTIVE_MULTIPLIERS = {
    'extreme_negative': -0.6,   # -60% of average
    'moderate_negative': -0.2,  # -20% of average
    'moderate_positive': 0.2,   # +20% of average
    'extreme_positive': 0.6     # +60% of average
}
```

## File Structure

```
.strategy_stats/
├── strategy_stats.json        # Win rates, expectancy, Sharpe
├── mm_confidence.json         # (future: cached confidence calculations)
└── change_log.jsonl           # All automatic updates with timestamps
```

### Example `strategy_stats.json`:
```json
{
  "BULLISH_CALL_SPREAD": {
    "win_rate": 0.672,
    "avg_win": 3.45,
    "avg_loss": -2.12,
    "expectancy": 1.23,
    "sharpe_ratio": 1.87,
    "total_trades": 47,
    "last_updated": "2025-11-12T14:23:45",
    "source": "backtest",
    "backtest_period": "2024-01-01 to 2024-12-31"
  }
}
```

### Example `change_log.jsonl`:
```jsonl
{"timestamp": "2025-11-12T14:23:45", "category": "STRATEGY_STATS", "item": "BULLISH_CALL_SPREAD", "old_value": "win_rate=65.0%", "new_value": "win_rate=67.2%, expectancy=1.23%", "reason": "Updated from backtest (47 trades, 2024-01-01 to 2024-12-31)"}
{"timestamp": "2025-11-12T15:10:12", "category": "STRATEGY_STATS", "item": "IRON_CONDOR", "old_value": "win_rate=72.0%", "new_value": "win_rate=74.1%, expectancy=0.87%", "reason": "Updated from backtest (63 trades, 2024-01-01 to 2024-12-31)"}
```

## API Integration

### Gamma Intelligence Endpoint

**Before**:
```python
# Hardcoded thresholds
if net_gex < -3e9:
    mm_state = "PANICKING"
    confidence = 90  # Hardcoded!
```

**After**:
```python
from strategy_stats import calculate_mm_confidence, get_mm_states

# Dynamic calculation
mm_result = calculate_mm_confidence(net_gex, spot_price, flip_point)
mm_state_name = mm_result['state']  # "PANICKING"
confidence = mm_result['confidence']  # 87.3 (calculated!)

# Output logs:
# 📊 MM State: PANICKING (confidence: 87.3%, calculated dynamically)
```

### Strategy Selection

**Before**:
```python
strategies = STRATEGIES  # Static hardcoded win rates
```

**After**:
```python
from config_and_database import get_dynamic_strategies

strategies = get_dynamic_strategies()
# Merges live backtest data with static configuration
# Win rates update automatically when backtests run
```

## Viewing Recent Changes

```python
from strategy_stats import print_change_summary

print_change_summary()
```

**Output**:
```
======================================================================
📊 RECENT AUTOMATIC UPDATES
======================================================================

[2025-11-12T15:10:12]
  STRATEGY_STATS > IRON_CONDOR
  win_rate=72.0% → win_rate=74.1%, expectancy=0.87%
  Reason: Updated from backtest (63 trades, 2024-01-01 to 2024-12-31)

[2025-11-12T14:23:45]
  STRATEGY_STATS > BULLISH_CALL_SPREAD
  win_rate=65.0% → win_rate=67.2%, expectancy=1.23%
  Reason: Updated from backtest (47 trades, 2024-01-01 to 2024-12-31)

======================================================================
```

## How to Use

### For Backtests

**Just run backtests normally** - auto-update happens automatically:

```bash
python backtest_gex_strategies.py
```

The system will:
1. ✅ Calculate win rate from trades
2. ✅ Save to `.strategy_stats/strategy_stats.json`
3. ✅ Log change to `.strategy_stats/change_log.jsonl`
4. ✅ Print notification to console
5. ✅ Next API call uses updated value

**No manual steps required!**

### For API Calls

**No changes needed** - just call endpoints normally:

```bash
curl http://localhost:8000/api/gamma/SPY/intelligence
```

Response will include:
```json
{
  "mm_state": {
    "name": "PANICKING",
    "confidence": 87.3,  // ← Calculated dynamically!
    "behavior": "Capitulation - covering at any price",
    "threshold": -3000000000
  }
}
```

### For Strategy Configuration

**Option 1: Use dynamic wrapper** (recommended):
```python
from config_and_database import get_dynamic_strategies

strategies = get_dynamic_strategies()
# Returns strategies with live win rates
```

**Option 2: Direct access** (fallback):
```python
from strategy_stats import get_strategy_stats

stats = get_strategy_stats()
win_rate = stats['BULLISH_CALL_SPREAD']['win_rate']
```

## Benefits

### 1. No More Guessing
- Win rates come from real backtest data
- Confidence calculated from actual GEX levels
- Thresholds adapt to market size

### 2. Automatic Updates
- Run backtest → Stats update automatically
- No manual editing of config files
- No risk of stale data

### 3. Full Transparency
- Every change is logged with timestamp
- See exactly when and why values changed
- Audit trail for all updates

### 4. Safety Built-In
- Requires minimum 10 trades before update
- Confidence capped at 95% (never overconfident)
- Fallback to defaults if data unavailable

## Troubleshooting

**Q: Win rates not updating after backtest?**
```bash
# Check if backtest had enough trades
# Minimum 10 trades required

# Check the stats file
cat .strategy_stats/strategy_stats.json | python -m json.tool

# Check the change log
tail .strategy_stats/change_log.jsonl
```

**Q: Where are stats stored?**
```bash
ls -la .strategy_stats/
# Should show:
#   strategy_stats.json
#   change_log.jsonl
```

**Q: How to reset to defaults?**
```bash
rm -rf .strategy_stats/
# Next backtest will recreate with fresh data
```

**Q: Stats file corrupted?**
```bash
# Delete and let it rebuild
rm .strategy_stats/strategy_stats.json

# Run backtest
python backtest_gex_strategies.py
```

## Configuration

### Minimum Trades Threshold

**File**: `strategy_stats.py`
```python
if total_trades < 10:  # ← Change this to require more/fewer trades
    print("Insufficient data")
    return
```

### Confidence Calculation

**File**: `strategy_stats.py` - `calculate_mm_confidence()`

Adjust boost factors:
```python
# Distance beyond threshold (currently up to +40%)
confidence_boost = min(40, (excess / threshold) * 40)

# Distance from flip point (currently up to +10%)
flip_boost = min(10, distance_pct / 2)

# Max confidence (currently capped at 95%)
confidence = min(95.0, confidence)
```

### Adaptive Multipliers

**File**: `config.py`
```python
ADAPTIVE_MULTIPLIERS = {
    'extreme_negative': -0.6,  # Adjust these percentages
    'moderate_negative': -0.2,
    ...
}
```

## Examples

### Example 1: First Backtest Run

```bash
$ python backtest_gex_strategies.py

# Output:
Running backtest for BULLISH_CALL_SPREAD...
Completed: 47 trades, 67.2% win rate

📊 AUTO-UPDATE: STRATEGY_STATS > BULLISH_CALL_SPREAD
   Old: win_rate=65.0% → New: win_rate=67.2%, expectancy=1.23%
   Reason: Updated from backtest (47 trades, 2024-01-01 to 2024-12-31)
   Logged: 2025-11-12T14:23:45
```

### Example 2: API Call Shows Dynamic Confidence

```bash
$ curl http://localhost:8000/api/gamma/SPY/intelligence | jq .data.mm_state

{
  "name": "TRAPPED",
  "confidence": 81.7,  # ← Calculated from GEX=-$2.1B, distance from flip
  "behavior": "Forced buying on rallies, selling on dips",
  "action": "HUNT: Buy calls on any approach to flip point"
}
```

### Example 3: Strategy Selection Uses Live Data

```python
from config_and_database import get_dynamic_strategies

strategies = get_dynamic_strategies()

print(strategies['BULLISH_CALL_SPREAD'])
# Output:
# {
#   'win_rate': 0.672,  # ← From latest backtest!
#   'expectancy': 1.23,
#   'last_updated': '2025-11-12T14:23:45',
#   'source': 'backtest',
#   'conditions': {...},
#   'entry': 'Near support or flip point',
#   ...
# }
```

---

## Summary

✅ **Fully Automatic** - No manual updates required
✅ **Real Data** - Win rates from actual backtests
✅ **Adaptive** - Thresholds scale with market conditions
✅ **Transparent** - All changes logged with timestamps
✅ **Safe** - Requires minimum data, caps confidence
✅ **Auditable** - Complete change history

**Just run backtests and let the system update itself!**

---

Last Updated: 2025-11-12
Version: 1.0.0
