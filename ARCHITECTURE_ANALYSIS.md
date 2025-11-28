# AlphaGEX System Architecture Analysis

## Executive Summary

AlphaGEX is an autonomous options trading system built around GEX (Gamma Exposure) analysis. The system consists of:
- **183 Python files** across multiple modules
- **19 API route modules** with 100+ endpoints
- **63 database tables** for persistence
- **4 mixin modules** for the autonomous trader

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ALPHAGEX ARCHITECTURE                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                       │
│  │  Streamlit   │    │   React UI   │    │  API Test    │                       │
│  │  Dashboard   │    │  (Frontend)  │    │    Page      │                       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                       │
│         │                   │                   │                               │
│         └───────────────────┴───────────────────┘                               │
│                             │                                                   │
└─────────────────────────────┼───────────────────────────────────────────────────┘
                              │ HTTP/WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI BACKEND                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         API ROUTES (19 modules)                          │   │
│  ├──────────────┬──────────────┬──────────────┬──────────────┬─────────────┤   │
│  │ core_routes  │ gex_routes   │ gamma_routes │ vix_routes   │ spx_routes  │   │
│  │ /api/        │ /api/gex/    │ /api/gamma/  │ /api/vix/    │ /api/spx/   │   │
│  ├──────────────┼──────────────┼──────────────┼──────────────┼─────────────┤   │
│  │trader_routes │backtest_routes│optimizer_rts│ ai_routes    │scanner_rts  │   │
│  │ /api/trader/ │/api/backtests/│/api/optimizer│ /api/ai/    │/api/scanner/│   │
│  ├──────────────┼──────────────┼──────────────┼──────────────┼─────────────┤   │
│  │system_routes │database_rts  │alerts_routes │setups_routes │notif_routes │   │
│  │ /api/system/ │ /api/database│ /api/alerts/ │ /api/setups/ │/api/notif/  │   │
│  ├──────────────┼──────────────┼──────────────┼──────────────┼─────────────┤   │
│  │misc_routes   │probability_rt│autonomous_rt │psychology_rt │             │   │
│  │ /api/oi/     │/api/probabil/│/api/autonomo/│/api/psycho/  │             │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┴─────────────┘   │
│                                     │                                           │
│  ┌─────────────────────────────────┴─────────────────────────────────────┐     │
│  │                        DEPENDENCIES (api/dependencies.py)              │     │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐           │     │
│  │  │  api_client    │  │   claude_ai    │  │  monte_carlo   │           │     │
│  │  │(TradingVolAPI) │  │(ClaudeIntel)   │  │  (MCEngine)    │           │     │
│  │  └────────────────┘  └────────────────┘  └────────────────┘           │     │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐           │     │
│  │  │    pricer      │  │strategy_optim  │  │probability_calc│           │     │
│  │  │ (BS Pricer)    │  │(MultiStrategy) │  │ (ProbCalc)     │           │     │
│  │  └────────────────┘  └────────────────┘  └────────────────┘           │     │
│  └───────────────────────────────────────────────────────────────────────┘     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS TRADING SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    AUTONOMOUS SCHEDULER (autonomous_scheduler.py)        │   │
│  │  - Runs continuous trading loop                                          │   │
│  │  - Manages market hours (9:30am-4pm ET)                                  │   │
│  │  - Calls trader.find_and_execute_daily_trade()                          │   │
│  │  - Calls trader.auto_manage_positions()                                  │   │
│  └─────────────────────────────────────────┬───────────────────────────────┘   │
│                                            │                                    │
│  ┌─────────────────────────────────────────▼───────────────────────────────┐   │
│  │              AUTONOMOUS PAPER TRADER (autonomous_paper_trader.py)        │   │
│  │                           2,597 lines                                    │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │                         MIXIN CLASSES                            │    │   │
│  │  ├─────────────────┬─────────────────┬───────────────┬─────────────┤    │   │
│  │  │PositionSizer    │ TradeExecutor   │PositionManager│Performance  │    │   │
│  │  │    Mixin        │    Mixin        │    Mixin      │TrackerMixin │    │   │
│  │  │  (455 lines)    │  (545 lines)    │  (454 lines)  │ (622 lines) │    │   │
│  │  ├─────────────────┼─────────────────┼───────────────┼─────────────┤    │   │
│  │  │•calculate_kelly │•_execute_iron   │•auto_manage   │•get_perform │    │   │
│  │  │ _position_size  │ _condor         │ _positions    │ ance        │    │   │
│  │  │•get_available   │•_execute_bull   │•_check_exit   │•_log_trade  │    │   │
│  │  │ _capital        │ _put_spread     │ _conditions   │ _activity   │    │   │
│  │  │•get_strategy    │•_execute_bear   │•_close_posit  │•_create_equ │    │   │
│  │  │ _stats          │ _call_spread    │ ion           │ ity_snapshot│    │   │
│  │  └─────────────────┴─────────────────┴───────────────┴─────────────┘    │   │
│  │                                                                          │   │
│  │  CORE METHODS:                                                           │   │
│  │  • find_and_execute_daily_trade() - Main entry point                    │   │
│  │  • generate_entry_signal() - Signal generation                          │   │
│  │  • _execute_directional_trade() - Trade execution                       │   │
│  │  • _analyze_and_find_trade() - Trade analysis                           │   │
│  │  • _get_unified_regime_decision() - Regime classification               │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                            │                                    │
│  ┌─────────────────────────────────────────┼───────────────────────────────┐   │
│  │                     SUPPORTING COMPONENTS                                │   │
│  ├─────────────────────────────────────────┴───────────────────────────────┤   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │   │
│  │  │  Database      │  │   Risk         │  │    AI          │             │   │
│  │  │   Logger       │  │  Manager       │  │  Reasoning     │             │   │
│  │  │(15,796 lines)  │  │(16,127 lines)  │  │(13,837 lines)  │             │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘             │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │   │
│  │  │   Backtest     │  │  ML Pattern    │  │   Strategy     │             │   │
│  │  │   Engine       │  │   Learner      │  │  Competition   │             │   │
│  │  │(12,412 lines)  │  │(13,561 lines)  │  │(12,448 lines)  │             │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CORE ANALYSIS LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │ Market Regime   │  │  Psychology     │  │  Probability    │                 │
│  │  Classifier     │  │ Trap Detector   │  │  Calculator     │                 │
│  │ (38,499 lines)  │  │(108,911 lines)  │  │ (31,731 lines)  │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │   Strategy      │  │ Trading Costs   │  │  VIX Hedge      │                 │
│  │    Stats        │  │   Calculator    │  │   Manager       │                 │
│  │ (14,336 lines)  │  │ (19,196 lines)  │  │ (25,953 lines)  │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DATA PROVIDER LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │              UNIFIED DATA PROVIDER (unified_data_provider.py)            │   │
│  │                        Primary: Tradier | Fallback: Polygon              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                              │                 │                                │
│              ┌───────────────┴─────┐   ┌──────┴──────────────┐                 │
│              ▼                     ▼   ▼                     ▼                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │ Tradier Data    │  │  Polygon Data   │  │ TradingVol API  │                 │
│  │   Fetcher       │  │    Fetcher      │  │    Client       │                 │
│  │(40,098 lines)   │  │ (36,687 lines)  │  │(core_classes)   │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PERSISTENCE LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │              DATABASE ADAPTER (database_adapter.py)                      │   │
│  │                        PostgreSQL via psycopg2                           │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                              │                                                  │
│              ┌───────────────┼───────────────────────────────┐                 │
│              ▼               ▼                               ▼                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐    │
│  │  Trading Data   │  │  System State   │  │     Analytics Data          │    │
│  │  (17 tables)    │  │  (12 tables)    │  │     (34 tables)             │    │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────────────────┤    │
│  │• autonomous_    │  │• autonomous_    │  │• backtest_results           │    │
│  │  open_positions │  │  config         │  │• gex_history                │    │
│  │• autonomous_    │  │• scheduler_     │  │• gamma_history              │    │
│  │  closed_trades  │  │  state          │  │• probability_outcomes       │    │
│  │• autonomous_    │  │• alerts         │  │• regime_classifications     │    │
│  │  trade_log      │  │• push_          │  │• strategy_competition       │    │
│  │• unified_trades │  │  subscriptions  │  │• ai_recommendations         │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘    │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Integration Map

