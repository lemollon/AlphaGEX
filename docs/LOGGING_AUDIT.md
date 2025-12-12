# AlphaGEX Logging System Audit

Generated: 2025-12-12

## Full Table Trace - 22 Logging Tables

### ACTIVE TABLES (Production Writers)

| # | Table | Writers | Purpose |
|---|-------|---------|---------|
| 1 | `trading_decisions` | `trading/decision_logger.py` | Main bot decisions (PHOENIX, ATLAS, ARES, HERMES, ORACLE) |
| 2 | `autonomous_trader_logs` | `db/autonomous_database_logger.py` | Detailed scan cycle logs with market context, psychology |
| 3 | `autonomous_trade_log` | `core/autonomous_paper_trader.py` | Simple trade action log (date, time, action, details) |
| 4 | `autonomous_trade_activity` | `trading/mixins/performance_tracker.py` | Trade activity with symbol, pnl_impact |
| 5 | `ml_decision_logs` | `backend/api/routes/ml_routes.py` | ML decision logging |
| 6 | `oracle_predictions` | `quant/oracle_advisor.py` | Oracle predictions with confidence |
| 7 | `ares_ml_outcomes` | `quant/ares_ml_advisor.py` | ARES ML model outcomes |
| 8 | `spx_wheel_ml_outcomes` | `trading/spx_wheel_ml.py` | SPX wheel ML outcomes |
| 9 | `psychology_analysis` | `data/automated_data_collector.py` | Psychology trap analysis |
| 10 | `ai_analysis_history` | `services/data_collector.py` | AI analysis history |
| 11 | `ai_predictions` | `ai/ai_trade_advisor.py` | AI predictions |
| 12 | `ai_performance` | `ai/ai_trade_advisor.py` | AI performance tracking |
| 13 | `ai_recommendations` | `ai/ai_strategy_optimizer.py` | AI recommendations |
| 14 | `wheel_activity_log` | `trading/wheel_strategy.py` | Wheel strategy activity |
| 15 | `gex_change_log` | `data/automated_data_collector.py` | GEX change tracking |
| 16 | `spx_debug_logs` | `utils/spx_debug_logger.py` | Debug logs |
| 17 | `data_collection_log` | `data/automated_data_collector.py`, `services/data_collector.py` | Data collection tracking |
| 18 | `options_collection_log` | `data/option_chain_collector.py` | Options chain collection |

### PREVIOUSLY ORPHAN TABLES (Now Wired)

| # | Table | Status | Writer |
|---|-------|--------|--------|
| 19 | `ml_predictions` | **WIRED** | `quant/ml_regime_classifier.py` |
| 20 | `pattern_learning` | **WIRED** | `ai/autonomous_ml_pattern_learner.py` |
| 21 | `ml_regime_models` | Low priority | Models stored in pickle files |
| 22 | `ml_models` | Low priority | Models stored in pickle files |
| 23 | `psychology_notifications` | Low priority | Alerts work via push notifications |

## DUPLICATES IDENTIFIED - RESOLVED

### 1. Trade Activity Logging (CONSOLIDATED)
- **`autonomous_trade_log`**: Written by `autonomous_paper_trader.py`
  - Fields: date, time, action, details, position_id, success
- **`autonomous_trade_activity`**: Written by `performance_tracker.py` AND `autonomous_paper_trader.py`
  - Fields: timestamp, action, symbol, strike, option_type, contracts, price, reason, success

**Resolution**: DONE - `autonomous_paper_trader.py` now writes to BOTH tables. Backfill exists in `db/config_and_database.py`.

### 2. ML Predictions (WIRED)
- **`ml_predictions`**: Now ACTIVE - written by `quant/ml_regime_classifier.py`
- **`ai_predictions`**: Active (ai_trade_advisor.py)

**Resolution**: DONE - Both tables now have distinct purposes. `ml_predictions` logs regime classifier predictions, `ai_predictions` logs AI advisor predictions.

### 3. ML Models (LOW PRIORITY)
- **`ml_models`**: Models are stored in pickle files, table not critical
- **`ml_regime_models`**: Models are stored in pickle files, table not critical

**Resolution**: Low priority - ML models use pickle file persistence, not database storage.

## ACTION ITEMS - COMPLETED

### Priority 1: Wire Orphan Tables - DONE
1. [x] Wire `ml_predictions` to actual ML prediction code - **WIRED to `quant/ml_regime_classifier.py`**
2. [x] Wire `pattern_learning` to psychology trap detection - **WIRED to `ai/autonomous_ml_pattern_learner.py`**
3. [ ] Wire `ml_regime_models` to regime detection code - *Low priority, models stored in pickle files*
4. [ ] Wire `ml_models` to model persistence - *Low priority, models stored in pickle files*
5. [ ] Wire `psychology_notifications` to alert system - *Low priority, alerts work via push notifications*

### Priority 2: Consolidate Duplicates - DONE
1. [x] Migrate `autonomous_trade_log` → `autonomous_trade_activity` - **UPDATED `core/autonomous_paper_trader.py` to write to both**
2. [x] Backfill exists in `db/config_and_database.py` to sync historical data
3. [x] Keep both tables for backward compatibility

### Priority 3: API Coverage - DONE
All 18 active tables have:
- [x] API read endpoint (via `/api/logs/*` routes)
- [x] UI display component (`/logs` page with 8 categories)
- [x] Export functionality (CSV/JSON)

## Files Modified for Logging
- `frontend/src/app/logs/page.tsx` - Master logs dashboard with export/filter
- `backend/api/routes/logs_routes.py` - Comprehensive API for all tables
- `trading/decision_logger.py` - DecisionLogger class
- `db/autonomous_database_logger.py` - AutonomousDatabaseLogger class
- `quant/ml_regime_classifier.py` - Added `_log_prediction_to_db()` method (WIRES `ml_predictions`)
- `ai/autonomous_ml_pattern_learner.py` - Added `log_pattern_to_db()` method (WIRES `pattern_learning`)
- `core/autonomous_paper_trader.py` - Updated `log_action()` to write to both trade log tables
