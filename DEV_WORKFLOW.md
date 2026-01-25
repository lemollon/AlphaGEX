# AlphaGEX Development Workflow Guide

This document defines expectations for code quality, testing, debugging, and production readiness. Reference this when developing features or fixing bugs.

---

## THE GOLDEN RULE: NO SCAFFOLDING

**Every implementation must be complete, wired up, and production-ready.**

This is the most important principle in this codebase:

### What "Production-Ready" Means

| WRONG (Scaffolding) | RIGHT (Production-Ready) |
|---------------------|--------------------------|
| Add database columns but leave them empty | Add columns AND update code that populates them |
| Create API endpoint that returns mock data | Create endpoint that queries real database |
| Build UI component with placeholder text | Build component that fetches and displays real data |
| Write function signature with `pass` or `TODO` | Write complete function with working logic |
| Add config option that isn't read anywhere | Add config AND wire it into the system |
| Create table without any code that uses it | Create table AND the insert/select logic |

### The Complete Loop

Every feature MUST complete this entire loop:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. DATABASE                                                     │
│     - Schema exists                                              │
│     - Migrations applied                                         │
│     - Indexes created                                            │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. DATA POPULATION                                              │
│     - Code writes to the table                                   │
│     - Scheduler/trigger runs the code                            │
│     - Data actually appears in production                        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. BACKEND API                                                  │
│     - Endpoint reads from database                               │
│     - Returns properly formatted response                        │
│     - Handles errors gracefully                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. FRONTEND                                                     │
│     - Component calls the API                                    │
│     - Displays data to user                                      │
│     - Handles loading/error states                               │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. VERIFICATION                                                 │
│     - Manually tested end-to-end                                 │
│     - Data flows correctly                                       │
│     - User can see and interact with feature                     │
└─────────────────────────────────────────────────────────────────┘
```

### Examples of Incomplete vs Complete Work

**Example 1: Adding ML Analysis to Scan Activity**

INCOMPLETE (Scaffolding):
```python
# Added to database
ALTER TABLE scan_activity ADD COLUMN ml_score DECIMAL;
ALTER TABLE scan_activity ADD COLUMN ml_recommendation VARCHAR;

# Added to UI
<div>ML Score: {scan.ml_score}</div>

# BUT: Bots never call ML, columns stay NULL forever
```

COMPLETE (Production-Ready):
```python
# 1. Database columns added
ALTER TABLE scan_activity ADD COLUMN ml_score DECIMAL;
ALTER TABLE scan_activity ADD COLUMN ml_recommendation VARCHAR;

# 2. Bot trader.py calls ML during scan
ml_result = await sage_advisor.predict(market_data)
scan_record["ml_score"] = ml_result.probability
scan_record["ml_recommendation"] = ml_result.action

# 3. API endpoint returns the data
return {"scans": [...], "ml_score": row["ml_score"]}

# 4. UI displays it
<div>ML Score: {scan.ml_score ?? 'N/A'}</div>

# 5. Verified: Data appears in production scans
```

**Example 2: Adding a New Configuration Option**

INCOMPLETE:
```python
# config.py
NEW_FEATURE_ENABLED = os.getenv("NEW_FEATURE_ENABLED", "false")

# But nothing reads this variable
```

COMPLETE:
```python
# config.py
NEW_FEATURE_ENABLED = os.getenv("NEW_FEATURE_ENABLED", "false") == "true"

# trader.py
if config.NEW_FEATURE_ENABLED:
    await execute_new_feature_logic()
else:
    await execute_standard_logic()

# .env.example updated
NEW_FEATURE_ENABLED=true  # Enable the new feature

# README updated with what this option does
```

**Example 3: Creating a New API Endpoint**

INCOMPLETE:
```python
@router.get("/api/feature/data")
async def get_data():
    # TODO: Implement this
    return {"data": []}
