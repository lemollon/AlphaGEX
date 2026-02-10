# PROPHET ML Advisor - Comprehensive Audit Report

**Date:** 2026-02-10
**File:** `quant/prophet_advisor.py` (~5,600 lines)
**Model:** GradientBoostingClassifier (sklearn) with IsotonicCalibration
**Role:** Central advisory system - ALL bots consult Prophet before trading

---

## EXECUTIVE SUMMARY

Prophet is a massive, well-structured advisory system that serves as the central decision-maker for all trading bots. However, it suffers from **many of the same bugs we fixed in WISDOM** - most critically, no class imbalance handling. Since Prophet is the final trade authority, these bugs have a larger blast radius than WISDOM's.

### Verdict: FIX - Same critical bugs as WISDOM, but higher impact

**Critical Issues: 4** | **High Impact: 5** | **Improvements: 4**

---

## SECTION 1: ARCHITECTURE & SIGNAL CHAIN

### Finding 1.1: WISDOM and Prophet are SEPARATE ML models (IMPORTANT)
**Impact: UNDERSTANDING**

The signal chain is:
```
WISDOM (FortressMLAdvisor) → signals.py → win_probability
                                              ↓
Prophet (ProphetAdvisor) → trader.py → strategy_recommendation + bot-specific advice
```

- **WISDOM** runs in `signals.py` (signal generation) - provides ML win probability
- **Prophet** runs in `trader.py` (trade execution) - provides strategy type (IC vs Directional), bot-specific advice, strike suggestions

They are **not redundant** - they answer different questions:
- WISDOM: "What's the probability this trade wins?"
- Prophet: "Should we trade IC or Directional? What strikes? What risk %?"

### Finding 1.2: Prophet has bot-specific advice methods
**Impact: GOOD DESIGN**

Each bot type has a dedicated method:
- `get_fortress_advice()` - IC bots (FORTRESS, SAMSON, ANCHOR)
- `get_solomon_advice()` - Directional bots (SOLOMON, GIDEON)
- `get_lazarus_advice()` - Directional calls (LAZARUS)
- `get_cornerstone_advice()` - Wheel strategy (CORNERSTONE)
- `get_strategy_recommendation()` - IC vs Directional decision

---

## SECTION 2: CLASS IMBALANCE (CRITICAL)

### Finding 2.1: No scale_pos_weight or class weight handling
**Severity: CRITICAL** | **Same bug as WISDOM**

```python
# Line 4425 - train_from_chronicles()
self.model = GradientBoostingClassifier(
    n_estimators=150,
    max_depth=4,
    learning_rate=0.1,
    min_samples_split=20,
    min_samples_leaf=10,
    subsample=0.8,
    random_state=42
)
```

**Problem:** GradientBoostingClassifier has NO built-in `sample_weight` parameter like XGBoost's `scale_pos_weight`. With an ~89% win rate dataset, the model will predict WIN for almost everything - exactly the same bug we fixed in WISDOM.

**Note:** sklearn's GBClassifier can accept `sample_weight` in `.fit()`, but Prophet never computes or passes it.

**Same issue exists in `train_from_live_outcomes()` (line 5272).**

### Finding 2.2: Hardcoded confidence thresholds
**Severity: CRITICAL** | **Same bug as WISDOM**

```python
# Line 1465-1466
self.high_confidence_threshold = 0.65
self.low_confidence_threshold = 0.45
```

With 89% base rate:
- **0.65 threshold for TRADE_FULL**: Model outputs ~0.85+ for almost everything → almost always TRADE_FULL
- **0.45 threshold for SKIP**: Model almost never outputs below 0.45 → almost never SKIPs

The thresholds need to be adaptive relative to the base rate, exactly as we implemented in WISDOM V3.

---

## SECTION 3: FEATURE ENGINEERING

### Finding 3.1: V2 features defined but NEVER used in training
**Severity: HIGH**

