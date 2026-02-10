# WISDOM ML Trading Bot — Comprehensive Audit Report
## Options Market Evaluation (Iron Condor Focus)

**Audit Date:** February 10, 2026
**System Audited:** WISDOM (formerly SAGE) — Strategic Algorithmic Guidance Engine
**Core File:** `quant/fortress_ml_advisor.py` (FortressMLAdvisor class)
**Bots Served:** FORTRESS, ANCHOR, SAMSON (IC), SOLOMON, GIDEON (Directional)

---

## SECTION 1: DATA PIPELINE AUDIT

### 1.1 Data Sources & Quality

**Current Data Sources:**

| Source | Data Type | Quality | Freshness |
|--------|-----------|---------|-----------|
| `zero_dte_backtest_trades` | CHRONICLES IC backtests | Good — has VIX, price, outcome, GEX regime | Stale (stops ~12/25/2025) |
| `prophet_training_outcomes` | Live trades with JSONB features | Good — pre-computed feature vectors | Ongoing (daily) |
| `fortress/anchor/samson_positions` | Live bot closed positions | Good — VIX, GEX, price, P&L | Ongoing (daily) |

**What's Missing:**
- No raw options chain data (bid/ask, Greeks per strike, IV surface)
- No intraday OHLCV data — only point-in-time snapshots at trade entry
- No order book depth or options order flow data
- No dividend/earnings calendar data
- VIX is the only volatility signal — no VVIX, IV term structure, or skew data

**Look-Ahead Bias:** Mostly clean. Training uses `TimeSeriesSplit` (walk-forward). However:

> 🟡 **FINDING**: `win_rate_30d` is computed as a rolling window over the training data using trade index (not calendar days). If trades cluster on certain dates, the "30-trade lookback" may span weeks or days unpredictably, creating inconsistent feature semantics between training and live prediction.

> 🟡 **FINDING**: `vix_percentile_30d` is calculated post-hoc using `df['vix'].rolling(30)` over trade sequence — this means "30 trades" not "30 calendar days". In live prediction, the caller passes a true 30-calendar-day percentile. **Training/inference mismatch.**

> 🟡 **FINDING**: `price_change_1d` during training is computed as `(close_price - open_price) / open_price` — this is the intraday move on the trade day. But in live prediction, `price_change_1d` is passed as yesterday's price change. **Different definitions, same feature name.**

### 1.2 Options-Specific Data Integrity

| Question | Answer | Status |
|----------|--------|--------|
| Greeks calculated or sourced? | Not used at all | 🔴 MISSING |
| IV per-strike or interpolated? | Not used — only `expected_move_pct` (aggregate) | 🔴 MISSING |
| IV surface modeled? | No | 🔴 MISSING |
| Bid-ask spreads captured? | Backtest uses $0.10 slippage assumption | ⚠️ SIMPLIFIED |
| Open interest for liquidity? | Not used | 🟡 MISSING |
| Dividends/earnings in pricing? | Not accounted for | 🟡 MISSING |

**Bottom Line:** WISDOM is making Iron Condor predictions without any options-specific data. It sees VIX, price, day of week, and GEX regime — but not the actual options chain, Greeks, IV surface, or strike-level characteristics that drive IC outcomes.

### 1.3 Look-Ahead Bias Check

| Check | Result |
|-------|--------|
| Train/test temporal ordering | ✅ `TimeSeriesSplit` (walk-forward, 5 folds) |
| No future info in features | ⚠️ `price_change_1d` definition mismatch (see above) |
| Rolling windows exclude target | ✅ Rolling stats use `outcomes[lookback_start:i]` (excludes current) |
| Brier score computed on training data | 🟡 Line 562: `brier_score_loss(y, y_proba_full)` uses full training set, not held-out |

---

## SECTION 2: FEATURE ENGINEERING AUDIT

### 2.1 Current Feature Inventory (11 Features)