```

COMPLETE:
```python
@router.get("/api/feature/data")
async def get_data(
    symbol: str = Query(...),
    limit: int = Query(10, ge=1, le=100)
):
    """Get feature data for analysis."""
    try:
        async with get_db_connection() as conn:
            rows = await conn.fetch("""
                SELECT * FROM feature_data
                WHERE symbol = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """, symbol, limit)

        return {
            "status": "success",
            "data": [dict(row) for row in rows],
            "count": len(rows)
        }
    except Exception as e:
        logger.exception(f"Failed to fetch feature data: {e}")
        raise HTTPException(status_code=500, detail="Database error")
```

### Before Marking ANY Task Complete

Ask yourself:

1. **Does data actually flow?** Can I query the database and see real values?
2. **Does the API return real data?** Not mocks, not hardcoded, not empty arrays
3. **Does the UI show the data?** Can I see it in the browser?
4. **Is it scheduled/triggered?** If it needs to run periodically, is that set up?
5. **Did I test it manually?** Not just unit tests - actually use the feature

### Trigger Phrases

When you see these phrases, ensure COMPLETE implementation:
- "make it work"
- "wire it up"
- "production-ready"
- "end-to-end"
- "actually implement"
- "no scaffolding"
- "make it real"

---

## Table of Contents
1. [Feature Development Lifecycle](#feature-development-lifecycle)
2. [Code Quality Standards](#code-quality-standards)
3. [Testing Requirements](#testing-requirements)
4. [Debugging Workflow](#debugging-workflow)
5. [Production Readiness Checklist](#production-readiness-checklist)
6. [Bot-Specific Requirements](#bot-specific-requirements)
7. [API Development Standards](#api-development-standards)
8. [Frontend Development Standards](#frontend-development-standards)
9. [Database Changes](#database-changes)
10. [Deployment Checklist](#deployment-checklist)

---

## Feature Development Lifecycle

### Phase 1: Planning
Before writing code:
- [ ] Understand the full scope (backend, frontend, database, scheduler)
- [ ] Identify all affected files and systems
- [ ] Check for similar existing patterns in the codebase
- [ ] Determine if this affects any trading bots (if yes, see [Bot-Specific Requirements](#bot-specific-requirements))

### Phase 2: Implementation
While coding:
- [ ] Follow existing code patterns in similar files
- [ ] Add type hints to all function signatures
- [ ] Add docstrings to public functions
- [ ] Handle errors gracefully with meaningful messages
- [ ] Log important operations (not print statements)
- [ ] Consider edge cases and failure modes

### Phase 3: Testing
Before committing:
- [ ] Write unit tests for new logic
- [ ] Run existing tests to ensure no regressions
- [ ] Test manually in development environment
- [ ] Test error paths, not just happy paths

### Phase 4: Integration
Before marking complete:
- [ ] Wire up all components end-to-end
- [ ] Verify data flows from database → backend → frontend
- [ ] Test with realistic data, not just mocks
- [ ] Confirm UI displays data correctly

---

## Code Quality Standards

### Python (Backend)

```python
# GOOD: Type hints, docstring, proper error handling
async def calculate_win_probability(
    symbol: str,
    strike: float,
    expiration: str
) -> dict[str, float]:
    """
    Calculate win probability for a given strike.

    Args:
        symbol: Trading symbol (SPY, SPX)
        strike: Option strike price
        expiration: Expiration date (YYYY-MM-DD)

    Returns:
        Dictionary with probability metrics

    Raises:
        ValueError: If symbol is not supported
    """
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")

    try:
        result = await _fetch_probability(symbol, strike, expiration)
        return result
    except Exception as e:
        logger.error(f"Win probability calculation failed: {e}")
        raise

# BAD: No types, no docstring, bare except
def calc_prob(sym, strike, exp):
    try:
        return _fetch_probability(sym, strike, exp)
    except:
        return None
```

### Error Handling Pattern
```python
# For optional dependencies - graceful fallback
OracleAdvisor = None
try:
    from quant.oracle_advisor import OracleAdvisor
    logger.info("OracleAdvisor loaded successfully")
except ImportError as e:
    logger.warning(f"OracleAdvisor not available: {e}")

