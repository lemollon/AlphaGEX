# AlphaGEX Bot Rename — Phase 1 Audit Report

**Date:** 2026-02-08
**Branch:** `claude/bot-name-mapping-Jdf6H`
**Status:** AUDIT ONLY — Zero code changes made

---

## 1. Executive Summary

| Metric | Count |
|--------|-------|
| Total references to rename | ~11,500+ |
| Python files affected | ~500+ |
| Frontend files affected | ~150+ |
| Database tables to rename | ~65 |
| API route prefixes to rename | 11 |
| Class definitions to rename | ~65 |
| Environment variables to rename | 2 (ARES-specific only) |
| Directory renames needed | ~25 |
| File renames needed | ~50+ |

---

## 2. Reference Count Summary — All Systems

### Trading Bots

| Old Name | New Name | Python Refs | Python Files | Frontend Refs | Frontend Files | TOTAL Refs | Risk |
|----------|----------|-------------|--------------|---------------|----------------|------------|------|
| ARES | FORTRESS | 1,520 | 171 | 255 | 59 | **1,775** | 🔴 HIGH |
| ATHENA | SOLOMON | 1,009 | 130 | 233 | 53 | **1,242** | 🔴 HIGH |
| TITAN | SAMSON | 542 | 68 | 149 | 35 | **691** | 🔴 HIGH |
| PEGASUS | ANCHOR | 767 | 94 | 170 | 43 | **937** | 🔴 HIGH |
| ICARUS | GIDEON | 619 | 78 | 145 | 30 | **764** | 🔴 HIGH |
| PHOENIX | LAZARUS | 238 | 41 | * | * | **~300** | 🟡 MEDIUM |
| ATLAS | CORNERSTONE | 213 | 36 | * | * | **~270** | 🟡 MEDIUM |
| HERMES | SHEPHERD | 27 | 12 | * | * | **~40** | 🟢 LOW |
| PROMETHEUS | JUBILEE | 670 | 42 | 90 | 14 | **760** | 🔴 HIGH |
| HERACLES | VALOR | 551 | 49 | * | * | **~600** | 🟡 MEDIUM |
| AGAPE | AGAPE | — | — | — | — | **NO CHANGE** | ⚪ SKIP |

*\* Included in combined frontend search (457 total for remaining systems across 51 files)*

### Advisory Systems

| Old Name | New Name | Python Refs | Python Files | Frontend Refs | Frontend Files | TOTAL Refs | Risk |
|----------|----------|-------------|--------------|---------------|----------------|------------|------|
| ORACLE | PROPHET | 2,114 | 145 | 407 | 42 | **2,521** | 🔴 CRITICAL |
| SAGE | WISDOM | 86 | 9 | * | * | **~120** | 🟡 MEDIUM |
| SOLOMON (advisory) | PROVERBS | 755 | 44 | 102 | 12 | **857** | 🔴 CRITICAL (COLLISION) |
| ARGUS | WATCHTOWER | 396 | 35 | 241 | 22 | **637** | 🔴 HIGH |
| GEXIS | COUNSELOR | 315 | 29 | * | * | **~370** | 🟡 MEDIUM |
| ORION | STARS | 19 | 8 | * | * | **~30** | 🟢 LOW |
| KRONOS | CHRONICLES | 221 | 48 | * | * | **~260** | 🟡 MEDIUM |
| HYPERION | GLORY | 90 | 12 | * | * | **~110** | 🟡 MEDIUM |
| APOLLO | DISCERNMENT | 116 | 17 | * | * | **~140** | 🟡 MEDIUM |
| NEXUS | COVENANT | 2 | 2 | * | * | **~50** | 🟢 LOW |

---

## 3. SOLOMON Collision Map ⚠️ CRITICAL

The name `SOLOMON` exists in TWO completely different contexts:

### Current SOLOMON References (Advisory System → rename to PROVERBS)

These are the advisory system "Solomon Enhancements" / "Solomon Feedback Loop":

