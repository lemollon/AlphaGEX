# AlphaGEX Database Schema Registry

> **Last Updated:** 2025-12-03
> **Schema File:** `db/config_and_database.py`
> **Database:** PostgreSQL

## Overview

This document is the **single source of truth** for all database tables in AlphaGEX. Every table MUST be:
1. Defined in `db/config_and_database.py`
2. Documented in this registry
3. Have a clear owner/purpose

## Quick Reference

| Category | Tables | Status |
|----------|--------|--------|
| Core Trading | 18 | Active |
| Market Data | 16 | Active |
| AI/ML | 10 | Active |
| Backtest | 14 | Active |
| User Features | 12 | User-Activated |
| System | 8 | Active |
| SPX Wheel | 12 | Active |
| Validation/Debug | 5 | Development |
| Planned (Orphaned) | 4 | Not Yet Wired |
| **Total** | **95** | |

---

## Core Trading Tables

### autonomous_config
- **Purpose:** Trader configuration key-value pairs
- **Timestamp Column:** None (static config)
- **Insert Source:** `core/autonomous_paper_trader.py`
- **Frequency:** One-time + updates

### autonomous_open_positions
- **Purpose:** Currently open trading positions
- **Timestamp Column:** `created_at`, `last_updated`
- **Insert Source:** `trading/mixins/position_manager.py`
- **Frequency:** Per position entry

### autonomous_closed_trades
- **Purpose:** Historical closed trades (audit trail)
- **Timestamp Column:** `created_at`, `exit_date`
- **Insert Source:** `trading/mixins/position_manager.py`
- **Frequency:** Per trade exit

### autonomous_trade_log
- **Purpose:** Trade execution log
- **Timestamp Column:** `date`, `time` (TEXT)
- **Insert Source:** `core/autonomous_paper_trader.py`
- **Frequency:** Per trade

### autonomous_trade_activity
- **Purpose:** Trade activity feed
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/mixins/performance_tracker.py`
- **Frequency:** Per trade action

### autonomous_live_status
- **Purpose:** Live trader status snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/autonomous_paper_trader.py`
- **Frequency:** Every 5 minutes

### autonomous_equity_snapshots
- **Purpose:** Equity curve snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/mixins/performance_tracker.py`
- **Frequency:** Every 5 minutes

### trading_decisions
- **Purpose:** Complete decision audit trail
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/decision_logger.py`
- **Frequency:** Per trading decision

### trades
- **Purpose:** Simplified trade records
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backfilled from autonomous_positions
- **Frequency:** Per trade

### positions
- **Purpose:** General positions tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** AI agents
- **Frequency:** Per position

---

## Market Data Tables

### gex_history
- **Purpose:** Main GEX historical data for charts
- **Timestamp Column:** `timestamp`
- **Insert Source:** `services/data_collector.py`
- **Frequency:** Every 5 minutes

### gamma_history
- **Purpose:** Extended gamma snapshots with more fields
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gamma_tracking_database.py`
- **Frequency:** Every 5 minutes

### gamma_daily_summary
- **Purpose:** Daily aggregated gamma data
- **Timestamp Column:** `date`
- **Insert Source:** `gamma/gamma_tracking_database.py`
- **Frequency:** Daily

### gex_levels
- **Purpose:** GEX strike levels
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backfilled from gex_history
- **Frequency:** Every 5 minutes

### gex_snapshots_detailed
- **Purpose:** Detailed GEX with strike data
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gex_data_tracker.py`
- **Frequency:** Per request

