# CLAUDE.md - AlphaGEX AI Assistant Guide

This document provides comprehensive context for AI assistants working with the AlphaGEX codebase.

## Project Overview

**AlphaGEX** is an autonomous options trading platform built around GEX (Gamma Exposure) analysis. It predicts market maker behavior to generate profitable options trading signals.

### Core Value Proposition
- Profitable Monday/Tuesday directional plays
- Iron Condor timing optimization
- Market regime classification (MOVE vs. DO NOTHING)
- Automated trading via 8 specialized bots: ARES, ATHENA, TITAN, PEGASUS, ICARUS, PHOENIX, ATLAS, HERMES

### Key Metrics
- ~590 Python files across multiple modules
- 50 API route modules with 635+ endpoints
- 49 database tables for persistence
- ~300,000 lines of Python code

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                       │
│  React 18 + TypeScript + Tailwind CSS + SWR                     │
│  Deployed: Vercel                                                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTP/REST
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                           │
│  Python 3.11 + PostgreSQL + 50 Route Modules                    │
│  Deployed: Render                                                │
├─────────────────────────────────────────────────────────────────┤
│  BACKGROUND WORKERS (Render)                                     │
│  - alphagex-trader: All 8 trading bots                          │
│  - alphagex-collector: Automated data collection                 │
│  - alphagex-backtester: Long-running backtest jobs              │
├─────────────────────────────────────────────────────────────────┤
│  ML ADVISORY LAYER                                               │
│  - SAGE: XGBoost ML probability predictions                     │
│  - Oracle: Primary decision maker for all bots                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AlphaGEX/
├── backend/                    # FastAPI backend API
│   ├── main.py                 # Entry point (~2K lines)
│   ├── api/
│   │   ├── routes/             # 50 route modules
│   │   │   ├── core_routes.py      # Health, time endpoints
│   │   │   ├── gex_routes.py       # GEX data endpoints
│   │   │   ├── gamma_routes.py     # Gamma analysis
│   │   │   ├── ares_routes.py      # ARES Iron Condor bot
│   │   │   ├── athena_routes.py    # ATHENA Directional spreads
│   │   │   ├── titan_routes.py     # TITAN Aggressive IC bot
│   │   │   ├── oracle_routes.py    # Oracle ML advisory
│   │   │   ├── ml_routes.py        # SAGE ML endpoints
│   │   │   ├── logs_routes.py      # Unified logging (22+ tables)
│   │   │   ├── data_transparency_routes.py  # Hidden data exposure
│   │   │   ├── trader_routes.py    # Trading operations
│   │   │   ├── prometheus_box_routes.py  # PROMETHEUS Box Spread Synthetic Borrowing
│   │   │   └── ...                 # 38 more route files
│   │   ├── dependencies.py     # Shared API dependencies
│   │   └── utils.py            # API utilities
│   ├── services/               # Background services
│   ├── tests/                  # Backend unit tests
│   └── requirements.txt        # Backend dependencies
│
├── frontend/                   # Next.js React frontend
│   ├── src/
│   │   ├── app/                # Next.js App Router (50+ pages)
│   │   │   ├── page.tsx            # Dashboard home
│   │   │   ├── ares/               # ARES Iron Condor page
│   │   │   ├── athena/             # ATHENA spreads page
│   │   │   ├── titan/              # TITAN Aggressive IC page
│   │   │   ├── pegasus/            # PEGASUS Weekly IC page
│   │   │   ├── icarus/             # ICARUS Aggressive Directional
│   │   │   ├── prometheus-box/     # PROMETHEUS Box Spread Synthetic Borrowing
│   │   │   ├── sage/               # SAGE ML Advisor dashboard
│   │   │   ├── oracle/             # Oracle predictions
│   │   │   ├── gamma/0dte/         # 0DTE Gamma Expiration Tracker
│   │   │   ├── argus/              # Real-time gamma viz
│   │   │   ├── gex/                # GEX analysis
│   │   │   └── ...                 # 32+ more pages
│   │   ├── components/         # Reusable React components
│   │   ├── hooks/              # Custom React hooks
│   │   └── lib/
│   │       └── api.ts          # API client with types
│   ├── __tests__/              # Frontend unit tests (Jest)
│   ├── package.json            # npm dependencies
│   └── tailwind.config.ts      # Tailwind CSS config
│
├── core/                       # Core trading logic (~21K lines total)
│   ├── autonomous_paper_trader.py  # Main trader (~2.8K)
│   ├── intelligence_and_strategies.py  # AI strategies (~3.4K)
│   ├── psychology_trap_detector.py    # Psychology system (~2.6K)
│   ├── market_regime_classifier.py    # Regime detection (~1.2K)
│   ├── probability_calculator.py      # Probability engine (~800)
│   └── ...
│
├── trading/                    # Trading execution
│   ├── ares_v2/                # ARES Iron Condor bot (~5K lines)
│   │   ├── trader.py               # ARESTrader class
│   │   ├── models.py               # ARESConfig
│   │   ├── db.py                   # ARESDatabase
│   │   ├── executor.py             # Order execution
│   │   └── signals.py              # Signal generation
│   ├── athena_v2/              # ATHENA Directional Spreads bot (~4.4K lines)
│   │   └── (same structure as ares_v2)
│   ├── titan/                  # TITAN Aggressive IC bot
│   │   └── (same structure as ares_v2)
│   ├── pegasus/                # PEGASUS Weekly IC bot
│   │   └── (same structure as ares_v2)
│   ├── icarus/                 # ICARUS Aggressive Directional bot
│   │   └── (same structure as ares_v2)
│   ├── prometheus/             # PROMETHEUS Box Spread Synthetic Borrowing
│   │   ├── models.py               # BoxSpreadPosition, PrometheusConfig
│   │   ├── db.py                   # PrometheusDatabase
│   │   ├── signals.py              # BoxSpreadSignalGenerator
│   │   ├── executor.py             # Order execution, MTM calculation
│   │   └── trader.py               # PrometheusTrader orchestrator
│   ├── spx_wheel_system.py     # SPX Wheel strategy (ATLAS)
│   ├── wheel_strategy.py       # Wheel strategy base
│   ├── risk_management.py      # Risk controls
│   ├── circuit_breaker.py      # DEPRECATED - use solomon_enhancements
│   └── mixins/                 # Trading behavior mixins
│
├── ai/                         # AI/ML integration (~5.2K lines GEXIS)
│   ├── gexis_*.py              # GEXIS AI assistant (9 modules)
│   │   ├── gexis_personality.py    # Core identity, J.A.R.V.I.S. persona
│   │   ├── gexis_tools.py          # 17 agentic tools
│   │   ├── gexis_knowledge.py      # System knowledge base
│   │   ├── gexis_commands.py       # Slash commands
│   │   ├── gexis_learning_memory.py # Prediction tracking
│   │   └── gexis_*.py              # Cache, rate limiter, tracing
│   ├── langchain_*.py          # LangChain integrations
│   ├── ai_strategy_optimizer.py    # Strategy optimization
│   └── ai_trade_advisor.py     # Trade recommendations
│
├── quant/                      # Quantitative analysis
│   ├── oracle_advisor.py       # Oracle predictions (~5.2K lines)
│   ├── solomon_enhancements.py # Circuit breaker replacement
│   ├── gex_probability_models.py   # GEX ML models
│   ├── monte_carlo_kelly.py    # Kelly criterion
│   ├── ml_regime_classifier.py # DEPRECATED - Oracle handles regime
│   └── ensemble_strategy.py    # DEPRECATED - Oracle is sole authority
│
├── data/                       # Data providers
│   ├── unified_data_provider.py    # Tradier/Polygon unified
│   ├── tradier_data_fetcher.py     # Tradier API
│   ├── polygon_data_fetcher.py     # Polygon.io API
│   └── gex_calculator.py       # GEX calculations
│
├── gamma/                      # Gamma-specific modules
│   ├── gamma_expiration_builder.py
│   ├── gamma_alerts.py
│   └── forward_magnets_detector.py
│
├── backtest/                   # Backtesting engines
│   ├── backtest_framework.py   # Core backtest engine
│   ├── zero_dte_*.py           # 0DTE strategy backtests
│   └── wheel_backtest.py       # Wheel strategy backtest
│
├── monitoring/                 # System monitoring
│   ├── autonomous_monitoring.py
│   ├── alerts_system.py
│   └── data_quality_dashboard.py
│
├── scheduler/                  # Background job schedulers
│   └── trader_scheduler.py     # Bot scheduling
│
├── scripts/                    # Utility scripts (170+ files)
│   ├── test_*.py               # Test scripts
│   ├── train_*.py              # ML training scripts
│   └── verify_*.py             # Verification scripts
│
├── tests/                      # Main test suite
│   ├── conftest.py             # Shared pytest fixtures
│   ├── test_*.py               # Test files (~80 files)
│   └── e2e/                    # End-to-end tests
│
├── config.py                   # Central configuration
├── database_adapter.py         # PostgreSQL adapter
├── core_classes_and_engines.py # Core trading classes
├── unified_trading_engine.py   # Unified trading interface
├── requirements.txt            # Python dependencies
├── render.yaml                 # Render deployment config
└── pytest.ini                  # Pytest configuration
```

---

## Tech Stack

### Backend
- **Framework**: FastAPI 0.115+
- **Python**: 3.11
- **Database**: PostgreSQL (via psycopg2)
- **AI/ML**: LangChain 0.3+, Anthropic Claude, scikit-learn, XGBoost 2.x
- **Data Sources**: Tradier (primary), Polygon.io (fallback), TradingVolatility API

### Frontend
- **Framework**: Next.js 14.2 (App Router)
- **React**: 18.2
- **Language**: TypeScript 5.7
- **Styling**: Tailwind CSS 3.4
- **State Management**: SWR for data fetching
- **Charts**: Recharts, Plotly.js, Lightweight Charts
- **UI Components**: Radix UI primitives

### Infrastructure
- **Backend Hosting**: Render (web service + workers)
- **Frontend Hosting**: Vercel
- **Database**: Render PostgreSQL

---

## Development Workflows

### Starting the Backend

```bash
# From project root
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
python main.py
# OR
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

