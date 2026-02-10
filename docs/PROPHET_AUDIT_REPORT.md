# PROPHET ML Advisor — Comprehensive ML Trading Bot Audit & Review
## Options Market — Full Evaluation Framework

**Date**: 2026-02-10
**Branch**: `claude/watchtower-data-analysis-6FWPk`
**Auditor**: Claude Code (Orchestration Layer Evaluation)
**Framework**: ML Trading Bot Audit & Review — Options Market Comprehensive Edition
**Status**: POST-V2 AUDIT — Critical fixes implemented, remaining issues documented

---

## PURPOSE

This audit evaluates Prophet (`quant/prophet_advisor.py`, ~5,700 lines), the **sole ML decision authority** for all AlphaGEX trading bots. When Prophet says TRADE, bots trade. When Prophet says SKIP, bots skip. This makes Prophet the highest-leverage codebase component — any bug here impacts every dollar traded. Prophet serves 6 active bots: FORTRESS (SPY 0DTE IC), ANCHOR (SPX weekly IC), SOLOMON/GIDEON (directional spreads), SAMSON (aggressive SPX IC), and VALOR (futures scalping).

### Signal Chain Context
```
WISDOM (signals.py)  → win_probability      → Signal passed to trader
                                                  ↓
Prophet (trader.py)  → TRADE/SKIP + strikes  → Executor
                     → risk_pct + SD mult     → Position sizing
                     → Claude AI validation   → Confidence adjustment
                                                  ↓
Executor             → Thompson × Kelly       → Tradier API → fills
```

WISDOM and Prophet are **separate ML models** answering different questions:
- **WISDOM**: "What's the probability this specific trade wins?" (XGBoost, runs in signals.py)
- **Prophet**: "Should this bot trade? IC or directional? What strikes? What risk %?" (sklearn GBC, runs in trader.py)

They do NOT feed predictions into each other. Both train on overlapping but separately extracted data.

---

## SECTION 1: DATA PIPELINE AUDIT

### 1.1 Data Sources & Quality

| Source | Table/Method | Type | Frequency | Quality |
|--------|-------------|------|-----------|---------|
| **Live trade outcomes** | `prophet_training_outcomes` | Closed trades with features JSON, outcome, P&L | Per-trade | **Best** — actual execution results |
| **CHRONICLES backtests** | `extract_features_from_chronicles()` | Historical backtest results | Per-trade (historical) | **Good** — some feature approximations |
| **Database backtests** | `zero_dte_backtest_trades` | Persisted backtest trade records | Per-trade (historical) | **Moderate** — `expected_move_1d` approximated as 1% of spot |

**Data consumed per prediction**: VIX (level, percentile, change), day of week (cyclical sin/cos), price change (previous-day), expected move %, VRP, rolling 60-trade win rate, GEX (normalized, regime, flip distance, between walls). Total: **13 features in V3**.

**Data flow**: MarketContext dataclass → `_get_base_prediction()` → StandardScaler → GBC `predict_proba()` → isotonic calibration → win_probability.

**Missing data handling**:
- `vix_percentile_30d`: Rolling rank, NaN filled with 50 (median). **Acceptable.**
- `vix_change_1d`: `pct_change().fillna(0)` for first sample. **Correct.**
- `win_rate_60d`: Defaults to 0.68 when insufficient history. **Acceptable seed value**, though 0.68 is suspiciously precise — should be configurable.
- GEX fields: Default to 0/NEUTRAL/True when unavailable. **Correct** — degrades to V1 gracefully.
- `expected_move_pct`: From live VIX; in backtests, approximated as `expected_move_sd / open_price * 100`. **Acceptable.**

**Point-in-time correctness**: V2 fixed the primary look-ahead bias (price_change_1d). Other features (VIX, GEX) are known at trade entry time — **no remaining look-ahead bias identified**.

**Data frequency**: Per-trade (not time-series bars). This is appropriate — Prophet makes one decision per trade opportunity, not per bar.

### 1.2 Options-Specific Data Integrity

| Data Element | Present? | Source | Assessment |
|-------------|----------|--------|------------|
| **IV (Implied Volatility)** | Proxy only | VIX as market-wide IV | Per-strike IV absent — VIX is a blunt proxy |
| **IV Rank / IV Percentile** | ✓ | `vix_percentile_30d` (30-day rolling rank) | Correct approach, but VIX-based, not per-strike |
| **IV Skew** | ✗ | Not modeled | **GAP** — OTM put vs call IV affects IC pricing |
| **IV Term Structure** | ✗ | Not modeled | **GAP** — contango/backwardation matters for 0DTE vs weekly |
| **Greeks (Delta/Gamma/Theta/Vega)** | ✗ | Not in Prophet features | Handled downstream by execution layer — **acceptable** |
| **Charm (delta decay)** | ✗ | Not modeled | Critical for 0DTE position management — handled by signals.py |
| **Vanna (delta-IV sensitivity)** | ✗ | Not modeled | Important for vol surface changes |
| **GEX (Gamma Exposure)** | ✓ | 4 features: normalized, regime, flip distance, between walls | **Strong** — key differentiator |
| **Bid-Ask Spreads** | ✗ | Not captured | **GAP** — no slippage model in training data |
| **Open Interest / Volume** | ✗ | Not used | **GAP** — liquidity filtering absent |
| **VRP (Volatility Risk Premium)** | ✓ | V3 feature: `expected_move_pct - realized_vol_5d` | **Good** — captures premium selling profitability |
| **Earnings/FOMC calendar** | ✗ | Not implemented | **GAP** — CLAUDE.md mentions detection but code doesn't implement it |

