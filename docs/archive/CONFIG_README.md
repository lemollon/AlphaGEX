# AlphaGEX Configuration Guide

## Overview

The `config.py` file centralizes all tunable parameters, thresholds, and constants for the AlphaGEX trading system. This allows you to adjust system behavior without modifying core application code.

## Configuration Sections

### 1. VIX Configuration (`VIXConfig`)

Controls VIX (volatility index) handling and fallback behavior.

**Key Parameters:**
- `HISTORICAL_AVERAGE_VIX = 16.5`: Long-term VIX average (used as fallback)
- `RECENT_AVERAGE_VIX = 18.0`: Recent 5-year average (preferred fallback)
- `LOW_VIX_THRESHOLD = 15.0`: Below this = low volatility environment
- `ELEVATED_VIX_THRESHOLD = 20.0`: Above this = elevated volatility
- `HIGH_VIX_THRESHOLD = 30.0`: Above this = high volatility
- `EXTREME_VIX_THRESHOLD = 40.0`: Above this = extreme volatility/crisis

**Use Case:**
Adjust VIX thresholds if you want to be more/less sensitive to volatility regime changes.

### 2. Gamma Decay Configuration (`GammaDecayConfig`)

Controls weekly gamma expiration patterns for 0DTE trading.

**Available Patterns:**
- `FRONT_LOADED_PATTERN`: Heavy decay early in week (typical for 0DTE)
- `BALANCED_PATTERN`: More gradual decay
- `BACK_LOADED_PATTERN`: Gamma concentrated late in week

**Key Parameters:**
- `USE_ADAPTIVE_PATTERN = True`: System auto-selects pattern based on market conditions
  - High VIX or negative GEX → Front-loaded pattern
  - Low VIX → Back-loaded pattern
  - Normal conditions → Balanced pattern

**Tuning:**
To manually select a pattern, set `USE_ADAPTIVE_PATTERN = False` and change `ACTIVE_PATTERN`:
```python
USE_ADAPTIVE_PATTERN = False
ACTIVE_PATTERN = BALANCED_PATTERN  # Force balanced pattern
```

### 3. GEX Threshold Configuration (`GEXThresholdConfig`)

Controls gamma exposure (GEX) thresholds for regime classification.

**Adaptive Mode (Recommended):**
```python
USE_ADAPTIVE_THRESHOLDS = True
ADAPTIVE_MULTIPLIERS = {
    'extreme_negative': -0.6,  # -60% of average = extreme short gamma
    'high_negative': -0.4,     # -40% of average
    'moderate_negative': -0.2, # -20% of average
    'moderate_positive': 0.2,  # +20% of average
    'high_positive': 0.4,      # +40% of average
    'extreme_positive': 0.6    # +60% of average
}
```

**How It Works:**
- System calculates rolling 20-day average GEX
- Thresholds scale as multiples of this average
- Example: If avg GEX = $5B, "moderate_negative" = -$1B (20% of $5B)

**Fixed Mode (Fallback):**
```python
USE_ADAPTIVE_THRESHOLDS = False
FIXED_THRESHOLDS = {
    'extreme_negative': -3e9,  # Fixed at -$3B
    'moderate_negative': -1e9, # Fixed at -$1B
    ...
}
```

**Tuning:**
- Increase multipliers to require stronger signals (less sensitive)
- Decrease multipliers for more frequent regime changes (more sensitive)

### 4. Directional Prediction Configuration (`DirectionalPredictionConfig`)

Controls the SPY directional forecast algorithm.

**Scoring Weights:**
```python
FACTOR_WEIGHTS = {
    'gex_regime': 0.40,      # 40% - GEX regime influence
    'wall_proximity': 0.30,  # 30% - Distance to gamma walls
    'vix_regime': 0.20,      # 20% - VIX level
    'day_of_week': 0.10      # 10% - Day of week effect
}
```

**Direction Thresholds:**
```python
NEUTRAL_SCORE = 50           # Starting score (neutral)
UPWARD_THRESHOLD = 65        # Score >= 65 → UPWARD prediction
DOWNWARD_THRESHOLD = 35      # Score <= 35 → DOWNWARD prediction
# Between 35-65 → SIDEWAYS prediction
```

**Influence Parameters:**
```python
GEX_REGIME_STRONG_INFLUENCE = 20  # Points for short gamma
GEX_REGIME_MILD_INFLUENCE = 5     # Points for long gamma
WALL_INFLUENCE = 15               # Points for wall proximity
WALL_PROXIMITY_THRESHOLD = 1.5    # 1.5% from wall = strong influence

VIX_HIGH_DAMPENING = 0.7   # High VIX pulls score toward neutral
VIX_LOW_DAMPENING = 0.8    # Low VIX pulls score toward neutral
```

**Tuning Examples:**

**Make predictions more conservative:**
```python
UPWARD_THRESHOLD = 70  # Require higher score for UPWARD
DOWNWARD_THRESHOLD = 30  # Require lower score for DOWNWARD
# Result: More SIDEWAYS predictions, fewer directional calls
```

**Increase GEX regime influence:**
```python
FACTOR_WEIGHTS = {
    'gex_regime': 0.50,      # Increase to 50%
    'wall_proximity': 0.25,  # Reduce to 25%
    'vix_regime': 0.15,
    'day_of_week': 0.10
}
```

### 5. Risk Level Configuration (`RiskLevelConfig`)

Controls daily risk levels for 0DTE trading.

```python
DAILY_RISK_LEVELS = {
    'monday': 29,     # Low risk (max gamma)
    'tuesday': 41,    # Moderate
    'wednesday': 70,  # High (major decay)
    'thursday': 38,   # Moderate
    'friday': 100     # Extreme (expiration)
}
```