| # | Feature | Type | Relevance | Stationarity | Issues |
|---|---------|------|-----------|-------------|--------|
| 1 | `vix` | Continuous | ✅ High — VIX is the primary driver of IC premium and risk | ⚠️ Non-stationary (trends) | Should use VIX relative measures, not raw level |
| 2 | `vix_percentile_30d` | Continuous (0-100) | ✅ High — contextualizes VIX level | ✅ Stationary | Good feature |
| 3 | `vix_change_1d` | Continuous (%) | ✅ Medium — momentum signal | ✅ Stationary | Good feature |
| 4 | `day_of_week` | Integer (0-4) | ✅ Medium — theta patterns, Monday gaps | ⚠️ Ordinal encoding | Should use cyclical sin/cos encoding |
| 5 | `price_change_1d` | Continuous (%) | ⚠️ Low — yesterday's equity move weakly predicts today's IC outcome | ✅ Stationary | Training/inference definition mismatch |
| 6 | `expected_move_pct` | Continuous (%) | ✅ High — directly affects IC strike distance | ⚠️ Drifts with VIX | Redundant with VIX |
| 7 | `win_rate_30d` | Continuous (0-1) | 🔴 Problematic — encodes momentum but also overfits to recent streak | ⚠️ Regime-dependent | **High leakage risk** — recent win rate predicts continuation, which is circular |
| 8 | `gex_normalized` | Continuous | ✅ High — GEX drives mean-reversion vs momentum | ⚠️ Scale varies | Good unique signal |
| 9 | `gex_regime_positive` | Binary (0/1) | ✅ High — positive GEX = mean-reversion = good for IC | ✅ Stationary | Good feature |
| 10 | `gex_distance_to_flip_pct` | Continuous (%) | ✅ Medium — proximity to regime change | ✅ Stationary | Currently hardcoded to 0 from bot positions source |
| 11 | `gex_between_walls` | Binary (0/1) | ✅ Medium — price inside gamma walls = safer | ✅ Stationary | Currently hardcoded to 1 from bot positions source |

### 2.2 Critical Missing Features

**Volatility Features (MISSING — HIGH IMPACT):**
- ❌ **IV Rank / IV Percentile** — the single most important feature for premium selling strategies. "Is IV high or low relative to its own history?" VIX percentile is a proxy but not the same as per-strategy IV rank.
- ❌ **HV vs IV spread (Volatility Risk Premium)** — the entire profit engine of Iron Condors is selling inflated implied vol. Not measuring the VRP gap is flying blind.
- ❌ **IV term structure slope** — front/back month spread signals regime
- ❌ **IV skew** (OTM put IV vs OTM call IV) — skew predicts directional risk
- ❌ **VVIX** (volatility of VIX) — high VVIX = VIX itself is unstable = IC risk

**Greeks-Based Features (MISSING — HIGH IMPACT):**
- ❌ **Position Gamma** — how much delta changes with a $1 move. Near expiration, gamma explodes. This is THE risk for 0DTE ICs.
- ❌ **Position Theta** — the profit engine. Higher theta = faster premium decay
- ❌ **Charm (delta decay)** — critical for 0DTE: delta accelerates near expiry
- ❌ **Strike distance as delta** — WISDOM uses SD multiplier but not actual delta of short strikes

**Market Microstructure (MISSING — MEDIUM IMPACT):**
- ❌ **Put/call ratio** (volume or OI)
- ❌ **Bid-ask spread width** at proposed strikes — liquidity signal
- ❌ **Options order flow imbalance**

**Macro/Regime (PARTIALLY PRESENT):**
- ✅ GEX regime (positive/negative) — unique and valuable
- ❌ **Correlation regime** (risk-on/risk-off)
- ❌ **Earnings/event binary flags** — FOMC, CPI, NFP

### 2.3 Feature Engineering Red Flags