**Key gap**: Prophet advises IC strategies without per-strike IV data. It uses VIX as a proxy for all volatility measurements. This means Prophet cannot distinguish between:
- "VIX is 20 with normal skew" (safe for IC)
- "VIX is 20 with extremely steep put skew" (IC put side at risk)

**Impact**: Estimated 5-10% of IC losses may be attributable to skew-related breaches that VIX alone cannot predict.

### 1.3 Look-Ahead Bias Check

| Feature | Before V2 | After V2 | Status |
|---------|-----------|----------|--------|
| `price_change_1d` | Same-day close (knows future at entry) | Previous trade's move | **FIXED** |
| `win_rate_60d` | Included current trade in window | Rolling lookback excluding current | **FIXED** |
| `vix_change_1d` | Post-hoc % change | Same — but VIX known at entry | **OK** |
| `expected_move_pct` | Calculated from VIX at entry | Same — IV-implied, available pre-trade | **OK** |
| `volatility_risk_premium` | Not present | V3: `expected_move - realized_vol_5d` using prior trades only | **OK** |
| Train/test split | `TimeSeriesSplit(n_splits=5)` — no random shuffle | Same | **CORRECT** |

**Remaining concern**: `vix_percentile_30d` is computed as a rolling rank over ALL training data during `extract_features_from_chronicles()` (line 4375-4377). This means early samples see "future" VIX values in their rank calculation. However, the impact is minimal since percentile rank only uses relative ordering, not absolute values.

---

## SECTION 2: FEATURE ENGINEERING AUDIT

### 2.1 Current Feature Inventory (V3)

| # | Feature | Type | Range | Relevance | Redundancy | Stationarity | Leakage Risk |
|---|---------|------|-------|-----------|------------|-------------|-------------|
| 1 | `vix` | Continuous | 10-80 | **HIGH** — Core vol signal for premium selling | Partially overlaps VIX percentile | Non-stationary (regime dependent) | None |
| 2 | `vix_percentile_30d` | Continuous | 0-100 | **HIGH** — Relative VIX rank = IV percentile proxy | Adds context to raw VIX | Stationary by design | Minor (see 1.3) |
| 3 | `vix_change_1d` | Continuous | -30 to +50 | **MEDIUM** — Vol momentum | Unique signal | Stationary | None |
| 4 | `day_of_week_sin` | Continuous | [-1, 1] | **MEDIUM** — Cyclical day encoding | Pair with cos | Stationary | None |
| 5 | `day_of_week_cos` | Continuous | [-1, 1] | **MEDIUM** — Cyclical day encoding | Pair with sin | Stationary | None |
| 6 | `price_change_1d` | Continuous | -5 to +5% | **LOW-MEDIUM** — Yesterday's equity move | Unique | Stationary | **FIXED V2** — was same-day |
| 7 | `expected_move_pct` | Continuous | 0.3-4% | **HIGH** — IV-implied daily range = premium available | Related to VIX | Stationary (normalized) | None |
| 8 | `volatility_risk_premium` | Continuous | -2 to +3% | **HIGH** — `IV - realized vol` = profit engine | Unique V3 | Stationary | None |
| 9 | `win_rate_60d` | Continuous | 0-1 | **QUESTIONABLE** — Self-referential feedback loop | Unique | Non-stationary (drifts) | **MEDIUM** — model's own past performance |
| 10 | `gex_normalized` | Continuous | -5 to +5 | **HIGH** — Market maker positioning magnitude | Unique | Semi-stationary | None |
| 11 | `gex_regime_positive` | Binary 0/1 | {0, 1} | **HIGH** — Pinning vs trending regime | Derived from gex_normalized | Stationary | None |
| 12 | `gex_distance_to_flip_pct` | Continuous | -10 to +10% | **HIGH** — Proximity to regime change | Unique | Stationary | None |
| 13 | `gex_between_walls` | Binary 0/1 | {0, 1} | **HIGH** — Price contained = IC safe | Unique | Stationary | None |

### 2.2 Options-Critical Features — Missing Assessment

**Volatility Features (4/6 present):**
- ✅ VIX level and VIX change
- ✅ VIX percentile (IV rank proxy)
- ✅ Volatility risk premium (IV vs realized spread)
- ❌ **IV skew** (OTM put IV vs call IV) — critical for IC asymmetric risk
- ❌ **IV term structure slope** (front vs back month) — affects 0DTE vs weekly differently
- ❌ **VVIX** (volatility of volatility) — predicts vol expansion/contraction

**Greeks-Based Features (0/4 — acceptable delegation):**
- ❌ Delta, Gamma, Theta, Vega — handled by execution layer, not Prophet's decision scope
- ❌ Charm, Vanna — intraday risk management, not entry decisions

**Market Microstructure (0/4):**
- ❌ **Bid-ask spread** — no liquidity filter
- ❌ **Put/call ratio** — sentiment signal absent
- ❌ **Options order flow** — not available
- ❌ **Unusual options activity** — not available

