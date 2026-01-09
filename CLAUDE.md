# CLAUDE.md - AlphaGEX AI Assistant Guide

This document provides comprehensive context for AI assistants working with the AlphaGEX codebase.

## Project Overview

**AlphaGEX** is an autonomous options trading platform built around GEX (Gamma Exposure) analysis. It predicts market maker behavior to generate profitable options trading signals.

### Core Value Proposition
- Profitable Monday/Tuesday directional plays
- Iron Condor timing optimization
- Market regime classification (MOVE vs. DO NOTHING)
- Automated trading via ARES, ATHENA, PHOENIX, and ATLAS bots

### Key Metrics
- ~183 Python files across multiple modules
- 38+ API route modules with 100+ endpoints
- 63 database tables for persistence
- ~120,000 lines of Python code

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
│  Python 3.11 + PostgreSQL + 38 Route Modules                    │
│  Deployed: Render                                                │
├─────────────────────────────────────────────────────────────────┤
│  BACKGROUND WORKERS (Render)                                     │
│  - alphagex-trader: ARES, ATHENA, PHOENIX, ATLAS bots           │
│  - alphagex-collector: Automated data collection                 │
│  - alphagex-backtester: Long-running backtest jobs              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AlphaGEX/
├── backend/                    # FastAPI backend API
│   ├── main.py                 # Entry point (74K lines)
│   ├── api/
│   │   ├── routes/             # 38 route modules
│   │   │   ├── core_routes.py      # Health, time endpoints
│   │   │   ├── gex_routes.py       # GEX data endpoints
│   │   │   ├── gamma_routes.py     # Gamma analysis
│   │   │   ├── ares_routes.py      # Iron Condor bot
│   │   │   ├── athena_routes.py    # Directional spreads bot
│   │   │   ├── trader_routes.py    # Trading operations
│   │   │   └── ...                 # 32 more route files
│   │   ├── dependencies.py     # Shared API dependencies
│   │   └── utils.py            # API utilities
│   ├── services/               # Background services
│   ├── tests/                  # Backend unit tests
│   └── requirements.txt        # Backend dependencies
│
├── frontend/                   # Next.js React frontend
│   ├── src/
│   │   ├── app/                # Next.js App Router (40+ pages)
│   │   │   ├── page.tsx            # Dashboard home
│   │   │   ├── ares/               # ARES Iron Condor page
│   │   │   ├── athena/             # ATHENA spreads page
│   │   │   ├── oracle/             # Oracle predictions
│   │   │   ├── argus/              # Real-time gamma viz
│   │   │   ├── gex/                # GEX analysis
│   │   │   └── ...                 # 35+ more pages
│   │   ├── components/         # Reusable React components
│   │   ├── hooks/              # Custom React hooks
│   │   └── lib/
│   │       └── api.ts          # API client with types
│   ├── __tests__/              # Frontend unit tests (Jest)
│   ├── package.json            # npm dependencies
│   └── tailwind.config.ts      # Tailwind CSS config
│
├── core/                       # Core trading logic (670K lines total)
│   ├── autonomous_paper_trader.py  # Main trader (125K)
│   ├── intelligence_and_strategies.py  # AI strategies (142K)
│   ├── psychology_trap_detector.py    # Psychology system (109K)
│   ├── market_regime_classifier.py    # Regime detection (46K)
│   ├── probability_calculator.py      # Probability engine (30K)
│   └── ...
│
├── trading/                    # Trading execution
│   ├── ares_iron_condor.py     # ARES bot (181K)
│   ├── athena_directional_spreads.py  # ATHENA bot (187K)
│   ├── wheel_strategy.py       # SPX Wheel strategy
│   ├── risk_management.py      # Risk controls
│   ├── circuit_breaker.py      # Trading circuit breaker
│   └── mixins/                 # Trading behavior mixins
│
├── ai/                         # AI/ML integration
│   ├── gexis_personality.py    # GEXIS AI personality
│   ├── langchain_*.py          # LangChain integrations
│   ├── ai_strategy_optimizer.py    # Strategy optimization
│   └── ai_trade_advisor.py     # Trade recommendations
│
├── quant/                      # Quantitative analysis
│   ├── oracle_advisor.py       # Oracle predictions (132K)
│   ├── gex_probability_models.py   # GEX ML models
│   ├── monte_carlo_kelly.py    # Kelly criterion
│   └── ml_regime_classifier.py # ML regime detection
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
├── scripts/                    # Utility scripts (130+ files)
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
- **Framework**: FastAPI 0.104+
- **Python**: 3.11
- **Database**: PostgreSQL (via psycopg2)
- **AI/ML**: LangChain, Anthropic Claude, scikit-learn, XGBoost
- **Data Sources**: Tradier (primary), Polygon.io (fallback), TradingVolatility API