| File | Refs | Type | Owner |
|------|------|------|-------|
| `quant/solomon_feedback_loop.py` | 126 | CORE MODULE: Classes, DB tables (solomon_*), functions | ADVISORY |
| `quant/solomon_enhancements.py` | 67 | CORE MODULE: SolomonEnhanced class, get_solomon_enhanced() | ADVISORY |
| `quant/solomon_ai_analyst.py` | 55 | CORE MODULE: SolomonAIAnalyst class | ADVISORY |
| `quant/solomon_notifications.py` | 9 | Notification system | ADVISORY |
| `quant/oracle_advisor.py` | 27 | SolomonAdvisory class, solomon integration | ADVISORY |
| `trading/mixins/solomon_integration.py` | 50 | SolomonIntegrationMixin class | ADVISORY |
| `trading/mixins/omega_mixin.py` | 5 | solomon references | ADVISORY |
| `core/omega_orchestrator.py` | 29 | SolomonVerdict class | ADVISORY |
| `core/math_optimizers.py` | 14 | solomon integration | ADVISORY |
| `backend/api/routes/solomon_routes.py` | 73 | API routes `/api/solomon/` | ADVISORY |
| `backend/tests/test_solomon_routes.py` | 22 | Test file | ADVISORY |
| `backend/main.py` | 2 | Router import | ADVISORY |
| `scheduler/trader_scheduler.py` | 32 | solomon imports, get_solomon | ADVISORY |
| `trading/*/executor.py` | ~20 | solomon_integration calls in all bot executors | ADVISORY |
| `trading/*/trader.py` | ~30 | solomon references in all bot traders | ADVISORY |
| `scripts/test_solomon_*.py` | ~80+ | Test scripts | ADVISORY |
| `scripts/test_oracle_solomon_separation.py` | 28 | Test script | ADVISORY |
| Various test files | ~30 | Test references | ADVISORY |

### Future SOLOMON References (ATHENA's new name — do NOT rename yet)

| File | Refs | Type | Owner |
|------|------|------|-------|
| `frontend/src/lib/botDisplayNames.ts` | 7 | Display name mapping (ATHENA → "SOLOMON") | BOT_DISPLAY |
| `frontend/src/app/solomon/page.tsx` | 5+ | Solomon feedback loop dashboard (currently shows advisory) | AMBIGUOUS |

### Collision Resolution Order (NON-NEGOTIABLE)
1. **FIRST**: Rename advisory `SOLOMON` → `PROVERBS` in ALL Python files, routes, DB tables, tests
2. **VERIFY**: Zero advisory SOLOMON references remain
3. **THEN**: Rename bot `ATHENA` → `SOLOMON` safely

---

## 4. Database Tables to Rename

### ARES → FORTRESS (7 tables)
- `ares_positions` (created in `trading/ares_v2/db.py`, `db/config_and_database.py`, `scripts/live_bot_diagnostic.py`)
- `ares_signals` (created in `trading/ares_v2/db.py`)
- `ares_daily_perf` (created in `trading/ares_v2/db.py`, `db/config_and_database.py`)
- `ares_logs` (created in `trading/ares_v2/db.py`)
- `ares_equity_snapshots` (created in `trading/ares_v2/db.py`, `db/config_and_database.py`, `backend/api/routes/ares_routes.py`)
- `ares_ml_outcomes` (created in `quant/ares_ml_advisor.py`)
- `ares_scan_activity` (referenced in scan activity logger)

### ATHENA → SOLOMON (5 tables)
- `athena_positions` (created in `trading/athena_v2/db.py`, `db/config_and_database.py`, `scripts/live_bot_diagnostic.py`)
- `athena_signals` (created in `trading/athena_v2/db.py`)
- `athena_daily_perf` (created in `trading/athena_v2/db.py`)
- `athena_logs` (created in `trading/athena_v2/db.py`)
- `athena_equity_snapshots` (created in `trading/athena_v2/db.py`, `db/config_and_database.py`, `backend/api/routes/athena_routes.py`)

### TITAN → SAMSON (5 tables)
- `titan_positions` (created in `trading/titan/db.py`, `db/config_and_database.py`, `scripts/live_bot_diagnostic.py`)
- `titan_signals` (created in `trading/titan/db.py`)
- `titan_daily_perf` (created in `trading/titan/db.py`)
- `titan_logs` (created in `trading/titan/db.py`)
- `titan_equity_snapshots` (created in `trading/titan/db.py`, `db/config_and_database.py`, `backend/api/routes/titan_routes.py`)

### PEGASUS → ANCHOR (5 tables)
- `pegasus_positions` (created in `trading/pegasus/db.py`, `db/config_and_database.py`, `scripts/live_bot_diagnostic.py`)
- `pegasus_signals` (created in `trading/pegasus/db.py`)
- `pegasus_daily_perf` (created in `trading/pegasus/db.py`)
- `pegasus_logs` (created in `trading/pegasus/db.py`)
- `pegasus_equity_snapshots` (created in `trading/pegasus/db.py`, `db/config_and_database.py`, `backend/api/routes/pegasus_routes.py`)

