# ORION (GEX Probability Models) - Comprehensive ML Bot Audit Report

**Date**: 2026-02-10
**Branch**: `claude/watchtower-data-analysis-6FWPk`
**Auditor**: Claude Code (Orchestration Layer Evaluation)
**Status**: AUDIT COMPLETE - Multiple Critical Issues Found

---

## Executive Summary

ORION is a 5-model XGBoost ensemble that predicts gamma-based market structure outcomes (direction, flip gravity, magnet attraction, volatility, pin zone behavior). It provides probability predictions consumed by GIDEON, SOLOMON_V2, and the WATCHTOWER/GLORY dashboard via a 60/40 hybrid probability system.

**Architecture is well-designed** with hypothesis-driven features, TimeSeriesSplit validation, and database persistence. However, the system suffers from the **same class imbalance blindness** found in WISDOM and Prophet, plus a **win probability manipulation bug** and a **direction probabilities function that always returns uniform values**.

### Severity Summary
| Severity | Count | Key Issues |
|----------|-------|-----------|
| CRITICAL | 3 | No class imbalance handling, win_prob +10% boost, _get_direction_probs always uniform |
| HIGH | 4 | No Brier score, no calibration, FlipGravity on unconfirmed hypothesis, integer day_of_week |
| MEDIUM | 4 | Accuracy-only metrics, no feature importance stored, hardcoded conviction factors, fallback data quality |
| LOW | 3 | No VRP feature, fixed 60/40 hybrid weight, no FOMC/CPI awareness |

---

## Section 1: Data Pipeline

### 1.1 Data Sources

| Source | Table | Usage | Quality |
|--------|-------|-------|---------|
| Primary | `gex_structure_daily` JOIN `vix_daily` | Training data | Good - pre-computed daily structure |
| Fallback | `gex_history` | When primary empty | Poor - crude approximations |
| Auto-populate | `options_chain_snapshots` → `gex_structure_daily` | 30-day lookback refresh before training | Good - automated |

**Primary query** (`gex_probability_models.py:308-349`): Loads 25+ columns including spot OHLC, gamma metrics, magnet strikes, wall levels, distance metrics, and VIX from `gex_structure_daily` joined with `vix_daily`.

**Training window**: 2020-01-01 to present. Very long lookback — may include regime changes that hurt model performance.

### 1.2 Fallback Data Quality Issues

The `gex_history` fallback (`gex_probability_models.py:120-289`) makes **crude approximations**:

| Approximation | Code | Problem |
|---------------|------|---------|
| `total_call_gamma = net_gamma * 0.6` | Line 225 | Arbitrary 60/40 split, not real call/put decomposition |
| `total_put_gamma = net_gamma * 0.4` | Line 226 | Same issue |
| `nearest_magnet_strike = call_wall` | Line 243 | Always uses call wall, ignores put wall proximity |
| `gamma_imbalance_pct = sign(net_gamma) * 100` | Lines 238-240 | Binary ±100, not actual imbalance |
| `num_magnets_above = 1` (always) | Line 241 | Hardcoded, not actual count |
| `open_in_pin_zone = FALSE` (always) | Line 250 | Never detects pin zone |

**Impact**: If `gex_structure_daily` is empty and fallback is used, ORION trains on fabricated feature distributions. Models trained on this data will learn artifacts.

### 1.3 Look-Ahead Bias Assessment

**No look-ahead bias found in data loading.** The SQL queries properly order by `trade_date` and the feature engineering uses `.shift(1)` for previous-day features. The `price_change_pct` target uses same-day open-to-close, which is appropriate since these are end-of-day classifications.

### 1.4 Data Freshness

- Training data auto-populated from `options_chain_snapshots` (30-day lookback) before each training run
- Scheduler refreshes `gex_structure_daily` via `populate_recent_gex_structures(days=30)`
- Model staleness tracked via `get_model_staleness_hours()` with 168-hour (7-day) threshold

---

## Section 2: Feature Engineering

### 2.1 Feature Inventory

**engineer_features()** (`gex_probability_models.py:377-477`) creates 30+ features from raw data:

| Category | Features | Count |
|----------|----------|-------|
| Gamma Regime | `gamma_regime_positive`, `gamma_regime_negative` | 2 |
| Gamma Magnitude | `net_gamma_normalized` (per-symbol z-score) | 1 |
| Gamma Imbalance | `gamma_ratio_log`, `gamma_imbalance_pct`, `top_magnet_concentration` | 3 |
| Distance | `flip_distance_normalized`, `near_flip`, `magnet_distance_normalized`, `near_magnet`, `wall_spread_pct` | 5 |
| VIX | `vix_level`, `vix_regime_low`, `vix_regime_mid`, `vix_regime_high`, `vix_percentile` | 5 |
| Momentum | `prev_price_change_pct`, `prev_price_range_pct`, `gamma_regime_changed`, `gamma_change_1d`, `gamma_change_3d` | 5 |
| Calendar | `day_of_week`, `is_monday`, `is_friday`, `is_opex_week`, `is_month_end` | 5 |
| Pin Zone | `open_in_pin_zone`, `pin_zone_width_pct` | 2 |

**Per-model feature selection** (each model uses a subset):

| Model | Feature Count | Key Features |
|-------|--------------|-------------|
| DirectionModel | 21 | Full gamma + VIX + momentum + calendar |
| FlipGravityModel | 10 | Gamma + flip distance + VIX |
| MagnetAttractionModel | 10 | Pin zone + magnet distance + gamma |
| VolatilityModel | 13 | Gamma + VIX + previous range + calendar |
| PinZoneModel | 10 | Pin zone + gamma + VIX + momentum |

### 2.2 Feature Quality Assessment

**Good practices:**
- Per-symbol normalization of `net_gamma` (z-score within symbol)
- Rolling VIX percentile (30-day window, min_periods=5)
- Proper `.shift(1)` for previous-day momentum features
- Hypothesis-driven feature selection (H1-H5)
- `gamma_ratio_log` clipped to [0.1, 10.0] then log-transformed

**Issues found:**

| Issue | Severity | Detail |
|-------|----------|--------|
| Integer `day_of_week` | HIGH | Used as ordinal (0-4) not cyclical. Friday→Monday jump creates discontinuity. Should use sin/cos encoding. |
| No VRP feature | LOW | Volatility Risk Premium (expected_move vs realized) would capture IV/RV spread — added to WISDOM V3 and Prophet V2 but missing here. |
| `fillna(0)` blanket fill | MEDIUM | Line 475: All NaN features filled with 0. Some features (like `vix_percentile`) should use 0.5 (median), not 0. |
| No FOMC/CPI/NFP awareness | LOW | Calendar features lack macro event flags despite CLAUDE.md mentioning them. |
| `vix_percentile` uses simple rolling min/max | LOW | Not true percentile rank, just normalized within window. Sensitive to outliers. |

### 2.3 Feature Consistency Between Training and Inference

**Major concern**: The `GEXSignalIntegration.extract_features()` (`gex_signal_integration.py:133-256`) and `GEXProbabilityModels._build_features()` (`gex_probability_models.py:1602-1664`) build features differently from `engineer_features()`:

| Feature | Training (engineer_features) | Inference (_build_features) |
|---------|------------------------------|---------------------------|
| `net_gamma_normalized` | Per-symbol z-score over history | `net_gamma / total_gamma` |
| `top_magnet_concentration` | Calculated from magnet gammas | Hardcoded `0.5` |
| `vix_percentile` | Rolling 30-day percentile | Hardcoded `0.5` or not computed |
| `gamma_change_1d` | Differenced normalized gamma | `0` (no previous context) |

**Impact**: Models learn patterns from properly normalized training features but receive differently-scaled features at inference time. This distribution mismatch degrades prediction quality.

---

## Section 3: Model Architecture

### 3.1 Sub-Model Specifications

