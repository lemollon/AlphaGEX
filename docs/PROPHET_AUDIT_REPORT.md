# PROPHET ML Advisor - Comprehensive Audit Report
## Options Market — Full Evaluation (8 Sections)

**Date:** 2026-02-10
**File:** `quant/prophet_advisor.py` (~5,600 lines)
**Model:** sklearn GradientBoostingClassifier + IsotonicCalibration
**Role:** Central advisory system — ALL 9 bots consult Prophet before trading
**Training:** Daily at midnight CT from `zero_dte_backtest_trades` + `prophet_training_outcomes`

---

## EXECUTIVE SUMMARY

Prophet is the **sole decision authority** for all trading bots. When Prophet says TRADE, bots trade — no override. This makes Prophet bugs the highest-impact issues in the entire system. The audit reveals Prophet suffers from the **same critical bugs we fixed in WISDOM** (class imbalance, hardcoded thresholds, in-sample metrics) plus unique issues: 1.2x confidence inflation, post-ML probability manipulation that destroys calibration, V2 features defined but never trained, and a UNIQUE constraint that discards all but one trade per day per bot.

### Signal Chain Context
```
WISDOM (signals.py) → win_probability → Signal
                                            ↓
Prophet (trader.py) → strategy_recommendation + bot-specific advice → TRADE/SKIP
                                            ↓
Executor → position_size (Thompson × Kelly) → Tradier API → fills
```

WISDOM and Prophet are **separate ML models** answering different questions:
- **WISDOM**: "What's the probability this specific trade wins?" (binary classifier)
- **Prophet**: "Should we trade IC or Directional? What strikes? What risk %?" (strategy advisor + binary classifier)

### Verdict: FIX — Apply WISDOM V3 patterns to Prophet's ML layer

---

## SECTION 1: DATA PIPELINE AUDIT

### 1.1 Data Sources & Quality

**Training data sources (3 paths, priority order):**

| Source | Table | Rows | Used By |
|--------|-------|------|---------|
| Live outcomes | `prophet_training_outcomes` | 6 | `train_from_live_outcomes()` (priority 1) |
| DB backtests | `zero_dte_backtest_trades` | 7,246 | `train_from_database_backtests()` (priority 2) |
| In-memory | CHRONICLES engine | varies | `train_from_chronicles()` (priority 3) |

**Data frequency:** Daily aggregated trades. The bot scans every 5 minutes but only stores 1 outcome per day per bot (see Finding 7.1).

**Inference data sources (live):**
- Spot price: Tradier production API (real-time)
- VIX: Data provider (`get_vix()`) with floor of 10
- GEX: Tradier GEX calculator (real-time chain data)
- GEX walls/flip: Computed from options chain gamma per strike

### 1.2 Options-Specific Data Integrity

**Greeks:** GEX (gamma exposure) is calculated from the full options chain using Tradier data. Per-strike gamma is summed to get net GEX, call wall, put wall, and flip point. This is **calculated, not sourced from broker** — using Black-Scholes via the GEX calculator.

**Implied Volatility:** VIX is used as a market-wide IV proxy. **No per-strike IV** or IV surface modeling is used in Prophet's features. IV skew, term structure, and smile are NOT captured.

**Bid-ask spreads:** The executor uses real Tradier bid/ask quotes for entry and exit pricing:
```python
# Entry: short bid - long ask (conservative credit)
put_credit = put_short_quote['bid'] - put_long_quote['ask']
# Exit: short ask - long bid (conservative debit)
put_value = put_short['ask'] - put_long['bid']
```
This is realistic slippage handling at the execution layer. However, **bid-ask is NOT a feature** in Prophet's ML model.

**Open interest/volume:** NOT used for liquidity filtering in Prophet. Liquidity is assumed by trading only SPY/SPX.

**Dividends/earnings:** NOT accounted for in Prophet's features or logic. No event calendar integration despite CLAUDE.md mentioning FOMC/CPI/NFP detection.

### 1.3 Look-Ahead Bias Check