### ICARUS → GIDEON (5 tables)
- `icarus_positions` (created in `trading/icarus/db.py`, `db/config_and_database.py`, `scripts/live_bot_diagnostic.py`, `backend/api/routes/icarus_routes.py`)
- `icarus_signals` (created in `trading/icarus/db.py`, `backend/api/routes/icarus_routes.py`)
- `icarus_daily_perf` (created in `trading/icarus/db.py`, `backend/api/routes/icarus_routes.py`)
- `icarus_logs` (created in `trading/icarus/db.py`, `backend/api/routes/icarus_routes.py`)
- `icarus_equity_snapshots` (created in `trading/icarus/db.py`, `backend/api/routes/icarus_routes.py`)

### HERACLES → VALOR (10 tables)
- `heracles_positions` (created in `trading/heracles/db.py`)
- `heracles_closed_trades` (created in `trading/heracles/db.py`)
- `heracles_signals` (created in `trading/heracles/db.py`)
- `heracles_equity_snapshots` (created in `trading/heracles/db.py`)
- `heracles_config` (created in `trading/heracles/db.py`)
- `heracles_win_tracker` (created in `trading/heracles/db.py`)
- `heracles_logs` (created in `trading/heracles/db.py`)
- `heracles_daily_perf` (created in `trading/heracles/db.py`)
- `heracles_paper_account` (created in `trading/heracles/db.py`)
- `heracles_scan_activity` (created in `trading/heracles/db.py`)

### PROMETHEUS → JUBILEE (13 tables)
- `prometheus_positions` (created in `trading/prometheus/db.py`)
- `prometheus_signals` (created in `trading/prometheus/db.py`)
- `prometheus_capital_deployments` (created in `trading/prometheus/db.py`)
- `prometheus_rate_analysis` (created in `trading/prometheus/db.py`)
- `prometheus_daily_briefings` (created in `trading/prometheus/db.py`)
- `prometheus_roll_decisions` (created in `trading/prometheus/db.py`)
- `prometheus_config` (created in `trading/prometheus/db.py`)
- `prometheus_logs` (created in `trading/prometheus/db.py`)
- `prometheus_equity_snapshots` (created in `trading/prometheus/db.py`)
- `prometheus_ic_positions` (created in `trading/prometheus/db.py`)
- `prometheus_ic_closed_trades` (created in `trading/prometheus/db.py`)
- `prometheus_ic_signals` (created in `trading/prometheus/db.py`)
- `prometheus_ic_config` (created in `trading/prometheus/db.py`)
- `prometheus_ic_equity_snapshots` (created in `trading/prometheus/db.py`)

### SOLOMON (advisory) → PROVERBS (9 tables)
- `solomon_audit_log` (created in `quant/solomon_feedback_loop.py`)
- `solomon_proposals` (created in `quant/solomon_feedback_loop.py`)
- `solomon_versions` (created in `quant/solomon_feedback_loop.py`)
- `solomon_performance` (created in `quant/solomon_feedback_loop.py`)
- `solomon_rollbacks` (created in `quant/solomon_feedback_loop.py`)
- `solomon_health` (created in `quant/solomon_feedback_loop.py`)
- `solomon_kill_switch` (created in `quant/solomon_feedback_loop.py`)
- `solomon_validations` (created in `quant/solomon_feedback_loop.py`)
- `solomon_ab_tests` (created in `quant/solomon_feedback_loop.py`)

### AGAPE — NO CHANGE (4 tables)
- `agape_positions`, `agape_equity_snapshots`, `agape_scan_activity`, `agape_activity_log`

### Other bot-prefixed tables referenced in code
- `oracle_predictions` (referenced but no CREATE TABLE found in search)
- `oracle_prediction_log` (referenced in routes)

**Total DB tables to rename: ~65 tables**

---

## 5. API Route Prefixes to Rename

| Current Prefix | New Prefix | Route File | Endpoints |
|----------------|------------|------------|-----------|
| `/api/ares` | `/api/fortress` | `backend/api/routes/ares_routes.py` | ~29 |
| `/api/athena` | `/api/solomon` | `backend/api/routes/athena_routes.py` | ~21 |
| `/api/titan` | `/api/samson` | `backend/api/routes/titan_routes.py` | ~15 |
| `/api/pegasus` | `/api/anchor` | `backend/api/routes/pegasus_routes.py` | ~15 |
| `/api/icarus` | `/api/gideon` | `backend/api/routes/icarus_routes.py` | ~15 |
| `/api/prometheus-box` | `/api/jubilee` | `backend/api/routes/prometheus_box_routes.py` | ~60 |
| `/api/heracles` | `/api/valor` | `backend/api/routes/heracles_routes.py` | ~15 |
| `/api/solomon` | `/api/proverbs` | `backend/api/routes/solomon_routes.py` | ~10 |
| `/api/oracle` | `/api/prophet` | `backend/api/routes/oracle_routes.py` | ~10 |
| `/api/argus` | `/api/watchtower` | `backend/api/routes/argus_routes.py` | ~15 |
| `/api/hyperion` | `/api/glory` | `backend/api/routes/hyperion_routes.py` | ~8 |
| `/api/apollo` | `/api/discernment` | `backend/api/routes/apollo_routes.py` | ~5 |

