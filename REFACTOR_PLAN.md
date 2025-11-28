# AlphaGEX Architecture Refactor Plan

## Goal
Demo-ready, sellable algo with clean architecture, working features, and testable code.

---

## Current State Analysis

### Two Trader Problem
```
autonomous_paper_trader.py (2,597 lines) - Uses mixins, trades SPY
spx_institutional_trader.py (2,479 lines) - Standalone, trades SPX
```

### Frontend Pages (18 total)
| Page | API Dependency | Priority |
|------|----------------|----------|
| `/trader` | `/api/trader/*` | HIGH |
| `/spx` | `/api/spx/*` | HIGH |
| `/psychology` | `/api/psychology/*` | HIGH |
| `/gex` | `/api/gex/*` | HIGH |
| `/gamma` | `/api/gamma/*` | HIGH |
| `/backtesting` | `/api/autonomous/backtests/*` | MEDIUM |
| `/scanner` | `/api/scanner/*` | MEDIUM |
| `/strategies` | `/api/strategies/*` | MEDIUM |
| `/position-sizing` | `/api/position-sizing/*` | MEDIUM |
| `/ai-copilot` | `/api/ai/*` | LOW |
| `/optimizer` | `/api/optimizer/*` | LOW |
| `/probability` | `/api/probability/*` | LOW |

---

## Target Architecture

```
alphagex/
├── trading/                    # Core trading module
│   ├── __init__.py
│   ├── base_trader.py          # Abstract base class
│   ├── unified_trader.py       # Single trader (SPY + SPX)
│   ├── mixins/                 # Already created
│   │   ├── position_sizer.py
│   │   ├── trade_executor.py
│   │   ├── position_manager.py
│   │   └── performance_tracker.py
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── iron_condor.py
│   │   ├── bull_put_spread.py
│   │   ├── bear_call_spread.py
│   │   └── directional.py
│   └── config/
│       ├── __init__.py
│       ├── settings.py         # ALL settings
│       └── strategies.py       # Strategy definitions
│
├── analysis/                   # Analysis modules
│   ├── __init__.py
│   ├── gex_analyzer.py
│   ├── regime_classifier.py
│   └── psychology_detector.py
│
├── data/                       # Data providers
│   ├── __init__.py
│   ├── unified_provider.py     # Already exists
│   ├── tradier.py
│   └── polygon.py
│
├── backend/                    # API layer (already structured)
│   ├── api/routes/             # 19 route modules ✓
│   └── main.py                 # Entry point ✓
│
└── tests/                      # Test suite
    ├── test_trading/
    ├── test_analysis/
    └── test_api/
```

---

## Execution Plan

### Phase 1: Consolidate Traders (Day 1)
**Goal:** Single trader handles both SPY and SPX

1. **Create `trading/unified_trader.py`**
   - Combine best of both traders
   - Support multiple symbols (SPY, SPX, QQQ)
   - Use existing mixins

2. **Update route modules**
   - `/api/trader/*` → uses UnifiedTrader
   - `/api/spx/*` → uses UnifiedTrader (SPX mode)
   - Both endpoints work, same underlying code

3. **Delete `spx_institutional_trader.py`**

### Phase 2: Centralize Config (Day 1)
**Goal:** Single source of truth

1. **Create `trading/config/settings.py`**
   ```python
   TRADING_CONFIG = {
       'symbols': ['SPY', 'SPX', 'QQQ'],
       'account_size': 50000,
       'max_risk_per_trade': 0.02,
       'max_daily_trades': 3,
       ...
   }

   STRATEGY_CONFIG = {
       'IRON_CONDOR': {...},
       'BULL_PUT_SPREAD': {...},
       ...
   }
   ```

2. **Update all files to import from one place**

### Phase 3: Clean Up Routes (Day 2)
**Goal:** No duplicate endpoints

1. **Merge SPX routes into trader routes**
   - `/api/trader/status` (symbol=SPY|SPX)
   - `/api/trader/performance` (symbol=SPY|SPX)

2. **Keep backward compatibility**
   - `/api/spx/*` redirects to `/api/trader/*?symbol=SPX`

### Phase 4: Test Critical Paths (Day 2)
**Goal:** Core trading logic tested

1. **Test position sizing** (already have 33 tests)
2. **Test trade execution** (new)
3. **Test exit conditions** (new)
4. **Test Kelly calculations** (partially done)

### Phase 5: UI Verification (Day 3)
**Goal:** All pages work

1. Run frontend locally
2. Test each page
3. Fix any broken endpoints

---

## Files to Create

| File | Purpose | Lines Est. |
|------|---------|------------|
| `trading/__init__.py` | Module exports | 20 |
| `trading/base_trader.py` | Abstract base | 100 |
| `trading/unified_trader.py` | Main trader | 800 |
| `trading/config/settings.py` | All config | 200 |
| `trading/config/strategies.py` | Strategy defs | 150 |
| `trading/strategies/__init__.py` | Strategy exports | 30 |

## Files to Delete

| File | Reason |
|------|--------|
| `spx_institutional_trader.py` | Duplicate |
| `deprecated/*` | Already deprecated |
| `trader_*.py` in deprecated/ | Old code |

## Files to Modify

| File | Change |
|------|--------|
| `backend/api/routes/trader_routes.py` | Use UnifiedTrader |
| `backend/api/routes/spx_routes.py` | Redirect to trader |
| `autonomous_scheduler.py` | Use UnifiedTrader |

---

## Risk Mitigation

1. **Don't break working features**
   - Test each endpoint before/after
   - Keep old code until new is verified

2. **Backward compatibility**
   - All existing API endpoints keep working
   - Frontend doesn't need changes

3. **Rollback plan**
   - Git branch for refactor
   - Easy to revert if needed

---

## Success Criteria

- [ ] Single trader class handles all symbols
- [ ] All 18 UI pages work
- [ ] All API endpoints return valid data
- [ ] Core trading logic has tests
- [ ] No duplicate code
- [ ] Config in one place

---

## Time Estimate

| Phase | Time |
|-------|------|
| Phase 1: Consolidate Traders | 4-6 hours |
| Phase 2: Centralize Config | 2-3 hours |
| Phase 3: Clean Up Routes | 2-3 hours |
| Phase 4: Test Critical Paths | 3-4 hours |
| Phase 5: UI Verification | 2-3 hours |
| **Total** | **13-19 hours** |

---

## Start Command

Ready to execute? Let's start with Phase 1: Creating the UnifiedTrader.
