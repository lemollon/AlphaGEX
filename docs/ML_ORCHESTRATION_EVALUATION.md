# AlphaGEX ML Orchestration Evaluation
## Complete System Audit & Architecture Assessment

**Author**: Claude Code (Forensic Audit Series)
**Date**: February 10, 2026
**Branch**: `claude/watchtower-data-analysis-6FWPk`
**Scope**: Every ML/AI training system in the codebase

---

## Executive Summary

AlphaGEX contains **18 distinct ML/AI systems** across ~15,000 lines of ML code. After auditing every system, the critical finding is:

**The orchestration layer already exists (OMEGA Orchestrator) but NO TRADING BOT USES IT.**

The entire system suffers from a common pattern: sophisticated infrastructure is built but never wired into the actual trading flow. This report catalogs every system, its status, and provides a concrete wiring plan.

---

## Table of Contents

1. [Complete System Inventory](#1-complete-system-inventory)
2. [Audit Results by System](#2-audit-results-by-system)
3. [Critical Architecture Gaps](#3-critical-architecture-gaps)
4. [Current vs. Intended Decision Flow](#4-current-vs-intended-decision-flow)
5. [Wiring Plan](#5-wiring-plan)
6. [Priority Matrix](#6-priority-matrix)

---

## 1. Complete System Inventory

### Tier 1: Core ML Decision Systems (Audited + Fixed)

| System | File | Lines | ML Type | Status | Changes Made |
|--------|------|-------|---------|--------|--------------|
| **WISDOM** | `quant/fortress_ml_advisor.py` | ~3,200 | XGBoost classifier | V3 FIXED | scale_pos_weight, VRP, cyclical day, adaptive thresholds |
| **Prophet** | `quant/prophet_advisor.py` | ~6,269 | GBC + isotonic calibration | V3 FIXED | Sub-models, 6 root-cause bugs, strategy features, rule retirement |
| **ORION** | `quant/gex_probability_models.py` + `gex_signal_integration.py` | ~4,000 | 5 XGBoost sub-models | V2 FIXED | scale_pos_weight, Brier on CV, VRP, removed +10% boost |

### Tier 2: Orchestration & Safety (Audited, NOT Fixed)

| System | File | Lines | Type | Status | Key Issue |
|--------|------|-------|------|--------|-----------|
| **OMEGA** | `core/omega_orchestrator.py` | 1,450 | Decision hub | EXISTS BUT UNUSED | No bot calls it |
| **PROVERBS** | `quant/proverbs_enhancements.py` + `proverbs_feedback_loop.py` | 5,919 | Guardrails/risk | PARTIALLY BROKEN | Kill switch always returns False |
| **Auto Validation** | `quant/auto_validation_system.py` | 1,454 | Model validation | EXISTS | Registers 11 models, runs walk-forward |

### Tier 3: Specialized ML Systems (Audited, NOT Fixed)

| System | File | Lines | ML Type | Status | Key Issue |
|--------|------|-------|---------|--------|-----------|
| **DISCERNMENT** | `core/discernment_ml_engine.py` | 1,482 | XGBoost + RF + GBC | OPERATIONAL | 6 of 9 strategy builders are stubs |
| **GEX Directional** | `quant/gex_directional_ml.py` | 900 | XGBoost classifier | COMPLETE | Used by directional bots |
| **SPX Wheel ML** | `trading/spx_wheel_ml.py` | 300+ | RF/GBC | PARTIAL | Not wired into ATLAS |
| **VALOR ML** | `trading/valor/ml.py` | 100+ | XGBoost | DESIGNED | Mirrors WISDOM for MES futures |
| **Pattern Learner** | `ai/autonomous_ml_pattern_learner.py` | 150+ | RandomForest | OPERATIONAL | Multi-timeframe RSI patterns |

### Tier 4: Frameworks & Utilities

| System | File | Lines | Type | Status |
|--------|------|-------|------|--------|
| **Walk-Forward** | `quant/walk_forward_optimizer.py` | 565 | Validation framework | OPERATIONAL |
| **Model Persistence** | `quant/model_persistence.py` | 374 | PostgreSQL storage | OPERATIONAL |
| **Proverbs AI** | `quant/proverbs_ai_analyst.py` | 634 | Claude API analysis | OPERATIONAL |
| **Price Trend Tracker** | `quant/price_trend_tracker.py` | 726 | Rule-based trends | OPERATIONAL |
| **Strategy Competition** | `core/autonomous_strategy_competition.py` | 100+ | Benchmark framework | OPERATIONAL |
| **Integration Layer** | `quant/integration.py` | 639 | Walk-forward + Kelly | OPERATIONAL |

### Tier 5: Bot Integration (Mixins)

| System | File | Lines | Status | Key Issue |
|--------|------|-------|--------|-----------|
| **OMEGA Mixin** | `trading/mixins/omega_mixin.py` | ~200 | DEAD CODE | No bot inherits it |
| **Proverbs Mixin** | `trading/mixins/proverbs_integration.py` | ~310 | DEAD CODE | No bot inherits it; proverbs_can_trade() always True |

---

## 2. Audit Results by System

### WISDOM (V3 - FIXED)
- **Role**: Primary ML win_probability provider in signals.py
- **Bug Found**: 89% win rate base rate not accounted for → scale_pos_weight fix
- **Bug Found**: Training used datetime split not TimeSeriesSplit → fixed
- **Enhancement**: VRP feature, cyclical day encoding, adaptive thresholds
- **Verdict**: PRODUCTION-READY after V3 fixes

### Prophet (V3 - FIXED)
- **Role**: Strategy recommendation + bot-specific advice in trader.py
- **6 Bugs Fixed**: ANCHOR hardcoded thresholds, SOLOMON probability override, ANCHOR hallucination penalties, VRP proxy, connection leaks, thread safety
- **Enhancement**: Strategy-specific sub-models (IC vs Directional), multi-prediction storage (Migration 027), rule retirement framework
- **Verdict**: PRODUCTION-READY after V3 fixes

### ORION (V2 - FIXED)
- **Role**: 5 GEX probability sub-models for WATCHTOWER/GIDEON/SOLOMON_V2
- **Bug Found**: MagnetAttraction ~89% base rate, no class balancing → fixed
- **Bug Found**: +10% win_probability hardcoded boost → removed
- **Enhancement**: VRP feature, cyclical day, feature versioning, Brier on CV
- **Verdict**: PRODUCTION-READY after V2 fixes

### OMEGA Orchestrator (EXISTS - NOT WIRED)
- **Role**: 4-layer decision hub (Proverbs → Ensemble → ML → Prophet)
- **Architecture**: Correct — exactly what's needed
- **Gap Implementations**: AutoRetrainMonitor, Thompson Capital, RegimeTransitionDetector, CrossBotCorrelation, EquityCompoundScaler
- **Critical Issue**: **NO TRADING BOT CALLS IT**
  - OmegaMixin exists but no bot inherits from it
  - Bots still call Prophet directly in trader.py
  - OMEGA's Ensemble layer is gutted (returns neutral — "Prophet is god")
  - OMEGA uses WISDOM (fortress_ml_advisor) as ML layer, but Prophet is already called separately
- **Verdict**: Well-designed but completely disconnected from production

### PROVERBS (PARTIALLY BROKEN)
- **Role**: Guardrails, kill switch, feedback loop, A/B testing
- **What Works**: Outcome recording, consecutive loss tracking, daily loss tracking, notifications, AI analysis, proposals, dashboard (44 API endpoints)
- **What's Broken**:
  - `is_bot_killed()` ALWAYS returns False (line 2286-2296)
  - `proverbs_can_trade()` in mixin ALWAYS returns True
  - Kill switch activation logs and updates DB but is never enforced
  - Consecutive loss triggers 5-minute local pause only, not actual kill
- **Verdict**: Monitoring works, enforcement doesn't. False sense of security.

### DISCERNMENT (OPERATIONAL)
- **Role**: AI options scanner with direction/magnitude/timing predictions
- **Architecture**: 3 parallel ML models (XGBoost direction, RF magnitude, GBC timing)
- **24 Features**: Price, GEX, VIX, options Greeks, technicals, volume
- **What Works**: Scanning, outcome tracking (every 5 min), API (15 endpoints), dashboard
- **What's Broken**: 6 of 9 strategy builders are stubs (return placeholders)
- **Verdict**: Solid scanner, incomplete strategy execution

### Auto Validation System (EXISTS)
- **Role**: Central model validation + auto-retraining
- **Registers 11 Models**: All major ML systems
- **Walk-Forward**: Proper IS/OOS validation with degradation thresholds
- **Thompson Sampling**: Capital allocation based on bot performance
- **Verdict**: Good framework, needs verification that all retrain triggers are wired

---

## 3. Critical Architecture Gaps

### Gap A: OMEGA is Not Wired (CRITICAL)

**Current Flow** (what actually happens):
```
Bot scanner triggers every 5 min
  → signals.py calls WISDOM for win_probability (PRIMARY)
  → trader.py calls Prophet for strategy_recommendation (BACKUP)
  → trader.py checks Proverbs for consecutive losses (local pause only)
  → trader.py makes its own TRADE/SKIP decision based on Prophet advice
  → No OMEGA involvement at any point
```

**Intended Flow** (what OMEGA was designed for):
```
Bot scanner triggers every 5 min
  → OMEGA Layer 1: Proverbs safety check (absolute veto)
  → OMEGA Layer 2: Ensemble context (informational) [GUTTED]
  → OMEGA Layer 3: ML Advisor (WISDOM) decision (primary)
  → OMEGA Layer 4: Prophet adaptation (bot-specific, no veto)
  → OMEGA Gap implementations: correlation, equity scaling, regime
  → OMEGA returns unified OmegaDecision with full transparency
```

**Impact**:
- No cross-bot correlation enforcement
- No equity compound scaling
- No regime transition detection
- No unified decision trace/audit trail
- No Thompson Sampling capital allocation

### Gap B: Kill Switch Never Enforces (HIGH)

The entire safety stack is broken at the enforcement layer:
```
ConsecutiveLossMonitor detects 3 losses in a row → WORKING
  → activate_kill_switch() called → WORKING (logs + DB update)
    → is_bot_killed() checked → BROKEN (always returns False)
      → Bot keeps trading → DANGEROUS
```

### Gap C: Duplicate Decision-Making (MEDIUM)

WISDOM and Prophet both make predictions independently:
- WISDOM: XGBoost → win_probability → used in signals.py
- Prophet: GBC → strategy_recommendation → used in trader.py
- Neither feeds into the other
- OMEGA was supposed to unify them but doesn't

### Gap D: Model Training is Not Coordinated (MEDIUM)

Each system trains independently:
- WISDOM: trains from fortress_closed_trades
- Prophet: trains from database backtests + live outcomes
- ORION: trains every Sunday 6PM CT
- DISCERNMENT: manual trigger or auto-validation
- No coordination on timing, data freshness, or versioning

---

## 4. Current vs. Intended Decision Flow

### Current (Fragmented)
```
┌─────────────────────────────────────────────────────────────────┐
│                      FORTRESS trader.py                          │
│                                                                  │
│  signals.py ──→ WISDOM (win_prob) ──→ should_trade()            │
│       ↓                                                          │
│  trader.py ──→ Prophet (advice) ──→ execute_if_TRADE_FULL()     │
│       ↓                                                          │
│  trader.py ──→ Proverbs (consecutive losses) ──→ 5min pause     │
│       ↓                                                          │
│  trader.py ──→ Open position with bot's own logic               │
│                                                                  │
│  (OMEGA exists but is never called)                              │
│  (Kill switch exists but always returns False)                   │
│  (Correlation enforcement exists but nobody uses it)             │
└─────────────────────────────────────────────────────────────────┘
```

### Intended (Unified via OMEGA)
```
┌─────────────────────────────────────────────────────────────────┐
│                    OMEGA Orchestrator                             │
│                                                                  │
│  PROVERBS ──→ Safety gate (kill switch actually works)           │
│       ↓                                                          │
│  WISDOM ──→ Win probability (ML primary)                         │
│       ↓                                                          │
│  Prophet ──→ Bot-specific adaptation (no veto)                   │
│       ↓                                                          │
│  Cross-bot correlation ──→ Exposure limit check                  │
│       ↓                                                          │
│  Equity scaler ──→ Position size adjustment                      │
│       ↓                                                          │
│  OmegaDecision ──→ Full transparency audit trail                │
│       ↓                                                          │
│  Bot executes (or skips) based on unified decision               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Wiring Plan

### Phase 1: Fix Kill Switch (1 hour, CRITICAL)
**File**: `quant/proverbs_feedback_loop.py`
- Replace `is_bot_killed()` stub with actual database check
- Wire kill switch into bot trading loop (check before every trade)
- Add kill switch status to dashboard responses

### Phase 2: Wire OMEGA into Bots (4-6 hours, HIGH)
**Files**: Each bot's `trader.py`
- Option A: Have bots inherit from OmegaMixin (cleaner but bigger change)
- Option B: Have trader.py call `omega.get_trading_decision()` directly (simpler)
- OMEGA's Layer 2 (Ensemble) stays gutted — Prophet remains sole authority
- OMEGA provides: Proverbs check + ML decision + correlation enforcement + equity scaling

### Phase 3: Coordinate Training (2-3 hours, MEDIUM)
**File**: `scheduler/trader_scheduler.py`
- Sunday 4PM: WISDOM retrains
- Sunday 5PM: Prophet retrains (combined + sub-models)
- Sunday 6PM: ORION retrains (already scheduled)
- Sunday 7PM: Auto-Validation runs walk-forward on all models
- Daily 4PM: PROVERBS feedback loop (already scheduled)

### Phase 4: DISCERNMENT Strategy Completion (2-3 hours, LOW)
**File**: `core/discernment_ml_engine.py`
- Complete 6 stub strategy builders
- Copy pattern from `_build_bull_call_spread()` (lines 1057-1138)

---

## 6. Priority Matrix

| Priority | Task | Impact | Effort | Risk of Not Doing |
|----------|------|--------|--------|-------------------|
| **P0** | Fix kill switch enforcement | Safety | 1hr | Bots trade through loss streaks unchecked |
| **P1** | Wire OMEGA into FORTRESS (pilot) | Architecture | 3hr | No unified decision flow |
| **P1** | Wire OMEGA into remaining bots | Architecture | 3hr | Inconsistent decision-making |
| **P2** | Coordinate training schedule | Reliability | 2hr | Models train at random times |
| **P2** | Prophet sub-model training data | ML Quality | 1hr | Sub-models stay untrained |
| **P3** | Complete DISCERNMENT strategies | Features | 2hr | Scanner can't recommend 6/9 strategies |
| **P3** | Wire SPX Wheel ML into ATLAS | Features | 2hr | ATLAS uses no ML |
| **P4** | Wire VALOR ML into production | Features | 2hr | VALOR uses Bayesian fallback |

---

## Appendix A: Files Modified in This Audit Series

### Fixed (Code Changes):
1. `quant/fortress_ml_advisor.py` — WISDOM V3 (scale_pos_weight, VRP, cyclical day, adaptive thresholds)
2. `quant/prophet_advisor.py` — Prophet V3 (6 bugs + sub-models + multi-prediction + rule retirement)
3. `quant/gex_probability_models.py` — ORION V2 (class balancing, Brier on CV, VRP)
4. `quant/gex_signal_integration.py` — ORION V2 (removed +10% boost)
5. `db/migrations/027_prophet_multi_prediction.sql` — New migration

### Audited (Reports Only):
6. `quant/proverbs_enhancements.py` — PROVERBS (5,919 lines, kill switch broken)
7. `quant/proverbs_feedback_loop.py` — PROVERBS (kill switch stub)
8. `core/discernment_ml_engine.py` — DISCERNMENT (6 stub strategies)
9. `core/omega_orchestrator.py` — OMEGA (not wired into any bot)
10. `quant/auto_validation_system.py` — Auto Validation (11 registered models)
11. `quant/gex_directional_ml.py` — GEX Directional ML
12. `trading/spx_wheel_ml.py` — SPX Wheel ML
13. `trading/valor/ml.py` — VALOR ML
14. `ai/autonomous_ml_pattern_learner.py` — Pattern Learner
15. `quant/walk_forward_optimizer.py` — Walk-Forward framework
16. `quant/model_persistence.py` — Model persistence
17. `trading/mixins/omega_mixin.py` — OMEGA mixin (dead code)
18. `trading/mixins/proverbs_integration.py` — Proverbs mixin (dead code)

### Commits on Branch:
- Watchtower data analysis (initial investigation)
- WISDOM V3 features + training fixes
- Prophet V2 + forensic audit report
- ORION V2 audit + fixes
- Prophet V3 root-cause fixes (6 bugs)
- Prophet V3 enhancements (sub-models, multi-prediction, rule retirement)
- This orchestration evaluation report

---

## Appendix B: System Dependency Graph

```
                        ┌──────────────────┐
                        │  OMEGA           │ ← EXISTS BUT NOT WIRED
                        │  Orchestrator    │
                        └────────┬─────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ↓                    ↓                    ↓
   ┌────────────────┐  ┌─────────────────┐  ┌────────────────┐
   │ PROVERBS       │  │ WISDOM (ML)     │  │ Prophet (GBC)  │
   │ Safety Layer   │  │ Win Probability │  │ Bot-Specific   │
   │ [BROKEN KILL]  │  │ [V3 FIXED]      │  │ [V3 FIXED]     │
   └───────┬────────┘  └────────┬────────┘  └────────┬───────┘
           │                    │                     │
           ↓                    ↓                     ↓
   ┌────────────────┐  ┌─────────────────┐  ┌────────────────┐
   │ Proverbs AI    │  │ ORION           │  │ GEX Direction  │
   │ Claude Analysis│  │ 5 GEX Models    │  │ XGBoost        │
   │ [WORKING]      │  │ [V2 FIXED]      │  │ [WORKING]      │
   └────────────────┘  └─────────────────┘  └────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ↓            ↓            ↓
             ┌───────────┐ ┌──────────┐ ┌──────────┐
             │ WATCHTOWER │ │ GIDEON   │ │SOLOMON V2│
             │ (Display)  │ │ (Bot)    │ │ (Bot)    │
             └───────────┘ └──────────┘ └──────────┘

   STANDALONE SYSTEMS:
   ┌──────────────────┐  ┌─────────────────┐  ┌───────────────┐
   │ DISCERNMENT      │  │ Auto Validation │  │ Pattern       │
   │ Options Scanner  │  │ Walk-Forward    │  │ Learner       │
   │ [6 STUBS]        │  │ 11 Models       │  │ [WORKING]     │
   └──────────────────┘  └─────────────────┘  └───────────────┘
   ┌──────────────────┐  ┌─────────────────┐
   │ SPX Wheel ML     │  │ VALOR ML        │
   │ [NOT WIRED]      │  │ [NOT WIRED]     │
   └──────────────────┘  └─────────────────┘
```

---

## Appendix C: Per-System Line Counts

| System | File(s) | Lines | % of Total ML Code |
|--------|---------|-------|-------------------|
| Prophet V3 | prophet_advisor.py | 6,269 | 38% |
| PROVERBS | enhancements + feedback_loop | 5,919 | 36% |
| WISDOM V3 | fortress_ml_advisor.py | 3,200 | 19% |
| ORION V2 | gex_probability_models.py + integration | 4,000 | 24% |
| OMEGA | omega_orchestrator.py | 1,450 | 9% |
| DISCERNMENT | discernment_ml_engine.py + outcome_tracker | 1,907 | 12% |
| Auto Validation | auto_validation_system.py | 1,454 | 9% |
| GEX Directional | gex_directional_ml.py | 900 | 5% |
| Walk-Forward | walk_forward_optimizer.py | 565 | 3% |
| Price Trend | price_trend_tracker.py | 726 | 4% |
| Proverbs AI | proverbs_ai_analyst.py | 634 | 4% |
| Integration | integration.py | 639 | 4% |
| Model Persistence | model_persistence.py | 374 | 2% |
| SPX Wheel ML | spx_wheel_ml.py | 300 | 2% |
| VALOR ML | valor/ml.py | 100 | 1% |
| Pattern Learner | autonomous_ml_pattern_learner.py | 150 | 1% |

**Total ML Code: ~16,500+ lines across 18 systems**