**FOUND — price_change_1d leaks future information:**
```python
# Line 4246 - extract_features_from_chronicles()
price_change_1d = (close_price - open_price) / open_price * 100
```
In training, `price_change_1d` uses the **same-day close price** — information that wouldn't be available at trade entry (morning). In live inference, `context.price_change_1d` is populated from the previous day's move. This creates a training/inference mismatch where the model learns a signal it can never see in production.

**FOUND — win_rate_30d includes current trade's data point:**
```python
# Line 4231
win_rate_30d = sum(1 for o in recent_outcomes_30 if o == 'MAX_PROFIT') / len(recent_outcomes_30)
```
The rolling window is computed from `outcomes[lookback_start:i]` which correctly excludes the current trade. However, `outcomes` is appended to AFTER feature extraction (line 4254), so the window is valid. **No leakage here.**

**Train/test split:** TimeSeriesSplit(n_splits=5) is used for CV metrics — this correctly respects temporal ordering. However, the final model is trained on ALL data (line 4454), so the deployed model has seen future data relative to early trades.

---

## SECTION 2: FEATURE ENGINEERING AUDIT

### 2.1 Current Feature Inventory

**V1 features actually used in training (11 cols):**

| Feature | Relevance | Stationarity | Leakage Risk |
|---------|-----------|--------------|--------------|
| `vix` | HIGH — primary vol signal | Non-stationary (trends) | None |
| `vix_percentile_30d` | HIGH — relative vol context | Stationary (0-100) | None |
| `vix_change_1d` | MEDIUM — vol momentum | Stationary (returns) | None |
| `day_of_week` | MEDIUM — weekday patterns | Stationary | **RED FLAG: Integer encoding** |
| `price_change_1d` | MEDIUM — momentum | Stationary (returns) | **RED FLAG: Same-day close leak** |
| `expected_move_pct` | HIGH — option pricing context | Somewhat stationary | None |
| `win_rate_30d` | MEDIUM — recent performance | Stationary | **Recency bias** |
| `gex_normalized` | HIGH — gamma exposure | Non-stationary | None |
| `gex_regime_positive` | HIGH — regime binary | Stationary (0/1) | None |
| `gex_distance_to_flip_pct` | HIGH — flip proximity | Somewhat stationary | None |
| `gex_between_walls` | MEDIUM — containment | Stationary (0/1) | None |

**V2 features DEFINED but NEVER USED (22 cols):**

These are computed in `extract_features_from_chronicles()` but the training line (4416) only selects `FEATURE_COLS` (V1):

| Unused Feature | Value if Used |
|----------------|---------------|
| `win_rate_7d` | Faster momentum signal |
| `vix_regime_low/normal/elevated/high/extreme` | One-hot VIX regime encoding |
| `ic_suitability` | Pre-computed IC suitability score (0-1) |
| `dir_suitability` | Pre-computed directional suitability score (0-1) |
| `regime_trend_score` | Trend direction (-1 to 1) |
| `regime_vol_percentile` | Vol context (0-100) |
| `psychology_fear_score` | Fear/greed indicator (0-1) |
| `psychology_momentum` | Price momentum (-1 to 1) |

These features are computed on every training run but thrown away at the `X = df[feature_cols].values` line.

### 2.2 Options-Critical Features — Missing

| Missing Feature | Why It Matters | Priority |
|-----------------|----------------|----------|
| **Volatility Risk Premium (IV - HV)** | THE profit driver for IC strategies. High VRP = rich premiums = IC profits. Prophet decides IC vs Directional without this. | CRITICAL |
| **IV rank / IV percentile (per-strike)** | VIX is a proxy, but doesn't capture the actual premium available on the strikes being traded | HIGH |
| **IV term structure slope** | Front-month vs back-month IV indicates vol regime; steep contango = calm market = IC favorable | MEDIUM |
| **IV skew (OTM put vs OTM call)** | Asymmetric fear. Heavy put skew = crash fear = dangerous for short put spreads | MEDIUM |
| **Theta (position-level)** | Time decay is the IC profit mechanism; position theta determines daily capture | MEDIUM |
| **Charm (delta decay near expiry)** | Critical for 0DTE — delta accelerates near expiry; not modeled | MEDIUM |
| **Bid-ask spread % of mid** | Liquidity proxy for execution cost prediction | LOW |
| **Earnings/event binary flags** | FOMC/NFP/CPI create gap risk; mentioned in CLAUDE.md but not implemented | LOW |

