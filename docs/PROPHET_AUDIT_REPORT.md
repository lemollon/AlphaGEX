# PROPHET ML Advisor - ML Trading Bot Audit & Review

**Date**: 2026-02-10
**Branch**: `claude/watchtower-data-analysis-6FWPk`
**Auditor**: Claude Code (Orchestration Layer Evaluation)
**Framework**: Comprehensive ML Trading Bot Audit — Options Market Edition
**Status**: AUDIT + V2 FIXES COMPLETE

---

## Executive Summary

Prophet is the **sole decision authority** for all AlphaGEX trading bots (~5,700 lines). When Prophet says TRADE, bots trade. When Prophet says SKIP, bots skip. This makes Prophet bugs the highest-impact issues in the entire system. Prophet serves 6 active bots: FORTRESS (SPY 0DTE IC), ANCHOR (SPX weekly IC), SOLOMON/GIDEON (directional spreads), SAMSON (aggressive SPX IC), and VALOR (futures scalping).

**What was found**: Well-structured multi-bot advisory system with proper signal chain separation from WISDOM, extensive live logging, Claude AI validation, and Proverbs feedback integration. However, the original version suffered from 4 critical issues (class imbalance blindness, 1.2x confidence inflation, post-ML probability manipulation destroying calibration, hardcoded thresholds at ~89% base rate), 3 high-impact gaps, and several medium improvements — all now fixed in V2.

**V2 Fixes Applied** (prior session):
- `quant/prophet_advisor.py`: sample_weight for class imbalance, Brier score on CV folds, cyclical day encoding (sin/cos), VRP feature, adaptive thresholds from base rate, 60-trade win rate horizon, removed 1.2x confidence inflation from FORTRESS/CORNERSTONE/LAZARUS, removed post-ML GEX probability adjustments from all 4 bot advice methods, fixed price_change_1d look-ahead bias, feature version tracking (V1/V2/V3)

### Signal Chain Context
```
WISDOM (signals.py) → win_probability → Signal
                                            ↓
Prophet (trader.py) → strategy_recommendation + bot-specific advice → TRADE/SKIP
                                            ↓
Executor → position_size (Thompson × Kelly) → Tradier API → fills
```

WISDOM and Prophet are **separate ML models** answering different questions:
- **WISDOM**: "What's the probability this specific trade wins?" (XGBoost binary classifier in signals.py)
- **Prophet**: "Should we trade IC or Directional? What strikes? What risk %?" (sklearn GBC in trader.py)

They do NOT feed predictions into each other. Both train on overlapping but separately extracted data.

---

## SECTION 1: DATA PIPELINE AUDIT

### 1.1 Data Sources & Quality

| Source | Table/Method | Type | Quality Assessment |
|--------|-------------|------|-------------------|
| **CHRONICLES backtest** | `extract_features_from_chronicles()` | Historical backtest trades | Good — primary initial training source |
| **Live outcomes** | `prophet_training_outcomes` | Live trade results + features JSON | Good — most accurate, continuous learning |
| **Database backtests** | `zero_dte_backtest_trades` | Database-persisted backtest results | Moderate — some approximations (see below) |

**Data consumed per training sample**: VIX (level, percentile, change), day of week (cyclical sin/cos in V3), price change (previous-day in V3), expected move %, VRP (V3), rolling 60-trade win rate (V3), GEX (normalized, regime, flip distance, between walls).

**Data frequency**: Per-trade — each closed trade generates one training sample. Training triggered daily at midnight CT or when 20+ new outcomes accumulate.

**Missing data handling**:
- `vix_percentile_30d`: Rolling rank calculation, fills NaN with 50 (median) — **Correct**
- `vix_change_1d`: `pct_change().fillna(0)` — **Correct** for first sample
- `win_rate_60d`: Defaults to 0.68 when insufficient history — **Acceptable** seed value
- GEX fields: Default to 0/NEUTRAL when not available — **Correct**

### 1.2 Options-Specific Data Integrity

**IV Surface**: Not directly modeled. Prophet uses `expected_move_pct` and VIX as volatility proxies. The new V3 `volatility_risk_premium` feature partially captures IV vs realized vol spread, but per-strike IV surface (skew, term structure) is absent.