| Model | Type | Target | Features | Depth | Estimators | min_child_weight |
|-------|------|--------|----------|-------|------------|-----------------|
| DirectionModel | XGBClassifier | UP/DOWN/FLAT | 21 | 4 | 150 (final) | 10 |
| FlipGravityModel | XGBClassifier | 0/1 (toward flip) | 10 | 3 | 100 | 20 |
| MagnetAttractionModel | XGBClassifier | 0/1 (touched magnet) | 10 | 3 | 100 | 15 |
| VolatilityModel | XGBRegressor | price_range_pct | 13 | 4 | 150 (final) | 10 |
| PinZoneModel | XGBClassifier | 0/1 (closed in zone) | 10 | 3 | 100 | 15 |

All use sklearn `GradientBoostingClassifier`/`GradientBoostingRegressor` as fallback if XGBoost unavailable.

### 3.2 Validation Strategy

**TimeSeriesSplit(n_splits=5)** — Correct walk-forward validation preventing future data leakage. Each fold trains on past, tests on future.

**Scaler handling**: In CV folds, `self.scaler.fit_transform(X_train)` then `self.scaler.transform(X_test)` — correct per-fold scaling. Final model refits scaler on all data — acceptable since deployed model sees all historical data.

### 3.3 CRITICAL: No Class Imbalance Handling

**None of the 5 models use any class imbalance handling:**

| Model | Expected Base Rate | Imbalance Impact |
|-------|-------------------|-----------------|
| DirectionModel | FLAT likely 40-50%, UP/DOWN 25-30% each | 3-way imbalance, model biases toward majority class |
| FlipGravityModel | ~44.4% (documented as H4 NOT confirmed) | Near-balanced, less critical |
| MagnetAttractionModel | Likely high (H5: 89% interact with magnets) | **Severe imbalance** - model can predict all 1's |
| PinZoneModel | ~55.2% (documented) | Near-balanced, less critical |
| VolatilityModel | N/A (regression) | N/A |

**Missing from all `.fit()` calls:**
- No `sample_weight` parameter
- No `scale_pos_weight` parameter (XGBoost)
- No SMOTE or other resampling

**Impact**: MagnetAttractionModel with ~89% positive base rate will likely predict "ATTRACT" almost always and appear to have high accuracy while providing no predictive value.

### 3.4 No Calibration Assessment

- No Brier score computed on any model
- No calibration curve analysis
- `accuracy_score` is the only metric reported — misleading for imbalanced classes
- No confusion matrix analysis stored (computed but only printed, not saved)

### 3.5 Hyperparameter Concerns

- All hyperparameters hardcoded, no tuning
- `learning_rate=0.1` for all models — potentially too aggressive
- `n_estimators` differs between CV (100) and final model (150 for Direction, Volatility) — more trees on final could overfit
- No early stopping used

---

## Section 4: Signal Generation & Trade Logic

### 4.1 Combined Signal (GEXSignalGenerator.predict)

**Location**: `gex_probability_models.py:1178-1284`

The prediction flow:
1. Get predictions from all 5 models independently
2. Calculate conviction score from hardcoded factor mapping
3. Apply trade recommendation logic based on direction probabilities

**Conviction calculation** (lines 1198-1237):
```
conviction = mean([
    direction_confidence,                    # Direct model confidence
    0.5 if pin_zone > 0.7 else 0.8,        # Pin zone penalty
    0.9 if magnet > 0.7 else 0.6,          # Magnet boost
    0.5|0.7|0.9 based on flip_gravity,     # Flip gravity score
    0.5|0.7|0.8 based on volatility        # Volatility adjustment
])
```

**Issues**: Conviction factors are arbitrary fixed values (0.5, 0.6, 0.7, 0.8, 0.9) mapped to arbitrary thresholds. These should be learned or at least calibrated against historical performance.

### 4.2 CRITICAL: Win Probability +10% Boost

**Location**: `gex_signal_integration.py:478-483`

```python
win_probability = signal.overall_conviction
if signal.direction_confidence > 0.6:
    win_probability = min(0.85, win_probability + 0.10)
```

**This is the same pattern removed from Prophet V2.** A flat +10% boost when direction confidence exceeds 60% inflates win probability by 10 percentage points (capped at 85%). This destroys calibration.

**Downstream impact**: GIDEON and SOLOMON_V2 receive inflated `win_probability` values in their signal, potentially taking trades that should be skipped.