| Red Flag | Present? | Details |
|----------|----------|---------|
| Raw price as feature | ❌ Avoided | Price only used to derive `price_change_1d` and `expected_move_pct` |
| Unstandardized features | ✅ Handled | `StandardScaler` applied before model |
| High-cardinality categoricals | ❌ None | Only binary flags |
| Extreme outlier handling | ❌ None | VIX spikes, GEX outliers pass through unclipped |
| Calendar without cyclical encoding | 🔴 Yes | `day_of_week` is integer 0-4, model treats Thursday(3) as "more than" Tuesday(1) |
| Target leakage in features | ⚠️ Partial | `win_rate_30d` is borderline — it's a momentum signal that can also be a proxy for regime stability |

---

## SECTION 3: MODEL ARCHITECTURE AUDIT

### 3.1 Model Choice

**Current Model:** XGBoost Classifier
```python
xgb.XGBClassifier(
    n_estimators=150,
    max_depth=4,
    learning_rate=0.1,
    min_child_weight=10,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1.0,
)
```

**Assessment:** ✅ Good choice for tabular data with 11 features. XGBoost is the right tool.

**Hyperparameters:**
- `max_depth=4` — ✅ Good, prevents overfitting on small datasets
- `min_child_weight=10` — ✅ Excellent, requires 10+ samples per leaf (prevents overfitting to rare events)
- `n_estimators=150` — ⚠️ May be excessive for 11 features. Could overfit with walk-forward on small datasets.
- `learning_rate=0.1` — ✅ Standard
- L1/L2 regularization — ✅ Present (`reg_alpha=0.1`, `reg_lambda=1.0`)

**Prediction Target:** Binary classification — `is_win` (MAX_PROFIT vs any breach)

> 🟡 **FINDING**: Collapsing PUT_BREACHED, CALL_BREACHED, and DOUBLE_BREACH into a single "loss" class discards directional information. The model can't distinguish between bullish risk (call breach) and bearish risk (put breach), which have different feature signatures.

### 3.2 Training & Validation

| Aspect | Implementation | Assessment |
|--------|---------------|------------|
| **Split method** | `TimeSeriesSplit(n_splits=5)` | ✅ Correct — walk-forward |
| **Purging/embargo** | None | 🟡 Minor — 0DTE trades don't overlap, so less critical than multi-day strategies |
| **Class imbalance** | Not handled | 🔴 **CRITICAL** — IC win rate ~70-90% creates severe imbalance. Loss class (10-30%) is underrepresented. Model will default to predicting "WIN" always. |
| **Hyperparameter tuning** | None — hardcoded | 🟡 Should at least do Bayesian optimization on validation folds |
| **Probability calibration** | `CalibratedClassifierCV(method='isotonic', cv=3)` | ✅ Excellent — isotonic calibration on imbalanced data |
| **Final model** | Retrained on ALL data after CV | ⚠️ Standard but means in-sample metrics are optimistic |

> 🔴 **CRITICAL FINDING**: **Class imbalance is unaddressed.** With ~89% wins (1410/1568), the model can achieve 89% accuracy by predicting WIN every time. No `scale_pos_weight`, no SMOTE, no class_weight adjustment, no threshold tuning. The 70-90% base win rate of ICs means the model's "accuracy" is largely a reflection of the class distribution, not learned skill.

> 🔴 **CRITICAL FINDING**: **Brier score computed on training data** (line 562). The calibrated model is fit on the same data that Brier score is measured on. This inflates calibration quality. Should compute on held-out fold.

> 🟡 **FINDING**: **`retrain_from_outcomes()` trains on ALL data without CV** (line 963). When retraining from live outcomes, there's no walk-forward validation — just `model.fit(X_scaled, y)` on everything. Metrics are then computed on training data (lines 977-978), making them meaningless for evaluating generalization.

### 3.3 Model Interpretability

| Question | Answer |
|----------|--------|
| Feature importances tracked? | ✅ Yes — XGBoost gain-based importance stored in `TrainingMetrics` |
| SHAP values? | ❌ No — only gain importance (can be misleading with correlated features) |
| Top features make sense? | ⚠️ Depends — VIX and GEX should dominate. If `win_rate_30d` dominates, that's suspicious (momentum/leakage) |

---