# For API endpoints - meaningful errors
@router.get("/api/feature/data")
async def get_data():
    try:
        data = await fetch_data()
        if not data:
            raise HTTPException(status_code=404, detail="No data found")
        return {"status": "success", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in get_data")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Logging Standards
```python
import logging
logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed debugging info")      # Development only
logger.info("Normal operation events")       # Startup, config loaded
logger.warning("Something unexpected")       # Recoverable issues
logger.error("Operation failed")             # Failures that need attention
logger.exception("Error with traceback")     # In except blocks
```

### TypeScript (Frontend)

```typescript
// GOOD: Typed, documented, handles loading/error states
interface TradeData {
  id: string;
  symbol: string;
  pnl: number;
  timestamp: string;
}

interface TradeListProps {
  botName: string;
  limit?: number;
}

export function TradeList({ botName, limit = 10 }: TradeListProps) {
  const { data, error, isLoading } = useSWR<TradeData[]>(
    `/api/${botName}/trades?limit=${limit}`,
    fetcher
  );

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorDisplay error={error} />;
  if (!data?.length) return <EmptyState message="No trades found" />;

  return (
    <div className="space-y-2">
      {data.map((trade) => (
        <TradeRow key={trade.id} trade={trade} />
      ))}
    </div>
  );
}

// BAD: No types, no loading/error handling
export function TradeList({ botName }) {
  const { data } = useSWR(`/api/${botName}/trades`);
  return data.map(t => <div>{t.pnl}</div>);
}
```

---

## Testing Requirements

### Unit Tests (Required)

**What to test:**
- Business logic functions
- Data transformations
- Calculation functions
- Edge cases and error conditions

**What NOT to unit test:**
- Simple getters/setters
- Database queries (use integration tests)
- External API calls (mock them)

```python
# tests/test_probability_calculator.py
import pytest
from core.probability_calculator import calculate_probability

class TestProbabilityCalculator:
    def test_returns_probability_between_0_and_1(self):
        result = calculate_probability(strike=590, spot=585, dte=1)
        assert 0 <= result <= 1

    def test_higher_strike_has_lower_call_probability(self):
        low_strike = calculate_probability(strike=580, spot=585, dte=1)
        high_strike = calculate_probability(strike=600, spot=585, dte=1)
        assert low_strike > high_strike

    def test_raises_on_invalid_dte(self):
        with pytest.raises(ValueError, match="DTE must be positive"):
            calculate_probability(strike=590, spot=585, dte=-1)

    def test_handles_at_the_money(self):
        result = calculate_probability(strike=585, spot=585, dte=1)
        assert 0.45 <= result <= 0.55  # Close to 50%
```

### Integration Tests (Required for APIs)

```python
# tests/test_ares_routes.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class TestAresRoutes:
    def test_status_endpoint_returns_200(self):
        response = client.get("/api/ares/status")
        assert response.status_code == 200
        assert "status" in response.json()

    def test_positions_returns_list(self):
        response = client.get("/api/ares/positions")
        assert response.status_code == 200
        assert isinstance(response.json().get("positions"), list)

    def test_invalid_endpoint_returns_404(self):
        response = client.get("/api/ares/nonexistent")
        assert response.status_code == 404
```

### Frontend Tests (Required for Components)

```typescript
// __tests__/components/TradeList.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { TradeList } from '@/components/TradeList';
import { SWRConfig } from 'swr';

const mockTrades = [
  { id: '1', symbol: 'SPY', pnl: 150, timestamp: '2025-01-25T10:00:00Z' },
];

describe('TradeList', () => {
  it('displays trades when data loads', async () => {
    render(
      <SWRConfig value={{ fetcher: () => mockTrades }}>
        <TradeList botName="ares" />
      </SWRConfig>
    );

    await waitFor(() => {
      expect(screen.getByText('$150')).toBeInTheDocument();
    });
  });

  it('shows loading state initially', () => {
    render(<TradeList botName="ares" />);
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
  });

  it('shows error state on failure', async () => {
    render(
      <SWRConfig value={{ fetcher: () => { throw new Error('Failed'); } }}>
        <TradeList botName="ares" />
      </SWRConfig>
    );

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

### Running Tests

```bash
# Backend - all tests
pytest -v

# Backend - specific file
pytest tests/test_gex_calculator.py -v

# Backend - with coverage
pytest --cov=core --cov=trading --cov-report=html

# Frontend - all tests
cd frontend && npm test

# Frontend - with coverage
cd frontend && npm run test:coverage

# Frontend - specific file
cd frontend && npm test -- TradeList.test.tsx
```

---

## Debugging Workflow

### Step 1: Reproduce the Issue
```bash
# Check logs for errors
tail -f logs/alphagex.log | grep -i error

# Check specific bot logs
grep "ARES" logs/alphagex.log | tail -50

# Check database state
psql $DATABASE_URL -c "SELECT * FROM ares_positions WHERE status = 'open';"
```

### Step 2: Isolate the Problem

**Is it backend or frontend?**
```bash
# Test API directly
curl -X GET "http://localhost:8000/api/ares/status" | jq .

# Check if endpoint exists
curl -X GET "http://localhost:8000/docs" | grep "ares"
```

**Is it a data issue?**
```sql
-- Check recent data
SELECT * FROM gex_history
WHERE symbol = 'SPY'
ORDER BY timestamp DESC
LIMIT 10;

-- Check for nulls
SELECT COUNT(*) as total,
       COUNT(flip_point) as with_flip,
       COUNT(call_wall) as with_call_wall
FROM gex_history
WHERE timestamp > NOW() - INTERVAL '1 day';
```

**Is it a timing issue?**
```python
# Add timing logs
import time
start = time.time()
result = expensive_operation()
logger.info(f"Operation took {time.time() - start:.2f}s")
```

### Step 3: Fix and Verify

**Before the fix:**
```bash
# Create a test that fails
pytest tests/test_issue_123.py -v
# Should FAIL
```

**After the fix:**
```bash
# Same test should pass
pytest tests/test_issue_123.py -v
# Should PASS

# Run full test suite to check for regressions
pytest -v
```

### Common Debugging Patterns

**Database connection issues:**
```python
# Add connection retry
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)
```

**API timeout issues:**
```python
# Add timeout and logging
import httpx