**Greeks**: Not modeled. Prophet operates at the strategy level (trade/skip, IC/directional, risk %), not at the option chain level. Individual Greeks (delta, gamma, theta, vanna, charm) are handled downstream by the execution layer (signals.py files).

**Bid-ask spreads**: Not captured in training data. No slippage model. This is acceptable since Prophet advises on whether TO trade, not on specific execution prices. The `expected_move_pct` partially captures volatility environment.

**Open interest / Volume**: Not used as features. This is a gap — unusual options activity could improve directional prediction for SOLOMON/GIDEON.

### 1.3 Data Pipeline Issues

| Issue | Severity | Status |
|-------|----------|--------|
| **Look-ahead bias**: `price_change_1d` used same-day close in training | CRITICAL | **FIXED V2** — Now uses previous trade's price change |
| **VRP approximation at inference**: `expected_move_pct * 0.2` is a rough proxy | MEDIUM | Known limitation — live inference lacks 5-day realized vol |
| **DB backtest data quality**: `expected_move_1d` approximated as 1% of spot | MEDIUM | Acceptable fallback |
| **UNIQUE(trade_date, bot_name)**: Training outcomes table allows only 1 trade/day/bot | HIGH | **OPEN** — 0DTE bots make multiple trades/day, only last recorded |

---

## SECTION 2: FEATURE ENGINEERING AUDIT

### 2.1 Feature Set Comparison (V1 → V2 → V3)

| Feature | V1 | V2 | V3 | Type | Rationale |
|---------|----|----|-----|------|-----------|
| `vix` | ✓ | ✓ | ✓ | Continuous | Core volatility signal |
| `vix_percentile_30d` | ✓ | ✓ | ✓ | Continuous | VIX relative to recent history |
| `vix_change_1d` | ✓ | ✓ | ✓ | Continuous | VIX momentum |
| `day_of_week` | ✓ | ✓ | — | Integer 0-4 | **Removed V3**: Cyclical discontinuity Mon→Fri |
| `day_of_week_sin` | — | — | ✓ | Continuous [-1,1] | Cyclical encoding: `sin(2π·dow/5)` |
| `day_of_week_cos` | — | — | ✓ | Continuous [-1,1] | Cyclical encoding: `cos(2π·dow/5)` |
| `price_change_1d` | ✓ | ✓ | ✓ | Continuous | **V3 FIX**: Previous-day move (no look-ahead) |
| `expected_move_pct` | ✓ | ✓ | ✓ | Continuous | IV-implied expected daily range |
| `volatility_risk_premium` | — | — | ✓ | Continuous | `expected_move - realized_vol_5d` |
| `win_rate_30d` | ✓ | ✓ | — | Continuous | **Replaced V3**: Too much leakage |
| `win_rate_60d` | — | — | ✓ | Continuous | 60-trade rolling win rate (reduced leakage) |
| `gex_normalized` | — | ✓ | ✓ | Continuous | Normalized gamma exposure |
| `gex_regime_positive` | — | ✓ | ✓ | Binary 0/1 | GEX regime classification |
| `gex_distance_to_flip_pct` | — | ✓ | ✓ | Continuous | Distance to gamma flip point |
| `gex_between_walls` | — | ✓ | ✓ | Binary 0/1 | Price contained within gamma walls |

**Total features**: V1=7, V2=11, V3=13

### 2.2 Feature Quality Assessment

**Strong Features** (hypothesis-driven, options-relevant):
- `vix` + `vix_percentile_30d` + `vix_change_1d`: Complete volatility characterization (level, rank, momentum)
- `gex_regime_positive` + `gex_between_walls`: Market maker positioning signals
- `volatility_risk_premium`: Captures IV overpricing — core profit engine for premium sellers
- `expected_move_pct`: Direct measure of option-implied volatility

**Weak/Questionable Features**:
- `win_rate_60d`: Self-referential — the model's own past win rate becomes an input. Creates positive feedback loop when things go well and death spiral when they don't. Should be replaced with an external signal.
- `gex_distance_to_flip_pct`: Can be zero when flip point data is unavailable, creating a misleading "at the flip point" signal
- `price_change_1d`: Previous-day move has weak predictive power for mean-reverting strategies (ICs). Better suited for momentum/directional models.