## SECTION 4: SIGNAL GENERATION & TRADE LOGIC AUDIT

### 4.1 Signal-to-Trade Translation

**Decision thresholds:**
```
win_probability >= 0.65 → TRADE_FULL (10% risk)
0.45 <= win_probability < 0.65 → TRADE_REDUCED (3-8% risk, scaled)
win_probability < 0.45 → SKIP_TODAY (0% risk)
```

> 🟡 **FINDING**: These thresholds are **hardcoded, not calibrated**. On a ~89% base-rate dataset, a well-calibrated model should output probabilities near 0.89 for most trades. A 0.65 threshold would rarely trigger SKIP. A 0.45 threshold would essentially never trigger. **The thresholds don't account for the base rate.**

> 🟡 **FINDING**: **Confidence inflation** at line 708: `confidence = min(100, win_probability * 100 * 1.2)`. Multiplying by 1.2 artificially inflates confidence by 20% for display purposes. This is cosmetic but misleading.

### 4.2 Options Strategy Selection

WISDOM only advises on **Iron Condors** and makes 3 decisions:
1. **Trade or skip** — binary, based on win probability
2. **Position size** — risk percentage (0-15%)
3. **SD multiplier** — strike width (0.9, 1.0, or 1.2)

> 🟡 **FINDING**: **SD multiplier is coarsely bucketed** (3 values). Given that strike selection is the single biggest determinant of IC outcome, this deserves a continuous recommendation, not a 3-bucket approximation.

> 🟡 **FINDING**: **No strategy switching.** When conditions are unfavorable for Iron Condors (negative GEX, high VIX, trending market), the model can only say SKIP — it can't recommend switching to a directional strategy. This leaves money on the table in non-IC-friendly regimes.

### 4.3 Entry & Exit Logic

| Aspect | Implementation |
|--------|---------------|
| **Entry trigger** | Prophet says TRADE → execute IC |
| **Exit: profit target** | Max profit at 0DTE expiration (settlement) |
| **Exit: stop loss** | FORTRESS has force exit at 2:50 PM CT (10 min before close) |
| **Exit: time-based** | 0DTE = expires same day, no rolling |
| **Rolling** | Not applicable (0DTE) |
| **Assignment risk** | SPX/SPY cash-settled options — no assignment risk ✅ |

---

## SECTION 5: RISK MANAGEMENT AUDIT

### 5.1 Position Sizing

| Metric | Value | Assessment |
|--------|-------|------------|
| Risk per trade | **15%** | 🔴 5-7x industry standard (2-3%) |
| Max contracts | 75 | ⚠️ On $100K account = $15K-22.5K max loss per trade |
| Kelly criterion | Monte Carlo safe Kelly (when available) | ✅ Good methodology |
| Thompson Sampling | 0.5x - 2.0x multiplier | ⚠️ Can push effective risk to 30% |
| Max daily trades | 3 | ⚠️ 3 × 15% = 45% at risk per day |

### 5.2 Portfolio-Level Risk

| Check | Present? | Details |
|-------|----------|---------|
| Max portfolio exposure | ❌ None | No aggregate limit across FORTRESS + ANCHOR + SAMSON |
| Net portfolio Greeks | ❌ None | No delta/gamma/vega aggregation |
| Tail risk modeling | ❌ None | No 3-sigma scenario analysis |
| Margin management | ❌ None | No buying power tracking |
| Daily drawdown limit | ⚠️ Inactive | Proverbs has $5K limit but not integrated in FORTRESS execution |
| Consecutive loss kill | ⚠️ Inactive | Proverbs has 3-loss kill but not actively called |

> 🔴 **CRITICAL**: **Proverbs risk guardrails exist in code but are not integrated into the FORTRESS execution loop.** The `ConsecutiveLossTracker` and `DailyLossTracker` are defined but `run_cycle()` in `trader.py` does not call them. The guardrails are decorative, not functional.

### 5.3 Options-Specific Risk Checks