### gamma_strike_history
- **Purpose:** Strike-level gamma history
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gex_data_tracker.py`
- **Frequency:** Per collection

### market_data
- **Purpose:** Market data snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** `services/data_collector.py`
- **Frequency:** Every 5 minutes

### historical_open_interest
- **Purpose:** Historical OI data
- **Timestamp Column:** `date`
- **Insert Source:** `gamma/gex_data_tracker.py`
- **Frequency:** Daily

### regime_signals
- **Purpose:** Psychology regime signals
- **Timestamp Column:** `timestamp`, `created_at`
- **Insert Source:** `core/psychology_trap_detector.py`
- **Frequency:** Every 5 minutes

### regime_classifications
- **Purpose:** Market regime classification history
- **Timestamp Column:** `timestamp`
- **Insert Source:** `unified_trading_engine.py`
- **Frequency:** Per classification

### spy_correlation
- **Purpose:** SPY correlation tracking
- **Timestamp Column:** `date`
- **Insert Source:** `gamma/gamma_tracking_database.py`
- **Frequency:** Daily

### gamma_correlation
- **Purpose:** Multi-symbol gamma correlation
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gamma_correlation_tracker.py`
- **Frequency:** Per calculation

---

## AI/ML Tables

### ai_predictions
- **Purpose:** AI model predictions
- **Timestamp Column:** `timestamp`, `prediction_date`
- **Insert Source:** `ai/ai_trade_advisor.py`
- **Frequency:** Per prediction

### ai_performance
- **Purpose:** AI model performance tracking
- **Timestamp Column:** `date`
- **Insert Source:** `ai/ai_trade_advisor.py`
- **Frequency:** Daily

### ai_recommendations
- **Purpose:** AI trade recommendations
- **Timestamp Column:** `timestamp`
- **Insert Source:** `ai/ai_strategy_optimizer.py`
- **Frequency:** Per recommendation

### pattern_learning
- **Purpose:** Pattern learning history
- **Timestamp Column:** `last_seen`, `created_at`
- **Insert Source:** `ai/ai_trade_advisor.py`
- **Frequency:** Per pattern

### ml_predictions
- **Purpose:** ML model predictions
- **Timestamp Column:** `timestamp`
- **Insert Source:** ML pipeline
- **Frequency:** Per prediction

### probability_predictions
- **Purpose:** Probability predictions
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/probability_calculator.py`
- **Frequency:** Per decision

---

## Backtest Tables

### backtest_results
- **Purpose:** Backtest result summaries
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backtest/backtest_framework.py`
- **Frequency:** Weekly refresh + on-demand

### backtest_summary
- **Purpose:** Backtest session metadata
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backtest/autonomous_backtest_engine.py`
- **Frequency:** Per backtest

### backtest_trades
- **Purpose:** Individual backtest trades
- **Timestamp Column:** `timestamp`
- **Insert Source:** `services/data_collector.py`
- **Frequency:** During backtests

### spx_wheel_backtest_runs
- **Purpose:** SPX backtest run metadata
- **Timestamp Column:** None
- **Insert Source:** `backend/api/routes/spx_backtest_routes.py`
- **Frequency:** User-triggered

### spx_wheel_backtest_equity
- **Purpose:** SPX backtest equity curves
- **Timestamp Column:** `backtest_date`
- **Insert Source:** `backtest/spx_premium_backtest.py`
- **Frequency:** User-triggered

### spx_wheel_backtest_trades
- **Purpose:** SPX backtest trade records
- **Timestamp Column:** `backtest_date`
- **Insert Source:** `backtest/spx_premium_backtest.py`
- **Frequency:** User-triggered

### sucker_statistics
- **Purpose:** Psychology backtest statistics
- **Timestamp Column:** None
- **Insert Source:** `backtest/psychology_backtest.py`
- **Frequency:** Per psychology backtest

### psychology_analysis
- **Purpose:** Psychology analysis snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backfilled from regime_signals
- **Frequency:** Every 5 minutes

---

## User-Activated Feature Tables

### alerts
- **Purpose:** User-defined price/GEX alerts
- **Timestamp Column:** `created_at`
- **Insert Source:** `backend/api/routes/alerts_routes.py`
- **Frequency:** User-activated

### alert_history
- **Purpose:** Alert trigger history
- **Timestamp Column:** `triggered_at`
- **Insert Source:** `backend/api/routes/alerts_routes.py`
- **Frequency:** Per alert trigger

### trade_setups
- **Purpose:** Saved trade setups
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backend/api/routes/setups_routes.py`
- **Frequency:** User-activated