### 2.3 Options-Specific Feature Gaps

| Missing Feature | Impact | Difficulty |
|----------------|--------|------------|
| **IV Rank / IV Percentile** | HIGH — Premium selling profitability correlates with elevated IV rank | LOW — VIX percentile partially covers this |
| **Put/Call skew** | MEDIUM — Skew predicts directional risk for IC strategies | MEDIUM — Requires options chain data |
| **Term structure slope** | MEDIUM — Contango vs backwardation affects 0DTE strategies | HIGH — Requires multi-expiry data |
| **Charm (delta decay)** | LOW — Matters for intraday position management, not entry decisions | N/A — Handled by execution layer |
| **Time of day** | MEDIUM — 0DTE ICs have different profile at open vs close | LOW — Easy to add, Proverbs tracks this |

### 2.4 Feature Version Tracking

```python
FEATURE_COLS     = [...13 V3 features...]   # Current (cyclical day, VRP, 60d win rate)
FEATURE_COLS_V2  = [...11 V2 features...]   # Backward compat (integer day, 30d win rate)
FEATURE_COLS_V1  = [...7 V1 features...]    # Backward compat (no GEX)
```

**Backward compatibility**: `_load_model()` reads `feature_version` from saved metadata and selects correct feature list. `_get_base_prediction()` branches on `feature_version >= 3` to construct correct feature array.

---

## SECTION 3: MODEL ARCHITECTURE AUDIT

### 3.1 Model Configuration

```python
GradientBoostingClassifier(
    n_estimators=150,
    max_depth=4,
    learning_rate=0.1,
    min_samples_split=20,
    min_samples_leaf=10,
    subsample=0.8,
    random_state=42
)
```

**Model choice**: sklearn GBC (not XGBoost). Appropriate for the dataset size (~100-1000 trades). Lighter than XGBoost, sufficient for 13 features.

**Why not XGBoost?** Prophet was originally designed for smaller datasets from individual bot outcomes. XGBoost's advantages (sparse-aware, GPU acceleration, regularization) are less important at this scale. sklearn GBC integrates cleanly with `CalibratedClassifierCV`.

### 3.2 Class Imbalance Handling

| Metric | Before V2 | After V2 |
|--------|-----------|----------|
| **Base rate** | ~89% wins (IC trading) | ~89% wins |
| **Handling** | None — model predicts majority class | `sample_weight`: minority class upweighted |
| **Effect** | Model outputs ~0.89 for everything | Model learns to distinguish win/loss patterns |

**V2 Implementation** (`prophet_advisor.py:4420-4430`):
```python
weight_win = n_losses / len(y)    # ~0.11 for wins
weight_loss = n_wins / len(y)     # ~0.89 for losses
sample_weight_array = np.where(y == 1, weight_win, weight_loss)
```

**Why sample_weight, not class_weight?** sklearn GBC uses `sample_weight` in `.fit()`, not `class_weight` parameter. This is correct — GBC computes per-sample gradients where `sample_weight` directly scales the loss contribution.

### 3.3 Calibration

**Method**: `CalibratedClassifierCV(model, method='isotonic', cv=3)`

Isotonic calibration is appropriate for this use case:
- Enough samples (100+) for isotonic to be stable
- Non-parametric — doesn't assume sigmoid shape
- Applied AFTER the main model training, preserving GBC's gradient structure

**V2 Fix**: Previously, post-ML probability manipulation (+3%/+5% GEX adjustments, 1.2x confidence multiplier) destroyed the isotonic calibration. All post-ML manipulations were removed in V2.

### 3.4 Validation Strategy

**Method**: `TimeSeriesSplit(n_splits=5)` — Correct for financial time series (no future leak).

**Metrics computed on CV folds** (not in-sample):
- Accuracy, Precision, Recall, F1
- AUC-ROC
- **Brier Score** (V2 addition) — proper calibration metric