| Risk | Handled? | Details |
|------|----------|---------|
| Pin risk near expiry | ❌ | No logic to avoid short strikes near spot into final hour |
| Early assignment | N/A | Cash-settled SPX/SPY options |
| Liquidity check | ❌ | No bid-ask width check before entering |
| Event risk (FOMC, CPI) | ❌ | Flags exist in scan_activity but not used for decisions |
| Volatility crush | N/A | 0DTE — no overnight vol crush risk |

---

## SECTION 6: BACKTEST INTEGRITY AUDIT

### 6.1 Backtest Realism

| Aspect | Implementation | Assessment |
|--------|---------------|------------|
| Slippage | $0.10/spread ($0.05/leg) | ✅ Realistic |
| Commission | $0.65/contract/leg × 4 legs | ✅ Matches Tradier retail pricing |
| Fill assumption | Mid-price minus slippage | ✅ Conservative |
| Margin costs | Not modeled | ⚠️ For ANCHOR/SAMSON SPX positions, margin matters |
| Market impact | Not modeled | ✅ OK at ≤100 contracts for SPX/SPY |

### 6.2 Statistical Validity

| Metric | Value | Assessment |
|--------|-------|------------|
| Sample size (CHRONICLES) | ~1,568 trades | ✅ Sufficient for XGBoost |
| Win rate | ~89.9% (1410W/158L) | ⚠️ Suspiciously high — could indicate backtest overfitting or survivorship bias |
| Max drawdown | Unknown — not tracked | 🔴 No drawdown analysis in training pipeline |
| Monte Carlo stress test | ❌ Not done | 🟡 Should randomize trade sequences |

> 🟡 **FINDING**: **89.9% win rate on backtests should be scrutinized.** Real-world 0DTE Iron Condors on SPX/SPY typically see 65-80% win rates. 89.9% either indicates (a) very wide strikes with very thin premiums, (b) favorable backtest period selection, or (c) look-ahead in strike selection. The P&L distribution matters more than win rate — a 90% win rate with occasional 5x losses nets negative expectancy.

### 6.3 Regime Analysis

| Regime | Tested? |
|--------|---------|
| Bull trend | ⚠️ Only if in backtest period |
| Bear trend | ⚠️ Only if in backtest period |
| High vol (VIX > 30) | ⚠️ Limited — high VIX periods are rare |
| Vol expansion (2020-style) | ❌ Unknown — backtest period not documented |
| Sideways/chop | ⚠️ Likely well-represented but not isolated |

> 🟡 **FINDING**: No per-regime performance breakdown exists. We don't know if the model works in all conditions or just the dominant regime in the training period.

---

## SECTION 7: EXECUTION & INFRASTRUCTURE AUDIT

### 7.1 Execution Quality

| Aspect | Implementation |
|--------|---------------|
| Broker | Tradier (production) |
| Order types | Market orders for 0DTE (fills quickly) |
| Latency | HTTP API calls — seconds, not milliseconds |
| Partial fills | Handled by executor retry logic |
| Failed order retry | Yes — retry with adjusted price |

### 7.2 System Reliability

| Aspect | Implementation |
|--------|---------------|
| Model persistence | ✅ Dual — pickle file + PostgreSQL (survives Render deploys) |
| Logging | ✅ Comprehensive — every scan, signal, prediction, outcome logged |
| Monitoring | ✅ scan_activity table, equity snapshots, daily performance |
| Failover | ⚠️ Fallback prediction if model not loaded (rule-based) |
| Scheduled retraining | ✅ Weekly Sunday 4:30 PM CT (WISDOM), Daily midnight (Prophet) |

---

## SECTION 8: FINDINGS SUMMARY

### 🔴 CRITICAL — Fix Immediately

