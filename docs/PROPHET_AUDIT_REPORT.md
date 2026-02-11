# PROPHET — Forensic ML Trading Bot Audit
## "Oracle is God" — The Sole Trade Authority for AlphaGEX

**Date**: 2026-02-10
**Branch**: `claude/watchtower-data-analysis-6FWPk`
**Auditor**: Claude Code (Orchestration Layer Evaluation)
**File Under Review**: `quant/prophet_advisor.py` — **5,696 lines**
**Lines Read**: Every single line, plus all 9 integration files

---

## EXECUTIVE SUMMARY

Prophet is the single most important file in AlphaGEX. Every dollar traded flows through it. When Prophet says SKIP, six bots sit idle. When Prophet says TRADE_FULL at 10% risk, real money enters the market within seconds. A single miscalibrated probability here doesn't just lose one trade — it systematically biases every bot, every day, compounding into catastrophic P&L drift.

This audit reads every line of Prophet (5,696) plus every signals.py (9 bots), every trader.py (7 bots), the scheduler, the API routes, and the Proverbs feedback loop. It documents every data path, every probability manipulation, every threshold, every bug — with exact line numbers.

**Verdict**: V2 fixes resolved the 5 most critical issues (class imbalance, confidence inflation, post-ML manipulation, look-ahead bias, hardcoded thresholds). But **6 HIGH-severity issues remain open**, including one where SOLOMON silently overwrites the calibrated ML probability on every single prediction.

---

## TABLE OF CONTENTS