**Issue**: Final model is fit on ALL data (`model.fit(X_scaled, y, sample_weight=...)`), then calibrated on ALL data again (`CalibratedClassifierCV(model, cv=3).fit(X_scaled, y)`). The CV metrics reflect fold performance, but the final deployed model has seen all training data. This is standard practice but means reported metrics are optimistic for the deployed model.

### 3.5 Adaptive Thresholds

| Parameter | Before V2 | After V2 |
|-----------|-----------|----------|
| **SKIP threshold** | `< 0.45` (hardcoded) | `< base_rate - 0.15` (e.g., `< 0.74`) |
| **TRADE_FULL threshold** | `>= 0.65` (hardcoded) | `>= base_rate - 0.05` (e.g., `>= 0.84`) |
| **TRADE_REDUCED** | 0.45 to 0.65 | 0.74 to 0.84 |

**Why this matters**: With 89% base rate, the old 0.45 SKIP threshold was unreachable — the model averaged ~0.89 output. SKIP would essentially never fire, meaning Prophet would advise trading in ALL market conditions.

---

## SECTION 4: SIGNAL GENERATION AUDIT

### 4.1 Bot-Specific Advice Methods

Prophet provides **5 advice methods**, each tailored to a specific trading strategy:

| Method | Bot(s) | Strategy | Key Logic |
|--------|--------|----------|-----------|
| `get_fortress_advice()` | FORTRESS | SPY 0DTE IC | VIX skip rules, GEX wall strikes, Claude validation |
| `get_anchor_advice()` | ANCHOR | SPX Weekly IC | Same as FORTRESS + $10 spread width, 1 SD minimum strikes |
| `get_solomon_advice()` | SOLOMON, GIDEON | Directional spreads | ML direction, flip distance filter, Friday filter |
| `get_cornerstone_advice()` | CORNERSTONE | Wheel strategy | Simpler — VIX/GEX reasoning, no Claude |
| `get_lazarus_advice()` | LAZARUS | Directional calls | Negative GEX squeeze detection, Claude validation |

### 4.2 Signal Flow (FORTRESS Example)

```
1. _check_and_reload_model_if_stale()     → Auto-reload if newer model in DB
2. VIX skip rules (unless omega_mode)     → SKIP_TODAY + suggest SOLOMON if directional
3. _get_base_prediction(context)           → ML model predict_proba → win_probability
4. GEX wall strike calculation             → SPY→SPX scaling, buffer calculation
5. GEX regime scoring                      → ic_suitability adjustment
6. Claude AI validation (optional)         → Confidence adjustment ±0.10
7. Hallucination risk check                → Penalty 2-5% for MEDIUM/HIGH
8. _get_advice_from_probability()          → TRADE_FULL / TRADE_REDUCED / SKIP_TODAY
9. SD multiplier selection                 → 1.2/1.3/1.4 based on confidence
10. _add_staleness_to_prediction()         → Track model freshness
```

### 4.3 V2 Fixes to Signal Generation

| Issue | Before V2 | After V2 |
|-------|-----------|----------|
| **1.2x confidence inflation** | `confidence = base_pred['win_probability'] * 1.2` | `confidence = base_pred['win_probability']` |
| **Post-ML GEX +3%/+5%** | `win_probability += 0.03` for positive GEX | Removed — GEX already in features |
| **Hallucination penalty** | 10%/5% for HIGH/MEDIUM | Reduced to 5%/2% (was too aggressive) |
| **ANCHOR uses hardcoded thresholds** | `>= 0.58` TRADE_FULL, `>= 0.52` TRADE_REDUCED | Still hardcoded — **OPEN ISSUE** |

### 4.4 SOLOMON Direction Logic

SOLOMON/GIDEON uses a 3-tier direction determination:

1. **ML Direction** (primary): `GEXSignalIntegration.get_combined_signal()` — ORION models provide BULLISH/BEARISH/FLAT
2. **GEX Fallback**: Negative GEX + flip distance → BEARISH. Positive GEX + wall proximity → direction
3. **Neutral Fallback**: Trend tracker or wall-proximity heuristic