### conversations
- **Purpose:** AI copilot chat history
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/intelligence_and_strategies.py`
- **Frequency:** User-activated

### push_subscriptions
- **Purpose:** Push notification subscriptions
- **Timestamp Column:** `created_at`
- **Insert Source:** `backend/push_notification_service.py`
- **Frequency:** User-activated

### wheel_cycles
- **Purpose:** Wheel strategy cycles
- **Timestamp Column:** `start_date`, `created_at`
- **Insert Source:** `trading/wheel_strategy.py`
- **Frequency:** When wheel strategy active

### wheel_legs
- **Purpose:** Wheel strategy option legs
- **Timestamp Column:** `open_date`, `created_at`
- **Insert Source:** `trading/wheel_strategy.py`
- **Frequency:** When wheel strategy active

### wheel_activity_log
- **Purpose:** Wheel strategy action log
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/wheel_strategy.py`
- **Frequency:** When wheel strategy active

### vix_hedge_signals
- **Purpose:** VIX hedge signals
- **Timestamp Column:** `signal_date`, `created_at`
- **Insert Source:** `core/vix_hedge_manager.py`
- **Frequency:** When VIX hedging active

### vix_hedge_positions
- **Purpose:** VIX hedge positions
- **Timestamp Column:** `entry_date`, `created_at`
- **Insert Source:** `core/vix_hedge_manager.py`
- **Frequency:** When VIX hedging active

---

## System Tables

### background_jobs
- **Purpose:** Background job tracking
- **Timestamp Column:** `started_at`, `completed_at`
- **Insert Source:** `backend/jobs/background_jobs.py`
- **Frequency:** Per job

### scheduler_state
- **Purpose:** Scheduler state persistence
- **Timestamp Column:** `updated_at`
- **Insert Source:** `scheduler/trader_scheduler.py`
- **Frequency:** Every 5 minutes

### data_collection_log
- **Purpose:** Data collection audit trail
- **Timestamp Column:** `timestamp`
- **Insert Source:** `services/data_collector.py`
- **Frequency:** Per collection

### performance
- **Purpose:** Daily performance summary
- **Timestamp Column:** `date`
- **Insert Source:** `monitoring/daily_performance_aggregator.py`
- **Frequency:** Daily EOD

### recommendations
- **Purpose:** Trading recommendations
- **Timestamp Column:** `timestamp`
- **Insert Source:** Recommendation system
- **Frequency:** Per setup

---

## Data Collection Tables (Empty Until Wired)

These tables have INSERT methods in `services/data_collector.py` but need to be called:

| Table | Method | Status |
|-------|--------|--------|
| greeks_snapshots | `store_greeks()` | Needs wiring |
| vix_term_structure | `store_vix_term_structure()` | Needs wiring |
| options_flow | `store_options_flow()` | Needs wiring |
| ai_analysis_history | `store_ai_analysis()` | Needs wiring |
| market_snapshots | `store_market_snapshot()` | Needs wiring |
| position_sizing_history | `store_position_sizing()` | Needs wiring |
| price_history | `store_prices()` | Called by polygon |

---

## Validation Tables

### paper_signals
- **Purpose:** Paper trading signals
- **Timestamp Column:** `timestamp`
- **Insert Source:** `validation/quant_validation.py`
- **Frequency:** When validation active

### paper_outcomes
- **Purpose:** Paper trading outcomes
- **Timestamp Column:** `timestamp`
- **Insert Source:** `validation/quant_validation.py`
- **Frequency:** When validation active

---

## Unified Trading Engine Tables

### unified_positions
- **Purpose:** Unified engine positions
- **Timestamp Column:** `entry_date`, `created_at`
- **Insert Source:** `unified_trading_engine.py`
- **Frequency:** Engine-internal

### unified_trades
- **Purpose:** Unified engine trades
- **Timestamp Column:** `entry_date`, `exit_date`
- **Insert Source:** `unified_trading_engine.py`
- **Frequency:** Engine-internal