```python
# Line 1382 - V2 features defined with 22 columns including:
FEATURE_COLS_V2 = [
    'vix', 'vix_percentile_30d', 'vix_change_1d', 'day_of_week',
    'price_change_1d', 'expected_move_pct', 'win_rate_30d', 'win_rate_7d',
    'gex_normalized', 'gex_regime_positive', 'gex_distance_to_flip_pct',
    'gex_between_walls',
    'vix_regime_low', 'vix_regime_normal', 'vix_regime_elevated',
    'vix_regime_high', 'vix_regime_extreme',
    'ic_suitability', 'dir_suitability',
    'regime_trend_score', 'regime_vol_percentile',
    'psychology_fear_score', 'psychology_momentum',
]
```

**But training only uses V1 features (11 cols):**
```python
# Line 4416
feature_cols = self.FEATURE_COLS if self._has_gex_features else self.FEATURE_COLS_V1
```

The V2 feature set with VIX regime encoding, IC/directional suitability, trend scores, and psychology features is **computed in `extract_features_from_chronicles()`** but never selected for training. The model only ever trains on `FEATURE_COLS` (11 features) or `FEATURE_COLS_V1` (7 features).

### Finding 3.2: Integer day_of_week (same bug as WISDOM)
**Severity: HIGH**

```python
# Line 1370
'day_of_week',  # Integer 0-4
```

Same problem: model treats Monday(0) as 5x closer to nothing than Friday(4). Should use cyclical sin/cos encoding.

### Finding 3.3: win_rate_30d short-horizon leakage risk
**Severity: MEDIUM**

Same issue as WISDOM - 30-trade lookback creates recency bias. Should be 60d for consistency with WISDOM V3.

### Finding 3.4: price_change_1d training/inference mismatch
**Severity: HIGH**

```python
# Line 4246 (training)
price_change_1d = (close_price - open_price) / open_price * 100
```

In training: uses same-day (open→close) price change (hindsight).
In live inference: `context.price_change_1d` is previous day's change.

This is the same mismatch we fixed in WISDOM V3.

### Finding 3.5: No VRP feature
**Severity: MEDIUM**

Prophet doesn't have a volatility risk premium feature, even though it controls IC vs Directional decisions where VRP is the key driver of profitability.

---

## SECTION 4: TRAINING PIPELINE

### Finding 4.1: Brier score computed on training data (in-sample)
**Severity: HIGH** | **Same bug as WISDOM**

```python
# Line 4454-4460
self.model.fit(X_scaled, y)  # Final fit on ALL data
self.calibrated_model = CalibratedClassifierCV(self.model, method='isotonic', cv=3)
self.calibrated_model.fit(X_scaled, y)
y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
brier = brier_score_loss(y, y_proba_full)  # BRIER ON TRAINING DATA
```

Brier score should be computed on held-out CV folds, not on the same data the model was trained on. In-sample Brier is meaninglessly optimistic.

### Finding 4.2: Calibration on training data leaks
**Severity: HIGH**

```python
# Line 4456-4457
self.calibrated_model = CalibratedClassifierCV(self.model, method='isotonic', cv=3)
self.calibrated_model.fit(X_scaled, y)
```

The calibrated model is fitted on ALL training data after the model has already been fitted on ALL data. The `cv=3` inside CalibratedClassifierCV creates internal folds, but the base model has already seen all the data. This means isotonic calibration is partially calibrating on leaked data.

**Fix:** Calibrate on a held-out validation set, or use the CV fold predictions for calibration.

### Finding 4.3: train_from_live_outcomes() has NO validation split
**Severity: HIGH**

```python
# Line 5301-5302
prophet.model.fit(X_scaled, y)  # Trains on everything
prophet.calibrated_model = CalibratedClassifierCV(prophet.model, method='isotonic', cv=3)
prophet.calibrated_model.fit(X_scaled, y)  # Calibrates on everything
```

While TimeSeriesSplit is used for metrics (line 5270-5299), the final model is still trained on 100% of data. The metrics from CV are reported but the actual deployed model has seen all data including future data (from a time-series perspective).