**Additional Filters** (directional only):
- **Flip distance filter**: 0.5-3% optimal, 3-5% reduced, >5% skip
- **Friday filter**: 0DTE + weekend gap risk → TRADE_REDUCED, size halved
- **Wall filter**: `dist_to_wall < wall_filter_pct` (3% SOLOMON, 6% GIDEON)

### 4.5 Remaining Signal Issues

| Issue | Severity | Impact |
|-------|----------|--------|
| **ANCHOR hardcoded thresholds** (0.58/0.52/0.48) | HIGH | Doesn't use adaptive thresholds from base rate |
| **ANCHOR hallucination penalty** (10%/5%) | MEDIUM | Not reduced like FORTRESS/LAZARUS/SOLOMON |
| **win_probability overwrite in SOLOMON** | MEDIUM | `base_pred['win_probability'] = direction_confidence` ignores ML model output |
| **Claude validation is LLM-dependent** | LOW | If Claude API is down, no validation — acceptable degradation |

---

## SECTION 5: RISK MANAGEMENT AUDIT

### 5.1 Position Sizing

| Advice Level | Risk % | SD Multiplier | Notes |
|-------------|--------|---------------|-------|
| TRADE_FULL | 10.0% | 1.2 (>=0.70), 1.3 (>=0.60), 1.4 (<0.60) | Full position |
| TRADE_REDUCED | 3.0-8.0% (sliding scale) | Same as FULL | Reduced position |
| SKIP_TODAY | 0% | N/A | No trade |

**SD multiplier fix** (V2): Minimum raised from 1.0 to 1.2. Previously, 1.0 SD placed strikes at the exact expected move boundary — breached 32% of the time. 1.2 SD provides 20% cushion.

### 5.2 VIX Skip Rules (FORTRESS/ANCHOR)

```
Rule 1: vix > vix_hard_skip          → SKIP (e.g., VIX > 32)
Rule 2: vix > vix_monday_friday_skip  → SKIP on Mon/Fri (e.g., VIX > 30)
Rule 3: vix > vix_streak_skip         → SKIP after 2+ losses (e.g., VIX > 28)
```

**OMEGA mode**: When `omega_mode=True`, VIX skip rules are disabled — defers to WISDOM ML Advisor as primary decision maker.

### 5.3 Cross-Bot Correlation Risk

Via Proverbs integration:
- **Correlation threshold**: abs(correlation) > 0.7 triggers size reduction
- **Size reduction**: 15% per correlated bot (max 30%)
- **STATUS**: Information-only in V2 — does NOT affect Prophet's scores

### 5.4 Weekend Risk (Friday)

SOLOMON/GIDEON:
- **Friday filter**: `win_probability -= 0.05`, downgrade TRADE_FULL → TRADE_REDUCED
- **Size halved**: `risk_pct *= 0.5`
- **Rationale**: Data showed Friday has 14% win rate with -$215K losses for directional

FORTRESS/ANCHOR:
- VIX Monday/Friday skip rule covers this case
- Proverbs weekend pre-check provides additional context (display only)

### 5.5 Risk Management Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| **No max daily loss limit** | HIGH | Prophet has no circuit breaker — "Oracle is god" philosophy removed it |
| **No per-bot position limit** | MEDIUM | Prophet doesn't track how many positions a bot has open |
| **No portfolio-level risk** | HIGH | No aggregated risk view across all 6 bots trading simultaneously |
| **Proverbs is display-only** | MEDIUM | Correlation risk, time-of-day adjustments collected but not used |

---

## SECTION 6: BACKTEST INTEGRITY AUDIT

### 6.1 Training Data Sources

| Method | Source | Priority | Min Samples |
|--------|--------|----------|-------------|
| `train_from_live_outcomes()` | `prophet_training_outcomes` | 1st | 20 |
| `train_from_database_backtests()` | `zero_dte_backtest_trades` | 2nd | 100 |
| `train_from_chronicles()` | In-memory CHRONICLES results | 3rd (fallback) | 100 |

### 6.2 Look-Ahead Bias Check

| Feature | Before V2 | After V2 | Status |
|---------|-----------|----------|--------|
| `price_change_1d` | Same-day close (know future) | Previous trade's move | **FIXED** |
| `win_rate_60d` | Uses current trade outcome in window | Rolling lookback excluding current | **FIXED** |
| `vix_change_1d` | Post-hoc calculation | Same — but VIX is known at trade entry | OK |
| `expected_move_pct` | Calculated from VIX | Same — implied vol is known pre-trade | OK |