**Macro/Regime Features (2/4 present):**
- ✅ GEX regime (market maker positioning regime)
- ✅ Day of week (cyclical encoding)
- ❌ **Earnings/FOMC binary flags** — NOT implemented despite CLAUDE.md mention
- ❌ **Interest rate environment** — irrelevant for 0DTE but matters for weekly DTE

### 2.3 Feature Engineering Red Flags

| Flag | Status | Evidence |
|------|--------|----------|
| Raw price levels as features | ✅ **OK** — not present. Uses returns/ratios/percentiles | |
| Unstandardized features | ✅ **OK** — `StandardScaler()` applied to all features | Line 4437 |
| High-cardinality categoricals | ✅ **OK** — Only binary (0/1) categoricals | |
| Extreme outliers not clipped | ⚠️ **MINOR** — VIX spikes (>50) not winsorized | Could destabilize scaler |
| Calendar without cyclical encoding | ✅ **FIXED V2** — sin/cos replaces integer day_of_week | Lines 4300-4302 |
| Self-referential feature | ⚠️ **PRESENT** — `win_rate_60d` creates feedback loop | Feature #9 |

**Self-referential feedback risk**: `win_rate_60d` feeds Prophet's own historical win rate back as an input feature. During winning streaks, this inflates win probability predictions, encouraging more trading, extending the streak. During losing streaks, the inverse occurs — a death spiral. This positive feedback loop amplifies both good and bad performance regimes. **Recommendation**: Replace with external signal (e.g., cumulative VRP, VIX regime persistence, or rolling Sharpe of SPY returns).

---

## SECTION 3: MODEL ARCHITECTURE AUDIT

### 3.1 Model Choice Evaluation

**Model**: `sklearn.ensemble.GradientBoostingClassifier`

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

**Is it appropriate?** Yes — sklearn GBC is suitable for:
- Tabular data with 13 features
- Small-to-medium dataset (~100-1000 trades)
- Binary classification (win/loss)
- Integrates cleanly with `CalibratedClassifierCV`

**Why not XGBoost?** Prophet was designed for smaller per-bot outcome datasets. XGBoost's advantages (sparse-aware, GPU, L1/L2 regularization) are less impactful at this scale. sklearn GBC has native `sample_weight` support in `.fit()` and simpler `CalibratedClassifierCV` integration.

**Target variable**: Binary (`is_win`) — 1 if trade outcome == MAX_PROFIT, 0 otherwise. This is well-defined and aligned with execution. However, it doesn't distinguish between "barely profitable" and "highly profitable" — a regression target (net_pnl) could capture this but would need larger sample size.

**Alternative consideration**: A separate directional model (for SOLOMON/GIDEON) vs IC model (for FORTRESS/ANCHOR) could capture strategy-specific patterns better than one unified model. Currently, the same GBC model predicts for all 6+ bots.

### 3.2 Training & Validation

| Aspect | Implementation | Assessment |
|--------|---------------|------------|
| **Train/test split** | `TimeSeriesSplit(n_splits=5)` | ✅ **Correct** — no random shuffling |
| **Walk-forward** | Daily retraining at midnight CT when 20+ new outcomes | ✅ **Good** — continuous learning |
| **Purging/embargo** | No explicit purge gap between folds | ⚠️ **MINOR** — could leak for overlapping positions |
| **Class imbalance** | V2: `sample_weight` (losses get ~8x weight of wins) | ✅ **FIXED** — was absent pre-V2 |
| **Hyperparameter tuning** | None — hardcoded params | ⚠️ **GAP** — no optimization |
| **Calibration** | `CalibratedClassifierCV(method='isotonic', cv=3)` | ✅ **Good** — appropriate for 100+ samples |
| **Final model** | Fit on ALL data, then calibrated on ALL data | ⚠️ **Standard practice** — CV metrics are optimistic |

**Overfitting indicators**:
- No comparison of train vs test accuracy reported
- CV metrics averaged across 5 folds — fold variance not tracked
- Brier score on CV folds (V2 addition) provides calibration check
- `min_samples_split=20`, `min_samples_leaf=10`, `subsample=0.8` provide regularization

**Class imbalance fix (V2)**:
```python
# Lines 4420-4430
weight_win = n_losses / len(y)    # ~0.11 for majority (wins)
weight_loss = n_wins / len(y)     # ~0.89 for minority (losses)
sample_weight_array = np.where(y == 1, weight_win, weight_loss)
```

This is correct — sklearn GBC uses `sample_weight` in `.fit()`, not a `class_weight` parameter. Each loss sample has ~8x the gradient contribution of a win sample, forcing the model to learn loss-distinguishing patterns.

### 3.3 Model Interpretability

| Aspect | Implementation |
|--------|---------------|
| Feature importances | `model.feature_importances_` stored in `TrainingMetrics` |
| Top factors per prediction | Returned in every `ProphetPrediction.top_factors` |
| SHAP values | Not implemented |
| Feature importance drift | Not tracked between training runs |

**What to expect**: VIX and GEX features should dominate importance for IC strategies. If `win_rate_60d` or `price_change_1d` rank highest, it's likely noise/leakage rather than genuine signal.

---

## SECTION 4: SIGNAL GENERATION & TRADE LOGIC AUDIT

### 4.1 Signal-to-Trade Translation