async with httpx.AsyncClient(timeout=30.0) as client:
    logger.info(f"Fetching {url}")
    response = await client.get(url)
    logger.info(f"Response: {response.status_code} in {response.elapsed.total_seconds():.2f}s")
```

**Frontend data not updating:**
```typescript
// Force SWR revalidation
const { data, mutate } = useSWR('/api/data');

// After an action
await performAction();
mutate(); // Trigger refetch
```

---

## Production Readiness Checklist

### Before Deploying ANY Feature

#### Code Quality
- [ ] All functions have type hints
- [ ] Public functions have docstrings
- [ ] No hardcoded values (use config/env vars)
- [ ] No `print()` statements (use logging)
- [ ] No bare `except:` clauses
- [ ] Sensitive data not logged

#### Testing
- [ ] Unit tests written and passing
- [ ] Integration tests for new APIs
- [ ] Manual testing completed
- [ ] Edge cases tested
- [ ] Error paths tested

#### Performance
- [ ] Database queries use indexes
- [ ] No N+1 query problems
- [ ] Large data sets paginated
- [ ] Expensive operations cached where appropriate
- [ ] Async operations used for I/O

#### Security
- [ ] Input validation on all endpoints
- [ ] SQL queries use parameterization
- [ ] No secrets in code (use env vars)
- [ ] CORS configured correctly
- [ ] Rate limiting where needed

#### Observability
- [ ] Appropriate logging added
- [ ] Errors include context for debugging
- [ ] Health check endpoints work
- [ ] Metrics/monitoring considered

#### Documentation
- [ ] API endpoints documented (OpenAPI/Swagger)
- [ ] Complex logic has inline comments
- [ ] CLAUDE.md updated if architecture changed
- [ ] README updated if setup changed

---

## Bot-Specific Requirements

### When Modifying ANY Bot (ARES, TITAN, PEGASUS, ATHENA, ICARUS)

**Each bot MUST have these working:**

| Endpoint | Purpose | Verification |
|----------|---------|--------------|
| `/status` | Bot health | Returns config, state, position count |
| `/positions` | Open positions | All fields populated correctly |
| `/closed-trades` | Trade history | Has realized_pnl, close_time |
| `/equity-curve` | Historical P&L | Cumulative math is correct |
| `/equity-curve/intraday` | Today's P&L | Snapshots being recorded |
| `/performance` | Statistics | Win rate, total P&L accurate |
| `/logs` | Activity log | Actions being logged |
| `/scan-activity` | Scan history | Scans recorded with ML data |

### Equity Curve Correctness

```sql
-- Historical equity curve query pattern
-- CRITICAL: No date filter on closed trades - filter OUTPUT only
SELECT
    date_trunc('day', close_time) as date,
    SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl,
    starting_capital + SUM(realized_pnl) OVER (ORDER BY close_time) as equity
