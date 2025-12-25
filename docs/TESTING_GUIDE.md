# AlphaGEX Testing Guide

## Overview

This guide covers how to run tests, write new tests, and maintain test coverage for the AlphaGEX trading system.

---

## Quick Start

### Running All Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_position_sizer.py

# Run tests matching a pattern
pytest -k "kelly"
```

### Viewing Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html

# Open in browser
open htmlcov/index.html
```

---

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── test_position_sizer.py         # Position sizing tests (33 tests)
├── test_kelly_criterion.py        # Kelly calculation tests
├── test_market_regime.py          # Regime classification tests
├── test_strategy_selection.py     # Strategy selection tests
├── test_api/
│   ├── test_gex_routes.py         # GEX API endpoint tests
│   ├── test_trader_routes.py      # Trader API endpoint tests
│   └── test_health.py             # Health check tests
├── test_trading/
│   ├── test_trade_executor.py     # Trade execution tests
│   ├── test_position_monitor.py   # Position monitoring tests
│   └── test_circuit_breaker.py    # Circuit breaker tests
└── test_integration/
    ├── test_full_trade_flow.py    # End-to-end trade tests
    └── test_data_pipeline.py      # Data flow tests
```

---

## Writing Tests

### Basic Test Structure

```python
# tests/test_example.py
import pytest
from trading.mixins.position_sizer import PositionSizerMixin

class TestPositionSizer:
    """Tests for position sizing logic."""

    def test_kelly_positive_expectancy(self):
        """Kelly should return positive size for profitable strategy."""
        sizer = PositionSizerMixin()

        result = sizer.calculate_kelly(
            win_rate=0.68,
            avg_win=0.15,
            avg_loss=0.25
        )

        assert result > 0
        assert result < 1  # Should be a fraction

    def test_kelly_negative_expectancy_returns_zero(self):
        """Kelly should return 0 for unprofitable strategy."""
        sizer = PositionSizerMixin()

        result = sizer.calculate_kelly(
            win_rate=0.30,
            avg_win=0.10,
            avg_loss=0.40
        )

        assert result == 0

    @pytest.mark.parametrize("win_rate,avg_win,avg_loss,expected_positive", [
        (0.70, 0.15, 0.20, True),   # Good strategy
        (0.50, 0.30, 0.30, False),  # Break-even
        (0.80, 0.05, 0.50, False),  # High win rate but bad R:R
    ])
    def test_kelly_various_scenarios(self, win_rate, avg_win, avg_loss, expected_positive):
        """Test Kelly across different strategy profiles."""
        sizer = PositionSizerMixin()

        result = sizer.calculate_kelly(win_rate, avg_win, avg_loss)

        if expected_positive:
            assert result > 0
        else:
            assert result <= 0
```

### Using Fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_market_data():
    """Provides mock market data for tests."""
    return {
        "symbol": "SPY",
        "spot_price": 585.42,
        "net_gex": 2450000000,
        "vix": 18.5,
        "iv_rank": 45,
        "call_wall": 590,
        "put_wall": 575,
        "gex_flip_point": 580
    }

@pytest.fixture
def mock_strategy_stats():
    """Provides mock strategy statistics."""
    return {
        "BULL_PUT_SPREAD": {
            "win_rate": 68.0,
            "avg_win_pct": 15.0,
            "avg_loss_pct": 25.0,
            "total_trades": 47,
            "expectancy": 3.42
        }
    }

@pytest.fixture
def mock_tradier_api():
    """Mocks Tradier API for order tests."""
    with patch('trading.mixins.trade_executor.TradierAPI') as mock:
        mock.return_value.place_order.return_value = {
            "order_id": "TEST-123",
            "status": "filled",
            "fill_price": 1.25
        }
        yield mock

@pytest.fixture
def test_db_session():
    """Provides a test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
```

### Testing API Endpoints