### 6.3 Survivorship Bias

**Potential issue**: Training only on trades that were actually taken. Prophet doesn't see the "what if we had traded here" counterfactual. Backtests (CHRONICLES, zero_dte_backtest_trades) include all signals, but live outcomes only include executed trades.

**Mitigation**: Live training supplements backtests, not replaces them. `auto_train()` falls back to backtest data when live data is insufficient.

### 6.4 UNIQUE Constraint Problem

**CRITICAL OPEN ISSUE**: `prophet_training_outcomes` has `UNIQUE(trade_date, bot_name)`.

0DTE bots (FORTRESS, SAMSON) can make **multiple trades per day**. The UNIQUE constraint means only the **last** trade's outcome is recorded. This systematically discards intraday trade data, reducing training set size and potentially introducing bias (if first trades of the day have different characteristics than last trades).

**Impact**: For a bot making 3 trades/day, this discards 67% of training data.

**Fix needed**: Remove UNIQUE constraint or change to `UNIQUE(trade_date, bot_name, prediction_id)`.

### 6.5 TimeSeriesSplit Validation

```python
tscv = TimeSeriesSplit(n_splits=5)
for train_idx, test_idx in tscv.split(X_scaled):
    # Train on past, test on future — no leakage
```

**Correct**: No shuffling, no random split. Preserves temporal ordering. 5 folds is standard for financial data.

---

## SECTION 7: EXECUTION & INFRASTRUCTURE AUDIT

### 7.1 Model Persistence

| Storage | Priority | Persistence |
|---------|----------|-------------|
| PostgreSQL `prophet_trained_models` | Primary | Survives Render deploys |
| Local file `prophet_model.pkl` | Backup | Lost on Render redeploy |

**Serialization**: `pickle.dumps()` for model + calibrator + scaler + V3 metadata (feature_version, feature_cols, base_rate).

**Loading order**: Database first → local file fallback → untrained (rule-based fallback).

### 7.2 Model Staleness Detection

```python
_version_check_interval_seconds = 300  # Check DB for new model every 5 min
_check_and_reload_model_if_stale()     # Called before EVERY prediction
```

**Flow**:
1. Every 5 minutes, check DB for newer `model_version`
2. If DB version differs from in-memory version, reload from DB
3. Prediction includes `hours_since_training` and `is_model_fresh` fields

**Correct**: Prevents bots from using stale models after scheduled retraining.

### 7.3 Thread Safety

| Component | Thread Safety | Implementation |
|-----------|--------------|----------------|
| `ProphetAdvisor` singleton | ✓ | Double-check locking pattern |
| `ProphetLiveLog` singleton | ✓ | Thread lock on all list operations |
| Model reload | ✓ | Version check is read-only, reload is atomic |
| DB connections | ✓ | Context manager `get_db_connection()` |

### 7.4 Training Schedule

| Trigger | Time | Threshold | Source |
|---------|------|-----------|--------|
| Midnight job | 00:00 CT daily | 10 outcomes | `scheduled_prophet_training_logic()` |
| Proverbs feedback loop | 16:00 CT daily | 10 outcomes | `scheduled_proverbs_feedback_loop()` |
| Manual API | On demand | Configurable | `POST /api/prophet/train` |

### 7.5 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/prophet/health` | GET | Staleness metrics, model freshness |
| `/api/prophet/status` | GET | Full status with training metrics |
| `/api/prophet/strategy-recommendation` | POST/GET | IC vs Directional recommendation |
| `/api/prophet/strategy-performance` | GET | Performance by VIX/GEX regime |
| `/api/prophet/train` | POST | Trigger manual training |
| `/api/prophet/pending-outcomes` | GET | Count pending training outcomes |
| `/api/prophet/vix-regimes` | GET | VIX regime definitions |

### 7.6 Live Logging & Transparency

`ProphetLiveLog` captures every step of the prediction pipeline:

```
INPUT → ML_FEATURES → ML_OUTPUT → CLAUDE_PROMPT → CLAUDE_RESPONSE → DECISION → SENT_TO_BOT
```

**Claude exchange logging**: Full prompt/response pairs stored for audit trail, including hallucination risk assessment and token usage.

### 7.7 Backward Compatibility

| Component | Compatibility |
|-----------|--------------|
| Feature versions | V1/V2/V3 automatic detection from saved metadata |
| Bot names | `FortressMLAdvisor = ProphetAdvisor` alias preserved |
| Functions | `get_advisor = get_prophet`, `get_trading_advice = get_fortress_advice` |
| Old pickle format | `saved.get('feature_version', 2)` defaults to V2 |

---

## SECTION 8: COMPREHENSIVE FINDINGS

### 8.1 Critical Issues (All Fixed in V2)

| # | Issue | Impact | Fix Applied |
|---|-------|--------|-------------|
| C1 | **Class imbalance blindness** — 89% win rate, model predicts majority class | Prophet advises TRADE on everything, cannot identify losing conditions | `sample_weight` array: losses get 8x weight of wins |
| C2 | **1.2x confidence inflation** — `confidence = win_prob * 1.2` | Confidence > 1.0 possible, downstream bots misinterpret | `confidence = win_prob` (no inflation) |
| C3 | **Post-ML GEX probability manipulation** — +3%/+5% adjustments in bot advice methods | Destroys isotonic calibration, double-counts GEX signal | All post-ML adjustments removed from FORTRESS, CORNERSTONE, LAZARUS, SOLOMON |
| C4 | **Hardcoded thresholds at 0.45/0.65** — useless with 89% base rate | SKIP never fires (0.45 unreachable), TRADE_FULL fires on everything | Adaptive: SKIP < base_rate-0.15, FULL >= base_rate-0.05 |

### 8.2 High-Impact Issues

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| H1 | **UNIQUE(trade_date, bot_name)** on training outcomes | Discards multiple intraday trades — up to 67% data loss | **OPEN** |
| H2 | **ANCHOR hardcoded thresholds** (0.58/0.52/0.48) | Doesn't benefit from adaptive threshold logic | **OPEN** |
| H3 | **No portfolio-level risk** | 6 bots trade independently with no aggregated risk view | **OPEN** |
| H4 | **SOLOMON overwrites ML probability with direction confidence** | Ignores trained model output for directional trades | **OPEN** |

### 8.3 Medium Issues

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| M1 | **VRP approximation at inference** (`expected_move_pct * 0.2`) | Training VRP uses rolling realized vol, inference uses rough proxy | Known limitation |
| M2 | **ANCHOR hallucination penalty not reduced** (10%/5% vs 5%/2%) | More aggressive Claude penalty than other bots | **OPEN** |
| M3 | **Proverbs data collected but not used** | Time-of-day, regime, correlation data is display-only | By design ("Prophet is god") |
| M4 | **No feature importance tracking in production** | Can't monitor feature drift without retraining | Feature importances stored in TrainingMetrics |
| M5 | **win_rate_60d self-referential feedback** | Model's own past performance used as input feature | Could amplify winning/losing streaks |

### 8.4 Improvements Made (V2 Summary)

| Improvement | Section | Lines Changed |
|-------------|---------|---------------|
| `sample_weight` for class imbalance | Training | 4420-4430, 5324-5332 |
| Brier score on CV folds | Training | 4466, 5368 |
| Cyclical day encoding (sin/cos) | Features | 4300-4302, 5262-5263 |
| VRP feature | Features | 4332-4339, 5269-5275 |
| 60-trade win rate horizon | Features | 4286-4290, 5277-5279 |
| Price change look-ahead fix | Features | 4308-4316 |
| Removed 1.2x confidence inflation | Signal gen | 2807, 2923, 3047 |
| Removed post-ML GEX adjustments | Signal gen | FORTRESS, CORNERSTONE, LAZARUS, SOLOMON |
| Adaptive thresholds from base rate | Decision | 1478-1498 |
| Feature version tracking (V1/V2/V3) | Persistence | 1365-1408, 1839-1842, 1893-1896 |

### 8.5 Architecture Assessment