### Starting the Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend available at: http://localhost:3000

### Running Tests

```bash
# Backend tests (from project root)
pytest -v

# With coverage
pytest --cov=core --cov=trading --cov-report=html

# Specific test file
pytest tests/test_gex_calculator.py -v

# Frontend tests
cd frontend
npm test
npm run test:coverage

# E2E tests (Playwright)
npm run test:e2e
```

---

## Environment Variables

### Required Variables

```bash
# Database (Required)
DATABASE_URL=postgresql://user:password@host:5432/alphagex

# GEX Data (Required for GEX features)
TRADING_VOLATILITY_API_KEY=your_key
# OR
TV_USERNAME=your_username

# Live Trading (Required for ARES/ATHENA)
TRADIER_API_KEY=your_production_key
TRADIER_ACCOUNT_ID=your_account_id
TRADIER_SANDBOX_API_KEY=your_sandbox_key
TRADIER_SANDBOX_ACCOUNT_ID=your_sandbox_account
```

### Optional Variables

```bash
# Polygon.io (fallback data source)
POLYGON_API_KEY=your_polygon_key

# AI Features
ANTHROPIC_API_KEY=your_claude_key
CLAUDE_API_KEY=your_claude_key

# ORAT Database (for KRONOS backtester)
ORAT_DATABASE_URL=postgresql://...

# CORS (production)
CORS_ORIGINS=https://your-frontend.vercel.app
```