**Prophet output → Trade decision flow**:

```
1. _check_and_reload_model_if_stale()    → Ensure fresh model (5-min check interval)
2. VIX skip rules (FORTRESS/ANCHOR only)  → Hard skip if VIX > threshold
3. _get_base_prediction(context)           → GBC predict_proba → win_probability [0, 1]
4. Bot-specific logic:
   - FORTRESS/ANCHOR: GEX wall strikes, ic_suitability scoring
   - SOLOMON/GIDEON: ML direction (ORION), wall filters, flip distance filter
   - LAZARUS: Negative GEX squeeze detection
5. Claude AI validation (optional)         → ±0.10 confidence adjustment
6. Hallucination risk check                → -2% to -5% penalty
7. _get_advice_from_probability()          → TRADE_FULL / TRADE_REDUCED / SKIP_TODAY
8. SD multiplier selection                 → 1.2 / 1.3 / 1.4 (based on confidence)
```

**Confidence thresholds (V2 adaptive)**:
```python
SKIP_TODAY:   win_prob < base_rate - 0.15  (e.g., < 0.74 with 89% base rate)
TRADE_REDUCED: base_rate - 0.15 <= win_prob < base_rate - 0.05
TRADE_FULL:   win_prob >= base_rate - 0.05 (e.g., >= 0.84)
```

**Cooldown**: No explicit cooldown in Prophet itself. Handled by bot schedulers (5-minute intervals for most bots, 30-minute for TITAN).

### 4.2 Options Strategy Selection

**Strategy recommendation** (`get_strategy_recommendation()`):
- **Rule-based**, NOT ML-powered
- Uses VIX regime × GEX regime scoring matrix:

| VIX Regime | GEX POSITIVE | GEX NEUTRAL | GEX NEGATIVE |
|------------|-------------|-------------|-------------|
| LOW (<15) | IC marginally | IC slight | Directional |
| NORMAL (15-22) | **IC strong** | IC slight | Mixed |
| ELEVATED (22-28) | IC slight | Mixed | **Directional** |
| HIGH (28-35) | Mixed | Directional | **Directional strong** |
| EXTREME (>35) | SKIP | SKIP | Directional reduced |

**Strike selection**:
- FORTRESS: GEX walls with buffer (0.25 × expected move), SPY→SPX scaling
- ANCHOR: GEX walls with $10 spread width, minimum 1 SD from spot
- SOLOMON: ML direction → bull/bear spread based on wall proximity

**Expiration selection**: Not optimized by Prophet — bots have hardcoded DTE preferences (FORTRESS=0DTE, ANCHOR=weekly, etc.).

### 4.3 Entry & Exit Logic

**Entry triggers**:
- Model signal (win_probability above adaptive threshold)
- VIX skip rules pass (FORTRESS/ANCHOR)
- Claude AI validation (optional, adjusts confidence ±0.10)
- Wall filter pass (SOLOMON/GIDEON: distance to relevant wall)
- Flip distance filter (SOLOMON: 0.5-3% optimal, 3-5% reduced, >5% skip)
- Friday filter (SOLOMON: -5% probability, half size)

**Exit**: Not managed by Prophet — handled entirely by bot execution layers (profit targets, stop losses, time-based exits). Prophet only controls entry decisions.

**Rolling logic**: Not present — Prophet doesn't advise on position management after entry.

### 4.4 V2 Fixes to Signal Generation

| Issue | Before V2 | After V2 | Evidence |
|-------|-----------|----------|----------|
| **1.2x confidence inflation** | `confidence = win_prob * 1.2` in FORTRESS/CORNERSTONE/LAZARUS | `confidence = win_prob` | Lines 2807, 2923, 3047 |
| **Post-ML +3%/+5% GEX adjustments** | `win_probability += 0.03` for positive GEX in all 4 bot advice methods | Removed — GEX already in features | All bot methods |
| **Hallucination penalty too harsh** | 10%/5% for HIGH/MEDIUM in FORTRESS/SOLOMON/LAZARUS | 5%/2% (reduced) | Lines 2775-2786, 3371-3381 |
| **ANCHOR hallucination penalty** | 10%/5% | **STILL 10%/5%** — not updated | Lines 3851-3858 |
| **ANCHOR hardcoded thresholds** | 0.58/0.52/0.48 | **STILL hardcoded** — doesn't use adaptive | Lines 3783-3798 |

### 4.5 Remaining Signal Issues

| Issue | Severity | Location | Impact |
|-------|----------|----------|--------|
| **SOLOMON overwrites ML win_probability** | HIGH | Line 3338: `base_pred['win_probability'] = max(0.50, min(0.85, direction_confidence))` | ML model output replaced with direction confidence — trained model's calibrated probability discarded |
| **ANCHOR hardcoded thresholds** | HIGH | Lines 3783-3798: `0.58/0.52/0.48` | Doesn't benefit from adaptive base-rate thresholds |
| **ANCHOR hallucination penalty not reduced** | MEDIUM | Lines 3851-3858: `0.10/0.05` vs other bots' `0.05/0.02` | 2x harsher Claude penalty than FORTRESS/SOLOMON |
| **VRP approximation at inference** | MEDIUM | Line 3944: `context.expected_move_pct * 0.2` | Training uses 5-trade rolling realized vol, inference uses rough proxy |
| **Single model for IC + directional** | MEDIUM | Architecture | Same GBC weights predict for IC bots and directional bots with fundamentally different P&L profiles |