### 4.3 CRITICAL: _get_direction_probs Always Returns Uniform

**Location**: `gex_signal_integration.py:351-362`

```python
def _get_direction_probs(self, signal) -> Dict[str, float]:
    try:
        from quant.gex_probability_models import Direction
        return {'UP': 0.33, 'DOWN': 0.33, 'FLAT': 0.34}
    except:
        return {'UP': 0.33, 'DOWN': 0.33, 'FLAT': 0.34}
```

This function **always returns uniform probabilities** regardless of what the model actually predicted. The `signal` parameter contains `direction_confidence` and actual probabilities from DirectionModel, but they are completely ignored.

**Impact**: The `EnhancedTradingSignal.direction_probabilities` field is always `{UP: 0.33, DOWN: 0.33, FLAT: 0.34}`. Any downstream code using these probabilities gets useless data.

### 4.4 Trade Recommendation Logic

Thresholds (lines 1253-1256):
```python
MIN_DIRECTIONAL_PROB = 0.35    # Min probability for direction
MIN_EDGE = 0.10                # Min edge over opposite direction
MIN_CONVICTION = 0.55          # Min overall conviction
```

Logic: LONG if `up_prob >= 0.35 AND up_prob > down_prob + 0.10 AND conviction >= 0.55`. SHORT mirrors for down. Else STAY_OUT.

**Assessment**: Thresholds are reasonable but not adaptive. No evidence of calibration against historical performance.

---

## Section 5: Risk Management

### 5.1 Position Sizing

ORION does **not** produce position sizing recommendations. It outputs direction, conviction, and win probability. Position sizing is handled by the consuming bots (GIDEON, SOLOMON_V2).

### 5.2 Risk Adjustments in Signal

**Location**: `gex_signal_integration.py:329-333`

```python
risk_score = signal.overall_conviction
if signal.expected_volatility_pct > 2.0:
    risk_score *= 0.8   # Reduce in high vol
if signal.pin_zone_prob > 0.7 and suggested_spread != "NONE":
    risk_score *= 0.9   # Reduce in strong pin zones
```

**Assessment**: Basic risk adjustment. No circuit breaker integration, no drawdown protection.

### 5.3 Fallback Behavior

When models unavailable, `_create_fallback_signal()` returns:
- direction: FLAT, confidence: 0.0
- recommendation: STAY_OUT
- reasoning: "Models not available - defaulting to STAY_OUT"

**Good**: Fails safe to no-trade.

### 5.4 Hybrid Probability Safety

**Location**: `shared_gamma_engine.py:529-603`

The 60/40 hybrid ensures ML never fully controls probability:
- If ML fails → falls back to 100% distance-based
- ML probability capped by `min(0.85, ...)` in integration layer

---

## Section 6: Backtest Integrity

### 6.1 No Backtesting Framework

ORION has **no dedicated backtesting system**. Unlike WISDOM/Prophet which can be backtested against historical trade outcomes, ORION's predictions are not systematically tracked and evaluated.

### 6.2 Auto-Validation System

**Location**: `quant/auto_validation_system.py:449-491`

Weekly validation (Saturday 6 PM CT):
- Computes in-sample vs out-of-sample accuracy
- Flags degradation if OOS drops >20% below IS
- Can trigger automatic retraining

**Issue**: Uses the same `accuracy_score` metric — doesn't detect calibration drift or class imbalance exploitation.

### 6.3 Signal Tracking Gap

- No signal logging table for ORION predictions
- No outcome tracking (did the predicted direction come true?)
- Only `logger.info()` at inference time
- No performance dashboard for ORION signal quality

**Impact**: Impossible to know if ORION is providing value without manual analysis.

---

## Section 7: Execution & Infrastructure

### 7.1 Model Lifecycle

| Phase | Mechanism | Schedule |
|-------|-----------|----------|
| Data population | `populate_recent_gex_structures(days=30)` | Before each training run |
| Training | `GEXSignalGenerator.train()` | Sunday 6 PM CT |
| Validation | `auto_validation_system` | Saturday 6 PM CT |
| Persistence | pickle → zlib → base64 → PostgreSQL `ml_models` table | After each training |
| Loading | Singleton `GEXProbabilityModels.__new__` auto-loads from DB | On first use |
| Staleness | `needs_retraining(max_age_hours=168)` | Checked before inference |