FROM {bot}_closed_trades
WHERE close_time IS NOT NULL
ORDER BY close_time;

-- Starting capital from config (NOT hardcoded)
SELECT value::numeric FROM {bot}_config WHERE key = 'starting_capital';
```

### Position Lifecycle

```python
# When closing a position - ALL these fields must be set
async def close_position(position_id: str, close_price: float):
    realized_pnl = (close_price - entry_price) * contracts * 100

    await db.execute("""
        UPDATE {bot}_positions SET
            status = 'closed',
            close_time = NOW(),
            close_price = $1,
            realized_pnl = $2
        WHERE id = $3
    """, close_price, realized_pnl, position_id)

    # Also insert into closed_trades table
    await db.execute("""
        INSERT INTO {bot}_closed_trades (...)
        SELECT ... FROM {bot}_positions WHERE id = $1
    """, position_id)
```

### Cross-Bot Consistency

When fixing an issue in ONE bot, check ALL bots:
```bash
# Search for similar patterns across all bots
grep -r "close_position" trading/*/trader.py
grep -r "equity-curve" backend/api/routes/*_routes.py
```

---

## API Development Standards

### Endpoint Structure

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/feature", tags=["Feature"])

class FeatureResponse(BaseModel):
    status: str
    data: dict
    timestamp: str

@router.get("/data", response_model=FeatureResponse)
async def get_feature_data(
    symbol: str = Query(..., description="Trading symbol"),
    limit: int = Query(10, ge=1, le=100, description="Max results")
):
    """
    Get feature data for a symbol.

    - **symbol**: Trading symbol (SPY, SPX)
    - **limit**: Maximum number of results (1-100)
    """
    try:
        data = await fetch_data(symbol, limit)
        return FeatureResponse(
            status="success",
            data=data,
            timestamp=datetime.utcnow().isoformat()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error fetching data for {symbol}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Response Format Consistency

```python
# Success responses
{"status": "success", "data": {...}}
{"status": "success", "items": [...], "total": 100}

# Error responses
{"detail": "Error message here"}

# Health/Status responses
{"status": "healthy", "version": "1.0.0", "uptime": 3600}
```

### API Testing Checklist

- [ ] Endpoint returns correct status codes (200, 400, 404, 500)
- [ ] Response matches documented schema
- [ ] Query parameters validated
- [ ] Invalid input returns 400 with helpful message
- [ ] Authentication works (if required)
- [ ] Rate limiting works (if required)

---

## Frontend Development Standards

### Component Structure

```typescript
// components/FeatureCard.tsx
'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface FeatureCardProps {
  title: string
  endpoint: string
  refreshInterval?: number
}

export function FeatureCard({
  title,
  endpoint,
  refreshInterval = 30000
}: FeatureCardProps) {
  const { data, error, isLoading } = useSWR(
    endpoint,
    fetcher,
    { refreshInterval }
  )

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-32">
          <Spinner />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="border-red-500">
        <CardContent className="text-red-500">
          Failed to load: {error.message}
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Render data */}
      </CardContent>
    </Card>
  )
}
```

### State Management

```typescript
// Use SWR for server state
const { data, mutate } = useSWR('/api/data')