### 2.3 Feature Engineering Red Flags

| Red Flag | Location | Impact |
|----------|----------|--------|
| **Integer day_of_week (0-4)** | FEATURE_COLS line 1370 | Model sees Monday(0) as "closer to nothing" than Friday(4). Creates artificial ordinal distance that doesn't reflect weekly cyclical patterns. Should use sin/cos encoding. |
| **Raw VIX level as feature** | Already present but needs context | VIX of 20 in 2019 vs VIX of 20 in 2022 mean different things. `vix_percentile_30d` helps but doesn't fully address regime shifts. |
| **price_change_1d uses close price in training** | Line 4246 | Same-day close is unavailable at entry time. Training sees forward information. |
| **win_rate_30d default of 0.68** | Line 4231 | When insufficient history exists, win_rate defaults to 0.68. This hard-coded optimistic default biases early trades. |
| **vix_percentile_30d hardcoded to 50** | Line 4301 | During feature extraction, `vix_percentile_30d` is initially set to 50 and then overwritten with rolling calculation only if `len(df) > 1`. With a single trade, model sees flat 50th percentile. |

---

## SECTION 3: MODEL ARCHITECTURE AUDIT

### 3.1 Model Choice Evaluation

**Current model:** `sklearn.ensemble.GradientBoostingClassifier`
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

**Assessment:** GBC is a reasonable choice for tabular features with cross-sectional patterns. However:
- WISDOM uses XGBoost which has native `scale_pos_weight` — GBC lacks this convenience but supports `sample_weight` in `.fit()`
- With 11 features and ~7,000 samples, GBC is appropriately sized (not overparameterized)
- `max_depth=4` is conservative enough to resist overfitting
- `min_samples_leaf=10` prevents thin nodes

**Prediction target:** Binary classification (is_win: 0/1). This is correct for the trade/skip decision. The win_probability from `predict_proba` maps directly to confidence thresholds.

**Calibration:** IsotonicCalibration via `CalibratedClassifierCV(method='isotonic', cv=3)`. Isotonic is appropriate for the sample size (7K+). However, the calibration is fitted on training data after the model has seen all data (see Finding 4.2).

### 3.2 Training & Validation

**Train/test split:** TimeSeriesSplit(n_splits=5) — **CORRECT** for time-series. No random shuffling.

**Purging and embargo:** **NOT IMPLEMENTED**. There is no gap between train and test folds. With daily data this matters less than intraday, but overlapping feature windows (30-trade rolling stats) mean the last few train samples and first few test samples share information.

**Class imbalance:** **NOT HANDLED**. This is the single biggest bug.
```python
# Line 4441 — no sample_weight passed
self.model.fit(X_train, y_train)
```
With ~89% win rate (y.mean() ≈ 0.89), the model minimizes loss by predicting WIN for everything. It learns to output ~0.89 for all inputs, which passes the 0.65 TRADE_FULL threshold, making the model functionally useless — it never discriminates.

**Expected impact of class imbalance fix:** Based on WISDOM V3 results, adding `sample_weight` where loss samples get ~9x weight forces the model to actually learn what predicts LOSSES. This should reduce win-always prediction to genuinely discriminating outputs, enabling the model to actually SKIP bad trades.

**Hyperparameter tuning:** **NONE**. Parameters are hardcoded. No grid search, Bayesian optimization, or systematic tuning has been performed. The parameters are reasonable defaults but not optimized for this specific dataset.

**Overfitting indicators:**
- In-sample Brier score is reported as the only calibration metric — likely optimistically low
- No out-of-sample Sharpe or Brier reported
- Model trains on ALL data (line 4454) after CV metrics are computed
- With 89% class imbalance, 89% accuracy is achievable by predicting WIN always

### 3.3 Model Interpretability