### 7.2 Singleton Pattern

`GEXProbabilityModels` uses `__new__` singleton — only one instance across the application. Models loaded once from database on first instantiation. `_load_attempted` flag prevents repeated load attempts.

### 7.3 Integration Map

```
ORION (gex_probability_models.py)
├── GEXSignalGenerator: 5 sub-models trained together
├── GEXProbabilityModels: Singleton wrapper, auto-loads from DB
│   └── Used by: shared_gamma_engine.py → WATCHTOWER/GLORY dashboard
│       calculate_probability_hybrid(): 60% ML + 40% distance
│
├── GEXSignalIntegration (gex_signal_integration.py): Bot-facing interface
│   ├── GIDEON (trading/gideon/signals.py): get_combined_signal()
│   └── SOLOMON_V2 (trading/solomon_v2/signals.py): get_combined_signal()
│
└── API Layer (ml_routes.py)
    ├── GET  /api/ml/gex-models/status
    ├── POST /api/ml/gex-models/train
    ├── POST /api/ml/gex-models/predict
    └── GET  /api/ml/gex-models/data-status
```

### 7.4 Model Persistence Details

- Serialization: `joblib.dump()` → `pickle + zlib compression + base64`
- Storage: PostgreSQL `ml_models` table via `model_persistence.py`
- Payload: All 5 models + scalers + label encoders + feature names
- No feature version tracking (unlike WISDOM V3 and Prophet V2)
- No backward compatibility mechanism if features change

---

## Section 8: Prioritized Findings & Recommendations

### CRITICAL Severity

#### C1: No Class Imbalance Handling in Any Sub-Model
**Files**: `gex_probability_models.py` — all 5 model `.train()` methods
**Impact**: MagnetAttractionModel (~89% base rate) is essentially useless. DirectionModel biased toward FLAT.
**Fix**: Add `scale_pos_weight` for binary models, `sample_weight` for multi-class DirectionModel. Compute per-fold for proper CV evaluation.

#### C2: Win Probability +10% Boost in gex_signal_integration.py
**File**: `gex_signal_integration.py:478-483`
**Impact**: GIDEON and SOLOMON_V2 receive inflated win probabilities, taking trades that should be skipped.
**Fix**: Remove the `+ 0.10` boost. Let models provide calibrated probabilities.

#### C3: _get_direction_probs Returns Uniform Values Always
**File**: `gex_signal_integration.py:351-362`
**Impact**: `EnhancedTradingSignal.direction_probabilities` is always `{UP: 0.33, DOWN: 0.33, FLAT: 0.34}` regardless of model output.
**Fix**: Extract actual probabilities from `signal.direction_confidence` and the `CombinedSignal`. The direction model's `predict()` returns a `ModelPrediction` with real probabilities — pass them through.

### HIGH Severity

#### H1: No Brier Score or Calibration Assessment
**Impact**: Cannot evaluate if predicted probabilities match observed frequencies.
**Fix**: Compute Brier score on CV folds (not in-sample). Add calibration curve analysis to training output.

#### H2: FlipGravity Model Based on Unconfirmed Hypothesis
**File**: `gex_probability_models.py:630-637`
**Impact**: H4 was NOT confirmed (44.4% base rate). Model trained anyway "to let ML find conditional patterns" but may add noise to combined signal.
**Fix**: Consider removing FlipGravity from the ensemble or adding a reliability weight. If CV accuracy ≤ base rate + 2%, exclude from conviction calculation.

#### H3: Integer day_of_week (Not Cyclical)
**Impact**: Friday (4) to Monday (0) discontinuity. Models may learn spurious ordinal relationships.
**Fix**: Replace with `day_of_week_sin` and `day_of_week_cos` (same pattern as WISDOM V3 and Prophet V2).

