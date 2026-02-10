# AlphaGEX Bot Audit Framework - Findings Report

**Audit Date**: February 10, 2026
**Methodology**: Source code deep-dive against 91-question audit framework
**Bots Audited**: 9 trading bots + 4 ML advisory systems

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Bot-by-Bot Audit Cards](#bot-by-bot-audit-cards)
   - [FORTRESS](#fortress---spy-0dte-iron-condor)
   - [SOLOMON](#solomon---spy-0dte-directional-spreads)
   - [GIDEON](#gideon---aggressive-directional-spreads)
   - [ANCHOR](#anchor---conservative-spx-iron-condor)
   - [SAMSON](#samson---aggressive-spx-iron-condor)
   - [JUBILEE](#jubilee---box-spread-synthetic-borrowing)
   - [VALOR](#valor---mes-futures-scalping)
   - [AGAPE](#agape---eth-micro-futures)
   - [AGAPE-SPOT](#agape-spot---multi-ticker-247-spot)
3. [ML Advisory Systems Audit](#ml-advisory-systems-audit)
   - [Prophet Advisor](#prophet-advisor---central-decision-maker)
   - [Fortress ML Advisor](#fortress-ml-advisor---iron-condor-specialist)
   - [GEX Probability Models (WATCHTOWER/GLORY)](#gex-probability-models-watchtowerglory)
   - [Proverbs Enhancements](#proverbs-enhancements---risk-management)
4. [Cross-Bot Analysis](#cross-bot-analysis)
   - [Overlap & Redundancy Map](#overlap--redundancy-map)
   - [Risk Control Gaps](#risk-control-gaps)
   - [Logging Completeness Matrix](#logging-completeness-matrix)
5. [Scorecards](#scorecards)
6. [Priority Action Items](#priority-action-items)

---

## Executive Summary

### What's Working Well

1. **Logging is comprehensive** - Every bot logs full audit trails: market context, ML predictions, signal reasoning, and outcomes. You CAN reconstruct any trade decision from the database.

2. **Prophet feedback loops are real** - Outcomes are recorded back to Prophet with prediction IDs, enabling actual ML learning from live results.

3. **Code architecture is consistent** - All bots follow the same 5-file pattern (trader/models/signals/db/executor), making maintenance predictable.

4. **Asset class diversification** - SPY options, SPX options, MES futures, ETH futures, crypto spot. Genuine diversification across instruments.

### Critical Problems Found

1. **NO daily loss limits on most bots** - FORTRESS, ANCHOR, SAMSON have no hard circuit breaker. A bad day could accumulate unlimited losses across multiple trades.

2. **Prophet is a single point of failure** - ALL 9 bots defer to Prophet as "god." If Prophet's model degrades, every bot degrades simultaneously. No independent decision-making exists.

3. **ANCHOR and SAMSON are 92% identical code** - ~4,000 lines of duplicated code with only parameter differences. Bug fixes in one don't automatically apply to the other.

4. **FORTRESS ML Advisor is partially orphaned** - Trained on Chronicles backtests but only used by 3 of 9 bots. Redundant with Prophet for IC trades.

5. **No systematic prediction tracking in production** - Models train on backtests but don't systematically measure prediction accuracy vs actual outcomes to detect model drift.

6. **Several "safety filters" are warnings only** - SOLOMON's confidence check, R:R ratio check, and VIX filter are all bypassed when Prophet says TRADE. These aren't filters; they're cosmetic logging.

---

## Bot-by-Bot Audit Cards

---

### FORTRESS - SPY 0DTE Iron Condor

**File**: `trading/fortress_v2/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | 0DTE Iron Condor spreads on SPY, one position per day |
| Trading decisions | WHEN to trade, WHAT strikes, HOW MANY contracts, WHEN to exit |
| If turned off 30 days | ~30 potential trades missed. Loss of feedback loop data for Prophet retraining |

#### Phase 2: Model Architecture

| Question | Answer |
|----------|--------|
| Model type | **Hybrid**: Prophet (GradientBoosting) + Fortress ML (XGBoost) |
| Actual model class | `sklearn.ensemble.GradientBoostingClassifier` (Prophet), `xgb.XGBClassifier` (FortressML) |
| Rule-based or ML? | **ML** - genuine trained models with calibrated probabilities |
| Input features (11) | vix, day_of_week, price, price_change_1d, expected_move_pct, win_rate_30d, vix_percentile_30d, vix_change_1d, gex_normalized, gex_regime_positive, gex_distance_to_flip_pct, gex_between_walls |
| Output | Binary classification (win/loss) → calibrated probability (0-1) + advice enum |
| Prediction horizon | 0DTE (same day, expires at market close) |
| Train/test split | `TimeSeriesSplit(n_splits=5)` - correct for time series |
| Training data | Chronicles backtests + live outcomes |

#### Phase 3: Signal Quality

| Question | Answer |
|----------|--------|
| Signals per day | ~1 (max 3 allowed by config, practically 1 at a time) |
| Hard filters | Prophet must say TRADE_FULL/TRADE_REDUCED/ENTER; VIX must be < 50 |
| Soft filters (warnings only) | Min credit ($0.02), confidence level |
| Confidence scoring | Prophet win_probability (0-1), calibrated via isotonic regression |
| Strike selection | SD-based math: MIN_SD_FLOOR = 1.5 SD from spot (put rounds DOWN, call rounds UP) |

**RED FLAG**: `win_rate_30d` is hardcoded to `0.70` in the ML feature input (`signals.py:345`). This means the model ALWAYS sees 70% historical win rate regardless of actual performance. This is a feature leak / stale input.

#### Phase 4: Logging & Transparency

| Question | Answer |
|----------|--------|
| Logs every signal? | YES - via `log_fortress_scan()` |
| Logs input features? | YES - oracle_confidence, oracle_reasoning, oracle_top_factors, strike_selection, market data |
| Logs outcomes? | YES - three systems: Prophet, Proverbs Enhanced, Thompson Sampling |
| Can reconstruct WHY? | YES - position row stores oracle_confidence, oracle_reasoning, oracle_top_factors, oracle_use_gex_walls |
| Outcome linked to prediction? | YES - prediction_id links Prophet prediction to position to outcome |

#### Phase 5: Risk Controls

| Control | Status |
|---------|--------|
| Max position size | 75 contracts (hardcoded cap) |
| Risk per trade | 15% of capital ($15K on $100K) |
| Daily loss limit | **NOT IMPLEMENTED** - `get_daily_realized_pnl()` exists but never checked |
| Circuit breaker | **REMOVED** - Solomon/Proverbs imported but OPTIONAL |
| Flash crash protection | VIX > 50 blocks only. No gap risk mitigation |
| Force exit | 2:50 PM CT (10 min before close) |
| Profit target | 50% of credit received |

**CRITICAL**: No daily loss limit. Three losing trades = $22,500 potential loss (3 x 75 contracts x $100 max loss).

#### Phase 6: Code Quality

| Issue | Status |
|-------|--------|
| Error handling | GOOD - retry with exponential backoff for Tradier, graceful fallbacks for GEX/ML |
| Data feed failure | GOOD - returns BLOCKED signal when no market data; estimation fallback for pricing |
| Hardcoded values | **12+ thresholds hardcoded**: 1.5 SD floor, $0.02 min credit, 50% profit target, 2:50 PM force exit, VIX 50 block, $2 spread width |

#### Execution Mode Note

FORTRESS uses **SANDBOX Tradier** even in "LIVE" mode (`executor.py:224-244`). All trades are paper with production API quotes.

---

### SOLOMON - SPY 0DTE Directional Spreads

**File**: `trading/solomon_v2/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | 0DTE directional spreads (Bull Call / Bear Put) on SPY |
| Trading decisions | Direction (BULLISH/BEARISH), strike selection, position sizing, exit timing |
| If turned off 30 days | ~20-40 directional trades missed |

#### Phase 2: Model Architecture

| Question | Answer |
|----------|--------|
| Model type | **Hybrid**: 5 GEX Probability Models (XGBoost) + Prophet (GradientBoosting) |
| Input features (15+) | spot_price, vix, call_wall, put_wall, gex_regime, net_gex, flip_point, day_of_week, gex_normalized, gex_distance_to_flip_pct, gex_between_walls, expected_move_pct, vix_percentile_30d, vix_change_1d, price_change_1d, win_rate_30d |
| Output | Direction (BULLISH/BEARISH) + confidence (0-1) + win_probability (0-1) |
| Prediction horizon | 0DTE (same day) |

#### Phase 3: Signal Quality

| Question | Answer |
|----------|--------|
| Signals per day | Up to 5 (max_daily_trades = 5, max_open_positions = 3) |
| Hard filter | Prophet must say TRADE. **All other filters bypassed when Prophet approves** |
| VIX filter | min 12, max 35 - BUT bypassed if Prophet says TRADE |
| GEX wall proximity | 1.0% threshold - BUT bypassed if Prophet says TRADE |
| GEX ratio asymmetry | min 1.2 bearish / max 0.85 bullish - BUT bypassed if Prophet says TRADE |
| Confidence check | min 0.50 - **WARNING ONLY, does NOT block trades** |
| R:R ratio check | min 1.5 - **WARNING ONLY, does NOT block trades** |

**RED FLAG**: Every safety filter except "Prophet says TRADE" is either bypassed or a warning. The signal generation has ONE effective gate: Prophet's advice. If Prophet is wrong, there are no backstops.

#### Phase 4: Logging

| Question | Answer |
|----------|--------|
| Logs every signal? | YES - `solomon_signals` table + scan activity |
| Missing from logs | vix_percentile, vix_change_1d, price_change_1d, win_rate_30d, gex_normalized, distance_to_flip - fetched for ML but NOT persisted in position record |
| Outcome tracking | YES - Prophet + Proverbs + Learning Memory (three feedback loops) |

**GAP**: 6 ML input features are used for prediction but not stored in the position record, making post-trade feature analysis incomplete.

#### Phase 5: Risk Controls

| Control | Status |
|---------|--------|
| Risk per trade | 2% ($2K on $100K) - CONSERVATIVE |
| Max contracts | 50 (hardcoded cap) |
| Max open positions | 3 simultaneously |
| Max daily trades | 5 |
| Daily loss limit | Via Proverbs Enhanced (external, thresholds not in SOLOMON code) |
| Consecutive loss limit | Via Proverbs Enhanced |
| Force exit | 2:50 PM CT |
| Stop loss | 50% of max loss |
| Profit target | 50% of max profit |

SOLOMON has the **best risk control set** of all bots (2% risk, 3-position limit, 5-trade daily cap).

---

### GIDEON - Aggressive Directional Spreads

**File**: `trading/gideon/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Aggressive clone of SOLOMON with relaxed parameters for 0DTE SPY directional spreads |
| If turned off 30 days | Higher-frequency trades missed, but SOLOMON covers same strategy conservatively |

#### Key Differences from SOLOMON

| Parameter | SOLOMON | GIDEON | Impact |
|-----------|---------|--------|--------|
| risk_per_trade_pct | 2% | 3% | 50% more risk |
| max_daily_trades | 5 | 8 | 60% more trades |
| max_open_positions | 3 | 4 | 33% more concurrent |
| min_win_probability | 50% | 48% | Lower threshold |
| VIX range | 12-35 | 12-30 | Narrower (stops earlier) |

#### Overlap Assessment

**GIDEON is essentially SOLOMON with different config values.** Same ML models, same signal generation flow, same strike selection, same exit rules. The code duplication is near-total.

**Recommendation**: This should be a SOLOMON preset/profile, not a separate bot with duplicated code.

---

### ANCHOR - Conservative SPX Iron Condor

**File**: `trading/anchor/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Conservative daily SPX Iron Condor, $10 spread width, max 1 trade/day |
| Trading decisions | When to enter IC, strike selection (1.0 SD minimum), position sizing, exit timing |

#### Phase 2: Model Architecture

| Question | Answer |
|----------|--------|
| Model type | **Same as FORTRESS**: Prophet + Fortress ML Advisor (XGBoost) |
| Input features | **Identical 11 features** to FORTRESS |
| Output | Same: win_probability + advice + confidence |

**RED FLAG**: `win_rate_30d` hardcoded to `0.70` (same bug as FORTRESS). Does not use actual ANCHOR win rate.

#### Phase 3: Signal & Risk

| Parameter | Value |
|-----------|-------|
| Spread width | $10 (SPX-appropriate) |
| SD multiplier | 1.0 (minimum 1 SD from spot) |
| Risk per trade | 10% |
| Max contracts | 100 |
| Max open positions | 5 |
| Min credit | $0.75 per spread |
| Min win probability | 42% |
| VIX skip threshold | 32 |
| Profit target | 50% |
| Stop loss | 2x entry credit |
| Daily loss limit | **NOT IMPLEMENTED** |

---

### SAMSON - Aggressive SPX Iron Condor

**File**: `trading/samson/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Aggressive multi-trade SPX Iron Condor, $12 spread width, multiple trades/day |
| Key difference from ANCHOR | Tighter strikes (0.8 SD), more positions, faster profit-taking |

#### ANCHOR vs SAMSON Comparison

| Parameter | ANCHOR | SAMSON | Impact |
|-----------|--------|--------|--------|
| Spread width | $10 | $12 | SAMSON wider spreads |
| SD multiplier | 1.0 | 0.8 | SAMSON tighter = more risk |
| Max open positions | 5 | 10 | SAMSON 2x exposure |
| Risk per trade | 10% | 15% | SAMSON 50% more |
| Min credit | $0.75 | $0.50 | SAMSON accepts lower premiums |
| Min win probability | 42% | 40% | SAMSON slightly lower bar |
| Profit target | 50% | 30% | SAMSON takes profits faster |
| VIX skip | 32 | 40 | SAMSON trades in higher vol |
| Cooldown | None (1/day) | 30 min | SAMSON re-enters after cooldown |

#### Code Duplication: 92%

**ANCHOR and SAMSON share 92% identical code.** The differences are entirely parametric:
- Same signal generation logic
- Same ML advisor integration (identical features)
- Same executor (identical position sizing formula)
- Same database schema (different table names)
- Same exit rules (different thresholds)

**Every difference could be expressed as a config preset.** This is the single biggest maintenance debt in the codebase.

**Consolidation Proposal**:
```
trading/spx_iron_condor/  (single bot, preset-driven)
├── trader.py
├── models.py
├── signals.py
├── executor.py
├── db.py
└── presets.py  ← ANCHOR_PRESET, SAMSON_PRESET
```

---

### JUBILEE - Box Spread Synthetic Borrowing

**File**: `trading/jubilee/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Borrow capital via SPX box spreads at sub-margin rates, deploy to IC bots |
| Model type | **Deterministic pricing** (no ML). Box value = strike_width x 100, always |
| Prediction horizon | 90+ DTE (weeks/months, not intraday) |

#### Unique Value

JUBILEE is **completely unique** in the AlphaGEX ecosystem:
- Only system doing synthetic borrowing
- Only system with 90+ DTE positions (everything else is 0DTE)
- Coordinates capital deployment across FORTRESS/ANCHOR/SAMSON
- Transparent borrowing cost tracking (daily cost, annual rate, vs alternatives)

#### Risk Controls

| Control | Status |
|---------|--------|
| Margin management | Tracks current_margin_used, margin_cushion |
| Early assignment risk | Per-position assessment (SPX=LOW) |
| DTE management | Rolls positions when DTE < 30 days |
| Capital deployment limits | Reserved cash buffer + allocation splits |

#### Assessment

JUBILEE is the **highest-value, lowest-risk bot** in the ecosystem. It doesn't make directional bets - it provides infrastructure (cheaper borrowing) that amplifies the other bots' returns. This is worth preserving even if all other bots were paused.

---

### VALOR - MES Futures Scalping

**File**: `trading/valor/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Ultra-aggressive MES (Micro E-mini S&P 500) futures scalping using GEX regime signals |
| Schedule | Every 1 minute during futures hours (Sun 5PM - Fri 4PM CT) |
| Strategy | POSITIVE gamma = mean reversion (fade moves). NEGATIVE gamma = momentum (trade breakouts) |

#### Phase 2: Model Architecture

| Question | Answer |
|----------|--------|
| Model type | **Rule-based with Bayesian updating** - NOT traditional ML |
| Honest label | GEX regime classifier + Bayesian win probability tracker |
| Input features | GEX regime, flip_point, call_wall, put_wall, ATR, VIX, recent win/loss by direction |
| Output | FuturesSignal: direction (LONG/SHORT), confidence, stop_loss, profit_target |

**Honest Assessment**: VALOR is rule-based logic (if POSITIVE gamma → fade; if NEGATIVE → momentum) with a Bayesian layer that adjusts confidence from historical outcomes. Calling it "ML" would be misleading - it's smart heuristics with feedback.

#### Unique Features

- **Stop-and-Reverse (SAR)**: Reverses position when stopped out (captures momentum)
- **Direction Tracker**: Pauses a direction after losses (2-scan cooldown)
- **No-loss trailing stops**: Activation at +0.75 pts, trail 0.75 pts behind best price
- **Bayesian win probability**: Learns per-GEX-regime win rates from live trades

#### Risk Controls

| Control | Status |
|---------|--------|
| Risk per trade | 1% (LOWEST of all bots) |
| Stop loss | 5.0 MES points ($25/contract) |
| Trailing stop | 0.75 points after +0.75 pts profit |
| Loss streak pause | 5 minutes after 3 consecutive losses |
| Daily loss limit | **NOT IMPLEMENTED** |
| Max positions | 100 (effectively unlimited) |

**CONCERN**: 100 max positions with 1-minute scan frequency could accumulate rapidly. Even at 1% risk per trade, 20 open positions = 20% portfolio exposure.

---

### AGAPE - ETH Micro Futures

**File**: `trading/agape/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Crypto futures trading on CME Micro Ether (/MET) using crypto microstructure signals |
| Model type | **Market microstructure classifier** (rule-based, not ML) |
| Input features | Funding rate, LS ratio, liquidation clusters, squeeze risk, max pain level |
| Schedule | Every 5 min, Sun 5PM - Fri 4PM CT |

#### Honest Assessment

AGAPE translates GEX concepts into crypto equivalents:
- Funding rate regime → directional bias (like GEX regime)
- Long/short liquidation levels → support/resistance (like gamma walls)
- LS ratio → positioning imbalance (like dealer positioning)

This is **creative and well-designed** but it's rule-based pattern matching, not ML. The "crypto GEX" analogy is a framework for decision-making, not a trained model.

#### Risk Controls

| Control | Status |
|---------|--------|
| Risk per trade | 5% (AGGRESSIVE) |
| Max contracts | 10 /MET |
| Max positions | 20 concurrent |
| Stop loss | 1.5% from entry |
| Loss streak pause | 3 min after 3 losses |
| Daily loss limit | **NOT IMPLEMENTED** |
| Max hold | 24 hours |

---

### AGAPE-SPOT - Multi-Ticker 24/7 Spot

**File**: `trading/agape_spot/`

#### Phase 1: Identity

| Question | Answer |
|----------|--------|
| Purpose | Long-only 24/7 Coinbase spot trading across 4 tickers: ETH-USD, XRP-USD, SHIB-USD, DOGE-USD |
| Model type | Same crypto microstructure as AGAPE, adapted for spot (long-only) |
| Schedule | Every 5 min, 24/7/365 |

#### Unique Value

- Only 24/7/365 bot (operates weekends)
- Long-only (no leverage, no liquidation risk)
- Multi-ticker with per-ticker state management
- Per-ticker capital allocation: ETH ($5K), others ($1K each)

#### Per-Ticker Position Sizing

| Ticker | Per-Trade Qty | Starting Capital |
|--------|--------------|-----------------|
| ETH-USD | 0.1 ETH | $5,000 |
| XRP-USD | 100 XRP | $1,000 |
| SHIB-USD | 1,000,000 SHIB | $1,000 |
| DOGE-USD | 500 DOGE | $1,000 |

---

## ML Advisory Systems Audit

---

### Prophet Advisor - Central Decision Maker

**File**: `quant/prophet_advisor.py` (5,620 lines)

#### Identity

Prophet is THE decision authority for all 9 trading bots. Every bot explicitly defers to Prophet with comments like "Prophet is god" and "When Prophet says TRADE, we TRADE. Period."

#### Model Details

| Question | Answer |
|----------|--------|
| Model class | `sklearn.ensemble.GradientBoostingClassifier` |
| Calibration | `CalibratedClassifierCV(method='isotonic', cv=3)` |
| Feature scaler | `StandardScaler` |
| Train/test split | `TimeSeriesSplit(n_splits=5)` - correct for time series |
| Test size | 20% |

#### Feature Sets

**V1 (7 features)**: vix, vix_percentile_30d, vix_change_1d, day_of_week, price_change_1d, expected_move_pct, win_rate_30d

**V2 (21 features)** adds: win_rate_7d, 5 VIX regime dummies, ic_suitability, dir_suitability, regime_trend_score, regime_vol_percentile, psychology_fear_score, psychology_momentum, gex_normalized, gex_regime_positive, gex_distance_to_flip_pct, gex_between_walls

#### Training Data Sources

1. Chronicles backtest results (`train_from_chronicles()`)
2. Live trading outcomes (`train_from_live_outcomes()`)
3. Database backtests (`train_from_database_backtests()`)

#### Staleness Tracking

| Metric | Implementation |
|--------|---------------|
| Hours since training | `_get_hours_since_training()` - tracks delta from `_model_trained_at` |
| Freshness check | `_is_model_fresh(max_age_hours=24.0)` |
| Auto-reload | Checks DB for newer model every 300 seconds |
| When stale | Returns degraded fallback prediction, adjusts confidence |
| Auto-retrain | **MANUAL ONLY** - no scheduled retraining |

#### Critical Issues

1. **Single point of failure**: If Prophet degrades, ALL 9 bots degrade simultaneously
2. **No scheduled retraining**: Requires manual trigger to retrain
3. **Stale model degrades silently**: Returns lower-confidence predictions but doesn't stop trading
4. **No A/B testing**: Can't compare Prophet V1 vs V2 in production

---

### Fortress ML Advisor - Iron Condor Specialist

**File**: `quant/fortress_ml_advisor.py` (1,178 lines)

#### Model Details

| Question | Answer |
|----------|--------|
| Model class | `xgb.XGBClassifier` with n_estimators=150, max_depth=4 |
| Calibration | `CalibratedClassifierCV(method='isotonic', cv=3)` |
| Features | Same 11 features as Prophet V1 + GEX additions |
| Training data | Chronicles backtests only |
| Min retrain samples | 50 new samples required |

#### Issues

1. **Only used by 3 of 9 bots** (FORTRESS, ANCHOR, SAMSON)
2. **Redundant with Prophet** for IC trade decisions
3. **No staleness tracking** - no `hours_since_training`, no freshness check
4. **Falls back to heuristics when stale** (`_fallback_prediction()`) without any alert

#### Recommendation

Either:
- **Retire entirely** and let Prophet handle all IC decisions (simpler, less maintenance)
- **Make it truly differentiated** with IC-specific features that Prophet doesn't have (e.g., spread-specific Greeks, historical IC performance by strike distance)

---

### GEX Probability Models (WATCHTOWER/GLORY)

**File**: `quant/gex_probability_models.py` (1,762 lines)
**Integration**: Used by WATCHTOWER (gamma visualization) and GLORY (gamma analysis/ML training)

#### 5 Sub-Models

| Model | Type | Output | Validation Status |
|-------|------|--------|-------------------|
| Direction Probability | XGBoost Classifier | UP/DOWN/FLAT | Standard |
| Flip Gravity | XGBoost Classifier | moved_toward_flip (0/1) | H4: Only 44.4% confirmed (LOW) |
| Magnet Attraction | XGBoost Classifier | touched_magnet (0/1) | H5: 89% confirmed (GOOD) |
| Volatility Estimate | XGBoost Regressor | price_range_pct | Standard |
| Pin Zone Behavior | XGBoost Classifier | closed_in_pin_zone (0/1) | H3: 55.2% confirmed (WEAK) |

#### Issues

1. **Flip Gravity model is weak** - Only 44.4% accuracy. Comment in code: "may have limited predictive power"
2. **Pin Zone model barely above random** - 55.2% is marginally better than coin flip
3. **Auto-trains weekly** (Sunday 6 PM CT) but models could be 7 days stale during volatile weeks
4. **Fallback is 100% distance-based** - when models not trained, predictions revert to simple math

---

### Proverbs Enhancements - Risk Management

**File**: `quant/proverbs_enhancements.py` (2,921 lines)

#### Components

| Component | Type | Purpose |
|-----------|------|---------|
| ConsecutiveLossMonitor | Rule-based | Auto-kill after 3 consecutive losses |
| DailyLossMonitor | Rule-based | Auto-kill on $5K daily loss or 5% account loss |
| TimeOfDayAnalyzer | Statistical | Best/worst hours per bot |
| VersionComparer | Statistical | Performance comparison across code versions |
| CrossBotCorrelation | Statistical | Correlation between bot performances |
| WeekendPreCheck | Rule-based | Risk analysis for upcoming week |
| ABTest | Framework | Experiment framework for config changes |

#### Critical Issue

Proverbs is **imported as optional** in most bots. From FORTRESS `executor.py`:
```python
PROVERBS_ENHANCEMENTS_AVAILABLE = False  # Optional import
try:
    from quant.proverbs_enhancements import ConsecutiveLossTracker, DailyLossTracker
    PROVERBS_ENHANCEMENTS_AVAILABLE = True
except ImportError:
    pass
```

If the import fails silently, the bot runs **without any risk management**. This should be a required dependency, not optional.

---

## Cross-Bot Analysis

### Overlap & Redundancy Map

```
SPY 0DTE OPTIONS
├── FORTRESS ──── Iron Condor (conservative)
├── SOLOMON ──── Directional Spreads (conservative)
└── GIDEON ───── Directional Spreads (aggressive)
    └── GIDEON ≈ SOLOMON with relaxed params (REDUNDANT)

SPX OPTIONS
├── ANCHOR ───── Iron Condor (conservative)
└── SAMSON ───── Iron Condor (aggressive)
    └── SAMSON ≈ ANCHOR with relaxed params (REDUNDANT, 92% code overlap)

SPX BOX SPREADS
└── JUBILEE ──── Synthetic Borrowing (UNIQUE, no overlap)

FUTURES
└── VALOR ────── MES Scalping (UNIQUE, no overlap)

CRYPTO
├── AGAPE ────── ETH Micro Futures (leveraged)
└── AGAPE-SPOT ─ Multi-ticker Spot (unleveraged)
    └── Shared microstructure framework but different instruments
```

**Consolidation Opportunities**:

| Current | Proposed | Lines Saved |
|---------|----------|-------------|
| ANCHOR + SAMSON | Single SPX IC bot with presets | ~4,000 lines |
| SOLOMON + GIDEON | Single SPY Directional bot with presets | ~3,000 lines |

### Risk Control Gaps

| Bot | Daily Loss Limit | Consecutive Loss Kill | Max Concurrent Risk |
|-----|------------------|-----------------------|---------------------|
| FORTRESS | **MISSING** | Optional (Proverbs) | 15% per trade, 1 position |
| SOLOMON | Proverbs (external) | Proverbs (external) | 2% per trade, 3 positions = 6% |
| GIDEON | Proverbs (external) | Proverbs (external) | 3% per trade, 4 positions = 12% |
| ANCHOR | **MISSING** | Optional (Proverbs) | 10% per trade, 5 positions = 50% |
| SAMSON | **MISSING** | Optional (Proverbs) | 15% per trade, 10 positions = 150% (!!) |
| JUBILEE | N/A (infrastructure) | N/A | Margin-tracked |
| VALOR | **MISSING** | 5-min pause after 3 losses | 1% per trade, 100 positions = 100% |
| AGAPE | **MISSING** | 3-min pause after 3 losses | 5% per trade, 20 positions = 100% |
| AGAPE-SPOT | **MISSING** | Per-ticker pause | Per-ticker, unleveraged |

**SAMSON theoretical max concurrent risk: 150% of capital.** At 15% risk per trade x 10 positions, SAMSON could theoretically have 1.5x its capital at risk simultaneously. This needs a hard portfolio-level cap.

### Logging Completeness Matrix

| Bot | Signals Logged | Features Logged | Outcomes Logged | Prophet Link | Full Reconstruct? |
|-----|---------------|-----------------|-----------------|-------------|-------------------|
| FORTRESS | YES | YES (full) | YES (3 systems) | YES (prediction_id) | YES |
| SOLOMON | YES | PARTIAL (6 features missing) | YES (3 systems) | YES | MOSTLY |
| GIDEON | YES | YES | YES | YES | YES |
| ANCHOR | YES | YES | YES | YES | YES |
| SAMSON | YES | YES | YES | YES | YES |
| JUBILEE | YES | YES (borrowing costs) | YES | N/A | YES |
| VALOR | YES | YES (GEX regime) | YES | Optional | YES |
| AGAPE | YES | YES (microstructure) | YES | Optional | YES |
| AGAPE-SPOT | YES | YES (per-ticker) | YES | Optional | YES |

---

## Scorecards

### Rating Scale
- **5**: Production-grade, no issues
- **4**: Functional, minor improvements needed
- **3**: Works but has gaps that should be addressed
- **2**: Significant problems, consider pausing
- **1**: Dangerous gaps, pause immediately

### FORTRESS
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | ML trained, but no production accuracy tracking |
| Logging & Transparency | 5 | Full audit trail, 3 feedback loops |
| Regime Awareness | 4 | GEX regime + VIX, but only VIX>50 blocks |
| Signal Quality | 4 | SD-based strikes fixed after Jan losses |
| Unique Value | 4 | Only SPY IC bot |
| P&L Attribution | 3 | Linked predictions, but no systematic accuracy report |
| Code Quality | 4 | Clean architecture, good error handling |
| Risk Controls | 2 | **No daily loss limit, optional Proverbs** |
| **TOTAL** | **29/40** | Functional but risk controls need work |

### SOLOMON
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | Dual ML system, no production accuracy tracking |
| Logging & Transparency | 4 | Good but 6 ML features not persisted |
| Regime Awareness | 4 | Prophet handles regime, multiple data sources |
| Signal Quality | 3 | **All filters bypassed when Prophet approves** |
| Unique Value | 3 | Directional spreads, but GIDEON is same thing |
| P&L Attribution | 3 | Three feedback systems |
| Code Quality | 4 | Good error handling, graceful fallbacks |
| Risk Controls | 4 | Best control set: 2% risk, 3-position limit |
| **TOTAL** | **28/40** | Solid but signal quality bypasses are concerning |

### GIDEON
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | Same as SOLOMON |
| Logging & Transparency | 4 | Same as SOLOMON |
| Regime Awareness | 4 | Same as SOLOMON |
| Signal Quality | 2 | Lowest min_win_prob (48%), most relaxed filters |
| Unique Value | 1 | **SOLOMON clone with different params** |
| P&L Attribution | 3 | Same systems as SOLOMON |
| Code Quality | 4 | Same as SOLOMON |
| Risk Controls | 3 | 3% risk, 4 positions = 12% concurrent |
| **TOTAL** | **24/40** | Redundant - consolidate with SOLOMON |

### ANCHOR
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | Same ML as FORTRESS |
| Logging & Transparency | 5 | Full audit trail |
| Regime Awareness | 4 | Prophet + GEX |
| Signal Quality | 4 | Conservative 1.0 SD, $0.75 min credit |
| Unique Value | 3 | SPX IC conservative, but SAMSON overlaps |
| P&L Attribution | 3 | Linked predictions |
| Code Quality | 4 | Clean |
| Risk Controls | 2 | **No daily loss limit, 50% theoretical max exposure** |
| **TOTAL** | **28/40** | Good bot but needs daily loss limit |

### SAMSON
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | Same ML as ANCHOR/FORTRESS |
| Logging & Transparency | 5 | Full audit trail |
| Regime Awareness | 4 | Prophet + GEX |
| Signal Quality | 3 | 0.8 SD tighter strikes, $0.50 min credit |
| Unique Value | 2 | **92% code duplicate of ANCHOR** |
| P&L Attribution | 3 | Linked predictions |
| Code Quality | 4 | Clean |
| Risk Controls | 1 | **150% theoretical max exposure, no daily cap** |
| **TOTAL** | **25/40** | Risk controls are dangerous |

### JUBILEE
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 4 | Deterministic pricing (box value = strike width) |
| Logging & Transparency | 5 | Full borrowing cost transparency |
| Regime Awareness | 3 | Interest rate environment only |
| Signal Quality | 4 | Clear favorability check (box rate < margin rate) |
| Unique Value | 5 | **Only box spread system - completely unique** |
| P&L Attribution | 4 | Clear cost/benefit tracking |
| Code Quality | 4 | Good |
| Risk Controls | 4 | Margin tracking, DTE management, assignment risk |
| **TOTAL** | **33/40** | Best bot in the ecosystem |

### VALOR
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 3 | Bayesian updating but no formal backtest |
| Logging & Transparency | 4 | Full GEX regime logging |
| Regime Awareness | 5 | Core design is regime-based (positive=fade, negative=momentum) |
| Signal Quality | 4 | SAR + direction tracker + trailing stops |
| Unique Value | 5 | **Only futures bot** |
| P&L Attribution | 3 | Per-trade tracking |
| Code Quality | 4 | Good |
| Risk Controls | 2 | **100 max positions, no daily loss limit** |
| **TOTAL** | **30/40** | Good concept, needs position limits |

### AGAPE
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 2 | Crypto microstructure is untested hypothesis |
| Logging & Transparency | 4 | Full microstructure audit trail |
| Regime Awareness | 4 | Funding rate regime + LS ratio |
| Signal Quality | 3 | Novel but unproven |
| Unique Value | 4 | Only crypto futures bot |
| P&L Attribution | 3 | Per-trade tracking |
| Code Quality | 4 | Good, ported from VALOR patterns |
| Risk Controls | 2 | **5% risk, 20 positions = 100% exposure** |
| **TOTAL** | **26/40** | Needs statistical validation badly |

### AGAPE-SPOT
| Dimension | Score | Notes |
|-----------|-------|-------|
| Statistical Edge Verified | 2 | Same unproven hypothesis as AGAPE |
| Logging & Transparency | 4 | Per-ticker audit trail |
| Regime Awareness | 4 | Same as AGAPE |
| Signal Quality | 3 | Long-only reduces signal space |
| Unique Value | 4 | Only 24/7/365 bot, multi-ticker |
| P&L Attribution | 3 | Per-ticker tracking |
| Code Quality | 4 | Good |
| Risk Controls | 3 | Unleveraged, per-ticker limits |
| **TOTAL** | **27/40** | Better risk profile than AGAPE due to no leverage |

---

## Priority Action Items

### IMMEDIATE (This Week)

1. **Add daily loss limits to ALL bots**
   - FORTRESS, ANCHOR, SAMSON, VALOR, AGAPE: No hard daily loss circuit breaker exists
   - Proverbs has the logic but it's imported as OPTIONAL
   - **Fix**: Make Proverbs a required dependency. If import fails, bot should refuse to start

2. **Cap SAMSON concurrent risk**
   - 15% risk x 10 positions = 150% theoretical exposure
   - **Fix**: Add portfolio-level risk cap (e.g., 50% max concurrent exposure)

3. **Fix hardcoded win_rate_30d = 0.70**
   - FORTRESS (`signals.py:345`), ANCHOR, SAMSON all pass hardcoded 70% to ML model
   - **Fix**: Query actual 30-day win rate from closed trades table

### SHORT-TERM (This Month)

4. **Consolidate ANCHOR + SAMSON** into single SPX IC bot with preset configs
   - Eliminates ~4,000 lines of duplicate code
   - Bug fixes apply to both instantly
   - Create ANCHOR_PRESET and SAMSON_PRESET in a presets module

5. **Consolidate SOLOMON + GIDEON** into single SPY Directional bot with presets
   - Same rationale as above, ~3,000 lines saved

6. **Add production prediction accuracy tracking**
   - Prophet predictions need a daily accuracy dashboard
   - Compare predicted win_probability vs actual outcomes
   - Alert when accuracy drops below training accuracy by >10%

7. **Make SOLOMON safety filters real**
   - Confidence check, R:R ratio check, VIX filter are currently warnings only
   - Either make them hard blocks OR remove the code (don't pretend they're filters)

### MEDIUM-TERM (This Quarter)

8. **Eliminate Prophet single-point-of-failure**
   - If Prophet degrades, all 9 bots degrade together
   - Options: (a) independent fallback per bot, (b) ensemble of Prophet versions, (c) bot-specific models

9. **Retire or differentiate Fortress ML Advisor**
   - Currently redundant with Prophet for IC trades
   - Either remove it or add IC-specific features Prophet doesn't have

10. **Statistical validation of AGAPE/AGAPE-SPOT**
    - Crypto microstructure hypothesis is untested
    - Run backtests on historical funding rate / LS ratio data
    - Establish minimum sample size before live capital

11. **Reduce VALOR max positions**
    - 100 max positions at 1-minute frequency is excessive
    - Recommend 5-10 max concurrent

12. **Address GEX Probability Models weak sub-models**
    - Flip Gravity: 44.4% (below random for binary)
    - Pin Zone: 55.2% (barely above random)
    - Either improve these or disable them to prevent noise

### LONG-TERM

13. **Build unified bot framework with preset system**
    - All IC bots share 90%+ code
    - All directional bots share 90%+ code
    - Create `BaseIronCondorBot` and `BaseDirectionalBot` with presets

14. **Implement A/B testing infrastructure**
    - Proverbs has ABTest framework but it's not wired into production
    - Use it to test parameter changes (e.g., ANCHOR 50% vs 40% profit target)

15. **Monte Carlo simulation for portfolio-level risk**
    - Individual bot risk controls exist but no portfolio-level view
    - What's the probability of ruin across ALL bots simultaneously?

---

## Appendix: Questions for Brainstorming

These are open questions the audit raised that don't have clear answers in the code:

1. **Prophet retraining**: Should it auto-retrain weekly? What triggers retraining today?
2. **Capital allocation**: Thompson Sampling adjusts per-bot weights, but is anyone reviewing the allocations?
3. **Regime mismatch**: What happens when GEX models say POSITIVE gamma but Prophet says SKIP? Who wins?
4. **Crypto hypothesis**: Is there published evidence that funding rates predict price direction reliably enough to trade?
5. **Box spread risk**: JUBILEE's box spreads are theoretically risk-free at expiration, but early assignment on American-style options would break this. Are SPX options European? (Yes, but worth verifying for any SPY box variants)
6. **Time-of-day edge**: Proverbs tracks best/worst hours per bot. Is this data being used to restrict trading windows?
7. **Inter-bot correlation**: If FORTRESS and ANCHOR both lose on the same day (SPY and SPX correlated), is there a cross-bot circuit breaker?
8. **Backtest vs Live drift**: Is anyone monitoring whether live performance matches Chronicles backtest predictions?

---

*Generated by source code audit on February 10, 2026*
*Files analyzed: ~45 Python files across trading/, quant/, backend/api/routes/*
*Total lines reviewed: ~30,000+*
