# CLAUDE.md - AlphaGEX AI Assistant Guide

## Project Overview

**AlphaGEX** is an autonomous options trading platform built around GEX (Gamma Exposure) analysis. It predicts market maker behavior to generate profitable options trading signals.

### Core Value Proposition
- Profitable Monday/Tuesday directional plays
- Iron Condor timing optimization
- Market regime classification (MOVE vs. DO NOTHING)
- Automated trading via 20+ specialized bots across options, futures, and crypto
- Bot naming convention: Greek mythology (internal/code) → Biblical (display/UI)

### Naming Convention
All systems use a dual-naming scheme defined in `backend/api/bot_names.py`:
- **Internal names** (Greek mythology): Used in code, API endpoints, database tables, file/directory names
- **Display names** (Biblical): Used in UI, logs, notifications, user-facing text
- Example: ARES (internal) → FORTRESS (display), ORACLE (internal) → PROPHET (display)

### Key Metrics
- ~900 Python files across multiple modules
- 69 API route modules with 800+ endpoints
- 285+ database tables for persistence
- ~400,000+ lines of Python code

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
│  Python 3.11 + PostgreSQL + 69 Route Modules                    │
│  Deployed: Render                                                │
├─────────────────────────────────────────────────────────────────┤
│  BACKGROUND WORKERS (Render)                                     │
│  - alphagex-trader: All 20+ trading bots                        │
│  - alphagex-collector: Automated data collection                 │
│  - alphagex-backtester: Long-running backtest jobs              │
├─────────────────────────────────────────────────────────────────┤
│  ML ADVISORY LAYER                                               │
│  - WISDOM (SAGE): XGBoost ML probability predictions            │
│  - PROPHET (Oracle): Primary decision maker for all bots        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AlphaGEX/
├── backend/                    # FastAPI backend API
│   ├── main.py                 # Entry point (~2.7K lines)
│   ├── api/
│   │   ├── bot_names.py        # Greek→Biblical name mapping (master registry)
│   │   ├── routes/             # 69 route modules
│   │   ├── dependencies.py     # Shared API dependencies
│   │   └── utils.py            # API utilities
│   ├── services/               # Background services
│   ├── tests/                  # Backend unit tests
│   └── requirements.txt        # Backend dependencies
├── frontend/                   # Next.js React frontend
│   ├── src/
│   │   ├── app/                # Next.js App Router (70+ pages)
│   │   ├── components/         # Reusable React components
│   │   ├── hooks/              # Custom React hooks
│   │   └── lib/api.ts          # API client with types
│   ├── __tests__/              # Frontend unit tests (Jest)
│   └── package.json            # npm dependencies
├── core/                       # Core trading logic
│   ├── autonomous_paper_trader.py  # Main trader (LAZARUS/PHOENIX)
│   ├── watchtower_engine.py        # WATCHTOWER (ARGUS) gamma engine
│   ├── shared_gamma_engine.py      # Shared gamma calculations
│   └── discernment_ml_engine.py    # DISCERNMENT (APOLLO) ML scanner
├── trading/                    # Trading execution (23 directories)
│   ├── fortress_v2/            # FORTRESS (ARES) Iron Condor bot
│   ├── solomon_v2/             # SOLOMON (ATHENA) Directional Spreads
│   ├── samson/                 # SAMSON (TITAN) Aggressive SPX IC
│   ├── anchor/                 # ANCHOR (PEGASUS) SPX Weekly IC
│   ├── gideon/                 # GIDEON (ICARUS) Aggressive Directional
│   ├── jubilee/                # JUBILEE (PROMETHEUS) Box Spread + IC
│   ├── valor/                  # VALOR (HERACLES) MES Futures
│   ├── faith/                  # FAITH - 2DTE Paper IC
│   ├── grace/                  # GRACE - 1DTE Paper IC
│   ├── agape_spot/             # AGAPE-SPOT 24/7 Crypto Spot
│   ├── agape_*_perp/           # AGAPE Perpetual Contracts (5 bots)
│   └── spx_wheel_system.py     # SPX Wheel (CORNERSTONE/ATLAS)
├── ai/                         # AI/ML integration (COUNSELOR/GEXIS)
│   └── counselor_*.py          # COUNSELOR AI assistant (11+ modules)
├── quant/                      # Quantitative analysis
│   ├── prophet_advisor.py      # PROPHET (Oracle) ML predictions
│   ├── gex_probability_models.py   # STARS (ORION) GEX ML models
│   └── proverbs_feedback_loop.py   # PROVERBS feedback system
├── data/                       # Data providers (Tradier, Polygon)
├── gamma/                      # Gamma-specific modules
├── backtest/                   # Backtesting engines
├── monitoring/                 # System monitoring
├── scheduler/trader_scheduler.py   # Central bot orchestration
├── scripts/                    # Utility scripts (236+ files)
├── tests/                      # Main test suite (~115 files)
├── config.py                   # Central configuration
├── database_adapter.py         # PostgreSQL adapter
├── render.yaml                 # Render deployment config
└── pytest.ini                  # Pytest configuration
```

---

## Tech Stack

### Backend
- **Framework**: FastAPI 0.115+, Python 3.11
- **Database**: PostgreSQL (via psycopg2)
- **AI/ML**: Anthropic Claude (direct SDK), scikit-learn, XGBoost 2.x
- **Data Sources**: Tradier (primary), Polygon.io (fallback), TradingVolatility API
- **Futures Broker**: Tastytrade (for VALOR)
- **Crypto Exchange**: Coinbase Advanced Trade (for AGAPE)

### Frontend
- **Framework**: Next.js 14.2 (App Router), React 18.2, TypeScript 5.7
- **Styling**: Tailwind CSS 3.4, Radix UI primitives
- **Data Fetching**: SWR
- **Charts**: Recharts, Plotly.js, Lightweight Charts

### Infrastructure
- **Backend**: Render (web service + 3 workers)
- **Frontend**: Vercel (auto-deploy from main)
- **Database**: Render PostgreSQL

---

## Environment Variables

### Required
```bash
DATABASE_URL=postgresql://user:password@host:5432/alphagex
TRADING_VOLATILITY_API_KEY=your_key   # OR TV_USERNAME=your_username
TRADIER_API_KEY=your_production_key
TRADIER_ACCOUNT_ID=your_account_id
TRADIER_SANDBOX_API_KEY=your_sandbox_key
TRADIER_SANDBOX_ACCOUNT_ID=your_sandbox_account
```

### Optional
```bash
POLYGON_API_KEY=your_key              # Fallback data source
ANTHROPIC_API_KEY=your_key            # AI features
TASTYTRADE_USERNAME=your_username     # VALOR futures
TASTYTRADE_PASSWORD=your_password
ORAT_DATABASE_URL=postgresql://...    # CHRONICLES backtester
CORS_ORIGINS=https://your-frontend.vercel.app
```

---

## Development Workflows

### Starting Services
```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000  # API docs at /docs