---

## Key Trading Bots

AlphaGEX operates 8 specialized trading bots, all advised by the Oracle ML system:

### ARES - Aggressive Iron Condor (SPY 0DTE) ✓ LIVE
- **Schedule**: 8:30 AM - 3:30 PM CT, every 5 min
- **Strategy**: Iron Condor with dynamic strike selection on SPY
- **Files**: `trading/ares_v2/`, `backend/api/routes/ares_routes.py`
- **29 API endpoints** - Most mature bot

### ATHENA - Directional Spreads ✓ LIVE
- **Schedule**: 8:35 AM - 2:30 PM CT, every 5 min
- **Strategy**: GEX-based directional spreads on SPY
- **Files**: `trading/athena_v2/`, `backend/api/routes/athena_routes.py`
- **21 API endpoints**

### TITAN - Aggressive SPX Iron Condor ✓ LIVE
- **Schedule**: Multiple trades daily with 30-min cooldown
- **Strategy**: Aggressive Iron Condor on SPX with tighter parameters
- **Parameters**: 15% risk/trade (vs 10%), 40% min win prob (vs 50%), 0.8 SD strikes
- **Files**: `trading/titan/`, `backend/api/routes/titan_routes.py`

### PEGASUS - SPX Weekly Iron Condor ✓ LIVE
- **Schedule**: Every 5 min during market hours
- **Strategy**: Standard SPX Iron Condor, more conservative than TITAN
- **Files**: `trading/pegasus/`, `backend/api/routes/pegasus_routes.py`

### ICARUS - Aggressive Directional ✓ LIVE
- **Schedule**: Every 5 min during market hours
- **Strategy**: Aggressive directional variant of ATHENA on SPY
- **Files**: `trading/icarus/`, `backend/api/routes/icarus_routes.py`

### PROMETHEUS - Standalone Box Spread + IC Trading ✓ PAPER
A self-contained two-part system: borrows capital via box spreads, then trades Iron Condors with that capital.

**Part 1: Box Spread Manager**
- **Schedule**: Daily at 9:30 AM CT (position management cycle)
- **Strategy**: Synthetic borrowing via SPX box spreads
- **Parameters**: 50pt strike width default, 90+ DTE, 30-day roll threshold

**Part 2: IC Trader**
- **Schedule**: Every 5-15 min during market hours
- **Strategy**: Iron Condors using borrowed capital to generate returns
- **Parameters**: Oracle-approved trades, 0DTE-1DTE SPX options

**Files**: `trading/prometheus/`, `backend/api/routes/prometheus_box_routes.py`
**Dashboard**: `/prometheus-box` - 5 tabs (Overview, Positions, Analytics, Education, Calculator)

**Key Features**:
  - Production Tradier API quotes for realistic paper trading
  - Real-time mark-to-market with actual bid/ask spreads
  - PROMETHEUS trades its own ICs (not deploying to ARES/TITAN/PEGASUS)
  - Rolling interest rate transparency and daily briefings
  - Combined performance tracking: IC returns vs borrowing costs
  - Educational mode with comprehensive explanations

**IC Trading Endpoints** (per STANDARDS.md Bot-Specific Requirements):
- `/ic/status` - IC trading status and configuration
- `/ic/positions` - Open IC positions with unrealized P&L
- `/ic/closed-trades` - IC trade history
- `/ic/equity-curve` - Historical IC equity curve
- `/ic/equity-curve/intraday` - Today's IC equity snapshots
- `/ic/performance` - IC win rate, P&L, statistics
- `/ic/logs` - IC activity log for audit trail
- `/ic/signals/recent` - Recent IC signals (scan activity)

**60+ API endpoints** including Box Spread MTM, IC trading, combined performance

### PHOENIX - 0DTE Options ⚠️ PAPER (Partial Implementation)
- **Schedule**: Every 5 min during market hours
- **Strategy**: 0DTE SPY/SPX options via AutonomousPaperTrader
- **Files**: `core/autonomous_paper_trader.py`
- **Note**: No dedicated API routes - uses internal trading logic only

### ATLAS - SPX Wheel ⚠️ LIVE (Partial Implementation)
- **Schedule**: Daily at 9:05 AM CT
- **Strategy**: SPX Wheel premium collection
- **Files**: `trading/spx_wheel_system.py`, `trading/wheel_strategy.py`
- **Note**: No dedicated API routes - scheduled but lacks full API integration

### HERMES - Manual Wheel Manager (Not Automated)
- **Type**: Manual UI-driven bot, not scheduled
- **Strategy**: Manual wheel strategy management via frontend
- **Note**: No routes file - this is by design as a UI-only tool

---

## ML Advisory Systems

### Oracle - Primary Decision Maker
The Oracle is the central ML advisory system that all trading bots consult before taking positions.