**Tuning:**
Adjust risk levels based on observed volatility patterns.

### 6. Trade Setup Configuration (`TradeSetupConfig`)

Controls trade setup generation parameters.

**Spread Widths:**
```python
SPREAD_WIDTH_NORMAL = 0.015       # 1.5% for most stocks
SPREAD_WIDTH_LOW_PRICE = 0.02     # 2% for stocks under $50
```

**Confidence Thresholds:**
```python
MIN_CONFIDENCE_THRESHOLD = 0.65   # 65% minimum
MIN_WIN_RATE_THRESHOLD = 0.50     # 50% minimum win rate
```

**Tuning:**
- Increase confidence threshold for fewer, higher-quality setups
- Decrease for more trading opportunities

### 7. Rate Limiting Configuration (`RateLimitConfig`)

Controls API rate limiting.

```python
MIN_REQUEST_INTERVAL = 4.0  # 4 seconds between requests
CIRCUIT_BREAKER_DURATION = 60  # Wait 60s when rate limited
MAX_CONSECUTIVE_ERRORS = 3     # Errors before circuit breaker
CACHE_DURATION = 1800  # 30 minutes cache
```

**Tuning:**
- **Faster responses**: Reduce `MIN_REQUEST_INTERVAL` to 3.0 (risky)
- **Safer**: Increase to 5.0 (slower but more stable)

### 8. Implied Volatility Configuration (`ImpliedVolatilityConfig`)

Controls IV defaults and thresholds.

```python
DEFAULT_IV = 0.20  # 20% when not available from API
```

## Helper Functions

### `get_gex_thresholds(symbol, avg_gex)`
Returns adaptive or fixed GEX thresholds.
```python
from config import get_gex_thresholds

# Get adaptive thresholds (recommended)
thresholds = get_gex_thresholds('SPY', avg_gex=5e9)
# Returns: {'extreme_negative': -3e9, 'moderate_positive': 1e9, ...}

# Get fixed thresholds (fallback)
thresholds = get_gex_thresholds('SPY', avg_gex=None)
```

### `get_gamma_decay_pattern(vix, net_gex)`
Returns adaptive gamma decay pattern.
```python
from config import get_gamma_decay_pattern

# Auto-select pattern based on conditions
pattern = get_gamma_decay_pattern(vix=25.0, net_gex=-2e9)
# Returns: {0: 1.00, 1: 0.71, ...} (FRONT_LOADED in this case)
```

### `get_vix_fallback(last_known_vix)`
Returns intelligent VIX fallback value.
```python
from config import get_vix_fallback

# Use recent historical average (preferred)
vix = get_vix_fallback(last_known_vix=18.5)
# Returns: 18.5 (last known value)

vix = get_vix_fallback(last_known_vix=None)
# Returns: 18.0 (RECENT_AVERAGE_VIX)
```

## Common Tuning Scenarios

### Scenario 1: More Aggressive Directional Predictions
```python
# In DirectionalPredictionConfig:
UPWARD_THRESHOLD = 60  # Lower from 65
DOWNWARD_THRESHOLD = 40  # Raise from 35
GEX_REGIME_STRONG_INFLUENCE = 25  # Increase from 20
```

### Scenario 2: More Conservative Regime Changes
```python
# In GEXThresholdConfig:
ADAPTIVE_MULTIPLIERS = {
    'extreme_negative': -0.8,  # Increase from -0.6
    'moderate_negative': -0.3, # Increase from -0.2
    ...
}
```

### Scenario 3: Faster API Responses (Risky)
```python
# In RateLimitConfig:
MIN_REQUEST_INTERVAL = 3.0  # Reduce from 4.0
# WARNING: May trigger rate limits more often
```

### Scenario 4: High-VIX Environment Adaptation
```python
# In VIXConfig:
ELEVATED_VIX_THRESHOLD = 25.0  # Increase from 20.0
HIGH_VIX_THRESHOLD = 35.0      # Increase from 30.0
# Result: Treats current environment as "normal" instead of "elevated"
```

## Validation

The configuration validates itself on import:
```python
# Automatic validation checks:
✅ Directional prediction weights sum to 100%
✅ Thresholds are in logical order
✅ VIX thresholds are ascending
```

If validation fails, you'll see a warning message.

## Best Practices

1. **Test changes incrementally**: Change one parameter at a time
2. **Monitor results**: Track prediction accuracy after tuning
3. **Document changes**: Add comments explaining why you changed values
4. **Backup original**: Keep a copy of `config.py` before major changes
5. **Use adaptive modes**: Enable `USE_ADAPTIVE_THRESHOLDS` and `USE_ADAPTIVE_PATTERN` for better performance

## Troubleshooting

**Problem**: Predictions are always SIDEWAYS
**Solution**: Lower `UPWARD_THRESHOLD` and raise `DOWNWARD_THRESHOLD`

**Problem**: Too many regime changes
**Solution**: Increase `ADAPTIVE_MULTIPLIERS` values or use fixed thresholds

**Problem**: Rate limit errors
**Solution**: Increase `MIN_REQUEST_INTERVAL` or `CACHE_DURATION`

**Problem**: VIX fallback seems wrong
**Solution**: Adjust `RECENT_AVERAGE_VIX` based on current market conditions

## Feature Flags

Control which adaptive features are enabled:
```python
# In SystemConfig:
ENABLE_ADAPTIVE_GEX_THRESHOLDS = True
ENABLE_ADAPTIVE_GAMMA_PATTERN = True
ENABLE_HISTORICAL_VIX_FALLBACK = True
```

Set to `False` to disable adaptive behavior and use fixed values.

---

**Last Updated**: 2025-11-12
**Version**: 1.0.0
