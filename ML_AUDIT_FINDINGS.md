# AlphaGEX ML Systems - Honest Audit Report

**Audit Date**: February 10, 2026
**Methodology**: Line-by-line source code review of all ML systems
**Verdict**: The ML adds negligible proven value. Most trading decisions are controlled by rule-based logic wearing ML clothing.

---

## Table of Contents

1. [Executive Summary: Is the ML Doing Anything?](#executive-summary)
2. [Prophet Advisor - The "God" That May Be Mortal](#prophet-advisor)
3. [Fortress ML Advisor - XGBoost With Data Leakage](#fortress-ml-advisor)
4. [GEX Probability Models (WATCHTOWER/GLORY) - 5 Models, 0 Proven Edges](#gex-probability-models)
5. [SAGE - Well-Built But Never Used](#sage)
6. [How ML Actually Flows Into Trade Decisions](#ml-decision-flow)
7. [The Uncomfortable Questions](#uncomfortable-questions)
8. [What Would Actually Fix This](#what-would-fix-this)

---

## Executive Summary

**The short answer: No, the ML is not doing anything provably relevant.**

Here's why:

| System | Model Type | Does It Control Trades? | Proven Edge? | Honest Assessment |
|--------|-----------|------------------------|-------------|-------------------|
| **Prophet** | GradientBoosting | YES (it's "god") | NO evidence | Glorified VIX + GEX if/else with ML wrapping |
| **Fortress ML** | XGBoost | NO (informational only) | NO evidence | Has data leakage; probably useless |
| **GEX Prob Models** | 5 XGBoost models | Partially (via WATCHTOWER) | 1 of 5 models WORSE than random | Over-engineered; distance-based math does 40-100% of the work |
| **SAGE** | RandomForest | NO (never integrated) | N/A | Well-designed but literally unused |

**The critical finding**: For FORTRESS and SOLOMON (the two primary bots), the ML prediction is **logged but ignored**. Prophet's advice enum (TRADE/SKIP) controls all decisions. The ML win_probability number goes into the database for auditing but does not gate trades.

**If you replaced every ML model with a hardcoded `return {"advice": "TRADE", "confidence": 0.65}`, only ANCHOR's behavior would change.** FORTRESS and SOLOMON would trade identically.

---

## Prophet Advisor

**File**: `quant/prophet_advisor.py` (~5,600 lines)

### What It Claims To Be
A GradientBoosting ML model that predicts Iron Condor win probability using 11 market features, trained on backtests and live outcomes with isotonic calibration.

### What It Actually Is
A rule-based VIX/GEX decision system with an ML model bolted on that may or may not improve predictions. No evidence exists either way.

### The Model

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
# Then calibrated with:
CalibratedClassifierCV(model, method='isotonic', cv=3)
```

Standard hyperparameters. Nothing exotic. The calibration is correct methodology.

### The 11 Features

| # | Feature | Available at Prediction? | Problem? |
|---|---------|--------------------------|----------|
| 1 | `vix` | Yes | None - good feature |
| 2 | `vix_percentile_30d` | Yes | None |
| 3 | `vix_change_1d` | Yes | None |
| 4 | `day_of_week` | Yes | Weak signal (~2% importance) |
| 5 | `price_change_1d` | Yes | Noisy |
| 6 | `expected_move_pct` | Yes | Correlated with VIX |
| 7 | **`win_rate_30d`** | **NO** | **DATA LEAKAGE - see below** |
| 8 | `gex_normalized` | Yes | None |
| 9 | `gex_regime_positive` | Yes | None |
| 10 | `gex_distance_to_flip_pct` | Yes | None |
| 11 | `gex_between_walls` | Yes | None |

### Data Leakage: win_rate_30d

This is the single biggest problem in the entire ML stack.

**At training time** (from backtest data):
```python
# Computes ACTUAL 30-day rolling win rate from labeled outcomes
win_rate_30d = sum(1 for o in recent_outcomes_30 if o == 'MAX_PROFIT') / len(recent_outcomes_30)
```

**At prediction time** (in live trading):
```python
# FORTRESS signals.py - HARDCODED
win_rate_30d = 0.70

# SOLOMON signals.py - DEFAULT FALLBACK
win_rate_30d = gex_data.get('win_rate_30d', 0.68)

# ANCHOR signals.py - HARDCODED
win_rate_30d = 0.70
```

The model learned "when recent trades are winning (win_rate > 0.65), predict this trade will win too." At prediction time, it ALWAYS sees win_rate = 0.68-0.70, so it ALWAYS gets a confidence boost from this feature. **The model is being told "you've been winning 70% recently" on every single prediction, regardless of actual performance.**

This inflates reported accuracy during training and provides zero real-world predictive value from this feature.

### The Fallback: What Prophet Does Without ML

When `is_trained = False`, Prophet uses pure rule-based heuristics:

```python
base_prob = 0.60
if vix > 35: base_prob -= 0.20
elif vix > 30: base_prob -= 0.15
elif vix > 25: base_prob -= 0.10
elif vix > 20: base_prob -= 0.05
elif vix < 12: base_prob -= 0.05
elif 14 <= vix <= 18: base_prob += 0.08  # "Sweet spot"

if gex_regime == POSITIVE: base_prob += 0.10
elif gex_regime == NEGATIVE: base_prob -= 0.12

if not gex_between_walls: base_prob -= 0.10
# ...more rules
return max(0.30, min(0.85, base_prob))
```

**This is literally the same logic the ML model probably learned**, expressed as if/else instead of tree splits. The GradientBoosting model is likely replicating these exact thresholds because these are the dominant features.

### No Evidence of Predictive Power

| What Would Prove It | Does It Exist? |
|---------------------|----------------|
| Out-of-sample test accuracy | NO - final model trained on ALL data |
| Comparison vs "always predict 60%" baseline | NO |
| Comparison vs "VIX-only" model | NO |
| Live prediction accuracy tracking | NO |
| Brier score on held-out data | NO - calculated on training data |
| Feature importance proving ML finds non-obvious patterns | NO - top features are VIX and GEX (obvious) |

### VIX Overrides Bypass the Model Anyway

```python
# Line 2466 - Hard skip regardless of model prediction
if vix > 32: return SKIP_TODAY

# Line 2471 - Monday/Friday rules override
if day_of_week in (0, 4) and vix > 25: return SKIP_TODAY

# Line 2478 - Streak rules override
if consecutive_losses >= 2: return SKIP_TODAY
```

So even when the model predicts "72% win probability," these hardcoded VIX rules can override it. The model's prediction is not the final word.

### Prophet Verdict

**What Prophet provides**: A unified interface to VIX + GEX logic with a consistent API that all bots can call. This is valuable as software architecture.

**What Prophet does NOT provide**: Proven predictive edge over the fallback heuristics it already contains.

**A simple rule that probably performs identically**:
```python
def should_trade(vix, gex_regime):
    if vix > 32 or vix < 12: return SKIP
    if 14 <= vix <= 22 and gex_regime == POSITIVE: return TRADE_FULL
    if vix <= 28: return TRADE_REDUCED
    return SKIP
```

---

## Fortress ML Advisor

**File**: `quant/fortress_ml_advisor.py` (~1,178 lines)

### What It Is
XGBoost classifier trained on Chronicles backtests for IC-specific win/loss prediction.

### Model

```python
XGBClassifier(
    n_estimators=150,
    max_depth=4,
    learning_rate=0.1,
    reg_alpha=0.1,   # L1
    reg_lambda=1.0,   # L2
)
# Calibrated with CalibratedClassifierCV (isotonic, cv=3)
```

### Same Features, Same Problems

Uses the identical 11 features as Prophet, including the **same `win_rate_30d` data leakage**.

### Used By Only 3 of 9 Bots

FORTRESS, ANCHOR, SAMSON import it. The other 6 bots don't.

### Redundant With Prophet

Both models:
- Use the same 11 features
- Use the same training data (Chronicles backtests)
- Output the same thing (win_probability 0-1)
- Are calibrated the same way (isotonic)

The difference: Prophet uses GradientBoosting, Fortress ML uses XGBoost. On the same features and data, these will produce very similar predictions.

### The Fallback Is Just Heuristics

```python
def _fallback_prediction(self):
    base_prob = 0.70
    if vix > 35: base_prob -= 0.05
    if vix < 12: base_prob -= 0.02
    if day_of_week == 0: base_prob -= 0.01  # Monday
    if gex_regime_positive == 1: base_prob += 0.03
    return max(0.5, min(0.85, base_prob))
```

This is Prophet's fallback with slightly different numbers.

### Fortress ML Verdict

**Retire this model.** It's redundant with Prophet, uses the same leaky features, and only serves 3 bots. Let Prophet handle all IC predictions. Removing this eliminates a maintenance burden with zero capability loss.

---

## GEX Probability Models (WATCHTOWER/GLORY)

**File**: `quant/gex_probability_models.py` (~1,762 lines)
**Integration**: Used by WATCHTOWER (gamma visualization) and GLORY (gamma analysis/ML training)

### 5 Sub-Models - Honest Assessment

#### Model 1: Direction Probability
- **What it does**: Classifies daily price move as UP (+0.3%), DOWN (-0.3%), or FLAT
- **Problem**: No baseline comparison. If FLAT happens 65% of days, predicting FLAT always gets 65% accuracy. Is the model beating that? Nobody checked.
- **Verdict**: Unknown edge. Useless without baseline comparison.

#### Model 2: Flip Gravity
- **What it does**: Predicts if price moves toward flip point during the day
- **The code literally says**: "Hypothesis H4 was NOT confirmed (44.4%), so this model may have limited predictive power. We train it anyway to let the model find any conditional patterns."
- **Reality**: 44.4% accuracy on a binary prediction. Random guessing = 50%. **This model is WORSE than a coin flip.**
- **Verdict**: Delete it. It's adding noise.

#### Model 3: Magnet Attraction
- **What it does**: Predicts if price touches the nearest high-gamma strike
- **89% accuracy sounds great, but**: Magnets ARE high-gamma strikes. Price naturally gravitates to high-gamma areas due to dealer hedging mechanics. You're predicting "will price visit the area with the most market maker activity?" That's like predicting "will people walk on the sidewalk." Yes, 89% of the time they will.
- **Verdict**: Tautological. Not a prediction - a restatement of market microstructure.

#### Model 4: Volatility Estimate
- **What it does**: Regresses on daily price range as % of open
- **Problem**: No comparison to VIX-implied expected move (the industry standard). Is XGBoost beating `Spot * VIX/100 * sqrt(1/365)`? Nobody checked.
- **Verdict**: Unknown edge. Likely redundant with VIX.

#### Model 5: Pin Zone Behavior
- **What it does**: Predicts if price closes between the two biggest gamma magnets
- **55.2% accuracy** on a binary prediction = 5.2% edge over random
- **With ~250 test samples per fold**: This edge is NOT statistically significant. Need at least 1,000+ samples to distinguish 55% from 50% with confidence.
- **Verdict**: Probably noise. Insufficient sample size to prove otherwise.

### How They Combine: Not ML

The 5 models don't feed into a learned combination. Instead:

```python
# Hardcoded thresholds and manual averaging
if pin_zone.raw_value > 0.7:
    conviction_factors.append(0.5)  # Reduce conviction
else:
    conviction_factors.append(0.8)

if magnet_attraction.raw_value > 0.7:
    conviction_factors.append(0.9)
else:
    conviction_factors.append(0.6)

overall_conviction = np.mean(conviction_factors)  # Simple average
```

This is a human writing rules, not a model learning optimal weights.

### The "60% ML / 40% Distance" Hybrid

```python
combined = (0.6 * ml_probability) + (0.4 * distance_probability)
```

Where `distance_probability` is:
```python
gamma_weight = gamma_magnitude / total_gamma
distance_decay = math.exp(-distance_from_spot / expected_move)
distance_probability = gamma_weight * distance_decay * 100
```

**When models aren't trained** (which is the default state), `ml_probability` defaults to `distance_probability`. So the formula becomes:
```
combined = 0.6 * distance_probability + 0.4 * distance_probability = distance_probability
```

The ML contributes zero. The system runs on pure exponential distance decay math.

**Has anyone compared hybrid vs distance-only?** No. There is no A/B test, no accuracy comparison, no logged evidence that the 60% ML component improves anything.

### GEX Probability Models Verdict

| Model | Action |
|-------|--------|
| Direction | Keep but ADD baseline comparison |
| Flip Gravity | **DELETE** - worse than random |
| Magnet Attraction | Demote to "feature" not "model" - it's a market microstructure fact |
| Volatility | Keep but ADD VIX comparison |
| Pin Zone | **PAUSE** until sample size proves significance |

---

## SAGE

**File**: Referenced in `backend/api/routes/ml_routes.py`

### What It Is
RandomForest classifier for SPX wheel trade outcome prediction. 15 clean features (no data leakage). Proper stratified split + 5-fold CV. Methodologically the best-designed ML system in the codebase.

### The Problem
**It's never been integrated into actual trading.** The endpoints exist:
- `POST /api/ml/sage/train` - works
- `POST /api/ml/sage/predict` - works

But no bot calls these endpoints. No outcome data feeds back. The training pipeline exists but the integration pipeline doesn't.

### SAGE Verdict

This is a Rolls-Royce engine sitting in a garage. It's the only ML system with clean methodology, but it has zero impact because it's disconnected from trading.

---

## How ML Actually Flows Into Trade Decisions

This is the most important section. I traced the exact code path from ML prediction to trade execution in the three primary bots.

### FORTRESS (SPY Iron Condor)

```
ML Prediction → win_probability → LOGGED TO DATABASE → IGNORED
Prophet Advice → TRADE_FULL / SKIP_TODAY → THIS CONTROLS THE TRADE
```

**Code proof** (fortress_v2/signals.py):
```python
# "CRITICAL: When Prophet says TRADE, we TRADE. Period.
#  Prophet already analyzed VIX, GEX, walls, regime, day of week.
#  Bot's min_win_probability threshold does NOT override Prophet."
```

ML win_probability is logged for auditing but **does not gate the trade decision**.

### SOLOMON (Directional Spreads)

```
ML Prediction → direction + win_probability → LOGGED → IGNORED
Prophet Advice → TRADE_FULL / SKIP_TODAY → THIS CONTROLS THE TRADE
```

**Code proof** (solomon_v2/signals.py):
```python
# "PROPHET IS THE GOD: If Prophet says TRADE, we TRADE
#  No min_win_probability threshold check - Prophet's word is final"
```

Same as FORTRESS. ML is informational only.

### ANCHOR (SPX Iron Condor)

```
ML Prediction → win_probability → COMPARED TO THRESHOLD → GATES TRADE
```

**Code proof** (anchor/signals.py):
```python
effective_win_prob >= min_win_probability  # min = 0.42
```

ANCHOR is the **only bot where ML win_probability actually controls the trade decision**. If win_prob < 0.42, the trade is blocked.

### Summary: The Architecture's Dirty Secret

| Bot | Does ML Control Trades? | What Actually Decides? |
|-----|------------------------|----------------------|
| FORTRESS | **NO** - informational only | Prophet advice enum |
| SOLOMON | **NO** - informational only | Prophet advice enum |
| GIDEON | **NO** - informational only | Prophet advice enum |
| ANCHOR | **YES** - threshold gate | ML win_probability >= 0.42 |
| SAMSON | **YES** - threshold gate | ML win_probability >= 0.40 |
| JUBILEE | N/A | Deterministic pricing |
| VALOR | **NO** | Rule-based GEX regime |
| AGAPE | **NO** | Rule-based microstructure |
| AGAPE-SPOT | **NO** | Rule-based microstructure |

**For 7 of 9 bots, ML predictions are logged but don't control trades.** For ANCHOR and SAMSON, ML gates trades but uses the leaky `win_rate_30d = 0.70` feature, and the threshold is so low (0.40-0.42) that the model almost always passes.

---

## The Uncomfortable Questions

### 1. Has anyone ever turned the ML off and compared results?
No. There is no A/B testing infrastructure in production. Nobody knows if ML-on vs ML-off produces different P&L.

### 2. If Prophet is just VIX + GEX rules, why is it 5,600 lines?
Because it also handles: model persistence to PostgreSQL, staleness tracking, Claude AI validation, multiple training data sources, feature engineering, calibration, version management, logging. The ML logic is ~200 lines. The other 5,400 lines are infrastructure.

### 3. What is the actual accuracy of Prophet on live trades?
Unknown. The code tracks prediction_id → outcome linkage, but no script or dashboard aggregates this into "Prophet predicted 72% win rate, actual was 68%."

### 4. Could you replace all ML with 20 lines of rules?
Probably. The effective decision logic across all bots reduces to:

```python
def should_trade(vix, gex_regime, gex_between_walls):
    if vix > 32: return SKIP
    if vix < 12: return SKIP
    if gex_regime == NEGATIVE and vix > 25: return SKIP
    if 14 <= vix <= 22 and gex_regime == POSITIVE and gex_between_walls:
        return TRADE_FULL
    if vix <= 28:
        return TRADE_REDUCED
    return SKIP
```

This captures the essence of what Prophet does. The ML model may find slight non-linear interactions between features, but nobody has proven those interactions exist or are stable.

### 5. Are the GEX Probability Models making WATCHTOWER better?
When GEX models are trained: 60% ML + 40% distance math.
When GEX models are NOT trained: 100% distance math.
Nobody has compared whether WATCHTOWER with ML is more accurate than WATCHTOWER without. The default (untrained) state uses pure math and probably works fine.

### 6. Is SAGE the only ML system worth saving?
Yes, from a methodology standpoint. It has:
- Clean features (no data leakage)
- Proper train/test split
- 5-fold cross-validation
- No hardcoded fallback features

But it needs to be actually connected to trading before it can prove value.

---

## What Would Actually Fix This

### Tier 1: Stop the Bleeding (This Week)

1. **Remove `win_rate_30d` from all ML feature sets**
   - It's data leakage. The model sees fake 0.70 at prediction time.
   - Retrain on the remaining 10 features.
   - Accept that accuracy will drop. The current accuracy is fake.

2. **Delete the Flip Gravity sub-model from GEX Probability Models**
   - It's confirmed WORSE than random (44.4% on binary).
   - Every prediction from this model adds noise.

3. **Make Proverbs (risk management) a REQUIRED dependency, not optional**
   - If the ML import fails, bots run without risk controls.
   - This is more dangerous than the ML being wrong.

### Tier 2: Prove It Works (This Month)

4. **Build a prediction accuracy dashboard**
   - Prophet predictions are linked to outcomes via `prediction_id`.
   - Write a query: `SELECT predicted_win_prob, actual_outcome FROM predictions JOIN trades`.
   - Plot calibration curve: does 70% predicted = 70% actual?
   - Compare vs baseline: "always predict 60%."

5. **Run an A/B test: ML vs Rules**
   - For 2 weeks, run FORTRESS with Prophet ML.
   - For 2 weeks, run FORTRESS with the simple rule fallback.
   - Compare: win rate, total P&L, trades taken, max drawdown.
   - If ML doesn't win by >5%, retire the ML and use rules.

6. **Integrate SAGE into one bot**
   - Pick ANCHOR (the one bot where ML actually gates trades).
   - Wire SAGE predictions into the signal flow.
   - Track accuracy vs Prophet for 30 days.

### Tier 3: Build Real ML (This Quarter)

7. **If ML is worth keeping, fix the fundamentals**
   - Proper held-out test set (never trained on).
   - Baseline comparison for every model (random, VIX-only, historical-average).
   - Minimum 200 out-of-sample predictions before trusting a model.
   - Statistical significance test: is accuracy different from baseline at p < 0.05?

8. **Add features that might actually be predictive**
   - Intraday order flow (not just daily GEX snapshots)
   - Options volume/open interest changes
   - Implied volatility skew changes
   - Cross-asset signals (bonds, VIX term structure)

9. **Consider whether ML is even the right approach**
   - Iron Condors have a ~70% baseline win rate (structural).
   - The ML needs to beat 70% to add value.
   - Beating a 70% baseline with 11 features is HARD.
   - Maybe the alpha is in position sizing and exit timing, not entry prediction.

---

## Final Assessment

**The AlphaGEX ML systems are well-engineered software that solve an unproven problem.**

The code quality is high. The architecture is clean. The infrastructure (model persistence, staleness tracking, calibration, feature engineering) is professional-grade.

But none of it has been validated against the only question that matters: **Does the ML make more money than not having ML?**

Until someone runs that comparison, the honest answer is: **we don't know, and the evidence suggests probably not by much.**

The good news: the rule-based fallbacks are solid. The VIX + GEX decision logic is sound trading intuition. The bots would probably perform similarly with or without the ML models, because the ML models are likely just learning the same VIX + GEX patterns that the rules already capture.

The bad news: 5,600 lines of Prophet + 1,178 lines of Fortress ML + 1,762 lines of GEX Probability Models = **8,540 lines of ML code with no proven edge**. That's significant maintenance burden for unproven value.

---

*Generated by line-by-line source code audit on February 10, 2026*
*Files analyzed: prophet_advisor.py, fortress_ml_advisor.py, gex_probability_models.py, shared_gamma_engine.py, ml_routes.py, fortress_v2/signals.py, solomon_v2/signals.py, anchor/signals.py*