**Feature importances:** Tracked via `self.model.feature_importances_` (gain-based importance from GBC). Top 3 factors are returned with each prediction.

**Assessment:** If the model is predicting WIN always due to class imbalance, feature importances may reflect which features correlate with the majority class (wins) rather than which features discriminate between wins and losses. After fixing class imbalance, feature importances will become meaningful.

---

## SECTION 4: SIGNAL GENERATION & TRADE LOGIC AUDIT

### 4.1 Signal-to-Trade Translation

**Prophet's output becomes a direct trade decision:**
```python
advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])
```

Where:
| Probability | Advice | Risk % |
|-------------|--------|--------|
| >= 0.65 | TRADE_FULL | 10.0% |
| 0.45 - 0.65 | TRADE_REDUCED | 3.0 - 8.0% (linear interpolation) |
| < 0.45 | SKIP_TODAY | 0.0% |

**Problem:** With 89% base rate and no class imbalance handling, the model outputs ~0.85+ for almost everything. This means:
- **TRADE_FULL**: Almost always triggered
- **TRADE_REDUCED**: Rarely seen
- **SKIP_TODAY**: Almost never triggered

**Prophet is "god"** — from `signals.py` line 847:
```python
# PROPHET IS THE GOD: If Prophet says TRADE, we TRADE
# No min_win_probability threshold check - Prophet's word is final
```
This means the broken thresholds cause the system to trade in conditions it should skip.

### 4.2 Options Strategy Selection

**Strategy recommendation logic** (`get_strategy_recommendation()`):
- Rule-based scoring: VIX regime + GEX regime → IC score vs Directional score
- IC favored when: Normal VIX (15-22) + Positive GEX
- Directional favored when: High VIX (28+) + Negative GEX
- SKIP when: Extreme VIX (35+) without clear directional signal

This is **well-designed** and doesn't depend on the ML model. It's a pure rule-based decision using market regime classification. The scores are intuitive and the logic is sound.

**Strike selection:**
- IC bots: SD multiplier (1.2-1.4x based on confidence) places strikes OUTSIDE expected move
- GEX-protected strikes: Puts below put wall, calls above call wall, with proportional buffer
- SOLOMON directional: ATM strikes for spread entry

**Expiration selection:** Fixed per bot type (0DTE for FORTRESS, weekly for ANCHOR). Not optimized dynamically.

### 4.3 Entry & Exit Logic

**Entry:** Prophet signal + strategy recommendation + VIX skip rules
- VIX hard skip configurable per strategy preset
- Monday/Friday VIX penalty rules
- Loss streak VIX tightening (3+ recent losses → lower threshold)
- When IC is skipped due to high VIX, Prophet suggests SOLOMON directional instead — good adaptive behavior

**Exit:**
- Profit target: 50% of max credit (configurable)
- Stop loss: Based on spread width
- Time-based: 0DTE positions auto-close before market close
- **No Greeks-based exit** (e.g., exit if delta exceeds X)
- **No rolling logic** — positions are closed and re-entered

**Cooldown:** Proverbs guardrails provide 5-minute cooldown after 3 consecutive losses (recently implemented in WISDOM V3 phase).

### 4.4 Confidence Inflation (1.2x multiplier)

**FOUND in 3 bot-specific advice methods:**
```python
# Line 2779 (FORTRESS), 2896 (CORNERSTONE), 3021 (LAZARUS)
confidence=min(1.0, base_pred['win_probability'] * 1.2)
```

This artificially inflates reported confidence by 20%. A model outputting 0.75 win probability gets reported as 0.90 confidence. This doesn't affect the TRADE/SKIP decision (which uses raw `win_probability`) but it misleads downstream consumers and logging. **SOLOMON's confidence (line 3437) correctly uses `direction_confidence` without inflation.**

### 4.5 Post-ML Probability Manipulation

After `_get_base_prediction()` returns the ML probability, the bot-specific methods apply manual adjustments:

| Condition | Adjustment | Effect |
|-----------|------------|--------|
| GEX POSITIVE | +3% to win_probability | Double-counts GEX input |
| GEX NEUTRAL + between walls | +5% to win_probability | Double-counts GEX input |
| GEX NEGATIVE | -2% to win_probability | Double-counts GEX input |
| Between walls | +10% to IC suitability | Redundant with `gex_between_walls` feature |
| Claude hallucination HIGH | -5% to win_probability | External check — reasonable |
| Claude hallucination MEDIUM | -2% to win_probability | External check — reasonable |

The GEX adjustments are problematic because `gex_regime_positive`, `gex_between_walls`, and `gex_distance_to_flip_pct` are already ML features. Adding +3%/+5% after the model has already factored GEX in destroys calibration. If the model learned GEX means +3%, the post-adjustment makes it effectively +6%.

---

## SECTION 5: RISK MANAGEMENT AUDIT

### 5.1 Position Sizing

**Multi-layer sizing:**
1. **Kelly Criterion** (primary): Monte Carlo Kelly sizing that survives 95% of simulations
2. **Config fallback**: Fixed `risk_per_trade_pct` from config table
3. **Thompson Sampling**: Dynamic weight (0.5x-2.0x) based on bot's recent performance across all bots

```python
# Execution: base_contracts * thompson_weight
adjusted_contracts = int(base_contracts * clamped_weight)
return max(1, min(adjusted_contracts, self.config.max_contracts))
```

**Max position capped** at `self.config.max_contracts`.
**Max 1 open position** for 0DTE bots (FORTRESS checks `open_positions > 0`).

### 5.2 Portfolio-Level Risk

**Concentration:** Each bot trades a single underlying (SPY or SPX). No multi-underlying risk.

**Correlation risk across bots:** Proverbs tracks `correlated_bots_active` and reports correlation risk level (LOW/MEDIUM/HIGH). However, this is **informational only** — Prophet doesn't reduce sizing based on it. The comment in code explicitly says:
```python
# NOTE: Proverbs is information-only and does NOT affect sizing
# Prophet is the sole authority for all trading decisions
```

**Tail risk:** No explicit tail risk modeling. The VIX EXTREME regime (>35) triggers SKIP for IC and reduced sizing for directional. But there's no portfolio-level stress test or VaR calculation.

**Margin management:** Not tracked by Prophet. Executor handles margin via `max_contracts` limit and capital-based position sizing.

### 5.3 Options-Specific Risk Checks

| Risk Type | Handled? | Details |
|-----------|----------|---------|
| **Pin risk near expiry** | PARTIAL | 0DTE positions auto-close before market close. No specific pin-strike avoidance logic. |
| **Early assignment** | N/A | SPX is European-style (cash-settled). SPY is American but positions are 0DTE. |
| **Liquidity risk** | IMPLICIT | Only trades SPY/SPX which are highly liquid. No per-strike liquidity check. |
| **Event risk (FOMC/NFP/CPI)** | NOT IMPLEMENTED | CLAUDE.md mentions it but no code exists. Prophet has no economic calendar integration. |
| **Volatility crush** | NOT HANDLED | For long options (SOLOMON directional), post-event IV crush is not modeled. |
| **Friday 0DTE risk** | HANDLED | SOLOMON applies Friday filter: -5% probability, TRADE_REDUCED cap, 0.5x size |
| **Weekend gap risk** | PARTIAL | Proverbs reports weekend gap prediction (INFO ONLY), Prophet doesn't act on it |

---

## SECTION 6: BACKTEST INTEGRITY AUDIT

### 6.1 Backtest Realism

**Slippage model:** At the execution layer, real bid/ask quotes from Tradier are used. This is **better than most backtests** — it captures actual spread costs. However, the CHRONICLES backtest data (`zero_dte_backtest_trades`) used for training uses estimated fills, not actual bid/ask.

**Fill assumptions:** Live trading uses bid/ask (conservative). Backtest training data uses mid-price or estimated fills.

**Commission and fees:** Not explicitly modeled in Prophet's training data. The executor tracks fees separately.

**Market impact:** Not modeled, but position sizes are small relative to SPY/SPX liquidity.

### 6.2 Statistical Validity