**Missing route files (no dedicated routes):**
- PHOENIX/LAZARUS — no `phoenix_routes.py`
- ATLAS/CORNERSTONE — no `atlas_routes.py`
- HERMES/SHEPHERD — no `hermes_routes.py`
- KRONOS/CHRONICLES — no `kronos_routes.py` (uses `kronos_infrastructure.py` service)
- GEXIS/COUNSELOR — uses `ai_routes.py` with `/api/ai/gexis/` sub-paths
- SAGE/WISDOM — uses `ml_routes.py` with `/api/ml/sage/` sub-paths
- ORION/STARS — uses `ml_routes.py` with `/api/ml/gex-models/` sub-paths
- NEXUS/COVENANT — no dedicated routes (frontend-only 3D viz)

---

## 6. Environment Variables to Rename

Only ARES has bot-specific env vars:

| Current Env Var | New Env Var | Files |
|----------------|-------------|-------|
| `TRADIER_ARES_SANDBOX_API_KEY_2` | `TRADIER_FORTRESS_SANDBOX_API_KEY_2` | `unified_config.py`, `trading/ares_v2/executor.py`, `scripts/test_ares_dual_accounts.py`, `scripts/test_ares_mirror_order.py` |
| `TRADIER_ARES_SANDBOX_ACCOUNT_ID_2` | `TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2` | Same files as above |

**IMPORTANT:** These env vars must also be renamed in Render deployment config and any `.env` files.

---

## 7. Class Definitions to Rename

### Trading Bot Classes

| Current Class | New Class | File |
|--------------|-----------|------|
| `ARESTrader` | `FortressTrader` | `trading/ares_v2/trader.py` |
| `ARESConfig` | `FortressConfig` | `trading/ares_v2/models.py` |
| `ARESDatabase` | `FortressDatabase` | `trading/ares_v2/db.py` |
| `ARESConfigUpdate` | `FortressConfigUpdate` | `backend/api/models.py` |
| `ARESSkipDayRequest` | `FortressSkipDayRequest` | `backend/api/models.py` |
| `AresMLAdvisor` | `FortressMLAdvisor` | `quant/ares_ml_advisor.py` |
| `ATHENATrader` | `SolomonTrader` | `trading/athena_v2/trader.py` |
| `ATHENAConfig` | `SolomonConfig` | `trading/athena_v2/models.py` |
| `ATHENADatabase` | `SolomonDatabase` | `trading/athena_v2/db.py` |
| `ATHENAConfigUpdate` | `SolomonConfigUpdate` | `backend/api/models.py` |
| `ATHENATradeRequest` | `SolomonTradeRequest` | `backend/api/models.py` |
| `TITANTrader` | `SamsonTrader` | `trading/titan/trader.py` |
| `TITANConfig` | `SamsonConfig` | `trading/titan/models.py` |
| `TITANDatabase` | `SamsonDatabase` | `trading/titan/db.py` |
| `PEGASUSTrader` | `AnchorTrader` | `trading/pegasus/trader.py` |
| `PEGASUSConfig` | `AnchorConfig` | `trading/pegasus/models.py` |
| `PEGASUSDatabase` | `AnchorDatabase` | `trading/pegasus/db.py` |
| `ICARUSTrader` | `GideonTrader` | `trading/icarus/trader.py` |
| `ICARUSConfig` | `GideonConfig` | `trading/icarus/models.py` |
| `ICARUSDatabase` | `GideonDatabase` | `trading/icarus/db.py` |
| `PrometheusTrader` | `JubileeTrader` | `trading/prometheus/trader.py` |
| `PrometheusICTrader` | `JubileeICTrader` | `trading/prometheus/trader.py` |
| `PrometheusConfig` | `JubileeConfig` | `trading/prometheus/models.py` |
| `PrometheusICConfig` | `JubileeICConfig` | `trading/prometheus/models.py` |
| `PrometheusICSignal` | `JubileeICSignal` | `trading/prometheus/models.py` |
| `PrometheusICPosition` | `JubileeICPosition` | `trading/prometheus/models.py` |
| `PrometheusPerformanceSummary` | `JubileePerformanceSummary` | `trading/prometheus/models.py` |
| `PrometheusDatabase` | `JubileeDatabase` | `trading/prometheus/db.py` |
| `PrometheusICExecutor` | `JubileeICExecutor` | `trading/prometheus/executor.py` |
| `PrometheusICSignalGenerator` | `JubileeICSignalGenerator` | `trading/prometheus/signals.py` |
| `PrometheusSpan` | `JubileeSpan` | `trading/prometheus/tracing.py` |
| `PrometheusTracer` | `JubileeTracer` | `trading/prometheus/tracing.py` |
| `HERACLESTrader` | `ValorTrader` | `trading/heracles/trader.py` |
| `HERACLESConfig` | `ValorConfig` | `trading/heracles/models.py` |
| `HERACLESDatabase` | `ValorDatabase` | `trading/heracles/db.py` |
| `HERACLESSignalGenerator` | `ValorSignalGenerator` | `trading/heracles/signals.py` |
| `HERACLESMLAdvisor` | `ValorMLAdvisor` | `trading/heracles/ml.py` |
| `HERACLESTrainingMetrics` | `ValorTrainingMetrics` | `trading/heracles/ml.py` |