- **Role**: Strategy recommendation (IC vs Directional), win probability estimation
- **Inputs**: SAGE predictions, market regime, VIX levels, GEX data
- **Staleness Monitoring**: Tracks `hours_since_training`, `is_model_fresh`, `model_trained_at`
- **Training Sources**: Live outcomes → Database backtests → KRONOS data
- **Files**: `quant/oracle_advisor.py`, `backend/api/routes/oracle_routes.py`

### SAGE - Strategic Algorithmic Guidance Engine
XGBoost-based ML system that feeds probability predictions into Oracle.

- **Model**: XGBoost classifier for trade outcome prediction
- **Training Data**: KRONOS backtests, live trade outcomes
- **Features Used**:
  - Volatility: VIX, VIX percentile, VIX change, expected move
  - GEX: Regime, normalized value, distance to flip point
  - Timing: Day of week, price change, 30-day win rate
- **Capabilities**: Favorable condition identification, position sizing adjustment, calibrated probabilities
- **Limitations**: Cannot predict black swans, does not replace risk management
- **Files**: `backend/api/routes/ml_routes.py` (SAGE endpoints)
- **Dashboard**: `/sage` page with 6 tabs (Overview, Predictions, Features, Performance, Decision Logs, Training)

### ORION - GEX Probability Models for ARGUS/HYPERION
Named after the mighty hunter constellation, ORION provides ML-powered probability predictions that guide ARGUS (0DTE) and HYPERION (Weekly) gamma visualizations.

- **Model**: 5 XGBoost sub-models (classifiers and regressors)
- **Sub-Models**:
  1. **Direction Probability** - UP/DOWN/FLAT classification
  2. **Flip Gravity** - Probability price moves toward flip point
  3. **Magnet Attraction** - Probability price reaches nearest magnet (used for strike probabilities)
  4. **Volatility Estimate** - Expected price range prediction
  5. **Pin Zone Behavior** - Probability of staying pinned between magnets
- **Integration**: Hybrid probability calculation: `combined = (0.6 × ML_prob) + (0.4 × distance_prob)`
- **Auto-Loading**: Models auto-load from PostgreSQL on initialization (singleton pattern)
- **Auto-Training**: Every Sunday at 6:00 PM CT (after QUANT training at 5 PM)
  - Only retrains if models older than 7 days
  - Trains on SPX and SPY historical data
  - Saves to database for persistence across deploys
- **Fallback**: When models not trained, uses 100% distance-based probability
- **Data Sources**:
  - Primary: `gex_structure_daily` table
  - Fallback: `gex_history` table (aggregates intraday snapshots)
- **Files**:
  - Core: `quant/gex_probability_models.py` (GEXProbabilityModels, GEXSignalGenerator)
  - Shared Engine: `core/shared_gamma_engine.py` (calculate_probability_hybrid)
  - ARGUS Engine: `core/argus_engine.py` (gamma_structure building)
  - Scheduler: `scheduler/trader_scheduler.py` (scheduled_gex_ml_training_logic)
- **API Endpoints**:
  ```
  GET  /api/ml/gex-models/status      # Model status, staleness, sub-model states
  POST /api/ml/gex-models/train       # Trigger training on GEX historical data
  POST /api/ml/gex-models/predict     # Get combined prediction
  GET  /api/ml/gex-models/data-status # Training data availability (both sources)
  ```
- **Dashboard**: `/gex-ml` - ORION page with model status, training controls, auto-schedule info

### GEXIS - AI Trading Assistant
J.A.R.V.I.S.-style AI chatbot providing decision support throughout the platform (~5.2K lines).

- **Personality**: Time-aware greetings, Central Time, professional demeanor, "Optionist Prime" user
- **Files** (9 core modules in `ai/`):
  - `gexis_personality.py` - Core identity and prompts
  - `gexis_tools.py` - 17 agentic tools (database, market data, bot control)
  - `gexis_knowledge.py` - Knowledge base (49 database tables documented)
  - `gexis_commands.py` - Slash commands (`/market-hours`, `/suggestion`, `/risk`)
  - `gexis_learning_memory.py` - Self-improving prediction accuracy tracking
  - `gexis_extended_thinking.py` - Claude Extended Thinking for complex analysis
  - `gexis_cache.py` - TTL-based caching (60s market, 30s positions)
  - `gexis_rate_limiter.py` - Token bucket rate limiting
  - `gexis_tracing.py` - Request tracing and telemetry
- **Frontend**: `FloatingChatbot.tsx` (1.1K lines) - Streaming chat widget
- **API Routes**: `backend/api/routes/ai_routes.py` - 35+ endpoints
- **Capabilities**:
  - Real-time market data and bot status queries
  - Bot control with 2-minute confirmation windows
  - Trade opportunity analysis with extended thinking
  - Economic calendar integration (NFP, CPI, FOMC)
  - Learning from prediction outcomes by market regime
  - Conversation export (markdown/JSON)

---

## Removed Legacy Systems (January 2025)

The following systems were removed in favor of **Oracle as the sole decision authority**:

### Circuit Breaker (REMOVED)
- **Old File**: `trading/circuit_breaker.py` - **DELETED**
- **Replacement**: `quant/solomon_enhancements.py`
- **Migration**: Use `get_solomon_enhanced()` for risk checks
- **Reason**: Solomon provides all CircuitBreaker functionality PLUS consecutive loss monitoring, daily loss monitoring, cross-bot correlation tracking, and A/B testing

### Ensemble Strategy (REMOVED)
- **Old File**: `quant/ensemble_strategy.py` - **DELETED**
- **Reason**: "Oracle is god" - weighted voting replaced by Oracle sole authority
- **API behavior**: `/api/quant/ensemble` endpoints return unavailable status