**C1: Class Imbalance Unaddressed**
- **What:** ~89% win rate means model achieves "high accuracy" by always predicting WIN. No `scale_pos_weight`, SMOTE, or threshold tuning.
- **Why it matters:** The model cannot effectively identify the 10-30% of trades that will LOSE — which is its entire purpose. A model that says "always trade" provides zero filtering value.
- **Fix:** Add `scale_pos_weight = len(y_win) / len(y_loss)` (~8.9) to XGBoost params. Alternatively, tune the classification threshold to optimize F1 or precision on the minority (loss) class. Focus on PRECISION of SKIP signals, not overall accuracy.
- **Impact:** HIGH — this is the difference between WISDOM adding value vs being decorative.

**C2: Risk Guardrails Not Integrated**
- **What:** Proverbs has `ConsecutiveLossTracker` (3-loss kill), `DailyLossTracker` ($5K limit) — but FORTRESS `run_cycle()` never calls them.
- **Why it matters:** On a bad day, FORTRESS can lose 3 × 15% = 45% of capital with no automatic stop.
- **Fix:** Add Proverbs guardrail checks at the top of FORTRESS `run_cycle()` before generating any signals.
- **Impact:** HIGH — catastrophic loss prevention.

**C3: No Portfolio-Level Drawdown Stop**
- **What:** No mechanism to pause trading if account drops below a threshold (e.g., -20% from peak).
- **Why it matters:** Multiple bots (FORTRESS, ANCHOR, SAMSON) trade simultaneously. A correlated loss event hits all three.
- **Fix:** Track portfolio-level equity curve. If cumulative drawdown exceeds 15-20%, pause all IC bots for 24-48 hours.
- **Impact:** HIGH — existential risk to account.

**C4: Training/Inference Feature Mismatch**
- **What:** `price_change_1d` in training = same-day open-to-close move. In live prediction = yesterday's move. `vix_percentile_30d` in training = rolling over trade sequence. In live = true calendar percentile.
- **Why it matters:** The model learns one signal but receives a different one at prediction time. This degrades prediction quality unpredictably.
- **Fix:** Align feature definitions. In training, compute features exactly as they would be available at trade entry time (before the trade happens).
- **Impact:** MEDIUM-HIGH — reduces prediction noise.

### 🟡 HIGH IMPACT — Fix in Next Iteration

**H1: Missing Volatility Risk Premium Feature**
- **What:** No HV vs IV spread feature. The VRP is the profit engine of Iron Condors.
- **Fix:** Add `iv_minus_hv = expected_move_pct - realized_vol_5d` as a feature. When IV >> HV, IC premiums are rich → higher win probability.
- **Impact:** HIGH — this is the most predictive feature for premium selling strategies.

**H2: Missing IV Rank Feature**
- **What:** VIX is used as raw level, but what matters is "is IV high relative to its own recent range?"
- **Fix:** Already have `vix_percentile_30d`. Extend to per-strategy IV rank using the expected_move_pct history.
- **Impact:** MEDIUM-HIGH.

**H3: No Event Risk Adjustment**
- **What:** FOMC/CPI/NFP days tracked in `scan_activity` but not used for trade decisions. IC risk spikes dramatically on event days.
- **Fix:** Add `is_event_day` binary feature. Or simply: reduce position size 50% on event days, skip FOMC announcement days entirely.
- **Impact:** MEDIUM-HIGH — prevents occasional catastrophic event-day losses.

**H4: Hardcoded Decision Thresholds Don't Account for Base Rate**
- **What:** SKIP threshold of 0.45 on a 89% base-rate dataset means essentially no trades get skipped. TRADE_FULL threshold of 0.65 is also below the base rate.
- **Fix:** Set thresholds relative to the base rate. E.g., SKIP when predicted probability is significantly below the base rate: `threshold = base_rate - 0.1`. Or use the model's predicted loss probability as the primary signal (predict breach probability, skip when > X%).
- **Impact:** MEDIUM — makes the model's advice actually discriminative.

**H5: win_rate_30d Feature is Borderline Leakage**
- **What:** Using recent win rate to predict future wins is partially circular — it's momentum, but it can also overfit to short-term streaks.
- **Fix:** Replace with longer-horizon metric (60-90 day) or remove entirely and let the model learn from underlying conditions instead of outcome history.
- **Impact:** MEDIUM — reduces overfitting risk.