### Advisory System Classes

| Current Class | New Class | File |
|--------------|-----------|------|
| `OracleAdvisor` | `ProphetAdvisor` | `quant/oracle_advisor.py` |
| `OracleConfig` | `ProphetConfig` | `config.py` |
| `OraclePrediction` | `ProphetPrediction` | `quant/oracle_advisor.py` |
| `OracleClaudeEnhancer` | `ProphetClaudeEnhancer` | `quant/oracle_advisor.py` |
| `OracleLiveLog` | `ProphetLiveLog` | `quant/oracle_advisor.py` |
| `OracleAdaptation` | `ProphetAdaptation` | `core/omega_orchestrator.py` |
| `OracleAnalysisRequest` | `ProphetAnalysisRequest` | `backend/api/routes/zero_dte_backtest_routes.py` |
| `OracleExplainRequest` | `ProphetExplainRequest` | `backend/api/routes/zero_dte_backtest_routes.py` |
| `SolomonVerdict` | `ProverbsVerdict` | `core/omega_orchestrator.py` |
| `SolomonEnhanced` | `ProverbsEnhanced` | `quant/solomon_enhancements.py` |
| `SolomonFeedbackLoop` | `ProverbsFeedbackLoop` | `quant/solomon_feedback_loop.py` |
| `SolomonAIAnalyst` | `ProverbsAIAnalyst` | `quant/solomon_ai_analyst.py` |
| `SolomonNotifications` | `ProverbsNotifications` | `quant/solomon_notifications.py` |
| `SolomonIntegrationMixin` | `ProverbsIntegrationMixin` | `trading/mixins/solomon_integration.py` |
| `SolomonAdvisory` | `ProverbsAdvisory` | `quant/oracle_advisor.py` |
| `SagePredictRequest` | `WisdomPredictRequest` | `backend/api/routes/ml_routes.py` |
| `ArgusEngine` | `WatchtowerEngine` | `core/argus_engine.py` |
| `GEXISCache` | `CounselorCache` | `ai/gexis_cache.py` |
| `GEXISLearningMemory` | `CounselorLearningMemory` | `ai/gexis_learning_memory.py` |
| `GEXISTracer` | `CounselorTracer` | `ai/gexis_tracing.py` |
| `GEXISRateLimiter` | `CounselorRateLimiter` | `ai/gexis_rate_limiter.py` |
| `ApolloMLEngine` | `DiscernmentMLEngine` | `core/apollo_ml_engine.py` |
| `ApolloFeatures` | `DiscernmentFeatures` | `core/apollo_ml_engine.py` |
| `ApolloPrediction` | `DiscernmentPrediction` | `core/apollo_ml_engine.py` |
| `ApolloStrategy` | `DiscernmentStrategy` | `core/apollo_ml_engine.py` |
| `ApolloScanResult` | `DiscernmentScanResult` | `core/apollo_ml_engine.py` |
| `KronosGEXCalculator` | `ChroniclesGEXCalculator` | `quant/kronos_gex_calculator.py` |
| `KronosJob` | `ChroniclesJob` | `backend/services/kronos_infrastructure.py` |
| `KronosWebSocketManager` | `ChroniclesWebSocketManager` | `backend/services/kronos_infrastructure.py` |
| `SolomonTestSuite` | `ProverbsTestSuite` | `scripts/test_solomon_complete.py` |