### strategy_competition
- **Purpose:** Strategy competition tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/autonomous_strategy_competition.py`
- **Frequency:** When competition active

---

## Additional Core Trading Tables

### autonomous_positions
- **Purpose:** Raw autonomous positions table (internal)
- **Timestamp Column:** `created_at`
- **Insert Source:** `core/autonomous_paper_trader.py`
- **Frequency:** Per position

### autonomous_trader_logs
- **Purpose:** Detailed trader action logs
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/autonomous_paper_trader.py`
- **Frequency:** Per action

### account_state
- **Purpose:** Account state snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** Trading engine
- **Frequency:** Per update

---

## Additional Market Data Tables

### gamma_expiration_timeline
- **Purpose:** Gamma expiration timeline tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gamma_tracking_database.py`
- **Frequency:** Daily

### forward_magnets
- **Purpose:** Forward magnet levels
- **Timestamp Column:** `timestamp`
- **Insert Source:** `gamma/gex_data_tracker.py`
- **Frequency:** Per calculation

### options_chain_snapshots
- **Purpose:** Full options chain snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** `data/option_chain_collector.py`
- **Frequency:** Per collection

### options_collection_log
- **Purpose:** Options collection audit log
- **Timestamp Column:** `timestamp`
- **Insert Source:** `data/option_chain_collector.py`
- **Frequency:** Per collection

---

## Additional AI/ML Tables

### ml_models
- **Purpose:** ML model registry
- **Timestamp Column:** `created_at`
- **Insert Source:** ML pipeline
- **Frequency:** Per model training

### calibration_history
- **Purpose:** Probability calibration history
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/probability_calculator.py`
- **Frequency:** Per calibration

### probability_outcomes
- **Purpose:** Probability prediction outcomes
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/probability_calculator.py`
- **Frequency:** Per prediction

### probability_weights
- **Purpose:** Probability weight factors
- **Timestamp Column:** `updated_at`
- **Insert Source:** `core/probability_calculator.py`
- **Frequency:** Per weight update

---

## Additional Backtest Tables

### dte_performance
- **Purpose:** DTE (Days to Expiration) performance tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backtest engine
- **Frequency:** Per backtest

### strike_performance
- **Purpose:** Strike-level performance tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backtest engine
- **Frequency:** Per backtest

### spread_width_performance
- **Purpose:** Spread width performance analysis
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backtest engine
- **Frequency:** Per backtest

### greeks_performance
- **Purpose:** Greeks-based performance tracking
- **Timestamp Column:** `timestamp`
- **Insert Source:** Backtest engine
- **Frequency:** Per backtest

---

## Additional User Feature Tables

### scanner_history
- **Purpose:** Scanner run history
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backend/api/routes/scanner_routes.py`
- **Frequency:** Per scan

### strategy_config
- **Purpose:** Strategy configuration storage
- **Timestamp Column:** `updated_at`
- **Insert Source:** `backend/api/routes/trader_routes.py`
- **Frequency:** Per config change

### psychology_notifications
- **Purpose:** Psychology alert notifications
- **Timestamp Column:** `timestamp`
- **Insert Source:** `core/psychology_trap_detector.py`
- **Frequency:** Per notification

### liberation_outcomes
- **Purpose:** Liberation trade outcome tracking
- **Timestamp Column:** `created_at`
- **Insert Source:** `core/psychology_trap_detector.py`
- **Frequency:** Per liberation event

---

## Debug/Development Tables

### spx_debug_logs
- **Purpose:** SPX system debug logging
- **Timestamp Column:** `timestamp`
- **Insert Source:** `utils/spx_debug_logger.py`
- **Frequency:** Development only

---

## SPX Wheel System Tables

### spx_wheel_parameters
- **Purpose:** SPX wheel strategy parameters configuration
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/spx_wheel_system.py`
- **Frequency:** Per calibration

### spx_wheel_positions
- **Purpose:** SPX wheel open/closed positions
- **Timestamp Column:** `opened_at`, `closed_at`
- **Insert Source:** `trading/spx_wheel_system.py`
- **Frequency:** Per trade

### spx_wheel_performance
- **Purpose:** Daily SPX wheel performance tracking
- **Timestamp Column:** `date`
- **Insert Source:** `trading/spx_wheel_system.py`
- **Frequency:** Daily

### spx_wheel_greeks
- **Purpose:** Position Greeks snapshots
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/risk_management.py`
- **Frequency:** Per update