### ML Regime Classifier (REMOVED)
- **Old File**: `quant/ml_regime_classifier.py` - **DELETED**
- **Reason**: "Only blocked trades unnecessarily" - Oracle handles all regime decisions
- **API behavior**: Routes gracefully handle module absence

### GEX Directional ML (REMOVED)
- **Status**: Removed from all bot signal files
- **Reason**: Redundant with Oracle predictions

### Kill Switch (REMOVED)
- **Status**: Functionality removed from Solomon integration
- **Note**: "Always allow trading" - Oracle controls trade frequency instead

### Daily Trade Limits (REMOVED)
- **Status**: Removed from ARES, ICARUS traders
- **Note**: Oracle now decides trade frequency

### LangChain AI System (REMOVED)
- **Old Files**: `ai/langchain_*.py`, `ai/ai_trade_advisor.py`, `ai/ai_trade_recommendations.py`, `ai/ai_strategy_optimizer.py`, `ai/autonomous_ai_reasoning.py`
- **Reason**: Unnecessary abstraction layer - GEXIS provides all AI capabilities via direct Anthropic SDK
- **Replacement**: GEXIS AI assistant (`ai/gexis_*.py`) - 9 modules, 17 tools
- **API behavior**: `/api/ai/optimize-strategy`, `/api/ai/trade-advice`, `/api/optimizer/*` return 503 with redirect to GEXIS
- **Dependencies removed**: `langchain`, `langchain-anthropic`, `langchain-community`, `langchain-core`

---

## Dashboard Features

### 0DTE Gamma Expiration Tracker (`/gamma/0dte`)
Real-time 0DTE gamma analysis with actionable trading strategies.

**Analysis Views**:
1. **TODAY'S IMPACT** - Intraday trading opportunities
   - Directional prediction (UPWARD/DOWNWARD/SIDEWAYS with probabilities)
   - Current day gamma impact
   - Fade the Close strategy (3:45pm entries)
   - ATM Straddle into expiration

2. **WEEKLY EVOLUTION** - Positional trading
   - Weekly gamma structure with decay patterns
   - Daily risk levels for entire week
   - Aggressive Theta Farming (Mon-Wed)
   - Delta Buying (Thu-Fri)

3. **VOLATILITY CLIFFS** - Risk management by day
   - Flip point calculations
   - Call/put wall identification
   - Pre-Expiration Volatility Scalp (Friday)
   - Post-Expiration Directional Positioning

**0DTE Straddle Playbook**:
- Entry timing: 9:30-10:30 AM ET
- Strike selection methodology
- Exit rules with profit targets
- Risk/reward calculations

**Files**: `frontend/src/app/gamma/0dte/page.tsx` (715 lines)

### ARGUS - Real-Time 0DTE Gamma Visualization (`/argus`)
Named after the "all-seeing" giant with 100 eyes from Greek mythology. ARGUS provides real-time gamma analysis with comprehensive market structure signals.

**Core Features**:
- Real-time gamma visualization with per-strike data
- Danger zone detection (BUILDING/COLLAPSING/SPIKE gamma)
- Pin strike prediction with ML-enhanced probability
- Magnet identification (high gamma attractors)
- Gamma regime tracking (POSITIVE/NEGATIVE/NEUTRAL)
- **ML Integration**: Uses ORION (GEX Probability Models) for hybrid probability (60% ML + 40% distance)

**Market Structure Panel** (9 signals comparing today vs prior day):

| Signal | What It Shows | Trading Use |
|--------|--------------|-------------|
| **Flip Point** | RISING/FALLING/STABLE | Dealer repositioning - where support/resistance moved |
| **±1 Std Bounds** | SHIFTED_UP/DOWN/STABLE/MIXED | Options market's price expectations |
| **Range Width** | WIDENING/NARROWING/STABLE | Volatility expansion/contraction |
| **Gamma Walls** | PUT CLOSER/CALL CLOSER/BALANCED | Asymmetric risk profile |
| **Intraday Vol** | EXPANDING/CONTRACTING/STABLE | Real-time vol vs open |
| **VIX Regime** | LOW/NORMAL/ELEVATED/HIGH/EXTREME | Sizing and strategy context |
| **Gamma Regime** | MEAN_REVERSION/MOMENTUM | IC safety vs breakout reliability |
| **GEX Momentum** | STRONG_BULLISH/FADING/etc | Dealer conviction direction |
| **Wall Break Risk** | HIGH/ELEVATED/MODERATE/LOW | Imminent breakout warning |

**Combined Signal Logic Matrix**:

| Flip Point | Bounds | Width | Gamma Regime | Combined Signal |
|------------|--------|-------|--------------|-----------------|
| RISING | SHIFTED_UP | WIDENING | NEGATIVE | BULLISH_BREAKOUT (HIGH confidence) |
| RISING | SHIFTED_UP | * | POSITIVE | BULLISH_GRIND (MEDIUM confidence) |
| FALLING | SHIFTED_DOWN | WIDENING | NEGATIVE | BEARISH_BREAKOUT (HIGH confidence) |
| FALLING | SHIFTED_DOWN | * | POSITIVE | BEARISH_GRIND (MEDIUM confidence) |
| STABLE | STABLE | NARROWING | POSITIVE | SELL_PREMIUM (HIGH confidence) |
| STABLE | STABLE | NARROWING | NEGATIVE | SELL_PREMIUM_CAUTION (LOW confidence) |
| * | * | WIDENING | STABLE | VOL_EXPANSION_NO_DIRECTION |
| RISING | SHIFTED_DOWN | * | * | DIVERGENCE_BULLISH_DEALERS |
| FALLING | SHIFTED_UP | * | * | DIVERGENCE_BEARISH_DEALERS |