// Use useState for local UI state only
const [isOpen, setIsOpen] = useState(false)
const [selectedTab, setSelectedTab] = useState('overview')

// DON'T store server data in useState
// BAD:
const [serverData, setServerData] = useState(null)
useEffect(() => {
  fetch('/api/data').then(r => r.json()).then(setServerData)
}, [])

// GOOD:
const { data: serverData } = useSWR('/api/data')
```

### Error Boundaries

```typescript
// app/feature/error.tsx
'use client'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px]">
      <h2 className="text-xl font-bold text-red-500">Something went wrong!</h2>
      <p className="text-gray-500 mt-2">{error.message}</p>
      <button
        onClick={reset}
        className="mt-4 px-4 py-2 bg-blue-500 text-white rounded"
      >
        Try again
      </button>
    </div>
  )
}
```

---

## Database Changes

### Adding New Tables

```sql
-- migrations/001_add_feature_table.sql

-- Create table with proper constraints
CREATE TABLE IF NOT EXISTS feature_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    value DECIMAL(10, 4) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Indexes for common queries
    CONSTRAINT feature_data_symbol_check CHECK (symbol IN ('SPY', 'SPX', 'QQQ'))
);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_feature_data_timestamp
ON feature_data (timestamp DESC);

-- Index for symbol lookups
CREATE INDEX IF NOT EXISTS idx_feature_data_symbol
ON feature_data (symbol, timestamp DESC);

-- Comment for documentation
COMMENT ON TABLE feature_data IS 'Stores feature data for analysis';
```

### Modifying Existing Tables

```sql
-- Always use IF NOT EXISTS / IF EXISTS
ALTER TABLE existing_table
ADD COLUMN IF NOT EXISTS new_column VARCHAR(50);

-- Add with default for existing rows
ALTER TABLE existing_table
ADD COLUMN IF NOT EXISTS new_column BOOLEAN DEFAULT false;

-- Never drop columns in production without migration plan
-- BAD: ALTER TABLE x DROP COLUMN y;
-- GOOD: Mark deprecated, remove after confirming no usage
```

### Query Performance

```sql
-- Check query performance
EXPLAIN ANALYZE
SELECT * FROM large_table
WHERE symbol = 'SPY'
AND timestamp > NOW() - INTERVAL '1 day';

-- Add missing indexes if needed
CREATE INDEX CONCURRENTLY idx_table_symbol_timestamp
ON large_table (symbol, timestamp DESC);
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing locally
- [ ] Code reviewed (or self-reviewed for solo work)
- [ ] Environment variables documented
- [ ] Database migrations ready
- [ ] No debug code left in
- [ ] Logging is appropriate (not too verbose)

### Deployment Steps

```bash
# 1. Create feature branch
git checkout -b feature/new-feature

# 2. Make changes and commit
git add .
git commit -m "feat: Add new feature description"

# 3. Push to remote
git push -u origin feature/new-feature

# 4. Create PR and merge (after review)
# 5. Render auto-deploys from main

# 6. Verify deployment
curl https://alphagex-api.onrender.com/health
```

### Post-Deployment Verification

- [ ] Health endpoints responding
- [ ] New features working in production
- [ ] No errors in logs
- [ ] Performance acceptable
- [ ] Monitoring/alerts configured

### Rollback Plan

```bash
# If issues found, revert immediately
git revert HEAD
git push origin main

# Render will auto-deploy the revert
```

---

## Quick Reference Commands