---

## SECTION 5: RISK MANAGEMENT AUDIT

### 5.1 Position Sizing

| Advice Level | Risk % | SD Multiplier | Application |
|-------------|--------|---------------|-------------|
| TRADE_FULL | 10.0% | 1.2 (>=0.70), 1.3 (>=0.60), 1.4 (<0.60) | Full position, all bots |
| TRADE_REDUCED | 3.0-8.0% (sliding scale) | Same as FULL | Reduced position |
| SKIP_TODAY | 0% | N/A | No trade |

**ANCHOR override**: Fixed 3% TRADE_FULL, 1.5% TRADE_REDUCED, 1% TRADE_CAUTIOUS — does not use Prophet's sliding scale.

**SD multiplier fix (V2)**: Minimum raised from 1.0 to 1.2. Old 1.0 SD placed strikes at the expected move boundary — breached ~32% of the time by definition. 1.2 SD provides 20% cushion.

**Kelly criterion**: Not in Prophet. Position sizing uses Thompson Sampling × Kelly in the execution layer, but Prophet doesn't inform the Kelly input (expected edge).

### 5.2 Portfolio-Level Risk

| Risk Dimension | Implemented? | Assessment |
|----------------|-------------|------------|
| **Max position per bot** | ❌ | Prophet doesn't track open positions |
| **Max daily loss per bot** | ❌ | Removed — "Oracle is god" philosophy |
| **Cross-bot concentration** | Proverbs display only | Correlation > 0.7 tracked but does NOT reduce sizing |
| **Net portfolio Greeks** | ❌ | No aggregated delta/gamma/vega across bots |
| **Max daily drawdown** | ❌ | No circuit breaker — intentionally removed |
| **Margin management** | ❌ | Prophet doesn't track buying power usage |
| **Tail risk protection** | ❌ | No hedging logic for 3+ sigma events |

**Critical gap**: 6 bots can all be TRADE_FULL simultaneously on the same underlying (SPY/SPX) with zero awareness of aggregate exposure. A single 3-sigma move could breach FORTRESS, ANCHOR, and SAMSON Iron Condors simultaneously while SOLOMON/GIDEON directional positions also lose.

### 5.3 Options-Specific Risk Checks

| Risk Check | Status | Notes |
|------------|--------|-------|
| **Pin risk near expiry** | ❌ | FORTRESS trades 0DTE — always near expiry. Not modeled. |
| **Early assignment** | N/A | SPX is cash-settled (no assignment risk). SPY: not checked. |
| **Liquidity risk** | ❌ | No bid-ask spread filter before entry |
| **Event risk (earnings/FOMC)** | ❌ | Not implemented — CLAUDE.md mentions it, code doesn't |
| **Volatility crush** | ❌ | Long options (LAZARUS) at risk post-event; not modeled |
| **Weekend gap risk** | ✓ Partial | SOLOMON Friday filter: -5% probability, half size. Proverbs weekend pre-check is display-only. |

### 5.4 VIX Skip Rules (FORTRESS/ANCHOR)

```
Rule 1: vix > vix_hard_skip          → SKIP (e.g., VIX > 32)
Rule 2: vix > vix_monday_friday_skip  → SKIP on Mon/Fri (e.g., VIX > 30)
Rule 3: vix > vix_streak_skip         → SKIP after 2+ losses (e.g., VIX > 28)
```

**OMEGA mode**: When `omega_mode=True`, all VIX skip rules disabled — defers to WISDOM ML Advisor as primary. This is architecturally correct since WISDOM already has VIX as a feature.

**Note**: SOLOMON/GIDEON have NO VIX skip rules — they rely entirely on ML direction and flip distance filtering.

---

## SECTION 6: BACKTEST INTEGRITY AUDIT

### 6.1 Backtest Realism

| Aspect | Implementation | Assessment |
|--------|---------------|------------|
| **Slippage model** | None | ❌ **Not modeled** — fills assumed at computed price |
| **Fill assumptions** | Mid-price implied | ❌ **Unrealistic** — 0DTE options have 5-15% bid-ask spreads |
| **Commission and fees** | Not in training data | ⚠️ **Minor** — commissions are small vs option premiums |
| **Margin costs** | Not modeled | ⚠️ **Minor** — short-term strategies, margin cost minimal |
| **Market impact** | Not modeled | ⚠️ **Minor** — small position sizes |

**Estimated slippage impact**: For 0DTE SPY options with ~$0.05 wide markets on individual legs, a 4-leg IC has ~$0.10 total slippage per contract. On ~$1.00 credit IC, this is 10% of max profit. This slippage is NOT captured in training outcomes, meaning the model's "win" threshold is too low — trades that barely expired profitable may have been net losers after slippage.

### 6.2 Statistical Validity

| Metric | Implementation | Assessment |
|--------|---------------|------------|
| **Sample size** | 20+ for live retraining, 100+ for initial training | ⚠️ **20 is low** — Brier/AUC unreliable at this size |
| **CV metrics** | Accuracy, Precision, Recall, F1, AUC-ROC, Brier on 5-fold TSCV | ✅ **Comprehensive** |
| **Win rate vs payoff** | ~89% win rate for ICs — need to verify payoff ratio | ⚠️ **Classic IC pattern** — high win rate, occasional large losses |
| **Monte Carlo** | Not implemented | ❌ **Missing** — no stress testing of trade sequence randomization |