**Wall Break Risk Logic**:
```
HIGH RISK = Distance <0.3% AND (gamma COLLAPSING at wall OR NEGATIVE regime)
ELEVATED = Distance <0.3% OR (Distance <0.7% AND COLLAPSING)
MODERATE = Distance 0.3-0.7%
LOW = Distance >0.7%
```

When wall break is HIGH, it overrides other signals with `CALL_WALL_BREAK_IMMINENT` or `PUT_WALL_BREAK_IMMINENT`.

**VIX Regime Thresholds**:
- LOW: VIX < 15 (thin premiums, favor directional)
- NORMAL: 15-22 (ideal for Iron Condors)
- ELEVATED: 22-28 (widen IC strikes)
- HIGH: 28-35 (reduce size 50%)
- EXTREME: >35 (skip ICs, small directional only)

**Key Thresholds**:
- Flip point change: ±$2 or ±0.3% = significant
- Bounds shift: ±$0.50 = significant
- Width change: ±5% = significant
- Intraday EM change: ±3% = significant

**Actionable Trade Recommendations** (`/api/argus/trade-action`):
Instead of generic "BULLISH" signals, provides executable trades:
- Exact trade structure: "SELL SPY 588/586 PUT SPREAD @ $0.45 credit"
- Position sizing based on account size and risk tolerance
- THE WHY: Reasoning for each decision (gamma regime, order flow, VIX)
- Entry triggers and exit rules (profit target, stop loss, time stop)
- Four scenarios: Iron Condor, Put/Call Credit Spread, Debit Spread

**Signal Tracking** (`/api/argus/signals/*`):
Track hypothetical performance of ARGUS recommendations:
- Log signals manually or auto-log all non-WAIT signals
- Outcome detection at market close (WIN/LOSS based on strike placement)
- Performance stats: win rate, total P&L, avg win/loss, by action type
- Recent signals list with status indicators

**Files**:
- Backend: `backend/api/routes/argus_routes.py` (~5.5K lines)
- Frontend: `frontend/src/app/argus/page.tsx` (~4.8K lines)
- Engine: `core/argus_engine.py` (~1.7K lines)

**API Endpoints**:
```
GET  /api/argus/snapshot           # Full gamma snapshot with market structure
GET  /api/argus/history            # Historical gamma for sparklines
GET  /api/argus/danger-zones       # Active danger zone alerts
GET  /api/argus/pattern-matching   # Historical pattern analysis
POST /api/argus/commentary         # Generate AI commentary
GET  /api/argus/trade-action       # Actionable trade with strikes, sizing, WHY
POST /api/argus/signals/log        # Log signal for tracking
GET  /api/argus/signals/recent     # Recent signals with outcomes
GET  /api/argus/signals/performance # Win rate, P&L, stats
POST /api/argus/signals/update-outcomes # Update open signal outcomes
```

### Key Dashboard Components
- `SAGEStatusWidget.tsx` - ML Advisor status and bot integration
- `DriftStatusCard.tsx` - Backtest vs Live performance comparison
- `EquityCurveChart.tsx` - Shared equity curve visualization
- `DashboardScanFeed.tsx` - Real-time scan activity feed
- `OracleRecommendationWidget.tsx` - Oracle prediction display
- `BotStatusOverview.tsx` - All bots status (ARES, ATHENA, ICARUS, PEGASUS, TITAN)

---

## API Structure

### Route Naming Convention
All routes are in `backend/api/routes/`. Each file follows the pattern:
- `*_routes.py` - Route handlers
- Router prefix matches the domain (e.g., `/api/gex/`, `/api/ares/`)

### Key API Endpoints

```
# Health & System
GET  /health                    # System health check
GET  /api/system-health         # Comprehensive health (includes Oracle staleness)
GET  /ready                     # Kubernetes readiness probe

# GEX Data
GET  /api/gex/{symbol}          # GEX data for symbol
GET  /api/gex/{symbol}/levels   # Support/resistance levels
GET  /api/gamma/0dte            # 0DTE gamma expiration data

# ARGUS (Real-time 0DTE Gamma)
GET  /api/argus/snapshot        # Full gamma snapshot with market structure (9 signals)
GET  /api/argus/history         # Historical gamma for sparklines
GET  /api/argus/danger-zones    # Active danger zone alerts (BUILDING/COLLAPSING/SPIKE)
GET  /api/argus/pattern-matching # Historical pattern analysis
GET  /api/argus/gamma-flip-history # Regime flip history
POST /api/argus/commentary      # Generate AI commentary
GET  /api/argus/trade-action    # Actionable trade recommendation with strikes, sizing, WHY
POST /api/argus/signals/log     # Log signal for performance tracking
GET  /api/argus/signals/recent  # Recent signals with outcomes
GET  /api/argus/signals/performance # Win rate, total P&L, stats by action type
POST /api/argus/signals/update-outcomes # Update open signal outcomes

# Trading Bots (8 bots, 100+ endpoints total)
GET  /api/ares/status           # ARES bot status
POST /api/ares/analyze          # Analyze IC opportunity
GET  /api/athena/status         # ATHENA bot status
GET  /api/titan/status          # TITAN bot status
GET  /api/titan/positions       # TITAN open positions
GET  /api/titan/equity-curve    # TITAN equity curve
GET  /api/pegasus/status        # PEGASUS bot status
GET  /api/icarus/status         # ICARUS bot status
GET  /api/trader/performance    # Unified trading performance

# Oracle (ML Advisory)
GET  /api/oracle/health         # Oracle health with staleness metrics
GET  /api/oracle/status         # Detailed Oracle status
POST /api/oracle/strategy-recommendation  # IC vs Directional recommendation
GET  /api/oracle/vix-regimes    # VIX regime definitions

# SAGE (ML Predictions)
GET  /api/ml/sage/status        # SAGE model status
POST /api/ml/sage/predict       # Run prediction
POST /api/ml/sage/train         # Trigger training
GET  /api/ml/sage/feature-importance  # Feature importance rankings

# AI & GEXIS (35+ endpoints)
POST /api/ai/analyze            # AI market analysis
GET  /api/ai/gexis/info         # GEXIS system info
GET  /api/ai/gexis/welcome      # Welcome message
GET  /api/ai/gexis/daily-briefing  # Market briefing
POST /api/ai/gexis/command      # Execute slash commands
POST /api/ai/gexis/agentic-chat # Full agentic chat with tools
POST /api/ai/gexis/agentic-chat/stream  # Streaming responses
POST /api/ai/gexis/extended-thinking    # Deep analysis mode
GET  /api/ai/gexis/learning-memory/stats  # Prediction accuracy

# Transparency & Logging
GET  /api/logs/summary          # Summary of all 22+ log tables
GET  /api/logs/bot-decisions    # All bot trading decisions
GET  /api/data-transparency/summary  # Hidden data categories
GET  /api/data-transparency/regime-signals  # All 80+ regime signals
```