**Strengths**:
- Clean separation between WISDOM (primary ML) and Prophet (strategy advisor)
- Comprehensive live logging with full data flow transparency
- Claude AI validation with anti-hallucination checks
- Proverbs integration for historical performance feedback
- Proper model staleness detection and auto-reload
- Thread-safe singleton pattern with proper locking
- Database persistence surviving Render deploys
- Backward compatibility across 3 feature versions

**Weaknesses**:
- Single model serves all 6+ bots — same weights for IC vs directional
- No per-strategy model specialization (e.g., IC-specific vs directional-specific)
- Strategy recommendation is rule-based (VIX×GEX matrix), not ML-powered
- UNIQUE constraint limits training data collection
- No portfolio-level risk aggregation
- Proverbs intelligence collected but intentionally unused

### 8.6 Recommendations for Orchestration Layer

1. **UNIQUE constraint fix**: Change to `UNIQUE(trade_date, bot_name, prediction_id)` to capture all intraday trades
2. **ANCHOR alignment**: Apply adaptive thresholds and reduced hallucination penalties to match other bots
3. **SOLOMON ML override**: Stop overwriting ML probability with direction confidence — blend instead
4. **Portfolio risk**: Add cross-bot position tracking to prevent correlated losses
5. **Feature monitoring**: Track feature importance drift between training runs
6. **Separate directional model**: Consider training a separate model for SOLOMON/GIDEON with direction-specific features
7. **Replace win_rate_60d**: Use external signal (e.g., cumulative VRP, rolling Sharpe) instead of self-referential metric

---

## APPENDIX A: File References

| File | Lines | Purpose |
|------|-------|---------|
| `quant/prophet_advisor.py` | ~5,700 | ProphetAdvisor class, training, inference, bot advice |
| `backend/api/routes/prophet_routes.py` | ~465 | REST API endpoints |
| `scheduler/trader_scheduler.py` | ~3,500 | Training schedule (midnight + 4 PM CT) |
| `trading/fortress_v2/signals.py` | ~900 | Calls `get_fortress_advice()` |
| `trading/fortress_v2/trader.py` | ~1,400 | Stores predictions, records outcomes |
| `trading/anchor/signals.py` | ~900 | Calls `get_anchor_advice()` |
| `trading/solomon_v2/signals.py` | ~900 | Calls `get_solomon_advice()` |
| `trading/gideon/signals.py` | ~1,000 | Calls `get_solomon_advice(bot_name="GIDEON")` |
| `trading/samson/trader.py` | ~1,300 | Uses Prophet recommendations |
| `trading/valor/trader.py` | ~1,300 | Uses Prophet for strategy decisions |
| `quant/proverbs_enhancements.py` | ~2,100 | Feedback loop integration |

## APPENDIX B: Bot-Prophet Integration Matrix

| Bot | Advice Method | Claude? | VIX Skip? | GEX Walls? | Direction? | Training Outcomes? |
|-----|--------------|---------|-----------|------------|------------|-------------------|
| FORTRESS | `get_fortress_advice()` | ✓ | ✓ | ✓ | N/A (IC) | ✓ |
| ANCHOR | `get_anchor_advice()` | ✓ | ✓ | ✓ | N/A (IC) | ✓ |
| SOLOMON | `get_solomon_advice()` | ✓ | — | ✓ | ✓ (ML/GEX) | ✓ |
| GIDEON | `get_solomon_advice(bot_name="GIDEON")` | ✓ | — | ✓ | ✓ (ML/GEX) | ✓ |
| CORNERSTONE | `get_cornerstone_advice()` | — | — | — | N/A (Wheel) | — |
| LAZARUS | `get_lazarus_advice()` | ✓ | — | — | ✓ (GEX) | — |
| SAMSON | `get_strategy_recommendation()` | — | — | — | N/A (IC) | ✓ |
| VALOR | `get_strategy_recommendation()` | — | — | — | N/A (Futures) | ✓ |

---

*Last Updated: 2026-02-10*
*Prophet V2 fixes implemented and pushed in prior session*
*This audit documents the comprehensive review using the 8-section ML Trading Bot Audit framework*