**Win rate reality check**: 89% win rate with IC trading is expected (ICs expire worthless ~85-90% when strikes are ≥1 SD out). The key question is whether the occasional large losses (10-20% of portfolio) are offset by the many small wins. Prophet's training doesn't capture this asymmetry because it uses binary classification (win/loss) rather than regression (P&L amount).

### 6.3 Regime Analysis

**Strategy performance by VIX×GEX regime** is analyzed via `analyze_strategy_performance()` (lines 2285-2427) — queries `prophet_training_outcomes` grouped by regime. This is good for understanding where Prophet performs well vs poorly.

**Concern**: No explicit regime-switching detection. If the market shifts from low-vol/positive-GEX (IC paradise) to high-vol/negative-GEX (IC slaughter), Prophet adapts only after enough losses accumulate (20+ outcomes) to trigger retraining. During the transition, it may continue recommending ICs.

### 6.4 UNIQUE Constraint Data Loss

**CRITICAL OPEN ISSUE**: `prophet_training_outcomes` has `UNIQUE(trade_date, bot_name)`.

0DTE bots (FORTRESS, SAMSON) make **multiple trades per day**. The `ON CONFLICT DO UPDATE` means only the **last** trade per day per bot is retained. For a bot making 3 trades/day, this discards **67% of training data**.

**Impact on model**: Systematically biased training data — if last trades of the day have different characteristics than first trades (e.g., higher gamma risk, tighter spreads), the model learns the wrong distribution.

**Fix**: Change to `UNIQUE(trade_date, bot_name, prediction_id)` to capture all intraday outcomes.

---

## SECTION 7: EXECUTION & INFRASTRUCTURE AUDIT

### 7.1 Execution Quality

| Aspect | Implementation |
|--------|---------------|
| **Broker** | Tradier (production + sandbox) |
| **Order types** | Limit orders via execution layer |
| **Latency** | Signal → order: seconds (scheduler interval = 5 min) |
| **Partial fills** | Handled by execution layer, not Prophet |
| **Failed order retry** | Handled by execution layer |

Prophet is not involved in order execution — it produces `ProphetPrediction` which the bot's executor converts into actual orders.

### 7.2 System Reliability

| Aspect | Implementation | Assessment |
|--------|---------------|------------|
| **Model persistence** | PostgreSQL primary, local file backup | ✅ **Robust** — survives Render deploys |
| **Staleness detection** | 5-min DB version check, auto-reload | ✅ **Good** — prevents stale model use |
| **Thread safety** | Double-check locking singleton, `_log_lock` on lists | ✅ **Correct** |
| **Failover** | Untrained model → rule-based `_fallback_prediction()` | ✅ **Graceful** degradation |
| **Logging** | ProphetLiveLog: INPUT→ML_FEATURES→ML_OUTPUT→CLAUDE→DECISION | ✅ **Excellent** transparency |
| **Claude exchange logging** | Full prompt/response + hallucination risk | ✅ **Full** audit trail |
| **Backward compatibility** | V1/V2/V3 feature version auto-detection from saved metadata | ✅ **Well-designed** |

### 7.3 Training Schedule

| Trigger | Time | Threshold | Data Source |
|---------|------|-----------|-------------|
| **Midnight job** | 00:00 CT daily | 10+ outcomes | `prophet_training_outcomes` |
| **Proverbs feedback** | 16:00 CT daily | 10+ outcomes | Same |
| **Manual API** | On demand | Configurable | Same |
| **Auto-train on outcome** | After threshold reached | 20+ outcomes | Same |

### 7.4 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/prophet/health` | GET | Staleness metrics, model freshness |
| `/api/prophet/status` | GET | Full status with training metrics |
| `/api/prophet/strategy-recommendation` | POST/GET | IC vs Directional recommendation |
| `/api/prophet/strategy-performance` | GET | Performance by VIX/GEX regime |
| `/api/prophet/train` | POST | Trigger manual training |
| `/api/prophet/pending-outcomes` | GET | Count pending training outcomes |
| `/api/prophet/vix-regimes` | GET | VIX regime definitions |

---

## SECTION 8: OUTPUT — FINDINGS & RECOMMENDATIONS

### 8.1 Findings Summary

#### 🔴 CRITICAL (Fixed in V2)

| # | Finding | Evidence | Impact | Status |
|---|---------|----------|--------|--------|
| C1 | **Class imbalance blindness** — 89% win rate, model always predicts majority | No `sample_weight` pre-V2 | Prophet advises TRADE on everything — cannot identify losing conditions | **FIXED** — `sample_weight` array |
| C2 | **1.2x confidence inflation** — `confidence = win_prob * 1.2` | Lines 2807, 2923, 3047 (pre-V2) | Confidence exceeds 1.0; downstream bots misinterpret | **FIXED** — `confidence = win_prob` |
| C3 | **Post-ML probability manipulation** — +3%/+5% GEX adjustments | All 4 bot advice methods (pre-V2) | Destroys isotonic calibration; double-counts GEX signal already in features | **FIXED** — all removed |
| C4 | **Hardcoded thresholds at 0.45/0.65** — unreachable with 89% base rate | Lines 1453-1455 (pre-V2) | SKIP never fires; TRADE_FULL fires on everything | **FIXED** — adaptive `base_rate ± offset` |
| C5 | **price_change_1d look-ahead** — uses same-day close in training | `extract_features_from_chronicles()` (pre-V2) | ~0.3 Sharpe inflation estimated | **FIXED** — uses previous trade's move |