### spx_wheel_reconciliation
- **Purpose:** Broker reconciliation logs
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/risk_management.py`
- **Frequency:** Per reconciliation

### spx_wheel_alerts
- **Purpose:** SPX wheel trading alerts
- **Timestamp Column:** `timestamp`
- **Insert Source:** `trading/alerts.py`
- **Frequency:** Per alert

### spx_wheel_multileg_positions
- **Purpose:** Multi-leg strategy positions
- **Timestamp Column:** `opened_at`
- **Insert Source:** `trading/multi_leg_strategies.py`
- **Frequency:** Per position

### spx_wheel_ml_outcomes
- **Purpose:** ML prediction outcomes tracking
- **Timestamp Column:** `created_at`
- **Insert Source:** `trading/spx_wheel_ml.py`
- **Frequency:** Per outcome

### spx_wheel_backtest_runs
- **Purpose:** SPX backtest run metadata
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backend/api/routes/spx_backtest_routes.py`
- **Frequency:** Per backtest

### spx_wheel_backtest_equity
- **Purpose:** SPX backtest equity curve
- **Timestamp Column:** `date`
- **Insert Source:** `backtest/spx_premium_backtest.py`
- **Frequency:** Per snapshot

### spx_wheel_backtest_trades
- **Purpose:** SPX backtest trade details
- **Timestamp Column:** `backtest_date`
- **Insert Source:** `backtest/spx_premium_backtest.py`
- **Frequency:** Per trade

### ml_decision_logs
- **Purpose:** ML decision audit trail
- **Timestamp Column:** `timestamp`
- **Insert Source:** `backend/api/routes/ml_routes.py`
- **Frequency:** Per ML action

---

## Planned Tables (Orphaned - Not Yet Wired)

> **Note:** These tables are defined in the schema but have no INSERT/SELECT statements yet.
> They represent planned features and should NOT be deleted.

### backtest_runs
- **Purpose:** Backtest run metadata and tracking
- **Timestamp Column:** `started_at`
- **Status:** ⚠️ Planned - INSERT not yet wired
- **Future Use:** Will track individual backtest executions

### gex_change_log
- **Purpose:** GEX change event logging
- **Timestamp Column:** `timestamp`
- **Status:** ⚠️ Planned - INSERT not yet wired
- **Future Use:** Will log significant GEX changes for analysis

### spx_institutional_positions
- **Purpose:** SPX institutional position tracking
- **Timestamp Column:** `timestamp`
- **Status:** ⚠️ Planned - INSERT not yet wired
- **Future Use:** Will track institutional SPX positions

### strategy_comparison_history
- **Purpose:** Strategy comparison results storage
- **Timestamp Column:** `timestamp`
- **Status:** ⚠️ Planned - INSERT not yet wired
- **Future Use:** Will store strategy comparison analysis

---

## Schema Rules

### DO:
1. Define ALL tables in `db/config_and_database.py`
2. Document new tables in this registry
3. Include a timestamp column (`timestamp`, `created_at`, or `date`)
4. Add appropriate indexes
5. Use PostgreSQL syntax (SERIAL, TIMESTAMPTZ)

### DON'T:
1. Create tables in feature files (duplicate definitions)
2. Use SQLite syntax (AUTOINCREMENT, DATETIME)
3. Add tables without documentation
4. Delete tables without migration script

---

## Maintenance

- **Weekly:** Run `python scripts/validate_schema.py`
- **Per PR:** Check for database changes
- **Monthly:** Review this registry for accuracy

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2025-12-03 | Added 12 SPX wheel tables, total now 95 tables | Claude |
| 2025-12-03 | Updated to 84 tables, documented orphaned tables | Claude |
| 2025-12-03 | Initial consolidation - 56 tables | Claude |