### Frontend
- **Framework**: Next.js 14 (App Router)
- **React**: 18.2
- **Language**: TypeScript 5.3
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

### ARES - Aggressive Iron Condor
- **Schedule**: 8:30 AM - 3:30 PM CT, every 5 min, once daily
- **Strategy**: Iron Condor with dynamic strike selection
- **Files**: `trading/ares_iron_condor.py`, `backend/api/routes/ares_routes.py`

### ATHENA - Directional Spreads
- **Schedule**: 8:35 AM - 2:30 PM CT, every 5 min, max 5/day
- **Strategy**: GEX-based directional spreads
- **Files**: `trading/athena_directional_spreads.py`, `backend/api/routes/athena_routes.py`

### PHOENIX - 0DTE Options
- **Schedule**: Hourly during market hours
- **Strategy**: 0DTE SPY/SPX options
- **Files**: Various in `trading/` and `backtest/`

### ATLAS - SPX Wheel
- **Schedule**: Daily at 9:05 AM CT
- **Strategy**: SPX Wheel premium collection
- **Files**: `trading/spx_wheel_system.py`, `trading/wheel_strategy.py`

---

## API Structure

### Route Naming Convention
All routes are in `backend/api/routes/`. Each file follows the pattern:
- `*_routes.py` - Route handlers
- Router prefix matches the domain (e.g., `/api/gex/`, `/api/ares/`)

### Key API Endpoints

```
# Health
GET  /health                    # System health check
GET  /api/system-health         # Comprehensive health

# GEX Data
GET  /api/gex/{symbol}          # GEX data for symbol
GET  /api/gex/{symbol}/levels   # Support/resistance levels

# Trading Bots
GET  /api/ares/status           # ARES bot status
POST /api/ares/analyze          # Analyze IC opportunity
GET  /api/athena/status         # ATHENA bot status
GET  /api/trader/performance    # Trading performance

# AI
POST /api/ai/analyze            # AI market analysis
GET  /api/gexis/chat            # GEXIS AI chat

# Oracle (ML Predictions)
GET  /api/oracle/prediction     # Direction prediction
```

---

## Database Schema

### Core Trading Tables
- `autonomous_open_positions` - Active positions
- `autonomous_closed_trades` - Completed trades
- `autonomous_trade_log` - Trade history
- `unified_trades` - Unified trade records

### Analytics Tables
- `gex_history` - Historical GEX data
- `gamma_history` - Gamma exposure history
- `regime_classifications` - Market regime data
- `backtest_results` - Backtest outcomes

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

### Critical Files (Handle with Care)
- `backend/main.py` - Main application entry point
- `core/autonomous_paper_trader.py` - Core trading logic
- `config.py` - System-wide configuration
- `database_adapter.py` - Database connections
- `trading/ares_iron_condor.py` - Live trading execution
- `trading/athena_directional_spreads.py` - Live trading execution

### Market Hours (Central Time)
- Market Open: 8:30 AM CT
- Market Close: 3:00 PM CT
- Pre-market: 7:00 AM - 8:30 AM CT
- After-hours: 3:00 PM - 5:00 PM CT

---

*Last Updated: December 2024*
*Generated from codebase analysis*