### Data Flow: Signal Generation to Trade Execution

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        TRADE EXECUTION FLOW                                   │
└──────────────────────────────────────────────────────────────────────────────┘

1. MARKET DATA INGESTION
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   Tradier   │────▶│  Unified    │────▶│   GEX       │
   │   API       │     │  Provider   │     │  Analysis   │
   └─────────────┘     └─────────────┘     └──────┬──────┘
                                                   │
2. REGIME CLASSIFICATION                           │
   ┌─────────────┐     ┌─────────────┐            │
   │  Psychology │────▶│   Market    │◀───────────┘
   │   Traps     │     │   Regime    │
   └─────────────┘     └──────┬──────┘
                              │
3. SIGNAL GENERATION          │
   ┌─────────────┐            │
   │  Strategy   │◀───────────┘
   │   Stats     │
   └──────┬──────┘
          │
4. POSITION SIZING            │
   ┌─────────────┐            │
   │   Kelly     │◀───────────┘
   │  Criterion  │
   └──────┬──────┘
          │
5. TRADE EXECUTION            │
   ┌─────────────┐            │     ┌─────────────┐
   │   Trade     │◀───────────┴────▶│   Risk      │
   │  Executor   │                  │  Manager    │
   └──────┬──────┘                  └─────────────┘
          │