---

## Database Schema

### Core Trading Tables
- `autonomous_open_positions` - Active positions
- `autonomous_closed_trades` - Completed trades
- `autonomous_trade_log` - Trade history
- `unified_trades` - Unified trade records
- `trading_decisions` - Bot trading decisions with full audit trail

### Bot-Specific Tables
- `titan_positions` - TITAN open positions
- `titan_closed_trades` - TITAN completed trades
- `titan_equity_snapshots` - TITAN equity curve data
- `titan_scan_activity` - TITAN scan logs

### ML & Oracle Tables
- `oracle_predictions` - Oracle prediction history
- `ml_decision_logs` - SAGE decision audit trail
- `sage_training_history` - SAGE model training records
- `ml_model_metadata` - Model versioning and metrics

### Analytics Tables
- `gex_history` - Historical GEX data
- `gamma_history` - Gamma exposure history
- `regime_classifications` - Market regime data (80+ columns)
- `backtest_results` - Backtest outcomes
- `drift_analysis` - Backtest vs live drift metrics

### Logging Tables (22+ tables)
- `ai_analysis_history` - AI analysis with confidence scores
- `psychology_analysis` - Psychology trap detection logs
- `wheel_activity_log` - SPX Wheel activity
- `gex_change_log` - GEX change events
- `ares_ml_outcomes` - ARES ML prediction outcomes

### Configuration Tables
- `autonomous_config` - Bot configuration
- `alerts` - Alert definitions
- `push_subscriptions` - Push notification subscribers

---

## Coding Conventions

### Python Style
- Use type hints for function signatures
- Docstrings for public functions
- Import organization: stdlib, third-party, local
- Use `try/except` with fallbacks for optional dependencies
- Log with `logging` module, not print statements

### Error Handling Pattern
```python
# Common pattern - graceful fallback for imports
TradingVolatilityAPI = None
try:
    from core_classes_and_engines import TradingVolatilityAPI
    print("  Backend: TradingVolatilityAPI loaded")
except ImportError as e:
    print(f"  Backend: TradingVolatilityAPI import failed: {e}")
```

### API Route Pattern
```python
from fastapi import APIRouter, HTTPException
router = APIRouter(tags=["Domain"])

@router.get("/api/domain/endpoint")
async def endpoint_name():
    """Docstring describing the endpoint"""
    try:
        # Implementation
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Frontend Component Pattern
```tsx
'use client'

import { useState, useEffect } from 'react'
import useSWR from 'swr'

export default function ComponentName() {
  const { data, error, isLoading } = useSWR('/api/endpoint', fetcher)

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState error={error} />

  return (
    <div className="tailwind-classes">
      {/* Component content */}
    </div>
  )
}
```

---

## Testing Conventions

### Pytest Configuration
```ini
# pytest.ini
testpaths = tests backend/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### Test Fixtures (from conftest.py)
```python
@pytest.fixture
def mock_spot_price():
    return 585.50

@pytest.fixture
def mock_vix():
    return 15.5

@pytest.fixture
def mock_market_data(mock_spot_price, mock_vix):
    return {
        "symbol": "SPY",
        "spot_price": mock_spot_price,
        "vix": mock_vix,
        # ...
    }
```

### Running Specific Tests
```bash
# Run tests matching pattern
pytest -k "test_gex" -v

# Run with output
pytest -v -s tests/test_gex_calculator.py

# Skip slow tests
pytest -m "not slow"
```

---

## Common Tasks

### Adding a New API Route
1. Create `backend/api/routes/new_feature_routes.py`
2. Define router: `router = APIRouter(tags=["NewFeature"])`
3. Import in `backend/main.py`
4. Include router: `app.include_router(new_feature_routes.router)`

### Adding a New Frontend Page
1. Create directory: `frontend/src/app/new-page/`
2. Add `page.tsx` with 'use client' directive
3. Import components from `@/components/`
4. Use SWR for data fetching from API

### Running Backtests
```bash
# Run specific backtest
python scripts/run_spx_backtest.sh

# Run all backtests
python scripts/run_all_backtests.py
```