# Frontend
cd frontend && npm install && npm run dev  # http://localhost:3000
```

### Running Tests
```bash
pytest -v                                    # All backend tests
pytest --cov=core --cov=trading --cov-report=html  # With coverage
pytest -k "test_gex" -v                      # Pattern match
cd frontend && npm test                      # Frontend tests
```

### Running Backtests
**IMPORTANT**: Always pipe through `| tee` — Render's web shell has no scrollback.
```bash
python backtest/run_ic_matrix.py 2>&1 | tee /tmp/ic_matrix_results.txt
```

### Adding a New API Route
1. Create `backend/api/routes/new_feature_routes.py`
2. Define router: `router = APIRouter(tags=["NewFeature"])`
3. Import in `backend/main.py`
4. Include router: `app.include_router(new_feature_routes.router)`

### Adding a New Frontend Page
1. Create `frontend/src/app/new-page/page.tsx` with `'use client'`
2. Use SWR for data fetching, Tailwind for styling

---

## Coding Conventions

### Python Style
```python
# Graceful fallback for imports
TradingVolatilityAPI = None
try:
    from core_classes_and_engines import TradingVolatilityAPI
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
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Frontend Component Pattern
```tsx
'use client'
import useSWR from 'swr'

export default function ComponentName() {
  const { data, error, isLoading } = useSWR('/api/endpoint', fetcher)
  if (isLoading) return <LoadingState />
  if (error) return <ErrorState error={error} />
  return <div className="tailwind-classes">{/* content */}</div>
}
```

### Testing
```bash
pytest -k "test_gex" -v        # Pattern match
pytest -v -s tests/test_gex_calculator.py  # With output
pytest -m "not slow"           # Skip slow tests
```

---

## Deployment

### Render (Backend)
Configured via `render.yaml`:
- `alphagex-api`: Main FastAPI service
- `alphagex-trader`: All 20+ trading bots
- `alphagex-collector`: Data collection
- `alphagex-backtester`: Backtest worker
- `alphagex-db`: PostgreSQL (285+ tables)