### 🟢 IMPROVEMENT — Would Help But Not Urgent

**I1: Day of Week as Cyclical Encoding**
- **What:** `day_of_week` as integer 0-4 implies ordinal relationship. Friday(4) is not "more" than Monday(0).
- **Fix:** Replace with `sin(2π × dow/5)` and `cos(2π × dow/5)`.
- **Impact:** LOW — XGBoost can handle ordinal encoding via splits, but cyclical is cleaner.

**I2: Multiclass Target Instead of Binary**
- **What:** PUT_BREACHED, CALL_BREACHED, DOUBLE_BREACH collapsed into single "loss" class.
- **Fix:** Train multiclass model to predict breach type. Use breach-type probabilities to adjust strike placement (if put breach probability is high, widen put side).
- **Impact:** LOW-MEDIUM — adds directional intelligence to strike selection.

**I3: SD Multiplier as Continuous Recommendation**
- **What:** Only 3 buckets (0.9, 1.0, 1.2) for strike width.
- **Fix:** Use regression head to predict optimal SD multiplier, or at least expand to 5-7 buckets.
- **Impact:** LOW — refinement, not fundamental.

**I4: Add SHAP Values for Interpretability**
- **What:** Only gain-based feature importance (can be misleading with correlated features).
- **Fix:** Add SHAP computation after training for proper attribution.
- **Impact:** LOW — interpretability, not P&L.

**I5: Hyperparameter Optimization**
- **What:** All XGBoost params hardcoded.
- **Fix:** Run Bayesian optimization (Optuna) on walk-forward validation folds.
- **Impact:** LOW-MEDIUM — can squeeze out 1-3% better metrics.

---

## QUICK WINS (Highest Impact-to-Effort Ratio)

### 1. Add `scale_pos_weight` to XGBoost (5 min fix, HIGH impact)
```python
self.model = xgb.XGBClassifier(
    ...
    scale_pos_weight=len(y[y==0]) / len(y[y==1]),  # ~0.11 for 89% win rate
    ...
)
```
This single line makes the model pay 9x more attention to loss cases. Without it, the model is a glorified coin flip that says "always trade."

### 2. Wire Proverbs guardrails into FORTRESS run_cycle (30 min fix, HIGH impact)
Add at the top of `run_cycle()`:
```python
from quant.proverbs_enhancements import check_guardrails
if check_guardrails(bot_name="FORTRESS").kill_switch_active:
    logger.warning("FORTRESS: Kill switch active, skipping cycle")
    return
```

### 3. Add VRP feature (1 hr fix, MEDIUM-HIGH impact)
```python
# In feature extraction:
realized_vol_5d = df['price_change_1d'].rolling(5).std()
record['volatility_risk_premium'] = expected_move_pct - realized_vol_5d
```

---

## ARCHITECTURE RECOMMENDATION

**Should the current model be kept, modified, or replaced?**

**KEEP the model architecture (XGBoost + isotonic calibration), but MODIFY the feature engineering and training process significantly.**

The XGBoost architecture is sound for this task. The problems are:
1. **Insufficient features** — missing the most predictive signals for IC trading (VRP, Greeks, event flags)
2. **Class imbalance** — makes the model's predictions non-discriminative
3. **Feature definition mismatches** — training vs inference inconsistencies
4. **Risk guardrails disconnected** — good risk code exists but isn't wired up

**Is an ensemble approach warranted?**

Not yet. Fix the fundamentals first. An ensemble of poorly-engineered features is still poorly-engineered. Once the feature set is robust, an ensemble of XGBoost (tabular features) + a simple time-aware model (VIX regime transitions) could add value.

**Is the strategy logic fundamentally sound?**

Yes. Selling premium via Iron Condors on SPX/SPY with GEX-informed strike selection is a valid strategy with a known edge (volatility risk premium). The ML layer's job — filter out high-risk conditions — is the right application. The implementation just needs the fixes above to actually deliver on that promise.

---

*Report generated: February 10, 2026*