### Training ML Models
```bash
python scripts/train_gex_probability_models.py
python scripts/train_oracle_model.py
python scripts/train_directional_ml.py
```

---

## Deployment

### Render (Backend)
Configured via `render.yaml`:
- `alphagex-api`: Main FastAPI service
- `alphagex-trader`: Trading bot worker
- `alphagex-collector`: Data collection worker
- `alphagex-backtester`: Backtest worker
- `alphagex-db`: PostgreSQL database

### Vercel (Frontend)
- Auto-deploys from `main` branch
- Environment variable: `NEXT_PUBLIC_API_URL`

### Manual Deploy Commands
```bash
# Backend (Render handles via render.yaml)
git push origin main

# Frontend (Vercel handles automatically)
git push origin main
```

---

## Development Standards

### Production-Ready Implementation
When implementing features, **always deliver production-ready, end-to-end implementations**:

1. **Don't just write scaffolding** - Wire it up to actually run in production
2. **Complete the full loop**: Database schema → Backend logic → API endpoint → Frontend display
3. **If adding data fields**, integrate them into the code that populates them
4. **If adding UI components**, ensure the backend sends the data they need
5. **If adding new analysis systems**, integrate them into the bots that use them

**Example**: If asked to "add ML analysis to scan activity":
- BAD: Add database columns and UI components, but leave bots unchanged
- GOOD: Add columns, update bots to call ML systems, pass data to logger, display in UI

### Trigger Phrases
When the user says any of these, ensure full end-to-end implementation:
- "make it production-ready"
- "implement end-to-end"
- "wire it up"
- "make it actually work"
- "activate it"

### Bot Completeness Requirements
**CRITICAL: Each trading bot is an independent system.** When fixing issues or adding features to ANY bot, treat it as a complete web application that must work end-to-end:

**Each bot (ARES, TITAN, PEGASUS, ATHENA, ICARUS) MUST have:**

1. **Historical Equity Curve** (`/equity-curve`)
   - Query ALL closed trades (no date filter on SQL - filter output only)
   - Cumulative P&L = running sum of all realized_pnl
   - Equity = starting_capital + cumulative_pnl
   - starting_capital from config table (NOT hardcoded)

2. **Intraday Equity Curve** (`/equity-curve/intraday`)
   - Read from `{bot}_equity_snapshots` table
   - Include unrealized P&L from open positions
   - Market open equity = starting_capital + previous_day_cumulative_pnl

3. **Position Management**
   - `close_position()` must set: `close_time = NOW()`, `realized_pnl`
   - `expire_position()` must exist and set same fields
   - All position status changes must update `close_time`

4. **Data Consistency**
   - Same starting_capital lookup in ALL endpoints (config table)
   - Same P&L formula everywhere: `(close_price - entry_price) * contracts * 100`
   - Timezone handling: `::timestamptz AT TIME ZONE 'America/Chicago'`

**When fixing ONE bot, check ALL bots for the same issue.** Don't fix ARES and leave TITAN broken.

**Common Bot Endpoints to Verify:**
| Endpoint | Purpose | Key Checks |
|----------|---------|------------|
| `/status` | Bot health | Config loaded, positions counted |
| `/positions` | Open positions | All fields populated |
| `/equity-curve` | Historical P&L | Cumulative math correct |
| `/equity-curve/intraday` | Today's P&L | Snapshots being saved |
| `/performance` | Statistics | Win rate, total P&L accurate |
| `/logs` | Activity log | Actions being logged |
| `/scan-activity` | Scan history | Scans recorded |

---

## Important Notes for AI Assistants

### When Modifying Code
1. **Always read before editing** - Understand existing patterns first
2. **Maintain fallback patterns** - Optional dependencies should have graceful fallbacks
3. **Follow existing patterns** - Look at similar files for conventions
4. **Test changes** - Run relevant tests before committing
5. **Use Central Time** - All market times are in America/Chicago timezone

### Known Technical Debt
- Bare except clauses (89 instances) - Could be more specific
- Some incomplete function implementations
- Test coverage gaps in AI modules and route handlers
- **PHOENIX/ATLAS lack full API integration**: No dedicated route files
- **Legacy Flask dashboard**: `dashboard/app.py` still exists but unused

### Critical Files (Handle with Care)
- `backend/main.py` - Main application entry point
- `core/autonomous_paper_trader.py` - Core trading logic (PHOENIX)
- `config.py` - System-wide configuration
- `database_adapter.py` - Database connections
- `trading/ares_v2/trader.py` - ARES live trading execution
- `trading/athena_v2/trader.py` - ATHENA live trading execution
- `trading/titan/trader.py` - TITAN trading execution
- `trading/pegasus/trader.py` - PEGASUS trading execution
- `trading/icarus/trader.py` - ICARUS trading execution
- `trading/prometheus/trader.py` - PROMETHEUS box spread synthetic borrowing
- `quant/oracle_advisor.py` - Oracle ML advisory system (sole trade authority)
- `quant/solomon_enhancements.py` - Risk management (replaced circuit_breaker)
- `scheduler/trader_scheduler.py` - Central bot orchestration
- `backend/api/routes/oracle_routes.py` - Oracle API endpoints

### Market Hours (Central Time)
- Market Open: 8:30 AM CT
- Market Close: 3:00 PM CT
- Pre-market: 7:00 AM - 8:30 AM CT
- After-hours: 3:00 PM - 5:00 PM CT

---

*Last Updated: January 30, 2026*
*PROMETHEUS updated to standalone system with IC trading (no longer deploys to ARES/TITAN/PEGASUS)*