---

## 8. Directory Renames Needed

### Backend (Python)
| Current Directory | New Directory |
|-------------------|---------------|
| `trading/ares_v2/` | `trading/fortress/` |
| `trading/athena_v2/` | `trading/solomon/` |
| `trading/titan/` | `trading/samson/` |
| `trading/pegasus/` | `trading/anchor/` |
| `trading/icarus/` | `trading/gideon/` |
| `trading/prometheus/` | `trading/jubilee/` |
| `trading/heracles/` | `trading/valor/` |

### Frontend (Pages)
| Current Directory | New Directory |
|-------------------|---------------|
| `frontend/src/app/ares/` | `frontend/src/app/fortress/` |
| `frontend/src/app/athena/` | `frontend/src/app/solomon/` |
| `frontend/src/app/titan/` | `frontend/src/app/samson/` |
| `frontend/src/app/pegasus/` | `frontend/src/app/anchor/` |
| `frontend/src/app/icarus/` | `frontend/src/app/gideon/` |
| `frontend/src/app/prometheus-box/` | `frontend/src/app/jubilee/` |
| `frontend/src/app/heracles/` | `frontend/src/app/valor/` |
| `frontend/src/app/oracle/` | `frontend/src/app/prophet/` |
| `frontend/src/app/sage/` | `frontend/src/app/wisdom/` |
| `frontend/src/app/argus/` | `frontend/src/app/watchtower/` |
| `frontend/src/app/gex-ml/` | `frontend/src/app/stars/` (ORION page) |
| `frontend/src/app/gexis-commands/` | `frontend/src/app/counselor-commands/` |
| `frontend/src/app/hyperion/` | `frontend/src/app/glory/` |
| `frontend/src/app/apollo/` | `frontend/src/app/discernment/` |
| `frontend/src/app/solomon/` | `frontend/src/app/proverbs/` (FIRST, before athena→solomon) |
| `frontend/src/app/nexus/` | `frontend/src/app/covenant/` |
| `frontend/src/app/nexus-demo/` | `frontend/src/app/covenant-demo/` |
| `frontend/src/app/phoenix/` | `frontend/src/app/lazarus/` |
| `frontend/src/app/atlas/` | `frontend/src/app/cornerstone/` |
| `frontend/src/app/hermes/` | `frontend/src/app/shepherd/` |

### Backend Route Files to Rename
| Current File | New File |
|-------------|----------|
| `backend/api/routes/ares_routes.py` | `backend/api/routes/fortress_routes.py` |
| `backend/api/routes/athena_routes.py` | `backend/api/routes/solomon_routes.py` |
| `backend/api/routes/titan_routes.py` | `backend/api/routes/samson_routes.py` |
| `backend/api/routes/pegasus_routes.py` | `backend/api/routes/anchor_routes.py` |
| `backend/api/routes/icarus_routes.py` | `backend/api/routes/gideon_routes.py` |
| `backend/api/routes/prometheus_box_routes.py` | `backend/api/routes/jubilee_routes.py` |
| `backend/api/routes/heracles_routes.py` | `backend/api/routes/valor_routes.py` |
| `backend/api/routes/solomon_routes.py` | `backend/api/routes/proverbs_routes.py` (FIRST!) |
| `backend/api/routes/oracle_routes.py` | `backend/api/routes/prophet_routes.py` |
| `backend/api/routes/argus_routes.py` | `backend/api/routes/watchtower_routes.py` |
| `backend/api/routes/hyperion_routes.py` | `backend/api/routes/glory_routes.py` |
| `backend/api/routes/apollo_routes.py` | `backend/api/routes/discernment_routes.py` |

### AI Module Files to Rename
| Current File | New File |
|-------------|----------|
| `ai/gexis_personality.py` | `ai/counselor_personality.py` |
| `ai/gexis_tools.py` | `ai/counselor_tools.py` |
| `ai/gexis_knowledge.py` | `ai/counselor_knowledge.py` |
| `ai/gexis_commands.py` | `ai/counselor_commands.py` |
| `ai/gexis_learning_memory.py` | `ai/counselor_learning_memory.py` |
| `ai/gexis_extended_thinking.py` | `ai/counselor_extended_thinking.py` |
| `ai/gexis_cache.py` | `ai/counselor_cache.py` |
| `ai/gexis_rate_limiter.py` | `ai/counselor_rate_limiter.py` |
| `ai/gexis_tracing.py` | `ai/counselor_tracing.py` |