**Sample size:** 7,246 trades from `zero_dte_backtest_trades` — this is a **strong sample** for a binary classifier. Sufficient for reliable Sharpe and win rate estimates.

**Win rate vs payoff ratio:**
- ~89% win rate with IC strategies
- Wins are small (credit captured), losses are large (spread width - credit)
- This asymmetric payoff is characteristic of short premium strategies
- The model needs to identify the 11% of conditions where losses occur — which it CANNOT do without class imbalance handling

**Brier score:** Computed on training data (in-sample). The reported Brier is meaninglessly optimistic.

```python
# Line 4459-4460 — Brier on TRAINING data
y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
brier = brier_score_loss(y, y_proba_full)
```

**Expected Brier impact:** Based on WISDOM V3, computing Brier on held-out CV folds typically shows ~0.05-0.15 higher (worse) Brier than in-sample. This is the actual calibration quality the live system experiences.

### 6.3 Regime Analysis

**Strategy recommendation includes regime awareness:**
- Bull trend + Positive GEX → IC
- Bear trend + Negative GEX → Directional
- Extreme VIX → SKIP
- Low VIX → Directional preference

**Regime analysis in `analyze_strategy_performance()`:** Prophet has a method (line 2257) that queries outcomes by VIX regime and GEX regime. However, this is only available as an API endpoint — it doesn't feed back into training or threshold selection.

**Missing regime backtesting:** No evidence that Prophet's performance has been analyzed across different market regime periods (2020 crash, 2022 bear, 2023 bull, 2024 chop).

---

## SECTION 7: EXECUTION & INFRASTRUCTURE AUDIT

### 7.1 Execution Quality

**Broker:** Tradier (production API for live, sandbox for paper)
**Order types:** Market orders via Tradier multi-leg API
**Latency:** Signal → order within the same 5-minute scan cycle
**Partial fills:** Handled with retry logic:
```python
# Retry closing the call leg up to 3 times with exponential backoff
for attempt in range(3):
    time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
```

### 7.2 System Reliability

**Failover:** No explicit failover. If Render restarts, the model reloads from PostgreSQL (persists across deploys).

**Model staleness:** Tracked with `_get_hours_since_training()` and `_is_model_fresh(max_age_hours=24)`. Stale models trigger retraining. Version checks every 5 minutes via `_check_and_reload_model_if_stale()`.

**Logging:** Excellent. Every prediction request, ML output, and decision is logged via `ProphetLiveLog` with full data flow tracing:
- INPUT stage: All market context fields
- ML_OUTPUT stage: Win probability, top factors, probabilities
- DECISION stage: Final advice, risk %, reasoning, Claude analysis

**Monitoring:** `/api/prophet/health` endpoint reports model freshness, training metrics, and pending outcomes.

---

## SECTION 8: OUTPUT — FINDINGS & RECOMMENDATIONS

### 8.1 Findings Summary

#### CRITICAL — Actively Degrading P&L (Fix Immediately)

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| C1 | **No class imbalance handling** | `self.model.fit(X_train, y_train)` — no `sample_weight`. Lines 4441, 5288. | Model outputs ~0.89 for all inputs. SKIP threshold (0.45) never triggers. Prophet effectively approves ALL trades. Every losing trade that should have been skipped costs the full spread width ($500-$1,000). |
| C2 | **Hardcoded 0.45/0.65 thresholds on 89% base rate** | Lines 1465-1466. `_get_advice_from_probability()` line 4022. | SKIP < 0.45 and TRADE_FULL >= 0.65 are meaningless when the model's output distribution is centered at ~0.89. The thresholds need to be relative to the learned base rate. |
| C3 | **price_change_1d training/inference mismatch** | Line 4246: `(close_price - open_price) / open_price * 100`. Live uses prior day. | The model learns from a signal (same-day return) it cannot see in production. This could inflate backtest accuracy by ~0.5-1% and create spurious feature importance for `price_change_1d`. |
| C4 | **1.2x confidence inflation** | Lines 2779, 2896, 3021: `confidence=min(1.0, base_pred['win_probability'] * 1.2)` | Reported confidence is 20% higher than actual probability. A 0.75 probability is logged as 0.90 confidence. Misleads monitoring, dashboards, and any downstream system that reads `confidence`. |