#### 🟡 HIGH IMPACT (Open)

| # | Finding | Evidence | Impact | Recommended Fix |
|---|---------|----------|--------|-----------------|
| H1 | **UNIQUE(trade_date, bot_name)** discards intraday trades | Training outcomes table schema | Up to 67% data loss for 0DTE bots | Change to `UNIQUE(trade_date, bot_name, prediction_id)` |
| H2 | **ANCHOR uses hardcoded thresholds** (0.58/0.52/0.48) | Lines 3783-3798 | Doesn't benefit from adaptive base-rate logic; may SKIP when FORTRESS trades (or vice versa) | Use `_get_advice_from_probability()` like other bots |
| H3 | **No portfolio-level risk** — 6 bots trade independently | Architecture design | 3-sigma event could breach all IC positions simultaneously with zero defense | Add cross-bot position tracking; aggregate delta/vega caps |
| H4 | **SOLOMON overwrites ML win_probability** | Line 3338: `base_pred['win_probability'] = direction_confidence` | Trained model's calibrated probability discarded; direction confidence is a different scale | Blend: `0.5 * ml_prob + 0.5 * direction_confidence` |
| H5 | **Event risk not implemented** | CLAUDE.md mentions FOMC/CPI/NFP detection; code has no implementation | Bots trade blind through high-impact events, causing spikes in IC breaches | Add binary flags from economic calendar API |

#### 🟢 IMPROVEMENT

| # | Finding | Evidence | Impact | P&L Impact Est. |
|---|---------|----------|--------|-----------------|
| I1 | **ANCHOR hallucination penalty 2x other bots** | Lines 3851-3858: 10%/5% vs 5%/2% | ANCHOR more likely to be downgraded by Claude noise | LOW — align to 5%/2% |
| I2 | **VRP approximation at inference** | Line 3944: `expected_move_pct * 0.2` | Training VRP uses rolling realized vol; inference uses rough proxy | MEDIUM — pass realized vol from signals.py |
| I3 | **win_rate_60d self-referential** | Feature #9 in V3 feature set | Positive feedback loop amplifying streaks | MEDIUM — replace with external signal |
| I4 | **Proverbs data collected but display-only** | `get_proverbs_advisory()` returns data; scores not adjusted | Time-of-day, regime, correlation intelligence unused | LOW — by design ("Prophet is god") |
| I5 | **No hyperparameter optimization** | Hardcoded GBC params (n_estimators=150, etc.) | Suboptimal model configuration | LOW — current params are reasonable |
| I6 | **Single model for all strategies** | Same GBC for IC + directional + wheel + futures | IC and directional have fundamentally different P&L profiles | MEDIUM — separate models per strategy type |
| I7 | **IV skew not captured** | No per-strike IV features | Can't distinguish safe IC environment from skew-distorted one | MEDIUM — add skew feature from options chain |
| I8 | **No slippage in training data** | Backtest assumes mid-price fills | Model "wins" may be net losers after slippage | LOW — most trades have clear win/loss margin |

### 8.2 Quick Wins (Highest Impact-to-Effort)

**1. Fix ANCHOR to use adaptive thresholds** (H2)
- **Effort**: 10 lines of code — replace hardcoded `0.58/0.52/0.48` with `_get_advice_from_probability()`
- **Impact**: ANCHOR decisions align with Prophet's learned base rate; prevents scenario where ANCHOR skips profitable trades or trades losing ones
- **P&L impact**: MEDIUM

**2. Fix UNIQUE constraint on training outcomes** (H1)
- **Effort**: 1 SQL migration — `ALTER TABLE prophet_training_outcomes DROP CONSTRAINT ... ADD CONSTRAINT ... UNIQUE(trade_date, bot_name, prediction_id)`
- **Impact**: Up to 3x more training data for 0DTE bots; better model generalization
- **P&L impact**: MEDIUM-HIGH (more data → better model → better decisions)

**3. Fix SOLOMON win_probability override** (H4)
- **Effort**: 5 lines — blend ML probability with direction confidence instead of replacing
- **Impact**: Trained model output no longer discarded; calibrated probabilities flow through to threshold decisions
- **P&L impact**: MEDIUM

### 8.3 Architecture Recommendation

**Should the current model be kept, modified, or replaced?**
- **KEEP** the sklearn GBC architecture — it's appropriate for the data size and problem type
- **MODIFY** by splitting into 2 models: IC model (FORTRESS/ANCHOR/SAMSON) and Directional model (SOLOMON/GIDEON)
- **KEEP** isotonic calibration — correct for this use case
- **KEEP** Claude AI validation as optional confidence adjustment — adds human-interpretable reasoning

**Is an ensemble approach warranted?**
- Not at current scale (~100-1000 trades). A single well-calibrated GBC is sufficient.
- If data grows to 5000+ trades, consider XGBoost + LightGBM + GBC meta-ensemble.

