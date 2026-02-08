# AlphaGEX Test Suite

Comprehensive end-to-end testing scripts for AlphaGEX deployment verification.

## Quick Start

```bash
# Run all tests
python scripts/tests/run_all_tests.py

# Quick health check (fast)
python scripts/tests/quick_health_check.py
```

## Available Test Scripts

### 1. `run_all_tests.py` - Master Test Runner
Runs all test suites in sequence and provides a comprehensive report.

```bash
python scripts/tests/run_all_tests.py
```

### 2. `quick_health_check.py` - Fast Health Check
Quick deployment verification - checks environment, database, and basic connectivity.

```bash
python scripts/tests/quick_health_check.py
```

### 3. `test_database.py` - Database Tests
Tests database connectivity, schema, and data integrity.

```bash
python scripts/tests/test_database.py
```

**Tests included:**
- Database connection
- Schema tables existence
- PYTHIA (probability) schema
- PROPHET schema
- Wheel Strategy schema
- Data integrity checks

### 4. `test_api_endpoints.py` - API Endpoint Tests
Tests all major API endpoints for availability and correct responses.

```bash
python scripts/tests/test_api_endpoints.py
```

**Endpoint groups tested:**
- Health check endpoints
- Market data (GEX, VIX, Psychology)
- PYTHIA (Probability) endpoints
- PROPHET AI endpoints
- PROMETHEUS (ML) endpoints
- Wheel Strategy endpoints
- Trader endpoints
- KRONOS backtest endpoints
- GEXIS chatbot endpoints
- Decision log endpoints
- Optimizer endpoints

### 5. `test_integration.py` - Integration Tests
Tests full system integration and data flows.

```bash
python scripts/tests/test_integration.py
```

**Flows tested:**
- PROPHET prediction flow
- PYTHIA calibration flow
- PROMETHEUS ML flow
- Wheel cycle management
- Trader decision flow
- GEXIS conversation flow
- KRONOS backtest flow
- Database operations

### 6. `test_claude_integration.py` - Claude AI Tests
Tests Claude API connectivity and AI features.

```bash
python scripts/tests/test_claude_integration.py
```

**Tests included:**
- API key configuration
- PROPHET Claude status
- GEXIS commands
- PROPHET analysis with Claude explanation
- GEXIS contextual analysis

## Environment Variables

Set these before running tests:

```bash
# Required
export DATABASE_URL="postgresql://..."
export CLAUDE_API_KEY="your-api-key..."

# Optional (for API tests)
export API_BASE_URL="http://localhost:8000"  # or your deployed URL
```

## Running in Render Shell

1. Open Render shell for your backend service
2. Navigate to project root: `cd /app` (or wherever deployed)
3. Run tests:

```bash
# Quick check first
python scripts/tests/quick_health_check.py

# Full test suite
python scripts/tests/run_all_tests.py
```

## Exit Codes

- `0` - All tests passed
- `1` - Some tests failed
- `2` - Critical failures (multiple systems down)

## Test Output

Each test provides:
- ✓ PASS - Test succeeded
- ✗ FAIL - Test failed
- ⏭️ SKIP - Test skipped (missing dependencies)

Example output:
```
════════════════════════════════════════════════════════════
  DATABASE CONNECTION TEST
════════════════════════════════════════════════════════════
  ✓ [PASS] DATABASE_URL environment variable
  ✓ [PASS] Database availability check
  ✓ [PASS] Database connection
  ✓ [PASS] Simple query execution
  ✓ [PASS] PostgreSQL version
```

## Adding New Tests

1. Create a new test file in `scripts/tests/`
2. Follow the pattern of existing tests
3. Use `print_header()` and `print_result()` helpers
4. Return exit code 0 for success, 1+ for failure
5. Add to `run_all_tests.py` if needed