### Quant Module Files to Rename
| Current File | New File |
|-------------|----------|
| `quant/oracle_advisor.py` | `quant/prophet_advisor.py` |
| `quant/solomon_enhancements.py` | `quant/proverbs_enhancements.py` |
| `quant/solomon_feedback_loop.py` | `quant/proverbs_feedback_loop.py` |
| `quant/solomon_ai_analyst.py` | `quant/proverbs_ai_analyst.py` |
| `quant/solomon_notifications.py` | `quant/proverbs_notifications.py` |
| `quant/ares_ml_advisor.py` | `quant/fortress_ml_advisor.py` |
| `quant/kronos_gex_calculator.py` | `quant/chronicles_gex_calculator.py` |

### Core Module Files to Rename
| Current File | New File |
|-------------|----------|
| `core/argus_engine.py` | `core/watchtower_engine.py` |
| `core/apollo_ml_engine.py` | `core/discernment_ml_engine.py` |
| `core/apollo_outcome_tracker.py` | `core/discernment_outcome_tracker.py` |

### Frontend Component Files to Rename
| Current File | New File |
|-------------|----------|
| `frontend/src/components/ARGUSAlertsWidget.tsx` | `frontend/src/components/WatchtowerAlertsWidget.tsx` |
| `frontend/src/components/ArgusEnhancements.tsx` | `frontend/src/components/WatchtowerEnhancements.tsx` |
| `frontend/src/components/HyperionEnhancements.tsx` | `frontend/src/components/GloryEnhancements.tsx` |
| `frontend/src/components/OrionStatusBadge.tsx` | `frontend/src/components/StarsStatusBadge.tsx` |
| `frontend/src/components/OracleRecommendationWidget.tsx` | `frontend/src/components/ProphetRecommendationWidget.tsx` |
| `frontend/src/components/SAGEStatusWidget.tsx` | `frontend/src/components/WisdomStatusWidget.tsx` |
| `frontend/src/components/FloatingChatbot.tsx` | Keep name (generic) but update GEXIS refs inside |
| `frontend/src/components/Nexus3D.tsx` | `frontend/src/components/Covenant3D.tsx` |
| `frontend/src/components/NexusCanvas.tsx` | `frontend/src/components/CovenantCanvas.tsx` |
| `frontend/src/components/NexusLoadingScreen.tsx` | `frontend/src/components/CovenantLoadingScreen.tsx` |
| `frontend/src/components/ScanActivityFeed.tsx` | Keep name but update Oracle refs inside |
| `frontend/src/components/DangerZoneCard.tsx` | Keep name but update ARGUS refs inside |

---

## 9. False Positive Exclusion List

| Name | Context | Action |
|------|---------|--------|
| AGAPE | AlphaGEX bot (NO CHANGE requested) | SKIP entirely |
| `trading/mixins/solomon_integration.py` | ADVISORY Solomon, not bot | Rename to `proverbs_integration.py` |
| "oracle" in generic English text | Some comments say "oracle" generically | Review case-by-case |

No MongoDB Atlas, Apollo GraphQL, Phoenix framework, npm Nexus, or GPU Titan references were found. All references are AlphaGEX-specific.

---

## 10. Recommended Execution Order

### Batch 0: SOLOMON Collision Resolution (MUST BE FIRST)
**Scope:** Advisory SOLOMON → PROVERBS
1. Rename `quant/solomon_*.py` → `quant/proverbs_*.py` (4 files)
2. Rename `trading/mixins/solomon_integration.py` → `proverbs_integration.py`
3. Rename `backend/api/routes/solomon_routes.py` → `proverbs_routes.py`
4. Rename `frontend/src/app/solomon/` → `frontend/src/app/proverbs/`
5. Update all class names: Solomon* → Proverbs*
6. Update API prefix: `/api/solomon` → `/api/proverbs`
7. Update all imports and references (~755 Python refs, ~102 Frontend refs)
8. DB table migration: `solomon_*` → `proverbs_*` (9 tables)
9. **VERIFY:** Zero advisory "solomon" references remain in code
10. **BUILD + TEST**

### Batch 1: Low-Risk Bot Renames (small footprint)
- HERMES → SHEPHERD (27 Python refs, minimal)
- ORION → STARS (19 Python refs)
- NEXUS → COVENANT (2 Python refs + frontend 3D viz)