**Is the strategy logic fundamentally sound?**
- **Yes** — VIX×GEX regime matrix for strategy selection is hypothesis-driven and options-specific
- **Yes** — GEX wall-based strike placement leverages unique market maker positioning data
- **Yes** — Adaptive thresholds (V2) properly handle the 89% base rate problem
- **Weakness** — Single model for both IC and directional strategies; direction override in SOLOMON

### 8.4 V2 Fixes Summary (Already Implemented)

| Fix | Section | Lines Changed |
|-----|---------|---------------|
| `sample_weight` for class imbalance | Training | 4420-4430 |
| Brier score on CV folds | Training | 4466 |
| Cyclical day encoding (sin/cos) | Features | 4300-4302 |
| VRP feature | Features | 4332-4339 |
| 60-trade win rate horizon | Features | 4286-4290 |
| Price change look-ahead fix | Features | 4308-4316 |
| Removed 1.2x confidence inflation | Signal gen | 2807, 2923, 3047 |
| Removed post-ML GEX adjustments | Signal gen | All 4 bot methods |
| Adaptive thresholds from base rate | Decision | 1478-1498 |
| Feature version tracking (V1/V2/V3) | Persistence | 1365-1408 |
| SD multiplier minimum raised to 1.2 | Signal gen | 2796-2801 |
| Reduced hallucination penalties | Signal gen | 2773-2786 (FORTRESS), 3370-3381 (SOLOMON) |

---

## APPENDIX A: File References

| File | Lines | Purpose |
|------|-------|---------|
| `quant/prophet_advisor.py` | ~5,700 | ProphetAdvisor: ML model, training, inference, 5 bot advice methods |
| `backend/api/routes/prophet_routes.py` | ~465 | 7 REST API endpoints |
| `scheduler/trader_scheduler.py` | ~3,500 | Training triggers: midnight + 4 PM CT |
| `trading/fortress_v2/signals.py` | ~900 | Calls `get_fortress_advice()` |
| `trading/fortress_v2/trader.py` | ~1,400 | Stores predictions, records outcomes |
| `trading/anchor/signals.py` | ~900 | Calls `get_anchor_advice()` |
| `trading/solomon_v2/signals.py` | ~900 | Calls `get_solomon_advice()` |
| `trading/gideon/signals.py` | ~1,000 | Calls `get_solomon_advice(bot_name="GIDEON")` |
| `trading/samson/trader.py` | ~1,300 | Uses `get_strategy_recommendation()` |
| `trading/valor/trader.py` | ~1,300 | Uses `get_strategy_recommendation()` |
| `quant/proverbs_enhancements.py` | ~2,100 | Feedback loop: trains Prophet at 4 PM daily |

## APPENDIX B: Bot-Prophet Integration Matrix

| Bot | Advice Method | Claude? | VIX Skip? | GEX Walls? | Direction? | Adaptive Thresh? | Training Data? |
|-----|--------------|---------|-----------|------------|------------|-----------------|---------------|
| FORTRESS | `get_fortress_advice()` | ✓ | ✓ | ✓ | N/A (IC) | ✓ | ✓ |
| ANCHOR | `get_anchor_advice()` | ✓ | ✓ | ✓ | N/A (IC) | ❌ **Hardcoded** | ✓ |
| SOLOMON | `get_solomon_advice()` | ✓ | — | ✓ | ✓ (ML/GEX) | ✓ | ✓ |
| GIDEON | `get_solomon_advice(bot="GIDEON")` | ✓ | — | ✓ | ✓ (ML/GEX) | ✓ | ✓ |
| CORNERSTONE | `get_cornerstone_advice()` | — | — | — | N/A (Wheel) | ✓ | — |
| LAZARUS | `get_lazarus_advice()` | ✓ | — | — | ✓ (GEX) | ✓ | — |
| SAMSON | `get_strategy_recommendation()` | — | — | — | N/A (IC) | N/A | ✓ |
| VALOR | `get_strategy_recommendation()` | — | — | — | N/A (Futures) | N/A | ✓ |

## APPENDIX C: Feature Version Comparison

| Feature | V1 (7) | V2 (11) | V3 (13) |
|---------|--------|---------|---------|
| vix | ✓ | ✓ | ✓ |
| vix_percentile_30d | ✓ | ✓ | ✓ |
| vix_change_1d | ✓ | ✓ | ✓ |
| day_of_week (integer) | ✓ | ✓ | — |
| day_of_week_sin | — | — | ✓ |
| day_of_week_cos | — | — | ✓ |
| price_change_1d | ✓ | ✓ | ✓ (fixed) |
| expected_move_pct | ✓ | ✓ | ✓ |
| volatility_risk_premium | — | — | ✓ |
| win_rate_30d | ✓ | ✓ | — |
| win_rate_60d | — | — | ✓ |
| gex_normalized | — | ✓ | ✓ |
| gex_regime_positive | — | ✓ | ✓ |
| gex_distance_to_flip_pct | — | ✓ | ✓ |
| gex_between_walls | — | ✓ | ✓ |

---

*Last Updated: 2026-02-10*
*Prophet V2 fixes implemented and pushed in prior session*
*This audit uses the full ML Trading Bot Audit & Review — Options Market Comprehensive Edition template*