### Finding 4.4: Model always version 1.0.0 from chronicles
**Severity: LOW**

```python
# Line 4484
self.model_version = "1.0.0"
```

The chronicles training always sets version to 1.0.0 regardless of how many times it's been retrained. Only `train_from_live_outcomes()` increments the minor version.

---

## SECTION 5: PREDICTION PIPELINE

### Finding 5.1: Post-prediction probability manipulation
**Severity: MEDIUM**

In `get_fortress_advice()` (lines 2638-2658):
```python
if context.gex_regime == GEXRegime.POSITIVE:
    base_pred['win_probability'] = min(0.85, base_pred['win_probability'] + 0.03)
elif context.gex_regime == GEXRegime.NEGATIVE:
    base_pred['win_probability'] = max(0.50, base_pred['win_probability'] - 0.02)
elif context.gex_regime == GEXRegime.NEUTRAL:
    if context.gex_between_walls:
        base_pred['win_probability'] = min(0.85, base_pred['win_probability'] + 0.05)
```

The ML model already has GEX features as inputs. Adding +3%/+5% adjustments after the model prediction double-counts GEX influence. If the model is well-calibrated, these adjustments destroy calibration.

### Finding 5.2: Fallback prediction biased toward IC success
**Severity: MEDIUM**

```python
# Line 3964
base_prob = 0.60  # Start with 60% base
```

When model is untrained, the fallback starts at 60% and then gets boosted by VIX sweet spot (+8%), GEX positive (+10%), between walls, etc. This can easily reach 0.75+ which passes the 0.65 TRADE_FULL threshold, meaning the fallback almost always recommends full trading.

---

## SECTION 6: RELATIONSHIP WITH WISDOM

### Finding 6.1: WISDOM is PRIMARY, Prophet is BACKUP in signals
**Impact: CRITICAL UNDERSTANDING**

From `trading/fortress_v2/signals.py`:
```python
# FORTRESS ML Advisor (PRIMARY - trained on CHRONICLES backtests with ~70% win rate)
self.fortress_ml = FortressMLAdvisor()

# Prophet Advisor (BACKUP - used when ML not available)
self.prophet = ProphetAdvisor()
```

This means:
1. WISDOM V3 fixes (scale_pos_weight, adaptive thresholds, VRP) improve signal quality
2. Prophet independently makes strategy and risk decisions in `trader.py`
3. Prophet has its OWN separate ML model with the SAME bugs we fixed in WISDOM

### Finding 6.2: Prophet trains on DIFFERENT data than WISDOM
**Impact: MEDIUM**

- **WISDOM** trains from: `zero_dte_backtest_trades` + `prophet_training_outcomes` + bot positions
- **Prophet** trains from: `zero_dte_backtest_trades` (via `train_from_database_backtests`) + `prophet_training_outcomes` (via `train_from_live_outcomes`) + CHRONICLES in-memory (via `train_from_chronicles`)

Both use overlapping data sources but different extraction logic:
- WISDOM has V3 features (VRP, cyclical day, win_rate_60d)
- Prophet has V1 features (integer day, win_rate_30d, no VRP)

### Finding 6.3: No WISDOM signal fed into Prophet
**Impact: MEDIUM**

WISDOM computes a win_probability that the signal generators use, but Prophet's `_get_base_prediction()` doesn't incorporate WISDOM's output. Prophet makes its own independent prediction. This means:
- Two separate models predict independently
- No ensemble or fusion of their predictions
- Potential for conflicting signals (WISDOM says SKIP, Prophet says TRADE_FULL)

---

## SECTION 7: DATABASE & FEEDBACK LOOP

### Finding 7.1: UNIQUE constraint prevents multiple trades per day per bot
**Severity: MEDIUM**

```sql
CONSTRAINT unique_prediction UNIQUE (trade_date, bot_name)
```

And in training_outcomes:
```sql
UNIQUE(trade_date, bot_name)
```