```bash
# Backend
cd backend && python main.py                    # Run dev server
pytest -v                                       # Run tests
pytest --cov=core --cov-report=html            # Coverage report

# Frontend
cd frontend && npm run dev                      # Run dev server
npm test                                        # Run tests
npm run build                                   # Production build

# Database
psql $DATABASE_URL                              # Connect to DB
psql $DATABASE_URL -c "SELECT * FROM table;"   # Quick query

# Logs
tail -f logs/alphagex.log                       # Watch logs
grep -i error logs/alphagex.log | tail -20     # Recent errors

# Git
git status                                      # Check changes
git diff                                        # See changes
git log --oneline -10                          # Recent commits
```

---

## Final Verification Checklist

**Use this checklist before ANY task is marked complete.**

### Data Layer Verification
```bash
# Can you query real data from the database?
psql $DATABASE_URL -c "SELECT * FROM your_new_table LIMIT 5;"

# Are the columns populated (not all NULL)?
psql $DATABASE_URL -c "SELECT COUNT(*), COUNT(new_column) FROM table;"

# Is data being written? Check recent inserts:
psql $DATABASE_URL -c "SELECT * FROM table WHERE created_at > NOW() - INTERVAL '1 hour';"
```

### API Verification
```bash
# Does the endpoint return real data?
curl http://localhost:8000/api/your/endpoint | jq .

# Does it return the new fields?
curl http://localhost:8000/api/your/endpoint | jq '.data[0].new_field'

# Does error handling work?
curl http://localhost:8000/api/your/endpoint?invalid=param
```

### Frontend Verification
```bash
# Start the frontend
cd frontend && npm run dev

# Open browser to http://localhost:3000/your-page
# Can you SEE the data on screen?
# Does it update when data changes?
# Does it handle loading states?
# Does it handle errors gracefully?
```

### Integration Verification

| Check | Command/Action | Expected Result |
|-------|---------------|-----------------|
| Data exists | Query database | Rows with real values |
| API works | curl endpoint | JSON with data |
| UI displays | Browser check | Data visible on page |
| Updates work | Trigger change | New data appears |
| Errors handled | Break something | Graceful error message |

### The "5 Whys" of Completion

Before marking done, ask:

1. **WHY** would a user care about this feature? → Understand the value
2. **WHERE** does the data come from? → Verify the source is connected
3. **WHEN** does the data get populated? → Verify triggers/schedulers
4. **HOW** does the data reach the UI? → Trace the full path
5. **WHAT** happens if something fails? → Verify error handling

### Signs of Incomplete Work

🚩 **Red Flags - Do NOT mark complete if you see:**

- `# TODO` comments left in code
- `pass` statements in function bodies
- Empty arrays returned from APIs: `return {"data": []}`
- Hardcoded mock data: `return {"value": 42}`
- Database columns that are always NULL
- UI showing "N/A" or placeholder text permanently
- Config options that nothing reads
- Scheduled tasks that aren't in the scheduler
- Tests that are skipped or marked `@pytest.skip`
- "Wire this up later" comments
- Frontend components with `{/* TODO */}`

### Completion Statement

When you complete a task, you should be able to say:

> "I implemented [feature]. Data is being written to [table] by [component/scheduler].
> The API endpoint [/api/path] returns this data. The frontend page [/page] displays it.
> I verified this by [specific test action] and saw [specific result]."

If you can't fill in ALL of those blanks, the task is not complete.

---

## Quick Verification Commands

```bash
# Check if table has data
psql $DATABASE_URL -c "SELECT COUNT(*) FROM table_name;"

# Check if columns are populated
psql $DATABASE_URL -c "SELECT * FROM table_name ORDER BY created_at DESC LIMIT 1;"

# Test API endpoint
curl -s http://localhost:8000/api/endpoint | jq '.'

# Check scheduler has the job
grep -r "schedule" scheduler/trader_scheduler.py | grep "your_function"

# Check frontend calls the API
grep -r "api/endpoint" frontend/src/

# Run the specific test
pytest tests/test_your_feature.py -v

# Full test suite (no skips)
pytest -v --tb=short
```

---

*Last Updated: January 2025*
*Reference this document when developing features or debugging issues*
*THE GOLDEN RULE: NO SCAFFOLDING - Every implementation must be complete and production-ready*