1. [Architecture & Signal Chain](#section-1-architecture--signal-chain)
2. [Data Pipeline — Every Byte In](#section-2-data-pipeline--every-byte-in)
3. [Feature Engineering — The 13 Inputs](#section-3-feature-engineering--the-13-inputs)
4. [Model Architecture — The Brain](#section-4-model-architecture--the-brain)
5. [Signal Generation — Every Probability Manipulation](#section-5-signal-generation--every-probability-manipulation)
6. [Bot Integration — Every Consumer](#section-6-bot-integration--every-consumer)
7. [Training Pipeline — The Feedback Loop](#section-7-training-pipeline--the-feedback-loop)
8. [Risk Management — What's Missing](#section-8-risk-management--whats-missing)
9. [Infrastructure & Reliability](#section-9-infrastructure--reliability)
10. [Findings — Severity-Ranked](#section-10-findings--severity-ranked)

---

## SECTION 1: ARCHITECTURE & SIGNAL CHAIN

### 1.1 How Prophet Fits in the Trading Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        EVERY 5 MINUTES (Market Hours)                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  signals.py                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐  │
│  │ WISDOM (XGB)  │────▶│ win_probability   │────▶│ Signal object      │  │
│  │ signals.py:*  │     │ (PRIMARY)         │     │ .oracle_*          │  │
│  └──────────────┘     └──────────────────┘     │ .win_probability   │  │
│                                                  │ .advice            │  │
│  ┌──────────────┐     ┌──────────────────┐     │ .strikes           │  │
│  │ PROPHET (GBC) │────▶│ advice, risk_pct  │────▶│ .risk_pct          │  │
│  │ prophet_adv:* │     │ sd_mult, strikes  │     │ .sd_mult           │  │
│  └──────────────┘     └──────────────────┘     └────────┬───────────┘  │
│                                                           │              │
│  trader.py                                                ▼              │
│  ┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐  │
│  │ Strategy Rec  │────▶│ IC vs Directional │     │ Thompson × Kelly   │  │
│  │ (informational)│     │ (display only)    │     │ Position Sizing    │  │
│  └──────────────┘     └──────────────────┘     └────────┬───────────┘  │
│                                                           │              │
│                                                           ▼              │
│                                                  ┌────────────────────┐  │
│                                                  │ Tradier API        │  │
│                                                  │ Real Money Fills   │  │
│                                                  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Critical Understanding: WISDOM vs Prophet

| Aspect | WISDOM | Prophet |
|--------|--------|---------|
| **File** | `fortress_ml_advisor.py` | `prophet_advisor.py` |
| **Where called** | `signals.py` (PRIMARY) | `signals.py` (bot-specific advice) |
| **Model** | XGBoost | sklearn GradientBoostingClassifier |
| **Question answered** | "Win probability for this trade?" | "Should bot trade? What strikes? What risk %?" |
| **Output** | Single float: win_probability | ProphetPrediction: advice + strikes + risk + confidence |
| **Features** | 13 V3 (same as Prophet) | 13 V3 (same feature set) |
| **Feeds into** | Signal object → trader | Signal object → trader |
| **Feeds each other?** | **NO** | **NO** |

They are **independent models** answering different questions, trained on overlapping but separately extracted data. This is by design — two perspectives on the same market.

### 1.3 Bot Name Mapping

| Bot Enum (Prophet) | Internal Name | Trading Style | Prophet Method Called |
|-----|------|------|------|
| `FORTRESS` | FORTRESS_V2 | SPY 0DTE Iron Condor | `get_fortress_advice()` |
| `ANCHOR` | ANCHOR | SPX Weekly Iron Condor | `get_anchor_advice()` |
| `SOLOMON` | SOLOMON_V2 | SPY Directional Spreads | `get_solomon_advice()` |
| `GIDEON` | GIDEON | Aggressive Directional | `get_solomon_advice(bot_name="GIDEON")` |
| `SAMSON` | SAMSON | Aggressive SPX IC | `get_anchor_advice()` |
| `CORNERSTONE` | CORNERSTONE | SPX Wheel | `get_cornerstone_advice()` |
| `LAZARUS` | LAZARUS | Directional Calls | `get_lazarus_advice()` |
| `JUBILEE` | JUBILEE | Box Spread + IC | `get_anchor_advice()` |
| `SHEPHERD` | SHEPHERD | Manual Wheel | Not called |

---

## SECTION 2: DATA PIPELINE — EVERY BYTE IN

### 2.1 Three Training Data Sources

| # | Source | Table/Method | Line | Quality | Notes |
|---|--------|-------------|------|---------|-------|
| 1 | **Live trade outcomes** | `prophet_training_outcomes` | 5237 | **Best** | Actual fills with features JSON |
| 2 | **Database backtests** | `zero_dte_backtest_trades` | 5571 | Moderate | `expected_move_1d` hardcoded as 1% of spot (line 5616) |
| 3 | **CHRONICLES in-memory** | `extract_features_from_chronicles()` | 4244 | Good | Feature approximations for VRP, win_rate |

### 2.2 Training Data Flow

```
Live outcomes (best)
    ↓ train_from_live_outcomes() [line 5218]
    ↓ Reads prophet_training_outcomes table
    ↓ Converts to DataFrame with V3 features
    ↓ ──────────────────────────────┐
                                     ↓
DB backtests (fallback #1)          GBC.fit(X, y, sample_weight=sw)
    ↓ train_from_database_backtests()  ↓
    ↓ Reads zero_dte_backtest_trades   CalibratedClassifierCV(isotonic)
    ↓ Maps to CHRONICLES format        ↓
    ↓ ──────────────────────────────┤  _save_model() → DB + local file
                                     ↑
CHRONICLES (fallback #2)             │
    ↓ train_from_chronicles()        │
    ↓ extract_features_from_chronicles()
    ↓ ──────────────────────────────┘
```

### 2.3 Prediction Data Flow (Inference)

```
MarketContext (from bot's signals.py)
    ↓ 13 fields → np.array [line 3937-3960]
    ↓ StandardScaler.transform() [line 3992]
    ↓ calibrated_model.predict_proba() [line 3995]
    ↓ win_probability = float(proba[1]) [line 4006]
    ↓
    ├── FORTRESS: + GEX wall strikes + SD multiplier + Claude validation
    ├── ANCHOR: + hardcoded 0.58/0.52/0.48 thresholds (!!!)
    ├── SOLOMON: + ORION ML direction → OVERWRITES win_probability (!!!)
    ├── CORNERSTONE: clean pass-through
    └── LAZARUS: + Claude validation, reduced risk
```

### 2.4 Data Integrity Issues

| Issue | Location | Severity | Detail |
|-------|----------|----------|--------|
| **UNIQUE constraint data loss** | `prophet_training_outcomes` line 4949 | **HIGH** | `UNIQUE(trade_date, bot_name)` means if FORTRESS trades 3x on Monday, only 1 outcome is stored. With 0DTE bots trading every 5 min, this could discard **67%+ of intraday data** |
| **UNIQUE constraint data loss** | `prophet_predictions` line 4661 | **HIGH** | Same `UNIQUE(trade_date, bot_name)` on predictions table |
| **VRP approximation at inference** | Line 3944 | LOW | `volatility_risk_premium = expected_move_pct * 0.2` — constant multiplier, not actual IV - RV. Training uses rolling 5-trade realized vol. Inference/training mismatch |
| **win_rate_30d field name mismatch** | Line 3955 | LOW | Comment says "MarketContext still uses win_rate_30d field for 60d value" — confusing but functional |
| **DB backtest expected_move** | Line 5616 | LOW | Hardcoded `spy_price * 0.01` for expected_move_1d — constant 1% assumption |
| **Connection leak in update_outcome** | Line 4855 | MEDIUM | Uses raw `conn = get_connection()` instead of `with get_db_connection()` context manager (lines 4855, 5003-5004). If exception between lines 4855-5003, connection leaks |
| **Connection leak in analyze_strategy_performance** | Line 2299 | MEDIUM | Same pattern — raw `get_connection()` without context manager |

---

## SECTION 3: FEATURE ENGINEERING — THE 13 INPUTS

### 3.1 Complete Feature Table (V3)

| # | Feature | Type | Range | Source (Training) | Source (Inference) | Risk Assessment |
|---|---------|------|-------|-------------------|-------------------|-----------------|
| 1 | `vix` | Continuous | 10-80 | Trade record | `context.vix` | OK — core volatility signal |
| 2 | `vix_percentile_30d` | Continuous | 0-100 | Rolling rank (line 4375) | `context.vix_percentile_30d` | OK — measures VIX regime relative to history |
| 3 | `vix_change_1d` | Continuous | -50% to +200% | `.pct_change()` (line 4378) | `context.vix_change_1d` | OK — momentum signal |
| 4 | `day_of_week_sin` | Cyclical | -1 to 1 | `sin(2π*dow/5)` (line 4301) | Same (line 3939) | **V3 FIX** — replaces integer day_of_week |
| 5 | `day_of_week_cos` | Cyclical | -1 to 1 | `cos(2π*dow/5)` (line 4302) | Same (line 3940) | **V3 FIX** — Mon≠Fri in feature space now |
| 6 | `price_change_1d` | Continuous | -10% to +10% | **Previous day** (line 4311-4316) | `context.price_change_1d` | **V3 FIX** — was using same-day close (look-ahead) |
| 7 | `expected_move_pct` | Continuous | 0.3-5% | `expected_move_1d / open_price` (line 4319) | `context.expected_move_pct` | OK — IV-implied expected range |
| 8 | `volatility_risk_premium` | Continuous | -2% to +3% | `EM - realized_vol_5d` (line 4339) | **`EM * 0.2` (line 3944)** | **MISMATCH** — training uses rolling calc, inference uses constant multiplier |
| 9 | `win_rate_60d` | Continuous | 0-1 | Rolling 60-trade lookback (line 4290) | `context.win_rate_30d` field (misnamed) | **SELF-REFERENTIAL** — model uses its own past accuracy as input. Creates feedback loop where lucky streaks → higher confidence → more trades → more data |
| 10 | `gex_normalized` | Continuous | -1e-4 to 1e-4 | Trade record (line 4360) | `context.gex_normalized` | OK — dealer hedging signal |
| 11 | `gex_regime_positive` | Binary | 0/1 | `1 if POSITIVE` (line 4361) | Same (line 3933) | OK — pinning vs trending |
| 12 | `gex_distance_to_flip_pct` | Continuous | -10% to +10% | Trade record (line 4362) | `context.gex_distance_to_flip_pct` | OK — regime stability |
| 13 | `gex_between_walls` | Binary | 0/1 | Trade record (line 4363) | Same (line 3934) | OK — containment flag |

### 3.2 Missing Features That Options Traders Would Expect

| Missing Feature | Why It Matters | Difficulty to Add |
|----------------|---------------|-------------------|
| **IV Rank / IV Percentile** | Core options pricing signal — tells you if premium is rich or cheap | MEDIUM — need IV data source |
| **Term structure slope** | VIX contango/backwardation predicts regime changes | MEDIUM — need VIX futures |
| **Put/Call volume ratio** | Sentiment signal, complements GEX | LOW — available from Tradier |
| **Time to expiration (DTE)** | Critical for theta decay timing — 0DTE vs 7DTE behave completely differently | LOW — already in MarketContext.days_to_opex but NOT in features |
| **Realized vol (actual)** | Currently approximated. Actual 5/10/20 day HV is cheap to compute | LOW |
| **FOMC/CPI/NFP flag** | Event risk dramatically changes IC win rate. CLAUDE.md says this exists but it doesn't | MEDIUM — need economic calendar API |
| **Intraday time (hour)** | Proverbs collects time-of-day data showing certain hours lose money, but Prophet ignores it | LOW — just add hour_sin/cos |
| **Spread width** | ANCHOR uses $10 spreads, SAMSON uses $12 — wider spreads have different risk profiles | LOW — pass as feature |

### 3.3 Feature Version Compatibility

| Version | Features | Feature Count | How Detected |
|---------|----------|---------------|--------------|
| V1 | No GEX | 7 | `_has_gex_features == False` |
| V2 | + GEX, integer day, win_rate_30d | 11 | `_feature_version < 3` |
| V3 | + cyclical day, VRP, win_rate_60d | 13 | `_feature_version >= 3` |

Backward compat: `_get_base_prediction()` (lines 3924-4016) branches on version at inference time. Model trained with V2 features will use V2 columns even if V3 code is deployed. **This is correct.**

---

## SECTION 4: MODEL ARCHITECTURE — THE BRAIN

### 4.1 Model Configuration

```python
# Line 4441-4449
GradientBoostingClassifier(
    n_estimators=150,      # 150 boosting rounds
    max_depth=4,           # 4-level trees (moderate complexity)
    learning_rate=0.1,     # Standard learning rate
    min_samples_split=20,  # Regularization: need 20 samples to split
    min_samples_leaf=10,   # Regularization: minimum 10 samples per leaf
    subsample=0.8,         # 80% row sampling (stochastic GBM)
    random_state=42        # Reproducible
)
```

**Assessment**: Conservative config suitable for small-to-medium datasets (100-1000 trades). `max_depth=4` with `min_samples_leaf=10` prevents overfitting on noisy financial data. `subsample=0.8` adds regularization. **This is well-tuned.**

### 4.2 Class Imbalance Handling (V2 Fix)

```python
# Lines 4420-4430
n_wins = int(y.sum())
n_losses = int(len(y) - n_wins)
weight_win = n_losses / len(y)      # e.g., 0.11 for 89% win rate
weight_loss = n_wins / len(y)       # e.g., 0.89 for 89% win rate
sample_weight_array = np.where(y == 1, weight_win, weight_loss)
```

**Assessment**: Correct inverse-frequency weighting. With 89% win rate, losses get 8x the weight of wins. This forces the model to learn what distinguishes the rare 11% of losses from the 89% of wins. **Critical V2 fix.**

Note: sklearn GBC uses `sample_weight` parameter in `.fit()`, not `scale_pos_weight` like XGBoost. The implementation is correct for this model type.

### 4.3 Calibration

```python
# Lines 4475-4477
self.calibrated_model = CalibratedClassifierCV(self.model, method='isotonic', cv=3)
self.calibrated_model.fit(X_scaled, y)
```

**Assessment**: Isotonic calibration on full dataset with 3-fold CV. This ensures `predict_proba(X)` returns actual probabilities, not just scores. **Critical for threshold-based decisions.**

**Concern**: Calibration is on the FULL dataset (train + test), not held-out only. For the Brier score calculation this is fine (done on CV folds), but the final calibrated model has seen all data during calibration. With isotonic regression, this could overfit calibration to the specific dataset. Consider calibrating on the last CV fold only.

### 4.4 Cross-Validation

```python
# Line 4439
tscv = TimeSeriesSplit(n_splits=5)
```

**Assessment**: `TimeSeriesSplit` respects temporal ordering — train on past, test on future. 5 splits gives reasonable fold sizes. **Correct for financial data.**

### 4.5 Evaluation Metrics

| Metric | Computed On | Line | Notes |
|--------|-----------|------|-------|
| Accuracy | CV folds | 4462 | OK |
| Precision | CV folds | 4463 | OK |
| Recall | CV folds | 4464 | OK |
| F1 | CV folds | 4465 | OK |
| AUC-ROC | CV folds | 4468 | OK |
| **Brier Score** | **CV folds** | 4466 | **V2 FIX** — was in-sample before |

### 4.6 Adaptive Thresholds (V2 Fix)

```python
# Lines 1490-1494
self.low_confidence_threshold = self._base_rate - 0.15   # SKIP below this
self.high_confidence_threshold = self._base_rate - 0.05   # TRADE_FULL above this
```

With 89% base rate:
- SKIP: < 0.74
- TRADE_REDUCED: 0.74 – 0.84
- TRADE_FULL: >= 0.84

**Assessment**: Correct approach — thresholds move with the data. When base rate is high, SKIP fires only when the model is significantly less confident than average. **Replaces broken hardcoded 0.45/0.65.**

---

## SECTION 5: SIGNAL GENERATION — EVERY PROBABILITY MANIPULATION

This is the most critical section. Prophet has **5 bot-specific advice methods**, and each one manipulates the ML probability differently. I trace every single manipulation with exact line numbers.

### 5.1 FORTRESS (`get_fortress_advice`, lines 2437-2859)

```
_get_base_prediction() → win_probability (calibrated)
    ↓
Claude validation (if enabled):
    └── ADJUST/OVERRIDE: win_prob += confidence_adjustment [-0.10, +0.10]
        Clamped to [0.40, 0.85] (line 2762)
    └── Hallucination HIGH: win_prob -= 0.05, floor 0.50 (line 2776)
    └── Hallucination MEDIUM: win_prob -= 0.02, floor 0.50 (line 2784)
    ↓
_get_advice_from_probability(win_prob) → TRADE_FULL / TRADE_REDUCED / SKIP
    ↓
SD multiplier: 1.2 (high conf) / 1.3 (medium) / 1.4 (low) (lines 2796-2801)
    ↓
confidence = win_probability (V2: removed 1.2x inflation, line 2807)
```

**Post-ML manipulations**: Only Claude validation (optional, ±0.10 max)
**Verdict**: **CLEAN** — V2 removed all post-ML probability manipulation

### 5.2 ANCHOR (`get_anchor_advice`, lines 3529-3918)

```
_get_base_prediction() → win_probability (calibrated)
    ↓
!!! HARDCODED THRESHOLDS (lines 3783-3798) !!!
    if win_prob >= 0.58: TRADE_FULL, risk 3%
    elif win_prob >= 0.52: TRADE_REDUCED, risk 1.5%
    elif win_prob >= 0.48: TRADE_REDUCED, risk 1%
    else: SKIP, risk 0%
    ↓
Claude validation (if enabled):
    └── confidence_adjustment applied to win_prob (line 3846)
        Clamped to [0.05, 0.95] (!!!) — much wider range than FORTRESS
    └── Hallucination HIGH: win_prob -= 0.10 (line 3851) (!!!)
    └── Hallucination MEDIUM: win_prob -= 0.05 (line 3856) (!!!)
    ↓
confidence = 0.5 + abs(win_prob - 0.5) * 2 (line 3867)
    — Custom formula, NOT calibrated probability
```

**CRITICAL ISSUES**:
1. **Lines 3783-3798**: Hardcoded `0.58/0.52/0.48` thresholds — does NOT use `_get_advice_from_probability()` with adaptive thresholds. With 89% base rate and adaptive thresholds at 0.74/0.84, ANCHOR's 0.58 threshold means it trades on predictions that the adaptive system would SKIP.
2. **Lines 3851-3858**: Hallucination penalties are 0.10/0.05 (original values) while FORTRESS/LAZARUS/SOLOMON use reduced 0.05/0.02. ANCHOR is 2-5x more penalized by Claude hallucinations.
3. **Line 3846**: Claude adjustment clamped to [0.05, 0.95] — FORTRESS clamps to [0.40, 0.85]. ANCHOR allows probability to drop to 5% (extreme) or rise to 95% (overconfident).
4. **Line 3867**: Confidence computed from custom formula, not from calibrated model.

### 5.3 SOLOMON (`get_solomon_advice`, lines 3082-3523)

```
_get_base_prediction() → win_probability (calibrated)
    ↓
ML Direction from ORION (lines 3187-3219):
    GEXSignalIntegration.get_combined_signal() → direction, direction_confidence
    ↓
!!! LINE 3338: win_probability OVERWRITTEN !!!
    base_pred['win_probability'] = max(0.50, min(0.85, direction_confidence))
    ↓
Wall filter boost: +0.10 if wall_filter_passed (line 3342)
Trend boost: +0.05 if trend_strength > 0.6 (line 3346)
    ↓
Flip distance filter:
    >5%: win_prob -= 0.15 (line 3395)
    3-5%: win_prob -= 0.08 (line 3401)
    ↓
Friday filter: win_prob -= 0.05 (line 3418)
    ↓
Claude validation (if enabled):
    └── Same ±0.10 adjustment pattern
    └── Hallucination penalties: 0.05/0.02 (reduced)
    ↓
_get_advice_from_probability(win_prob) → TRADE/SKIP
    ↓
Friday: TRADE_FULL → TRADE_REDUCED forced (line 3427)
Flip >3%: TRADE_FULL → TRADE_REDUCED forced (line 3432)
    ↓
confidence = direction_confidence (NOT win_probability, line 3463)
```

**CRITICAL ISSUE — LINE 3338**: The calibrated ML probability from `_get_base_prediction()` is **completely discarded**. It's replaced with `direction_confidence` from ORION's `GEXSignalIntegration`. This means:
- Prophet's GBC model outputs a calibrated 0.87 probability
- ORION says direction confidence is 0.62
- Prophet stores 0.62 as win_probability
- All downstream threshold logic operates on 0.62, not 0.87
- The GBC model is **irrelevant** for SOLOMON/GIDEON

This is not a minor bug — it means Prophet's entire ML pipeline (training, calibration, feature engineering) does NOTHING for directional bots. They're trading on ORION's direction confidence alone.

### 5.4 CORNERSTONE (`get_cornerstone_advice`, lines 2861-2950)

```
_get_base_prediction() → win_probability (calibrated)
    ↓ (no manipulation)
_get_advice_from_probability() → TRADE/SKIP
    ↓
confidence = win_probability (V2: removed 1.2x inflation, line 2923)
```

**Verdict**: **CLEANEST** — pure model output, no post-ML manipulation

### 5.5 LAZARUS (`get_lazarus_advice`, lines 2952-3080)

```
_get_base_prediction() → win_probability (calibrated)
    ↓
Claude validation (if enabled):
    └── Same ±0.10 adjustment, clamped [0.45, 0.80]
    └── Hallucination penalties: 0.05/0.02 (reduced)
    ↓
_get_advice_from_probability() → TRADE/SKIP
    ↓
risk_pct = risk * 0.5 (line 3048) — halved for directional risk
confidence = win_probability (V2: removed 1.2x inflation, line 3047)
```

**Verdict**: **CLEAN** — only Claude validation (optional)

### 5.6 Summary: Which Bots Use Adaptive Thresholds?

| Bot | Method | Uses `_get_advice_from_probability()`? | Thresholds |
|-----|--------|--------------------------------------|------------|
| **FORTRESS** | `get_fortress_advice` | **YES** (line 2789) | Adaptive ✓ |
| **ANCHOR** | `get_anchor_advice` | **NO** (lines 3783-3798) | Hardcoded 0.58/0.52/0.48 |
| **SOLOMON** | `get_solomon_advice` | **YES** (line 3423) | Adaptive, but input is ORION confidence, not GBC output |
| **GIDEON** | `get_solomon_advice` | **YES** | Same as SOLOMON |
| **CORNERSTONE** | `get_cornerstone_advice` | **YES** (line 2917) | Adaptive ✓ |
| **LAZARUS** | `get_lazarus_advice` | **YES** (line 3041) | Adaptive ✓ |
| **SAMSON** | Uses `get_anchor_advice` | **NO** | Same hardcoded as ANCHOR |
| **JUBILEE** | Uses `get_anchor_advice` | **NO** | Same hardcoded as ANCHOR |

**3 bots (ANCHOR, SAMSON, JUBILEE) use hardcoded thresholds that bypass the V2 adaptive fix entirely.**

---

## SECTION 6: BOT INTEGRATION — EVERY CONSUMER

### 6.1 Which Methods Each Bot Calls

| Bot | signals.py Call | trader.py Calls | Claude Enabled | store_prediction | update_outcome |
|-----|----------------|-----------------|----------------|-----------------|----------------|
| FORTRESS_V2 | `get_fortress_advice()` | `store_prediction()`, `update_outcome()`, `get_strategy_recommendation()` | YES | YES (line 1159) | YES (line 925) |
| ANCHOR | `get_anchor_advice()` | `store_prediction()`, `update_outcome()`, `get_strategy_recommendation()` | YES | YES (line 803) | YES (line 586) |
| SOLOMON_V2 | `get_solomon_advice()` | `store_prediction()`, `update_outcome()` | YES | YES (line 698) | YES (line 463) |
| GIDEON | `get_solomon_advice(bot_name="GIDEON")` | `store_prediction()`, `update_outcome()` | YES | YES (line 675) | YES (line 463) |
| SAMSON | `get_anchor_advice()` | `store_prediction()`, `update_outcome()` | YES | YES | YES (line 506) |
| JUBILEE | `get_anchor_advice()` | Not found in trader.py | **NO** (speed) | ? | ? |
| VALOR | **NOT USED in signals** | Import exists | N/A | ? | ? |
| AGAPE | `get_strategy_recommendation()` only | N/A | NO | NO | NO |
| AGAPE_SPOT | `get_strategy_recommendation()` only | N/A | NO | NO | NO |

### 6.2 Post-Prophet Manipulation in signals.py

| Bot | Manipulation | Lines | Severity |
|-----|-------------|-------|----------|
| FORTRESS_V2 | None | — | Clean |
| ANCHOR | Confidence boosting on `advice == 'ENTER'` when confidence > 0.6 | signals.py:945-949 | LOW |
| SOLOMON_V2 | Confidence boost/penalty based on direction match | signals.py:863-873 | MEDIUM |
| GIDEON | Same as SOLOMON | — | MEDIUM |
| SAMSON | Confidence boosting based on advice | signals.py:894-898 | LOW |
| AGAPE/AGAPE_SPOT | Maps `dir_suitability` → `win_probability` | signals.py:322 | LOW (different asset class) |

### 6.3 prediction_id Tracking (Feedback Loop)

All IC and directional bots properly implement the Migration 023 feedback loop:
1. `store_prediction()` returns `prediction_id` (with RETURNING clause, line 4741)
2. `prediction_id` stored in bot's `{bot}_positions` table via `db.update_oracle_prediction_id()`
3. On position close, `prediction_id` retrieved from DB and passed to `update_outcome()`
4. Directional bots (SOLOMON, GIDEON) additionally track `direction_predicted` and `direction_correct`

**This is well-implemented.** The one concern is the `UNIQUE(trade_date, bot_name)` constraint — see Section 2.4.

---

## SECTION 7: TRAINING PIPELINE — THE FEEDBACK LOOP

### 7.1 Training Schedule

| Trigger | Time | Function | Threshold | File:Line |
|---------|------|----------|-----------|-----------|
| **Daily scheduled** | 00:00 CT (midnight) | `prophet_auto_train(threshold_outcomes=10)` | 10 outcomes | trader_scheduler.py:4628 |
| **PROVERBS feedback loop** | 16:00 CT (4 PM) | `prophet_auto_train(threshold_outcomes=10)` | 10 outcomes | trader_scheduler.py:2821 |
| **Manual API** | On demand | `auto_train(threshold=20)` | 20 outcomes | prophet_routes.py:357 |

### 7.2 Training Data Cascade

```python
# auto_train() at line 5437
if pending_count >= 20:
    1. Try train_from_live_outcomes(min_samples=20)
if that fails:
    2. Try train_from_database_backtests(min_samples=100)
if that fails:
    3. Try CHRONICLES in-memory backtester
```

### 7.3 Model Persistence

```
Training complete
    ↓
_save_model() [line 1928]
    ├── _save_model_to_db() → prophet_trained_models table (BYTEA pickle)
    └── Local .pkl file (backup)
```

**On startup**:
```
__init__() → _load_model() [line 1812]
    ├── _load_model_from_db() [line 1851] → primary (survives Render redeploys)
    └── Local .pkl file → fallback
```

### 7.4 Model Staleness Detection

```python
# Every prediction call:
_check_and_reload_model_if_stale() [line 1755]
    ├── Throttled to every 5 minutes (line 1769)
    ├── Checks prophet_trained_models.is_active for newer version
    └── Auto-reloads if DB version != memory version
```

**Assessment**: Good design — models auto-refresh without restarts. 5-minute poll is reasonable.

### 7.5 Calibration Retraining Issue

The isotonic calibration is fit on the FULL dataset (line 4476-4477), not on held-out data. With `CalibratedClassifierCV(cv=3)`, sklearn does internal 3-fold calibration, which is fine. But the base GBC model has already been fitted on the full data (line 4473), so the calibrator is calibrating a model that has seen all the data. This is standard practice but worth noting — held-out calibration would be more conservative.

---

## SECTION 8: RISK MANAGEMENT — WHAT'S MISSING

### 8.1 What Prophet Controls

| Risk Factor | Implementation | Line |
|------------|---------------|------|
| **Trade/Skip decision** | Via win_probability thresholds | Varies per bot |
| **Position sizing** | `suggested_risk_pct` (3-10%) | Per bot method |
| **Strike selection** | GEX walls ± buffer, 1 SD minimum | FORTRESS: 2632, ANCHOR: 3820 |
| **SD multiplier** | 1.2/1.3/1.4 based on confidence | FORTRESS: 2796-2801 |
| **VIX hard skip** | Configurable per bot | FORTRESS: 2494, ANCHOR: 3586 |
| **Friday filter** | -5% probability + forced TRADE_REDUCED | SOLOMON: 3418 |
| **Flip distance filter** | >3% reduced, >5% high risk | SOLOMON: 3393 |

### 8.2 What Prophet Does NOT Control (Gaps)

| Gap | Risk | Impact |
|-----|------|--------|
| **No portfolio-level risk** | 6 bots can open positions simultaneously with no cross-bot coordination | If all 6 enter IC on same day and VIX spikes, cumulative loss could be 6x single-bot max |
| **No max daily loss limit** | Individual bots have no daily P&L stop. "Always allow trading" (CLAUDE.md) | A losing streak compounds without brake |
| **No correlation awareness** | FORTRESS (SPY IC) and ANCHOR (SPX IC) trade correlated underlyings | Both breach on same market move — doubles the loss |
| **No event risk detection** | FOMC, CPI, NFP not detected despite CLAUDE.md claiming it | IC win rate drops dramatically on event days |
| **No intraday drawdown limit** | No concept of "stop trading if today's loss exceeds X" | Bots keep entering new positions while bleeding |
| **No position count limit** | Multiple concurrent 0DTE positions possible | Each additional position adds gamma risk |
| **Proverbs data unused** | Proverbs collects time-of-day, regime, correlation data — all display-only (lines 2145-2209) | Rich risk data collected but never acted on |

### 8.3 VIX Skip Rules Configuration

| Bot | VIX Hard Skip | Mon/Fri Skip | Streak Skip | OMEGA Override |
|-----|--------------|-------------|-------------|----------------|
| FORTRESS_V2 | **0.0 (disabled)** | 0.0 (disabled) | 0.0 (disabled) | Supported |
| ANCHOR | **0.0 (disabled)** | 0.0 (disabled) | 0.0 (disabled) | Not used |
| SAMSON | **0.0 (disabled)** | 0.0 (disabled) | 0.0 (disabled) | Not used |
| JUBILEE | **0.0 (disabled)** | 0.0 (disabled) | 0.0 (disabled) | Not used |

**All VIX skip rules are disabled in production** — every IC bot passes `vix_hard_skip=0.0`. The skip logic (lines 2492-2563, 3582-3649) exists but is dead code in practice.

---

## SECTION 9: INFRASTRUCTURE & RELIABILITY

### 9.1 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/prophet/health` | GET | Model staleness, freshness |
| `/api/prophet/status` | GET | Training metrics, version |
| `/api/prophet/strategy-recommendation` | POST | Manual context → IC vs Directional |
| `/api/prophet/strategy-recommendation` | GET | Live data → IC vs Directional |
| `/api/prophet/strategy-performance` | GET | Historical IC vs Directional by regime |
| `/api/prophet/train` | POST | Trigger training (force or threshold) |
| `/api/prophet/pending-outcomes` | GET | Ready-for-training check |
| `/api/prophet/vix-regimes` | GET | VIX regime definitions |

### 9.2 Thread Safety

| Component | Thread-Safe? | Mechanism |
|-----------|-------------|-----------|
| `ProphetAdvisor` singleton | YES | `threading.Lock()` double-check locking (lines 5018-5029) |
| `ProphetLiveLog` singleton | YES | `threading.Lock()` + `_log_lock` (lines 482-497) |
| `GEXSignalIntegration` global | **NO** — global `_gex_signal_integration` (line 3189) | No lock on lazy init |
| Model reload | YES | Version check throttled (line 1769) |
| DB connections | YES | Context manager or per-call (varies) |

### 9.3 Failure Modes

| Failure | Behavior | Severity |
|---------|----------|----------|
| ML libraries unavailable | `_fallback_prediction()` — rule-based (line 4018) | LOW — graceful degradation |
| Database unavailable | Model not loaded, predictions still work if local .pkl exists | MEDIUM |
| Claude API down | `recommendation="AGREE"`, no adjustment (line 770-776) | LOW — graceful |
| ORION models not trained | SOLOMON falls through to GEX-based direction (lines 3222-3314) | MEDIUM |
| Scaler not fit | Exception on `transform()` — caught by caller | LOW |
| All training data sources fail | `auto_train()` returns `success=False` (line 5544) | MEDIUM — stale model |

---

## SECTION 10: FINDINGS — SEVERITY-RANKED

### CRITICAL (Fixed in V2)

| ID | Issue | Fix | Line |
|----|-------|-----|------|
| C1 | 89% win rate class imbalance — model couldn't distinguish losses | `sample_weight` inverse-frequency weighting | 4420-4430 |
| C2 | 1.2x confidence inflation — `confidence = win_prob * 1.2` destroyed calibration | `confidence = win_probability` | 2807 |
| C3 | Post-ML probability manipulation — +3%/+5% GEX adjustments double-counted features | Removed from all 4 bot advice methods | Throughout |
| C4 | Hardcoded 0.45/0.65 thresholds with 89% base rate — SKIP never fired, FULL always fired | Adaptive thresholds: base_rate ± offsets | 1478-1498 |
| C5 | price_change_1d look-ahead — training used same-day close | Now uses previous-day move | 4308-4316 |

### HIGH (Open)

| ID | Issue | Location | Impact | Fix |
|----|-------|----------|--------|-----|
| **H1** | **UNIQUE(trade_date, bot_name) data loss** | Lines 4661, 4949 | Discards 67%+ of intraday trades for 0DTE bots. FORTRESS can trade every 5 min — only first trade's prediction/outcome is stored per day | Change to `UNIQUE(trade_date, bot_name, prediction_time)` or add `position_id` to unique constraint |
| **H2** | **ANCHOR hardcoded thresholds** | Lines 3783-3798 | ANCHOR, SAMSON, JUBILEE all bypass adaptive thresholds. With 89% base rate, ANCHOR trades at 0.58 (model sees this as low confidence) while adaptive would require 0.84 | Replace with `_get_advice_from_probability()` call |
| **H3** | **SOLOMON overwrites ML probability** | Line 3338 | Calibrated GBC probability completely discarded, replaced with ORION direction_confidence. Prophet's GBC model is irrelevant for SOLOMON/GIDEON trades | Keep GBC probability for win_probability, use direction_confidence only for direction selection |
| **H4** | **ANCHOR hallucination penalties 2-5x higher** | Lines 3851-3858 | ANCHOR: 10%/5% penalty. FORTRESS/SOLOMON: 5%/2%. Same Claude API, different punishment. Inconsistent behavior for same market conditions | Standardize to 5%/2% across all bots |
| **H5** | **No portfolio-level risk coordination** | Missing entirely | 6 bots can open 6 correlated positions simultaneously. On a VIX spike, all 6 lose. No cross-bot position limit, no cumulative risk check | Add portfolio risk module that checks total open exposure before each trade |
| **H6** | **VRP inference/training mismatch** | Line 3944 vs 4332-4339 | Training computes VRP from 5-trade rolling realized vol. Inference uses `expected_move_pct * 0.2` (constant). Model trained on one distribution, predicts with another | Compute actual realized vol at inference or match the approximation in training |

### MEDIUM (Open)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| M1 | Connection leaks in `update_outcome()` and `analyze_strategy_performance()` | Lines 2299, 4855 | Use raw `get_connection()` without context manager. Exception between open and close leaks connection |
| M2 | win_rate_60d is self-referential | Feature #9 | Creates positive feedback loop: win streak → higher confidence → more trades → more data skewed toward wins |
| M3 | Global `_gex_signal_integration` not thread-safe | Line 3189 | Lazy init without lock — race condition on first SOLOMON/GIDEON prediction |
| M4 | Proverbs data collected but unused | Lines 2145-2209 | Time-of-day, regime, correlation data all collected but explicitly marked "DISPLAY ONLY — no score adjustment" |
| M5 | Event risk (FOMC/CPI/NFP) not implemented | Missing | CLAUDE.md claims it exists. IC win rates drop on event days but Prophet can't detect them |
| M6 | DTE not a feature | Missing from FEATURE_COLS | 0DTE and 7DTE options have completely different risk profiles but Prophet treats them identically |

### LOW (Open)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| L1 | `days_to_opex` in MarketContext but not in feature vector | Line 257 | Data available but unused by model |
| L2 | win_rate_30d field name used for 60d value | Line 3955, comment | Confusing but functional |
| L3 | DB backtest expected_move hardcoded as 1% | Line 5616 | Only affects DB backtest training source |
| L4 | VALOR doesn't use Prophet in signals | signals.py | Missing integration — uses internal ML |
| L5 | JUBILEE disables Claude validation for speed | signals.py:1228 | Loses validation layer, minor for IC bots |

### QUICK WINS (Can Fix Today)

1. **H2 (ANCHOR thresholds)**: Replace lines 3783-3798 with `advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])`. Add SPX-specific risk_pct scaling after. ~10 lines changed.

2. **H4 (Hallucination penalties)**: Change lines 3851/3856 from `0.10`/`0.05` to `0.05`/`0.02`. 2 lines.

3. **M1 (Connection leaks)**: Replace `conn = get_connection()` with `with get_db_connection() as conn:` in `update_outcome()` and `analyze_strategy_performance()`. ~20 lines.

4. **M3 (Thread safety)**: Add `threading.Lock()` around `_gex_signal_integration` lazy init at line 3189.

---

## APPENDIX A: FILE REFERENCE

| File | Lines | Role |
|------|-------|------|
| `quant/prophet_advisor.py` | 5,696 | Prophet core — model, training, bot advice |
| `trading/fortress_v2/signals.py` | ~800 | FORTRESS signal generation, calls `get_fortress_advice()` |
| `trading/fortress_v2/trader.py` | ~1200 | FORTRESS execution, calls `store_prediction()`, `update_outcome()` |
| `trading/anchor/signals.py` | ~950 | ANCHOR signal generation, calls `get_anchor_advice()` |
| `trading/anchor/trader.py` | ~850 | ANCHOR execution, calls `store_prediction()`, `update_outcome()` |
| `trading/solomon_v2/signals.py` | ~900 | SOLOMON signal generation, calls `get_solomon_advice()` |
| `trading/solomon_v2/trader.py` | ~750 | SOLOMON execution, calls `store_prediction()`, `update_outcome()` |
| `trading/gideon/signals.py` | ~900 | GIDEON signal generation, calls `get_solomon_advice(bot_name="GIDEON")` |
| `trading/gideon/trader.py` | ~700 | GIDEON execution |
| `trading/samson/signals.py` | ~900 | SAMSON signal generation, calls `get_anchor_advice()` |
| `trading/samson/trader.py` | ~700 | SAMSON execution |
| `trading/jubilee/signals.py` | ~1300 | JUBILEE IC signal generation, calls `get_anchor_advice()` |
| `scheduler/trader_scheduler.py` | ~4700 | Training schedule: midnight CT + 4PM CT |
| `backend/api/routes/prophet_routes.py` | 464 | 8 API endpoints |
| `quant/proverbs_enhancements.py` | 3,105 | Feedback loop — measures Prophet accuracy, triggers training |

## APPENDIX B: FEATURE VERSION MIGRATION PATH

```
V1 (7 features)                    V2 (11 features)                   V3 (13 features)
├─ vix                             ├─ vix                             ├─ vix
├─ vix_percentile_30d              ├─ vix_percentile_30d              ├─ vix_percentile_30d
├─ vix_change_1d                   ├─ vix_change_1d                   ├─ vix_change_1d
├─ day_of_week (int)               ├─ day_of_week (int)               ├─ day_of_week_sin (cyclical)
│                                  │                                  ├─ day_of_week_cos (cyclical)
├─ price_change_1d (same-day!)     ├─ price_change_1d (same-day!)     ├─ price_change_1d (PREV day)
├─ expected_move_pct               ├─ expected_move_pct               ├─ expected_move_pct
├─ win_rate_30d                    ├─ win_rate_30d                    ├─ volatility_risk_premium (NEW)
│                                  │                                  ├─ win_rate_60d (longer horizon)
│                                  ├─ gex_normalized                  ├─ gex_normalized
│                                  ├─ gex_regime_positive             ├─ gex_regime_positive
│                                  ├─ gex_distance_to_flip_pct        ├─ gex_distance_to_flip_pct
│                                  └─ gex_between_walls               └─ gex_between_walls
```

## APPENDIX C: PROBABILITY MANIPULATION SUMMARY

Every single point where win_probability is modified after the ML model outputs it:

| Location | Bot(s) | Manipulation | Magnitude | Notes |
|----------|--------|-------------|-----------|-------|
| Line 2762 | FORTRESS | Claude ADJUST/OVERRIDE | ±0.10 | Clamped [0.40, 0.85] |
| Line 2776 | FORTRESS | Claude hallucination HIGH | -0.05 | Floor 0.50 |
| Line 2784 | FORTRESS | Claude hallucination MEDIUM | -0.02 | Floor 0.50 |
| Line 3023 | LAZARUS | Claude ADJUST/OVERRIDE | ±0.10 | Clamped [0.45, 0.80] |
| Line 3031 | LAZARUS | Claude hallucination HIGH | -0.05 | Floor 0.45 |
| Line 3037 | LAZARUS | Claude hallucination MEDIUM | -0.02 | Floor 0.45 |
| **Line 3338** | **SOLOMON/GIDEON** | **OVERWRITE with direction_confidence** | **Full replacement** | **ML probability discarded** |
| Line 3342 | SOLOMON/GIDEON | Wall filter passed | +0.10 | Cap 0.90 |
| Line 3346 | SOLOMON/GIDEON | Strong trend | +0.05 | Cap 0.90 |
| Line 3365 | SOLOMON/GIDEON | Claude ADJUST/OVERRIDE | ±0.10 | Clamped [0.45, 0.85] |
| Line 3374 | SOLOMON/GIDEON | Claude hallucination HIGH | -0.05 | Floor 0.45 |
| Line 3379 | SOLOMON/GIDEON | Claude hallucination MEDIUM | -0.02 | Floor 0.45 |
| Line 3395 | SOLOMON/GIDEON | Flip distance >5% | -0.15 | Floor 0.35 |
| Line 3401 | SOLOMON/GIDEON | Flip distance 3-5% | -0.08 | Floor 0.40 |
| Line 3418 | SOLOMON/GIDEON | Friday filter | -0.05 | Floor 0.40 |
| Line 3846 | ANCHOR/SAMSON/JUBILEE | Claude confidence_adjustment | ±0.10 | Clamped [0.05, 0.95] (!!) |
| Line 3851 | ANCHOR/SAMSON/JUBILEE | Claude hallucination HIGH | **-0.10** | Floor 0.05 (!!) |
| Line 3856 | ANCHOR/SAMSON/JUBILEE | Claude hallucination MEDIUM | **-0.05** | Floor 0.05 (!!) |

---

*Audit complete. Every line of Prophet read. Every integration point documented. Every probability manipulation traced.*