If a bot makes multiple trades per day (which FORTRESS does every 5 minutes), only the LAST prediction and outcome are stored. Earlier trades are overwritten via `ON CONFLICT DO UPDATE`. This means:
- Training data loses intraday granularity
- If a bot trades 5 times in a day, only 1 outcome is recorded
- The feedback loop is learning from a fraction of actual trades

### Finding 7.2: Training outcomes only have 6 rows
**Impact: LOW (currently)**

From the test output earlier:
```
DB table 'prophet_training_outcomes' exists (6 rows)
```

Prophet needs 20+ outcomes for live training and 100+ for backtest training. With only 6 rows in `prophet_training_outcomes`, it's falling back to `zero_dte_backtest_trades` (7,246 rows) every time.

### Finding 7.3: VALOR doesn't record outcomes to Prophet
**Severity: LOW**

```python
# VALOR trader.py - Future: Call prophet.update_outcome() when BotName.VALOR is added
logger.info(f"VALOR: Recording outcome to Prophet...")
```

VALOR skips actual outcome recording. Missing from BotName enum.

---

## SECTION 8: FINDINGS SUMMARY

### CRITICAL (Fix Immediately)
| # | Finding | Impact |
|---|---------|--------|
| 2.1 | No class imbalance handling (no sample_weight) | Model predicts WIN always, same as WISDOM bug |
| 2.2 | Hardcoded 0.45/0.65 thresholds on ~89% base rate | SKIP/FULL decisions meaningless |
| 3.1 | V2 features defined but never used | 22 features computed but only 11 trained |
| 3.4 | price_change_1d training/inference mismatch | Hindsight leakage in training |

### HIGH IMPACT (Fix Soon)
| # | Finding | Impact |
|---|---------|--------|
| 3.2 | Integer day_of_week (not cyclical) | Artificial ordinal relationship |
| 4.1 | Brier score on training data | Calibration quality unknown |
| 4.2 | Calibration leaks on training data | Over-confident probabilities |
| 4.3 | train_from_live_outcomes no validation | Overfitting risk |
| 7.1 | UNIQUE constraint loses intraday trades | Only 1 trade/day/bot saved |

### IMPROVEMENTS (Nice to Have)
| # | Finding | Impact |
|---|---------|--------|
| 3.3 | win_rate_30d short horizon | Recency bias |
| 3.5 | No VRP feature | Missing key IC profitability driver |
| 5.1 | Post-prediction probability manipulation | Destroys calibration |
| 6.3 | No WISDOM signal fed into Prophet | Two models predict independently |

---

## QUICK WINS (Can Fix Today)

1. **Add sample_weight to GradientBoostingClassifier.fit()** - Compute weights from class distribution
2. **Make thresholds adaptive** - Same approach as WISDOM V3: relative to base rate
3. **Use V2 or V3 feature set for training** - The features are already computed but unused
4. **Fix price_change_1d** - Use previous trade's change in training
5. **Compute Brier on held-out folds** - Already have TimeSeriesSplit infrastructure

---

## RECOMMENDATION

**Approach: Apply WISDOM V3 patterns to Prophet**

Prophet uses GradientBoostingClassifier (sklearn) while WISDOM uses XGBoost. The fixes are analogous:

| WISDOM V3 Fix | Prophet Equivalent |
|---------------|-------------------|
| `scale_pos_weight` | `sample_weight` in `.fit()` |
| Adaptive thresholds | Same logic: base_rate - 0.15 / base_rate - 0.05 |
| Cyclical day encoding | Same sin/cos encoding |
| VRP feature | Add to feature set |
| Brier on CV folds | Accumulate predictions from TimeSeriesSplit |
| win_rate_60d | Change lookback window |
| price_change_1d fix | Use previous trade's change |

**Estimated complexity:** MEDIUM - Prophet is 5,600 lines but the ML training code follows the same structure as WISDOM.

**Risk:** LOW - Prophet's rule-based fallback (lines 3961-4020) provides a safety net if the ML model regresses.

---

*Report generated by Claude AI audit - AlphaGEX ML Bot Orchestration project*