### Vercel (Frontend)
Auto-deploys from `main` branch. Env var: `NEXT_PUBLIC_API_URL`.

---

## Important Notes for AI Assistants

### When Modifying Code
1. **Always read before editing** - Understand existing patterns first
2. **Maintain fallback patterns** - Optional dependencies should have graceful fallbacks
3. **Follow existing patterns** - Look at similar files for conventions
4. **Test changes** - Run relevant tests before committing
5. **Use Central Time** - All market times are in America/Chicago timezone

### Branch Merge Policy (added April 2026)
Once a feature branch is verified working, **merge to `main` proactively without waiting for per-merge approval.** Render auto-deploys `main`, so the merge IS the deploy. Don't sit on a working branch waiting for a green-light when the user has already authorized the work.

**Still pause before (always ask):**
- Force pushes (`git push --force` to any shared branch)
- Branch deletion or `git reset --hard` on shared branches
- Schema migrations on production tables — show the migration plan first
- Changes to credentials, API keys, or billing-relevant env vars
- Any modification under `ironforge/` (intentionally separate per project scope)
- Anything that disables a kill switch, paper-only lock, or risk control

The "do not wait" default applies to feature merges that have passed verification. It does not extend to destructive or production-altering operations — those still require explicit per-action confirmation.

### Critical Files (Handle with Care)
- `backend/main.py` - Application entry point (~2.7K lines)
- `backend/api/bot_names.py` - Greek→Biblical name mapping (master registry)
- `config.py` - System-wide configuration
- `database_adapter.py` - Database connections
- `quant/prophet_advisor.py` - PROPHET ML advisory (sole trade authority)
- `scheduler/trader_scheduler.py` - Central bot orchestration
- All `trading/*/trader.py` - Live trading execution

### Market Hours (Central Time)
- Pre-market: 7:00 AM - 8:30 AM CT
- Market Open: 8:30 AM CT
- Market Close: 3:00 PM CT
- After-hours: 3:00 PM - 5:00 PM CT

### Known Technical Debt
- Bare except clauses in some modules
- Test coverage gaps in AI modules and route handlers
- LAZARUS (PHOENIX) lacks dedicated API routes
- Legacy Flask dashboard `dashboard/app.py` still exists but unused

---

## Detailed Documentation (in `.claude/rules/`)

Domain-specific rules are loaded automatically based on context:
- `bot-registry.md` - All 20+ bot descriptions, ML systems, removed legacy systems
- `bot-development.md` - Bot completeness requirements, production-ready standards
- `common-mistakes.md` - 26 categories of real production bugs (90+ rules)
- `dashboard-features.md` - WATCHTOWER signals, 0DTE tracker, dashboard components
- `api-and-database.md` - 800+ API endpoints, 285+ database tables
- `agape-spot.md` - AGAPE-SPOT crypto system, Feb 2026 audit findings

## Custom Agents (in `.claude/agents/`)
- `bot-reviewer.md` - Audit all bots for consistency and completeness
- `backtest-analyzer.md` - Run and analyze backtests with proper output capture
- `cross-bot-fixer.md` - Apply the same fix across all 20+ bots systematically

## External SDK References (read-only, sibling clones)

These are upstream broker/exchange SDKs cloned alongside AlphaGEX. Read them when debugging bots that depend on them — method signatures, parameter names, and response shapes live here, not in the AlphaGEX repo.

- **Tastytrade SDK**: `/home/user/tastytrade/` — used by VALOR (HERACLES) MES futures via the `tastytrade` package. Key modules: `account.py`, `order.py`, `market_data.py`, `streamer.py` (DXLinkStreamer).
- **Coinbase Advanced Trade SDK**: `/home/user/coinbase-advanced-py/` — used by AGAPE-SPOT and 5 perp bots via `coinbase-advanced-py`. Key modules: `rest/`, `websocket/`, `jwt_generator.py`.
- **Polygon Python client**: `/home/user/polygon-client-python/` — reference only (AlphaGEX uses raw HTTP in `data/polygon_data_fetcher.py`, not this SDK). Note: upstream package directory is `massive/` (rest + websocket), not `polygon/`.
- **Browser-use**: `/home/user/browser-use/` — Python framework for AI-driven browser automation (clicks, forms, screenshots). Not used by AlphaGEX today; cloned as reference for future projects (e.g., dashboard E2E testing, scraping data sources without a public API).

Tradier and TradingVolatility have no quality public SDK — `data/tradier_data_fetcher.py` is the source of truth for those.

---

*Last Updated: April 27, 2026*