#### HIGH IMPACT — Leaving Profit on the Table (Fix Next Iteration)

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| H1 | **V2 features computed but never trained** | Line 4416: `feature_cols = self.FEATURE_COLS` (V1 only). V2 defined at line 1382 with 22 features. | 11 valuable features (VIX regime encoding, IC suitability, trend score, psychology) are computed every training run and discarded. These could improve the IC-vs-directional decision quality. |
| H2 | **Integer day_of_week** | FEATURE_COLS line 1370: `'day_of_week'` | Model treats Mon(0) as inherently different from Fri(4) by magnitude, not just category. sin/cos cyclical encoding eliminates this artificial distance. |
| H3 | **Brier score on training data** | Lines 4459-4460: Brier computed on `X_scaled` after `model.fit(X_scaled, y)` | The only calibration metric is meaninglessly optimistic. Real out-of-sample calibration could be 0.05-0.15 worse. Cannot assess whether probabilities are trustworthy. |
| H4 | **Post-ML probability manipulation** | Lines 2639-2658: +3/+5/-2% adjustments to `win_probability` based on GEX regime | GEX regime is already an ML input feature. Adding manual adjustments double-counts the signal and destroys isotonic calibration. With a well-trained model, these should be removed entirely. |
| H5 | **UNIQUE(trade_date, bot_name) loses intraday trades** | `prophet_predictions` and `prophet_training_outcomes` tables | FORTRESS scans every 5 minutes and can trade multiple times per day. Only the LAST prediction/outcome per day is stored. ML feedback loop learns from a fraction of actual trades. |

#### IMPROVEMENT — Performance Enhancement (Nice to Have)

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| I1 | **No VRP feature** | Feature list has no IV - realized vol spread | VRP is the core profit driver for Iron Condors. Prophet decides IC-vs-Directional without knowing if premium is rich or cheap. |
| I2 | **No event calendar** | CLAUDE.md mentions FOMC/CPI/NFP but no code exists | Event days create outsized gap risk. No position-size reduction or skip logic before FOMC. |
| I3 | **win_rate_30d short horizon** | Line 4231: 30-trade lookback | Creates recency bias. Matches WISDOM's old design. Should be 60d for consistency. |
| I4 | **Calibration on leaked data** | Line 4456: `CalibratedClassifierCV(self.model, cv=3).fit(X_scaled, y)` after final fit | Base model has seen all data; isotonic calibration's internal CV is partially fitting on data the model has memorized. |
| I5 | **No WISDOM→Prophet signal fusion** | WISDOM and Prophet predict independently with no ensemble | Two models making separate predictions with potential conflicts. WISDOM's win_prob could be fed as a Prophet feature. |
| I6 | **VALOR outcomes not recorded** | `trading/valor/trader.py`: "Future: Call prophet.update_outcome()" | Missing data from VALOR's trades weakens Prophet's feedback loop. |

### 8.2 Expected Impact on P&L

| Fix | Expected P&L Impact | Confidence |
|-----|---------------------|------------|
| Class imbalance + adaptive thresholds (C1+C2) | **HIGH** — The model will learn to skip the ~11% of trades that lose. Each avoided loss saves ~$500-$1,000 per spread width. With ~7,000 trades/year and 11% loss rate, even identifying 20% of losses saves ~$77K-$154K. | Medium-High |
| Remove confidence inflation (C4) | **LOW direct** — Doesn't change trade decisions, but fixes reporting accuracy | High |
| Fix price_change_1d (C3) | **LOW-MEDIUM** — Removes a noise signal that may be getting weight in the model | Medium |
| Add V2/V3 features (H1) | **MEDIUM** — More features for the model to discriminate wins/losses, especially VIX regime and suitability scores | Medium |
| Remove post-ML manipulation (H4) | **MEDIUM** — Restores calibration quality, prevents double-counting | Medium |
| Add VRP feature (I1) | **MEDIUM** — Captures the fundamental IC profit driver | Medium |
| Fix UNIQUE constraint (H5) | **MEDIUM** — More training data improves model quality over time | Low-Medium |