#### H4: Feature Distribution Mismatch Between Training and Inference
**Impact**: `net_gamma_normalized` computed differently in training (z-score) vs inference (`net_gamma/total_gamma`). `top_magnet_concentration` and `vix_percentile` hardcoded at inference.
**Fix**: Unify feature computation. Save scaler statistics and apply same normalization at inference.

### MEDIUM Severity

#### M1: Accuracy-Only Metrics
**Impact**: Accuracy is misleading for imbalanced targets. A model predicting all-FLAT would appear 40-50% accurate.
**Fix**: Add precision, recall, F1 per class, and ROC-AUC. Use F1-macro as primary metric for DirectionModel.

#### M2: No Feature Importance Stored
**Impact**: Cannot diagnose what the models are learning. Cannot detect feature drift.
**Fix**: Save `model.feature_importances_` to database alongside model artifacts.

#### M3: Hardcoded Conviction Factors
**Impact**: Conviction = mean of arbitrary 0.5/0.6/0.7/0.8/0.9 values. Not calibrated.
**Fix**: Learn conviction weights from historical signal performance, or at minimum calibrate against observed outcomes.

#### M4: Fallback Data Quality
**Impact**: If `gex_structure_daily` is empty, training uses crude approximations (60/40 gamma split, etc.)
**Fix**: Add data quality check before training. If fallback data used, log warning and reduce model confidence.

### LOW Severity

#### L1: No VRP Feature
**Fix**: Add `volatility_risk_premium = expected_move_pct - realized_vol_5d` as done in WISDOM V3 and Prophet V2.

#### L2: Fixed 60/40 Hybrid Weight
**Fix**: Consider making the ML weight adaptive based on model age/confidence, or learn optimal weight from validation.

#### L3: No Macro Event Awareness
**Fix**: Add FOMC/CPI/NFP binary flags to calendar features.

---

## Comparison with WISDOM V3 and Prophet V2

| Feature | WISDOM V3 | Prophet V2 | ORION (Current) |
|---------|-----------|------------|-----------------|
| Class imbalance | `scale_pos_weight` | `sample_weight` | **NONE** |
| Brier score | CV folds | CV folds | **Not computed** |
| Cyclical day | sin/cos | sin/cos | **Integer** |
| VRP feature | Yes | Yes | **No** |
| Adaptive thresholds | `base_rate - 0.15/0.05` | `base_rate - 0.15/0.05` | **Hardcoded** |
| Feature versioning | V1/V2/V3 | V1/V2/V3 | **None** |
| Win prob manipulation | Removed | Removed | **+10% boost active** |
| Calibration | Brier + thresholds | Brier + thresholds | **None** |

---

## Recommended Fix Priority

1. **Remove +10% win_probability boost** (C2) — Quick fix, high impact
2. **Fix _get_direction_probs to return real probabilities** (C3) — Quick fix, data integrity
3. **Add class imbalance handling to all models** (C1) — Medium effort, fundamental correctness
4. **Add Brier score to CV evaluation** (H1) — Easy addition to training loop
5. **Replace integer day_of_week with cyclical encoding** (H3) — Easy feature engineering change
6. **Unify feature computation between training/inference** (H4) — Medium effort, prevents distribution mismatch
7. **Evaluate FlipGravity model utility** (H2) — Requires analysis of CV metrics vs base rate
8. **Add feature versioning** — Follow WISDOM V3/Prophet V2 pattern for backward compat

---

## Files Audited

| File | Lines | Purpose |
|------|-------|---------|
| `quant/gex_probability_models.py` | 1,762 | Core 5-model ensemble |
| `quant/gex_signal_integration.py` | 576 | Bot-facing signal interface |
| `core/shared_gamma_engine.py` | 1,149 | Hybrid probability calculation |
| `scheduler/trader_scheduler.py` | ~5,000 | Training schedule (Sunday 6 PM CT) |
| `backend/api/routes/ml_routes.py` | ~2,000 | ORION API endpoints |
| `quant/auto_validation_system.py` | ~500 | Weekly model validation |
| `trading/gideon/signals.py` | ~300 | GIDEON bot integration |
| `trading/solomon_v2/signals.py` | ~300 | SOLOMON_V2 bot integration |