### Batch 2: Medium-Risk Advisory Renames
- SAGE → WISDOM (86 Python refs)
- HYPERION → GLORY (90 Python refs)
- APOLLO → DISCERNMENT (116 Python refs)
- KRONOS → CHRONICLES (221 Python refs)
- GEXIS → COUNSELOR (315 Python refs, 9 module files)

### Batch 3: Medium-Risk Bot Renames
- PHOENIX → LAZARUS (238 Python refs)
- ATLAS → CORNERSTONE (213 Python refs)
- HERACLES → VALOR (551 Python refs)

### Batch 4: High-Risk Bot Renames (large footprint, many cross-refs)
- TITAN → SAMSON (542 Python refs + 149 Frontend)
- ICARUS → GIDEON (619 Python refs + 145 Frontend)
- PEGASUS → ANCHOR (767 Python refs + 170 Frontend)
- ATHENA → SOLOMON (1,009 Python refs + 233 Frontend) — Safe now after Batch 0
- ARES → FORTRESS (1,520 Python refs + 255 Frontend) — Largest, do last

### Batch 5: High-Risk Advisory Renames
- ARGUS → WATCHTOWER (396 Python refs + 241 Frontend)
- ORACLE → PROPHET (2,114 Python refs + 407 Frontend) — LARGEST RENAME, do last

### Batch 6: Database Migrations (with approval gate)
- Generate migration scripts for all ~65 table renames
- Generate UPDATE statements for `bot_name` column values
- Generate migration for `bot_decision_logs` column values
- **REQUIRES EXPLICIT APPROVAL BEFORE EXECUTION**

### Batch 7: Verification
- Global search: zero old-name references remaining
- Build verification (backend + frontend)
- API endpoint smoke tests
- Database query verification

---

## 11. Risk Flags

1. **🔴 SOLOMON COLLISION** — Most dangerous. Mishandling order will corrupt codebase. Advisory SOLOMON → PROVERBS MUST complete before bot ATHENA → SOLOMON begins.

2. **🔴 ORACLE is MASSIVE** — 2,521 total references across 187 files. The word "oracle" appears in variable names, function names, class names, API routes, DB references, frontend components, and test files. This is the single riskiest rename.

3. **🔴 Database table renames are destructive** — 65 tables need `ALTER TABLE ... RENAME TO ...` statements. If done incorrectly, running bots will crash with table-not-found errors. Must coordinate with deployment.

4. **🔴 API route changes break frontend** — All frontend API calls reference old route paths. Backend routes and frontend `api.ts` must be updated simultaneously or behind a version flag.

5. **🟡 Import chain depth** — Many files import from renamed modules. A single missed import breaks the entire import chain. Need to update `__init__.py` files in every trading bot package.

6. **🟡 Scheduler references** — `scheduler/trader_scheduler.py` references EVERY bot by name (~77 unique variable references). This is the central orchestration point and must be updated atomically.

7. **🟡 Cross-bot references** — Bots reference each other (e.g., ARES trader references ATHENA scan activity). These cross-references must be updated consistently.

8. **🟡 Environment variables** — `TRADIER_ARES_SANDBOX_API_KEY_2` must be renamed in Render deployment AND in code simultaneously, or the live ARES bot loses access to its second sandbox account.

9. **🟢 CLAUDE.md** — This 700+ line documentation file references every bot name. Must be updated but is low-risk.

10. **🟢 Test files** — ~80+ test files reference bot names. Tests will fail after rename until updated, but this is expected.

---

## 12. Key Files by Impact

### Critical Files (touch with extreme care)
| File | Lines | Systems Referenced | Why Critical |
|------|-------|--------------------|--------------|
| `scheduler/trader_scheduler.py` | ~1.5K | ALL bots + ORACLE | Central orchestration |
| `quant/oracle_advisor.py` | ~5.2K | ORACLE + all bots | Decision authority |
| `backend/main.py` | ~2K | ALL routers | Import hub |
| `quant/solomon_feedback_loop.py` | ~2.8K | SOLOMON + all bots | 9 DB tables defined here |
| `quant/solomon_enhancements.py` | ~2K | SOLOMON + all bots | Core risk management |
| `frontend/src/lib/api.ts` | ~1K | ALL bots | Frontend API client |
| `frontend/src/lib/hooks/useMarketData.ts` | ~500 | ALL bots | Data fetching hooks |
| `db/config_and_database.py` | ~4K | ARES, ATHENA, TITAN, PEGASUS, ICARUS | Central DB schema |

---

*Report generated: 2026-02-08*
*This is an audit-only report. No code changes have been made.*