```python
# tests/test_api/test_gex_routes.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class TestGEXEndpoints:
    """Tests for GEX API endpoints."""

    def test_get_gex_success(self, mock_market_data):
        """GET /api/gex/{symbol} returns valid GEX data."""
        response = client.get("/api/gex/SPY")

        assert response.status_code == 200
        data = response.json()
        assert "net_gex" in data
        assert "spot_price" in data

    def test_get_gex_invalid_symbol(self):
        """GET /api/gex/{symbol} returns 404 for invalid symbol."""
        response = client.get("/api/gex/INVALID")

        assert response.status_code == 404

    def test_get_regime(self):
        """GET /api/gex/{symbol}/regime returns regime classification."""
        response = client.get("/api/gex/SPY/regime")

        assert response.status_code == 200
        data = response.json()
        assert data["regime"] in ["POSITIVE_GAMMA", "NEGATIVE_GAMMA", "NEUTRAL"]
        assert 0 <= data["confidence"] <= 100
```

### Testing Trading Logic

```python
# tests/test_trading/test_circuit_breaker.py
import pytest
from trading.circuit_breaker import CircuitBreaker

class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_circuit_breaker_trips_on_max_loss(self):
        """Circuit breaker should trip when daily loss exceeds limit."""
        breaker = CircuitBreaker(max_daily_loss=500)

        # Simulate losses
        breaker.record_loss(200)
        assert not breaker.is_tripped()

        breaker.record_loss(350)  # Total: 550
        assert breaker.is_tripped()

    def test_circuit_breaker_resets_daily(self):
        """Circuit breaker should reset at start of new trading day."""
        breaker = CircuitBreaker(max_daily_loss=500)

        breaker.record_loss(600)
        assert breaker.is_tripped()

        breaker.new_trading_day()
        assert not breaker.is_tripped()

    def test_circuit_breaker_blocks_trades(self):
        """When tripped, circuit breaker should block new trades."""
        breaker = CircuitBreaker(max_daily_loss=500)
        breaker.record_loss(600)

        can_trade = breaker.allow_trade()

        assert not can_trade
```

---

## Test Categories

### Unit Tests

Test individual functions and classes in isolation.

```python
# Focus: Single function behavior
def test_calculate_iv_rank():
    result = calculate_iv_rank(
        current_vix=20,
        vix_52w_low=12,
        vix_52w_high=35
    )

    expected = (20 - 12) / (35 - 12) * 100  # 34.78%
    assert abs(result - expected) < 0.01
```

### Integration Tests

Test how components work together.

```python
# Focus: Component interaction
def test_trade_flow_integration(mock_tradier_api, test_db_session):
    """Test complete trade flow from signal to execution."""
    # 1. Generate signal
    signal = generate_trade_signal(market_data)

    # 2. Size position
    size = calculate_position_size(signal, account_balance=50000)

    # 3. Execute trade
    result = execute_trade(signal, size)

    # 4. Verify position recorded
    position = test_db_session.query(Position).filter_by(
        order_id=result.order_id
    ).first()

    assert position is not None
    assert position.status == "OPEN"
```

### End-to-End Tests

Test complete user scenarios.

```python
# Focus: Full user flow
def test_e2e_profitable_trade():
    """Test a complete profitable trade lifecycle."""
    # Setup
    trader = AutonomousPaperTrader()

    # 1. Market opens, data arrives
    trader.on_market_data(bullish_gex_data)

    # 2. Signal generated, trade placed
    trader.evaluate_and_trade()
    assert len(trader.open_positions) == 1

    # 3. Price moves favorably
    trader.on_price_update(favorable_price)

    # 4. Profit target hit, trade closed
    trader.monitor_positions()
    assert len(trader.open_positions) == 0
    assert trader.closed_trades[-1].pnl > 0
```

---

## Mocking External Services

### Mocking APIs