### 8.3 Quick Wins (Highest Impact-to-Effort Ratio)

**1. Add `sample_weight` to `.fit()` calls**
```python
# Compute class weights
n_pos = y_train.sum()
n_neg = len(y_train) - n_pos
weights = np.where(y_train == 1, 1.0, n_pos / max(n_neg, 1))
self.model.fit(X_train, y_train, sample_weight=weights)
```
Applies to `train_from_chronicles()` (line 4441), `train_from_live_outcomes()` (line 5288), and the final fit (line 4454). **Expected effort: 30 minutes. Expected impact: HIGHEST.**

**2. Make thresholds adaptive relative to base rate**
```python
self._base_rate = y.mean()  # Store after training
self.low_confidence_threshold = self._base_rate - 0.15  # SKIP below this
self.high_confidence_threshold = self._base_rate - 0.05  # TRADE_FULL above this
```
Same approach as WISDOM V3. **Expected effort: 15 minutes. Expected impact: HIGH.**

**3. Remove 1.2x confidence inflation**
```python
# Change from:
confidence=min(1.0, base_pred['win_probability'] * 1.2)
# To:
confidence=base_pred['win_probability']
```
Three locations (lines 2779, 2896, 3021). **Expected effort: 5 minutes. Expected impact: LOW (accuracy fix).**

### 8.4 Architecture Recommendation

**Keep the current model, modify features and training:**

1. **GradientBoostingClassifier is fine** — the model class isn't the problem. sklearn GBC with isotonic calibration is appropriate for this task. No need to switch to XGBoost for Prophet (WISDOM already uses XGBoost for its own predictions).

2. **Do NOT merge WISDOM and Prophet** — they serve different purposes. WISDOM predicts individual trade outcomes; Prophet recommends strategy type and bot-specific parameters. Keeping them separate is correct.

3. **Consider feeding WISDOM's output as a Prophet feature** — Prophet could receive WISDOM's `win_probability` as an input signal, creating a lightweight ensemble. This would be a V3+ improvement.

4. **The rule-based strategy recommendation logic is GOOD** — `get_strategy_recommendation()` with VIX/GEX scoring is intuitive and doesn't depend on the broken ML model. It should be preserved as-is.

5. **Remove post-ML probability manipulation** — The +3%/+5% GEX adjustments after the ML prediction should be eliminated once class imbalance is fixed. Let the model learn these relationships instead of hardcoding them.

6. **Long-term: add event calendar** — FOMC/CPI/NFP binary features would improve the model's ability to reduce exposure on high-risk days. This is a multi-day project, not a quick win.

---

## APPENDIX: Prophet vs WISDOM Comparison

| Dimension | WISDOM | Prophet |
|-----------|--------|---------|
| **File** | `quant/fortress_ml_advisor.py` | `quant/prophet_advisor.py` |
| **Size** | ~1,300 lines | ~5,600 lines |
| **Model** | XGBoost (XGBClassifier) | sklearn GradientBoostingClassifier |
| **Role** | Win probability for individual trades | Strategy type + bot-specific advice |
| **Called from** | `signals.py` (signal generation) | `trader.py` (trade execution) |
| **Features (V3)** | 13: VRP, cyclical day, win_rate_60d | 11: integer day, win_rate_30d, no VRP |
| **Class imbalance** | FIXED (scale_pos_weight) | **NOT FIXED** |
| **Thresholds** | Adaptive (base_rate - 0.15/0.05) | **Hardcoded (0.45/0.65)** |
| **Brier score** | Held-out CV folds | **Training data (in-sample)** |
| **Confidence** | Raw probability (no inflation) | **1.2x inflated** |
| **Training data** | 3 sources (CHRONICLES + Prophet outcomes + bot positions) | 3 sources (DB backtests + live outcomes + CHRONICLES) |

---

*Full audit completed using ML Trading Bot Audit Framework v1.0*
*Generated 2026-02-10 — AlphaGEX ML Bot Orchestration project*