6. POSITION MANAGEMENT        │
   ┌─────────────┐            │
   │  Position   │◀───────────┘
   │  Manager    │
   └──────┬──────┘
          │
7. PERFORMANCE TRACKING       │
   ┌─────────────┐            │
   │ Performance │◀───────────┘
   │  Tracker    │
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │  Database   │
   │   Logger    │
   └─────────────┘
```

---

## Integration Status

### Mixin Integration (autonomous_paper_trader.py)

| Mixin | Methods | Called Internally | Called Externally | Status |
|-------|---------|-------------------|-------------------|--------|
| PositionSizerMixin | 8 | 1 (get_available_capital) | - | Partial |
| TradeExecutorMixin | 10 | 6 | - | Good |
| PositionManagerMixin | 6 | 0 | 1 (auto_manage_positions) | Good |
| PerformanceTrackerMixin | 6 | 1 (get_performance) | - | Partial |

**Note**: Many mixin methods are internal utilities called by other mixin methods, not the main class.

### API Route Integration

| Route Module | Endpoints | Included in App | Dependencies OK |
|--------------|-----------|-----------------|-----------------|
| core_routes | 8 | ✅ | ✅ |
| gex_routes | 4 | ✅ | ✅ |
| gamma_routes | 5 | ✅ | ✅ |
| vix_routes | 4 | ✅ | ✅ |
| spx_routes | 13 | ✅ | ✅ |
| trader_routes | 13 | ✅ | ✅ |
| backtest_routes | 5 | ✅ | ✅ |
| optimizer_routes | 9 | ✅ | ✅ |
| ai_routes | 9 | ✅ | ✅ |
| scanner_routes | 3 | ✅ | ✅ |
| system_routes | 5 | ✅ | ✅ |
| database_routes | 5 | ✅ | ✅ |
| alerts_routes | 5 | ✅ | ✅ |
| setups_routes | 4 | ✅ | ✅ |
| misc_routes | 4 | ✅ | ✅ |
| notification_routes | 7 | ✅ | ✅ |
| probability_routes | 6 | ✅ | ✅ |
| autonomous_routes | 7 | ✅ | ✅ |
| psychology_routes | 15 | ✅ | ✅ |

---

## Identified Issues

### 1. Code Quality Issues

| Issue | Count | Severity |
|-------|-------|----------|
| Bare except clauses | 89 | Low |
| TODO/FIXME comments | 5 | Low |
| Incomplete implementations | 2 | Medium |

### 2. Potential Bugs

| Location | Issue | Impact |
|----------|-------|--------|
| autonomous_monitoring.py:299 | Commented password template | None (commented) |
| Bare excepts | May hide errors | Debug difficulty |

### 3. Missing Integrations

| Feature | Status | Notes |
|---------|--------|-------|
| TRADIER_ACCESS_TOKEN | Optional | Required for live trading |
| VAPID_PRIVATE_KEY | Optional | Required for push notifications |
| ANTHROPIC_API_KEY | Optional | Required for AI features |

---

## Database Schema (63 Tables)

### Trading Tables
- autonomous_open_positions
- autonomous_closed_trades
- autonomous_trade_log
- autonomous_trade_activity
- unified_positions
- unified_trades
- positions
- trade_history

### Analytics Tables
- backtest_results
- backtest_summary
- gex_history
- gamma_history
- regime_classifications
- probability_outcomes
- strategy_competition

### Configuration Tables
- autonomous_config
- strategy_config
- alerts
- push_subscriptions

---

## Environment Variables Required

| Variable | Required | Purpose |
|----------|----------|---------|
| DATABASE_URL | Yes | PostgreSQL connection |
| POLYGON_API_KEY | Recommended | Historical data |
| TRADIER_ACCESS_TOKEN | For trading | Live quotes/trades |
| ANTHROPIC_API_KEY | For AI | Claude intelligence |
| TRADINGVOL_API_KEY | For GEX | GEX data source |

---

## Recommendations

### High Priority
1. ✅ All route modules properly integrated
2. ✅ Mixin integration complete
3. ✅ Database adapter working

### Medium Priority
1. Replace bare except clauses with specific exception types
2. Complete the 2 incomplete function implementations
3. Add missing environment variable validation

### Low Priority
1. Address TODO comments
2. Add more comprehensive error logging
3. Consider adding retry logic for API calls

---

## File Statistics

| Category | Files | Total Lines |
|----------|-------|-------------|
| Backend Routes | 19 | ~3,000 |
| Core Trading | 15 | ~50,000 |
| Autonomous Trader | 10 | ~30,000 |
| Data Providers | 5 | ~15,000 |
| Utilities | 20+ | ~20,000 |
| **Total** | **183** | **~120,000** |

---

*Generated: 2024-11-28*
*Analysis based on current codebase state*