```python
from unittest.mock import patch, Mock

@patch('data.trading_vol_fetcher.requests.get')
def test_fetch_gex_handles_timeout(mock_get):
    """GEX fetch should handle timeout gracefully."""
    mock_get.side_effect = requests.Timeout()

    result = fetch_gex_data("SPY")

    assert result is None or result.get("error")

@patch('data.polygon_fetcher.PolygonClient')
def test_fetch_vix_uses_cache(mock_polygon):
    """VIX fetch should use cached value if fresh."""
    # First call hits API
    mock_polygon.return_value.get_vix.return_value = 18.5
    result1 = fetch_vix()

    # Second call within TTL should use cache
    result2 = fetch_vix()

    assert mock_polygon.return_value.get_vix.call_count == 1
    assert result1 == result2
```

### Mocking Database

```python
@pytest.fixture
def mock_db():
    """Use SQLite in-memory for fast tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    yield Session()

def test_position_saved_to_db(mock_db):
    """Position should be saved after trade execution."""
    position = Position(
        symbol="SPY",
        strategy="BULL_PUT_SPREAD",
        entry_price=1.25,
        contracts=5
    )

    mock_db.add(position)
    mock_db.commit()

    saved = mock_db.query(Position).first()
    assert saved.symbol == "SPY"
```

---

## Coverage Requirements

### Current Coverage

| Module | Coverage | Target |
|--------|----------|--------|
| `trading/mixins/position_sizer.py` | 85% | 90% |
| `trading/mixins/trade_executor.py` | 45% | 80% |
| `trading/mixins/position_manager.py` | 30% | 80% |
| `trading/circuit_breaker.py` | 60% | 90% |
| `trading/risk_management.py` | 40% | 80% |
| `core/market_regime_classifier.py` | 70% | 85% |
| `backend/api/routes/*` | 55% | 75% |

### Coverage Goals

- **Critical paths (trading logic):** 90%+ coverage
- **API endpoints:** 75%+ coverage
- **Utility functions:** 60%+ coverage
- **Overall project:** 70%+ coverage

---

## Running Tests in CI

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run tests
        run: pytest --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: coverage.xml
```

---

## Test Best Practices

### DO

1. **Test behavior, not implementation**
   ```python
   # Good: Tests what the function does
   def test_position_size_respects_max_risk():
       size = calculate_size(account=50000, max_risk_pct=0.02)
       assert size <= 1000  # 2% of 50000
   ```

2. **Use descriptive test names**
   ```python
   # Good: Describes scenario and expected outcome
   def test_kelly_returns_zero_when_expectancy_negative():
   ```

3. **One assertion per test (when possible)**
   ```python
   # Good: Clear what failed
   def test_regime_is_positive():
       result = classify_regime(positive_gex_data)
       assert result.regime == "POSITIVE_GAMMA"
   ```

4. **Use fixtures for setup**
   ```python
   @pytest.fixture
   def bullish_market():
       return MarketData(net_gex=2e9, vix=15, trend="UP")
   ```

### DON'T

1. **Don't test external APIs directly**
   ```python
   # Bad: Depends on external service
   def test_tradier_order():
       result = tradier.place_order(...)  # Hits real API!
   ```

2. **Don't use sleep in tests**
   ```python
   # Bad: Slow and flaky
   def test_async_operation():
       start_operation()
       time.sleep(5)  # Don't do this
       assert operation_complete()
   ```

3. **Don't share state between tests**
   ```python
   # Bad: Tests depend on order
   global_counter = 0
   def test_increment():
       global_counter += 1
       assert global_counter == 1  # Fails if run after another test
   ```

---

## Debugging Failed Tests

### Verbose Output

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest --tb=long

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf
```

### Using pdb

```python
def test_complex_logic():
    result = complex_function(data)

    import pdb; pdb.set_trace()  # Debugger stops here

    assert result == expected
```

### Test Logging

```python
import logging

def test_with_logging(caplog):
    with caplog.at_level(logging.DEBUG):
        result = function_that_logs()

    assert "Expected log message" in caplog.text
```
